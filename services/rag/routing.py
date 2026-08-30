from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from .local_reply import LocalReplyFit
from .query import RagQueryPlan
from .retrieval import RetrievalBatch

RAG_ROUTER_VERSION = "chronovita-rag-router/v1"

RagRouteTarget = Literal[
    "local_template",
    "external_api",
    "clarify",
    "refuse",
]
EvidenceConfidence = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class RagRouteDecision:
    """A deterministic, inspectable routing decision.

    The router never produces prose and never calls a model.  It only decides
    which bounded answer path may run after query planning and retrieval.
    """

    target: RagRouteTarget
    reason: str
    evidence_confidence: EvidenceConfidence
    complexity_score: int

    @property
    def external_api_allowed(self) -> bool:
        return self.target == "external_api"


_OFF_TOPIC = re.compile(
    r"(?:数学|英语|物理|化学|生物)(?:题|作业|公式|考试|答案)|"
    r"(?:天气|气温|降雨|空气质量)(?:怎么样|如何|多少|预报)|"
    r"(?:股票|基金|彩票|汇率|比特币|加密货币)|"
    r"(?:足球|篮球|电竞)(?:比赛|比分|赛程|球员)|"
    r"(?:游戏攻略|代码报错|编程作业|菜谱|外卖|酒店|机票|明星八卦)"
)
_AMBIGUOUS_WHOLE_QUESTION = re.compile(
    r"^(?:请)?(?:"
    r"(?:这|那|它|他|她|这个|那个|这样|那样|这件事|那件事)?"
    r"(?:是)?(?:什么|什么意思|怎么回事|为什么|为何|怎么样|哪个好|怎么办|"
    r"然后呢|是真的吗)|"
    r"讲讲|说说|介绍一下|详细解释一下"
    r")[?？。！!]*$"
)
_AMBIGUOUS_PRONOUN = re.compile(
    r"^(?:他|她|它|他们|她们|这个|那个|这件事|那件事).{0,8}"
    r"(?:吗|呢|为什么|怎么|什么|谁|哪个)[?？。！!]*$"
)
_COMPLEX_SYNTHESIS = re.compile(
    r"比较|权衡|评价|评估|分析|综合|多方面|分别|异同|"
    r"一方面|另一方面|如何理解|如何看待|是否可以说|能否认为|"
    r"请论证|结合.{0,20}(?:分析|说明|解释)"
)
_MULTI_FACTOR = re.compile(
    r"原因|影响|代价|后果|作用|关系|为什么|为何|"
    r"以及|并且|同时|既.{0,16}又"
)


def route_rag_query(
    query_plan: RagQueryPlan,
    batch: RetrievalBatch,
    *,
    local_fit: LocalReplyFit | None = None,
    require_local_fit: bool = False,
) -> RagRouteDecision:
    """Choose one of the four V1 answer paths without invoking a model.

    Safety and grounding take precedence over fluency: blocked and off-topic
    inputs cannot reach an API, and unsupported retrieval can never reach an
    API even when the wording appears complex.
    """

    question = _normalize(query_plan.original_question)
    complexity = _complexity_score(query_plan, question)
    confidence = _evidence_confidence(
        query_plan,
        batch,
        local_fit=local_fit,
    )

    if query_plan.blocked:
        return RagRouteDecision(
            target="refuse",
            reason=f"blocked_{query_plan.blocked_reason or 'query'}",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    if _OFF_TOPIC.search(question):
        return RagRouteDecision(
            target="refuse",
            reason="off_topic",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    if _is_ambiguous(question):
        return RagRouteDecision(
            target="clarify",
            reason="ambiguous_course_question",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    if local_fit is not None and not local_fit.answer_slot_supported:
        return RagRouteDecision(
            target="clarify",
            reason=(
                "unsupported_question_facet"
                if local_fit.reason == "question_facet_not_published"
                else (
                    "unsupported_question_relation"
                    if local_fit.reason == "question_relation_not_published"
                    else (
                        "persona_answer_slot_not_enabled"
                        if local_fit.reason == "persona_answer_slot_not_enabled"
                        else "unsupported_answer_slot"
                    )
                )
            ),
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    # A person identity answer is assembled from the immutable published
    # profile. Retrieval is still required to attach a person-scoped citation,
    # but a one-line identity question should not need the general 0.40 support
    # threshold used for historical claims.
    if (
        query_plan.intent == "identity"
        and batch.passages
        and (local_fit is not None or not require_local_fit)
    ):
        return RagRouteDecision(
            target="local_template",
            reason="published_person_identity",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    if not batch.supported or not batch.passages:
        return RagRouteDecision(
            target="refuse",
            reason="insufficient_evidence",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    if require_local_fit and local_fit is None:
        return RagRouteDecision(
            target="refuse",
            reason="no_published_reply_state",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    if (
        confidence == "high"
        and complexity >= 3
        and len(batch.passages) >= 2
        and (local_fit is None or local_fit.api_synthesis_allowed)
    ):
        return RagRouteDecision(
            target="external_api",
            reason="complex_grounded_synthesis",
            evidence_confidence=confidence,
            complexity_score=complexity,
        )

    return RagRouteDecision(
        target="local_template",
        reason="grounded_local_answer",
        evidence_confidence=confidence,
        complexity_score=complexity,
    )


def _is_ambiguous(question: str) -> bool:
    if not question:
        return True
    return bool(
        _AMBIGUOUS_WHOLE_QUESTION.fullmatch(question)
        or _AMBIGUOUS_PRONOUN.fullmatch(question)
    )


def _evidence_confidence(
    query_plan: RagQueryPlan,
    batch: RetrievalBatch,
    *,
    local_fit: LocalReplyFit | None,
) -> EvidenceConfidence:
    if not batch.passages:
        return "none"
    if not batch.supported:
        return "low"

    candidates = batch.passages[:5]
    coverage = max(item.query_signal_coverage for item in candidates)
    matched_signals = sum(min(item.matched_signal_count, 3) for item in candidates)
    vector_similarity = max(
        (
            item.vector_similarity
            for item in candidates
            if item.vector_similarity is not None
        ),
        default=0.0,
    )
    high_from_retrieval = (
        len(candidates) >= 2
        and coverage >= 0.60
        and (matched_signals >= 3 or vector_similarity >= 0.84)
    )
    if high_from_retrieval and _rewrites_have_original_support(
        query_plan,
        local_fit,
    ):
        return "high"
    return "medium"


def _rewrites_have_original_support(
    query_plan: RagQueryPlan,
    local_fit: LocalReplyFit | None,
) -> bool:
    """Prevent a canonical rewrite from certifying its own retrieval hit.

    A single-query batch was measured from the student's wording directly. For
    a multi-query batch, high confidence is allowed only when at least two
    independent reviewed state anchors are already present in that original
    wording.  ``matched_terms`` is safe here because local fitting never reads
    expanded retrieval queries.
    """

    if len(query_plan.retrieval_queries) <= 1:
        return True
    if local_fit is None or not local_fit.answer_slot_supported:
        return False

    question = _normalize(query_plan.original_question)
    candidates = [
        _normalize(term)
        for term in local_fit.matched_terms
        if _normalize(term) in question
    ]
    # Longer canonical terms subsume their shorter spelling (for example
    # “商鞅方升” and “方升”) and count as one semantic anchor.
    independent: list[str] = []
    for term in sorted(set(candidates), key=lambda value: (-len(value), value)):
        if any(term in existing or existing in term for existing in independent):
            continue
        independent.append(term)
    return len(independent) >= 2


def _complexity_score(query_plan: RagQueryPlan, question: str) -> int:
    score = {
        "comparison": 2,
        "causality": 2,
        "evidence_boundary": 1,
    }.get(query_plan.intent, 0)
    if _COMPLEX_SYNTHESIS.search(question):
        score += 2
    if _MULTI_FACTOR.search(question):
        score += 1
    if len(question) >= 40:
        score += 1
    if question.count("，") + question.count("；") >= 2:
        score += 1
    return min(score, 6)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


__all__ = [
    "EvidenceConfidence",
    "RAG_ROUTER_VERSION",
    "RagRouteDecision",
    "RagRouteTarget",
    "route_rag_query",
]
