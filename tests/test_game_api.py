import json
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from main import app
from routers import game as game_router
from settings import settings
from services import content
from services.game_runtime import (
    RevisionConflict,
    RuntimeCommandV1,
    ScenarioFileError,
    ScenarioIntegrityError,
)
from services.game_runtime.catalog import (
    ScenarioCatalogRepository,
    ScenarioCatalogV1,
)
from services.game_runtime.service import (
    GameRuntimeService,
    PublishedScenarioPinRequired,
    ScenarioReleasePinV1,
    configure_game_runtime,
    get_game_runtime,
)
from services.game_runtime.store import GameRuntimeStore


class GameApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous = {
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
            "game_user_id": settings.game_user_id,
            "sqlite_path": settings.sqlite_path,
        }
        settings.content_root = str(REPO_ROOT / "content")
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        settings.game_user_id = "api-student"
        settings.sqlite_path = str(Path(self.temp_dir.name) / "chronovita.db")
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for key, value in self.previous.items():
            setattr(settings, key, value)
        content.configure()
        self.temp_dir.cleanup()

    def test_catalog_start_turn_get_and_complete_without_client_state(self):
        listed = self.client.get("/api/v1/practice/game/scenarios")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()["items"]), 2)
        self.assertEqual(listed.json()["session_storage"], "sqlite-json")
        self.assertEqual(
            {item["audience"] for item in listed.json()["items"]},
            {"development"},
        )

        started = self.client.post(
            "/api/v1/practice/game/sessions",
            json={
                "scenario_id": "scenario-dayu-flood-control",
                "client_request_id": "api-start-complete-001",
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        session = started.json()["session"]
        session_id = session["session_id"]
        self.assertEqual(session["user_id"], "api-student")
        self.assertNotIn("state", started.json()["scenario"])
        self.assertIsNone(started.json()["scenario"]["release_id"])
        self.assertIsNone(started.json()["scenario"]["release_no"])
        self.assertIsNone(started.json()["scenario"]["release_checksum"])

        specs = [
            ("survey-terrain", "先勘察地势和河道"),
            ("explain-plan", "向各部族解释疏导计划"),
            ("open-channels", "按勘察结果开挖疏导线"),
            ("allocate-food", "分配粮食，保障参与工程的民众"),
            ("open-channels", "扩大已经见效的疏导工程"),
        ]
        for revision, (action_id, raw_input) in enumerate(specs, start=1):
            response = self.client.post(
                f"/api/v1/practice/game/sessions/{session_id}/turns",
                json={
                    "client_action_id": f"api-action-{revision:03d}",
                    "action_id": action_id,
                    "raw_input": raw_input,
                    "expected_revision": revision,
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            session = response.json()["session"]

        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["ending_id"], "ending-water-controlled")
        self.assertEqual(session["current_state"]["flood_risk"], 35)
        fetched = self.client.get(
            f"/api/v1/practice/game/sessions/{session_id}"
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json(), session)

        rejected_state = self.client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json={
                "client_action_id": "api-illegal-state",
                "action_id": "reinforce-dam",
                "raw_input": "抢修堤坝",
                "expected_revision": session["revision"],
                "state": {"flood_risk": 1},
            },
        )
        self.assertEqual(rejected_state.status_code, 422)

    def test_turn_retry_is_idempotent_and_conflicts_are_stable(self):
        started = self.client.post(
            "/api/v1/practice/game/sessions",
            json={
                "scenario_id": "scenario-dayu-flood-control",
                "client_request_id": "api-start-idempotent-001",
            },
        ).json()["session"]
        session_id = started["session_id"]
        request = {
            "client_action_id": "api-idempotent-001",
            "action_id": "survey-terrain",
            "raw_input": "先勘察地势和河道",
            "expected_revision": 1,
        }
        first = self.client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json=request,
        )
        retry = self.client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json=request,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(first.json(), retry.json())

        stale = self.client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json={
                "client_action_id": "api-stale-001",
                "action_id": "reinforce-dam",
                "raw_input": "抢修堤坝",
                "expected_revision": 1,
            },
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"]["code"], "revision_conflict")

        conflicting_retry = self.client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json={
                **request,
                "action_id": "reinforce-dam",
                "raw_input": "抢修堤坝",
            },
        )
        self.assertEqual(conflicting_retry.status_code, 409, conflicting_retry.text)
        self.assertEqual(
            conflicting_retry.json()["detail"]["code"],
            "duplicate_action_conflict",
        )

        late_retry = self.client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json={**request, "expected_revision": 2},
        )
        self.assertEqual(late_retry.status_code, 409, late_retry.text)
        self.assertEqual(
            late_retry.json()["detail"]["code"],
            "duplicate_action_conflict",
        )

        missing_scenario = self.client.post(
            "/api/v1/practice/game/sessions",
            json={
                "scenario_id": "scenario-does-not-exist",
                "client_request_id": "api-start-missing-001",
            },
        )
        self.assertEqual(missing_scenario.status_code, 404)
        self.assertEqual(
            missing_scenario.json()["detail"]["code"],
            "scenario_catalog_not_found",
        )

        missing = self.client.get(
            "/api/v1/practice/game/sessions/session-does-not-exist"
        )
        self.assertEqual(missing.status_code, 404)

    def test_start_request_id_is_idempotent_and_cannot_be_reused(self):
        request = {
            "scenario_id": "scenario-dayu-flood-control",
            "client_request_id": "api-start-retry-001",
        }
        first = self.client.post(
            "/api/v1/practice/game/sessions",
            json=request,
        )
        retry = self.client.post(
            "/api/v1/practice/game/sessions",
            json=request,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(first.json(), retry.json())

        reused = self.client.post(
            "/api/v1/practice/game/sessions",
            json={
                "scenario_id": "scenario-shangyang-institutional-reform",
                "client_request_id": request["client_request_id"],
            },
        )
        self.assertEqual(reused.status_code, 409, reused.text)
        self.assertEqual(
            reused.json()["detail"]["code"],
            "duplicate_start_conflict",
        )

    def test_legacy_sandbox_routes_remain_compatible(self):
        listed = self.client.get("/api/v1/practice/sandbox")
        self.assertEqual(listed.status_code, 200, listed.text)
        scenario_id = listed.json()["items"][0]["id"]
        started = self.client.get(f"/api/v1/practice/sandbox/{scenario_id}")
        self.assertEqual(started.status_code, 200, started.text)
        payload = started.json()
        stepped = self.client.post(
            f"/api/v1/practice/sandbox/{scenario_id}/step",
            json={
                "node_id": payload["node"]["id"],
                "choice": payload["node"]["choices"][0]["key"],
                "state": payload["state"],
            },
        )
        self.assertEqual(stepped.status_code, 200, stepped.text)
        self.assertIn("state", stepped.json())

    def test_broken_catalog_returns_stable_service_unavailable(self):
        store = get_game_runtime().store
        configure_game_runtime(
            content_root=REPO_ROOT / "content",
            catalog_path="scenarios/catalog-does-not-exist.json",
            store=store,
        )
        response = self.client.get("/api/v1/practice/game/scenarios")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "scenario_file_error",
        )

    def test_published_pin_request_contract_and_missing_pin_error_are_stable(self):
        class PinRequiredRuntime:
            release_pin = None

            def start_session(self, _scenario_id, **kwargs):
                self.release_pin = kwargs["release_pin"]
                raise PublishedScenarioPinRequired("published pin required")

        runtime = PinRequiredRuntime()
        full_pin = {
            "release_id": "rel-abcdef0123-0001",
            "release_no": 1,
            "release_checksum": "a" * 64,
            "course_id": "C-api-pin",
            "lesson_id": "lesson-api-pin",
            "course_content_version": 1,
            "course_checksum": "b" * 64,
            "scenario_version": 1,
            "scenario_checksum": "c" * 64,
        }
        with patch.object(game_router, "get_game_runtime", return_value=runtime):
            missing = self.client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-api-pin",
                    "client_request_id": "api-pin-missing-001",
                },
            )
            accepted_contract = self.client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-api-pin",
                    "client_request_id": "api-pin-full-001",
                    "release_pin": full_pin,
                },
            )
            partial = self.client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-api-pin",
                    "client_request_id": "api-pin-partial-001",
                    "release_pin": {"release_id": full_pin["release_id"]},
                },
            )

        self.assertEqual(missing.status_code, 409, missing.text)
        self.assertEqual(
            missing.json()["detail"]["code"],
            "published_scenario_pin_required",
        )
        self.assertEqual(accepted_contract.status_code, 409, accepted_contract.text)
        self.assertIsInstance(runtime.release_pin, ScenarioReleasePinV1)
        self.assertEqual(runtime.release_pin.model_dump(mode="json"), full_pin)
        self.assertEqual(partial.status_code, 422, partial.text)


class ScenarioCatalogTests(unittest.TestCase):
    def test_catalog_is_explicit_and_rejects_path_traversal_or_identity_drift(self):
        raw_catalog = json.loads(
            (REPO_ROOT / "content" / "scenarios" / "catalog.v1.json").read_text(
                encoding="utf-8"
            )
        )
        invalid_path = json.loads(json.dumps(raw_catalog))
        invalid_path["entries"][0]["course_path"] = "../outside.json"
        with self.assertRaisesRegex(ValidationError, "stay inside"):
            ScenarioCatalogV1.model_validate(invalid_path)

        noncanonical_path = json.loads(json.dumps(raw_catalog))
        noncanonical_path["entries"][0]["course_path"] = (
            "examples//v1/dayu-course-package.json"
        )
        with self.assertRaisesRegex(ValidationError, "canonical POSIX"):
            ScenarioCatalogV1.model_validate(noncanonical_path)

        shared_course = json.loads(json.dumps(raw_catalog))
        second = json.loads(json.dumps(shared_course["entries"][0]))
        second.update(
            scenario_id="scenario-dayu-alternate",
            scenario_checksum="0" * 64,
            scenario_path="examples/v1/dayu-alternate-scenario.json",
        )
        shared_course["entries"].append(second)
        self.assertEqual(len(ScenarioCatalogV1.model_validate(shared_course).entries), 3)

        conflicting_course = json.loads(json.dumps(shared_course))
        conflicting_course["entries"][-1]["course_checksum"] = "f" * 64
        with self.assertRaisesRegex(ValidationError, "different course identities"):
            ScenarioCatalogV1.model_validate(conflicting_course)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            examples = root / "examples" / "v1"
            scenarios = root / "scenarios"
            examples.mkdir(parents=True)
            scenarios.mkdir(parents=True)
            for filename in (
                "dayu-course-package.json",
                "dayu-scenario-template.json",
            ):
                shutil.copy2(
                    REPO_ROOT / "content" / "examples" / "v1" / filename,
                    examples / filename,
                )
            shutil.copy2(
                examples / "dayu-scenario-template.json",
                examples / "rogue-unlisted-scenario.json",
            )
            one_entry = {
                "schema_version": "scenario-catalog/v1",
                "entries": [raw_catalog["entries"][0]],
            }
            catalog_path = scenarios / "catalog.v1.json"
            catalog_path.write_text(
                json.dumps(one_entry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            repository = ScenarioCatalogRepository(
                content_root=root,
                catalog_path=catalog_path,
            )
            self.assertEqual(len(repository.list_active()), 1)
            relative_repository = ScenarioCatalogRepository(
                content_root=root,
                catalog_path="scenarios/catalog.v1.json",
            )
            self.assertEqual(len(relative_repository.list_active()), 1)

            linked_scenario = examples / "linked-scenario.json"
            try:
                linked_scenario.symlink_to(examples / "dayu-scenario-template.json")
            except OSError:
                pass
            else:
                linked_entry = json.loads(json.dumps(one_entry))
                linked_entry["entries"][0]["scenario_path"] = (
                    "examples/v1/linked-scenario.json"
                )
                catalog_path.write_text(
                    json.dumps(linked_entry, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ScenarioFileError, "symbolic link"):
                    repository.list_active()

            one_entry["entries"][0]["scenario_checksum"] = "0" * 64
            catalog_path.write_text(
                json.dumps(one_entry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ScenarioIntegrityError, "identity"):
                repository.list_active()


class GameRuntimeServiceTests(unittest.TestCase):
    def test_returned_session_mutation_cannot_change_stored_authoritative_state(self):
        service = self._service()
        started_at = datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc)
        _, started = service.start_session(
            "scenario-dayu-flood-control",
            user_id="service-student",
            now=started_at,
        )
        original_state = dict(started.current_state)
        started.current_state["flood_risk"] = 0
        self.assertEqual(
            service.get_session(started.session_id).current_state,
            original_state,
        )

        result = service.apply_action(
            started.session_id,
            RuntimeCommandV1(
                client_action_id="service-action-001",
                raw_input="先勘察地势和河道",
                action_id="survey-terrain",
                expected_revision=1,
                occurred_at=started_at + timedelta(minutes=1),
            ),
        )
        applied_state = dict(result.session.current_state)
        result.session.current_state["flood_risk"] = 0
        fetched = service.get_session(started.session_id)
        self.assertEqual(fetched.current_state, applied_state)
        fetched.current_state["flood_risk"] = 0
        self.assertEqual(
            service.get_session(started.session_id).current_state,
            applied_state,
        )

    def test_concurrent_same_revision_allows_exactly_one_turn(self):
        service = self._service()
        started_at = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="concurrent-student",
            now=started_at,
        )
        barrier = threading.Barrier(3)

        def apply(action_id: str):
            barrier.wait()
            try:
                return service.apply_action(
                    session.session_id,
                    RuntimeCommandV1(
                        client_action_id=f"concurrent-{action_id}",
                        raw_input=action_id,
                        action_id=action_id,
                        expected_revision=1,
                        occurred_at=started_at + timedelta(minutes=1),
                    ),
                )
            except RevisionConflict as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(apply, "survey-terrain"),
                executor.submit(apply, "reinforce-dam"),
            ]
            barrier.wait()
            outcomes = [future.result(timeout=5) for future in futures]

        self.assertEqual(sum(not isinstance(item, Exception) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, RevisionConflict) for item in outcomes), 1)
        stored = service.get_session(session.session_id)
        self.assertEqual(stored.current_turn, 1)
        self.assertEqual(stored.revision, 2)

    def _service(self) -> GameRuntimeService:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(engine.dispose)
        return GameRuntimeService(
            ScenarioCatalogRepository(
                content_root=REPO_ROOT / "content",
                catalog_path=REPO_ROOT / "content" / "scenarios" / "catalog.v1.json",
            ),
            GameRuntimeStore(engine),
        )


if __name__ == "__main__":
    unittest.main()
