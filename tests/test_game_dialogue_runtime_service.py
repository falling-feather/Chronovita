from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, update
from sqlalchemy.engine import URL

from services.ai.contracts import ActionClassificationV1
from services.content import content_root, workflow
from services.contracts.v1 import reviewed_classification_fact_refs
from services.game_runtime import (
    RuntimeCommandV1,
    RuntimeNarrativeV1,
    ScenarioNpcDialogueV1,
    SessionIntegrityError,
)
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.dialogue_models import (
    ScenarioDialogueExternalCompletionV1,
    ScenarioDialogueModelOutputV1,
    dialogue_record_checksum,
)
from services.game_runtime.service import (
    GameRuntimeService,
    GameSessionNotFound,
    ScenarioReleasePinV1,
)
from services.game_runtime.store import (
    GameRuntimeStore,
    encode_stored_dialogue,
    game_npc_dialogues_table,
)
from services.persistence.schema import ensure_current_schema

BASE_TIME = datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)


class _RejectingNarrator:
    def __init__(self):
        self.calls = 0

    async def narrate(self, _engine, _session, _result):
        self.calls += 1
        raise AssertionError("V5 dialogue turns must not use the legacy narrator")


class _LegacyNarrator:
    def __init__(self):
        self.calls = 0

    async def narrate(self, _engine, _session, result):
        self.calls += 1
        return RuntimeNarrativeV1(
            narrative=result.turn.narrative,
            source="fallback",
            fallback_reason_code="provider_unavailable",
        )


class _Classifier:
    def __init__(self, source: str):
        self.source = source
        self.calls = 0

    async def classify(self, engine, session, _raw_input):
        self.calls += 1
        action_id = session.available_action_ids[0]
        payload = {
            "kind": "matched",
            "source": self.source,
            "reason_code": (
                "semantic_match" if self.source == "llm" else "exact_match"
            ),
            "action_id": action_id,
            "confidence": 0.91 if self.source == "llm" else 1.0,
            "available_action_ids": list(session.available_action_ids),
        }
        if self.source == "llm":
            payload.update(
                fact_refs=reviewed_classification_fact_refs(
                    engine.course,
                    engine.scenario,
                    list(session.available_action_ids),
                    classification_fact_sources=(engine.classification_fact_sources),
                ),
                provider="test-provider",
                model="test-classifier",
                output_checksum="a" * 64,
            )
        return ActionClassificationV1.model_validate(payload, strict=True)


class _DialogueGenerator:
    def __init__(self, *, barrier: asyncio.Event | None = None, label: str = "A"):
        self.calls = 0
        self.barrier = barrier
        self.label = label
        self.ready: asyncio.Queue[None] | None = None

    async def __call__(self, messages):
        self.calls += 1
        if self.ready is not None:
            await self.ready.put(None)
        if self.barrier is not None:
            await self.barrier.wait()
        context = json.loads(messages[1]["content"])
        passage_id = sorted(item["passage_id"] for item in context["allowed_passages"])[
            0
        ]
        return ScenarioDialogueExternalCompletionV1(
            output=ScenarioDialogueModelOutputV1(
                text=f"外部润色台词-{self.label}",
                used_passage_ids=(passage_id,),
            ),
            provider="test-provider",
            model="test-dialogue",
        )


class _BrokenGeneratorRuntime(GameRuntimeService):
    def _get_dialogue_generator(self):
        raise ImportError("dialogue adapter unavailable")


class _InterleavingDialogueStore(GameRuntimeStore):
    def __init__(self, engine):
        super().__init__(engine)
        self.before_dialogue_read = None

    def load_dialogues(self, session_id):
        callback = self.before_dialogue_read
        self.before_dialogue_read = None
        if callback is not None:
            callback()
        return super().load_dialogues(session_id)


class GameDialogueRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "game-dialogue.sqlite3"
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.db_path)),
            connect_args={"check_same_thread": False},
            future=True,
        )
        ensure_current_schema(self.engine)
        self.repository = ScenarioCatalogRepository(
            content_root=content_root(),
            catalog_path="scenarios/catalog.v1.json",
        )
        self.store = GameRuntimeStore(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    @staticmethod
    def _pin(lesson_id: str, *, release_id: str | None = None):
        if release_id is None:
            resources = workflow.get_published_lesson_resources(
                "C-prequin-state",
                lesson_id,
            )
        else:
            resources = workflow.get_release_lesson_resources(
                "C-prequin-state",
                lesson_id,
                release_id,
            )
        pack = resources.persona_pack
        if pack is not None:
            scenario_id = pack.scenario_id
            scenario_version = pack.scenario_version
            scenario_checksum = pack.scenario_checksum
        else:
            primary = next(
                item for item in resources.course_package.scenario_refs if item.primary
            )
            scenario_id = primary.scenario_id
            scenario_version = primary.scenario_version
            scenario_checksum = primary.checksum
        return (
            resources,
            scenario_id,
            ScenarioReleasePinV1(
                release_id=resources.release_id,
                release_no=resources.release_no,
                release_checksum=resources.release_checksum,
                course_id=resources.course_id,
                lesson_id=resources.lesson_id,
                course_content_version=resources.content_version,
                course_checksum=resources.course_package.checksum,
                scenario_version=scenario_version,
                scenario_checksum=scenario_checksum,
            ),
        )

    def _start(self, service, lesson_id: str, *, suffix: str):
        _resources, scenario_id, pin = self._pin(lesson_id)
        return service.start_session(
            scenario_id,
            user_id="dialogue-owner",
            client_request_id=f"start-{lesson_id}-{suffix}",
            release_pin=pin,
            now=BASE_TIME,
        )[1]

    def test_exact_catalog_lookup_preserves_only_v5_flagship_fact_context(self):
        resources, scenario_id, pin = self._pin("L103")
        exact = self.repository.get_exact(
            scenario_id,
            pin.scenario_version,
            pin.scenario_checksum,
            course_id=pin.course_id,
            lesson_id=pin.lesson_id,
            course_content_version=pin.course_content_version,
            course_checksum=pin.course_checksum,
        )
        self.assertTrue(exact.classification_fact_sources)
        self.assertTrue(
            reviewed_classification_fact_refs(
                exact.course,
                exact.scenario,
                list(
                    exact.start_session(
                        session_id="catalog-context-check",
                        user_id="catalog-checker",
                        started_at=BASE_TIME,
                    ).available_action_ids
                ),
                classification_fact_sources=exact.classification_fact_sources,
            )
        )

        current = workflow.get_current_release("C-prequin-state")
        self.assertIsNotNone(current.parent_release_id)
        old_resources, old_scenario_id, old_pin = self._pin(
            "L103",
            release_id=current.parent_release_id,
        )
        old_record = self.repository.get_published_record(
            old_scenario_id,
            old_pin.scenario_version,
            old_pin.scenario_checksum,
            release_id=old_pin.release_id,
            release_no=old_pin.release_no,
            release_checksum=old_pin.release_checksum,
            course_id=old_pin.course_id,
            lesson_id=old_pin.lesson_id,
            course_content_version=old_pin.course_content_version,
            course_checksum=old_pin.course_checksum,
        )
        self.assertIsNone(old_resources.persona_pack)
        self.assertIsNone(old_record.engine.classification_fact_sources)

        service = GameRuntimeService(self.repository, self.store)
        old_session = service.start_session(
            old_scenario_id,
            user_id="dialogue-owner",
            client_request_id="start-L103-exact-old-release",
            release_pin=old_pin,
            now=BASE_TIME,
        )[1]
        persisted = self.store.load_session(old_session.session_id)
        recovered = service._engine_for(
            persisted.session,
            persisted.envelope.release_identity,
        )
        self.assertIsNone(recovered.classification_fact_sources)

    async def test_v5_fixed_turns_for_both_lessons_are_local_atomic_and_idempotent(
        self,
    ):
        for lesson_id in ("L101", "L103"):
            narrator = _RejectingNarrator()
            generator = _DialogueGenerator()
            service = GameRuntimeService(
                self.repository,
                self.store,
                narrator=narrator,
                dialogue_generator=generator,
            )
            session = self._start(service, lesson_id, suffix="fixed")
            action_id = session.available_action_ids[0]
            result = await service.submit_fixed_action(
                session.session_id,
                client_action_id=f"fixed-{lesson_id}-001",
                action_id=action_id,
                expected_revision=1,
                owner_user_id="dialogue-owner",
            )
            retried = await service.submit_fixed_action(
                session.session_id,
                client_action_id=f"fixed-{lesson_id}-001",
                action_id=action_id,
                expected_revision=1,
                owner_user_id="dialogue-owner",
            )
            with self.subTest(lesson_id=lesson_id):
                self.assertIsNotNone(result.npc_dialogue)
                self.assertEqual(result.npc_dialogue.route_source, "local_state")
                self.assertEqual(generator.calls, 0)
                self.assertEqual(narrator.calls, 0)
                self.assertEqual(
                    retried.model_dump(mode="json"),
                    result.model_dump(mode="json"),
                )
                self.assertEqual(
                    service.get_dialogues(
                        session.session_id,
                        owner_user_id="dialogue-owner",
                    ),
                    (result.npc_dialogue,),
                )
                with self.assertRaises(GameSessionNotFound):
                    service.get_dialogues(
                        session.session_id,
                        owner_user_id="another-student",
                    )

    async def test_only_llm_classification_can_call_external_dialogue_generator(self):
        local_generator = _DialogueGenerator(label="local-should-not-run")
        local_service = GameRuntimeService(
            self.repository,
            self.store,
            classifier=_Classifier("exact"),
            narrator=_RejectingNarrator(),
            dialogue_generator=local_generator,
        )
        local_session = self._start(local_service, "L101", suffix="local")
        local = await local_service.apply_free_input(
            local_session.session_id,
            client_action_id="free-local-001",
            raw_input="先勘察水道",
            expected_revision=1,
            owner_user_id="dialogue-owner",
        )
        self.assertEqual(local.kind, "advanced")
        self.assertEqual(local_generator.calls, 0)
        self.assertEqual(local.result.npc_dialogue.route_source, "local_state")

        external_generator = _DialogueGenerator(label="external")
        external_service = GameRuntimeService(
            self.repository,
            self.store,
            classifier=_Classifier("llm"),
            narrator=_RejectingNarrator(),
            dialogue_generator=external_generator,
        )
        external_session = self._start(external_service, "L103", suffix="external")
        external = await external_service.apply_free_input(
            external_session.session_id,
            client_action_id="free-external-001",
            raw_input="先说明改革目标并听取意见",
            expected_revision=1,
            owner_user_id="dialogue-owner",
        )
        self.assertEqual(external.kind, "advanced")
        self.assertEqual(external_generator.calls, 1)
        self.assertEqual(external.result.npc_dialogue.route_source, "external_api")
        self.assertEqual(external.result.npc_dialogue.text, "外部润色台词-external")

    async def test_concurrent_same_message_returns_the_persisted_dialogue_winner(self):
        release = asyncio.Event()
        ready: asyncio.Queue[None] = asyncio.Queue()
        first_generator = _DialogueGenerator(barrier=release, label="A")
        second_generator = _DialogueGenerator(barrier=release, label="B")
        first_generator.ready = ready
        second_generator.ready = ready
        first = GameRuntimeService(
            self.repository,
            self.store,
            classifier=_Classifier("llm"),
            narrator=_RejectingNarrator(),
            dialogue_generator=first_generator,
        )
        second = GameRuntimeService(
            self.repository,
            self.store,
            classifier=_Classifier("llm"),
            narrator=_RejectingNarrator(),
            dialogue_generator=second_generator,
        )
        session = self._start(first, "L103", suffix="race")
        kwargs = {
            "client_action_id": "free-race-001",
            "raw_input": "先说明目标并听取各方意见",
            "expected_revision": 1,
            "owner_user_id": "dialogue-owner",
        }
        tasks = (
            asyncio.create_task(first.apply_free_input(session.session_id, **kwargs)),
            asyncio.create_task(second.apply_free_input(session.session_id, **kwargs)),
        )
        await asyncio.wait_for(ready.get(), timeout=5)
        await asyncio.wait_for(ready.get(), timeout=5)
        release.set()
        results = await asyncio.gather(*tasks)
        self.assertEqual(
            results[0].model_dump(mode="json"),
            results[1].model_dump(mode="json"),
        )
        stored = first.get_dialogues(
            session.session_id,
            owner_user_id="dialogue-owner",
        )
        self.assertEqual(len(stored), 1)
        self.assertEqual(results[0].result.npc_dialogue, stored[0])

    async def test_dialogue_adapter_initialization_failure_falls_back_atomically(self):
        service = _BrokenGeneratorRuntime(
            self.repository,
            self.store,
            classifier=_Classifier("llm"),
            narrator=_RejectingNarrator(),
        )
        session = self._start(service, "L103", suffix="adapter-init-failure")
        outcome = await service.apply_free_input(
            session.session_id,
            client_action_id="free-adapter-init-failure-001",
            raw_input="请先说明改革目标并听取各方意见",
            expected_revision=1,
            owner_user_id="dialogue-owner",
        )
        self.assertEqual(outcome.kind, "advanced")
        self.assertEqual(outcome.result.npc_dialogue.route_source, "fallback")
        self.assertEqual(
            outcome.result.npc_dialogue.fallback_reason,
            "provider_unavailable",
        )
        self.assertEqual(
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            ),
            (outcome.result.npc_dialogue,),
        )

    async def test_get_dialogues_retries_a_cross_connection_revision_race(self):
        store = _InterleavingDialogueStore(self.engine)
        reader = GameRuntimeService(
            self.repository,
            store,
            narrator=_RejectingNarrator(),
        )
        writer = GameRuntimeService(
            self.repository,
            store,
            narrator=_RejectingNarrator(),
        )
        session = self._start(reader, "L101", suffix="read-race")
        failures = []

        def commit_during_read():
            def run():
                try:
                    asyncio.run(
                        writer.submit_fixed_action(
                            session.session_id,
                            client_action_id="fixed-read-race-001",
                            action_id=session.available_action_ids[0],
                            expected_revision=1,
                            occurred_at=BASE_TIME + timedelta(minutes=1),
                            owner_user_id="dialogue-owner",
                        )
                    )
                except Exception as exc:  # pragma: no cover - asserted below
                    failures.append(exc)

            thread = threading.Thread(target=run)
            thread.start()
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())

        store.before_dialogue_read = commit_during_read
        dialogues = reader.get_dialogues(
            session.session_id,
            owner_user_id="dialogue-owner",
        )
        self.assertEqual(failures, [])
        self.assertEqual(len(dialogues), 1)
        self.assertEqual(dialogues[0].turn_no, 1)

    async def test_v5_public_synchronous_write_is_rejected(self):
        service = GameRuntimeService(
            self.repository,
            self.store,
            narrator=_RejectingNarrator(),
        )
        session = self._start(service, "L101", suffix="sync-rejected")
        with self.assertRaisesRegex(SessionIntegrityError, "asynchronous submit"):
            service.apply_fixed_action(
                session.session_id,
                client_action_id="fixed-sync-rejected-001",
                action_id=session.available_action_ids[0],
                expected_revision=1,
                occurred_at=BASE_TIME + timedelta(minutes=1),
                owner_user_id="dialogue-owner",
            )
        self.assertEqual(
            service.get_session(
                session.session_id,
                owner_user_id="dialogue-owner",
            ).revision,
            1,
        )
        self.assertEqual(
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            ),
            (),
        )

    async def test_v4_release_keeps_legacy_narrator_and_has_no_dialogue(self):
        current = workflow.get_current_release("C-prequin-state")
        self.assertIsNotNone(current.parent_release_id)
        resources, scenario_id, pin = self._pin(
            "L101",
            release_id=current.parent_release_id,
        )
        self.assertIsNone(resources.persona_pack)
        narrator = _LegacyNarrator()
        service = GameRuntimeService(
            self.repository,
            self.store,
            narrator=narrator,
            dialogue_generator=_DialogueGenerator(),
        )
        session = service.start_session(
            scenario_id,
            user_id="dialogue-owner",
            client_request_id="start-v4-legacy",
            release_pin=pin,
            now=BASE_TIME,
        )[1]
        result = await service.submit_fixed_action(
            session.session_id,
            client_action_id="fixed-v4-001",
            action_id=session.available_action_ids[0],
            expected_revision=1,
            owner_user_id="dialogue-owner",
        )
        self.assertEqual(narrator.calls, 1)
        self.assertIsNone(result.npc_dialogue)
        self.assertEqual(
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            ),
            (),
        )

    async def test_old_v5_turn_without_dialogue_can_continue_with_new_projection(self):
        service = GameRuntimeService(
            self.repository,
            self.store,
            narrator=_RejectingNarrator(),
            dialogue_generator=_DialogueGenerator(),
        )
        session = self._start(service, "L101", suffix="upgrade-compatible")
        record = self.store.load_session(
            session.session_id,
            owner_user_id="dialogue-owner",
        )
        engine = service._engine_for(session)
        first_action_id = session.available_action_ids[0]
        first_label = next(
            item.label
            for item in engine.scenario.action_rules
            if item.action_id == first_action_id
        )
        old_command = RuntimeCommandV1(
            client_action_id="old-v5-fixed-001",
            action_id=first_action_id,
            raw_input=first_label,
            action_source="fixed",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        rules_only = engine.apply_action(session, old_command)
        old_style = engine.with_narrative(
            session,
            rules_only,
            RuntimeNarrativeV1(
                narrative=rules_only.turn.narrative,
                source="fallback",
                fallback_reason_code="provider_unavailable",
            ),
        )
        self.store.compare_and_swap(record, old_style.session)

        self.assertEqual(
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            ),
            (),
        )
        continued = await service.submit_fixed_action(
            session.session_id,
            client_action_id="new-v5-fixed-002",
            action_id=old_style.session.available_action_ids[0],
            expected_revision=2,
            occurred_at=BASE_TIME + timedelta(minutes=2),
            owner_user_id="dialogue-owner",
        )
        stored = service.get_dialogues(
            session.session_id,
            owner_user_id="dialogue-owner",
        )
        self.assertIsNotNone(continued.npc_dialogue)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0], continued.npc_dialogue)
        self.assertEqual(stored[0].turn_no, 2)
        third = await service.submit_fixed_action(
            session.session_id,
            client_action_id="new-v5-fixed-003",
            action_id=continued.session.available_action_ids[0],
            expected_revision=3,
            occurred_at=BASE_TIME + timedelta(minutes=3),
            owner_user_id="dialogue-owner",
        )
        self.assertIsNotNone(third.npc_dialogue)
        self.assertEqual(
            [
                item.turn_no
                for item in service.get_dialogues(
                    session.session_id,
                    owner_user_id="dialogue-owner",
                )
            ],
            [2, 3],
        )
        with self.engine.begin() as connection:
            connection.execute(
                game_npc_dialogues_table.delete().where(
                    game_npc_dialogues_table.c.turn_id == stored[0].turn_id
                )
            )
        with self.assertRaisesRegex(SessionIntegrityError, "complete NPC dialogue"):
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            )

    async def test_get_dialogues_recomputes_basis_and_local_projection(self):
        service = GameRuntimeService(
            self.repository,
            self.store,
            narrator=_RejectingNarrator(),
        )
        session = self._start(service, "L101", suffix="read-integrity")
        result = await service.submit_fixed_action(
            session.session_id,
            client_action_id="fixed-read-integrity-001",
            action_id=session.available_action_ids[0],
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
            owner_user_id="dialogue-owner",
        )
        self.assertIsNotNone(result.npc_dialogue)
        original = result.npc_dialogue

        def persist_forgery(**changes):
            payload = original.model_dump(mode="json")
            payload.update(changes)
            payload["output_checksum"] = "0" * 64
            payload["output_checksum"] = dialogue_record_checksum(payload)
            forged = ScenarioNpcDialogueV1.model_validate(payload)
            with self.engine.begin() as connection:
                connection.execute(
                    update(game_npc_dialogues_table)
                    .where(game_npc_dialogues_table.c.turn_id == forged.turn_id)
                    .values(data=encode_stored_dialogue(forged))
                )

        persist_forgery(basis_checksum="b" * 64)
        with self.assertRaisesRegex(SessionIntegrityError, "basis checksum"):
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            )

        persist_forgery(text="重签记录校验和后伪造的本地台词。")
        with self.assertRaisesRegex(SessionIntegrityError, "deterministic projection"):
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            )

        with self.engine.begin() as connection:
            connection.execute(
                game_npc_dialogues_table.delete().where(
                    game_npc_dialogues_table.c.session_id == session.session_id
                )
            )
        with self.assertRaisesRegex(SessionIntegrityError, "complete NPC dialogue"):
            service.get_dialogues(
                session.session_id,
                owner_user_id="dialogue-owner",
            )


if __name__ == "__main__":
    unittest.main()
