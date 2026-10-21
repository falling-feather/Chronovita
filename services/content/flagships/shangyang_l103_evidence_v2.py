"""Reviewed EvidenceCorpusV2 authoring source for L103 商鞅变法.

The V2 corpus preserves the thirty published V1 passage identifiers and adds
smaller, independently citable passages for deterministic answer-slot routing.
Every statement remains bounded by the exact published course: an answer slot
may improve wording, but it never authorizes a model to supply missing history.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.content.flagships.shangyang_l103 import (
    COURSE_ID,
    LESSON_ID,
    SHANGYANG_CORPUS_ID,
    build_shangyang_evidence_draft,
)
from services.contracts.evidence_v1 import sign_evidence_contract
from services.contracts.evidence_v2 import (
    EvidenceAnswerSlotV1,
    EvidenceBoundaryV1,
    EvidenceCorpusV2,
    EvidencePassageV2,
)


SHANGYANG_V1_CHECKSUM = (
    "06ab368e3f54051f21e56e4047ab9efb8f447cb81e2ef68620105995db4ce633"
)
SHANGYANG_V2_CHECKSUM = (
    "e198a2a492a926ecef444aa230dacbe5b446a19bbc8e823714c334b2149d765c"
)
SHANGYANG_V3_CREATED_AT = datetime(2026, 8, 31, 7, 30, tzinfo=timezone.utc)


def _boundary(
    boundary_id: str,
    label: str,
    category: str,
    statement: str,
) -> EvidenceBoundaryV1:
    return EvidenceBoundaryV1(
        boundary_id=boundary_id,
        label=label,
        category=category,
        statement=statement,
    )


BOUNDARIES = tuple(
    sorted(
        (
            _boundary(
                "shangyang-boundary-01-transmitted-distance",
                "传世叙事不是现场记录",
                "source_distance",
                "《史记·商君列传》成书于西汉，距离公元前四世纪中叶的改革二百多年。它保存重要叙事传统，但其中对话、动机和戏剧性细节不能当作变法现场的逐字记录。",
            ),
            _boundary(
                "shangyang-boundary-02-reform-chronology",
                "改革不是同日完成",
                "chronology",
                "约公元前356年和前350年是教学中组织改革阶段的常用节点，不表示军功、田制、县政、计量与基层执行在同一天、以同一范围一次完成。",
            ),
            _boundary(
                "shangyang-boundary-03-fangsheng-claim",
                "方升只能证明其直接承载的制度信息",
                "claim_limit",
                "商鞅方升的器形、容量和铭文能够直接支持公元前344年前后秦国推行标准量器及其后续沿用；它不能单独证明徙木故事、全部变法措施或所有地区的执行效果。",
            ),
            _boundary(
                "shangyang-boundary-04-slips-distance",
                "睡虎地秦简属于较晚成熟秦制",
                "chronology",
                "睡虎地秦简主要写于战国晚期至秦始皇时期，晚于商鞅最初变法百余年。它们可以观察后来秦律和行政实践，不可逐条署名商鞅，也不能自动还原最初法令。",
            ),
            _boundary(
                "shangyang-boundary-05-shangjunshu-authorship",
                "《商君书》须分篇分层使用",
                "source_distance",
                "《商君书》是经历编纂、增补与传抄的累积文本。回答可以讨论其中的农战、法令与国家能力思想，但不得把现存全书每一句都写成商鞅亲口自述。",
            ),
            _boundary(
                "shangyang-boundary-06-modern-rule-of-law",
                "战国法令不等于现代法治",
                "modern_concept",
                "战国秦的法令公开、赏罚和官吏责任服务于君主国家的治理与动员；现代法治还包含权利保障、权力约束与程序正义，两者不可因都使用“法”字便直接等同。",
            ),
            _boundary(
                "shangyang-boundary-07-multi-causation",
                "秦强盛与统一是多因长期过程",
                "causation",
                "商鞅改革是秦国国家能力增强的重要基础之一，但地理、资源、此前积累、后继政策、官僚执行、军事行动与列国局势共同参与了此后两个世纪的变化。",
            ),
            _boundary(
                "shangyang-boundary-08-teaching-model",
                "课堂变量不是秦国统计",
                "teaching_model",
                "国家能力、粮食供给、军事准备、制度信用、社会压力和旧贵族阻力是课堂观察工具，不是从战国档案恢复的连续统计值，也不能据此计算真实税率或伤亡。",
            ),
            _boundary(
                "shangyang-boundary-09-persona-hindsight",
                "人物只能知道其角色范围内的材料",
                "persona_knowledge",
                "人物模式是依据已发布材料形成的角色化教学表达，不是史料原话。商鞅、秦孝公及合成人群不得声称亲见西汉《史记》、现代研究或晚出秦简，也不得预知秦统一结局。",
            ),
            _boundary(
                "shangyang-boundary-10-land-concept",
                "土地制度不能压缩成现代私有制",
                "modern_concept",
                "传世材料中的开阡陌、田界和赋役变化支持讨论土地制度调整，但战国地区差异、授田关系与现代完整私有产权之间仍有距离。",
            ),
            _boundary(
                "shangyang-boundary-11-unsupported-exact-data",
                "当前语料不支持精确税率与个案数字",
                "claim_limit",
                "当前发布没有足以核验某一家庭田亩、税率、徭役天数、具体战役斩获、刑罚人数或徙木围观者对白的材料；遇到这类问题必须说明依据不足，不能交给模型估算。",
            ),
        ),
        key=lambda item: item.boundary_id,
    )
)


def _slot(
    slot_id: str,
    label: str,
    *,
    status: str = "supported",
    response_mode: str = "topic",
    question_form: str = "any",
    term_groups: tuple[tuple[str, ...], ...],
    passage_ids: tuple[str, ...] = (),
    boundary_ids: tuple[str, ...] = (),
    api_synthesis_allowed: bool = False,
) -> EvidenceAnswerSlotV1:
    return EvidenceAnswerSlotV1(
        slot_id=slot_id,
        label=label,
        status=status,
        response_mode=response_mode,
        question_form=question_form,
        term_groups=tuple(tuple(sorted(set(group))) for group in term_groups),
        passage_ids=tuple(sorted(set(passage_ids))),
        boundary_ids=tuple(sorted(set(boundary_ids))),
        api_synthesis_allowed=api_synthesis_allowed,
    )


ANSWER_SLOTS = tuple(
    sorted(
        (
            _slot(
                "shangyang-slot-01-overview",
                "变法内容、目标与代价总览",
                response_mode="overview",
                term_groups=(("商鞅变法", "变法"), ("内容", "措施", "改了什么")),
                passage_ids=("shangyang-p001", "shangyang-p002", "shangyang-p003", "shangyang-p004", "shangyang-p006", "shangyang-p007", "shangyang-p008", "shangyang-p009", "shangyang-p010", "shangyang-p012", "shangyang-p015", "shangyang-p018", "shangyang-p023", "shangyang-p024", "shangyang-p032"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-02-reform-chronology", "shangyang-boundary-07-multi-causation"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-02-identity",
                "商鞅身份与角色边界",
                response_mode="identity",
                question_form="identity",
                term_groups=(("商鞅", "卫鞅"), ("你是谁", "身份", "是谁")),
                passage_ids=("shangyang-p003", "shangyang-p011", "shangyang-p020", "shangyang-p025", "shangyang-p047"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-09-persona-hindsight"),
            ),
            _slot(
                "shangyang-slot-03-chronology",
                "改革年代与分阶段执行",
                response_mode="boundary",
                question_form="evidence_boundary",
                term_groups=(("公元前350年", "公元前356年", "年代"), ("一次完成", "分阶段", "先后")),
                passage_ids=("shangyang-p004", "shangyang-p016", "shangyang-p023", "shangyang-p031", "shangyang-p032", "shangyang-p033"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-02-reform-chronology", "shangyang-boundary-04-slips-distance"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-04-moving-wood",
                "徙木立信与制度信用",
                question_form="causality",
                term_groups=(("徙木", "徙木立信", "搬木头"), ("信用", "相信", "兑现")),
                passage_ids=("shangyang-p005", "shangyang-p034", "shangyang-p035"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-11-unsupported-exact-data"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-05-military-merit",
                "军功爵的身份机会与战争代价",
                question_form="comparison",
                term_groups=(("军功", "军功爵", "打仗升爵"), ("代价", "机会", "身份")),
                passage_ids=("shangyang-p006", "shangyang-p024", "shangyang-p036", "shangyang-p037"),
                boundary_ids=("shangyang-boundary-07-multi-causation", "shangyang-boundary-09-persona-hindsight"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-06-agriculture-war",
                "奖励耕战与农耕家庭负担",
                question_form="comparison",
                term_groups=(("农战", "奖励耕战", "耕织"), ("农户", "好处", "负担")),
                passage_ids=("shangyang-p007", "shangyang-p017", "shangyang-p036", "shangyang-p038"),
                boundary_ids=("shangyang-boundary-04-slips-distance", "shangyang-boundary-08-teaching-model", "shangyang-boundary-11-unsupported-exact-data"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-07-collective-liability",
                "什伍、连带责任与治理压力",
                question_form="causality",
                term_groups=(("什伍", "相互告发", "连坐"), ("基层控制", "惩罚", "责任")),
                passage_ids=("shangyang-p008", "shangyang-p017", "shangyang-p038", "shangyang-p039"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-04-slips-distance", "shangyang-boundary-06-modern-rule-of-law"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-08-county-administration",
                "县制、地方官吏与国家能力",
                question_form="causality",
                term_groups=(("县制", "县廷", "地方官"), ("中央命令", "国家能力", "执行")),
                passage_ids=("shangyang-p009", "shangyang-p017", "shangyang-p023", "shangyang-p040"),
                boundary_ids=("shangyang-boundary-02-reform-chronology", "shangyang-boundary-04-slips-distance"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-09-land-system",
                "开阡陌与土地制度概念边界",
                response_mode="boundary",
                question_form="evidence_boundary",
                term_groups=(("土地制度", "开阡陌", "田制"), ("土地私有", "私有产权", "井田")),
                passage_ids=("shangyang-p010", "shangyang-p023", "shangyang-p041", "shangyang-p042"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-10-land-concept"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-10-death-and-legacy",
                "商鞅之死与制度延续",
                question_form="causality",
                term_groups=(("商鞅之死", "车裂", "死后"), ("制度延续", "改革保留", "人亡政息")),
                passage_ids=("shangyang-p011", "shangyang-p024", "shangyang-p025", "shangyang-p043"),
                boundary_ids=("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-07-multi-causation"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-11-fangsheng",
                "商鞅方升的直接证明力",
                response_mode="boundary",
                question_form="evidence_boundary",
                term_groups=(("商鞅方升", "方升", "量器"), ("公元前344年", "度量衡", "铭文")),
                passage_ids=("shangyang-p012", "shangyang-p013", "shangyang-p014", "shangyang-p029", "shangyang-p044"),
                boundary_ids=("shangyang-boundary-03-fangsheng-claim",),
            ),
            _slot(
                "shangyang-slot-12-sleeping-tiger-slips",
                "睡虎地秦简的年代与用途",
                response_mode="boundary",
                question_form="evidence_boundary",
                term_groups=(("云梦秦简", "睡虎地秦简", "秦简"), ("亲笔", "年代", "秦律")),
                passage_ids=("shangyang-p015", "shangyang-p016", "shangyang-p017", "shangyang-p029", "shangyang-p039", "shangyang-p040", "shangyang-p045"),
                boundary_ids=("shangyang-boundary-04-slips-distance", "shangyang-boundary-09-persona-hindsight"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-13-book-of-lord-shang",
                "《商君书》的作者与篇章层次",
                response_mode="boundary",
                question_form="creator_identity",
                term_groups=(("商君书", "商鞅学派"), ("作者", "亲笔", "谁写的")),
                passage_ids=("shangyang-p018", "shangyang-p019", "shangyang-p020", "shangyang-p021", "shangyang-p022", "shangyang-p046"),
                boundary_ids=("shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-09-persona-hindsight"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-14-modern-law",
                "秦法与现代法治的概念边界",
                response_mode="boundary",
                question_form="comparison",
                term_groups=(("依法治国", "法治", "法律面前人人平等"), ("现代法律", "秦法", "一样")),
                passage_ids=("shangyang-p019", "shangyang-p022", "shangyang-p026", "shangyang-p039", "shangyang-p043", "shangyang-p048"),
                boundary_ids=("shangyang-boundary-06-modern-rule-of-law",),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-15-evaluation",
                "富国强兵、制度延续与社会代价",
                question_form="comparison",
                term_groups=(("商鞅评价", "商鞅变法", "变法评价"), ("代价", "富国强兵", "成功")),
                passage_ids=("shangyang-p006", "shangyang-p007", "shangyang-p008", "shangyang-p011", "shangyang-p022", "shangyang-p024", "shangyang-p027", "shangyang-p028", "shangyang-p030", "shangyang-p037", "shangyang-p038", "shangyang-p043", "shangyang-p048"),
                boundary_ids=("shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-07-multi-causation", "shangyang-boundary-08-teaching-model"),
                api_synthesis_allowed=True,
            ),
            _slot(
                "shangyang-slot-16-unsupported-exact-data",
                "未发布的精确税率、伤亡与个案数字",
                status="unsupported",
                response_mode="boundary",
                term_groups=(("具体税率", "税率", "田租比例", "伤亡人数", "斩首数字", "确切人数", "徭役天数", "每户田亩", "精确数值"),),
                boundary_ids=("shangyang-boundary-11-unsupported-exact-data",),
            ),
            _slot(
                "shangyang-slot-17-shiji-source-distance",
                "《史记·商君列传》的史料价值与现场边界",
                response_mode="boundary",
                question_form="evidence_boundary",
                term_groups=(
                    ("《史记·商君列传》", "商君列传", "史记"),
                    ("为什么重要", "价值", "重要"),
                    ("现场记录", "现场笔录", "第一手记录"),
                ),
                passage_ids=(
                    "shangyang-p003",
                    "shangyang-p004",
                    "shangyang-p031",
                    "shangyang-p033",
                ),
                boundary_ids=(
                    "shangyang-boundary-01-transmitted-distance",
                ),
                api_synthesis_allowed=True,
            ),
        ),
        key=lambda item: item.slot_id,
    )
)


_V1_EXPANSIONS = {
    "shangyang-p001": "这里的“解释”不是先给结论再寻找例子，而是先辨认材料形成时间、材料性质与可证范围，再把制度作用和不同群体承担的代价写进同一条推理链。",
    "shangyang-p002": "适龄表达保留“国家能力、身份通道、制度信用、社会压力”等核心概念，但避免把未经核验的刑罚细节变成猎奇叙事，也不复制教材章节。",
    "shangyang-p003": "这段叙事能支持孝公政治支持与卫鞅改革关系的历史框架；至于廷议中每个人说过的完整句子，只能作为司马迁组织人物性格和因果关系的叙事来阅读。",
    "shangyang-p004": "分期的用途是帮助学生安排先后与因果，不是把复杂改革切成两个整齐发布日期。地方接受、官吏执行、制度修订和后世沿用都有自己的时间过程。",
    "shangyang-p005": "可信的最低结论是后世以兑现赏格解释新法如何建立信用；木头所在城门、围观人数、现场语气以及每个参与者的心理都没有可逐项对照的同时代记录。",
    "shangyang-p006": "军功标准削弱了仅凭宗族身份取得政治利益的路径，却没有创造现代意义上的普遍平等。获得机会的前提与战争贡献绑定，因此上升通道和军事化压力必须并列说明。",
    "shangyang-p007": "粮帛产出、户籍、赋役与兵源进入同一组织体系后，国家更容易动员资源；家庭可能获得奖励，也可能面对耕作时间被压缩、征发增加和成员赴战的风险。",
    "shangyang-p008": "基层编组可以提高登记、告发和追责效率，但责任从行为人扩展到邻里或家户时，制度执行的收益与惩罚外溢便同时出现，不能只写其中一面。",
    "shangyang-p009": "县不是地图上换一个名称，而是命令、登记、征收、司法和复核逐步进入地方的组织过程。较晚秦简能帮助观察成熟形态，却不能倒推每个环节都由商鞅一次设计。",
    "shangyang-p010": "“开阡陌”可作为田界和赋役关系变化的传世线索；若直接翻译为今天个人可以自由处分的完整产权，就会遗漏国家授田、征役、地区差异和长期演变。",
    "shangyang-p011": "人物遭遇说明改革依赖政治支持并会触动利益，制度继续存在则说明官署、规则与新的利益关系已经超出改革者个人。两者并置比“人死政息”更能解释历史张力。",
    "shangyang-p012": "器物铭文把“大良造鞅”、孝公纪年与标准容量联系在同一件实物上，因此比西汉叙事更接近改革时代；其证明力仍限于计量制度及铭文承载的信息。",
    "shangyang-p013": "共同尺度可以让不同地点和经手人的容量记录相互比较，为征收、仓储和交换提供基础。至于实际误差、覆盖地区和所有使用者的感受，仍需其他材料。",
    "shangyang-p014": "后刻诏文说明统一后的秦仍重申尺度标准，展示制度可能跨越人物生命继续运作；它不是“所有商鞅措施原样不变”的证据。",
    "shangyang-p015": "简牍来自有考古地点、墓葬背景和文字内容的材料群，可以直接观察后来秦法行政；把它们合称“商鞅法令”会抹去百余年的增补、执行与变化。",
    "shangyang-p016": "年代顺序要求回答使用“延续、发展或成熟形态”一类表述，而不能让角色说自己亲自写下或阅读这些晚出的简文。",
    "shangyang-p017": "农业、市场、徭役与官吏职责出现在同一批制度材料中，说明国家治理已经深入日常。它能帮助解释执行机制，但不能单独确定某一制度始创者。",
    "shangyang-p018": "文本中的农战关系适合解释国家怎样把生产和战争连接起来；由于篇章层次不一，引用时应说明这是《商君书》思想传统，而非自动改写为商鞅第一人称。",
    "shangyang-p019": "公开法令与官吏责任可以提高可预期性，却仍服务于君主国家的控制、征收和动员。课堂比较只能指出局部相似，不能据此宣布秦已形成现代法治。",
    "shangyang-p020": "文本史研究通过词汇、制度背景、思想结构和传承线索判断篇章关系。它削弱的是“全书一人一时写成”的简单说法，并不否定该书研究战国政治思想的价值。",
    "shangyang-p021": "不同篇章可能保存较早材料、后学解释或更晚编纂痕迹。回答具体句子时应先说明篇章与研究争议，而不是用一个笼统年代覆盖全书。",
    "shangyang-p022": "《韩非子》的分类和批评说明战国末期思想家怎样回看商鞅之法，也能呈现“法”与“术”等概念的理论化；它与孝公朝的命令文本不是同一种证据。",
    "shangyang-p023": "县政、迁都、耕战和计量彼此连接，体现秦国组织资源与执行命令的长期建设。把改革理解为系统关系，比背诵互不相连的措施清单更接近历史过程。",
    "shangyang-p024": "改革的重要性可以成立，唯一原因论却不能成立。后继统治者的选择、地方官吏的工作、生产者提供的资源以及战争胜负都会改变制度实际效果。",
    "shangyang-p025": "传世故事把阻力集中为鲜明冲突，适合追问旧身份利益和政治联盟；它不足以证明所有贵族立场完全一致，也不能把反对者一概写成拒绝任何变化。",
    "shangyang-p026": "规则公开、按标准执行和官吏受约束可用于跨时代比较，但现代法治强调的基本权利、权力制约与程序救济不能被删去。比较必须同时写出相似点和不可跨越的差异。",
    "shangyang-p027": "学生可以用变量观察一个选择如何同时改变数个维度，却不能把分数解释为真实粮仓数量、军队规模或百姓满意度。任何精确历史结论仍须返回材料。",
    "shangyang-p028": "合成人群让农户、士卒和吏员的制度位置进入讨论，不为他们虚构姓名、家产、对白或统一态度。人物回答必须使用“从这一群体可能承担的处境看”等限定语。",
    "shangyang-p029": "证明力取决于问题与材料是否匹配：器物回答计量，秦简回答较晚制度运行，传世文献回答后人保存和组织的叙事。材料年代越近，也不代表它能回答所有问题。",
    "shangyang-p030": "卷宗需要把支持判断的片段、保留的不确定性和被拒绝的越界说法一并保存。漂亮结论不能替代证据链，关卡胜负也不能代替历史评价。",
}


_LOCATORS = {
    "shangyang-p001": "课程标准：史料实证、历史解释与学业质量要求",
    "shangyang-p002": "七年级上册目录：战国时期社会变革的课程位置",
    "shangyang-p003": "《史记·商君列传》：孝公求贤、卫鞅入秦与廷议开端",
    "shangyang-p004": "《史记·商君列传》：孝公时期改革先后相关段落",
    "shangyang-p005": "《史记·商君列传》：法令将行与徙木赏金叙事",
    "shangyang-p006": "《史记·商君列传》：军功授爵与宗室属籍相关段落",
    "shangyang-p007": "《史记·商君列传》：耕织、粮帛与奖惩相关段落",
    "shangyang-p008": "《史记·商君列传》：什伍、告奸与连带处置相关段落",
    "shangyang-p009": "《史记·商君列传》：集小乡邑聚为县及置令丞相关段落",
    "shangyang-p010": "《史记·商君列传》：开阡陌封疆相关段落",
    "shangyang-p011": "《史记·商君列传》：孝公卒、商鞅结局与秦法延续叙事",
    "shangyang-p012": "上海博物馆藏商鞅方升：孝公十八年第一组铭文",
    "shangyang-p013": "上海博物馆藏商鞅方升：器形、容量与计量用途说明",
    "shangyang-p014": "上海博物馆藏商鞅方升：秦始皇时期后刻诏文",
    "shangyang-p015": "湖北省博物馆云梦睡虎地秦简：出土与秦律内容概览",
    "shangyang-p016": "湖北省文物考古研究院：睡虎地秦简书写年代说明",
    "shangyang-p017": "湖北省文物考古研究院：秦简法律、行政与官吏内容概览",
    "shangyang-p018": "《商君书》：农战、赏罚与国家力量相关篇章群",
    "shangyang-p019": "《商君书》：法令公开与官吏责任相关篇章群",
    "shangyang-p020": "Pines 2016：累积文本与成书过程结论",
    "shangyang-p021": "Pines 2016：篇章年代判定的方法讨论",
    "shangyang-p022": "《韩非子·定法》：商鞅之法与申不害之术评价段落",
    "shangyang-p023": "中国社科院秦文化研究：县制、迁都与耕战综合论述",
    "shangyang-p024": "中国社科院秦文化研究：秦长期国家建设与多因解释",
    "shangyang-p025": "《史记·商君列传》：廷议、太子犯法与孝公后政治冲突",
    "shangyang-p026": "课程标准导向的概念辨析：历史语境与现代法治",
    "shangyang-p027": "L103 六回合课堂模型：六项变量的教学用途说明",
    "shangyang-p028": "L103 人物档案：农耕家庭、军功士卒与县廷吏员",
    "shangyang-p029": "方升、秦简与《史记》的跨材料证明力比较",
    "shangyang-p030": "L103 史官卷宗：选择、轨迹、代价与来源要求",
    "shangyang-p031": "《史记·商君列传》：改革叙事顺序与史家组织方式",
    "shangyang-p032": "中国社科院秦文化研究：战国竞争与秦长期转型",
    "shangyang-p033": "课程标准导向的时序方法：事件、材料与解释分层",
    "shangyang-p034": "课程标准导向的制度信用教学解释",
    "shangyang-p035": "《韩非子·定法》与《史记》信赏叙事的材料差异",
    "shangyang-p036": "中国社科院秦文化研究：耕战政策与国家动员",
    "shangyang-p037": "课程标准导向的军功爵机会—代价比较",
    "shangyang-p038": "L103 农耕家庭档案：生产、赋役和战争风险",
    "shangyang-p039": "湖北省文物考古研究院：成熟秦制中的责任与执行",
    "shangyang-p040": "湖北省博物馆睡虎地秦简：地方官吏与行政实践",
    "shangyang-p041": "《史记·商君列传》：阡陌与田制叙述的文字范围",
    "shangyang-p042": "中国社科院秦文化研究：土地、赋役与长期制度变化",
    "shangyang-p043": "《韩非子·定法》：后世法家视角下的功效与不足",
    "shangyang-p044": "上海博物馆商鞅方升：两组铭文的分层读取",
    "shangyang-p045": "湖北省博物馆睡虎地秦简：材料群内部内容差异",
    "shangyang-p046": "Pines 2016：作者归属、学派传统与文本价值",
    "shangyang-p047": "《史记·商君列传》：卫鞅、商鞅称谓与人物经历",
    "shangyang-p048": "课程标准导向的秦法—现代法治比较框架",
}


_BOUNDARY_BY_PASSAGE = {
    "shangyang-p001": ("shangyang-boundary-08-teaching-model",),
    "shangyang-p002": ("shangyang-boundary-08-teaching-model",),
    "shangyang-p003": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p004": ("shangyang-boundary-02-reform-chronology",),
    "shangyang-p005": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-09-persona-hindsight", "shangyang-boundary-11-unsupported-exact-data"),
    "shangyang-p006": ("shangyang-boundary-07-multi-causation", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p007": ("shangyang-boundary-08-teaching-model", "shangyang-boundary-09-persona-hindsight", "shangyang-boundary-11-unsupported-exact-data"),
    "shangyang-p008": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p009": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-02-reform-chronology", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p010": ("shangyang-boundary-09-persona-hindsight", "shangyang-boundary-10-land-concept"),
    "shangyang-p011": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-07-multi-causation", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p012": ("shangyang-boundary-03-fangsheng-claim", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p013": ("shangyang-boundary-03-fangsheng-claim", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p014": ("shangyang-boundary-03-fangsheng-claim",),
    "shangyang-p015": ("shangyang-boundary-04-slips-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p016": ("shangyang-boundary-04-slips-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p017": ("shangyang-boundary-04-slips-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p018": ("shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p019": ("shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p020": ("shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p021": ("shangyang-boundary-05-shangjunshu-authorship",),
    "shangyang-p022": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p023": ("shangyang-boundary-02-reform-chronology", "shangyang-boundary-07-multi-causation"),
    "shangyang-p024": ("shangyang-boundary-07-multi-causation", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p025": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p026": ("shangyang-boundary-06-modern-rule-of-law",),
    "shangyang-p027": ("shangyang-boundary-08-teaching-model",),
    "shangyang-p028": ("shangyang-boundary-08-teaching-model", "shangyang-boundary-09-persona-hindsight"),
    "shangyang-p029": ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-03-fangsheng-claim", "shangyang-boundary-04-slips-distance"),
    "shangyang-p030": ("shangyang-boundary-08-teaching-model",),
}


_NEW_PASSAGE_SPECS = (
    ("shangyang-p031", "src-shiji-shangjun", "史家叙事顺序不等于原始档案顺序", "《史记·商君列传》把求贤、廷议、徙木、颁令、受封与结局连成有起伏的人物传记。这样的排列帮助后人理解司马迁怎样解释改革的机会、冲突和后果，却不能证明我们拥有每道法令的原始卷宗，也不能保证传记中的先后正好对应各地实施节奏。使用这段材料时，应把“史家如何组织叙事”与“改革实际如何分期执行”分开。", "《史记》的叙事次序是重要线索，不是完整行政日历。", "《史记·商君列传》：全篇叙事结构与事件排列", ("shangyang-p003", "shangyang-p004"), ("商鞅", "史记", "叙事顺序"), "transmitted_text", "interpretation", "西汉史家组织公元前四世纪事件的后世传记。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-02-reform-chronology", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p032", "src-nopss-qin", "改革发生在战国国家竞争与秦长期转型中", "现代综合研究把商鞅变法放在战国人口、土地、农业、战争和行政组织持续变化的背景中。秦并非在一次变法前毫无积累，也不是改革结束后便自动走向统一。政策能够持续，既需要君主支持，也需要地方官吏、生产者、士卒和后继统治者把规则转化为日常运行。因而“重要转折”比“一个人突然改变全部历史”更符合材料能够承受的解释。", "改革是秦长期国家建设的重要转折，不是孤立开关。", "中国社科院秦文化研究：战国竞争、制度积累与国家建设", ("shangyang-p023", "shangyang-p024"), ("战国竞争", "国家建设", "多因解释"), "scholarly_interpretation", "consensus", "现代研究对战国秦长期变化的综合解释。", ("shangyang-boundary-02-reform-chronology", "shangyang-boundary-07-multi-causation")),
    ("shangyang-p033", "src-moe-2022", "事件年代、材料年代与解释年代分层", "回答商鞅变法问题时至少要标出三种时间：改革发生于公元前四世纪中叶；方升第一组铭文接近改革时代；睡虎地秦简多晚出百余年，《史记》又成书于西汉，现代研究则是今天对这些材料的重新分析。材料形成得晚并不等于毫无价值，但它回答的问题会改变。先列时间层次，再判断证明力，可以防止把后世记忆倒写成现场。", "年代分层决定材料能直接回答哪一类问题。", "课程标准：时空观念与史料实证的综合运用", ("shangyang-p004", "shangyang-p012", "shangyang-p016", "shangyang-p020"), ("年代分层", "材料年代", "证据边界"), "teaching_explanation", "consensus", "现代教学方法，所列古代年代分别来自对应材料。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-02-reform-chronology", "shangyang-boundary-04-slips-distance")),
    ("shangyang-p034", "src-moe-2022", "制度信用来自规则可知、承诺兑现与执行可预期", "徙木立信之所以适合课堂讨论，不在于木头本身具有制度力量，而在于它把三个问题集中呈现出来：百姓能否知道规则，官府是否兑现已经公布的奖赏，相同条件下的处置是否可预期。一次赏格即使兑现，也不能代替长期、稳定和可复核的执行。因此模板回答应从传世故事提出制度信用问题，同时明确故事细节的证据距离。", "徙木故事提供制度信用问题，信用仍需长期执行维持。", "课程标准导向的制度信用教学解释", ("shangyang-p005", "shangyang-p019", "shangyang-p026"), ("兑现承诺", "制度信用", "规则公开"), "teaching_explanation", "interpretation", "现代课堂解释，不是战国术语的原样复述。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p035", "src-hanfeizi-dingfa", "后世思想评价不能核验徙木现场", "《韩非子·定法》从较晚战国的理论语境评价商鞅之法及其得失，说明商鞅改革在后世已成为讨论“法”与国家治理的重要对象。它可以和《史记》的信赏故事一起帮助解释后人如何理解制度执行，却没有提供徙木现场的独立同期记录。不同传世文本形成相互参照时，仍须保留各自年代、文体和问题意识。", "后世理论评价可解释制度思想，不能变成徙木现场旁证。", "《韩非子·定法》：商鞅之法评价及其材料性质", ("shangyang-p005", "shangyang-p022"), ("后世评价", "法", "徙木立信"), "transmitted_text", "interpretation", "较晚战国思想文本，仍晚于商鞅活动时期。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p036", "src-nopss-qin", "耕与战被纳入同一国家动员结构", "奖励农业生产可以增加粮食与赋税基础，军功奖励则把兵员、战场表现和身份利益联系起来；县政、户籍和计量又使资源更容易登记与调动。耕战并不是两个孤立口号，而是国家把生产、服役和奖惩组织起来的一套方向。它能增强竞争能力，也会使战争目标更深地进入家庭生活，因而必须和社会承受一同评价。", "耕战政策连接粮食、兵源、身份与行政动员。", "中国社科院秦文化研究：耕战、县制与国家能力相关论述", ("shangyang-p006", "shangyang-p007", "shangyang-p023"), ("兵源", "国家动员", "奖励耕战"), "scholarly_interpretation", "interpretation", "现代研究对战国秦政策关系的综合解释。", ("shangyang-boundary-07-multi-causation", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p037", "src-moe-2022", "军功爵评价必须同时写机会条件与战争成本", "与只按宗族出身分配身份相比，军功爵为部分非贵族男性提供了新的上升可能，也削弱了旧贵族对身份利益的独占。但这种机会以国家承认的军功为条件，不面向所有人，也与持续战争、伤亡风险和家庭分离相连。课堂回答不应在“完全公平”与“只有压迫”之间二选一，而要说明机会由什么条件产生、代价由谁承担。", "军功爵改变身份通道，却不等于现代普遍平等。", "课程标准导向的制度机会与代价比较", ("shangyang-p006", "shangyang-p024", "shangyang-p027"), ("世袭特权", "军功爵", "战争代价"), "teaching_explanation", "interpretation", "现代课堂比较框架，非战国统计或价值口号。", ("shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-08-teaching-model", "shangyang-boundary-09-persona-hindsight", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p038", "src-moe-2022", "从农耕家庭观察奖励、赋役与战争风险", "农耕家庭是课堂中的合成人群，用来追踪一项制度怎样同时影响耕作时间、粮食预期、征发责任和家庭成员赴战风险。传世材料能够说明国家奖励生产和服役的政策方向，较晚秦简能展示成熟制度深入日常的程度；二者都不足以恢复某一户的田亩、收成、税率或感受。角色回答必须使用群体处境，而非虚构个人日记。", "农户可能得到激励，也可能承担征发和战争压力。", "L103 农耕家庭角色档案与课堂负担模型", ("shangyang-p007", "shangyang-p017", "shangyang-p027", "shangyang-p028"), ("农耕家庭", "徭役", "社会压力"), "teaching_explanation", "interpretation", "现代合成人群表达；历史依据来自传世制度方向和较晚秦制。", ("shangyang-boundary-04-slips-distance", "shangyang-boundary-08-teaching-model", "shangyang-boundary-09-persona-hindsight", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p039", "src-hb-archaeology-slips", "成熟秦制显示责任如何进入基层执行", "睡虎地秦简所见法律、行政和官吏工作说明，到了战国晚期与统一前后，规则已能通过文书、登记、审理和官吏责任进入地方日常。这有助于理解早期改革强调执行能力的长期方向，也显示“有法”并不只是一句口号。由于材料年代较晚，它不能证明每项责任制度均在商鞅时期以同样文字、同样范围存在。", "秦简可观察成熟执行体系，不可倒推全部原初条文。", "湖北省文物考古研究院：睡虎地秦简法律行政内容与年代", ("shangyang-p008", "shangyang-p016", "shangyang-p017", "shangyang-p026"), ("官吏责任", "成熟秦制", "基层执行"), "archaeological_evidence", "consensus", "战国晚期至秦始皇时期，晚于最初变法百余年。", ("shangyang-boundary-04-slips-distance", "shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p040", "src-hubei-museum-slips", "地方官吏连接中央规则与日常治理", "睡虎地材料使市场、农业、徭役、司法和官吏工作等治理领域具体可见，说明中央规则需要地方人员记录、解释和执行。县制的历史意义因此不仅是行政区划名称，还包括命令能够抵达地方、地方信息能够形成文书并受到追责。简牍展示的是较晚成熟形态，适合解释制度如何运作，不适合让县吏角色自称手持商鞅原令。", "县政依赖地方官吏和文书执行，形成过程跨越较长时间。", "湖北省博物馆云梦睡虎地秦简：秦律与官吏工作材料概览", ("shangyang-p009", "shangyang-p015", "shangyang-p017", "shangyang-p023"), ("地方官吏", "文书", "县制"), "archaeological_evidence", "interpretation", "较晚秦制的出土材料，用于观察制度延续与成熟。", ("shangyang-boundary-02-reform-chronology", "shangyang-boundary-04-slips-distance", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p041", "src-shiji-shangjun", "“开阡陌”是传世制度线索而非现代产权定义", "《史记》用开阡陌封疆等语言描述田界和制度调整，证明西汉史家把土地关系变化视为变法的重要内容。文本没有为我们提供覆盖秦国所有地区、所有农户的现代产权登记，也没有直接回答土地能否自由买卖、国家授田如何运行等全部问题。因此可说改革推动田界、赋役和土地制度变化，不宜仅用“废井田即完全私有”收束。", "传世线索支持土地制度变化，不能包办现代产权结论。", "《史记·商君列传》：开阡陌封疆及相关田制叙述", ("shangyang-p010", "shangyang-p029"), ("土地制度", "开阡陌", "田界"), "transmitted_text", "interpretation", "西汉对战国田制变化的后世叙述。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-10-land-concept", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p042", "src-nopss-qin", "土地、赋役与国家建设需要长期解释", "现代综合研究把田制变化同农业开发、赋役组织、人口控制和国家建设联系起来，而不是把一条传世用语直接翻译成今天的所有权制度。不同地区的土地实践可能并不一致，政策目标、地方执行与家庭实际处境也需要分层。课程可以讨论改革怎样重组国家与土地、农户之间的关系，但不从现有材料编造统一地价、税率或分田面积。", "土地制度变化应放入赋役、农业与行政的长期关系中。", "中国社科院秦文化研究：农业、田制与国家建设综合论述", ("shangyang-p010", "shangyang-p023", "shangyang-p024"), ("农业开发", "土地关系", "赋役"), "scholarly_interpretation", "interpretation", "现代综合研究，不能替代地区性原始档案。", ("shangyang-boundary-07-multi-causation", "shangyang-boundary-10-land-concept", "shangyang-boundary-11-unsupported-exact-data")),
    ("shangyang-p043", "src-hanfeizi-dingfa", "后世评价把制度功效与不足放在一起", "《韩非子·定法》肯定商鞅重法带来的治理效果，同时从战国末期的理论立场讨论其不足。它证明后世法家内部并非只用单一赞歌评价改革，也说明制度是否有效和制度是否没有代价是两个不同问题。结合《史记》的个人结局和现代多因解释，课堂评价应同时观察规则执行、国家能力、政治支持与社会承受。", "后世评价既讨论功效，也保留对制度局限的判断。", "《韩非子·定法》：商鞅之法功效与不足相关段落", ("shangyang-p011", "shangyang-p022", "shangyang-p024", "shangyang-p025"), ("制度功效", "后世评价", "法"), "transmitted_text", "interpretation", "较晚战国思想评价，不是孝公朝行政档案。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-07-multi-causation")),
    ("shangyang-p044", "src-shanghaimuseum-fangsheng", "两组铭文必须按年代分别读取", "商鞅方升第一组铭文关联秦孝公十八年、大良造鞅和标准容量，接近改革时代；秦始皇时期后刻诏文则属于百余年后的统一推广。两组文字同处一器，恰好说明制度沿用可以被器物观察，也提醒读者不能把后刻内容倒置为商鞅当年的原话。回答应分别说明每组铭文的年代、直接信息与不能证明的范围。", "同一器物上的前后铭文展示沿用，也要求严格分层。", "上海博物馆藏商鞅方升：第一组铭文与后刻诏文对读", ("shangyang-p012", "shangyang-p014", "shangyang-p029"), ("后刻诏文", "商鞅方升", "铭文分层"), "archaeological_evidence", "consensus", "第一组铭文约前344年，后刻诏文属秦始皇时期。", ("shangyang-boundary-03-fangsheng-claim", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p045", "src-hubei-museum-slips", "秦简是材料群，不是一份单一法典", "睡虎地出土简牍包含法律条文、解释、行政文书和官吏工作相关材料，内容、用途与书写时间并不完全相同。把整批材料称为“商鞅亲笔法典”会同时抹去材料类型差异和百余年年代距离。可靠做法是先指出具体材料类别，再用它说明成熟秦制的某一方面，并把创制者、执行者和保存者区分开。", "睡虎地秦简须按材料类别使用，不能整批直接署名商鞅。", "湖北省博物馆云梦睡虎地秦简：简牍类别与内容范围", ("shangyang-p015", "shangyang-p016", "shangyang-p017"), ("材料类别", "睡虎地秦简", "秦律"), "archaeological_evidence", "consensus", "主要为战国晚期与秦始皇时期材料。", ("shangyang-boundary-04-slips-distance", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p046", "src-cambridge-shangjunshu", "作者边界不降低《商君书》的思想史价值", "把《商君书》视为累积文本，并不意味着全书无用或全部虚假。分篇研究可以辨认较早制度经验、商鞅学派思想、后续争论和编纂痕迹，使不同层次承担不同证明任务。人物模式不得把整书化为第一人称回忆；专家模式则可以在标明研究分歧后，用它讨论农战、法令公开和强国家思想怎样被继承与发展。", "分层使用能同时保留作者边界和文本的思想史价值。", "Pines 2016：篇章层次、作者归属与文本史意义", ("shangyang-p018", "shangyang-p020", "shangyang-p021"), ("作者归属", "商君书", "文本价值"), "scholarly_interpretation", "consensus", "现代文本史研究对先秦至后续编纂层次的分析。", ("shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p047", "src-shiji-shangjun", "卫鞅、商鞅与课堂人物身份", "传世叙事称其为卫鞅，记述入秦后主持改革、任大良造并受封商地，后世通常称商鞅。课堂人物档案据此介绍“改革主持者”的身份，但不会把传记中的全部对白写成本人原话，也不会让角色知道后世《史记》《商君书》研究、睡虎地秦简或秦最终统一的结果。身份回答应先交代称谓与角色，再主动说明知识边界。", "商鞅身份来自传世人物框架，角色回答必须声明后见之明边界。", "《史记·商君列传》：卫鞅称谓、任职、受封与人物经历", ("shangyang-p003", "shangyang-p011", "shangyang-p020", "shangyang-p025"), ("人物身份", "卫鞅", "商鞅"), "transmitted_text", "interpretation", "西汉传记保存的战国人物经历框架。", ("shangyang-boundary-01-transmitted-distance", "shangyang-boundary-05-shangjunshu-authorship", "shangyang-boundary-09-persona-hindsight")),
    ("shangyang-p048", "src-moe-2022", "比较秦法与现代法治要同时写相似和差异", "秦的法令公开、统一尺度、官吏责任和按规则执行，可以成为理解国家治理可预期性的历史材料；什伍追责、严密动员和君主国家目标又显示其制度语境。现代法治强调法律约束公共权力、基本权利与正当程序，不能只抽取“依法办事”四个字。规范回答应先说明可比较的局部问题，再明确两种制度的目的、权力结构和权利位置不同。", "秦法可用于历史比较，但绝不能直接命名为现代法治。", "课程标准导向的跨时代制度比较与概念边界", ("shangyang-p019", "shangyang-p022", "shangyang-p026"), ("权利保障", "法治", "程序"), "boundary_note", "consensus", "现代概念比较，不把现代术语倒置到战国。", ("shangyang-boundary-06-modern-rule-of-law", "shangyang-boundary-08-teaching-model")),
)


def _passage_slots() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for slot in ANSWER_SLOTS:
        for passage_id in slot.passage_ids:
            result.setdefault(passage_id, []).append(slot.slot_id)
    return {
        passage_id: tuple(sorted(slot_ids))
        for passage_id, slot_ids in result.items()
    }


def build_shangyang_evidence_v2(
    *,
    sealed_at: datetime = SHANGYANG_V3_CREATED_AT,
    sealed_by: str = "content-reviewer-shangyang-v3",
) -> EvidenceCorpusV2:
    """Build the current sealed L103 corpus using the V2 contract schema."""

    v1 = build_shangyang_evidence_draft()
    v1_by_id = {item.passage_id: item for item in v1.passages}
    slots_by_passage = _passage_slots()

    passages: list[EvidencePassageV2] = []
    for item in v1.passages:
        boundaries = tuple(sorted(_BOUNDARY_BY_PASSAGE[item.passage_id]))
        passages.append(
            EvidencePassageV2(
                passage_id=item.passage_id,
                source_id=item.source_id,
                title=item.title,
                text=item.text + _V1_EXPANSIONS[item.passage_id],
                summary=item.summary,
                source_locator=_LOCATORS[item.passage_id],
                fact_ids=item.fact_ids,
                person_ids=item.person_ids,
                keywords=item.keywords,
                answer_slot_ids=slots_by_passage.get(item.passage_id, ()),
                boundary_ids=boundaries,
                persona_scope=(
                    "expert_and_listed_people" if item.person_ids else "expert_only"
                ),
                evidence_kind=item.evidence_kind,
                certainty=item.certainty,
                chronology_note=item.chronology_note,
                teaching_note=item.teaching_note,
            )
        )

    for (
        passage_id,
        source_id,
        title,
        text,
        summary,
        source_locator,
        ancestor_ids,
        keywords,
        evidence_kind,
        certainty,
        chronology_note,
        boundary_ids,
    ) in _NEW_PASSAGE_SPECS:
        ancestors = [v1_by_id[item] for item in ancestor_ids]
        fact_ids = tuple(
            sorted({fact_id for item in ancestors for fact_id in item.fact_ids})
        )
        person_ids = tuple(
            sorted({person_id for item in ancestors for person_id in item.person_ids})
        )
        normalized_boundary_ids = set(boundary_ids)
        if person_ids:
            normalized_boundary_ids.add(
                "shangyang-boundary-09-persona-hindsight"
            )
        passages.append(
            EvidencePassageV2(
                passage_id=passage_id,
                source_id=source_id,
                title=title,
                text=text,
                summary=summary,
                source_locator=source_locator,
                fact_ids=fact_ids,
                person_ids=person_ids,
                keywords=tuple(sorted(set(keywords))),
                answer_slot_ids=slots_by_passage.get(passage_id, ()),
                boundary_ids=tuple(sorted(normalized_boundary_ids)),
                persona_scope=(
                    "expert_and_listed_people" if person_ids else "expert_only"
                ),
                evidence_kind=evidence_kind,
                certainty=certainty,
                chronology_note=chronology_note,
                teaching_note="",
            )
        )

    provisional = EvidenceCorpusV2(
        corpus_id=SHANGYANG_CORPUS_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        corpus_version=3,
        status="sealed",
        title="L103 商鞅变法正式证据库 V3",
        scope_note=(
            "仅服务 C-prequin-state/L103 的精确发布。V3 保留前版全部四十八个稳定片段 ID，"
            "并将传世文献、商鞅方升、睡虎地秦简、后世评价、现代法治边界与人物知识范围"
            "拆成可独立引用的原子片段，并显式支持《史记·商君列传》的史料价值与现场边界追问。"
            "API 只能综合受支持槽位列出的当前片段；未发布的精确"
            "税率、伤亡和个案数字必须返回依据不足。"
        ),
        supersedes_checksum=SHANGYANG_V2_CHECKSUM,
        sources=v1.sources,
        boundaries=BOUNDARIES,
        answer_slots=ANSWER_SLOTS,
        passages=tuple(sorted(passages, key=lambda item: item.passage_id)),
        created_at=SHANGYANG_V3_CREATED_AT,
        sealed_at=sealed_at,
        sealed_by=sealed_by,
        checksum="0" * 64,
    )
    return sign_evidence_contract(provisional)


# Explicit alias used by content integration code that names builders by corpus.
build_shangyang_evidence_corpus_v2 = build_shangyang_evidence_v2


__all__ = [
    "ANSWER_SLOTS",
    "BOUNDARIES",
    "SHANGYANG_V1_CHECKSUM",
    "SHANGYANG_V2_CHECKSUM",
    "SHANGYANG_V3_CREATED_AT",
    "build_shangyang_evidence_corpus_v2",
    "build_shangyang_evidence_v2",
]
