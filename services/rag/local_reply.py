from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
from typing import Literal
import unicodedata

from services.content.workflow import PublishedLessonResources
from services.contracts.evidence_v1 import (
    RagAskRequestV1,
    verify_evidence_checksum,
)
from services.contracts.evidence_v2 import (
    EvidenceAnswerSlotV1,
    EvidenceCorpusV2,
)
from services.contracts.v1 import PersonV1

from .query import RagQueryPlan
from .retrieval import RetrievalBatch


LOCAL_REPLY_VERSION = "chronovita-local-reply/v1"

LocalResponseMode = Literal[
    "identity",
    "overview",
    "topic",
    "boundary",
    "unsupported_slot",
]


@dataclass(frozen=True)
class LocalReplyFit:
    """A deterministic expression-state selected before prose is assembled.

    The fit contains no historical claim or answer text.  Callers must build
    every factual sentence from ``batch.passages`` and keep their citations.
    ``api_synthesis_allowed`` is only a state-level permission; it never means
    that an API call is required or that the evidence is sufficient by itself.
    """

    state_id: str
    topic_label: str
    response_mode: LocalResponseMode
    api_synthesis_allowed: bool
    matched_terms: tuple[str, ...]
    answer_slot_supported: bool = True
    reason: str = "matched_published_state"
    slot_ids: tuple[str, ...] = ()
    passage_ids: tuple[str, ...] = ()
    boundary_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _StateRule:
    state_id: str
    topic_label: str
    terms: tuple[str, ...]
    api_synthesis_allowed: bool = True


@dataclass(frozen=True)
class _UnsupportedSlotRule:
    slot_id: str
    topic_label: str
    required_term_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class _GenericUnsupportedSlotRule:
    slot_id: str
    topic_label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class _ApprovedQuestionRelation:
    relation_id: str
    state_ids: frozenset[str]
    intents: frozenset[str]
    predicate: re.Pattern[str]
    api_synthesis_allowed: bool = False


_SUPPORTED_LESSONS = frozenset(
    {
        ("C-prequin-state", "L101"),
        ("C-prequin-state", "L103"),
    }
)

# The deterministic state pack is reviewed against these exact sealed corpora.
# A later evidence release must update this binding deliberately; otherwise old
# answer states could silently be reused with a semantically different corpus.
_SUPPORTED_EVIDENCE_CHECKSUMS: dict[tuple[str, str], str] = {
    (
        "C-prequin-state",
        "L101",
    ): "ae736fd34b31fc99907e0a33b518dd2fd360530af95d2717e3a54832b2c1ff49",
    (
        "C-prequin-state",
        "L103",
    ): "06ab368e3f54051f21e56e4047ab9efb8f447cb81e2ef68620105995db4ce633",
}

# EvidenceCorpusV2 publishes the reviewed reply state together with the
# passages.  These aliases preserve the V1 diagnostic state names for existing
# clients while the new ``slot_ids`` field exposes the actual V2 authority.
_V2_SLOT_STATE_IDS: dict[str, str] = {
    "dayu-slot-erlitou-state": "L101.erlitou-state",
    "dayu-slot-erlitou-xia-boundary": "L101.erlitou-state",
    "dayu-slot-governance-power-cost": "L101.governance",
    "dayu-slot-jishi-flood": "L101.flood-science",
    "dayu-slot-memory-map": "L101.yugong-map",
    "dayu-slot-methods": "L101.governance",
    "dayu-slot-source-layers": "L101.transmitted-memory",
    "shangyang-slot-01-overview": "L103.reform-overview",
    "shangyang-slot-04-moving-wood": "L103.law-credit",
    "shangyang-slot-05-military-merit": "L103.farming-merit",
    "shangyang-slot-06-agriculture-war": "L103.farming-merit",
    "shangyang-slot-07-collective-liability": "L103.collective-cost",
    "shangyang-slot-08-county-administration": "L103.local-administration",
    "shangyang-slot-11-fangsheng": "L103.fangsheng",
    "shangyang-slot-12-sleeping-tiger-slips": "L103.text-layers",
    "shangyang-slot-13-book-of-lord-shang": "L103.text-layers",
    "shangyang-slot-15-evaluation": "L103.state-capacity",
}

_V2_LEGACY_STATE_SLOTS: dict[str, tuple[str, ...]] = {
    "L101.transmitted-memory": ("dayu-slot-source-layers",),
    "L101.yugong-map": ("dayu-slot-memory-map",),
    "L101.flood-science": ("dayu-slot-jishi-flood",),
    "L101.erlitou-state": (
        "dayu-slot-erlitou-state",
        "dayu-slot-erlitou-xia-boundary",
    ),
    "L101.governance": (
        "dayu-slot-governance-power-cost",
        "dayu-slot-methods",
    ),
    "L101.chronology": (
        "dayu-slot-erlitou-xia-boundary",
        "dayu-slot-jishi-flood",
    ),
    "L103.reform-overview": ("shangyang-slot-01-overview",),
    "L103.law-credit": ("shangyang-slot-04-moving-wood",),
    "L103.farming-merit": (
        "shangyang-slot-05-military-merit",
        "shangyang-slot-06-agriculture-war",
    ),
    "L103.local-administration": (
        "shangyang-slot-08-county-administration",
    ),
    "L103.collective-cost": (
        "shangyang-slot-07-collective-liability",
    ),
    "L103.fangsheng": ("shangyang-slot-11-fangsheng",),
    "L103.text-layers": (
        "shangyang-slot-12-sleeping-tiger-slips",
        "shangyang-slot-13-book-of-lord-shang",
    ),
    "L103.state-capacity": ("shangyang-slot-15-evaluation",),
}

_STATE_RULES: dict[tuple[str, str], tuple[_StateRule, ...]] = {
    ("C-prequin-state", "L101"): (
        _StateRule(
            "L101.transmitted-memory",
            "传世记忆与禹的叙事",
            (
                "大禹",
                "禹",
                "鲧",
                "益",
                "史记",
                "夏本纪",
                "孟子",
                "三过家门",
                "传世文献",
                "后世记忆",
            ),
        ),
        _StateRule(
            "L101.yugong-map",
            "《禹贡》与空间秩序",
            ("禹贡", "九州", "贡赋", "施工图", "记忆地图", "山川"),
        ),
        _StateRule(
            "L101.flood-science",
            "洪水研究与推论边界",
            (
                "积石峡",
                "堰塞湖",
                "溃决洪水",
                "洪水研究",
                "自然科学",
                "地质",
                "大洪水",
                "水灾",
            ),
        ),
        _StateRule(
            "L101.erlitou-state",
            "二里头与早期国家",
            (
                "二里头",
                "夏史",
                "夏都",
                "早期国家",
                "宫城",
                "宫殿",
                "道路网",
                "功能分区",
                "作坊",
                "青铜礼器",
                "专业分工",
                "王权",
            ),
        ),
        _StateRule(
            "L101.governance",
            "治水、协作与治理代价",
            (
                "治水",
                "疏导",
                "疏河",
                "堵水",
                "壅堵",
                "协作",
                "劳动",
                "劳作者",
                "公共动员",
                "公共责任",
                "治理权威",
                "治理代价",
            ),
        ),
        _StateRule(
            "L101.chronology",
            "年代框架与证据强度",
            ("年代", "公元前21世纪", "距今3800", "同时代", "铭文"),
        ),
    ),
    ("C-prequin-state", "L103"): (
        _StateRule(
            "L103.reform-overview",
            "变法内容与改革次序",
            (
                "商鞅变法",
                "变法",
                "改革",
                "公元前356年",
                "公元前350年",
                "两阶段",
            ),
        ),
        _StateRule(
            "L103.law-credit",
            "法令公开与制度信用",
            ("徙木立信", "徙木", "立木", "明法", "法令公开", "制度信用"),
        ),
        _StateRule(
            "L103.farming-merit",
            "奖励耕战、军功与家庭负担",
            (
                "奖励耕战",
                "耕战",
                "军功爵",
                "军功",
                "士卒",
                "农耕家庭",
                "农业",
                "战争代价",
                "赋役",
            ),
        ),
        _StateRule(
            "L103.local-administration",
            "县制与地方执行",
            ("县制", "县政", "县廷", "地方治理", "地方官吏", "官吏"),
        ),
        _StateRule(
            "L103.collective-cost",
            "什伍、连带责任与制度代价",
            (
                "什伍",
                "连坐",
                "连带责任",
                "相互追责",
                "告发",
                "严刑",
                "制度代价",
                "社会压力",
            ),
        ),
        _StateRule(
            "L103.land-boundary",
            "田制调整的概念边界",
            ("开阡陌", "阡陌", "土地制度", "私有产权"),
        ),
        _StateRule(
            "L103.fangsheng",
            "商鞅方升与统一尺度",
            (
                "商鞅方升",
                "方升",
                "度量衡",
                "标准量器",
                "量器",
                "容量",
                "两次铭文",
                "秦始皇诏",
            ),
        ),
        _StateRule(
            "L103.text-layers",
            "文献、秦简与年代边界",
            (
                "史记",
                "商君列传",
                "商君书",
                "韩非子",
                "睡虎地秦简",
                "秦简",
                "秦律",
                "亲笔",
                "文本分层",
                "年代边界",
            ),
        ),
        _StateRule(
            "L103.state-capacity",
            "富国强兵与多因解释",
            (
                "富国强兵",
                "秦国变强",
                "秦变强",
                "统一六国",
                "国家能力",
                "多因",
                "强盛",
                "制度延续",
                "商鞅之死",
                "处死",
            ),
        ),
        _StateRule(
            "L103.modern-law-boundary",
            "战国法令与现代法治边界",
            ("现代法治", "现代法律", "人人平等", "权利保障", "宪政"),
        ),
    ),
}

_COMPOSITE_STATES = {
    ("C-prequin-state", "L101"): (
        "L101.cross-evidence",
        "传说、文献、科学与考古的多层证据",
    ),
    ("C-prequin-state", "L103"): (
        "L103.cross-evidence",
        "制度措施、承受者与材料边界的综合",
    ),
}

# These aliases are deliberately small and map wording present in the
# student's *original* question to one reviewed state.  They are not copied
# from the expanded retrieval query: doing that would let a rewrite manufacture
# its own state match.  Broad audience words such as “老百姓” are intentionally
# absent because they do not identify an answerable course question by
# themselves.
_STATE_ALIASES: dict[
    tuple[str, str], tuple[tuple[str, tuple[str, ...]], ...]
] = {
    ("C-prequin-state", "L101"): (
        ("L101.transmitted-memory", ("没回家", "不回家", "路过家门", "过门不进")),
        ("L101.yugong-map", ("工程图", "古地图")),
        ("L101.governance", ("堵住洪水", "开沟排水", "全靠禹", "禹自己")),
        ("L101.chronology", ("大禹名字", "禹的名字", "挖到大禹名字")),
    ),
    ("C-prequin-state", "L103"): (
        (
            "L103.law-credit",
            (
                "搬木头",
                "搬根木头",
                "搬一根木头",
                "木头那个故事",
                "木头的故事",
            ),
        ),
        ("L103.fangsheng", ("量杯", "后来又刻", "后刻")),
        ("L103.text-layers", ("竹简",)),
        ("L103.farming-merit", ("打仗升官", "靠打仗")),
        ("L103.collective-cost", ("法律太严", "互相告发")),
        ("L103.local-administration", ("管到地方", "管地方")),
        ("L103.reform-overview", ("一次改完", "分阶段")),
    ),
}

_UNSUPPORTED_SLOT_RULES: dict[
    tuple[str, str], tuple[_UnsupportedSlotRule, ...]
] = {
    ("C-prequin-state", "L101"): (
        _UnsupportedSlotRule(
            "erlitou-builder-identity",
            "二里头营建者身份",
            (
                ("二里头",),
                ("宫殿", "宫城", "道路", "道路网", "作坊"),
            ),
        ),
    ),
    ("C-prequin-state", "L103"): (
        _UnsupportedSlotRule(
            "fangsheng-maker-identity",
            "商鞅方升制作者身份",
            (("商鞅方升", "方升"),),
        ),
    ),
}

_CREATOR_QUESTION = re.compile(
    r"(?:谁|何人|哪位.{0,3}(?:人|工匠|匠人)?|设计者|建造者|制造者|铸造者)"
    r".{0,12}(?:设计|建造|修建|营建|制造|铸造|铸的|制作|规划|建的)|"
    r"(?:设计|建造|修建|营建|制造|铸造|制作|规划)(?:者)?"
    r".{0,8}(?:是谁|谁|何人|哪位.{0,3}(?:人|工匠|匠人)?)|"
    r"(?:出自|来自|由).{0,6}(?:谁|何人|哪位|哪个).{0,4}(?:工匠|匠人|人)"
)
_GENERIC_UNSUPPORTED_SLOT_RULES = (
    _GenericUnsupportedSlotRule(
        "unpublished-area-or-size",
        "课程材料未发布的面积或尺寸",
        re.compile(
            r"面积|占地|多少(?:平方米|平方公里|平方|亩|公顷)|"
            r"(?:长|宽|高)(?:多少|几(?:米|厘米))"
        ),
    ),
    _GenericUnsupportedSlotRule(
        "unpublished-price-or-market-value",
        "课程材料未发布的价格或市场价值",
        re.compile(
            r"价格|价钱|售价|市场价|拍卖价|值多少钱|多少钱|"
            r"(?:市场|经济|收藏|拍卖)价值(?:是多少|多少|几何|多少钱)?|"
            r"价值(?:是多少|多少|几何|多少钱)"
        ),
    ),
    _GenericUnsupportedSlotRule(
        "unpublished-colour",
        "课程材料未发布的颜色细节",
        re.compile(r"颜色|什么色|何种色|哪种色"),
    ),
    _GenericUnsupportedSlotRule(
        "unpublished-shape",
        "课程材料未发布的形状细节",
        re.compile(r"形状|什么样子|长什么样|外形|造型|圆形|方形"),
    ),
    _GenericUnsupportedSlotRule(
        "unpublished-design-rationale",
        "课程材料未发布的设计思路",
        re.compile(r"设计思路|设计理念|为什么这样设计|为何这样设计|怎么设计|如何设计"),
    ),
)
_SYNTHESIS_LANGUAGE = re.compile(
    r"比较|综合|分别|以及|关系|同时|一方面|另一方面|权衡|评价|分析"
)
_FALSE_PREMISE_CORRECTION = re.compile(
    r"就是|对吗|是不是|并非|并不是|不能直接|能不能直接"
)
_HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_ASCII_WORD = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")

# Question grammar is allowed, but it is not evidence.  Historical predicates,
# facets and purposes still have to be present in the sealed corpus, a reviewed
# state rule, or a reviewed colloquial alias.  Listing question grammar here is
# a positive language contract rather than a catalogue of forbidden topics.
_APPROVED_QUESTION_LANGUAGE = (
    "是什么",
    "有哪些",
    "哪些",
    "什么意思",
    "为什么",
    "为何",
    "怎样",
    "怎么",
    "如何",
    "是否",
    "能否",
    "能不能",
    "可不可以",
    "说明什么",
    "证明什么",
    "能说明",
    "能证明",
    "直接证明",
    "间接支持",
    "证据边界",
    "有什么关系",
    "有什么影响",
    "有什么作用",
    "有什么代价",
    "什么原因",
    "比较",
    "对比",
    "综合分析",
    "分别分析",
    "评价",
    "理解",
    "看待",
    "解释",
    "介绍",
    "概括",
    "总结",
    "分别",
    "各自",
    "相同",
    "不同",
    "异同",
    "一方面",
    "另一方面",
    "导致",
    "增强",
    "削弱",
    "改变",
    "形成",
    "建立",
    "延续",
    "消失",
    "支持",
    "反驳",
    "推出",
    "等于",
    "属于",
    "保存",
    "反映",
    "体现",
    "意味着",
    "带来",
    "帮助",
    "适合",
    "承担",
    "付出",
    "做了什么",
    "改了什么",
    "主要内容",
    "先后次序",
    "历史过程",
    "制度措施",
    "治理路径",
    "结果",
    "后果",
    "机会",
    "风险",
    "可信",
    "可靠",
    "真的",
    "是不是",
    "对不对",
)
_STATE_APPROVED_QUESTION_FACETS: dict[str, tuple[str, ...]] = {
    "L101.flood-science": ("一定存在", "已经证明"),
    "L101.transmitted-memory": ("大禹名字", "禹的名字"),
    "L101.chronology": ("写着名字", "名字的铭文", "大禹名字"),
    "L101.erlitou-state": ("二里头遗址", "井字形道路", "井字形"),
    "L101.governance": ("两种治水思路", "治理思路"),
    "L103.law-credit": ("老百姓信法律", "相信法令", "信法律"),
    "L103.farming-merit": ("增加负担", "增加代价"),
    "L103.collective-cost": ("增加压力", "增加代价"),
    "L103.text-layers": ("材料性质", "年代与性质"),
    "L103.fangsheng": ("材料性质", "年代与性质"),
    "L103.state-capacity": (
        "归功于",
        "不能只归功于",
        "完全归功于",
        "一个人的功劳",
        "立刻消失",
    ),
}

_SINGLE_STATE_RELATIONS = (
    _ApprovedQuestionRelation("L101-memory", frozenset({"L101.transmitted-memory"}), frozenset({"detail", "evidence_boundary", "causality"}), re.compile(r"记忆|保存|传世|成书|现场|证明|能说明|真假|三过家门")),
    _ApprovedQuestionRelation("L101-map", frozenset({"L101.yugong-map"}), frozenset({"detail", "evidence_boundary", "comparison", "causality"}), re.compile(r"施工图|工程图|记忆地图|空间|九州|贡赋|山川|能说明|证明")),
    _ApprovedQuestionRelation("L101-flood", frozenset({"L101.flood-science"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"证明|说明|推论|边界|洪水|灾害|自然事件|关系")),
    _ApprovedQuestionRelation("L101-state", frozenset({"L101.erlitou-state"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"说明|证明|体现|关系|早期国家|功能分区|组织|劳动|专业分工|王权")),
    _ApprovedQuestionRelation("L101-governance", frozenset({"L101.governance"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"治水|疏导|堵水|壅堵|协作|劳动|动员|责任|权威|代价|影响|比较"), True),
    _ApprovedQuestionRelation("L101-chronology", frozenset({"L101.chronology"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"年代|同时代|铭文|名字|早于|晚于|距今")),
    _ApprovedQuestionRelation("L103-reform", frozenset({"L103.reform-overview"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"内容|次序|阶段|改了|改革|两阶段|一次完成")),
    _ApprovedQuestionRelation("L103-credit", frozenset({"L103.law-credit"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"制度信用|信法律|相信法令|法令公开|徙木|搬.{0,2}木头|明法")),
    _ApprovedQuestionRelation("L103-farming", frozenset({"L103.farming-merit"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"机会|代价|赋役|负担|影响|富国强兵|农业|战争|士卒|农耕家庭")),
    _ApprovedQuestionRelation("L103-local", frozenset({"L103.local-administration"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"地方|县政|治理|执行|官吏|增强|国家能力")),
    _ApprovedQuestionRelation("L103-collective", frozenset({"L103.collective-cost"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"代价|压力|责任|连坐|告发|严刑|影响")),
    _ApprovedQuestionRelation("L103-land", frozenset({"L103.land-boundary"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"土地|田制|阡陌|产权|概念|边界")),
    _ApprovedQuestionRelation("L103-measure", frozenset({"L103.fangsheng"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"度量衡|量器|容量|铭文|尺度|制度延续|说明|证明|关系")),
    _ApprovedQuestionRelation("L103-text", frozenset({"L103.text-layers"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"年代|性质|亲笔|法令|秦律|文本|材料|说明|证明|边界")),
    _ApprovedQuestionRelation("L103-capacity", frozenset({"L103.state-capacity"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"变强|强盛|统一六国|国家能力|多因|归功|制度延续|消失|处死")),
    _ApprovedQuestionRelation("L103-modern-law", frozenset({"L103.modern-law-boundary"}), frozenset({"detail", "evidence_boundary", "causality", "comparison"}), re.compile(r"现代法治|现代法律|人人平等|权利|宪政|边界|等于")),
)

_PEER_STATE_RELATIONS = (
    _ApprovedQuestionRelation(
        "L101-cross-evidence",
        frozenset({"L101.transmitted-memory", "L101.yugong-map", "L101.flood-science", "L101.erlitou-state", "L101.chronology"}),
        frozenset({"detail", "evidence_boundary", "causality", "comparison"}),
        re.compile(r"分别能说明|各自.{0,6}(?:说明|证明)|证据边界|不能.{0,12}(?:推出|证明|施工图)|夏代留下.{0,8}施工图|就是.{0,8}施工图|写着.{0,8}名字.{0,8}铭文|同时代.{0,8}铭文|考古.{0,8}(?:挖到|发现).{0,8}(?:大禹|禹).{0,4}名字|历史形成.{0,8}关系|材料.{0,8}(?:关系|边界)"),
        True,
    ),
    _ApprovedQuestionRelation(
        "L101-evidence-and-governance",
        frozenset({"L101.transmitted-memory", "L101.yugong-map", "L101.flood-science", "L101.erlitou-state", "L101.governance", "L101.chronology"}),
        frozenset({"detail", "evidence_boundary", "causality", "comparison"}),
        re.compile(r"证明.{0,12}治水现场|早期国家.{0,12}组织劳动|洪水记忆.{0,20}早期国家|治水传说.{0,20}早期国家|不能从洪水.{0,12}推出夏朝|夏代留下.{0,8}施工图|就是.{0,8}施工图|形成.{0,8}关系"),
        True,
    ),
    _ApprovedQuestionRelation(
        "L103-policy-effects",
        frozenset({"L103.reform-overview", "L103.law-credit", "L103.farming-merit", "L103.local-administration", "L103.collective-cost", "L103.state-capacity"}),
        frozenset({"detail", "evidence_boundary", "causality", "comparison"}),
        re.compile(r"增强.{0,10}(?:秦国|国家能力|地方治理)|富国强兵|制度代价|普通人.{0,10}(?:承担|代价)|农耕家庭.{0,10}(?:赋役|代价|负担)|措施.{0,8}(?:影响|作用)|分别怎样增强|改革制度.{0,8}消失|人亡政息|制度延续"),
        True,
    ),
    _ApprovedQuestionRelation(
        "L103-evidence-materials",
        frozenset({"L103.fangsheng", "L103.text-layers"}),
        frozenset({"detail", "evidence_boundary", "causality", "comparison"}),
        re.compile(r"年代与性质|各自.{0,8}(?:说明|证明)|分别能说明|材料.{0,8}(?:性质|边界)|制度变化"),
        True,
    ),
    _ApprovedQuestionRelation(
        "L103-reviewed-change-comparison",
        frozenset({"L103.fangsheng", "L103.farming-merit", "L103.local-administration"}),
        frozenset({"detail", "causality", "comparison"}),
        re.compile(r"分别怎样改变秦国|分别.{0,8}改变秦国"),
        True,
    ),
)
_QUESTION_FUNCTION_CHARS = frozenset(
    "的了呢吗啊呀吧和与及或是在有把被从到对中里上下前后为于这那个其"
    "请问说讲谈能可会就也又并而更较让使将给我你他她它们当做用各自"
)


def detect_unsupported_answer_slot(
    course_id: str,
    lesson_id: str,
    question: str,
) -> str | None:
    """Return an unpublished answer-slot id, or ``None`` when none matches."""

    match = _unsupported_slot_match(course_id, lesson_id, question)
    return match[0].slot_id if match is not None else None


def fit_local_reply(
    resources: PublishedLessonResources,
    request: RagAskRequestV1,
    person: PersonV1 | None,
    query_plan: RagQueryPlan,
    batch: RetrievalBatch,
) -> LocalReplyFit | None:
    """Fit one of the two flagship lessons to a bounded local reply state.

    Unknown lessons and inconsistent resource/request identities fail closed.
    A returned fit is an expression frame, never a source of historical facts.
    """

    lesson_key = (resources.course_id, resources.lesson_id)
    if (
        lesson_key not in _SUPPORTED_LESSONS
        or request.course_id != resources.course_id
        or request.lesson_id != resources.lesson_id
    ):
        return None

    corpus = resources.evidence_corpus
    if isinstance(corpus, EvidenceCorpusV2):
        if (
            not verify_evidence_checksum(corpus)
            or corpus.supersedes_checksum
            != _SUPPORTED_EVIDENCE_CHECKSUMS.get(lesson_key)
        ):
            return None
        return _fit_v2_local_reply(
            resources,
            request,
            person,
            query_plan,
            batch,
            corpus,
        )
    if corpus.checksum != _SUPPORTED_EVIDENCE_CHECKSUMS.get(lesson_key):
        return None

    slot_match = _unsupported_slot_match(
        resources.course_id,
        resources.lesson_id,
        query_plan.original_question,
    )
    if slot_match is not None:
        rule, matched_terms = slot_match
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.{rule.slot_id}",
            topic_label=rule.topic_label,
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=matched_terms,
            answer_slot_supported=False,
            reason="answer_slot_not_published",
        )

    if query_plan.intent == "identity":
        if not _valid_identity_person(resources, request, person):
            return None
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.identity.{person.person_id}",
            topic_label=f"{person.name}的课程身份",
            response_mode="identity",
            api_synthesis_allowed=False,
            matched_terms=(person.name,),
            reason=(
                "published_person_identity"
                if batch.passages
                else "published_identity_without_retrieved_evidence"
            ),
        )

    if query_plan.intent == "overview":
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.overview",
            topic_label=resources.course_package.title,
            response_mode="overview",
            api_synthesis_allowed=False,
            matched_terms=(resources.course_package.title,),
            reason=(
                "published_lesson_overview"
                if batch.supported
                else "overview_requires_retrieved_evidence"
            ),
        )

    # State selection is anchored to the student's original wording. Retrieval
    # rewrites can improve recall, but they cannot grant themselves a reply
    # state or turn a merely related hit into an answerable question.
    normalized = _normalize(query_plan.original_question)
    matches = _matching_states(lesson_key, normalized)
    matches = _merge_alias_matches(
        lesson_key,
        normalized,
        matches,
    )
    if not matches:
        return None

    unsupported_facets = _unsupported_question_facets(
        resources,
        lesson_key,
        query_plan.original_question,
        matched_state_ids=tuple(state.state_id for state, _ in matches),
    )
    if unsupported_facets:
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.unpublished-question-facet",
            topic_label="当前发布未覆盖的问题用途或表述维度",
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=unsupported_facets,
            answer_slot_supported=False,
            reason="question_facet_not_published",
        )

    approved_relation = _approved_question_relation(
        matches,
        query_plan.intent,
        normalized,
    )
    if approved_relation is None:
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.unpublished-question-relation",
            topic_label="当前发布未批准这些课程要素之间的问法关系",
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=_deduplicate(
                term for _, terms in matches for term in terms
            ),
            answer_slot_supported=False,
            reason="question_relation_not_published",
        )

    if len(matches) >= 2 and _SYNTHESIS_LANGUAGE.search(normalized):
        state_id, topic_label = _COMPOSITE_STATES[lesson_key]
        matched_terms = _deduplicate(
            term for _, terms in matches for term in terms
        )
        state_allows_api = approved_relation.api_synthesis_allowed
    else:
        state, matched_terms = matches[0]
        state_id = state.state_id
        topic_label = state.topic_label
        state_allows_api = (
            state.api_synthesis_allowed
            and approved_relation.api_synthesis_allowed
        )

    evidence_available = batch.supported and bool(batch.passages)
    return LocalReplyFit(
        state_id=state_id,
        topic_label=topic_label,
        response_mode=(
            "boundary" if query_plan.intent == "evidence_boundary" else "topic"
        ),
        api_synthesis_allowed=(
            state_allows_api and evidence_available and len(batch.passages) >= 2
        ),
        matched_terms=matched_terms,
        reason=(
            "matched_published_state"
            if evidence_available
            else "matched_state_without_sufficient_evidence"
        ),
    )


def _fit_v2_local_reply(
    resources: PublishedLessonResources,
    request: RagAskRequestV1,
    person: PersonV1 | None,
    query_plan: RagQueryPlan,
    batch: RetrievalBatch,
    corpus: EvidenceCorpusV2,
) -> LocalReplyFit | None:
    """Resolve a reply exclusively through the state pack sealed in V2.

    V2 answer slots are publication data, not application constants.  The
    compatibility maps above only retain V1 diagnostic names; they never add
    passages or grant API permission that the active corpus did not publish.
    """

    generic_unsupported = _unsupported_slot_match(
        resources.course_id,
        resources.lesson_id,
        query_plan.original_question,
    )
    if generic_unsupported is not None:
        rule, matched_terms = generic_unsupported
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.{rule.slot_id}",
            topic_label=rule.topic_label,
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=matched_terms,
            answer_slot_supported=False,
            reason="answer_slot_not_published",
        )

    normalized = _normalize(query_plan.original_question)
    lesson_key = (resources.course_id, resources.lesson_id)
    legacy_matches = _merge_alias_matches(
        lesson_key,
        normalized,
        _matching_states(lesson_key, normalized),
    )
    reviewed_relation = _approved_question_relation(
        legacy_matches,
        query_plan.intent,
        normalized,
    )
    unsupported = _matching_v2_slots(
        corpus,
        normalized,
        query_plan.intent,
        status="unsupported",
    )
    if unsupported and not (
        reviewed_relation is not None
        and _FALSE_PREMISE_CORRECTION.search(normalized)
    ):
        slot, matched_terms = unsupported[0]
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.{slot.slot_id}",
            topic_label=slot.label,
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=matched_terms,
            answer_slot_supported=False,
            reason="answer_slot_not_published",
            slot_ids=(slot.slot_id,),
            boundary_ids=slot.boundary_ids,
        )

    if query_plan.intent == "identity":
        if not _valid_identity_person(resources, request, person):
            return None
        identity_slots = [
            slot
            for slot in corpus.answer_slots
            if slot.status == "supported" and slot.response_mode == "identity"
        ]
        passage_ids = _deduplicate(
            (
                *(
                passage.passage_id
                for passage in corpus.passages
                if person is not None and person.person_id in passage.person_ids
                ),
                *(
                passage_id
                for slot in identity_slots
                for passage_id in slot.passage_ids
                ),
            ),
        )
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.identity.{person.person_id}",
            topic_label=f"{person.name}的课程身份",
            response_mode="identity",
            api_synthesis_allowed=False,
            matched_terms=(person.name,),
            reason=(
                "published_person_identity"
                if batch.passages
                else "published_identity_without_retrieved_evidence"
            ),
            slot_ids=tuple(slot.slot_id for slot in identity_slots),
            passage_ids=passage_ids,
            boundary_ids=_deduplicate(
                boundary_id
                for slot in identity_slots
                for boundary_id in slot.boundary_ids
            ),
        )

    if query_plan.intent == "overview":
        overview_slots = [
            slot
            for slot in corpus.answer_slots
            if slot.status == "supported" and slot.response_mode == "overview"
        ]
        if not overview_slots:
            return None
        return _v2_slot_fit(
            resources,
            batch,
            overview_slots,
            matched_terms=(resources.course_package.title,),
            state_id=f"{resources.lesson_id}.overview",
            topic_label=resources.course_package.title,
            response_mode="overview",
            allow_api=False,
        )

    supported = _matching_v2_slots(
        corpus,
        normalized,
        query_plan.intent,
        status="supported",
    )
    requires_composite = (
        len(legacy_matches) >= 2
        and bool(_SYNTHESIS_LANGUAGE.search(normalized))
    )
    if supported and not requires_composite:
        slot, matched_terms = supported[0]
        return _v2_slot_fit(
            resources,
            batch,
            (slot,),
            matched_terms=matched_terms,
            state_id=_V2_SLOT_STATE_IDS.get(
                slot.slot_id,
                f"{resources.lesson_id}.slot.{slot.slot_id}",
            ),
            topic_label=slot.label,
            response_mode=slot.response_mode,
        )

    # Compatibility for already-reviewed V1 question wordings.  A legacy
    # relation may select a V2 slot, but every citation and API permission still
    # comes from that slot in the active immutable corpus.
    matches = legacy_matches
    if not matches:
        return None

    unsupported_facets = _unsupported_question_facets(
        resources,
        lesson_key,
        query_plan.original_question,
        matched_state_ids=tuple(state.state_id for state, _ in matches),
    )
    if unsupported_facets:
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.unpublished-question-facet",
            topic_label="当前发布未覆盖的问题用途或表述维度",
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=unsupported_facets,
            answer_slot_supported=False,
            reason="question_facet_not_published",
        )

    relation = reviewed_relation
    if relation is None:
        return LocalReplyFit(
            state_id=f"{resources.lesson_id}.unsupported.unpublished-question-relation",
            topic_label="当前发布未批准这些课程要素之间的问法关系",
            response_mode="unsupported_slot",
            api_synthesis_allowed=False,
            matched_terms=_deduplicate(
                term for _, terms in matches for term in terms
            ),
            answer_slot_supported=False,
            reason="question_relation_not_published",
        )

    slot_index = {slot.slot_id: slot for slot in corpus.answer_slots}
    selected_slots = _deduplicate_slots(
        slot_index[slot_id]
        for state, _ in matches
        for slot_id in _V2_LEGACY_STATE_SLOTS.get(state.state_id, ())
        if slot_id in slot_index and slot_index[slot_id].status == "supported"
    )
    if not selected_slots:
        return None

    if len(matches) >= 2 and _SYNTHESIS_LANGUAGE.search(normalized):
        state_id, topic_label = _COMPOSITE_STATES[lesson_key]
    else:
        state_id = matches[0][0].state_id
        topic_label = matches[0][0].topic_label
    return _v2_slot_fit(
        resources,
        batch,
        selected_slots,
        matched_terms=_deduplicate(
            term for _, terms in matches for term in terms
        ),
        state_id=state_id,
        topic_label=topic_label,
        response_mode=(
            "boundary" if query_plan.intent == "evidence_boundary" else "topic"
        ),
        allow_api=relation.api_synthesis_allowed,
    )


def _matching_v2_slots(
    corpus: EvidenceCorpusV2,
    normalized_question: str,
    intent: str,
    *,
    status: Literal["supported", "unsupported"],
) -> list[tuple[EvidenceAnswerSlotV1, tuple[str, ...]]]:
    matches: list[tuple[EvidenceAnswerSlotV1, tuple[str, ...]]] = []
    all_terms = _deduplicate(
        term
        for slot in corpus.answer_slots
        for group in slot.term_groups
        for term in group
    )
    for slot in corpus.answer_slots:
        if slot.status != status or not _v2_question_form_matches(
            slot,
            normalized_question,
            intent,
        ):
            continue
        matched_terms: list[str] = []
        for group in slot.term_groups:
            group_matches = [
                term
                for term in group
                if _v2_term_occurs_independently(
                    term,
                    normalized_question,
                    all_terms,
                )
            ]
            if not group_matches:
                break
            matched_terms.extend(group_matches)
        else:
            matches.append((slot, _deduplicate(matched_terms)))
    matches.sort(
        key=lambda item: (
            sum(len(_normalize(term)) for term in item[1]),
            len(item[1]),
            item[0].slot_id,
        ),
        reverse=True,
    )
    return matches


def _v2_term_occurs_independently(
    term: str,
    normalized_question: str,
    all_terms: tuple[str, ...],
) -> bool:
    normalized_term = _normalize(term)
    for occurrence in re.finditer(
        re.escape(normalized_term),
        normalized_question,
    ):
        start, end = occurrence.span()
        covered = False
        for blocker in all_terms:
            normalized_blocker = _normalize(blocker)
            if len(normalized_blocker) <= len(normalized_term):
                continue
            for outer in re.finditer(
                re.escape(normalized_blocker),
                normalized_question,
            ):
                if outer.start() <= start and outer.end() >= end:
                    covered = True
                    break
            if covered:
                break
        if not covered:
            return True
    return False


def _v2_question_form_matches(
    slot: EvidenceAnswerSlotV1,
    normalized_question: str,
    intent: str,
) -> bool:
    if slot.question_form == "identity":
        return intent == "identity"
    if slot.question_form == "creator_identity":
        return bool(_CREATOR_QUESTION.search(normalized_question))
    # The term groups are the semantic permission.  These forms describe how
    # to arrange the answer; ordinary pupils need not use an exact interrogative.
    return True


def _v2_slot_fit(
    resources: PublishedLessonResources,
    batch: RetrievalBatch,
    slots: Iterable[EvidenceAnswerSlotV1],
    *,
    matched_terms: tuple[str, ...],
    state_id: str,
    topic_label: str,
    response_mode: LocalResponseMode,
    allow_api: bool = True,
) -> LocalReplyFit:
    selected = _deduplicate_slots(slots)
    passage_ids = _deduplicate(
        passage_id for slot in selected for passage_id in slot.passage_ids
    )
    boundary_ids = _deduplicate(
        boundary_id for slot in selected for boundary_id in slot.boundary_ids
    )
    retrieved_ids = {
        item.passage.passage_id for item in batch.passages
    }
    eligible_count = len(retrieved_ids.intersection(passage_ids))
    evidence_available = batch.supported and eligible_count > 0
    api_allowed = (
        allow_api
        and evidence_available
        and eligible_count >= 2
        and all(slot.api_synthesis_allowed for slot in selected)
    )
    return LocalReplyFit(
        state_id=state_id,
        topic_label=topic_label,
        response_mode=response_mode,
        api_synthesis_allowed=api_allowed,
        matched_terms=matched_terms,
        reason=(
            "matched_published_v2_slot"
            if evidence_available
            else "matched_state_without_sufficient_evidence"
        ),
        slot_ids=tuple(slot.slot_id for slot in selected),
        passage_ids=passage_ids,
        boundary_ids=boundary_ids,
    )


def _deduplicate_slots(
    values: Iterable[EvidenceAnswerSlotV1],
) -> tuple[EvidenceAnswerSlotV1, ...]:
    result: list[EvidenceAnswerSlotV1] = []
    seen: set[str] = set()
    for value in values:
        if value.slot_id in seen:
            continue
        seen.add(value.slot_id)
        result.append(value)
    return tuple(result)


def _valid_identity_person(
    resources: PublishedLessonResources,
    request: RagAskRequestV1,
    person: PersonV1 | None,
) -> bool:
    if (
        request.persona_mode != "person"
        or person is None
        or request.person_id != person.person_id
    ):
        return False
    return any(
        candidate.person_id == person.person_id
        for candidate in resources.course_package.people
    )


def _matching_states(
    lesson_key: tuple[str, str],
    normalized_question: str,
) -> list[tuple[_StateRule, tuple[str, ...]]]:
    occurrences: list[tuple[_StateRule, str, int, int]] = []
    for state in _STATE_RULES[lesson_key]:
        for term in state.terms:
            normalized_term = _normalize(term)
            occurrences.extend(
                (state, term, match.start(), match.end())
                for match in re.finditer(
                    re.escape(normalized_term),
                    normalized_question,
                )
            )

    # Longest-term masking keeps a short entity from manufacturing a second
    # state when it occurs only inside a reviewed longer entity.  For example,
    # ``禹`` inside ``禹贡`` must not turn a map question into a false
    # map-plus-person relation.  A separate ``禹`` occurrence remains active.
    active = [
        occurrence
        for occurrence in occurrences
        if not any(
            other[2] <= occurrence[2]
            and other[3] >= occurrence[3]
            and (other[3] - other[2]) > (occurrence[3] - occurrence[2])
            for other in occurrences
        )
    ]
    grouped: dict[str, tuple[_StateRule, list[str]]] = {}
    for state, term, _, _ in active:
        current = grouped.setdefault(state.state_id, (state, []))[1]
        if term not in current:
            current.append(term)
    matches = [
        (state, tuple(terms))
        for state, terms in grouped.values()
    ]
    matches.sort(
        key=lambda item: (
            sum(len(_normalize(term)) for term in item[1]),
            len(item[1]),
        ),
        reverse=True,
    )
    return matches


def _merge_alias_matches(
    lesson_key: tuple[str, str],
    normalized_question: str,
    direct_matches: list[tuple[_StateRule, tuple[str, ...]]],
) -> list[tuple[_StateRule, tuple[str, ...]]]:
    """Add only reviewed aliases that occur in the original question."""

    states = {state.state_id: state for state in _STATE_RULES[lesson_key]}
    combined: dict[str, tuple[_StateRule, list[str]]] = {
        state.state_id: (state, list(terms))
        for state, terms in direct_matches
    }
    for state_id, aliases in _STATE_ALIASES.get(lesson_key, ()):
        matched_aliases = [
            alias
            for alias in aliases
            if _normalize(alias) in normalized_question
        ]
        if not matched_aliases:
            continue
        state = states[state_id]
        current = combined.setdefault(state_id, (state, []))[1]
        current.extend(matched_aliases)

    result = [
        (state, _deduplicate(terms))
        for state, terms in combined.values()
    ]
    result.sort(
        key=lambda item: (
            sum(len(_normalize(term)) for term in item[1]),
            len(item[1]),
        ),
        reverse=True,
    )
    return result


def _unsupported_question_facets(
    resources: PublishedLessonResources,
    lesson_key: tuple[str, str],
    question: str,
    *,
    matched_state_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return semantic n-grams absent from the reviewed question domain.

    The vocabulary is built positively from this exact sealed publication plus
    explicit state and alias language.  Function words and generic question
    grammar are ignored; every remaining two-character semantic facet must be
    supported by that vocabulary.  This prevents a course entity from lending
    authority to an unrelated purpose such as using an artefact as a flowerpot.
    """

    approved_phrases = [
        *(
            value
            for passage in resources.evidence_corpus.passages
            for value in (
                passage.text,
                passage.summary,
                *passage.keywords,
            )
        ),
        resources.course_package.title,
        *(item.word for item in resources.course_package.keywords),
        *(item.name for item in resources.course_package.people),
        *(
            term
            for state in _STATE_RULES[lesson_key]
            for term in state.terms
        ),
        *(
            alias
            for _, aliases in _STATE_ALIASES.get(lesson_key, ())
            for alias in aliases
        ),
        *(
            phrase
            for state_id in matched_state_ids
            for phrase in _STATE_APPROVED_QUESTION_FACETS.get(state_id, ())
        ),
        *_APPROVED_QUESTION_LANGUAGE,
    ]
    approved_han_segments = {
        segment
        for phrase in approved_phrases
        for run in _HAN_RUN.findall(_normalize(phrase))
        for segment in _semantic_segments(run)
    }
    approved_ascii = {
        word
        for phrase in approved_phrases
        for word in _ASCII_WORD.findall(_normalize(phrase))
    }

    unknown: list[str] = []
    normalized = _normalize(question)
    for run in _HAN_RUN.findall(normalized):
        unknown.extend(_unknown_semantic_runs(run, approved_han_segments))
    unknown.extend(
        word
        for word in _ASCII_WORD.findall(normalized)
        if word not in approved_ascii and not word.isdecimal()
    )
    return _deduplicate(unknown)


def _approved_question_relation(
    matches: list[tuple[_StateRule, tuple[str, ...]]],
    intent: str,
    normalized_question: str,
) -> _ApprovedQuestionRelation | None:
    """Resolve an explicitly reviewed state/predicate relationship.

    Corpus vocabulary alone cannot establish that two valid entities have the
    relationship asserted by a student.  Multi-state questions therefore need
    a peer rule whose state family contains every matched state and whose
    predicate is present verbatim in the original question.  Single-state
    questions likewise need an approved slot for that state.
    """

    state_ids = frozenset(state.state_id for state, _ in matches)
    if not state_ids:
        return None
    candidates = (
        _SINGLE_STATE_RELATIONS
        if len(state_ids) == 1
        else _PEER_STATE_RELATIONS
    )
    for relation in candidates:
        states_match = (
            state_ids == relation.state_ids
            if len(state_ids) == 1
            else state_ids.issubset(relation.state_ids)
        )
        if (
            states_match
            and intent in relation.intents
            and relation.predicate.search(normalized_question)
        ):
            return relation
    return None


def _semantic_segments(run: str) -> tuple[str, ...]:
    segments: list[str] = []
    maximum = min(len(run), 8)
    for size in range(2, maximum + 1):
        segments.extend(
            run[start : start + size]
            for start in range(0, len(run) - size + 1)
        )
    return tuple(segments)


def _unknown_semantic_runs(
    run: str,
    approved: set[str],
) -> tuple[str, ...]:
    unknown: list[str] = []
    pending: list[str] = []
    index = 0
    while index < len(run):
        if run[index] in _QUESTION_FUNCTION_CHARS:
            if len(pending) >= 2:
                unknown.append("".join(pending))
            pending.clear()
            index += 1
            continue

        matched = next(
            (
                run[index : index + size]
                for size in range(min(8, len(run) - index), 1, -1)
                if run[index : index + size] in approved
            ),
            None,
        )
        if matched is not None:
            if len(pending) >= 2:
                unknown.append("".join(pending))
            pending.clear()
            index += len(matched)
            continue
        pending.append(run[index])
        index += 1
    if len(pending) >= 2:
        unknown.append("".join(pending))
    return tuple(unknown)


def _unsupported_slot_match(
    course_id: str,
    lesson_id: str,
    question: str,
) -> tuple[_UnsupportedSlotRule, tuple[str, ...]] | None:
    normalized = _normalize(question)
    lesson_key = (course_id, lesson_id)
    anchor_terms = _original_anchor_terms(lesson_key, normalized)
    if not anchor_terms:
        return None

    if _CREATOR_QUESTION.search(normalized):
        for rule in _UNSUPPORTED_SLOT_RULES.get(lesson_key, ()):
            matched: list[str] = []
            for term_group in rule.required_term_groups:
                group_matches = [
                    term for term in term_group if _normalize(term) in normalized
                ]
                if not group_matches:
                    break
                matched.extend(group_matches)
            else:
                return rule, _deduplicate(matched)

        # A creator/craftsman question attached to a material course object is
        # still unsupported even when it uses a wording variant not enumerated
        # by the object-specific rules above.
        material_terms = _material_object_terms(lesson_key, normalized)
        if material_terms:
            return (
                _UnsupportedSlotRule(
                    "unpublished-creator-identity",
                    "课程材料未发布的设计者、建造者或工匠身份",
                    (),
                ),
                material_terms,
            )

    for rule in _GENERIC_UNSUPPORTED_SLOT_RULES:
        if rule.pattern.search(normalized):
            return (
                _UnsupportedSlotRule(
                    rule.slot_id,
                    rule.topic_label,
                    (),
                ),
                anchor_terms,
            )
    return None


def _original_anchor_terms(
    lesson_key: tuple[str, str],
    normalized_question: str,
) -> tuple[str, ...]:
    if lesson_key not in _STATE_RULES:
        return ()
    direct = (
        term
        for state in _STATE_RULES[lesson_key]
        for term in state.terms
        if _normalize(term) in normalized_question
    )
    aliases = (
        alias
        for _, values in _STATE_ALIASES.get(lesson_key, ())
        for alias in values
        if _normalize(alias) in normalized_question
    )
    return _deduplicate((*direct, *aliases))


def _material_object_terms(
    lesson_key: tuple[str, str],
    normalized_question: str,
) -> tuple[str, ...]:
    terms = {
        ("C-prequin-state", "L101"): (
            "二里头",
            "宫殿",
            "宫城",
            "道路网",
            "作坊",
            "青铜礼器",
        ),
        ("C-prequin-state", "L103"): (
            "商鞅方升",
            "方升",
            "标准量器",
            "量器",
            "睡虎地秦简",
            "秦简",
        ),
    }.get(lesson_key, ())
    return _deduplicate(
        term for term in terms if _normalize(term) in normalized_question
    )


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return tuple(result)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


__all__ = [
    "LOCAL_REPLY_VERSION",
    "LocalReplyFit",
    "LocalResponseMode",
    "detect_unsupported_answer_slot",
    "fit_local_reply",
]
