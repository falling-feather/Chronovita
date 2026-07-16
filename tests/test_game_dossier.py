import hashlib
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import URL


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from main import app
from settings import settings
from services import content, persistence
from services.contracts.v1 import DossierV1, verify_contract_checksum
from services.game_runtime import RuntimeCommandV1, SessionIntegrityError
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.dossier import build_final_dossier
from services.game_runtime.service import (
    DossierNotReady,
    GameRuntimeService,
    get_game_runtime,
)
from services.game_runtime.store import (
    GameRuntimeStore,
    game_dossiers_table,
    game_sessions_table,
)


BASE_TIME = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
DAYU_ACTIONS = [
    "survey-terrain",
    "explain-plan",
    "open-channels",
    "allocate-food",
    "open-channels",
]
DAYU_ACTION_LABELS = [
    "勘察地势",
    "向部族解释计划",
    "开挖疏导线",
    "分配粮食保障",
    "开挖疏导线",
]


class GameDossierApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous = {
            "auth_mode": settings.auth_mode,
            "admin_token": settings.admin_token,
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
            "game_user_id": settings.game_user_id,
            "sqlite_path": settings.sqlite_path,
        }
        settings.auth_mode = "legacy-local"
        settings.admin_token = "dossier-admin-token"
        settings.content_root = str(REPO_ROOT / "content")
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        settings.game_user_id = "dossier-student"
        settings.sqlite_path = str(Path(self.temp_dir.name) / "chronovita.db")
        persistence.close_engine()

    def tearDown(self):
        persistence.close_engine()
        for key, value in self.previous.items():
            setattr(settings, key, value)
        content.configure()
        self.temp_dir.cleanup()

    def test_dossier_replay_and_teacher_summary_survive_restart(self):
        with TestClient(app) as first_client:
            started = self._start_dayu(first_client)
            session_id = started["session_id"]

            not_ready = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(not_ready.status_code, 409, not_ready.text)
            self.assertEqual(
                not_ready.json()["detail"]["code"],
                "dossier_not_ready",
            )
            active_summary = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/summary",
                headers={"X-Admin-Token": settings.admin_token},
            )
            self.assertEqual(active_summary.status_code, 200, active_summary.text)
            self.assertEqual(active_summary.json()["status"], "active")
            self.assertIsNone(active_summary.json()["dossier_id"])
            self.assertEqual(len(active_summary.json()["state_trajectory"]), 1)

            completed = self._complete_dayu(first_client, session_id)
            self.assertEqual(completed["status"], "completed")
            self.assertIsNotNone(completed["dossier_id"])

            dossier_response = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(dossier_response.status_code, 200, dossier_response.text)
            dossier_json = dossier_response.json()
            dossier = DossierV1.model_validate(dossier_json)
            self.assertTrue(verify_contract_checksum(dossier))
            self.assertEqual(dossier.dossier_id, completed["dossier_id"])
            self.assertEqual(len(dossier.key_choices), 5)
            self.assertEqual(len(dossier.state_trajectory), 6)
            self.assertEqual(
                [item.choice for item in dossier.key_choices],
                DAYU_ACTION_LABELS,
            )
            self.assertEqual(dossier.reflection_notes, [])
            self.assertEqual(dossier.knowledge_edges, [])

            runtime = get_game_runtime()
            engine = runtime.repository.get_active("scenario-dayu-flood-control")
            ending = next(
                item
                for item in engine.scenario.ending_rules
                if item.ending_id == completed["ending_id"]
            )
            self.assertEqual(dossier.major_costs, ending.major_costs)
            self.assertEqual(
                dossier.historical_explanation,
                ending.historical_explanation,
            )
            self.assertEqual(
                dossier.follow_up_questions,
                engine.scenario.dossier_template.reflection_questions,
            )
            self.assertEqual(
                dossier.title,
                engine.scenario.dossier_template.title_template.replace(
                    "{scenario_title}",
                    engine.scenario.title,
                ),
            )
            fact_statements = {
                item.statement
                for item in engine.course.facts
                if item.fact_id in dossier.fact_refs
            }
            self.assertEqual(
                {item.label for item in dossier.knowledge_nodes},
                fact_statements,
            )

            repeated = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(repeated.json(), dossier_json)
            ensured = first_client.post(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(ensured.status_code, 200, ensured.text)
            self.assertEqual(ensured.json(), dossier_json)

            replay = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/replay"
            )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()["verified"])
            self.assertEqual(len(replay.json()["commands"]), 5)
            self.assertEqual(replay.json()["session"], completed)

            summary = first_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/summary",
                headers={"X-Admin-Token": settings.admin_token},
            )
            self.assertEqual(summary.status_code, 200, summary.text)
            self.assertEqual(summary.json()["status"], "completed")
            self.assertEqual(summary.json()["dossier_id"], dossier.dossier_id)
            self.assertEqual(summary.json()["dossier_checksum"], dossier.checksum)
            self.assertEqual(len(summary.json()["key_choices"]), 5)

        with TestClient(app) as second_client:
            recovered_dossier = second_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(recovered_dossier.status_code, 200)
            self.assertEqual(recovered_dossier.json(), dossier_json)
            recovered_replay = second_client.get(
                f"/api/v1/practice/game/sessions/{session_id}/replay"
            )
            self.assertEqual(recovered_replay.status_code, 200)
            self.assertEqual(recovered_replay.json()["session"], completed)

    def test_replay_rejects_rechecksummed_non_rule_metadata_tampering(self):
        with TestClient(app) as client:
            session = self._start_dayu(client)
            session_id = session["session_id"]
            advanced = self._turn(client, session_id, 1, DAYU_ACTIONS[0])
            self.assertEqual(advanced["current_turn"], 1)

            store = get_game_runtime().store
            record = store.load_session(session_id)
            payload = json.loads(record.raw_data)
            payload["session"]["history"][-1]["text"] = "forged history"
            payload["checksum"] = _session_checksum(payload["session"])
            with store.engine.begin() as connection:
                connection.execute(
                    update(game_sessions_table)
                    .where(game_sessions_table.c.session_id == session_id)
                    .values(data=_canonical_json(payload))
                )

            replay = client.get(
                f"/api/v1/practice/game/sessions/{session_id}/replay"
            )
            self.assertEqual(replay.status_code, 503, replay.text)
            self.assertEqual(
                replay.json()["detail"]["code"],
                "session_integrity_error",
            )

    def test_dossier_tampering_invalidates_dossier_and_linked_session(self):
        with TestClient(app) as client:
            session = self._start_dayu(client)
            session_id = session["session_id"]
            completed = self._complete_dayu(client, session_id)
            dossier_id = completed["dossier_id"]
            store = get_game_runtime().store
            record = store.load_dossier(dossier_id)
            payload = json.loads(record.raw_data)
            payload["historical_explanation"] = "forged explanation"
            with store.engine.begin() as connection:
                connection.execute(
                    update(game_dossiers_table)
                    .where(game_dossiers_table.c.dossier_id == dossier_id)
                    .values(data=_canonical_json(payload))
                )

            for suffix in ("dossier", ""):
                path = f"/api/v1/practice/game/sessions/{session_id}"
                if suffix:
                    path += f"/{suffix}"
                response = client.get(path)
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "session_integrity_error",
                )

    def test_rechecksummed_dossier_text_tampering_fails_derivation_check(self):
        with TestClient(app) as client:
            session = self._start_dayu(client)
            session_id = session["session_id"]
            completed = self._complete_dayu(client, session_id)
            dossier_id = completed["dossier_id"]
            store = get_game_runtime().store
            record = store.load_dossier(dossier_id)
            payload = json.loads(record.raw_data)
            payload["strategy_summary"] = "forged but rechecksummed strategy"
            payload["checksum"] = _dossier_checksum(payload)
            with store.engine.begin() as connection:
                connection.execute(
                    update(game_dossiers_table)
                    .where(game_dossiers_table.c.dossier_id == dossier_id)
                    .values(data=_canonical_json(payload))
                )

            response = client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier"
            )
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "session_integrity_error",
            )

    @staticmethod
    def _start_dayu(client: TestClient) -> dict:
        response = client.post(
            "/api/v1/practice/game/sessions",
            json={
                "scenario_id": "scenario-dayu-flood-control",
                "client_request_id": "dossier-start-001",
            },
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return response.json()["session"]

    def _complete_dayu(self, client: TestClient, session_id: str) -> dict:
        session = None
        for revision, action_id in enumerate(DAYU_ACTIONS, start=1):
            session = self._turn(client, session_id, revision, action_id)
        if session is None:
            raise AssertionError("dayu action list is empty")
        return session

    @staticmethod
    def _turn(
        client: TestClient,
        session_id: str,
        revision: int,
        action_id: str,
    ) -> dict:
        response = client.post(
            f"/api/v1/practice/game/sessions/{session_id}/turns",
            json={
                "client_action_id": f"dossier-action-{revision:03d}",
                "action_id": action_id,
                "expected_revision": revision,
            },
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return response.json()["session"]


class GameDossierServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            URL.create(
                "sqlite",
                database=str(Path(self.temp_dir.name) / "game-dossier.db"),
            ),
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.engines = [self.engine]
        self.store = GameRuntimeStore(self.engine)
        self.repository = ScenarioCatalogRepository(
            content_root=REPO_ROOT / "content",
            catalog_path="scenarios/catalog.v1.json",
        )
        self.service = GameRuntimeService(self.repository, self.store)

    def tearDown(self):
        for engine in reversed(self.engines):
            engine.dispose()
        self.temp_dir.cleanup()

    def test_dossier_insert_failure_rolls_back_the_final_turn(self):
        _, session = self.service.start_session(
            "scenario-dayu-flood-control",
            user_id="transaction-student",
            now=BASE_TIME,
        )
        for revision, action_id in enumerate(DAYU_ACTIONS[:4], start=1):
            session = self.service.apply_action(
                session.session_id,
                _command(revision, action_id),
            ).session
        self.assertEqual(session.current_turn, 4)
        self.assertEqual(session.status, "active")

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TRIGGER reject_game_dossier "
                    "BEFORE INSERT ON game_dossiers "
                    "BEGIN SELECT RAISE(ABORT, 'injected dossier failure'); END"
                )
            )

        with self.assertRaises(SessionIntegrityError):
            self.service.apply_action(
                session.session_id,
                _command(5, DAYU_ACTIONS[4]),
            )

        stored = self.store.load_session(session.session_id).session
        self.assertEqual(stored.current_turn, 4)
        self.assertEqual(stored.revision, 5)
        self.assertEqual(stored.status, "active")
        self.assertIsNone(stored.dossier_id)
        with self.engine.connect() as connection:
            dossier_count = connection.scalar(
                select(func.count()).select_from(game_dossiers_table)
            )
        self.assertEqual(dossier_count, 0)

    def test_legacy_completed_session_gets_one_deterministic_dossier(self):
        engine = self.repository.get_active("scenario-dayu-flood-control")
        completed = engine.replay(
            session_id="session-legacy-completed",
            user_id="legacy-student",
            started_at=BASE_TIME,
            commands=[
                _command(index, action_id)
                for index, action_id in enumerate(DAYU_ACTIONS, start=1)
            ],
        )
        self.assertIsNone(completed.dossier_id)
        self.store.create_session(completed)

        before = self.store.load_session(completed.session_id).raw_data
        summary = self.service.teacher_summary(completed.session_id)
        self.assertIsNone(summary.dossier_id)
        self.assertEqual(
            self.store.load_session(completed.session_id).raw_data,
            before,
        )
        with self.assertRaises(DossierNotReady):
            self.service.get_dossier(completed.session_id)

        first = self.service.ensure_dossier(completed.session_id)
        second = self.service.ensure_dossier(completed.session_id)
        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))
        self.assertTrue(verify_contract_checksum(first))
        stored = self.service.get_session(completed.session_id)
        self.assertEqual(stored.dossier_id, first.dossier_id)

    def test_final_action_is_idempotent_across_two_service_instances(self):
        barrier = threading.Barrier(2)
        second_engine = create_engine(
            self.engine.url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.engines.append(second_engine)
        first_service = GameRuntimeService(
            self.repository,
            _FinalBarrierStore(self.engine, barrier),
        )
        second_service = GameRuntimeService(
            self.repository,
            _FinalBarrierStore(second_engine, barrier),
        )
        _, session = first_service.start_session(
            "scenario-dayu-flood-control",
            user_id="final-race-student",
            now=BASE_TIME,
        )
        for revision, action_id in enumerate(DAYU_ACTIONS[:4], start=1):
            session = first_service.apply_action(
                session.session_id,
                _command(revision, action_id),
            ).session

        command = _command(5, DAYU_ACTIONS[4])
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
        self.assertIsNotNone(results[0].session.dossier_id)
        with self.engine.connect() as connection:
            dossier_count = connection.scalar(
                select(func.count()).select_from(game_dossiers_table)
            )
        self.assertEqual(dossier_count, 1)

    def test_generator_uses_the_second_sealed_scenario_without_hardcoding(self):
        engine = self.repository.get_active(
            "scenario-shangyang-institutional-reform"
        )
        actions = [
            "consult-court",
            "standardize-rules",
            "apply-merit-system",
            "consolidate-rules",
        ]
        completed = engine.replay(
            session_id="session-shangyang-dossier",
            user_id="shangyang-student",
            started_at=BASE_TIME,
            commands=[
                _command(index, action_id)
                for index, action_id in enumerate(actions, start=1)
            ],
        )
        attached, dossier = build_final_dossier(engine, completed)
        ending = next(
            item
            for item in engine.scenario.ending_rules
            if item.ending_id == completed.ending_id
        )

        self.assertEqual(attached.dossier_id, dossier.dossier_id)
        self.assertEqual(dossier.historical_explanation, ending.historical_explanation)
        self.assertEqual(dossier.major_costs, ending.major_costs)
        self.assertIn(engine.scenario.title, dossier.title)
        self.assertEqual(len(dossier.key_choices), len(actions))
        self.assertTrue(verify_contract_checksum(dossier))


def _command(revision: int, action_id: str) -> RuntimeCommandV1:
    return RuntimeCommandV1(
        client_action_id=f"service-dossier-{revision:03d}",
        action_id=action_id,
        raw_input=action_id,
        expected_revision=revision,
        occurred_at=BASE_TIME + timedelta(minutes=revision),
    )


class _FinalBarrierStore(GameRuntimeStore):
    def __init__(self, engine, barrier: threading.Barrier) -> None:
        super().__init__(engine)
        self._barrier = barrier

    def compare_and_swap(self, current, next_session, dossier=None) -> None:
        if dossier is not None:
            self._barrier.wait(timeout=5)
        super().compare_and_swap(current, next_session, dossier)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _session_checksum(session_payload: dict) -> str:
    return hashlib.sha256(
        _canonical_json(session_payload).encode("utf-8")
    ).hexdigest()


def _dossier_checksum(dossier_payload: dict) -> str:
    unsigned = dict(dossier_payload)
    unsigned["checksum"] = None
    return hashlib.sha256(
        _canonical_json(unsigned).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
