from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.ai import ActionClassifierV1
from services.ai.contracts import ClassifierModelOutputV1
from services.content import content_root, workflow
from services.contracts.evidence_v1 import RagAskRequestV1
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.dialogue_models import verify_dialogue_record
from services.game_runtime.service import (
    GameRuntimeService,
    ScenarioReleasePinV1,
)
from services.game_runtime.store import GameRuntimeStore
from services.llm import (
    LLMFailureCode,
    StructuredCompletion,
    StructuredCompletionInfo,
    StructuredLLMError,
)
from services.persistence.schema import ensure_current_schema
from services.rag.retrieval import HybridEvidenceRetriever
from services.rag.service import RagAnswerService

ROUTE_BENCHMARK_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "flagship_agent_route_benchmark_v1.json"
)
RAG_BENCHMARK_PATHS = {
    "L101": REPO_ROOT / "tests" / "fixtures" / "rag_benchmark_l101_v2.json",
    "L103": REPO_ROOT / "tests" / "fixtures" / "rag_benchmark_l103_v2.json",
}
BASE_TIME = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)

EXPECTED_ROUTE_DISTRIBUTION = {
    "exact": 4,
    "local": 5,
    "ambiguous": 4,
    "off_topic": 4,
    "injection": 3,
    "unavailable": 4,
}
EXPECTED_ROUTE_OUTCOMES = {
    "exact": ("advanced", "exact", "exact_match", False),
    "local": ("advanced", "local_state", "local_semantic_match", False),
    "ambiguous": ("clarification_required", "llm", "ambiguous", True),
    "off_topic": ("rejected", "guardrail", "out_of_scope", False),
    "injection": ("rejected", "guardrail", "prompt_injection", False),
    "unavailable": ("rejected", "guardrail", "action_unavailable", False),
}


class ClarificationCompleter:
    """Record optional API use and resolve every ambiguous proposal as ambiguous."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        return StructuredCompletion(
            output=ClassifierModelOutputV1(
                kind="clarification_required",
                confidence=0.55,
                reason_code="ambiguous",
            ),
            info=StructuredCompletionInfo(
                provider="acceptance-provider",
                model="acceptance-classifier",
                finish_reason="stop",
                output_checksum="a" * 64,
            ),
        )


class RecordingClassifier:
    def __init__(self, classifier) -> None:
        self.classifier = classifier
        self.results = []

    async def classify(self, engine, session, raw_input):
        result = await self.classifier.classify(engine, session, raw_input)
        self.results.append(result)
        return result


class OfflineNarrator:
    def __init__(self) -> None:
        self.calls = 0

    async def narrate(self, *_args, **_kwargs):
        self.calls += 1
        raise StructuredLLMError(
            LLMFailureCode.PROVIDER_UNAVAILABLE,
            provider="offline-acceptance-provider",
            retryable=True,
        )


class OfflineDialogueGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, _messages):
        self.calls += 1
        raise StructuredLLMError(
            LLMFailureCode.PROVIDER_UNAVAILABLE,
            provider="offline-acceptance-provider",
            retryable=True,
        )


class FlagshipAgentAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.route_benchmark = json.loads(
            ROUTE_BENCHMARK_PATH.read_text(encoding="utf-8")
        )
        cls.repository = ScenarioCatalogRepository(
            content_root=content_root(),
            catalog_path="scenarios/catalog.v1.json",
        )

    def _runtime(
        self,
        *,
        classifier=None,
        narrator=None,
        dialogue_generator=None,
    ) -> GameRuntimeService:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        ensure_current_schema(engine)
        self.addCleanup(engine.dispose)
        return GameRuntimeService(
            self.repository,
            GameRuntimeStore(engine),
            classifier=classifier,
            narrator=narrator,
            dialogue_generator=dialogue_generator,
        )

    @staticmethod
    def _resources_and_pin(lesson_id: str):
        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            lesson_id,
        )
        pack = resources.persona_pack
        assert pack is not None
        return resources, ScenarioReleasePinV1(
            release_id=resources.release_id,
            release_no=resources.release_no,
            release_checksum=resources.release_checksum,
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            course_content_version=resources.content_version,
            course_checksum=resources.course_package.checksum,
            scenario_version=pack.scenario_version,
            scenario_checksum=pack.scenario_checksum,
        )

    def _start(self, service, lesson_id: str, request_id: str):
        resources, pin = self._resources_and_pin(lesson_id)
        pack = resources.persona_pack
        assert pack is not None
        summary, session = service.start_session(
            pack.scenario_id,
            user_id="flagship-acceptance-student",
            client_request_id=request_id,
            release_pin=pin,
            now=BASE_TIME,
        )
        self.assertEqual(summary.audience, "published")
        self.assertEqual(summary.release_id, resources.release_id)
        return resources, session

    def test_route_fixture_is_balanced_and_pinned_to_both_flagships(self):
        benchmark = self.route_benchmark
        self.assertEqual(
            benchmark["schema_version"],
            "flagship-agent-route-benchmark/v1",
        )
        self.assertEqual(benchmark["course_id"], "C-prequin-state")
        self.assertEqual(
            {lesson["lesson_id"] for lesson in benchmark["lessons"]},
            {"L101", "L103"},
        )
        release = workflow.get_current_release("C-prequin-state")
        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.schema_version, "course-release/v5")

        all_case_ids = []
        all_inputs = []
        release_ids = set()
        for lesson in benchmark["lessons"]:
            cases = lesson["cases"]
            all_case_ids.extend(item["case_id"] for item in cases)
            all_inputs.extend(item["input"] for item in cases)
            self.assertEqual(len(cases), 24)
            self.assertEqual(
                Counter(item["category"] for item in cases),
                EXPECTED_ROUTE_DISTRIBUTION,
            )
            for case in cases:
                expected = EXPECTED_ROUTE_OUTCOMES[case["category"]]
                self.assertEqual(
                    (
                        case["expected_kind"],
                        case["expected_source"],
                        case["expected_reason"],
                        case["api_expected"],
                    ),
                    expected,
                    case["case_id"],
                )
                self.assertTrue(case["case_id"].startswith(f'{lesson["lesson_id"]}-'))
                self.assertTrue(case["input"].strip())
            resources, _pin = self._resources_and_pin(lesson["lesson_id"])
            release_ids.add(resources.release_id)
            self.assertEqual(
                lesson["scenario_id"],
                resources.persona_pack.scenario_id,
            )
            self.assertEqual(resources.evidence_corpus.schema_version, "evidence-corpus/v2")
            self.assertEqual(resources.persona_pack.schema_version, "persona-pack/v1")
            self.assertEqual(resources.release_id, release.release_id)
            exact = workflow.get_release_lesson_resources(
                resources.course_id,
                resources.lesson_id,
                resources.release_id,
            )
            self.assertEqual(exact, resources)
        self.assertEqual(len(all_case_ids), 48)
        self.assertEqual(len(all_case_ids), len(set(all_case_ids)))
        self.assertEqual(len(all_inputs), len(set(all_inputs)))
        self.assertEqual(release_ids, {release.release_id})

    async def test_route_benchmark_uses_api_only_for_ambiguous_proposals(self):
        completer = ClarificationCompleter()
        classifier = RecordingClassifier(ActionClassifierV1(completer=completer))
        service = self._runtime(classifier=classifier)

        for lesson in self.route_benchmark["lessons"]:
            lesson_id = lesson["lesson_id"]
            for case in lesson["cases"]:
                with self.subTest(case_id=case["case_id"]):
                    resources, session = self._start(
                        service,
                        lesson_id,
                        f"route-{case['case_id']}",
                    )
                    calls_before = len(completer.calls)
                    result = await service.apply_free_input(
                        session.session_id,
                        client_action_id=f"action-{case['case_id']}",
                        raw_input=case["input"],
                        expected_revision=session.revision,
                        owner_user_id="flagship-acceptance-student",
                    )
                    classification = classifier.results[-1]
                    self.assertEqual(result.kind, case["expected_kind"])
                    self.assertEqual(classification.source, case["expected_source"])
                    self.assertEqual(
                        classification.reason_code,
                        case["expected_reason"],
                    )
                    self.assertEqual(
                        len(completer.calls) - calls_before,
                        1 if case["api_expected"] else 0,
                    )
                    self.assertEqual(
                        case["api_expected"],
                        case["category"] == "ambiguous",
                    )
                    self.assertEqual(
                        classification.available_action_ids,
                        session.available_action_ids,
                    )
                    if case["api_expected"]:
                        call = completer.calls[-1]
                        self.assertEqual(call["temperature"], 0.0)
                        self.assertEqual(call["max_tokens"], 192)
                        user_message = next(
                            item
                            for item in call["messages"]
                            if item["role"] == "user"
                        )
                        prompt_context = json.loads(user_message["content"])
                        self._assert_classifier_prompt_bounds(
                            resources,
                            session,
                            case["input"],
                            prompt_context,
                            classification,
                        )
                    else:
                        self.assertEqual(classification.fact_refs, [])
                    if result.kind == "advanced":
                        self.assertIsNotNone(result.result)
                        turn = result.result.turn
                        evidence = turn.classification_evidence
                        self.assertIsNotNone(evidence)
                        self.assertEqual(evidence.source, case["expected_source"])
                        self.assertIsNotNone(result.result.npc_dialogue)
                        dialogue = result.result.npc_dialogue
                        assert dialogue is not None
                        self.assertTrue(verify_dialogue_record(dialogue))
                        self.assertEqual(dialogue.route_source, "local_state")
                        self.assertEqual(dialogue.route_reason, "free_input_local")
                        self._assert_dialogue_bounds(resources, dialogue)
                    else:
                        self.assertEqual(
                            service.get_session(session.session_id).revision,
                            session.revision,
                        )

    async def test_both_fixed_six_turn_lessons_finish_offline_with_verified_dialogues(
        self,
    ):
        classifier_provider = ClarificationCompleter()
        narrator = OfflineNarrator()
        dialogue_provider = OfflineDialogueGenerator()
        service = self._runtime(
            classifier=ActionClassifierV1(completer=classifier_provider),
            narrator=narrator,
            dialogue_generator=dialogue_provider,
        )

        for lesson_id in ("L101", "L103"):
            resources, session = self._start(
                service,
                lesson_id,
                f"offline-six-turn-{lesson_id.lower()}",
            )
            pack = resources.persona_pack
            corpus = resources.evidence_corpus
            assert pack is not None
            for turn_no in range(1, 7):
                action_id = session.available_action_ids[0]
                result = await service.submit_fixed_action(
                    session.session_id,
                    client_action_id=f"offline-{lesson_id.lower()}-{turn_no:02d}",
                    action_id=action_id,
                    expected_revision=session.revision,
                    owner_user_id="flagship-acceptance-student",
                )
                session = result.session
                dialogue = result.npc_dialogue
                self.assertIsNotNone(dialogue)
                assert dialogue is not None
                self.assertTrue(verify_dialogue_record(dialogue))
                self.assertEqual(dialogue.turn_no, turn_no)
                self.assertEqual(dialogue.turn_id, result.turn.turn_id)
                self.assertEqual(dialogue.route_source, "local_state")
                self.assertEqual(dialogue.route_reason, "fixed_action_local")
                self._assert_dialogue_bounds(resources, dialogue)
                matching_bindings = [
                    item
                    for item in pack.scenario_voice_bindings
                    if item.binding_id == dialogue.binding_id
                    and item.node_id == dialogue.node_id
                    and item.action_id == dialogue.action_id
                    and item.person_id == dialogue.person_id
                ]
                self.assertEqual(len(matching_bindings), 1)

            with self.subTest(lesson_id=lesson_id):
                self.assertEqual(session.status, "completed")
                self.assertEqual(session.current_turn, 6)
                self.assertIsNotNone(session.ending_id)
                self.assertIsNotNone(session.dossier_id)
                dialogues = service.get_dialogues(
                    session.session_id,
                    owner_user_id="flagship-acceptance-student",
                )
                self.assertEqual(len(dialogues), 6)
                self.assertEqual(
                    tuple(item.turn_id for item in dialogues),
                    tuple(item.turn_id for item in session.turns),
                )
                stored = service.store.load_session(session.session_id)
                self.assertEqual(
                    stored.envelope.release_identity.release_id,
                    resources.release_id,
                )
                self.assertEqual(
                    stored.envelope.release_identity.release_checksum,
                    resources.release_checksum,
                )
                self.assertEqual(pack.checksum, dialogues[-1].persona_pack_checksum)
                self.assertEqual(corpus.checksum, dialogues[-1].evidence_checksum)

        self.assertEqual(classifier_provider.calls, [])
        self.assertEqual(narrator.calls, 0)
        self.assertEqual(dialogue_provider.calls, 0)

    async def test_current_rag_benchmarks_and_personas_never_escape_release_scope(self):
        with tempfile.TemporaryDirectory(
            prefix="chronovita-agent-acceptance-rag-"
        ) as temp_dir:
            answer_service = RagAnswerService(
                HybridEvidenceRetriever(Path(temp_dir) / "rag.sqlite3")
            )
            for lesson_id, benchmark_path in RAG_BENCHMARK_PATHS.items():
                benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
                case = benchmark["cases"][0]
                resources = workflow.get_published_lesson_resources(
                    "C-prequin-state",
                    lesson_id,
                )
                answer = await answer_service.ask(
                    RagAskRequestV1(
                        course_id="C-prequin-state",
                        lesson_id=lesson_id,
                        persona_mode="expert",
                        question=case["question"],
                    )
                )
                corpus_passages = {
                    item.passage_id: item for item in resources.evidence_corpus.passages
                }
                exact_resources = workflow.get_release_lesson_resources(
                    answer.course_id,
                    answer.lesson_id,
                    answer.release_id,
                )
                self.assertEqual(
                    exact_resources.release_checksum,
                    answer.release_checksum,
                )
                self.assertEqual(
                    exact_resources.evidence_corpus.checksum,
                    answer.evidence_checksum,
                )
                cited = {item.passage_id for item in answer.citations}
                with self.subTest(lesson_id=lesson_id, mode="expert"):
                    self.assertEqual(answer.answer_source, "extractive")
                    self.assertTrue(cited)
                    self.assertTrue(cited.issubset(answer.retrieved_passage_ids))
                    self.assertTrue(cited.issubset(corpus_passages))
                    self.assertTrue(cited.intersection(case["expected_passage_ids"]))
                    self.assertEqual(answer.release_id, resources.release_id)
                    self.assertEqual(answer.release_no, resources.release_no)
                    self.assertEqual(
                        answer.release_checksum,
                        resources.release_checksum,
                    )
                    self.assertEqual(
                        answer.evidence_checksum,
                        resources.evidence_corpus.checksum,
                    )
                    for citation in answer.citations:
                        self.assertEqual(
                            citation.source_id,
                            corpus_passages[citation.passage_id].source_id,
                        )

            person_cases = (
                ("L101", "person-7c4825d9", "您是谁？"),
                ("L103", "person-c797c18e", "商鞅方升能说明什么？"),
            )
            for lesson_id, person_id, question in person_cases:
                resources = workflow.get_published_lesson_resources(
                    "C-prequin-state",
                    lesson_id,
                )
                answer = await answer_service.ask(
                    RagAskRequestV1(
                        course_id="C-prequin-state",
                        lesson_id=lesson_id,
                        persona_mode="person",
                        person_id=person_id,
                        question=question,
                    )
                )
                profile = next(
                    item
                    for item in resources.persona_pack.profiles
                    if item.person_id == person_id
                )
                allowed = {item.passage_id for item in profile.evidence_uses}
                cited = {item.passage_id for item in answer.citations}
                with self.subTest(lesson_id=lesson_id, mode="person"):
                    self.assertEqual(answer.person_id, person_id)
                    self.assertEqual(
                        answer.role_disclaimer,
                        "角色化教学表达，不是史料原话。",
                    )
                    self.assertTrue(cited)
                    self.assertTrue(cited.issubset(allowed))
                    self.assertTrue(cited.issubset(answer.retrieved_passage_ids))
                    self.assertEqual(
                        answer.evidence_checksum,
                        resources.evidence_corpus.checksum,
                    )
                    corpus_passages = {
                        item.passage_id: item
                        for item in resources.evidence_corpus.passages
                    }
                    for passage_id in cited:
                        passage = corpus_passages[passage_id]
                        self.assertEqual(
                            passage.persona_scope,
                            "expert_and_listed_people",
                        )
                        self.assertIn(person_id, passage.person_ids)

    def _assert_classifier_prompt_bounds(
        self,
        resources,
        session,
        raw_input: str,
        prompt_context,
        classification,
    ) -> None:
        self.assertEqual(prompt_context["policy_version"], "action-classifier/v1")
        self.assertEqual(prompt_context["student_input"], raw_input)
        self.assertEqual(prompt_context["lesson"]["course_id"], resources.course_id)
        self.assertEqual(prompt_context["lesson"]["lesson_id"], resources.lesson_id)
        self.assertEqual(
            prompt_context["scenario"]["scenario_id"],
            resources.persona_pack.scenario_id,
        )
        self.assertEqual(
            [item["action_id"] for item in prompt_context["available_actions"]],
            session.available_action_ids,
        )

        fact_by_id = {
            item.fact_id: item for item in resources.course_package.facts
        }
        source_by_id = {
            item.source_id: item for item in resources.evidence_corpus.sources
        }
        facts = prompt_context["facts"]
        self.assertTrue(facts)
        self.assertEqual(
            [item["fact_id"] for item in facts],
            classification.fact_refs,
        )
        self.assertEqual(
            len(classification.fact_refs),
            len(set(classification.fact_refs)),
        )
        for fact in facts:
            source_ids = fact["source_ref_ids"]
            self.assertIn(fact["fact_id"], fact_by_id)
            self.assertEqual(
                fact["statement"],
                fact_by_id[fact["fact_id"]].statement,
            )
            self.assertEqual(
                fact["certainty"],
                fact_by_id[fact["fact_id"]].certainty,
            )
            self.assertTrue(source_ids)
            self.assertTrue(set(source_ids).issubset(source_by_id))
            self.assertTrue(
                all(
                    source_by_id[source_id].reliability == "reviewed"
                    for source_id in source_ids
                )
            )

    def _assert_dialogue_bounds(self, resources, dialogue) -> None:
        pack = resources.persona_pack
        corpus = resources.evidence_corpus
        assert pack is not None
        profile = next(
            item for item in pack.profiles if item.person_id == dialogue.person_id
        )
        role_voice_passages = {
            item.passage_id
            for item in profile.evidence_uses
            if item.mode == "role_voice"
        }
        corpus_passages = {item.passage_id for item in corpus.passages}
        corpus_slots = {item.slot_id for item in corpus.answer_slots}
        corpus_boundaries = {item.boundary_id for item in corpus.boundaries}
        person = next(
            item
            for item in resources.course_package.people
            if item.person_id == dialogue.person_id
        )
        self.assertTrue(set(dialogue.used_passage_ids).issubset(corpus_passages))
        self.assertTrue(set(dialogue.used_passage_ids).issubset(role_voice_passages))
        self.assertTrue(set(dialogue.used_slot_ids).issubset(corpus_slots))
        self.assertTrue(
            set(dialogue.used_slot_ids).issubset(profile.focus_answer_slot_ids)
        )
        self.assertTrue(set(profile.boundary_ids).issubset(dialogue.used_boundary_ids))
        self.assertTrue(set(dialogue.used_boundary_ids).issubset(corpus_boundaries))
        self.assertEqual(dialogue.display_name, person.name)
        self.assertEqual(dialogue.role, person.role)
        self.assertEqual(dialogue.persona_kind, profile.persona_kind)
        self.assertEqual(dialogue.portrait_asset_key, profile.portrait_asset_key)
        self.assertEqual(dialogue.release_id, resources.release_id)
        self.assertEqual(dialogue.release_no, resources.release_no)
        self.assertEqual(dialogue.release_checksum, resources.release_checksum)
        self.assertEqual(dialogue.course_id, resources.course_id)
        self.assertEqual(dialogue.lesson_id, resources.lesson_id)
        self.assertEqual(
            dialogue.course_content_version,
            resources.course_package.content_version,
        )
        self.assertEqual(dialogue.course_checksum, resources.course_package.checksum)
        self.assertEqual(dialogue.scenario_id, pack.scenario_id)
        self.assertEqual(dialogue.scenario_version, pack.scenario_version)
        self.assertEqual(dialogue.scenario_checksum, pack.scenario_checksum)
        self.assertEqual(dialogue.persona_pack_id, pack.pack_id)
        self.assertEqual(dialogue.persona_pack_version, pack.pack_version)
        self.assertEqual(dialogue.persona_pack_checksum, pack.checksum)
        self.assertEqual(dialogue.evidence_corpus_id, corpus.corpus_id)
        self.assertEqual(dialogue.evidence_version, corpus.corpus_version)
        self.assertEqual(dialogue.evidence_checksum, corpus.checksum)


if __name__ == "__main__":
    unittest.main()
