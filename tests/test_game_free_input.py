import asyncio
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, update
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.ai import ActionClassificationV1
from services.game_runtime import (
    DuplicateActionConflict,
    RevisionConflict,
    RuntimeCommandV1,
    SessionIntegrityError,
)
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.service import GameRuntimeService
from services.game_runtime.store import GameRuntimeStore, game_dossiers_table


BASE_TIME = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


class FakeClassifier:
    def __init__(self, factory, before_return=None):
        self.factory = factory
        self.before_return = before_return
        self.calls = []

    async def classify(self, engine, session, raw_input):
        self.calls.append(
            {
                "session_id": session.session_id,
                "revision": session.revision,
                "raw_input": raw_input,
            }
        )
        if self.before_return is not None:
            self.before_return(engine, session, raw_input)
        return self.factory(engine, session)


class ThreadBarrierClassifier(FakeClassifier):
    def __init__(self, factory, barrier):
        super().__init__(factory)
        self.barrier = barrier

    async def classify(self, engine, session, raw_input):
        self.calls.append(
            {
                "session_id": session.session_id,
                "revision": session.revision,
                "raw_input": raw_input,
            }
        )
        self.barrier.wait(timeout=5)
        return self.factory(engine, session)


def matched(action_id="survey-terrain", confidence=0.91):
    def factory(_engine, session):
        return ActionClassificationV1(
            kind="matched",
            source="llm",
            reason_code="semantic_match",
            action_id=action_id,
            confidence=confidence,
            available_action_ids=list(session.available_action_ids),
            provider="deepseek",
            model="classifier-test-model",
            output_checksum="a" * 64,
        )

    return factory


class GameFreeInputServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_match_applies_server_metadata_and_retry_skips_classifier(self):
        classifier = FakeClassifier(matched())
        service = self._service(classifier)
        session = self._start(service)

        first = await service.apply_free_input(
            session.session_id,
            client_action_id="free-match-001",
            raw_input="先看看水势从哪里来",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        retry = await service.apply_free_input(
            session.session_id,
            client_action_id="free-match-001",
            raw_input="先看看水势从哪里来",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=2),
        )

        self.assertEqual(first.kind, "advanced")
        self.assertIsNotNone(first.result)
        self.assertEqual(first.result.turn.action_source, "free_input")
        self.assertEqual(first.result.turn.classification_confidence, 0.91)
        self.assertEqual(first.result.turn.raw_input, "先看看水势从哪里来")
        self.assertEqual(first.result.turn.turn_id, retry.result.turn.turn_id)
        self.assertEqual(
            first.model_dump(mode="json"),
            retry.model_dump(mode="json"),
        )
        self.assertEqual(len(classifier.calls), 1)
        self.assertEqual(service.get_session(session.session_id).current_turn, 1)

        with self.assertRaises(DuplicateActionConflict):
            await service.apply_free_input(
                session.session_id,
                client_action_id="free-match-001",
                raw_input="换一个说法",
                expected_revision=1,
            )
        with self.assertRaises(DuplicateActionConflict):
            await service.apply_free_input(
                session.session_id,
                client_action_id="free-match-001",
                raw_input="先看看水势从哪里来",
                expected_revision=2,
            )
        self.assertEqual(len(classifier.calls), 1)

    async def test_idempotent_retry_still_validates_linked_dossier(self):
        classifier = FakeClassifier(matched())
        service = self._service(classifier)
        session = self._start(service)
        first = await service.apply_free_input(
            session.session_id,
            client_action_id="free-dossier-integrity-001",
            raw_input="先看看水势从哪里来",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        self.assertEqual(first.kind, "advanced")

        for revision, action_id in enumerate(
            (
                "explain-plan",
                "open-channels",
                "allocate-food",
                "open-channels",
            ),
            start=2,
        ):
            completed = service.apply_fixed_action(
                session.session_id,
                client_action_id=f"free-dossier-finish-{revision}",
                action_id=action_id,
                expected_revision=revision,
                occurred_at=BASE_TIME + timedelta(minutes=revision),
            )
        self.assertEqual(completed.session.status, "completed")
        self.assertIsNotNone(completed.session.dossier_id)

        with service.store.engine.begin() as connection:
            connection.execute(
                update(game_dossiers_table)
                .where(
                    game_dossiers_table.c.dossier_id
                    == completed.session.dossier_id
                )
                .values(data="{}")
            )

        with self.assertRaises(SessionIntegrityError):
            await service.apply_free_input(
                session.session_id,
                client_action_id="free-dossier-integrity-001",
                raw_input="先看看水势从哪里来",
                expected_revision=1,
            )

    async def test_non_matches_return_safe_no_write_results(self):
        cases = (
            (
                "clarification_required",
                lambda _engine, session: ActionClassificationV1(
                    kind="clarification_required",
                    source="llm",
                    reason_code="ambiguous",
                    confidence=0.4,
                    available_action_ids=list(session.available_action_ids),
                    provider="deepseek",
                    model="classifier-test-model",
                    output_checksum="b" * 64,
                ),
            ),
            (
                "rejected",
                lambda _engine, session: ActionClassificationV1(
                    kind="rejected",
                    source="guardrail",
                    reason_code="prompt_injection",
                    confidence=1.0,
                    available_action_ids=list(session.available_action_ids),
                ),
            ),
            (
                "provider_unavailable",
                lambda _engine, session: ActionClassificationV1(
                    kind="provider_unavailable",
                    source="fallback",
                    reason_code="provider_timeout",
                    available_action_ids=list(session.available_action_ids),
                    provider="do-not-expose-provider-detail",
                ),
            ),
        )
        for expected_kind, factory in cases:
            with self.subTest(kind=expected_kind):
                classifier = FakeClassifier(factory)
                service = self._service(classifier)
                session = self._start(service)
                result = await service.apply_free_input(
                    session.session_id,
                    client_action_id=f"free-{expected_kind}-001",
                    raw_input="请处理这一回合",
                    expected_revision=1,
                )

                self.assertEqual(result.kind, expected_kind)
                self.assertIsNone(result.result)
                self.assertNotIn(
                    "do-not-expose-provider-detail",
                    result.model_dump_json(),
                )
                stored = service.get_session(session.session_id)
                self.assertEqual(stored.revision, 1)
                self.assertEqual(stored.turns, [])

    async def test_stale_revision_is_rejected_before_classifier_call(self):
        classifier = FakeClassifier(matched())
        service = self._service(classifier)
        session = self._start(service)
        service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-before-free-001",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )

        with self.assertRaises(RevisionConflict):
            await service.apply_free_input(
                session.session_id,
                client_action_id="stale-free-001",
                raw_input="再看一次水势",
                expected_revision=1,
            )
        self.assertEqual(classifier.calls, [])
        self.assertEqual(service.get_session(session.session_id).current_turn, 1)

    async def test_revision_change_during_classification_cannot_apply_old_result(self):
        holder = {}

        def advance_other_turn(_engine, session, _raw_input):
            holder["service"].apply_fixed_action(
                session.session_id,
                client_action_id="racing-fixed-001",
                action_id="survey-terrain",
                expected_revision=1,
                occurred_at=BASE_TIME + timedelta(minutes=1),
            )

        classifier = FakeClassifier(matched(), advance_other_turn)
        service = self._service(classifier)
        holder["service"] = service
        session = self._start(service)

        with self.assertRaises(RevisionConflict):
            await service.apply_free_input(
                session.session_id,
                client_action_id="racing-free-001",
                raw_input="先看看水势",
                expected_revision=1,
                occurred_at=BASE_TIME + timedelta(minutes=2),
            )
        stored = service.get_session(session.session_id)
        self.assertEqual(stored.current_turn, 1)
        self.assertEqual(stored.turns[0].client_action_id, "racing-fixed-001")

    async def test_same_input_race_recovers_winner_without_model_output_equality(self):
        holder = {}

        def persist_other_classification(_engine, session, raw_input):
            holder["service"].apply_action(
                session.session_id,
                RuntimeCommandV1(
                    client_action_id="same-free-race-001",
                    raw_input=raw_input,
                    action_id="reinforce-dam",
                    action_source="free_input",
                    classification_confidence=0.88,
                    expected_revision=1,
                    occurred_at=BASE_TIME + timedelta(minutes=1),
                ),
            )

        classifier = FakeClassifier(matched("survey-terrain"), persist_other_classification)
        service = self._service(classifier)
        holder["service"] = service
        session = self._start(service)

        result = await service.apply_free_input(
            session.session_id,
            client_action_id="same-free-race-001",
            raw_input="先采取稳妥办法",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=2),
        )

        self.assertEqual(result.kind, "advanced")
        self.assertEqual(result.result.turn.classified_action_id, "reinforce-dam")
        self.assertEqual(result.result.turn.classification_confidence, 0.88)
        self.assertEqual(service.get_session(session.session_id).current_turn, 1)

    def test_fixed_action_uses_server_label_and_remains_idempotent(self):
        service = self._service(FakeClassifier(matched()))
        session = self._start(service)

        first = service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-label-001",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        retry = service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-label-001",
            action_id="survey-terrain",
            expected_revision=1,
        )

        self.assertEqual(first.turn.raw_input, "勘察地势")
        self.assertEqual(first.turn.action_source, "fixed")
        self.assertEqual(first.turn.classification_confidence, 1.0)
        self.assertEqual(first.turn.turn_id, retry.turn.turn_id)
        with self.assertRaises(DuplicateActionConflict):
            service.apply_fixed_action(
                session.session_id,
                client_action_id="fixed-label-001",
                action_id="reinforce-dam",
                expected_revision=1,
            )

    def test_same_free_input_is_idempotent_across_service_instances(self):
        barrier = threading.Barrier(2)
        first_classifier = ThreadBarrierClassifier(
            matched("survey-terrain", 0.91),
            barrier,
        )
        second_classifier = ThreadBarrierClassifier(
            matched("reinforce-dam", 0.88),
            barrier,
        )
        first_service, second_service = self._two_services(
            first_classifier,
            second_classifier,
        )
        session = self._start(first_service)

        def submit(service):
            return asyncio.run(
                service.apply_free_input(
                    session.session_id,
                    client_action_id="shared-free-input-001",
                    raw_input="先采取稳妥办法",
                    expected_revision=1,
                    occurred_at=BASE_TIME + timedelta(minutes=1),
                )
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(submit, service)
                for service in (first_service, second_service)
            ]
            results = [future.result(timeout=10) for future in futures]

        self.assertEqual(
            results[0].model_dump(mode="json"),
            results[1].model_dump(mode="json"),
        )
        stored = first_service.get_session(session.session_id)
        self.assertEqual(stored.current_turn, 1)
        self.assertEqual(
            stored.turns[0].client_action_id,
            "shared-free-input-001",
        )

    def test_different_free_inputs_competing_for_revision_have_one_winner(self):
        barrier = threading.Barrier(2)
        first_service, second_service = self._two_services(
            ThreadBarrierClassifier(matched("survey-terrain"), barrier),
            ThreadBarrierClassifier(matched("reinforce-dam"), barrier),
        )
        session = self._start(first_service)

        def submit(service, suffix):
            try:
                return asyncio.run(
                    service.apply_free_input(
                        session.session_id,
                        client_action_id=f"competing-free-{suffix}",
                        raw_input=f"行动方案 {suffix}",
                        expected_revision=1,
                        occurred_at=BASE_TIME + timedelta(minutes=1),
                    )
                )
            except RevisionConflict as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(submit, first_service, "a"),
                pool.submit(submit, second_service, "b"),
            ]
            outcomes = [future.result(timeout=10) for future in futures]

        self.assertEqual(
            sum(not isinstance(item, Exception) for item in outcomes),
            1,
        )
        self.assertEqual(
            sum(isinstance(item, RevisionConflict) for item in outcomes),
            1,
        )
        self.assertEqual(
            first_service.get_session(session.session_id).current_turn,
            1,
        )

    def _service(self, classifier):
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
                catalog_path=REPO_ROOT
                / "content"
                / "scenarios"
                / "catalog.v1.json",
            ),
            GameRuntimeStore(engine),
            classifier,
        )

    def _two_services(self, first_classifier, second_classifier):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database = Path(temp_dir.name) / "free-input-cas.db"
        engines = [
            create_engine(
                URL.create("sqlite", database=str(database)),
                connect_args={"check_same_thread": False},
                future=True,
            )
            for _ in range(2)
        ]
        for engine in engines:
            self.addCleanup(engine.dispose)
        services = []
        for engine, classifier in zip(
            engines,
            (first_classifier, second_classifier),
        ):
            services.append(
                GameRuntimeService(
                    ScenarioCatalogRepository(
                        content_root=REPO_ROOT / "content",
                        catalog_path=REPO_ROOT
                        / "content"
                        / "scenarios"
                        / "catalog.v1.json",
                    ),
                    GameRuntimeStore(engine),
                    classifier,
                )
            )
        return tuple(services)

    @staticmethod
    def _start(service):
        return service.start_session(
            "scenario-dayu-flood-control",
            user_id="free-input-student",
            now=BASE_TIME,
        )[1]


if __name__ == "__main__":
    unittest.main()
