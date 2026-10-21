from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.ai import ActionClassifierV1, ClassifierModelOutputV1
from services.content import content_root, workflow
from services.game_runtime import SituationEngineV1
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.llm import StructuredCompletion, StructuredCompletionInfo


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


class _ClarificationCompleter:
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
        self.calls.append({"messages": messages, "response_model": response_model})
        return StructuredCompletion(
            output=ClassifierModelOutputV1(
                kind="clarification_required",
                confidence=0.5,
                reason_code="ambiguous",
            ),
            info=StructuredCompletionInfo(
                provider="release-context-test",
                model="classifier-test",
                finish_reason="stop",
                output_checksum="a" * 64,
            ),
        )


class FlagshipClassificationReleaseContextTests(
    unittest.IsolatedAsyncioTestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = ScenarioCatalogRepository(
            content_root=content_root(),
            catalog_path="scenarios/catalog.v1.json",
        )

    async def test_both_flagships_use_only_current_reviewed_release_facts(self):
        cases = {
            "L101": "踏勘支流还是加固河岸",
            "L103": "听取意见还是公布目标",
        }
        for lesson_id, proposal in cases.items():
            with self.subTest(lesson_id=lesson_id):
                resources = workflow.get_published_lesson_resources(
                    "C-prequin-state",
                    lesson_id,
                )
                pack = resources.persona_pack
                self.assertIsNotNone(pack)
                engine = self.repository.get_active(pack.scenario_id)
                session = engine.start_session(
                    session_id=f"release-context-{lesson_id}",
                    user_id="release-context-student",
                    started_at=NOW,
                    ai_evidence_version=1,
                )
                completer = _ClarificationCompleter()
                result = await ActionClassifierV1(completer=completer).classify(
                    engine,
                    session,
                    proposal,
                )

                self.assertEqual(result.source, "llm")
                self.assertEqual(result.reason_code, "ambiguous")
                self.assertTrue(result.fact_refs)
                self.assertEqual(len(completer.calls), 1)
                prompt = json.loads(completer.calls[0]["messages"][1]["content"])
                prompt_facts = prompt["facts"]
                self.assertEqual(
                    [item["fact_id"] for item in prompt_facts],
                    result.fact_refs,
                )
                reviewed_sources = {
                    item.source_id
                    for item in resources.evidence_corpus.sources
                    if item.reliability == "reviewed"
                }
                disputed_sources = {
                    item.source_id
                    for item in resources.evidence_corpus.sources
                    if item.reliability == "disputed"
                }
                used_sources = {
                    source_id
                    for item in prompt_facts
                    for source_id in item["source_ref_ids"]
                }
                current_fact_ids = set(engine.scenario.fact_refs)
                action_by_id = {
                    item.action_id: item for item in engine.scenario.action_rules
                }
                for action_id in session.available_action_ids:
                    current_fact_ids.update(action_by_id[action_id].fact_refs)
                self.assertLessEqual(set(result.fact_refs), current_fact_ids)
                self.assertLessEqual(used_sources, reviewed_sources)
                self.assertTrue(used_sources.isdisjoint(disputed_sources))

    async def test_unbound_engine_preserves_fail_closed_legacy_policy(self):
        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            "L101",
        )
        pack = resources.persona_pack
        self.assertIsNotNone(pack)
        published = self.repository.get_active(pack.scenario_id)
        unbound = SituationEngineV1(published.course, published.scenario)
        session = unbound.start_session(
            session_id="unbound-release-context",
            user_id="release-context-student",
            started_at=NOW,
            ai_evidence_version=1,
        )
        completer = _ClarificationCompleter()
        result = await ActionClassifierV1(completer=completer).classify(
            unbound,
            session,
            "踏勘支流还是加固河岸",
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.reason_code, "fact_context_unavailable")
        self.assertEqual(completer.calls, [])


if __name__ == "__main__":
    unittest.main()
