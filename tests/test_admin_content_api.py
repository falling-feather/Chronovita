import shutil
import sys
import unittest
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Thread

from fastapi import FastAPI
from fastapi.testclient import TestClient


API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import admin_content, courses as courses_router
from settings import settings
from services import content
from services.contracts.v1 import (
    ScenarioTemplateV1,
    calculate_contract_checksum,
    verify_contract_checksum,
)


class AdminContentApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-admin-content-api-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        content.configure(self.tmp_root)
        self.previous_token = settings.admin_token
        self.previous_actor = settings.admin_actor
        settings.admin_token = "test-admin-token"
        settings.admin_actor = "trusted-admin"
        app = FastAPI()
        app.include_router(admin_content.router, prefix="/api/v1/admin/content")
        app.include_router(courses_router.router, prefix="/api/v1/courses")
        self.client = TestClient(app)
        self.headers = {"X-Admin-Token": settings.admin_token}

    def tearDown(self):
        self.client.close()
        settings.admin_token = self.previous_token
        settings.admin_actor = self.previous_actor
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass
        content.configure()

    def test_auth_and_full_publication_api(self):
        payload = self._payload()
        unauthorized = self.client.post(
            "/api/v1/admin/content/drafts",
            json=payload,
        )
        self.assertEqual(unauthorized.status_code, 403)

        saved = self.client.post(
            "/api/v1/admin/content/drafts",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        lesson_id = payload["lesson_id"]
        course_id = payload["course_id"]

        early_seal = self.client.post(
            f"/api/v1/admin/content/drafts/{lesson_id}/seal",
            headers=self.headers,
            json={"sealed_by": "reviewer"},
        )
        self.assertEqual(early_seal.status_code, 409)
        self.assertEqual(early_seal.json()["detail"]["code"], "invalid_content_transition")

        validated = self.client.post(
            f"/api/v1/admin/content/drafts/{lesson_id}/validate",
            headers=self.headers,
            json={"actor": "author"},
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertEqual(validated.json()["workflow"]["state"], "validated")
        self.assertTrue(validated.json()["report"]["valid"])

        submitted = self.client.post(
            f"/api/v1/admin/content/drafts/{lesson_id}/submit-review",
            headers=self.headers,
            json={"actor": "author", "note": "Ready for review."},
        )
        self.assertEqual(submitted.json()["workflow"]["state"], "in_review")

        approved = self.client.post(
            f"/api/v1/admin/content/drafts/{lesson_id}/review",
            headers=self.headers,
            json={"actor": "reviewer", "decision": "approve", "note": "Checked."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["workflow"]["state"], "approved")

        sealed = self.client.post(
            f"/api/v1/admin/content/drafts/{lesson_id}/seal",
            headers=self.headers,
            json={"sealed_by": "reviewer"},
        )
        self.assertEqual(sealed.status_code, 200, sealed.text)
        self.assertEqual(sealed.json()["workflow"]["state"], "sealed")
        self.assertEqual(sealed.json()["item"]["sealed_by"], "trusted-admin")
        self.assertEqual(
            self.client.get(f"/api/v1/courses/{course_id}/lessons/{lesson_id}").status_code,
            404,
        )

        published = self.client.post(
            f"/api/v1/admin/content/sealed/{lesson_id}/versions/1/publish",
            headers=self.headers,
            json={"actor": "publisher", "note": "Release to students."},
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["workflow"]["state"], "published")
        self.assertEqual(published.json()["release"]["created_by"], "trusted-admin")
        self.assertEqual(
            {event["actor"] for event in published.json()["workflow"]["history"]},
            {"trusted-admin"},
        )
        release_id = published.json()["release"]["release_id"]

        public_lesson = self.client.get(
            f"/api/v1/courses/{course_id}/lessons/{lesson_id}"
        )
        self.assertEqual(public_lesson.status_code, 200, public_lesson.text)
        self.assertEqual(public_lesson.json()["content_status"], "published")
        self.assertEqual(public_lesson.json()["body"], payload["body"])
        self.assertEqual(public_lesson.json()["release_id"], release_id)
        self.assertEqual(public_lesson.json()["release_no"], 2)
        self.assertEqual(
            public_lesson.json()["release_checksum"],
            published.json()["release"]["checksum"],
        )

        current = self.client.get(
            f"/api/v1/admin/content/releases/{course_id}/current",
            headers=self.headers,
        )
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["release"]["release_id"], release_id)

        history = self.client.get(
            f"/api/v1/admin/content/releases?course_id={course_id}",
            headers=self.headers,
        ).json()["items"]
        bootstrap_id = history[0]["release_id"]
        rolled_back = self.client.post(
            f"/api/v1/admin/content/releases/{course_id}/rollback",
            headers=self.headers,
            json={
                "actor": "publisher",
                "target_release_id": bootstrap_id,
                "note": "Withdraw the first release.",
            },
        )
        self.assertEqual(rolled_back.status_code, 200, rolled_back.text)
        self.assertEqual(rolled_back.json()["release"]["operation"], "rollback")
        self.assertEqual(
            self.client.get(f"/api/v1/courses/{course_id}/lessons/{lesson_id}").status_code,
            404,
        )

    def test_public_api_returns_stable_503_for_corrupt_active_release(self):
        payload = self._payload()
        lesson_id = payload["lesson_id"]
        course_id = payload["course_id"]
        self.client.post(
            "/api/v1/admin/content/drafts",
            headers=self.headers,
            json=payload,
        )
        for path, body in (
            (f"/drafts/{lesson_id}/validate", {"actor": "author"}),
            (f"/drafts/{lesson_id}/submit-review", {"actor": "author"}),
            (
                f"/drafts/{lesson_id}/review",
                {"actor": "reviewer", "decision": "approve"},
            ),
            (f"/drafts/{lesson_id}/seal", {"sealed_by": "reviewer"}),
            (
                f"/sealed/{lesson_id}/versions/1/publish",
                {"actor": "publisher"},
            ),
        ):
            response = self.client.post(
                f"/api/v1/admin/content{path}",
                headers=self.headers,
                json=body,
            )
            self.assertEqual(response.status_code, 200, response.text)

        pointer_path = content.release_dir() / "active" / f"{course_id}.json"
        original_pointer = pointer_path.read_text(encoding="utf-8")
        pointer = json.loads(original_pointer)
        pointer["generation"] = 999
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

        response = self.client.get(f"/api/v1/courses/{course_id}/lessons/{lesson_id}")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "published_content_integrity_error",
        )

        pointer_path.write_text(original_pointer, encoding="utf-8")
        (content.sealed_dir() / f"{lesson_id}-v001.json").unlink()
        response = self.client.get(f"/api/v1/courses/{course_id}/lessons/{lesson_id}")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "published_content_integrity_error",
        )

    def test_invalid_identifier_is_rejected_without_writing_files(self):
        payload = self._payload()
        payload["lesson_id"] = "invalid-id\n"

        response = self.client.post(
            "/api/v1/admin/content/drafts",
            headers=self.headers,
            json=payload,
        )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(list(content.draft_dir().glob("*.json")), [])
        self.assertEqual(list(content.workflow_dir().glob("*.json")), [])

    def test_admin_can_stage_and_jointly_publish_a_scenario(self):
        payload = self._payload()
        self._seal_through_api(payload)
        scenario = self._scenario_payload(
            "api-joint-scenario",
            payload["course_id"],
            payload["lesson_id"],
        )

        unauthorized = self.client.post(
            "/api/v1/admin/content/runtime-scenarios",
            json=scenario,
        )
        self.assertEqual(unauthorized.status_code, 403)
        staged = self.client.post(
            "/api/v1/admin/content/runtime-scenarios",
            headers=self.headers,
            json=scenario,
        )
        self.assertEqual(staged.status_code, 200, staged.text)
        descriptor = staged.json()["item"]["descriptor"]
        self.assertEqual(
            self.client.get(
                f"/api/v1/courses/{payload['course_id']}/lessons/{payload['lesson_id']}"
            ).status_code,
            404,
        )
        listed = self.client.get(
            "/api/v1/admin/content/runtime-scenarios",
            headers=self.headers,
        )
        self.assertEqual(len(listed.json()["items"]), 1)

        published = self.client.post(
            f"/api/v1/admin/content/sealed/{payload['lesson_id']}/versions/1/publish",
            headers=self.headers,
            json={
                "scenarios": [
                    {
                        "scenario_id": descriptor["artifact_id"],
                        "scenario_version": descriptor["version"],
                        "scenario_checksum": descriptor["checksum"],
                        "primary": True,
                    }
                ]
            },
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["release"]["schema_version"], "course-release/v2")
        self.assertEqual(
            published.json()["release"]["items"][0]["primary_scenario_id"],
            scenario["scenario_id"],
        )
        lesson = self.client.get(
            f"/api/v1/courses/{payload['course_id']}/lessons/{payload['lesson_id']}"
        )
        self.assertEqual(lesson.status_code, 200, lesson.text)
        lesson_payload = lesson.json()
        release_payload = published.json()["release"]
        self.assertEqual(lesson_payload["release_id"], release_payload["release_id"])
        self.assertEqual(lesson_payload["release_no"], release_payload["release_no"])
        self.assertEqual(
            lesson_payload["release_checksum"],
            release_payload["checksum"],
        )
        self.assertEqual(lesson_payload["primary_scenario_id"], scenario["scenario_id"])
        self.assertEqual(
            lesson_payload["scenario_refs"],
            [
                {
                    "scenario_id": descriptor["artifact_id"],
                    "scenario_version": descriptor["version"],
                    "checksum": descriptor["checksum"],
                    "primary": True,
                }
            ],
        )

    def test_admin_can_save_validate_and_idempotently_seal_scenario_draft(self):
        template = self.client.get(
            "/api/v1/admin/content/scenario-drafts/template",
            headers=self.headers,
        )
        self.assertEqual(template.status_code, 200, template.text)
        payload = template.json()
        payload.update(
            {
                "scenario_id": "low-code-scenario",
                "course_id": "C-low-code",
                "lesson_id": "low-code-lesson",
                "title": "Low-code scenario",
            }
        )

        unauthorized = self.client.post(
            "/api/v1/admin/content/scenario-drafts",
            json=payload,
        )
        self.assertEqual(unauthorized.status_code, 403)
        saved = self.client.post(
            "/api/v1/admin/content/scenario-drafts",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["item"]["revision"], 1)
        self.assertEqual(saved.json()["item"]["updated_by"], "trusted-admin")

        reopened = self.client.get(
            "/api/v1/admin/content/scenario-drafts/low-code-scenario",
            headers=self.headers,
        )
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["title"], "Low-code scenario")
        listed = self.client.get(
            "/api/v1/admin/content/scenario-drafts",
            headers=self.headers,
        )
        self.assertEqual(listed.json()["items"][0]["scenario_id"], "low-code-scenario")

        validated = self.client.post(
            "/api/v1/admin/content/scenario-drafts/low-code-scenario/validate",
            headers=self.headers,
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertTrue(validated.json()["report"]["valid"])
        self.assertEqual(validated.json()["report"]["action_count"], 1)

        sealed = self.client.post(
            "/api/v1/admin/content/scenario-drafts/low-code-scenario/seal",
            headers=self.headers,
        )
        self.assertEqual(sealed.status_code, 200, sealed.text)
        self.assertFalse(sealed.json()["idempotent"])
        self.assertEqual(sealed.json()["item"]["scenario_version"], 1)
        sealed_contract = ScenarioTemplateV1.model_validate(sealed.json()["item"])
        self.assertTrue(verify_contract_checksum(sealed_contract))
        self.assertEqual(
            sealed.json()["item"]["checksum"],
            sealed.json()["record"]["descriptor"]["checksum"],
        )

        descriptor = sealed.json()["record"]["descriptor"]
        detail_url = (
            "/api/v1/admin/content/runtime-scenarios/low-code-scenario/versions/1"
        )
        unauthorized_detail = self.client.get(
            detail_url,
            params={
                "course_id": payload["course_id"],
                "lesson_id": payload["lesson_id"],
                "scenario_checksum": descriptor["checksum"],
            },
        )
        self.assertEqual(unauthorized_detail.status_code, 403)
        loaded_detail = self.client.get(
            detail_url,
            headers=self.headers,
            params={
                "course_id": payload["course_id"],
                "lesson_id": payload["lesson_id"],
                "scenario_checksum": descriptor["checksum"],
            },
        )
        self.assertEqual(loaded_detail.status_code, 200, loaded_detail.text)
        self.assertEqual(loaded_detail.json()["item"], sealed.json()["item"])
        self.assertEqual(loaded_detail.json()["descriptor"], descriptor)

        file_url = f"{detail_url}/file"
        unauthorized_file = self.client.get(
            file_url,
            params={
                "course_id": payload["course_id"],
                "lesson_id": payload["lesson_id"],
                "scenario_checksum": descriptor["checksum"],
            },
        )
        self.assertEqual(unauthorized_file.status_code, 403)
        downloaded_file = self.client.get(
            file_url,
            headers=self.headers,
            params={
                "course_id": payload["course_id"],
                "lesson_id": payload["lesson_id"],
                "scenario_checksum": descriptor["checksum"],
            },
        )
        self.assertEqual(downloaded_file.status_code, 200, downloaded_file.text)
        self.assertEqual(
            downloaded_file.content,
            (content.content_root() / descriptor["path"]).read_bytes(),
        )
        self.assertEqual(
            downloaded_file.headers["x-content-checksum"],
            descriptor["checksum"],
        )

        missing_identity = self.client.get(
            detail_url,
            headers=self.headers,
            params={
                "course_id": payload["course_id"],
                "lesson_id": payload["lesson_id"],
                "scenario_checksum": "0" * 64,
            },
        )
        self.assertEqual(missing_identity.status_code, 404, missing_identity.text)

        repeated = self.client.post(
            "/api/v1/admin/content/scenario-drafts/low-code-scenario/seal",
            headers=self.headers,
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertTrue(repeated.json()["idempotent"])
        self.assertEqual(repeated.json()["item"]["scenario_version"], 1)

        changed = reopened.json()
        changed["revision"] = 1
        changed["title"] = "Low-code scenario revised"
        updated = self.client.put(
            "/api/v1/admin/content/scenario-drafts/low-code-scenario",
            headers=self.headers,
            json=changed,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["item"]["revision"], 2)
        resealed = self.client.post(
            "/api/v1/admin/content/scenario-drafts/low-code-scenario/seal",
            headers=self.headers,
        )
        self.assertEqual(resealed.status_code, 200, resealed.text)
        self.assertEqual(resealed.json()["item"]["scenario_version"], 2)

    def test_scenario_draft_reports_cross_reference_errors_before_sealing(self):
        for scenario_id in (
            "invalid-unknown-ref",
            "invalid-duplicate-id",
            "invalid-variable-range",
            "invalid-missing-ending",
        ):
            with self.subTest(scenario_id=scenario_id):
                payload = self.client.get(
                    "/api/v1/admin/content/scenario-drafts/template",
                    headers=self.headers,
                ).json()
                payload["scenario_id"] = scenario_id
                if scenario_id == "invalid-unknown-ref":
                    payload["action_rules"][0]["effects"][0]["variable_id"] = (
                        "unknown-variable"
                    )
                elif scenario_id == "invalid-duplicate-id":
                    payload["variables"].append(dict(payload["variables"][0]))
                elif scenario_id == "invalid-variable-range":
                    payload["variables"][0]["initial"] = 200
                else:
                    payload["ending_rules"] = []

                saved = self.client.post(
                    "/api/v1/admin/content/scenario-drafts",
                    headers=self.headers,
                    json=payload,
                )
                self.assertEqual(saved.status_code, 200, saved.text)

                validated = self.client.post(
                    f"/api/v1/admin/content/scenario-drafts/{scenario_id}/validate",
                    headers=self.headers,
                )
                self.assertEqual(validated.status_code, 200, validated.text)
                self.assertFalse(validated.json()["report"]["valid"])
                self.assertTrue(validated.json()["report"]["issues"])

                sealed = self.client.post(
                    f"/api/v1/admin/content/scenario-drafts/{scenario_id}/seal",
                    headers=self.headers,
                )
                self.assertEqual(sealed.status_code, 422, sealed.text)
                self.assertEqual(
                    sealed.json()["detail"]["code"],
                    "scenario_draft_invalid",
                )
                self.assertTrue(sealed.json()["detail"]["issues"])
        self.assertEqual(list(content.runtime_scenario_dir().rglob("*.json")), [])

    def test_scenario_draft_optimistic_revision_rejects_stale_writes(self):
        payload = self.client.get(
            "/api/v1/admin/content/scenario-drafts/template",
            headers=self.headers,
        ).json()
        payload["scenario_id"] = "revision-guard-scenario"
        first = self.client.post(
            "/api/v1/admin/content/scenario-drafts",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(first.status_code, 200, first.text)

        current = first.json()["item"]
        current["title"] = "Current title"
        second = self.client.put(
            "/api/v1/admin/content/scenario-drafts/revision-guard-scenario",
            headers=self.headers,
            json=current,
        )
        self.assertEqual(second.status_code, 200, second.text)

        stale = first.json()["item"]
        stale["title"] = "Stale title"
        rejected = self.client.put(
            "/api/v1/admin/content/scenario-drafts/revision-guard-scenario",
            headers=self.headers,
            json=stale,
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(
            rejected.json()["detail"]["code"],
            "scenario_draft_conflict",
        )

    def test_scenario_draft_seal_ignores_unrelated_damaged_staged_file(self):
        staged = self.client.post(
            "/api/v1/admin/content/runtime-scenarios",
            headers=self.headers,
            json=self._scenario_payload(
                "unrelated-damaged-scenario",
                "C-unrelated",
                "unrelated-lesson",
            ),
        )
        self.assertEqual(staged.status_code, 200, staged.text)
        damaged_path = content.content_root() / Path(
            staged.json()["item"]["descriptor"]["path"]
        )
        damaged_path.write_text("{broken", encoding="utf-8")

        payload = self.client.get(
            "/api/v1/admin/content/scenario-drafts/template",
            headers=self.headers,
        ).json()
        payload.update(
            {
                "scenario_id": "healthy-author-scenario",
                "course_id": "C-healthy",
                "lesson_id": "healthy-lesson",
            }
        )
        saved = self.client.post(
            "/api/v1/admin/content/scenario-drafts",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        sealed = self.client.post(
            "/api/v1/admin/content/scenario-drafts/healthy-author-scenario/seal",
            headers=self.headers,
        )
        self.assertEqual(sealed.status_code, 200, sealed.text)
        self.assertEqual(sealed.json()["item"]["scenario_version"], 1)

    def test_concurrent_divergent_scenario_registration_has_one_winner(self):
        first = self._scenario_payload(
            "api-race-scenario",
            "C-api-race",
            "api-race-lesson",
        )
        second = dict(first)
        second["title"] = "Divergent scenario content"
        second["checksum"] = "0" * 64
        provisional = ScenarioTemplateV1.model_validate(second)
        second["checksum"] = calculate_contract_checksum(provisional)
        second = ScenarioTemplateV1.model_validate(second).model_dump(mode="json")
        barrier = Barrier(2)
        responses = []

        def register(payload):
            barrier.wait(2)
            responses.append(
                self.client.post(
                    "/api/v1/admin/content/runtime-scenarios",
                    headers=self.headers,
                    json=payload,
                )
            )

        threads = [Thread(target=register, args=(payload,)) for payload in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        conflict = next(response for response in responses if response.status_code == 409)
        self.assertEqual(conflict.json()["detail"]["code"], "content_conflict")
        self.assertEqual(len(list(content.runtime_scenario_dir().rglob("*.json"))), 1)

        invalid = dict(first)
        invalid["checksum"] = "0" * 64
        rejected = self.client.post(
            "/api/v1/admin/content/runtime-scenarios",
            headers=self.headers,
            json=invalid,
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertEqual(
            rejected.json()["detail"]["code"],
            "content_validation_failed",
        )

    def test_legacy_bootstrap_is_explicit_and_admin_sealed_reads_fail_stably(self):
        payload = self._payload()
        payload["lesson_id"] = "legacy-api-lesson"
        payload["course_id"] = "C-legacy-api"
        self._seal_through_api(payload)

        self.assertEqual(
            self.client.get(
                "/api/v1/courses/C-legacy-api/lessons/legacy-api-lesson"
            ).status_code,
            404,
        )
        migrated = self.client.post(
            "/api/v1/admin/content/releases/C-legacy-api/bootstrap-legacy",
            headers=self.headers,
            json={
                "actor": "spoofed-migrator",
                "note": "Explicit migration.",
                "selections": [
                    {"lesson_id": "legacy-api-lesson", "content_version": 1}
                ],
            },
        )
        self.assertEqual(migrated.status_code, 200, migrated.text)
        self.assertEqual(migrated.json()["release"]["created_by"], "trusted-admin")
        legacy_lesson = self.client.get(
            "/api/v1/courses/C-legacy-api/lessons/legacy-api-lesson"
        )
        self.assertEqual(legacy_lesson.status_code, 200, legacy_lesson.text)
        self.assertEqual(legacy_lesson.json()["scenario_refs"], [])
        self.assertIsNone(legacy_lesson.json()["primary_scenario_id"])

        source_path = content.sealed_dir() / "legacy-api-lesson-v001.json"
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        raw["title"] = "tampered"
        source_path.write_text(json.dumps(raw), encoding="utf-8")
        response = self.client.get(
            "/api/v1/admin/content/sealed",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "content_integrity_error")

    def test_invalid_legacy_seal_stays_private_and_migration_is_rejected(self):
        package = content.content_template()
        package.lesson_id = "invalid-legacy-api"
        package.course_id = "C-invalid-legacy-api"
        package.title = "Invalid legacy package"
        package.unit = "Migration boundary"
        package.era = "Test era"
        package.body = []
        package.keywords = []
        package.people = []
        package.facts = []
        package.source_refs = []
        package.status = "sealed"
        package.version = 1
        package.sealed_at = datetime.now(timezone.utc)
        package.updated_at = package.sealed_at
        package.sealed_by = "legacy-import"
        package.checksum = content.package_checksum(package)
        package = content.LessonContentPackage.model_validate(package.model_dump(mode="json"))
        content._atomic_write_json(
            content.sealed_dir() / "invalid-legacy-api-v001.json",
            package.model_dump(mode="json"),
            overwrite=False,
        )

        public = self.client.get(
            "/api/v1/courses/C-invalid-legacy-api/lessons/invalid-legacy-api"
        )
        self.assertEqual(public.status_code, 404, public.text)

        migrated = self.client.post(
            "/api/v1/admin/content/releases/C-invalid-legacy-api/bootstrap-legacy",
            headers=self.headers,
            json={
                "selections": [
                    {"lesson_id": "invalid-legacy-api", "content_version": 1}
                ]
            },
        )
        self.assertEqual(migrated.status_code, 422, migrated.text)
        self.assertEqual(
            migrated.json()["detail"]["code"],
            "content_validation_failed",
        )
        self.assertEqual(content.load_published_snapshots(), [])

    def _seal_through_api(self, payload: dict) -> None:
        lesson_id = payload["lesson_id"]
        saved = self.client.post(
            "/api/v1/admin/content/drafts",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        for path, body in (
            (f"/drafts/{lesson_id}/validate", {"actor": "spoofed-author"}),
            (f"/drafts/{lesson_id}/submit-review", {"actor": "spoofed-author"}),
            (
                f"/drafts/{lesson_id}/review",
                {"actor": "spoofed-reviewer", "decision": "approve"},
            ),
            (f"/drafts/{lesson_id}/seal", {"sealed_by": "spoofed-reviewer"}),
        ):
            response = self.client.post(
                f"/api/v1/admin/content{path}",
                headers=self.headers,
                json=body,
            )
            self.assertEqual(response.status_code, 200, response.text)

    @staticmethod
    def _payload() -> dict:
        package = content.content_template()
        package.lesson_id = "api-workflow-lesson"
        package.course_id = "C-api-workflow"
        package.course_title = "API Workflow Course"
        package.title = "API Workflow Lesson"
        package.unit = "API Workflow Unit"
        package.era = "Test era"
        package.body = ["First paragraph.", "Second paragraph.", "Third paragraph."]
        return package.model_dump(mode="json")

    @staticmethod
    def _scenario_payload(scenario_id: str, course_id: str, lesson_id: str) -> dict:
        now = datetime.now(timezone.utc)
        payload = {
            "scenario_id": scenario_id,
            "scenario_version": 1,
            "status": "sealed",
            "course_id": course_id,
            "lesson_id": lesson_id,
            "title": "API joint scenario",
            "scenario_type": "crisis_governance",
            "student_role": "Decision maker",
            "objective": "Reach a valid ending",
            "opening": "The situation requires a decision.",
            "variables": [
                {
                    "variable_id": "progress",
                    "label": "Progress",
                    "initial": 0,
                    "minimum": 0,
                    "maximum": 10,
                }
            ],
            "action_rules": [
                {
                    "action_id": "advance",
                    "label": "Advance",
                    "effects": [
                        {
                            "kind": "state",
                            "variable_id": "progress",
                            "operation": "add",
                            "value": 1,
                        }
                    ],
                }
            ],
            "ending_rules": [
                {
                    "ending_id": "complete",
                    "title": "Complete",
                    "conditions": [
                        {
                            "kind": "state",
                            "variable_id": "progress",
                            "operator": "gte",
                            "value": 1,
                        }
                    ],
                    "summary": "The decision reached the ending.",
                }
            ],
            "sealed_at": now,
            "sealed_by": "scenario-reviewer",
            "checksum": "0" * 64,
        }
        provisional = ScenarioTemplateV1.model_validate(payload)
        payload["checksum"] = calculate_contract_checksum(provisional)
        return ScenarioTemplateV1.model_validate(payload).model_dump(mode="json")


if __name__ == "__main__":
    unittest.main()
