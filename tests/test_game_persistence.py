import hashlib
import json
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import URL


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from main import app
from settings import settings
from services import content, persistence
from services.game_runtime import RuntimeCommandV1, SessionIntegrityError
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.service import GameRuntimeService, get_game_runtime
from services.game_runtime.store import (
    GameSessionReleaseIdentityV1,
    GameRuntimeStore,
    StoredSessionIntegrityError,
    StoredSessionWriteConflict,
    game_sessions_table,
)


STARTED_AT = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)


class GamePersistenceApiTests(unittest.TestCase):
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
        settings.game_user_id = "restart-student"
        settings.sqlite_path = str(Path(self.temp_dir.name) / "chronovita.db")
        persistence.close_engine()

    def tearDown(self):
        persistence.close_engine()
        for key, value in self.previous.items():
            setattr(settings, key, value)
        content.configure()
        self.temp_dir.cleanup()

    def test_session_survives_application_restart_and_can_continue(self):
        with TestClient(app) as first_client:
            started = first_client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-dayu-flood-control",
                    "client_request_id": "restart-start-001",
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            session_id = started.json()["session"]["session_id"]
            first_turn = first_client.post(
                f"/api/v1/practice/game/sessions/{session_id}/turns",
                json={
                    "client_action_id": "restart-action-001",
                    "action_id": "survey-terrain",
                    "expected_revision": 1,
                },
            )
            self.assertEqual(first_turn.status_code, 200, first_turn.text)
            before_restart = first_turn.json()["session"]

        with TestClient(app) as second_client:
            recovered = second_client.get(
                f"/api/v1/practice/game/sessions/{session_id}"
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json(), before_restart)

            second_turn = second_client.post(
                f"/api/v1/practice/game/sessions/{session_id}/turns",
                json={
                    "client_action_id": "restart-action-002",
                    "action_id": "explain-plan",
                    "expected_revision": 2,
                },
            )
            self.assertEqual(second_turn.status_code, 200, second_turn.text)
            self.assertEqual(second_turn.json()["session"]["current_turn"], 2)
            self.assertEqual(second_turn.json()["session"]["revision"], 3)

    def test_checksum_tampering_fails_closed_at_the_api_boundary(self):
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-dayu-flood-control",
                    "client_request_id": "tamper-start-001",
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            session_id = started.json()["session"]["session_id"]

            store = get_game_runtime().store
            record = store.load_session(session_id)
            payload = json.loads(record.raw_data)
            payload["session"]["summary"] = "silently tampered"
            tampered = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            with store.engine.begin() as connection:
                connection.execute(
                    update(game_sessions_table)
                    .where(game_sessions_table.c.session_id == session_id)
                    .values(data=tampered)
                )

            response = client.get(
                f"/api/v1/practice/game/sessions/{session_id}"
            )
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "session_integrity_error",
            )

    def test_valid_record_checksum_cannot_hide_replay_tampering(self):
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-dayu-flood-control",
                    "client_request_id": "replay-tamper-start-001",
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            session_id = started.json()["session"]["session_id"]
            advanced = client.post(
                f"/api/v1/practice/game/sessions/{session_id}/turns",
                json={
                    "client_action_id": "replay-tamper-001",
                    "action_id": "survey-terrain",
                    "expected_revision": 1,
                },
            )
            self.assertEqual(advanced.status_code, 200, advanced.text)

            store = get_game_runtime().store
            record = store.load_session(session_id)
            payload = json.loads(record.raw_data)
            payload["session"]["turns"][0]["narrative"] = "forged narrative"
            canonical_session = json.dumps(
                payload["session"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            payload["checksum"] = hashlib.sha256(
                canonical_session.encode("utf-8")
            ).hexdigest()
            tampered = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            with store.engine.begin() as connection:
                connection.execute(
                    update(game_sessions_table)
                    .where(game_sessions_table.c.session_id == session_id)
                    .values(data=tampered)
                )

            response = client.get(
                f"/api/v1/practice/game/sessions/{session_id}"
            )
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "session_integrity_error",
            )

    def test_legacy_session_envelope_without_release_identity_remains_usable(self):
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-dayu-flood-control",
                    "client_request_id": "legacy-envelope-start-001",
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            started_session = started.json()["session"]
            session_id = started_session["session_id"]

            store = get_game_runtime().store
            record = store.load_session(session_id)
            payload = json.loads(record.raw_data)
            self.assertIsNone(payload.pop("release_identity"))
            legacy_raw = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            with store.engine.begin() as connection:
                connection.execute(
                    update(game_sessions_table)
                    .where(game_sessions_table.c.session_id == session_id)
                    .values(data=legacy_raw)
                )

            recovered = client.get(
                f"/api/v1/practice/game/sessions/{session_id}"
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json(), started_session)
            advanced = client.post(
                f"/api/v1/practice/game/sessions/{session_id}/turns",
                json={
                    "client_action_id": "legacy-envelope-action-001",
                    "action_id": "survey-terrain",
                    "expected_revision": 1,
                },
            )
            self.assertEqual(advanced.status_code, 200, advanced.text)
            self.assertEqual(advanced.json()["session"]["revision"], 2)
            self.assertIsNone(
                store.load_session(session_id).envelope.release_identity
            )

    def test_storage_failure_returns_stable_service_unavailable(self):
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/practice/game/sessions",
                json={
                    "scenario_id": "scenario-dayu-flood-control",
                    "client_request_id": "storage-failure-start-001",
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            session_id = started.json()["session"]["session_id"]

            store = get_game_runtime().store
            with store.engine.begin() as connection:
                connection.execute(text("DROP TABLE game_sessions"))

            response = client.get(
                f"/api/v1/practice/game/sessions/{session_id}"
            )
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "game_storage_unavailable",
            )


class GameRuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "game-runtime.db"
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            engine.dispose()
        self.temp_dir.cleanup()

    def test_stale_record_from_another_connection_cannot_overwrite_a_turn(self):
        first_store = GameRuntimeStore(self._engine())
        second_store = GameRuntimeStore(self._engine())
        repository = self._repository(REPO_ROOT / "content")
        service = GameRuntimeService(repository, first_store)
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="cas-student",
            now=STARTED_AT,
        )

        first_record = first_store.load_session(session.session_id)
        stale_record = second_store.load_session(session.session_id)
        rules = repository.get_active("scenario-dayu-flood-control")
        first_result = rules.apply_action(
            first_record.session,
            self._command("cas-action-001", "survey-terrain"),
        )
        stale_result = rules.apply_action(
            stale_record.session,
            self._command("cas-action-002", "reinforce-dam"),
        )

        first_store.compare_and_swap(first_record, first_result.session)
        with self.assertRaises(StoredSessionWriteConflict):
            second_store.compare_and_swap(stale_record, stale_result.session)

        stored = second_store.load_session(session.session_id).session
        self.assertEqual(stored.current_turn, 1)
        self.assertEqual(stored.turns[0].client_action_id, "cas-action-001")

    def test_v1_raw_checksum_survives_later_ai_evidence_default(self):
        store = GameRuntimeStore(self._engine())
        repository = self._repository(REPO_ROOT / "content")
        service = GameRuntimeService(repository, store)
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="legacy-default-student",
            now=STARTED_AT,
        )
        current = store.load_session(session.session_id)
        current_payload = json.loads(current.raw_data)
        self.assertEqual(
            current_payload["schema_version"],
            "persisted-game-session/v2",
        )

        legacy_session = current_payload["session"]
        legacy_session.pop("ai_evidence_version")
        legacy_payload = _v1_envelope(legacy_session)
        self._replace_session_raw(store, session.session_id, legacy_payload)

        recovered = store.load_session(session.session_id)
        self.assertEqual(
            recovered.envelope.schema_version,
            "persisted-game-session/v1",
        )
        self.assertEqual(recovered.session.ai_evidence_version, 0)
        self.assertNotIn(
            "ai_evidence_version",
            json.loads(recovered.raw_data)["session"],
        )

    def test_successful_cas_migrates_v1_to_v2_and_preserves_identity(self):
        store = GameRuntimeStore(self._engine())
        repository = self._repository(REPO_ROOT / "content")
        service = GameRuntimeService(repository, store)
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="legacy-migration-student",
            now=STARTED_AT,
        )
        current_payload = json.loads(
            store.load_session(session.session_id).raw_data
        )
        legacy_session = current_payload["session"]
        legacy_session.pop("ai_evidence_version")
        release_identity = GameSessionReleaseIdentityV1(
            release_id="release-dayu-legacy",
            release_no=7,
            release_checksum="a" * 64,
        )
        release_payload = release_identity.model_dump(mode="json")
        legacy_payload = _v1_envelope(legacy_session, release_payload)
        legacy_checksum = legacy_payload["checksum"]
        self._replace_session_raw(store, session.session_id, legacy_payload)

        legacy_record = store.load_session(session.session_id)
        rules = repository.get_active("scenario-dayu-flood-control")
        result = rules.apply_action(
            legacy_record.session,
            self._command("legacy-migration-action", "survey-terrain"),
        )
        store.compare_and_swap(legacy_record, result.session)

        migrated = store.load_session(session.session_id)
        migrated_payload = json.loads(migrated.raw_data)
        self.assertEqual(
            migrated_payload["schema_version"],
            "persisted-game-session/v2",
        )
        self.assertEqual(
            migrated.envelope.release_identity,
            release_identity,
        )
        self.assertEqual(
            migrated_payload["release_identity"],
            release_payload,
        )
        self.assertNotEqual(migrated_payload["checksum"], legacy_checksum)
        self.assertEqual(migrated.session.revision, 2)

    def test_v1_unknown_shapes_and_tampering_fail_closed(self):
        store = GameRuntimeStore(self._engine())
        repository = self._repository(REPO_ROOT / "content")
        service = GameRuntimeService(repository, store)
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="legacy-tamper-student",
            now=STARTED_AT,
        )
        session_payload = json.loads(
            store.load_session(session.session_id).raw_data
        )["session"]
        session_payload.pop("ai_evidence_version")
        release_payload = {
            "release_id": "release-dayu-legacy",
            "release_no": 3,
            "release_checksum": "b" * 64,
        }
        valid = _v1_envelope(session_payload, release_payload)

        bad_checksum = _json_clone(valid)
        bad_checksum["checksum"] = "0" * 64

        tampered_release = _json_clone(valid)
        tampered_release["release_identity"]["release_no"] = 4

        wrong_identity = _json_clone(valid)
        wrong_identity["session"]["session_id"] = "different-session-id"
        wrong_identity["checksum"] = _v1_session_checksum(
            wrong_identity["session"],
            wrong_identity["release_identity"],
        )

        unknown_version = _json_clone(valid)
        unknown_version["schema_version"] = "persisted-game-session/v999"

        unknown_envelope_field = _json_clone(valid)
        unknown_envelope_field["unexpected"] = True

        unknown_session_field = _json_clone(valid)
        unknown_session_field["session"]["unexpected"] = True
        unknown_session_field["checksum"] = _v1_session_checksum(
            unknown_session_field["session"],
            unknown_session_field["release_identity"],
        )

        disguised_v2_session = _json_clone(valid)
        disguised_v2_session["session"]["ai_evidence_version"] = 1
        disguised_v2_session["checksum"] = _v1_session_checksum(
            disguised_v2_session["session"],
            disguised_v2_session["release_identity"],
        )

        cases = {
            "checksum": bad_checksum,
            "release identity": tampered_release,
            "session identity": wrong_identity,
            "schema version": unknown_version,
            "envelope field": unknown_envelope_field,
            "session field": unknown_session_field,
            "v2 evidence disguised as v1": disguised_v2_session,
        }
        for label, payload in cases.items():
            with self.subTest(label=label):
                self._replace_session_raw(store, session.session_id, payload)
                with self.assertRaises(StoredSessionIntegrityError):
                    store.load_session(session.session_id)

    def test_same_action_is_idempotent_across_two_service_instances(self):
        barrier = threading.Barrier(2)
        first_store = _BarrierStore(self._engine(), barrier)
        second_store = _BarrierStore(self._engine(), barrier)
        first_service = GameRuntimeService(
            self._repository(REPO_ROOT / "content"),
            first_store,
        )
        second_service = GameRuntimeService(
            self._repository(REPO_ROOT / "content"),
            second_store,
        )
        _, session = first_service.start_session(
            "scenario-dayu-flood-control",
            user_id="idempotent-student",
            now=STARTED_AT,
        )
        command = self._command("shared-action-001", "survey-terrain")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(service.apply_action, session.session_id, command)
                for service in (first_service, second_service)
            ]
            results = [future.result(timeout=5) for future in futures]

        self.assertEqual(
            results[0].model_dump(mode="json"),
            results[1].model_dump(mode="json"),
        )
        stored = first_store.load_session(session.session_id).session
        self.assertEqual(stored.current_turn, 1)
        self.assertEqual(stored.revision, 2)
        self.assertEqual(stored.turns[0].client_action_id, "shared-action-001")

    def test_missing_pinned_scenario_is_reported_as_session_integrity_failure(self):
        content_root = Path(self.temp_dir.name) / "content"
        shutil.copytree(REPO_ROOT / "content", content_root)
        store = GameRuntimeStore(self._engine())
        repository = self._repository(content_root)
        service = GameRuntimeService(repository, store)
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="pin-student",
            now=STARTED_AT,
        )

        catalog_path = content_root / "scenarios" / "catalog.v1.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["entries"] = [
            entry
            for entry in catalog["entries"]
            if entry["scenario_id"] != session.scenario_id
        ]
        catalog_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            SessionIntegrityError,
            "pinned scenario artifact is no longer available",
        ):
            service.get_session(session.session_id)

    def _engine(self):
        engine = create_engine(
            URL.create("sqlite", database=str(self.db_path)),
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.engines.append(engine)
        return engine

    @staticmethod
    def _repository(content_root: Path) -> ScenarioCatalogRepository:
        return ScenarioCatalogRepository(
            content_root=content_root,
            catalog_path="scenarios/catalog.v1.json",
        )

    @staticmethod
    def _command(client_action_id: str, action_id: str) -> RuntimeCommandV1:
        return RuntimeCommandV1(
            client_action_id=client_action_id,
            action_id=action_id,
            raw_input=action_id,
            expected_revision=1,
            occurred_at=STARTED_AT + timedelta(seconds=1),
        )

    @staticmethod
    def _replace_session_raw(
        store: GameRuntimeStore,
        session_id: str,
        payload: dict,
    ) -> None:
        with store.engine.begin() as connection:
            connection.execute(
                update(game_sessions_table)
                .where(game_sessions_table.c.session_id == session_id)
                .values(data=_canonical_json(payload))
            )


class _BarrierStore(GameRuntimeStore):
    def __init__(self, engine, barrier: threading.Barrier) -> None:
        super().__init__(engine)
        self._barrier = barrier

    def compare_and_swap(self, current, next_session, dossier=None) -> None:
        self._barrier.wait(timeout=5)
        super().compare_and_swap(current, next_session, dossier)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_clone(payload: dict) -> dict:
    return json.loads(_canonical_json(payload))


def _v1_session_checksum(
    session_payload: dict,
    release_identity: dict | None = None,
) -> str:
    checksum_payload: object = session_payload
    if release_identity is not None:
        checksum_payload = {
            "session": session_payload,
            "release_identity": release_identity,
        }
    return hashlib.sha256(
        _canonical_json(checksum_payload).encode("utf-8")
    ).hexdigest()


def _v1_envelope(
    session_payload: dict,
    release_identity: dict | None = None,
) -> dict:
    return {
        "schema_version": "persisted-game-session/v1",
        "session": session_payload,
        "release_identity": release_identity,
        "checksum": _v1_session_checksum(session_payload, release_identity),
    }


if __name__ == "__main__":
    unittest.main()
