from pathlib import Path
import tempfile
import unittest

from services.content import workflow
from services.contracts.evidence_v1 import (
    EvidencePassageV1,
    EvidenceSourceV1,
    RagAskRequestV1,
)
from services.rag.local_reply import fit_local_reply
from services.rag.query import RagQueryPlan, plan_rag_query
from services.rag.retrieval import (
    HybridEvidenceRetriever,
    RetrievalBatch,
    RetrievedPassage,
)
from services.rag.routing import route_rag_query
from services.rag.service import RagAnswerService


def _high_false_hit_batch() -> RetrievalBatch:
    source = EvidenceSourceV1(
        source_id="source-related",
        title="相关课程来源",
        kind="research",
        url_or_path="sources/related.md",
        rights_note="测试夹具",
    )
    rows = tuple(
        RetrievedPassage(
            passage=EvidencePassageV1(
                passage_id=f"passage-related-{index}",
                source_id=source.source_id,
                title="农耕家庭与制度代价",
                text="这是课程内相关但不能回答苹果问题的材料。",
                summary="课程内相关材料",
                evidence_kind="teaching_explanation",
                certainty="interpretation",
                chronology_note="战国时期教学边界",
            ),
            source=source,
            score=1.0,
            relevance=1.0,
            lexical_rank=index,
            vector_rank=None,
            matched_signal_count=3,
            query_signal_coverage=0.95,
            vector_similarity=None,
        )
        for index in (1, 2)
    )
    return RetrievalBatch(
        scope_key="false-hit-expanded-query",
        passages=rows,
        supported=True,
        vector_used=False,
    )


class RagAnswerabilityGuardTests(unittest.TestCase):
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
            Path(self.temp_dir.name) / "answerability.sqlite3"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_related_alias_cannot_turn_an_apple_question_into_course_answer(self):
        resources = self.resources["L103"]
        question = "老百姓为什么喜欢吃苹果？请综合分析。"
        plan = plan_rag_query(resources, question)
        self.assertGreater(len(plan.retrieval_queries), 1)

        fit = self._fit("L103", question, batch=_high_false_hit_batch())
        self.assertIsNone(fit)
        decision = route_rag_query(
            plan,
            _high_false_hit_batch(),
            local_fit=fit,
            require_local_fit=True,
        )
        self.assertEqual(decision.target, "refuse")
        self.assertEqual(decision.reason, "no_published_reply_state")
        self.assertNotEqual(decision.evidence_confidence, "high")
        self.assertFalse(decision.external_api_allowed)

    def test_expanded_query_terms_cannot_select_a_state_without_original_anchor(self):
        resources = self.resources["L103"]
        request = RagAskRequestV1(
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            persona_mode="expert",
            question="这件东西到底怎么样？",
        )
        plan = RagQueryPlan(
            original_question=request.question,
            intent="detail",
            retrieval_queries=(
                request.question,
                "商鞅方升 度量衡 标准量器 两次铭文",
            ),
        )
        fit = fit_local_reply(
            resources,
            request,
            None,
            plan,
            _high_false_hit_batch(),
        )
        self.assertIsNone(fit)
        decision = route_rag_query(
            plan,
            _high_false_hit_batch(),
            local_fit=fit,
            require_local_fit=True,
        )
        self.assertEqual(decision.target, "refuse")
        self.assertEqual(decision.evidence_confidence, "medium")

    def test_unpublished_detail_slots_never_reach_api_or_local_extracts(self):
        cases = (
            ("L103", "比较商鞅方升和睡虎地秦简哪个更适合建立县制，并分析原因。"),
            ("L103", "综合分析军功爵和县制如何帮助商鞅方升建立制度信用。"),
            ("L101", "综合分析积石峡洪水如何帮助二里头建立宫殿道路网。"),
            ("L103", "比较商鞅方升和睡虎地秦简哪个更适合当花盆，并分析原因。"),
            ("L103", "综合分析军功爵和县制如何帮助我通过今天的考试。"),
            ("L103", "商鞅方升为什么是圆形的？请综合分析它的设计思路。"),
            ("L101", "二里头宫殿有多少平方米？"),
            ("L103", "商鞅方升现在值多少钱？"),
            ("L101", "二里头宫殿是谁建的？"),
            ("L103", "方升是谁铸的？"),
            ("L103", "方升出自哪位工匠？"),
            ("L101", "二里头宫殿是什么颜色？"),
            ("L103", "商鞅方升的外形是什么样子？"),
        )
        for lesson_id, question in cases:
            with self.subTest(question=question):
                resources = self.resources[lesson_id]
                plan = plan_rag_query(resources, question)
                batch = self.retriever.retrieve_many(
                    resources,
                    plan.retrieval_queries,
                    limit=8,
                )
                fit = self._fit(lesson_id, question, batch=batch)
                self.assertIsNotNone(fit)
                assert fit is not None
                self.assertFalse(fit.answer_slot_supported)
                self.assertFalse(fit.api_synthesis_allowed)
                decision = route_rag_query(
                    plan,
                    batch,
                    local_fit=fit,
                    require_local_fit=True,
                )
                self.assertEqual(decision.target, "clarify")
                self.assertIn(
                    decision.reason,
                    {
                        "unsupported_answer_slot",
                        "unsupported_question_facet",
                        "unsupported_question_relation",
                    },
                )
                self.assertFalse(decision.external_api_allowed)

    def test_natural_course_predicates_remain_answerable(self):
        cases = (
            ("L101", "二里头的宫殿和道路网能说明早期国家怎样组织劳动吗？"),
            ("L101", "比较疏导与堵水分别会怎样影响公共协作和劳动代价？"),
            ("L103", "军功爵和县制分别怎样增强秦国的国家能力？"),
            ("L103", "商鞅方升与睡虎地秦简各自能说明哪些制度变化？"),
            ("L103", "奖励耕战怎样影响农耕家庭承担的赋役？"),
        )
        for lesson_id, question in cases:
            with self.subTest(question=question):
                resources = self.resources[lesson_id]
                plan = plan_rag_query(resources, question)
                batch = self.retriever.retrieve_many(
                    resources,
                    plan.retrieval_queries,
                    limit=8,
                )
                fit = self._fit(lesson_id, question, batch=batch)
                self.assertIsNotNone(fit)
                assert fit is not None
                self.assertTrue(fit.answer_slot_supported, fit.matched_terms)
                decision = route_rag_query(
                    plan,
                    batch,
                    local_fit=fit,
                    require_local_fit=True,
                )
                self.assertIn(decision.target, {"local_template", "external_api"})

    def test_reviewed_colloquial_alias_remains_locally_answerable(self):
        for question in (
            "搬木头是什么故事？",
            "搬根木头就能让老百姓信法律吗？",
        ):
            with self.subTest(question=question):
                resources = self.resources["L103"]
                plan = plan_rag_query(resources, question)
                batch = self.retriever.retrieve_many(
                    resources,
                    plan.retrieval_queries,
                    limit=8,
                )
                fit = self._fit("L103", question, batch=batch)
                self.assertIsNotNone(fit)
                assert fit is not None
                self.assertEqual(fit.state_id, "L103.law-credit")
                self.assertTrue(fit.answer_slot_supported)
                decision = route_rag_query(
                    plan,
                    batch,
                    local_fit=fit,
                    require_local_fit=True,
                )
                self.assertEqual(decision.target, "local_template")
                self.assertFalse(decision.external_api_allowed)

    def test_state_pack_fails_closed_when_evidence_checksum_changes(self):
        for lesson_id in ("L101", "L103"):
            with self.subTest(lesson_id=lesson_id):
                resources = self.resources[lesson_id]
                changed_corpus = resources.evidence_corpus.model_copy(
                    update={"checksum": "0" * 64}
                )
                changed_resources = resources.model_copy(
                    update={"evidence_corpus": changed_corpus}
                )
                question = (
                    "二里头与早期国家有什么关系？"
                    if lesson_id == "L101"
                    else "徙木立信怎样建立制度信用？"
                )
                request = RagAskRequestV1(
                    course_id=resources.course_id,
                    lesson_id=resources.lesson_id,
                    persona_mode="expert",
                    question=question,
                )
                plan = plan_rag_query(resources, question)
                fit = fit_local_reply(
                    changed_resources,
                    request,
                    None,
                    plan,
                    _high_false_hit_batch(),
                )
                self.assertIsNone(fit)

    def _fit(
        self,
        lesson_id: str,
        question: str,
        *,
        batch: RetrievalBatch,
    ):
        resources = self.resources[lesson_id]
        request = RagAskRequestV1(
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            persona_mode="expert",
            question=question,
        )
        plan = plan_rag_query(resources, question)
        return fit_local_reply(resources, request, None, plan, batch)


class RagAnswerabilityServiceGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = RagAnswerService(
            HybridEvidenceRetriever(
                Path(self.temp_dir.name) / "answerability-service.sqlite3"
            )
        )

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_review_counterexamples_return_no_extracts_and_never_call_api(self):
        calls = 0

        async def forbidden_generator(_messages):
            nonlocal calls
            calls += 1
            raise AssertionError("unsupported questions must not reach the API")

        cases = (
            ("L103", "老百姓为什么喜欢吃苹果？请综合分析。"),
            ("L103", "比较商鞅方升和睡虎地秦简哪个更适合建立县制，并分析原因。"),
            ("L103", "综合分析军功爵和县制如何帮助商鞅方升建立制度信用。"),
            ("L101", "综合分析积石峡洪水如何帮助二里头建立宫殿道路网。"),
            ("L103", "比较商鞅方升和睡虎地秦简哪个更适合当花盆，并分析原因。"),
            ("L103", "综合分析军功爵和县制如何帮助我通过今天的考试。"),
            ("L103", "商鞅方升为什么是圆形的？请综合分析它的设计思路。"),
            ("L101", "二里头宫殿有多少平方米？"),
            ("L103", "商鞅方升现在值多少钱？"),
            ("L101", "二里头宫殿是谁建的？"),
            ("L103", "方升是谁铸的？"),
            ("L103", "方升出自哪位工匠？"),
        )
        for lesson_id, question in cases:
            with self.subTest(question=question):
                answer = await self.service.ask(
                    RagAskRequestV1(
                        course_id="C-prequin-state",
                        lesson_id=lesson_id,
                        persona_mode="expert",
                        question=question,
                    ),
                    external_generator=forbidden_generator,
                )
                self.assertEqual(answer.answer_source, "insufficient_evidence")
                self.assertEqual(answer.citations, ())
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
