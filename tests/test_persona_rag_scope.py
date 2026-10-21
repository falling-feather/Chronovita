import json
import tempfile
import unittest
from pathlib import Path

from services.content import workflow
from services.contracts.evidence_v1 import RagAskRequestV1
from services.rag.retrieval import HybridEvidenceRetriever
from services.rag.service import (
    ROLE_DISCLAIMER,
    RagAnswerService,
    _GroundedAnswerDraft,
)


class PersonaRagScopeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = RagAnswerService(
            HybridEvidenceRetriever(Path(self.temp_dir.name) / "rag.sqlite3")
        )

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_every_consult_identity_stays_inside_published_profile(self):
        for lesson_id in ("L101", "L103"):
            resources = workflow.get_published_lesson_resources(
                "C-prequin-state",
                lesson_id,
            )
            self.assertIsNotNone(resources.persona_pack)
            for profile in resources.persona_pack.profiles:
                if "consult" not in profile.channels:
                    continue
                with self.subTest(lesson_id=lesson_id, person_id=profile.person_id):
                    answer = await self.service.ask(
                        RagAskRequestV1(
                            course_id="C-prequin-state",
                            lesson_id=lesson_id,
                            persona_mode="person",
                            person_id=profile.person_id,
                            question="您是谁？",
                        )
                    )
                    allowed = {item.passage_id for item in profile.evidence_uses}
                    self.assertEqual(answer.answer_source, "extractive")
                    self.assertEqual(answer.role_disclaimer, ROLE_DISCLAIMER)
                    self.assertTrue(answer.citations)
                    self.assertTrue(set(answer.retrieved_passage_ids).issubset(allowed))
                    self.assertTrue(
                        {item.passage_id for item in answer.citations}.issubset(allowed)
                    )

    async def test_historian_note_is_visibly_separate_from_person_voice(self):
        answer = await self.service.ask(
            RagAskRequestV1(
                course_id="C-prequin-state",
                lesson_id="L103",
                persona_mode="person",
                person_id="person-c797c18e",
                question="商鞅方升能说明什么？",
            )
        )
        self.assertEqual(answer.answer_source, "extractive")
        self.assertIn("不能把这部分当作自己的亲历知识", answer.body)
        self.assertIn("史家补充（不属于人物所知）", answer.body)
        self.assertEqual(
            {item.passage_id for item in answer.citations},
            {"shangyang-p012"},
        )

    async def test_persona_local_state_can_use_one_strong_reviewed_passage(self):
        answer = await self.service.ask(
            RagAskRequestV1(
                course_id="C-prequin-state",
                lesson_id="L101",
                persona_mode="person",
                person_id="person-31118bee",
                question="治水为什么需要协作，又会怎样影响治理权威？",
            )
        )
        self.assertEqual(answer.answer_source, "extractive")
        self.assertIn("史家补充（不属于人物所知）", answer.body)
        self.assertIn("不能据此断言一次治水直接创造了王朝", answer.body)
        self.assertEqual(
            {item.passage_id for item in answer.citations},
            {"dayu-p028"},
        )

    async def test_unreviewed_persona_slot_redirects_without_calling_api(self):
        calls = 0

        async def forbidden_generator(_messages):
            nonlocal calls
            calls += 1
            raise AssertionError("a persona scope denial reached the API")

        answer = await self.service.ask(
            RagAskRequestV1(
                course_id="C-prequin-state",
                lesson_id="L103",
                persona_mode="person",
                person_id="person-c797c18e",
                question="睡虎地秦简为什么不能算作你的亲笔法令？",
            ),
            external_generator=forbidden_generator,
        )
        self.assertEqual(answer.answer_source, "insufficient_evidence")
        self.assertIn("超出了当前人物已经审校的知识范围", answer.body)
        self.assertIn("睡虎地秦简主要写于", answer.body)
        self.assertEqual(answer.citations, ())
        self.assertEqual(calls, 0)

    async def test_external_selector_sees_no_boundary_only_passage(self):
        captured_messages: list[dict[str, str]] = []

        async def grounded_generator(messages):
            captured_messages.extend(messages)
            evidence = _evidence_payload(messages)
            return _GroundedAnswerDraft(
                passage_ids=tuple(item["passage_id"] for item in evidence),
                synthesis_mode="causality",
                uncertainty="medium",
            )

        answer = await self.service.ask(
            RagAskRequestV1(
                course_id="C-prequin-state",
                lesson_id="L103",
                persona_mode="person",
                person_id="person-44990ad0",
                question=("军功爵的机会和代价是什么，为什么它也会推动国家动员？"),
            ),
            external_generator=grounded_generator,
        )
        self.assertEqual(answer.answer_source, "model")
        evidence_ids = {
            item["passage_id"] for item in _evidence_payload(captured_messages)
        }
        self.assertEqual(evidence_ids, {"shangyang-p006", "shangyang-p036"})
        self.assertNotIn("shangyang-p037", evidence_ids)
        self.assertEqual(
            {item.passage_id for item in answer.citations},
            evidence_ids,
        )


def _evidence_payload(messages: list[dict[str, str]]) -> list[dict[str, object]]:
    line = next(
        line
        for line in messages[1]["content"].splitlines()
        if line.startswith("EVIDENCE_JSON=")
    )
    return json.loads(line.split("=", 1)[1])


if __name__ == "__main__":
    unittest.main()
