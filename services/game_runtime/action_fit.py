from __future__ import annotations

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from typing import Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.contracts.v1 import ContractId
from services.game_runtime import AvailableActionV1

ACTION_FIT_POLICY_VERSION = "local-action-fit/v1"

ActionFitKind = Literal[
    "exact_alias",
    "local_semantic_match",
    "ambiguous",
    "off_topic",
    "injection",
]
ActionFitReason = Literal[
    "exact_action_label",
    "exact_reviewed_alias",
    "unique_high_confidence",
    "multiple_exact_candidates",
    "competing_candidates",
    "low_confidence",
    "action_unavailable",
    "topic_unrelated",
    "invalid_input",
    "prompt_injection",
]
MatchBasis = Literal["label", "description", "reviewed_alias"]


class ActionFitCandidateV1(BaseModel):
    """One deterministic candidate considered by the local fitting policy."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    action_id: ContractId
    score: float = Field(ge=0, le=1)
    available: bool
    match_basis: MatchBasis
    matched_phrase: str = Field(min_length=1, max_length=160)


class LocalActionFitResultV1(BaseModel):
    """Fail-closed result from the zero-model action fitting layer."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["local-action-fit/v1"] = "local-action-fit/v1"
    policy_version: Literal["local-action-fit/v1"] = ACTION_FIT_POLICY_VERSION
    lesson_id: Literal["L101", "L103"]
    kind: ActionFitKind
    reason_code: ActionFitReason
    action_id: ContractId | None = None
    blocked_action_id: ContractId | None = None
    score: float = Field(ge=0, le=1)
    runner_up_score: float = Field(ge=0, le=1)
    score_gap: float = Field(ge=0, le=1)
    normalized_input: str = Field(max_length=400)
    available_action_ids: tuple[ContractId, ...]
    candidates: tuple[ActionFitCandidateV1, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "LocalActionFitResultV1":
        available = set(self.available_action_ids)
        if len(available) != len(self.available_action_ids):
            raise ValueError("available_action_ids must be unique")
        candidate_ids = [item.action_id for item in self.candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate action_ids must be unique")
        if any(
            item.available != (item.action_id in available) for item in self.candidates
        ):
            raise ValueError("candidate availability must match available_action_ids")
        if list(self.candidates) != sorted(
            self.candidates,
            key=lambda item: (-item.score, item.action_id),
        ):
            raise ValueError("candidates must use stable descending score order")
        expected_score = self.candidates[0].score if self.candidates else 0.0
        expected_runner_up = (
            self.candidates[1].score if len(self.candidates) > 1 else 0.0
        )
        if abs(self.score - expected_score) > 0.000001:
            raise ValueError("score must equal the leading candidate score")
        if abs(self.runner_up_score - expected_runner_up) > 0.000001:
            raise ValueError("runner_up_score must equal the second candidate score")
        if abs(self.score_gap - max(0.0, self.score - self.runner_up_score)) > 0.000001:
            raise ValueError("score_gap must be derived from the first two candidates")

        matched = self.kind in {"exact_alias", "local_semantic_match"}
        if matched:
            if self.action_id is None or self.action_id not in available:
                raise ValueError("a match must name one currently available action")
            if not self.candidates or self.candidates[0].action_id != self.action_id:
                raise ValueError("a match must select its leading candidate")
            if self.blocked_action_id is not None:
                raise ValueError("a match cannot name a blocked action")
        elif self.action_id is not None:
            raise ValueError("a non-match cannot select an action")

        if self.reason_code == "action_unavailable":
            if (
                self.kind != "ambiguous"
                or self.blocked_action_id is None
                or self.blocked_action_id in available
                or not self.candidates
                or self.candidates[0].action_id != self.blocked_action_id
            ):
                raise ValueError(
                    "action_unavailable must identify the leading blocked action"
                )
        elif self.blocked_action_id is not None:
            raise ValueError("blocked_action_id is reserved for action_unavailable")

        exact_reasons = {"exact_action_label", "exact_reviewed_alias"}
        if self.kind == "exact_alias":
            if self.reason_code not in exact_reasons or self.score != 1.0:
                raise ValueError("exact_alias requires an exact reason and score 1")
        elif self.reason_code in exact_reasons:
            raise ValueError("exact reasons are reserved for exact_alias")
        if (
            self.kind == "local_semantic_match"
            and self.reason_code != "unique_high_confidence"
        ):
            raise ValueError("local_semantic_match requires unique_high_confidence")
        if self.kind == "injection" and (
            self.reason_code != "prompt_injection" or self.candidates
        ):
            raise ValueError("injection must fail closed without candidates")
        if self.kind == "off_topic" and self.reason_code not in {
            "topic_unrelated",
            "invalid_input",
        }:
            raise ValueError("off_topic requires an off-topic reason")
        return self


class LocalActionFitterV1:
    """Fit free Chinese proposals to current actions without an external model.

    The fitter deliberately has no I/O and no model adapter.  Its reviewed alias
    vocabulary is limited to the two V1.0 flagship lessons.  Only one available,
    high-scoring candidate with a clear margin can advance the game.
    """

    def __init__(
        self,
        *,
        match_threshold: float = 0.72,
        margin_threshold: float = 0.12,
        ambiguity_floor: float = 0.40,
    ) -> None:
        if not 0.5 <= match_threshold <= 1:
            raise ValueError("match_threshold must stay inside [0.5, 1]")
        if not 0.05 <= margin_threshold <= 0.5:
            raise ValueError("margin_threshold must stay inside [0.05, 0.5]")
        if not 0.2 <= ambiguity_floor < match_threshold:
            raise ValueError("ambiguity_floor must be below match_threshold")
        self.match_threshold = match_threshold
        self.margin_threshold = margin_threshold
        self.ambiguity_floor = ambiguity_floor

    def fit(
        self,
        *,
        lesson_id: Literal["L101", "L103"],
        raw_input: str,
        available_actions: Sequence[AvailableActionV1],
    ) -> LocalActionFitResultV1:
        actions = tuple(available_actions)
        available_ids = tuple(item.action_id for item in actions)
        if len(set(available_ids)) != len(available_ids):
            raise ValueError("available actions must have unique action_ids")
        if lesson_id not in _REVIEWED_ALIASES:
            raise ValueError("local fitting is limited to L101 and L103")

        if (
            not isinstance(raw_input, str)
            or not raw_input.strip()
            or len(raw_input) > 400
        ):
            return self._result(
                lesson_id=lesson_id,
                kind="off_topic",
                reason_code="invalid_input",
                normalized_input="",
                available_action_ids=available_ids,
            )
        normalized = _normalize_text(raw_input)
        if not normalized:
            return self._result(
                lesson_id=lesson_id,
                kind="off_topic",
                reason_code="invalid_input",
                normalized_input="",
                available_action_ids=available_ids,
            )
        if _looks_like_prompt_injection(raw_input):
            return self._result(
                lesson_id=lesson_id,
                kind="injection",
                reason_code="prompt_injection",
                normalized_input=normalized,
                available_action_ids=available_ids,
            )

        phrases = _phrase_index(lesson_id, actions)
        exact = _exact_candidates(normalized, phrases, set(available_ids))
        if exact:
            if len(exact) == 1 and exact[0].available:
                reason: ActionFitReason = (
                    "exact_action_label"
                    if exact[0].match_basis == "label"
                    else "exact_reviewed_alias"
                )
                return self._result(
                    lesson_id=lesson_id,
                    kind="exact_alias",
                    reason_code=reason,
                    normalized_input=normalized,
                    available_action_ids=available_ids,
                    candidates=exact,
                    action_id=exact[0].action_id,
                )
            if len(exact) == 1:
                return self._result(
                    lesson_id=lesson_id,
                    kind="ambiguous",
                    reason_code="action_unavailable",
                    normalized_input=normalized,
                    available_action_ids=available_ids,
                    candidates=exact,
                    blocked_action_id=exact[0].action_id,
                )
            return self._result(
                lesson_id=lesson_id,
                kind="ambiguous",
                reason_code="multiple_exact_candidates",
                normalized_input=normalized,
                available_action_ids=available_ids,
                candidates=exact,
            )

        if _is_explicitly_off_topic(raw_input):
            return self._result(
                lesson_id=lesson_id,
                kind="off_topic",
                reason_code="topic_unrelated",
                normalized_input=normalized,
                available_action_ids=available_ids,
            )

        candidates = _semantic_candidates(normalized, phrases, set(available_ids))
        leading = candidates[0] if candidates else None
        runner_up = candidates[1] if len(candidates) > 1 else None
        score = leading.score if leading else 0.0
        gap = score - (runner_up.score if runner_up else 0.0)
        multi_intent = _contains_multi_intent_marker(raw_input)

        if leading and not leading.available and score >= self.match_threshold:
            return self._result(
                lesson_id=lesson_id,
                kind="ambiguous",
                reason_code="action_unavailable",
                normalized_input=normalized,
                available_action_ids=available_ids,
                candidates=candidates,
                blocked_action_id=leading.action_id,
            )
        if (
            leading
            and leading.available
            and score >= self.match_threshold
            and gap >= self.margin_threshold
            and not (multi_intent and runner_up and runner_up.score >= 0.28)
        ):
            return self._result(
                lesson_id=lesson_id,
                kind="local_semantic_match",
                reason_code="unique_high_confidence",
                normalized_input=normalized,
                available_action_ids=available_ids,
                candidates=candidates,
                action_id=leading.action_id,
            )

        topic_relevant = _is_topic_relevant(lesson_id, raw_input)
        generic_proposal = _looks_like_generic_proposal(raw_input)
        if score >= self.ambiguity_floor or topic_relevant or generic_proposal:
            reason = (
                "competing_candidates"
                if runner_up
                and runner_up.score >= self.ambiguity_floor
                and (gap < self.margin_threshold or multi_intent)
                else "low_confidence"
            )
            return self._result(
                lesson_id=lesson_id,
                kind="ambiguous",
                reason_code=reason,
                normalized_input=normalized,
                available_action_ids=available_ids,
                candidates=candidates,
            )
        return self._result(
            lesson_id=lesson_id,
            kind="off_topic",
            reason_code="topic_unrelated",
            normalized_input=normalized,
            available_action_ids=available_ids,
            candidates=candidates,
        )

    @staticmethod
    def _result(
        *,
        lesson_id: Literal["L101", "L103"],
        kind: ActionFitKind,
        reason_code: ActionFitReason,
        normalized_input: str,
        available_action_ids: tuple[str, ...],
        candidates: Sequence[ActionFitCandidateV1] = (),
        action_id: str | None = None,
        blocked_action_id: str | None = None,
    ) -> LocalActionFitResultV1:
        ranked = tuple(candidates[:3])
        score = ranked[0].score if ranked else 0.0
        runner_up_score = ranked[1].score if len(ranked) > 1 else 0.0
        return LocalActionFitResultV1.model_validate(
            {
                "lesson_id": lesson_id,
                "kind": kind,
                "reason_code": reason_code,
                "action_id": action_id,
                "blocked_action_id": blocked_action_id,
                "score": score,
                "runner_up_score": runner_up_score,
                "score_gap": round(max(0.0, score - runner_up_score), 6),
                "normalized_input": normalized_input,
                "available_action_ids": available_action_ids,
                "candidates": ranked,
            },
            strict=True,
        )


def fit_local_action(
    *,
    lesson_id: Literal["L101", "L103"],
    raw_input: str,
    available_actions: Sequence[AvailableActionV1],
) -> LocalActionFitResultV1:
    return LocalActionFitterV1().fit(
        lesson_id=lesson_id,
        raw_input=raw_input,
        available_actions=available_actions,
    )


_PUNCTUATION_RE = re.compile(r"[^0-9a-z\u3400-\u9fff]+", re.IGNORECASE)
_FILLER_RE = re.compile(
    r"(?:我(?:们)?(?:认为|觉得|建议|想要|想)?|"
    r"不如|最好|还是|请|希望|能否|可否|可以|应该|决定|选择|采取|"
    r"这个|一种|一下|先来|先把|先让|立即|马上|现在)"
)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = _PUNCTUATION_RE.sub("", normalized)
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = _FILLER_RE.sub("", normalized)
    return normalized


_PROMPT_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(?:all\s+)?(?:previous|above|system|developer).{0,20}(?:instruction|message|prompt)",
        r"(?:show|reveal|print|leak).{0,24}(?:system\s+prompt|developer\s+message|api[_ -]?key|secret)",
        r"(?:system\s+prompt|developer\s+message|action_id)",
        r"(?:忽略|无视|绕过|覆盖).{0,18}(?:规则|指令|提示词|系统消息|开发者消息|限制)",
        r"(?:显示|泄露|打印|输出).{0,18}(?:提示词|系统消息|开发者消息|密钥|令牌)",
        r"(?:直接|强制|偷偷).{0,14}(?:修改|设置|篡改).{0,14}(?:状态|数值|结局|事件|人物态度|回合)",
        r"(?:假装|扮演).{0,16}(?:没有|不受).{0,12}(?:规则|限制)",
    )
)


def _looks_like_prompt_injection(value: str) -> bool:
    return any(pattern.search(value) for pattern in _PROMPT_INJECTION_PATTERNS)


_OFF_TOPIC_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:天气|气温|下雨).{0,12}(?:多少|怎么样|预报)",
        r"(?:写|修改|调试).{0,10}(?:代码|程序|python|javascript|网页)",
        r"(?:股票|基金|比特币|彩票|房价)",
        r"(?:足球|篮球|世界杯|nba|电子游戏|王者荣耀)",
        r"(?:披萨|火锅|奶茶|外卖|菜谱)",
        r"(?:唱首歌|讲笑话|电影推荐|旅游攻略)",
        r"(?:解方程|高等数学|英语作文|物理作业)",
    )
)


def _is_explicitly_off_topic(value: str) -> bool:
    return any(pattern.search(value) for pattern in _OFF_TOPIC_PATTERNS)


_TOPIC_TERMS = {
    "L101": (
        "洪水",
        "水势",
        "河道",
        "支流",
        "低地",
        "地形",
        "分洪",
        "疏浚",
        "开渠",
        "堤",
        "聚落",
        "粮",
        "赈济",
        "劳作",
        "人力",
        "议事",
        "水图",
        "治水",
    ),
    "L103": (
        "变法",
        "改革",
        "法令",
        "规则",
        "申诉",
        "赏罚",
        "贵族",
        "农户",
        "耕",
        "军功",
        "战备",
        "计量",
        "度量衡",
        "账册",
        "县",
        "吏",
        "征发",
        "严罚",
        "旧制",
        "连坐",
    ),
}


def _is_topic_relevant(lesson_id: str, value: str) -> bool:
    return any(term in value for term in _TOPIC_TERMS[lesson_id])


_GENERIC_PROPOSAL_RE = re.compile(
    r"(?:怎么办|如何处理|怎么做|想想办法|稳妥|激进|折中|协商|推进|暂停|听取|保护|记录|调查|公开|执行)"
)


def _looks_like_generic_proposal(value: str) -> bool:
    return bool(_GENERIC_PROPOSAL_RE.search(value))


def _contains_multi_intent_marker(value: str) -> bool:
    return bool(
        re.search(r"(?:还是|或者|同时|并且|一边.{0,12}一边|既.{0,12}又)", value)
    )


class _Phrase:
    __slots__ = ("action_id", "basis", "normalized", "raw")

    def __init__(self, action_id: str, basis: MatchBasis, raw: str) -> None:
        self.action_id = action_id
        self.basis = basis
        self.raw = raw
        self.normalized = _normalize_text(raw)


def _phrase_index(
    lesson_id: str,
    actions: Sequence[AvailableActionV1],
) -> tuple[_Phrase, ...]:
    result: list[_Phrase] = []
    seen: set[tuple[str, str]] = set()

    def add(action_id: str, basis: MatchBasis, raw: str) -> None:
        phrase = _Phrase(action_id, basis, raw)
        key = (action_id, phrase.normalized)
        if not phrase.normalized or key in seen:
            return
        seen.add(key)
        result.append(phrase)

    for action in actions:
        add(action.action_id, "label", action.label)
        if action.description:
            add(action.action_id, "description", action.description)
    for action_id, aliases in _REVIEWED_ALIASES[lesson_id].items():
        for alias in aliases:
            add(action_id, "reviewed_alias", alias)
    return tuple(result)


def _exact_candidates(
    normalized_input: str,
    phrases: Iterable[_Phrase],
    available_ids: set[str],
) -> tuple[ActionFitCandidateV1, ...]:
    by_action: dict[str, _Phrase] = {}
    for phrase in phrases:
        if phrase.normalized != normalized_input:
            continue
        current = by_action.get(phrase.action_id)
        if current is None or _basis_priority(phrase.basis) > _basis_priority(
            current.basis
        ):
            by_action[phrase.action_id] = phrase
    candidates = [
        ActionFitCandidateV1(
            action_id=action_id,
            score=1.0,
            available=action_id in available_ids,
            match_basis=phrase.basis,
            matched_phrase=phrase.raw,
        )
        for action_id, phrase in by_action.items()
    ]
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.action_id))[:3])


def _semantic_candidates(
    normalized_input: str,
    phrases: Iterable[_Phrase],
    available_ids: set[str],
) -> tuple[ActionFitCandidateV1, ...]:
    by_action: dict[str, ActionFitCandidateV1] = {}
    for phrase in phrases:
        score = _similarity(normalized_input, phrase.normalized)
        candidate = ActionFitCandidateV1(
            action_id=phrase.action_id,
            score=score,
            available=phrase.action_id in available_ids,
            match_basis=phrase.basis,
            matched_phrase=phrase.raw,
        )
        current = by_action.get(phrase.action_id)
        if current is None or (
            candidate.score,
            _basis_priority(candidate.match_basis),
        ) > (
            current.score,
            _basis_priority(current.match_basis),
        ):
            by_action[phrase.action_id] = candidate
    ranked = sorted(by_action.values(), key=lambda item: (-item.score, item.action_id))
    return tuple(item for item in ranked[:3] if item.score >= 0.12)


def _basis_priority(value: MatchBasis) -> int:
    return {"description": 0, "reviewed_alias": 1, "label": 2}[value]


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_bigrams = _ngrams(left, 2)
    right_bigrams = _ngrams(right, 2)
    bigram_dice = _counter_dice(left_bigrams, right_bigrams)
    sequence = SequenceMatcher(a=left, b=right, autojunk=False).ratio()
    char_jaccard = _jaccard(set(left), set(right))
    length_ratio = min(len(left), len(right)) / max(len(left), len(right))
    containment = 0.0
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) >= 3 and shorter in longer:
        containment = 0.82 + 0.16 * length_ratio
    score = max(
        containment,
        0.50 * bigram_dice
        + 0.28 * sequence
        + 0.16 * char_jaccard
        + 0.06 * length_ratio,
    )
    return round(min(1.0, score), 6)


def _ngrams(value: str, size: int) -> Counter[str]:
    if len(value) < size:
        return Counter({value: 1}) if value else Counter()
    return Counter(
        value[index : index + size] for index in range(len(value) - size + 1)
    )


def _counter_dice(left: Counter[str], right: Counter[str]) -> float:
    total = sum(left.values()) + sum(right.values())
    if not total:
        return 0.0
    overlap = sum((left & right).values())
    return 2 * overlap / total


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


# Reviewed classroom paraphrases.  These are intent aliases, not historical claims.
# The first entries repeat the published label/source aliases so unavailable actions
# remain detectable even when the server exposes only the current node's choices.
_REVIEWED_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "L101": {
        "survey-waterways": (
            "踏勘支流与低地",
            "踏勘",
            "勘察水道",
            "先看地形",
            "先派人摸清支流和低地的水势",
            "记录河道地形和水流方向",
            "调查哪里适合分洪",
        ),
        "dredge-diversion": (
            "依地形疏浚分流",
            "疏导",
            "开渠分洪",
            "疏浚",
            "顺着地势开渠把洪水分出去",
            "清理河道疏通水流",
            "依势导水泄洪",
        ),
        "reinforce-settlements": (
            "加固聚落关键岸段",
            "加固河岸",
            "护住聚落",
            "修临时堤",
            "先保护住房粮仓和饮水点",
            "加固关键河岸争取时间",
        ),
        "rotate-labor": (
            "轮换劳作并设安全线",
            "轮换",
            "让劳作者休整",
            "安全施工",
            "让各聚落轮流施工和耕作",
            "避免连续强征人力",
        ),
        "share-map-plan": (
            "公开水图并共同议事",
            "公开方案",
            "共同议事",
            "分享水图",
            "把地形和粮食消耗公开讨论",
            "邀请各聚落一起修改治水方案",
        ),
        "release-emergency-grain": (
            "开仓赈济受灾家庭",
            "赈济",
            "开仓",
            "发放口粮",
            "先给受灾家庭和劳作者粮食",
            "开粮仓维持迁居家庭生活",
        ),
        "force-emergency-dikes": (
            "强征人力抢筑长堤",
            "强征筑堤",
            "抢筑长堤",
            "集中人力",
            "不等勘察直接集中人力筑堤",
            "强行动员所有人抢修防线",
        ),
    },
    "L103": {
        "consult-interests": (
            "先听取各方陈述",
            "听取意见",
            "协商",
            "让贵族农户士卒和吏员分别发言",
            "先把各方利益和困难问清楚",
            "听各方意见",
        ),
        "announce-reform-goal": (
            "公布富国强兵目标",
            "公布目标",
            "宣布变法",
            "先向全国说明富国强兵方向",
            "公开改革的总体目标",
        ),
        "silence-opposition": (
            "压下反对立即推进",
            "强推",
            "压下反对",
            "不再争论直接推进变法",
            "依靠国君支持压住反对者",
        ),
        "publish-clear-rules": (
            "公开法令与申诉记录",
            "公开法令",
            "明法",
            "写清责任尺度和执行步骤",
            "让法令可以查询解释和申诉复核",
            "把责任尺度和执行步骤写清楚允许申诉复核",
        ),
        "stage-symbolic-promise": (
            "以公开赏格建立承诺",
            "徙木立信",
            "兑现赏格",
            "公开兑现一次悬赏来建立信用",
            "用徙木赏金证明新令会执行",
        ),
        "impose-collective-liability": (
            "先推什伍连带追责",
            "连坐",
            "什伍追责",
            "用邻里相互监督压实责任",
            "先建立连带处罚制度",
        ),
        "balance-farming-and-merit": (
            "并列耕作保障与军功通道",
            "平衡耕战",
            "耕战并举",
            "兼顾农业生产和军功奖励",
            "既保障耕作又开放军功晋升",
        ),
        "prioritize-military-merit": (
            "优先军功爵与战备",
            "军功爵",
            "优先战备",
            "把爵位和奖励主要给立军功者",
            "先加强军功激励和战争准备",
        ),
        "reward-farming-first": (
            "先稳农业与家庭生产",
            "奖励耕织",
            "先稳农业",
            "优先保证耕作时间和粮食产出",
            "先奖励农业再放慢军事动员",
        ),
        "standardize-measures": (
            "先统一计量与账册",
            "统一度量衡",
            "商鞅方升",
            "把各地度量标准和账册统一起来",
            "用标准量器统一粮食交换和征收记录",
        ),
        "build-county-offices": (
            "建设县廷并培训吏员",
            "推行县制",
            "建设县廷",
            "在地方建立县级机构并训练官吏",
            "让命令通过县廷落实和复核",
        ),
        "rapid-requisition-network": (
            "先建征发与追责网络",
            "严密征发",
            "基层追责",
            "用户籍编组快速集中粮食和人力",
            "建立严密的基层征收问责网络",
        ),
        "defer-local-implementation": (
            "暂留旧办法等待自愿采用",
            "暂缓县政",
            "地方自愿",
            "先不统一让各地自行决定",
            "保留旧办法等待地方自愿跟进",
        ),
        "phase-and-audit": (
            "分阶段执行并公开复核",
            "分阶段",
            "审计修订",
            "先在少数地区试行记录问题再调整",
            "边执行边公开检查负担和错误",
        ),
        "enforce-with-severe-penalties": (
            "以严罚完成全面执行",
            "严刑执行",
            "全面强推",
            "用严厉处罚迅速全面落实",
            "依靠连带责任压缩执行时间",
        ),
        "correct-burdens": (
            "纠正过重征发与含混条款",
            "减轻负担",
            "纠错",
            "减少过量征发并解释含混规则",
            "保护基本耕作时间纠正执行负担",
        ),
        "suspend-enforcement": (
            "暂停执行等待局势自行稳定",
            "暂停变法",
            "继续等待",
            "停止推进等待反对自行平息",
            "暂时中止改革执行",
        ),
        "consolidate-balanced-reform": (
            "封存规则并保留复核",
            "平衡收束",
            "封存改革",
            "把标准县政激励和减负写成长期方案",
            "保留复核机制完成平衡改革",
        ),
        "drive-mobilization": (
            "以战备成果继续加速",
            "继续强推",
            "加速动员",
            "把最后资源继续投入征发和军功",
            "依靠战备成果进一步提速",
        ),
        "negotiate-limited-reform": (
            "保留核心措施并继续协商",
            "折中收束",
            "有限改革",
            "承认能力有限只保留可兑现措施",
            "保住核心改革并留待以后复核",
        ),
        "abandon-reform": (
            "撤回方案恢复旧序",
            "放弃变法",
            "恢复旧制",
            "取消改革回到原来的制度",
            "因阻力太大撤回尚未稳固的措施",
        ),
    },
}


__all__ = [
    "ACTION_FIT_POLICY_VERSION",
    "ActionFitCandidateV1",
    "LocalActionFitResultV1",
    "LocalActionFitterV1",
    "fit_local_action",
]
