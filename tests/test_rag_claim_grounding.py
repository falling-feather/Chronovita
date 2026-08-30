import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from services.contracts.evidence_v1 import RagAskRequestV1
from services.rag.retrieval import HybridEvidenceRetriever
from services.rag.service import (
    RagAnswerService,
    RagExternalAnswerUnavailable,
    _GroundedAnswerDraft,
)


class RagClaimGroundingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = RagAnswerService(
            HybridEvidenceRetriever(Path(self.temp_dir.name) / "rag.sqlite3")
        )
        self.request = RagAskRequestV1(
            course_id="C-prequin-state",
            lesson_id="L101",
            persona_mode="expert",
            question="比较积石峡和二里头的证据边界。",
        )

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_free_model_prose_is_not_part_of_internal_contract(self) -> None:
        self.assertNotIn("body", _GroundedAnswerDraft.model_fields)
        fabricated_bodies = (
            "积石峡洪水发生在公元前1921年，因而可以确定夏王朝存在。",
            "秦始皇命令李冰主持修建都江堰，这解释了积石峡洪水。",
            "李冰与积石峡洪水有关。",
            "积石峡洪水导致夏王朝灭亡。",
            "积石峡洪水直接证明了禹和夏王朝。",
            "积石峡洪水迫使所有居民迁徙。",
            "积石峡洪水淹没了整个秦国。",
            "积石峡洪水让禹获得神力。",
            "积石峡洪水由外星人制造。",
            "积石峡洪水引发瘟疫并摧毁全部农田。",
        )

        for body in fabricated_bodies:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                _GroundedAnswerDraft.model_validate(
                    {
                        "body": body,
                        "passage_ids": ("dayu-p020", "dayu-p023"),
                        "synthesis_mode": "boundary",
                        "uncertainty": "medium",
                    }
                )

    async def test_valid_model_selection_uses_server_composed_body(self) -> None:
        captured_messages = []

        async def selector(messages):
            captured_messages.extend(messages)
            return _GroundedAnswerDraft(
                passage_ids=("dayu-p044", "dayu-p040", "dayu-p039"),
                synthesis_mode="boundary",
                uncertainty="low",
            )

        answer = await self.service.ask(
            self.request,
            external_generator=selector,
        )

        self.assertEqual(answer.answer_source, "model")
        self.assertEqual(
            {citation.passage_id for citation in answer.citations},
            {"dayu-p044", "dayu-p040", "dayu-p039"},
        )
        self.assertEqual(answer.uncertainty, "high")
        self.assertIn("当前发布证据可以支持", answer.body)
        self.assertIn("证据多样性取决于材料能力", answer.body)
        self.assertIn("自然事件链可以检验", answer.body)
        prompt = "\n".join(item["content"] for item in captured_messages)
        self.assertIn("dayu-p044", prompt)
        self.assertIn("dayu-p040", prompt)
        self.assertIn("dayu-p039", prompt)
        self.assertNotIn("dayu-p030", prompt)
        for forbidden in ("1921", "秦始皇", "李冰", "都江堰", "灭亡"):
            self.assertNotIn(forbidden, answer.body)

    async def test_selector_cannot_choose_weak_top_eight_passage(self) -> None:
        async def weak_selection(_messages):
            return _GroundedAnswerDraft(
                passage_ids=("dayu-p030",),
                synthesis_mode="boundary",
                uncertainty="low",
            )

        answer = await self.service.ask(
            self.request,
            external_generator=weak_selection,
        )

        self.assertEqual(answer.answer_source, "extractive")
        self.assertNotIn(
            "dayu-p030",
            {citation.passage_id for citation in answer.citations},
        )

    async def test_selection_must_cover_every_matched_query_facet(self) -> None:
        async def incomplete_selection(_messages):
            return _GroundedAnswerDraft(
                passage_ids=("dayu-p020", "dayu-p023"),
                synthesis_mode="boundary",
                uncertainty="medium",
            )

        answer = await self.service.ask(
            self.request,
            external_generator=incomplete_selection,
        )

        self.assertEqual(answer.answer_source, "extractive")

    async def test_low_uncertainty_requires_consensus_source_diversity(self) -> None:
        async def consensus_selection(_messages):
            return _GroundedAnswerDraft(
                passage_ids=("dayu-p038", "dayu-p035", "dayu-p014"),
                synthesis_mode="boundary",
                uncertainty="low",
            )

        answer = await self.service.ask(
            self.request.model_copy(
                update={
                    "question": (
                        "综合分析二里头宫殿区、道路网、手工业和区域聚落层级"
                        "为何能支持早期国家研究，又不能证明什么？"
                    )
                }
            ),
            external_generator=consensus_selection,
        )

        self.assertEqual(answer.answer_source, "model")
        self.assertEqual(answer.uncertainty, "low")

    async def test_selector_cannot_change_required_synthesis_mode(self) -> None:
        async def wrong_mode(_messages):
            return _GroundedAnswerDraft(
                passage_ids=("dayu-p020", "dayu-p023"),
                synthesis_mode="causality",
                uncertainty="medium",
            )

        answer = await self.service.ask(
            self.request,
            external_generator=wrong_mode,
        )

        self.assertEqual(answer.answer_source, "extractive")

    async def test_expected_external_unavailability_falls_back(self) -> None:
        async def unavailable(_messages):
            raise RagExternalAnswerUnavailable("online capacity unavailable")

        answer = await self.service.ask(
            self.request,
            external_generator=unavailable,
        )

        self.assertEqual(answer.answer_source, "extractive")

    async def test_provider_timeout_falls_back(self) -> None:
        async def provider_timeout(_messages):
            raise TimeoutError("provider timeout")

        answer = await self.service.ask(
            self.request,
            external_generator=provider_timeout,
        )

        self.assertEqual(answer.answer_source, "extractive")

    async def test_programming_error_is_not_silently_converted(self) -> None:
        async def broken_generator(_messages):
            raise TypeError("generator integration bug")

        with self.assertRaisesRegex(TypeError, "integration bug"):
            await self.service.ask(
                self.request,
                external_generator=broken_generator,
            )


if __name__ == "__main__":
    unittest.main()
