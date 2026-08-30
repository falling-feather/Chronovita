from pathlib import Path
import tempfile
import unittest

from services.content import workflow
from services.contracts.evidence_v1 import RagAskRequestV1
from services.rag.local_reply import (
    LOCAL_REPLY_VERSION,
    detect_unsupported_answer_slot,
    fit_local_reply,
)
from services.rag.query import plan_rag_query
from services.rag.retrieval import HybridEvidenceRetriever, RetrievalBatch


class RagLocalReplyFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = {
            lesson_id: workflow.get_published_lesson_resources(
                "C-prequin-state",
                lesson_id,
            )
            for lesson_id in ("L101", "L103")
        }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.retriever = HybridEvidenceRetriever(
            Path(self.temp_dir.name) / "rag-local-reply.sqlite3"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_contract_version_is_explicit(self):
        self.assertEqual(
            LOCAL_REPLY_VERSION,
            "chronovita-local-reply/v1",
        )

    def test_person_identity_uses_a_published_identity_state(self):
        for lesson_id, person_name in (("L101", "禹"), ("L103", "商鞅")):
            fit = self._fit(
                lesson_id,
                "您到底是谁？",
                person_name=person_name,
            )
            self.assertIsNotNone(fit)
            assert fit is not None
            self.assertEqual(fit.response_mode, "identity")
            self.assertTrue(fit.state_id.startswith(f"{lesson_id}.identity."))
            self.assertIn(person_name, fit.topic_label)
            self.assertFalse(fit.api_synthesis_allowed)
            self.assertTrue(fit.answer_slot_supported)

    def test_overview_is_local_for_both_flagship_lessons(self):
        for lesson_id in ("L101", "L103"):
            fit = self._fit(lesson_id, "这节课讲什么？")
            self.assertIsNotNone(fit)
            assert fit is not None
            self.assertEqual(fit.state_id, f"{lesson_id}.overview")
            self.assertEqual(fit.response_mode, "overview")
            self.assertFalse(fit.api_synthesis_allowed)

    def test_major_l101_topics_have_stable_states(self):
        cases = (
            ("《史记·夏本纪》怎样保存大禹的后世记忆？", "L101.transmitted-memory"),
            ("《禹贡》的九州为什么不能当成施工图？", "L101.yugong-map"),
            ("积石峡溃决洪水能证明什么？", "L101.flood-science"),
            ("二里头的道路网与宫殿说明什么？", "L101.erlitou-state"),
            ("比较堵水和疏导怎样影响治水协作。", "L101.governance"),
        )
        for question, expected_state in cases:
            with self.subTest(question=question):
                fit = self._fit("L101", question)
                self.assertIsNotNone(fit)
                assert fit is not None
                self.assertEqual(fit.state_id, expected_state)
                self.assertTrue(fit.matched_terms)

    def test_major_l103_topics_have_stable_states(self):
        cases = (
            ("徙木立信怎样建立制度信用？", "L103.law-credit"),
            ("军功爵给士卒带来什么机会和战争代价？", "L103.farming-merit"),
            ("县制怎样增强地方治理？", "L103.local-administration"),
            ("什伍连带责任有什么制度代价？", "L103.collective-cost"),
            ("商鞅方升上的两次铭文说明什么？", "L103.fangsheng"),
            ("睡虎地秦简为什么不是商鞅亲笔？", "L103.text-layers"),
            ("秦国变强为什么不能只归功于商鞅？", "L103.state-capacity"),
        )
        for question, expected_state in cases:
            with self.subTest(question=question):
                fit = self._fit("L103", question)
                self.assertIsNotNone(fit)
                assert fit is not None
                self.assertEqual(fit.state_id, expected_state)
                self.assertTrue(fit.matched_terms)

    def test_multi_topic_synthesis_uses_a_cross_evidence_state(self):
        l101 = self._fit(
            "L101",
            "综合比较《史记》、积石峡洪水研究和二里头考古分别能说明什么。",
        )
        l103 = self._fit(
            "L103",
            "综合比较军功爵、县制与商鞅方升分别怎样改变秦国。",
        )
        self.assertIsNotNone(l101)
        self.assertIsNotNone(l103)
        assert l101 is not None and l103 is not None
        self.assertEqual(l101.state_id, "L101.cross-evidence")
        self.assertEqual(l103.state_id, "L103.cross-evidence")
        self.assertGreaterEqual(len(l101.matched_terms), 3)
        self.assertGreaterEqual(len(l103.matched_terms), 3)
        self.assertTrue(l101.api_synthesis_allowed)
        # 商鞅方升槽只批准本地边界回答；把它纳入跨材料比较时也不能
        # 借其他槽位的权限升级到 API。
        self.assertFalse(l103.api_synthesis_allowed)

    def test_evidence_question_selects_boundary_expression_only(self):
        fit = self._fit(
            "L101",
            "二里头宫城能不能直接证明这里就是夏都？",
        )
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertEqual(fit.state_id, "L101.erlitou-state")
        self.assertEqual(fit.response_mode, "boundary")

    def test_unpublished_erlitou_designer_slot_never_allows_api(self):
        question = "二里头宫殿是谁设计的？"
        fit = self._fit("L101", question)
        self.assertEqual(
            detect_unsupported_answer_slot(
                "C-prequin-state",
                "L101",
                question,
            ),
            "erlitou-builder-identity",
        )
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertEqual(fit.response_mode, "unsupported_slot")
        self.assertFalse(fit.answer_slot_supported)
        self.assertFalse(fit.api_synthesis_allowed)
        self.assertEqual(fit.reason, "answer_slot_not_published")

    def test_unpublished_fangsheng_maker_slot_never_allows_api(self):
        questions = (
            "商鞅方升是谁制造的？",
            "商鞅方升是谁设计铸造的？",
            "方升的铸造者是谁？",
        )
        for question in questions:
            with self.subTest(question=question):
                fit = self._fit("L103", question)
                self.assertEqual(
                    detect_unsupported_answer_slot(
                        "C-prequin-state",
                        "L103",
                        question,
                    ),
                    "fangsheng-maker-identity",
                )
                self.assertIsNotNone(fit)
                assert fit is not None
                self.assertEqual(fit.response_mode, "unsupported_slot")
                self.assertFalse(fit.answer_slot_supported)
                self.assertFalse(fit.api_synthesis_allowed)

    def test_supported_fangsheng_question_is_not_mistaken_for_maker_slot(self):
        question = "商鞅方升与商鞅有什么关系？"
        fit = self._fit("L103", question)
        self.assertIsNone(
            detect_unsupported_answer_slot(
                "C-prequin-state",
                "L103",
                question,
            )
        )
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertEqual(fit.state_id, "L103.fangsheng")
        self.assertTrue(fit.answer_slot_supported)

    def test_insufficient_batch_cannot_grant_api_permission(self):
        resources = self.resources["L101"]
        request = RagAskRequestV1(
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            persona_mode="expert",
            question="比较堵水和疏导对治水协作的影响。",
        )
        plan = plan_rag_query(resources, request.question)
        fit = fit_local_reply(
            resources,
            request,
            None,
            plan,
            RetrievalBatch(
                scope_key="no-evidence",
                passages=(),
                supported=False,
                vector_used=False,
            ),
        )
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertFalse(fit.api_synthesis_allowed)
        self.assertEqual(
            fit.reason,
            "matched_state_without_sufficient_evidence",
        )

    def test_unknown_or_mismatched_lesson_fails_closed(self):
        resources = self.resources["L101"]
        request = RagAskRequestV1(
            course_id="C-prequin-state",
            lesson_id="L999",
            persona_mode="expert",
            question="二里头是什么？",
        )
        plan = plan_rag_query(resources, request.question)
        fit = fit_local_reply(
            resources,
            request,
            None,
            plan,
            RetrievalBatch(
                scope_key="mismatch",
                passages=(),
                supported=False,
                vector_used=False,
            ),
        )
        self.assertIsNone(fit)

    def test_fit_is_deterministic_and_contains_no_answer_body(self):
        first = self._fit("L103", "县制怎样增强地方治理？")
        second = self._fit("L103", "县制怎样增强地方治理？")
        self.assertEqual(first, second)
        self.assertFalse(hasattr(first, "body"))
        self.assertFalse(hasattr(first, "citations"))

    def _fit(self, lesson_id: str, question: str, *, person_name: str = ""):
        resources = self.resources[lesson_id]
        person = next(
            (
                candidate
                for candidate in resources.course_package.people
                if candidate.name == person_name
            ),
            None,
        )
        request = RagAskRequestV1(
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            persona_mode="person" if person is not None else "expert",
            person_id=person.person_id if person is not None else None,
            question=question,
        )
        plan = plan_rag_query(resources, question, person=person)
        batch = self.retriever.retrieve_many(
            resources,
            plan.retrieval_queries,
            person_id=person.person_id if person is not None else None,
            limit=8,
        )
        return fit_local_reply(resources, request, person, plan, batch)


if __name__ == "__main__":
    unittest.main()
