import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.ai import HistoricalNarratorV1, NarratorModelOutputV1
from services.contracts.v1 import (
    CoursePackageV1,
    RuntimeBundleV1,
    calculate_contract_checksum,
)
from services.game_runtime import (
    RevisionConflict,
    RuntimeCommandV1,
    RuntimeNarrativeV1,
)
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.service import GameRuntimeService
from services.game_runtime.store import GameRuntimeStore
from services.llm import (
    LLMFailureCode,
    StructuredCompletion,
    StructuredCompletionInfo,
    StructuredLLMError,
)
from services.persistence.schema import ensure_current_schema


BASE_TIME = datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)


class RecordingCompleter:
    def __init__(self, output_factory=None, error=None):
        self.output_factory = output_factory
        self.error = error
        self.calls = []

    async def complete(
        self,
        messages,
        response_model,
        *,
        model=None,
        temperature=0.0,
        max_tokens=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "response_model": response_model,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self.error is not None:
            raise self.error
        context = json.loads(messages[-1]["content"])
        output = (
            self.output_factory(context)
            if self.output_factory is not None
            else NarratorModelOutputV1(narrative="河势与民情逐渐清晰，治水方略有了可靠依据。")
        )
        return StructuredCompletion(
            output=output,
            info=StructuredCompletionInfo(
                provider="deepseek",
                model="narrator-test-model",
                finish_reason="stop",
                output_checksum="a" * 64,
            ),
        )


class CountingStore(GameRuntimeStore):
    def __init__(self, engine):
        super().__init__(engine)
        self.compare_and_swap_calls = 0

    def compare_and_swap(self, current, next_session, dossier=None):
        self.compare_and_swap_calls += 1
        return super().compare_and_swap(current, next_session, dossier)


class RacingNarrator:
    def __init__(self):
        self.service = None
        self.calls = 0

    async def narrate(self, engine, session, rule_result):
        self.calls += 1
        self.service.apply_fixed_action(
            session.session_id,
            client_action_id="narrator-race-winner",
            action_id="reinforce-dam",
            expected_revision=session.revision,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        return RuntimeNarrativeV1(
            narrative="这段旧 revision 叙事不得落库。",
            source="llm",
            provider="deepseek",
            model="narrator-race-model",
        )


class HistoricalNarratorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = self._reviewed_repository()
        self.engine = self.repository.get_active_record(
            "scenario-dayu-flood-control"
        ).engine
        self.session = self.engine.start_session(
            session_id="session-narrator-unit",
            user_id="student-narrator-unit",
            started_at=BASE_TIME,
            ai_evidence_version=1,
        )
        self.rule_result = self.engine.apply_action(
            self.session,
            RuntimeCommandV1(
                client_action_id="narrator-unit-action",
                raw_input="勘察地势",
                action_id="survey-terrain",
                action_source="fixed",
                expected_revision=1,
                occurred_at=BASE_TIME + timedelta(minutes=1),
            ),
        )

    async def test_strict_output_rejects_rule_fields_duplicates_and_overflow(self):
        with self.assertRaises(ValidationError):
            NarratorModelOutputV1.model_validate(
                {
                    "narrative": "非法结构",
                    "state_changes": [{"risk": 0}],
                }
            )
        with self.assertRaisesRegex(ValidationError, "must be unique"):
            NarratorModelOutputV1(
                narrative="重复引用",
                used_fact_refs=["fact-1", "fact-1"],
            )
        with self.assertRaises(ValidationError):
            NarratorModelOutputV1(narrative="长" * 1201)

    async def test_success_uses_only_reviewed_context_and_builds_llm_evidence(self):
        def output(context):
            return NarratorModelOutputV1(
                narrative="禹先审察水势，再据此筹划疏导，众人对后续方略更为明晰。",
                used_fact_refs=[context["allowed_fact_refs"][0]],
                used_source_ref_ids=[context["allowed_source_ref_ids"][0]],
            )

        completer = RecordingCompleter(output)
        narrator = HistoricalNarratorV1(completer=completer)
        outcome = await narrator.narrate(
            self.engine,
            self.session,
            self.rule_result,
        )
        result = self.engine.with_narrative(
            self.session,
            self.rule_result,
            outcome,
        )

        self.assertEqual(outcome.source, "llm")
        self.assertEqual(result.turn.narrative_source, "llm")
        self.assertEqual(result.turn.narrative_evidence.provider, "deepseek")
        self.assertEqual(result.turn.narrative_evidence.model, "narrator-test-model")
        self.assertEqual(result.session.history[-1].text, result.turn.narrative)
        self.assertEqual(result.session.summary, result.turn.narrative)
        prompt = completer.calls[0]["messages"][-1]["content"]
        self.assertNotIn("teacher_note", prompt)
        self.assertNotIn("url_or_path", prompt)
        self.assertNotIn("raw_input", prompt)
        self.assertNotIn('"effects"', prompt)
        RuntimeBundleV1(
            course=self.engine.course,
            scenario=self.engine.scenario,
            session=result.session,
        )

    async def test_provider_failure_and_reference_escape_use_exact_rule_fallback(self):
        timeout = StructuredLLMError(
            LLMFailureCode.PROVIDER_TIMEOUT,
            provider="deepseek",
            retryable=True,
        )
        timed_out = await HistoricalNarratorV1(
            completer=RecordingCompleter(error=timeout)
        ).narrate(self.engine, self.session, self.rule_result)
        self.assertEqual(timed_out.source, "fallback")
        self.assertEqual(timed_out.fallback_reason_code, "provider_timeout")
        self.assertEqual(timed_out.narrative, self.rule_result.turn.narrative)

        escaped = await HistoricalNarratorV1(
            completer=RecordingCompleter(
                lambda _context: NarratorModelOutputV1(
                    narrative="伪造引用不得进入持久回合。",
                    used_fact_refs=["fact-not-allowed"],
                    used_source_ref_ids=["source-not-allowed"],
                )
            )
        ).narrate(self.engine, self.session, self.rule_result)
        self.assertEqual(escaped.source, "fallback")
        self.assertEqual(
            escaped.fallback_reason_code,
            "reference_out_of_bounds",
        )
        self.assertEqual(escaped.narrative, self.rule_result.turn.narrative)

    async def test_pending_fact_context_skips_provider(self):
        source = self._reviewed_repository(
            remove_pending_markers=False
        ).get_active_record("scenario-dayu-flood-control").engine
        session = source.start_session(
            session_id="session-pending-narrator",
            user_id="student-pending-narrator",
            started_at=BASE_TIME,
            ai_evidence_version=1,
        )
        rule_result = source.apply_action(
            session,
            RuntimeCommandV1(
                client_action_id="pending-action",
                raw_input="勘察地势",
                action_id="survey-terrain",
                expected_revision=1,
                occurred_at=BASE_TIME + timedelta(minutes=1),
            ),
        )
        completer = RecordingCompleter()
        outcome = await HistoricalNarratorV1(completer=completer).narrate(
            source,
            session,
            rule_result,
        )

        self.assertEqual(outcome.source, "fallback")
        self.assertEqual(outcome.fallback_reason_code, "fact_context_unavailable")
        self.assertEqual(completer.calls, [])

    async def test_service_persists_narrative_with_one_cas_and_retry_is_offline(self):
        database = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(database.dispose)
        ensure_current_schema(database)
        store = CountingStore(database)
        completer = RecordingCompleter()
        service = GameRuntimeService(
            self.repository,
            store,
            narrator=HistoricalNarratorV1(completer=completer),
        )
        session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="student-service-narrator",
            client_request_id="request-service-narrator",
            now=BASE_TIME,
        )[1]

        first = await service.submit_fixed_action(
            session.session_id,
            client_action_id="service-narrator-action",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        retry = await service.submit_fixed_action(
            session.session_id,
            client_action_id="service-narrator-action",
            action_id="survey-terrain",
            expected_revision=1,
        )
        replay = service.replay_session(session.session_id)

        self.assertEqual(first.turn.narrative_source, "llm")
        self.assertEqual(first.model_dump(mode="json"), retry.model_dump(mode="json"))
        self.assertEqual(replay.session, first.session)
        self.assertEqual(store.compare_and_swap_calls, 1)
        self.assertEqual(len(completer.calls), 1)

    async def test_revision_change_during_narration_rejects_stale_text(self):
        database = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(database.dispose)
        ensure_current_schema(database)
        store = CountingStore(database)
        narrator = RacingNarrator()
        service = GameRuntimeService(
            self.repository,
            store,
            narrator=narrator,
        )
        narrator.service = service
        session = service.start_session(
            "scenario-dayu-flood-control",
            user_id="student-narrator-race",
            client_request_id="request-narrator-race",
            now=BASE_TIME,
        )[1]

        with self.assertRaises(RevisionConflict):
            await service.submit_fixed_action(
                session.session_id,
                client_action_id="narrator-race-loser",
                action_id="survey-terrain",
                expected_revision=1,
                occurred_at=BASE_TIME + timedelta(minutes=2),
            )

        stored = service.get_session(session.session_id)
        self.assertEqual(stored.current_turn, 1)
        self.assertEqual(stored.turns[0].client_action_id, "narrator-race-winner")
        self.assertNotIn("旧 revision", stored.model_dump_json())
        self.assertEqual(store.compare_and_swap_calls, 1)

    def _reviewed_repository(self, *, remove_pending_markers=True):
        source_repository = ScenarioCatalogRepository(
            content_root=REPO_ROOT / "content",
            catalog_path=REPO_ROOT / "content" / "scenarios" / "catalog.v1.json",
        )
        loaded = source_repository.get_active_record(
            "scenario-dayu-flood-control"
        )
        course_payload = loaded.engine.course.model_dump(mode="json")
        for source in course_payload["source_refs"]:
            source["reliability"] = "reviewed"
        if remove_pending_markers:
            for fact in course_payload["facts"]:
                fact["statement"] = fact["statement"].replace(
                    "【教师待审】",
                    "【测试已审】",
                )
        course_payload["checksum"] = "0" * 64
        course = CoursePackageV1.model_validate(course_payload)
        course_payload["checksum"] = calculate_contract_checksum(course)
        course = CoursePackageV1.model_validate(course_payload)

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        content_root = Path(temp_dir.name)
        (content_root / "course.json").write_text(
            json.dumps(course.model_dump(mode="json"), ensure_ascii=False),
            encoding="utf-8",
        )
        (content_root / "scenario.json").write_text(
            json.dumps(
                loaded.engine.scenario.model_dump(mode="json"),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        entry = loaded.entry.model_dump(mode="json")
        entry.update(
            course_checksum=str(course.checksum),
            course_path="course.json",
            scenario_path="scenario.json",
        )
        catalog_path = content_root / "catalog.json"
        catalog_path.write_text(
            json.dumps(
                {
                    "schema_version": "scenario-catalog/v1",
                    "entries": [entry],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return ScenarioCatalogRepository(
            content_root=content_root,
            catalog_path=catalog_path,
        )


if __name__ == "__main__":
    unittest.main()
