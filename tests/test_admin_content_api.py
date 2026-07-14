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
from services.contracts.v1 import ScenarioTemplateV1, calculate_contract_checksum


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
        self.assertEqual(
            self.client.get(
                f"/api/v1/courses/{payload['course_id']}/lessons/{payload['lesson_id']}"
            ).status_code,
            200,
        )

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
        self.assertEqual(
            self.client.get(
                "/api/v1/courses/C-legacy-api/lessons/legacy-api-lesson"
            ).status_code,
            200,
        )

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
