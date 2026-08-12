from __future__ import annotations

import inspect
import json
import shutil
import sys
import time
import unittest
import uuid
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from threading import Barrier, Thread
from unittest.mock import Mock, patch
from zipfile import ZipFile

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import admin_content, auth as auth_router
from auth_dependencies import AuthContext
from settings import settings
from services import content, persistence
from services.content import workflow as content_workflow
from services.content import evidence_workflow
from services.contracts.evidence_v1 import EvidencePassageV1, EvidenceSourceV1
from services.contracts.archive_examples import build_dayu_publish_request
from services.auth import (
    AuthServiceConfig,
    Principal,
    configure_identity,
    get_identity,
    shutdown_identity,
)
from services.auth.store import AuthStoreError


class ContentRbacApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-content-rbac-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.content_root = self.tmp_root / "content"
        self.sqlite_path = self.tmp_root / "chronovita.db"
        content.configure(self.content_root)
        self.previous = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "admin_token": settings.admin_token,
            "admin_actor": settings.admin_actor,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_cookie_name = "chronovita_rbac_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        settings.admin_token = ""

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            engine = persistence.init_engine(str(self.sqlite_path))
            try:
                configure_identity(
                    engine,
                    AuthServiceConfig(
                        mode=settings.auth_mode,
                        session_ttl_seconds=settings.auth_session_ttl_seconds,
                        bootstrap_username=settings.auth_bootstrap_username,
                        bootstrap_password=settings.auth_bootstrap_password,
                        bootstrap_display_name=settings.auth_bootstrap_display_name,
                    ),
                )
                yield
            finally:
                shutdown_identity()
                persistence.close_engine()

        app = FastAPI(lifespan=lifespan)
        app.include_router(auth_router.router, prefix="/api/v1/auth")
        app.include_router(admin_content.router, prefix="/api/v1/admin/content")
        self.client = TestClient(app)
        self.client.__enter__()

        self.admin = self._login("root.admin", "Root password 123!")
        self.teacher_a = self._create_account("teacher.a", ("teacher",))
        self.teacher_b = self._create_account("teacher.b", ("teacher",))
        self.reviewer = self._create_account("reviewer.a", ("reviewer",))
        self.student = self._create_account("student.a", ("student",))
        self.dual_role = self._create_account(
            "teacher.reviewer",
            ("teacher", "reviewer"),
        )

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for key, value in self.previous.items():
            setattr(settings, key, value)
        content.configure()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_direct_publication_requires_an_explicit_admin_role(self):
        reviewer_context = AuthContext(
            principal=Principal(
                user_id="reviewer",
                username="reviewer.a",
                display_name="Reviewer",
                roles=("reviewer",),
                auth_version=1,
            ),
            raw_token=None,
            source="bearer",
        )
        with self.assertRaises(HTTPException) as caught:
            admin_content._require_direct_commit_admin(
                reviewer_context,
                "direct_commit",
            )
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(
            caught.exception.detail["code"],
            "admin_role_required",
        )

        admin_context = reviewer_context.__class__(
            principal=reviewer_context.principal.model_copy(
                update={"roles": ("admin",)}
            ),
            raw_token=None,
            source="bearer",
        )
        admin_content._require_direct_commit_admin(
            admin_context,
            "direct_commit",
        )

    def test_person_asset_can_be_saved_sealed_and_downloaded_by_role(self):
        person = self.client.get(
            "/api/v1/admin/content/assets/people/template",
            headers=self.teacher_a["headers"],
        ).json()
        person.update(
            {
                "asset_id": "api-person-history",
                "name": "API 样板人物",
                "summary": "用于验证人物档案封存与归档下载。",
            }
        )
        saved = self.client.post(
            "/api/v1/admin/content/assets/people",
            headers=self.teacher_a["headers"],
            json=person,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["item"]["status"], "draft")

        denied = self.client.post(
            "/api/v1/admin/content/assets/people/api-person-history/seal",
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        validated = self.client.post(
            "/api/v1/admin/content/assets/people/api-person-history/validate",
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertTrue(validated.json()["report"]["valid"])

        sealed = self.client.post(
            "/api/v1/admin/content/assets/people/api-person-history/seal",
            headers=self.admin["headers"],
        )
        self.assertEqual(sealed.status_code, 200, sealed.text)
        sealed_body = sealed.json()
        self.assertEqual(sealed_body["item"]["version"], 1)
        self.assertEqual(
            sealed_body["item"]["sealed_by"],
            self.admin["user_id"],
        )
        self.assertFalse(sealed_body["idempotent"])

        versions = self.client.get(
            "/api/v1/admin/content/assets/people/api-person-history/versions",
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(versions.status_code, 200, versions.text)
        self.assertEqual(
            [
                (item["version"], item["checksum"])
                for item in versions.json()["items"]
            ],
            [(1, sealed_body["item"]["checksum"])],
        )

        archive_url = (
            "/api/v1/admin/content/asset-archives/person/"
            "api-person-history/versions/1"
        )
        query = {"source_checksum": sealed_body["item"]["checksum"]}
        preview = self.client.post(
            f"{archive_url}/preview",
            params=query,
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["archive"]["asset_kind"], "person")
        self.assertEqual(preview.json()["archive"]["version"], 1)

        downloaded = self.client.get(
            f"{archive_url}/archive.zip",
            params=query,
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        self.assertIn(
            "filename*=UTF-8''",
            downloaded.headers["content-disposition"],
        )
        with ZipFile(BytesIO(downloaded.content)) as bundle:
            names = bundle.namelist()
            self.assertEqual(len(names), 2)
            manifest_name = next(
                name for name in names if name.endswith("归档清单.json")
            )
            manifest = json.loads(bundle.read(manifest_name))
        self.assertEqual(
            manifest["archive_checksum"],
            preview.json()["archive"]["archive_checksum"],
        )

        missing = self.client.post(
            (
                "/api/v1/admin/content/asset-archives/person/"
                "missing-person/versions/1/preview"
            ),
            params=query,
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(missing.status_code, 404, missing.text)

        invalid_version = self.client.post(
            (
                "/api/v1/admin/content/asset-archives/person/"
                "api-person-history/versions/0/preview"
            ),
            params=query,
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(invalid_version.status_code, 422, invalid_version.text)

        invalid_checksum = self.client.post(
            f"{archive_url}/preview",
            params={"source_checksum": "not-a-checksum"},
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(invalid_checksum.status_code, 422, invalid_checksum.text)

        changed = self.client.post(
            f"{archive_url}/preview",
            params={"source_checksum": "f" * 64},
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(changed.status_code, 409, changed.text)

    def test_role_matrix_ownership_spoofing_and_audit_chain(self):
        self._assert_every_content_route_has_the_expected_permission()
        self.assertEqual(
            self.client.get(
                "/api/v1/admin/content/template",
                headers=self.student["headers"],
            ).status_code,
            403,
        )
        for account in (self.teacher_a, self.reviewer, self.admin):
            response = self.client.get(
                "/api/v1/admin/content/template",
                headers=account["headers"],
            )
            self.assertEqual(response.status_code, 200, response.text)

        payload = self._lesson_payload("rbac-owned-lesson", "C-rbac-owned")
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/content/drafts",
                headers=self.reviewer["headers"],
                json=payload,
            ).status_code,
            403,
        )
        saved = self.client.post(
            "/api/v1/admin/content/drafts",
            headers=self.teacher_a["headers"],
            json=payload,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(
            saved.json()["workflow"]["history"][-1]["actor"],
            self.teacher_a["user_id"],
        )

        foreign_update = self.client.put(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}",
            headers=self.teacher_b["headers"],
            json=payload,
        )
        self.assertEqual(foreign_update.status_code, 403, foreign_update.text)
        self.assertEqual(
            foreign_update.json()["detail"]["code"],
            "content_owner_required",
        )

        validated = self.client.post(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}/validate",
            headers=self.teacher_a["headers"],
            json={"actor": "forged-validator"},
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        submitted = self.client.post(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}/submit-review",
            headers=self.teacher_a["headers"],
            json={"actor": "forged-author", "note": "Ready."},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(
            {event["actor"] for event in submitted.json()["workflow"]["history"]},
            {self.teacher_a["user_id"]},
        )

        teacher_review = self.client.post(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}/review",
            headers=self.teacher_a["headers"],
            json={"decision": "approve"},
        )
        self.assertEqual(teacher_review.status_code, 403, teacher_review.text)
        approved = self.client.post(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}/review",
            headers=self.reviewer["headers"],
            json={
                "actor": "forged-reviewer",
                "decision": "approve",
                "note": "Reviewed.",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(
            approved.json()["workflow"]["history"][-1]["actor"],
            self.reviewer["user_id"],
        )

        reviewer_seal = self.client.post(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}/seal",
            headers=self.reviewer["headers"],
            json={"sealed_by": "forged-sealer"},
        )
        self.assertEqual(reviewer_seal.status_code, 403, reviewer_seal.text)
        sealed = self.client.post(
            f"/api/v1/admin/content/drafts/{payload['lesson_id']}/seal",
            headers=self.admin["headers"],
            json={"sealed_by": "forged-sealer"},
        )
        self.assertEqual(sealed.status_code, 200, sealed.text)
        self.assertEqual(sealed.json()["item"]["sealed_by"], self.admin["user_id"])

        reviewer_publish = self.client.post(
            f"/api/v1/admin/content/sealed/{payload['lesson_id']}/versions/1/publish",
            headers=self.reviewer["headers"],
            json={"actor": "forged-publisher"},
        )
        self.assertEqual(reviewer_publish.status_code, 403, reviewer_publish.text)
        published = self.client.post(
            f"/api/v1/admin/content/sealed/{payload['lesson_id']}/versions/1/publish",
            headers=self.admin["headers"],
            json={"actor": "forged-publisher"},
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(
            published.json()["release"]["created_by"],
            self.admin["user_id"],
        )

        keyword = self.client.get(
            "/api/v1/admin/content/assets/keywords/template",
            headers=self.teacher_a["headers"],
        ).json()
        keyword.update(
            {
                "asset_id": "rbac-keyword",
                "word": "Test keyword",
                "gloss": "Test-only reference entry.",
            }
        )
        saved_keyword = self.client.post(
            "/api/v1/admin/content/assets/keywords",
            headers=self.teacher_a["headers"],
            json=keyword,
        )
        self.assertEqual(saved_keyword.status_code, 200, saved_keyword.text)
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/content/assets/keywords",
                headers=self.reviewer["headers"],
                json=keyword,
            ).status_code,
            403,
        )

        dual_payload = self._lesson_payload("rbac-self-review", "C-rbac-self")
        self._save_validate_submit(dual_payload, self.dual_role)
        self_review = self.client.post(
            f"/api/v1/admin/content/drafts/{dual_payload['lesson_id']}/review",
            headers=self.dual_role["headers"],
            json={"decision": "approve"},
        )
        self.assertEqual(self_review.status_code, 403, self_review.text)
        self.assertEqual(
            self_review.json()["detail"]["code"],
            "self_review_forbidden",
        )

        audit = self.client.get(
            "/api/v1/auth/audit?limit=500",
            headers=self.admin["headers"],
        )
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertTrue(audit.json()["valid_chain"])
        content_events = [
            item for item in audit.json()["items"] if item["action"].startswith("content.")
        ]
        self.assertTrue(content_events)
        self.assertNotIn(
            "forged-author",
            {item["actor_user_id"] for item in content_events},
        )
        self.assertTrue(
            {
                "content.draft.save.authorize",
                "content.draft.approve.authorize",
                "content.draft.seal.authorize",
                "content.release.publish.authorize",
                "content.keyword.save.authorize",
            }.issubset({item["action"] for item in content_events})
        )

    def test_required_audit_failure_blocks_content_write(self):
        payload = self._lesson_payload("rbac-audit-block", "C-rbac-audit")
        with patch.object(
            get_identity().store,
            "append_audit",
            side_effect=AuthStoreError("forced audit outage"),
        ):
            response = self.client.post(
                "/api/v1/admin/content/drafts",
                headers=self.teacher_a["headers"],
                json=payload,
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "auth_storage_unavailable")
        self.assertIsNone(content.get_draft(payload["lesson_id"]))
        self.assertIsNone(content_workflow.get_workflow(payload["lesson_id"]))

        publication_factory = Mock()
        with (
            patch.object(
                get_identity().store,
                "append_audit",
                side_effect=AuthStoreError("forced publication audit outage"),
            ),
            patch.object(
                admin_content,
                "_new_publication_service",
                publication_factory,
            ),
        ):
            publication = self.client.post(
                "/api/v1/admin/content/publications",
                headers=self.admin["headers"],
                json=build_dayu_publish_request().model_dump(mode="json"),
            )
        self.assertEqual(publication.status_code, 503, publication.text)
        self.assertEqual(
            publication.json()["detail"]["code"],
            "auth_storage_unavailable",
        )
        publication_factory.assert_not_called()

        seed_lesson = self._lesson_payload(
            "rbac-evidence-audit-lesson",
            payload["course_id"],
        )
        content.save_draft(
            content.LessonContentPackage.model_validate(seed_lesson),
            saved_by=self.teacher_a["user_id"],
        )
        evidence = self._evidence_payload(
            "rbac-evidence-audit",
            payload["course_id"],
            seed_lesson["lesson_id"],
        )
        with patch.object(
            get_identity().store,
            "append_audit",
            side_effect=AuthStoreError("forced evidence audit outage"),
        ):
            response = self.client.post(
                "/api/v1/admin/content/evidence-drafts",
                headers=self.teacher_a["headers"],
                json=evidence,
            )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIsNone(
            evidence_workflow.get_evidence_draft("rbac-evidence-audit")
        )

    def test_evidence_role_matrix_and_self_review(self):
        lesson = self._lesson_payload("rbac-evidence-lesson", "C-rbac-evidence")
        saved_lesson = self.client.post(
            "/api/v1/admin/content/drafts",
            headers=self.teacher_a["headers"],
            json=lesson,
        )
        self.assertEqual(saved_lesson.status_code, 200, saved_lesson.text)
        evidence = self._evidence_payload(
            "rbac-evidence",
            lesson["course_id"],
            lesson["lesson_id"],
        )

        self.assertEqual(
            self.client.post(
                "/api/v1/admin/content/evidence-drafts",
                headers=self.reviewer["headers"],
                json=evidence,
            ).status_code,
            403,
        )
        saved = self.client.post(
            "/api/v1/admin/content/evidence-drafts",
            headers=self.teacher_a["headers"],
            json=evidence,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(
            saved.json()["item"]["created_by"],
            self.teacher_a["user_id"],
        )
        self.assertEqual(
            self.client.put(
                "/api/v1/admin/content/evidence-drafts/rbac-evidence",
                headers=self.teacher_b["headers"],
                json=saved.json()["item"],
            ).status_code,
            403,
        )
        validated = self.client.post(
            "/api/v1/admin/content/evidence-drafts/rbac-evidence/validate",
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        submitted = self.client.post(
            "/api/v1/admin/content/evidence-drafts/rbac-evidence/submit-review",
            headers=self.teacher_a["headers"],
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        approved = self.client.post(
            "/api/v1/admin/content/evidence-drafts/rbac-evidence/review",
            headers=self.reviewer["headers"],
            json={"decision": "approve", "note": "Evidence reviewed."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(
            approved.json()["workflow"]["history"][-1]["actor"],
            self.reviewer["user_id"],
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/content/evidence-drafts/rbac-evidence/seal",
                headers=self.teacher_a["headers"],
            ).status_code,
            403,
        )
        sealed = self.client.post(
            "/api/v1/admin/content/evidence-drafts/rbac-evidence/seal",
            headers=self.admin["headers"],
        )
        self.assertEqual(sealed.status_code, 200, sealed.text)

        dual_lesson = self._lesson_payload(
            "rbac-dual-evidence-lesson",
            "C-rbac-dual-evidence",
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/admin/content/drafts",
                headers=self.dual_role["headers"],
                json=dual_lesson,
            ).status_code,
            200,
        )
        dual_evidence = self._evidence_payload(
            "rbac-dual-evidence",
            dual_lesson["course_id"],
            dual_lesson["lesson_id"],
        )
        for path in (
            "/evidence-drafts",
            "/evidence-drafts/rbac-dual-evidence/validate",
            "/evidence-drafts/rbac-dual-evidence/submit-review",
        ):
            response = self.client.post(
                f"/api/v1/admin/content{path}",
                headers=self.dual_role["headers"],
                json=dual_evidence if path == "/evidence-drafts" else {},
            )
            self.assertEqual(response.status_code, 200, response.text)
        self_review = self.client.post(
            "/api/v1/admin/content/evidence-drafts/rbac-dual-evidence/review",
            headers=self.dual_role["headers"],
            json={"decision": "approve"},
        )
        self.assertEqual(self_review.status_code, 403, self_review.text)
        self.assertEqual(
            self_review.json()["detail"]["code"],
            "self_review_forbidden",
        )

    def test_concurrent_first_save_assigns_one_author(self):
        payload = self._lesson_payload("rbac-owner-race", "C-rbac-race")
        start = Barrier(2)
        results: list[tuple[str, int]] = []
        original_check = admin_content._require_lesson_author

        def delayed_check(context, lesson_id, *, allow_missing=False):
            original_check(context, lesson_id, allow_missing=allow_missing)
            if allow_missing and content_workflow.get_workflow(lesson_id) is None:
                time.sleep(0.15)

        def save(name: str, account: dict) -> None:
            start.wait()
            response = self.client.post(
                "/api/v1/admin/content/drafts",
                headers=account["headers"],
                json=payload,
            )
            results.append((name, response.status_code))

        with patch.object(
            admin_content,
            "_require_lesson_author",
            side_effect=delayed_check,
        ):
            threads = [
                Thread(target=save, args=("a", self.teacher_a)),
                Thread(target=save, args=("b", self.teacher_b)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(status for _, status in results), [200, 403])
        winner = next(name for name, status_code in results if status_code == 200)
        expected_owner = self.teacher_a if winner == "a" else self.teacher_b
        workflow = content_workflow.get_workflow(payload["lesson_id"])
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.history[0].actor, expected_owner["user_id"])

    def _create_account(self, username: str, roles: tuple[str, ...]) -> dict:
        created = self.client.post(
            "/api/v1/auth/users",
            headers=self.admin["headers"],
            json={
                "username": username,
                "password": f"Password for {username} 123!",
                "display_name": username,
                "roles": list(roles),
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        account = self._login(username, f"Password for {username} 123!")
        account["user_id"] = created.json()["user_id"]
        return account

    def _login(self, username: str, password: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/token",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.cookies.clear()
        body = response.json()
        return {
            "user_id": body["principal"]["user_id"],
            "headers": {"Authorization": f"Bearer {body['access_token']}"},
        }

    def _save_validate_submit(self, payload: dict, account: dict) -> None:
        lesson_id = payload["lesson_id"]
        for path, body in (
            ("/drafts", payload),
            (f"/drafts/{lesson_id}/validate", {}),
            (f"/drafts/{lesson_id}/submit-review", {}),
        ):
            response = self.client.post(
                f"/api/v1/admin/content{path}",
                headers=account["headers"],
                json=body,
            )
            self.assertEqual(response.status_code, 200, response.text)

    def _assert_every_content_route_has_the_expected_permission(self) -> None:
        prefix = "/api/v1/admin/content"
        write_permissions = {
            ("POST", f"{prefix}/drafts"): "content.author",
            ("PUT", f"{prefix}/drafts/{{lesson_id}}"): "content.author",
            ("POST", f"{prefix}/preview"): "content.read",
            ("POST", f"{prefix}/drafts/{{lesson_id}}/validate"): "content.author",
            ("POST", f"{prefix}/drafts/{{lesson_id}}/submit-review"): "content.author",
            ("POST", f"{prefix}/drafts/{{lesson_id}}/review"): "content.review",
            ("POST", f"{prefix}/drafts/{{lesson_id}}/seal"): "content.publish",
            ("POST", f"{prefix}/evidence-drafts"): "content.author",
            (
                "PUT",
                f"{prefix}/evidence-drafts/{{corpus_id}}",
            ): "content.author",
            (
                "POST",
                f"{prefix}/evidence-drafts/{{corpus_id}}/validate",
            ): "content.author",
            (
                "POST",
                f"{prefix}/evidence-drafts/{{corpus_id}}/submit-review",
            ): "content.author",
            (
                "POST",
                f"{prefix}/evidence-drafts/{{corpus_id}}/review",
            ): "content.review",
            (
                "POST",
                f"{prefix}/evidence-drafts/{{corpus_id}}/seal",
            ): "content.publish",
            (
                "POST",
                f"{prefix}/lesson-presentations",
            ): "content.publish",
            ("POST", f"{prefix}/runtime-scenarios"): "content.publish",
            ("POST", f"{prefix}/scenario-drafts"): "content.author",
            ("PUT", f"{prefix}/scenario-drafts/{{scenario_id}}"): "content.author",
            (
                "POST",
                f"{prefix}/scenario-drafts/{{scenario_id}}/validate",
            ): "content.author",
            (
                "POST",
                f"{prefix}/scenario-drafts/{{scenario_id}}/seal",
            ): "content.publish",
            (
                "POST",
                f"{prefix}/sealed/{{lesson_id}}/versions/{{version}}/publish",
            ): "content.publish",
            (
                "POST",
                f"{prefix}/releases/{{course_id}}/bootstrap-legacy",
            ): "content.publish",
            (
                "POST",
                (
                    f"{prefix}/releases/{{course_id}}/{{release_id}}/"
                    "archive-preview"
                ),
            ): "content.read",
            (
                "POST",
                (
                    f"{prefix}/asset-archives/{{asset_kind}}/{{asset_id}}/"
                    "versions/{version}/preview"
                ),
            ): "content.read",
            ("POST", f"{prefix}/publications"): "content.publish",
            (
                "POST",
                f"{prefix}/publications/{{publication_id}}/retry",
            ): "content.publish",
            ("POST", f"{prefix}/asset-publications"): "content.publish",
            (
                "POST",
                f"{prefix}/asset-publications/{{publication_id}}/retry",
            ): "content.publish",
            (
                "POST",
                f"{prefix}/releases/{{course_id}}/rollback",
            ): "content.publish",
            ("POST", f"{prefix}/assets/people"): "content.author",
            (
                "POST",
                f"{prefix}/assets/people/{{asset_id}}/validate",
            ): "content.author",
            (
                "POST",
                f"{prefix}/assets/people/{{asset_id}}/seal",
            ): "content.publish",
            ("POST", f"{prefix}/assets/keywords"): "content.author",
            (
                "POST",
                f"{prefix}/assets/keywords/{{asset_id}}/validate",
            ): "content.author",
            (
                "POST",
                f"{prefix}/assets/keywords/{{asset_id}}/seal",
            ): "content.publish",
        }
        seen_writes: set[tuple[str, str]] = set()
        for route in admin_content.router.routes:
            if not isinstance(route, APIRoute):
                continue
            full_path = f"{prefix}{route.path}"
            permission = None
            for dependency in route.dependant.dependencies:
                closure = inspect.getclosurevars(dependency.call)
                if "permission" in closure.nonlocals:
                    permission = closure.nonlocals["permission"]
                    break
            self.assertIsNotNone(permission, f"unguarded content route: {full_path}")
            for method in route.methods:
                key = (method, full_path)
                expected = "content.read" if method == "GET" else write_permissions.get(key)
                self.assertIsNotNone(expected, f"unclassified content route: {key}")
                self.assertEqual(permission, expected, f"wrong permission for {key}")
                if method != "GET":
                    seen_writes.add(key)
        self.assertEqual(seen_writes, set(write_permissions))

    @staticmethod
    def _lesson_payload(lesson_id: str, course_id: str) -> dict:
        package = content.content_template()
        package.lesson_id = lesson_id
        package.course_id = course_id
        package.course_title = "RBAC Test Course"
        package.title = "RBAC Test Lesson"
        package.unit = "RBAC Test Unit"
        package.era = "Test era"
        package.body = ["First paragraph.", "Second paragraph.", "Third paragraph."]
        return package.model_dump(mode="json")

    @staticmethod
    def _evidence_payload(corpus_id: str, course_id: str, lesson_id: str) -> dict:
        from services.contracts.v1 import course_package_from_legacy

        package = course_package_from_legacy(content.get_draft(lesson_id))
        source = EvidenceSourceV1(
            source_id=f"source-{corpus_id}",
            title="RBAC reviewed source",
            kind="research",
            url_or_path="https://example.test/rbac",
            rights_note="Self-authored summary for authorization tests.",
        )
        passage = EvidencePassageV1(
            passage_id=f"passage-{corpus_id}",
            source_id=source.source_id,
            title="RBAC evidence passage",
            text="A stable evidence passage for authorization tests.",
            summary="Authorization test summary.",
            fact_ids=(package.facts[0].fact_id,),
            person_ids=(package.people[0].person_id,),
            evidence_kind="teaching_explanation",
            certainty="interpretation",
            chronology_note="Modern authorization test material.",
        )
        return evidence_workflow.EvidenceCorpusDraftV1(
            corpus_id=corpus_id,
            course_id=course_id,
            lesson_id=lesson_id,
            title="RBAC evidence corpus",
            scope_note="Bound to one authorization test lesson.",
            sources=(source,),
            passages=(passage,),
        ).model_dump(mode="json")

if __name__ == "__main__":
    unittest.main()
