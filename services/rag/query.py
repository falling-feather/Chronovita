from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal
import unicodedata

from services.content.workflow import PublishedLessonResources
from services.contracts.v1 import PersonV1


QUERY_PLANNER_VERSION = "chronovita-rag-query/v1"

QueryIntent = Literal[
    "identity",
    "overview",
    "evidence_boundary",
    "causality",
    "comparison",
    "detail",
]


@dataclass(frozen=True)
class RagQueryPlan:
    original_question: str
    intent: QueryIntent
    retrieval_queries: tuple[str, ...]
    blocked_reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.blocked_reason is not None


_INSTRUCTION_OVERRIDE = re.compile(
    r"(?:忽略|绕过|覆盖|取消|忘记|泄露).{0,16}"
    r"(?:系统|规则|提示|指令|证据|边界|身份)|"
    r"(?:伪造|编造|虚构).{0,10}(?:引用|来源|史料)|"
    r"(?:system\s*prompt|developer\s*message|ignore\s+previous)",
    re.IGNORECASE,
)
_CLEAR_ANACHRONISM = re.compile(
    r"手机|微信|互联网|电脑|电子邮件|短视频|直播|飞机|卫星|电话|电报"
)
_IDENTITY = re.compile(
    r"^(?:请)?(?:先)?(?:介绍(?:一下)?(?:你|您|自己)|"
    r"(?:你|您)(?:到底|究竟)?(?:是|叫)?谁|"
    r"(?:你|您)(?:叫)?什么(?:名字)?|"
    r"(?:你|您)的身份(?:是)?什么|"
    r"我在和谁(?:说话|对话))(?:呢|呀|啊)?[?？。！!]*$"
)
_OVERVIEW = re.compile(
    r"这(?:一|节|门)?课.{0,8}(?:讲|说|学|学会)(?:了)?(?:什么|啥)|"
    r"(?:概括|介绍|总结).{0,8}(?:本课|这课|治水|变法)|"
    r"(?:变法|改革).{0,6}(?:改|做)(?:了)?(?:些)?什么|"
    r"商鞅.{0,6}改(?:了)?(?:些)?(?:什么|啥)|"
    r"(?:大禹|禹).{0,5}(?:怎么|如何)(?:治水|治理洪水)"
)
_BOUNDARY = re.compile(
    r"真的|真有|真假|靠谱吗|可信|可靠|证明|证据|史料|考古|"
    r"亲笔|原话|现场|铭文|年代|晚于|早于|可能|直接|是不是|等不等于|能不能"
)
_COMPARISON = re.compile(r"区别|一样|相同|相比|等同|等于|是不是.*(?:就是|一种)")
_CAUSALITY = re.compile(r"为什么|为何|原因|怎么会|如何导致|怎样影响|有什么影响")


# These are search aliases, not historical claims. Every expansion points only to
# canonical terms already present in the exact published course/evidence bundle.
_LESSON_ALIASES: dict[tuple[str, str], tuple[tuple[tuple[str, ...], str], ...]] = {
    (
        "C-prequin-state",
        "L101",
    ): (
        (("是不是夏朝", "就是夏朝", "算夏朝", "夏都"), "二里头 夏史 夏都 解释边界"),
        (("挖到禹", "找到禹", "禹的字", "禹名字", "大禹名字"), "禹 铭文 考古边界 人物证据"),
        (("没回家", "不回家", "路过家门", "过门不进", "准确三次"), "三过家门 公共责任"),
        (("真实统计", "统计数字", "关卡数字", "风险数字"), "变量 教学模型 治理模型"),
        (("堵水", "堵住洪水", "只堵", "一直堵", "开沟", "开沟排水"), "疏导 水势 治水工程"),
        (("一个人", "靠他", "全靠禹", "禹自己"), "协作 劳动 公共动员"),
        (("普通劳作者", "劳作者", "大家一起"), "协作 劳动 公共动员"),
        (("施工图", "工程图", "古地图", "那张地图", "禹贡", "九州"), "禹贡 九州 记忆地图 空间边界"),
        (("宫殿", "道路", "作坊", "青铜器"), "二里头 早期国家 专业分工"),
        (("史记", "夏本纪"), "史记 夏本纪 传世文献 成书年代"),
        (("大水", "洪水", "水灾", "洪灾"), "洪水传说 人物证据 王朝证据"),
    ),
    (
        "C-prequin-state",
        "L103",
    ): (
        (("搬木头", "立木", "木头", "木头那个故事", "木头的故事"), "徙木立信 制度信用"),
        (("后来又刻", "后刻", "两次铭文"), "方升 两次铭文 秦始皇诏 制度延续"),
        (("量杯", "量器", "容量", "方升"), "商鞅方升 度量衡 标准量器"),
        (("竹简", "秦简"), "睡虎地秦简 年代边界 秦律"),
        (("他死了", "死了以后", "死后", "人亡政息"), "商鞅之死 制度延续"),
        (("老百姓", "普通人", "农民", "百姓"), "农耕家庭 赋役 制度代价"),
        (("当兵", "打仗升官", "靠打仗", "军功"), "军功爵 身份机会 战争代价"),
        (("秦变强", "秦国变强", "强大起来", "统一六国"), "富国强兵 多因解释"),
        (("法律太严", "太狠", "连坐", "互相告发"), "什伍 连带责任 制度代价"),
        (("现代法治", "人人平等", "现代法律"), "概念边界 法治 明法"),
        (("改了什么", "改了啥", "到底改", "做了什么", "改革内容"), "商鞅变法 军功爵 奖励耕战 县制"),
        (("管到地方", "管地方", "县到底"), "县制 地方治理 县政"),
        (("分阶段", "一次完成", "一次改完"), "改革年代 公元前356年 公元前350年"),
    ),
}


def plan_rag_query(
    resources: PublishedLessonResources,
    question: str,
    *,
    person: PersonV1 | None = None,
) -> RagQueryPlan:
    original = question.strip()
    normalized = _normalize(original)
    blocked_reason = _blocked_reason(normalized)
    intent = _intent_for(normalized, person=person)
    if blocked_reason is not None:
        return RagQueryPlan(
            original_question=original,
            intent=intent,
            retrieval_queries=(original,),
            blocked_reason=blocked_reason,
        )

    queries = [original]
    if intent == "identity" and person is not None:
        queries.append(
            " ".join(
                value
                for value in (person.name, person.role, person.summary)
                if value
            )
        )
    elif person is not None:
        resolved = _resolve_person_reference(original, person.name)
        if resolved != original:
            queries.append(resolved)

    alias_terms = _matching_alias_terms(resources, normalized)
    explicit_terms = _published_terms_in_question(resources, normalized)
    if alias_terms:
        queries.append(" ".join(alias_terms))
        if intent != "overview":
            queries.append(f"{original}；检索要点：{' '.join(alias_terms)}")

    if intent == "overview" and not alias_terms:
        overview_terms = [
            resources.course_package.title,
            *(item.word for item in resources.course_package.keywords[:6]),
        ]
        queries.append("课程概览 " + " ".join(overview_terms))
    elif intent == "evidence_boundary" and (alias_terms or explicit_terms):
        queries.append(
            f"{original}；证据边界 年代 直接证明 "
            + " ".join((*explicit_terms, *alias_terms))
        )

    return RagQueryPlan(
        original_question=original,
        intent=intent,
        retrieval_queries=_deduplicate_queries(queries),
    )


def _blocked_reason(normalized: str) -> str | None:
    if _INSTRUCTION_OVERRIDE.search(normalized):
        return "instruction_override"
    if _CLEAR_ANACHRONISM.search(normalized):
        return "clear_anachronism"
    return None


def _intent_for(normalized: str, *, person: PersonV1 | None) -> QueryIntent:
    if person is not None and _IDENTITY.fullmatch(normalized):
        return "identity"
    if _OVERVIEW.search(normalized):
        return "overview"
    if _BOUNDARY.search(normalized):
        return "evidence_boundary"
    if _COMPARISON.search(normalized):
        return "comparison"
    if _CAUSALITY.search(normalized):
        return "causality"
    return "detail"


def _matching_alias_terms(
    resources: PublishedLessonResources,
    normalized: str,
) -> tuple[str, ...]:
    for triggers, expansion in _LESSON_ALIASES.get(
        (resources.course_id, resources.lesson_id),
        (),
    ):
        if any(_normalize(trigger) in normalized for trigger in triggers):
            # Rules are ordered from the most specific event/artifact wording to
            # broader audience wording. One precise rewrite avoids query drift
            # when a sentence mentions both an event and a generic group.
            return tuple(dict.fromkeys(expansion.split()))
    return ()


def _published_terms_in_question(
    resources: PublishedLessonResources,
    normalized: str,
) -> tuple[str, ...]:
    candidates = (
        *(item.word for item in resources.course_package.keywords),
        *(item.name for item in resources.course_package.people),
        *(
            keyword
            for passage in resources.evidence_corpus.passages
            for keyword in passage.keywords
        ),
    )
    matched = [value for value in candidates if _normalize(value) in normalized]
    return tuple(dict.fromkeys(matched))


def _resolve_person_reference(question: str, person_name: str) -> str:
    resolved = question
    replacements = (
        ("我的", f"{person_name}的"),
        ("你的", f"{person_name}的"),
        ("您的", f"{person_name}的"),
        ("你当时", f"{person_name}当时"),
        ("您当时", f"{person_name}当时"),
        ("你为什么", f"{person_name}为什么"),
        ("您为什么", f"{person_name}为什么"),
        ("你怎么", f"{person_name}怎么"),
        ("您怎么", f"{person_name}怎么"),
    )
    for source, target in replacements:
        resolved = resolved.replace(source, target)
    return resolved


def _deduplicate_queries(queries: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        value = query.strip()
        key = _normalize(value)
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value[:1200])
        if len(result) >= 4:
            break
    return tuple(result)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


__all__ = [
    "QUERY_PLANNER_VERSION",
    "QueryIntent",
    "RagQueryPlan",
    "plan_rag_query",
]
