"""Reviewed authoring source for C-prequin-state / L103.

The lesson distinguishes transmitted narratives, excavated evidence, scholarly
interpretation, and the classroom decision model. Runtime artifacts are produced
through the ordinary course, evidence, scenario, and V3 release workflows.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from services import content
from services.content import evidence_workflow, scenario_authoring
from services.contracts.evidence_v1 import (
    EvidencePassageV1,
    EvidenceSourceV1,
    LessonPresentationV1,
    sign_evidence_contract,
)
from services.contracts.v1 import CoursePackageV1, course_package_from_legacy


COURSE_ID = "C-prequin-state"
LESSON_ID = "L103"
SHANGYANG_SCENARIO_ID = "shangyang-institutional-reform"
SHANGYANG_CORPUS_ID = "shangyang-evidence"
SHANGYANG_PRESENTATION_ID = "shangyang-classroom-intro"


BODY = [
    (
        "公元前四世纪的秦国为什么要改变旧制度？如果一套改革让国家更能征粮、征兵和执行命令，却让家庭承受更严密的"
        "管束，我们应当只用“成功”或“失败”评价它吗？本课把商鞅变法放回战国竞争、秦孝公求变与秦国长期国家建设的"
        "背景中。学生不是背诵若干措施，而要追问：谁制定规则、规则怎样抵达地方、谁获得新机会、谁失去旧特权，又有谁"
        "承担了难以写进胜利叙事的压力。最后的判断必须同时写出国家能力、制度信用、社会代价和证据边界。"
    ),
    (
        "战国不是七国在同一时刻拥有相同制度的静态地图。兼并战争、人口与土地竞争、农业生产、官僚组织和交通条件都在"
        "变化。秦地处西方，但“落后所以一次变法便突然强盛”过于简单。秦此前已有政治与军事积累，改革也经历多年推行、"
        "修订和继承。把秦后来统一六国全部归功于商鞅，既会忽略孝公以后多代统治者、将领、官吏和普通生产者，也会把两个"
        "世纪的复杂过程压缩成一位人物按下开关。本课因此使用“重要转折和长期基础”，不使用“唯一原因”。"
    ),
    (
        "关于商鞅生平和变法次序，最完整、最有影响的叙事之一来自西汉司马迁《史记·商君列传》。它记述卫鞅入秦、与旧臣"
        "辩论、徙木立信、推行法令、受封于商以及孝公死后的结局。文本珍贵，因为它保存了汉代史家能够接触和整理的早期"
        "传统，也塑造了后世对商鞅的基本认识；但《史记》成书晚于变法二百多年，不能当作宫廷辩论逐字记录。越生动的对话"
        "和戏剧性场景，越需要标明它是传世叙事，而不是假装我们拥有当时的录音。"
    ),
    (
        "“徙木立信”讲的是法令公布后，人们不相信重赏会兑现，官府便把一根木头移到城门并按承诺给赏。这个故事适合讨论"
        "制度信用：规则若不公开、赏罚若不兑现，人们很难改变行为。不过它首先见于后世传世记载，目前没有可与情节逐项"
        "对应的出土档案。课堂可以问“为什么新制度要让人相信”，却不能宣称已经考古证实木头的位置、赏金数量和围观者"
        "对白。故事提供问题意识，不替代证据核验。"
    ),
    (
        "传世材料把奖励军功、鼓励耕织、整顿户籍与基层组织、设置县级治理、统一度量衡以及改变土地制度等内容同改革联系"
        "起来。这些措施不是互不相干的口号：稳定尺度有利于赋税和交换，户籍与地方官署有利于掌握人口资源，军功爵把"
        "战场表现同身份上升连接，农业激励则服务粮食供给。它们共同指向更强的组织和动员能力。但不同措施的年代、范围与"
        "具体执行方式并不都拥有同样强的证据，不能把后人概括的一张清单当作同一天颁布的完整原令。"
    ),
    (
        "军功爵常被解释为打破旧贵族对政治身份的垄断，让非贵族男性可能凭军功取得爵位和利益。这确实触动世袭特权，也"
        "可能扩大国家对士卒的激励；它同时把社会上升与战争绩效紧密相连。对七年级学生而言，关键不是简单称它“公平”，"
        "而是比较两种秩序：身份只看出身会排斥许多人，身份高度依赖军功又会让战争深入社会生活。旧特权被削弱和军事化"
        "压力上升可以同时成立。"
    ),
    (
        "“奖励耕战”把农业产出、粮食储备、服役和奖惩连接起来。国家可以借此获得更稳定的赋税和兵源，农户也可能因生产"
        "或军功得到利益；但政策目标优先服务富国强兵，并不等同于每个家庭都变得富裕自由。徭役、征发、战争风险和对其他"
        "生计的限制会落到具体家庭。关卡中的“粮食供给”和“军事准备”因此不是越高越好而无需代价，它们必须同“社会"
        "压力”一起阅读。数值只是帮助学生观察权衡的现代课堂模型。"
    ),
    (
        "县与基层行政使中央命令能更直接抵达地方，也让官吏承担登记、征收、司法和执行责任。传世记载常把合并小乡聚为县"
        "列为改革内容，后来的秦简则展示秦在战国晚期和统一前后已经形成十分细密的行政法律实践。两类材料可以相互照明，"
        "却不能倒置年代：睡虎地秦简比商鞅最初变法晚一百多年，证明的是后来秦制怎样运行和发展，不是商鞅本人写下每一条"
        "简文。制度有延续，也会在延续中增补和变化。"
    ),
    (
        "户籍、什伍组织与连带责任提高了国家识别、征发和追责能力，也可能让邻里相互监督。传世叙事把“不告奸者”与"
        "“告奸者”的不同处置写得尖锐，后世因此常用“连坐”概括制度压力。课堂不复演残酷刑罚，也不把所有秦人生活简化"
        "成恐惧；我们只把清楚的制度问题摆出来：当执行效率依赖相互告发和连带惩处时，公共秩序可能增强，私人信任、家庭"
        "安全与个体责任边界也可能受损。"
    ),
    (
        "商鞅方升提供了罕见的同时代实物窗口。上海博物馆所藏铜量器带有秦孝公十八年、大良造鞅和容量标准相关铭文，年代"
        "约为公元前344年。器物的形制、容量与铭文可以直接支持秦国推行标准量器、国家权力介入计量的判断；后来又加刻秦始"
        "皇时期诏文，还显示标准被长期沿用。它不能证明《史记》中每段故事，也不能单独概括全部变法，却比后世人物对白更"
        "接近改革时代，是本课证据强度最高的材料之一。"
    ),
    (
        "睡虎地秦墓竹简于湖北云梦出土，内容包括秦律、行政文书以及官吏工作相关材料。考古机构把其书写年代放在战国晚期"
        "和秦始皇时期，许多内容处于公元前221年统一前后。它们让我们看见市场、农业、徭役、官吏与法律如何进入日常治理，"
        "也提醒制度不是一句“依法治国”便能概括。由于简文年代晚于公元前四世纪中叶，本课只用它们观察成熟秦制和制度"
        "延续，不把任何一支简直接署名给商鞅。"
    ),
    (
        "《商君书》保留了重农战、强国家、明法令等思想，是理解商鞅学派和战国政治思想的重要材料；现代研究同时指出，这"
        "部书是经历增补、编辑和传抄的累积文本，各篇年代与作者不能一概而论。《韩非子·定法》则是更晚的战国思想家对"
        "商鞅“法”与申不害“术”的评价。两者能说明思想传统怎样解释改革，却不等于商鞅本人逐字说过现存全部句子。角色"
        "回答若引用这些材料，必须同时显示文本层次和不确定性。"
    ),
    (
        "土地制度尤其容易被一句“废井田、土地私有”讲得过度确定。传世文献确有开阡陌、改变田制等说法，学界也从国家"
        "授田、田界和赋役关系讨论其意义；但战国土地关系的区域差异、实施过程和现代“私有”概念之间仍有距离。本课保留"
        "“推动土地与赋役制度变化”的谨慎表述，不把它套进单线社会形态公式，也不要求学生用一条口号解释所有农户命运。"
        "能说清材料支持到哪里，比背下更响亮的结论重要。"
    ),
    (
        "秦孝公去世后，商鞅遭到追捕并被处死，而其制度并未随个人结局全部废止，这是《史记》叙事中最有张力的一部分。"
        "它提醒我们区分改革者、支持联盟和制度本身：君主支持可以打开改革窗口，官僚与地方执行决定制度能否落地，受益者"
        "和受损者会形成新的力量关系，继任者还会选择保留、调整或放弃。把商鞅之死只讲成“坏人报复好人”，会遮蔽改革"
        "为何既能延续又积累强制性代价。"
    ),
    (
        "进入六回合抉择后，你担任秦国改革议事记录者，依次面对公开法令、耕战激励、计量与县政、执行节奏和阶段评估。"
        "国家能力、军事准备、粮食供给、制度信用、社会压力与旧贵族阻力会共同变化。严厉推进可能迅速形成“强国但高压”"
        "结局，反复协商却不建立执行能力也可能使改革失去窗口；平衡成功必须同时留下清楚规则、可执行机构和可承受代价。"
        "这些路径用于观察制度关系，不是在模拟真实秦国的统计数据。"
    ),
    (
        "召见商鞅、秦孝公、旧贵族、农耕家庭、军功士卒或县廷吏员时，回答只能依据当前发布的证据片段，并标明“角色化"
        "教学表达，不是史料原话”。依据不足时必须停下，不能用模型常识补写。史官卷宗最终保存六次选择、变量轨迹、触发"
        "事件、关键代价、历史解释和来源，再导入知识画板。复盘要回答的不只是秦为何变强，还包括制度怎样取得信用、国家"
        "能力由谁承担，以及我们为什么对不同材料保持不同程度的确信。"
    ),
]


FACTS = {
    "warring_context": "【历史背景】商鞅变法发生在战国兼并、农业与国家组织持续变化的环境中，秦的转型不能简化为一次孤立事件。",
    "xiaogong_support": "【传世文献】秦孝公求贤并支持卫鞅改革是后世叙事的关键框架，具体对话不是同时代逐字记录。",
    "reform_chronology": "【年代边界】教学通常以约公元前356年、前350年前后概括两阶段改革；措施实际推行、修订与延续并非同日完成。",
    "shiji_later": "【传世文献】《史记·商君列传》成书于西汉，晚于商鞅变法二百多年，保存重要传统但不能作为宫廷现场记录。",
    "moving_wood": "【传世叙事】徙木立信用于说明兑现承诺与制度信用，目前没有出土材料可逐项核验木头、赏金和现场对白。",
    "law_publicity": "【文本与教学解释】公开规则、明确责任和兑现赏罚有助于制度取得信用；现存论述来自层次不同的传世材料。",
    "military_merit": "【制度解释】军功爵削弱世袭贵族特权并提供新的身份通道，同时把社会上升与战争绩效紧密连接。",
    "agriculture_war": "【制度解释】奖励耕战服务粮食、兵源与国家动员，不能直接推出每个农户都因此富裕或自由。",
    "county_admin": "【制度解释】县级治理与地方官吏增强中央命令、征收和司法执行能力，具体形成过程需要传世与出土材料互证。",
    "collective_responsibility": "【制度代价】户籍、什伍和连带责任提高识别与追责能力，也可能扩大邻里监督、惩罚外溢和家庭压力。",
    "fangsheng_direct": "【同时代实物】商鞅方升的公元前344年铭文与标准容量直接支持秦国推行统一量器，不能单独证明全部变法故事。",
    "land_boundary": "【解释边界】开阡陌与田制变化见于传世叙述；用现代‘完全土地私有’概括战国复杂土地关系会过度简化。",
    "shangjunshu_layers": "【文本边界】《商君书》是具有不同篇章年代与编纂层次的累积文本，不能把现存每句话都直接署名商鞅。",
    "hanfeizi_later": "【传世文献】《韩非子·定法》是较晚战国思想家对商鞅之法的评价，不是变法当时的行政档案。",
    "slips_date": "【出土文献】睡虎地秦简主要写于战国晚期与秦始皇时期，晚于商鞅最初变法一百多年。",
    "slips_scope": "【出土文献】秦简可观察成熟秦制的法律、行政与日常执行，不能反推每条简文均由商鞅制定。",
    "multi_causal_strength": "【历史解释】商鞅改革是秦国富国强兵和统一进程的重要基础之一，秦的长期强盛仍是多代、多因素共同结果。",
    "institutional_cost": "【教学解释】评价改革要同时观察国家能力、制度信用、战争动员、社会压力与不同群体承担的代价。",
    "modern_law_boundary": "【概念边界】战国秦的法令、赏罚与现代宪政法治并非同一概念，不宜直接用今天的‘法律面前人人平等’替换历史语境。",
}


def _course_sources() -> list[content.SourceRef]:
    return [
        content.SourceRef(title="义务教育历史课程标准（2022年版）", source="中华人民共和国教育部", url_or_path="https://www.moe.gov.cn/srcsite/A26/s8001/202204/t20220420_619921.html", citation_note="用于七年级历史核心素养、证据意识与适龄表达；只保存自写摘要。", reliability="reviewed"),
        content.SourceRef(title="义务教育教科书·中国历史七年级上册目录与课程位置", source="人民教育出版社", url_or_path="https://www.pep.com.cn/products/jc/czjks/201802/t20180227_1922743.shtml", citation_note="用于确认战国社会变革的学段位置，不复制教材正文。", reliability="reviewed"),
        content.SourceRef(title="《史记·商君列传》", source="司马迁；中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/shiji/shang-jun-lie-zhuan/zhs", citation_note="西汉成书的商鞅生平与改革叙事；具体对白和情节按后世记载呈现。", reliability="reviewed"),
        content.SourceRef(title="《韩非子·定法》", source="中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/hanfeizi/ding-fa/zh", citation_note="较晚战国时期对商鞅之法与申不害之术的思想评价。", reliability="reviewed"),
        content.SourceRef(title="《商君书》", source="中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/shang-jun-shu/zh", citation_note="理解商鞅学派与法、农战思想的重要传世文本；篇章年代和作者需分层。", reliability="disputed"),
        content.SourceRef(title="Dating a Pre-Imperial Text: The Case Study of the Book of Lord Shang", source="Yuri Pines / Early China / Cambridge University Press", url_or_path="https://www.cambridge.org/core/journals/early-china/article/dating-a-preimperial-text-the-case-study-of-the-book-of-lord-shang/199B57467F51A62EBD492DE47DA3360A", citation_note="用于《商君书》累积成书、篇章分层和作者边界。", reliability="reviewed"),
        content.SourceRef(title="商鞅方升——每月一珍", source="上海博物馆", url_or_path="https://www.shanghaimuseum.net/mu/show/202411/4335e32d-3cce-4602-955b-17ed7e0b9e59/", citation_note="用于公元前344年标准量器的器形、容量、铭文与后刻诏文。", reliability="reviewed"),
        content.SourceRef(title="云梦睡虎地秦简", source="湖北省博物馆", url_or_path="https://www.hbww.org.cn/zgzb/p/6912.html", citation_note="用于出土地点、法律文献范围与统一前后年代概览。", reliability="reviewed"),
        content.SourceRef(title="湖北简牍地理，一窥湖北简牍之风采", source="湖北省文物考古研究院", url_or_path="https://www.hbww.org.cn/yjy_mtbd/p/8892.html", citation_note="用于睡虎地秦简战国晚期至秦始皇时期的书写年代和内容边界。", reliability="reviewed"),
        content.SourceRef(title="秦文化的历史特点与当代价值", source="全国哲学社会科学工作办公室", url_or_path="https://www.nopss.gov.cn/n1/2022/0706/c219544-32467522.html", citation_note="用于县制、迁都、耕战与秦长期国家建设的现代综合解释。", reliability="reviewed"),
    ]


def build_shangyang_course_draft() -> content.LessonContentPackage:
    disclaimer = "角色化教学表达，不是史料原话。"
    return content.LessonContentPackage(
        lesson_id=LESSON_ID,
        course_id=COURSE_ID,
        title="商鞅变法：富国强兵与制度代价",
        unit="富国强兵与制度代价",
        course_title="先秦·早期国家与社会变革",
        era="战国中期，约公元前4世纪",
        era_id="preqin",
        section="通史",
        lesson_no="1.3",
        duration="40:00",
        abstract="从后世传世叙事、同时代量器铭文和较晚秦简出发，在六回合制度改革中比较国家能力、制度信用与社会代价。",
        body=BODY,
        keywords=[
            content.KeywordCard(word="商鞅变法", pinyin="shāng yāng biàn fǎ", gloss="战国中期秦孝公支持下持续推进的制度改革，具体措施与年代须按证据分层。"),
            content.KeywordCard(word="徙木立信", pinyin="xǐ mù lì xìn", gloss="《史记》所载兑现赏金以建立制度信用的故事，属于后世传世叙事。"),
            content.KeywordCard(word="军功爵", pinyin="jūn gōng jué", gloss="依据军功授予爵位和利益的制度，既改变身份通道也加强战争动员。"),
            content.KeywordCard(word="奖励耕战", pinyin="jiǎng lì gēng zhàn", gloss="以农业生产和军功服务粮食、兵源与国家能力的政策取向。"),
            content.KeywordCard(word="县制", pinyin="xiàn zhì", gloss="通过地方官署、登记、征收和司法把中央命令落实到基层的治理方式。"),
            content.KeywordCard(word="什伍与连带责任", pinyin="shí wǔ yǔ lián dài zé rèn", gloss="基层编组和相互追责机制；提高执行力，也可能扩大监督与惩罚。"),
            content.KeywordCard(word="商鞅方升", pinyin="shāng yāng fāng shēng", gloss="带公元前344年铭文的秦国标准铜量器，是度量衡改革的直接实物证据。"),
            content.KeywordCard(word="证据年代", pinyin="zhèng jù nián dài", gloss="先判断材料何时形成，再决定它能否直接说明改革当时。"),
        ],
        people=[
            content.PersonCard(name="商鞅", role="传世叙事中的改革主持者", summary="卫鞅入秦后在秦孝公支持下推动制度调整，后受封商地，史称商鞅。", persona=f"强调规则清楚、赏罚兑现与国家执行能力，同时承认现存对白来自后世材料。{disclaimer}", boundaries=["只依据本课已发布的《史记》《商君书》、方升与秦简片段回答。", "不得把《商君书》全部句子自称为本人原话。", "不得知道自己身后一百多年形成的睡虎地秦简内容。"]),
            content.PersonCard(name="秦孝公", role="传世叙事中的改革支持者", summary="为改变秦国处境而求贤并提供政治支持，是改革窗口的重要角色。", persona=f"从国家竞争、支持联盟和长期执行角度追问改革。{disclaimer}", boundaries=["求贤、辩论与任用依据后世传世叙事有限表达。", "不虚构密诏、私人情感或逐字宫廷对话。", "不能把秦后来统一预言为必然结果。"]),
            content.PersonCard(name="旧贵族代表", role="受世袭特权调整影响的合成人群", summary="集中呈现旧身份秩序、政治参与和利益受损者对改革的异议。", persona=f"追问改革程序、权力集中和旧秩序被改变的风险。{disclaimer}", boundaries=["这是课堂合成人群，不假冒甘龙、杜挚等某位人物的原话。", "不把所有贵族写成同一种立场。", "可以批评改革，但不得补写阴谋和暴力现场。"]),
            content.PersonCard(name="农耕家庭代表", role="承担生产、赋役与家庭风险的合成人群", summary="观察奖励耕战、户籍、征发和尺度统一怎样进入普通家庭。", persona=f"从收成、赋役、服兵役和家庭安全追问政策代价。{disclaimer}", boundaries=["不虚构某户的精确田亩、税额和伤亡。", "不能声称代表所有秦国农户。", "关卡数值是教学模型，不是出土账册。"]),
            content.PersonCard(name="军功士卒", role="通过服役争取身份机会的合成人群", summary="展示军功爵可能带来的上升通道与战争风险。", persona=f"同时说明获得爵位的希望、军纪约束和战场代价。{disclaimer}", boundaries=["不是某场战役具名士卒的自述。", "不提供未经课程片段支持的斩首数、爵级和赏田。", "不把军功通道等同于现代平等。"]),
            content.PersonCard(name="县廷吏员", role="执行登记、征收与司法的合成基层官吏", summary="连接中央法令与地方日常，展示执行能力和行政负担。", persona=f"要求规则可登记、可核验、可执行，也说明追责压力。{disclaimer}", boundaries=["依据较晚秦简理解成熟秦制，不自称直接奉行商鞅手令。", "不把秦简每条规定倒推到公元前四世纪中叶。", "遇到超出证据库的具体案件回答‘依据不足’。"]),
        ],
        map_points=[
            content.MapPoint(label="栎阳", region="今陕西西安阎良附近", lat=34.66, lng=109.23, kind="reform_context", note="秦孝公前期都城与早期改革叙事的重要空间；精确宫廷场景来自后世文献，地图不复原路线。"),
            content.MapPoint(label="咸阳", region="今陕西咸阳一带", lat=34.35, lng=108.71, kind="capital_region", note="传世材料把迁都与后续制度调整联系于此；城市范围与现代坐标不能简单重合。"),
            content.MapPoint(label="商於地区", region="今陕西商洛至河南西部相关区域", lat=33.87, lng=109.94, kind="memory_region", note="后世叙事以受封商地解释‘商君/商鞅’称号；不据此绘制个人活动精确路线。"),
            content.MapPoint(label="云梦睡虎地", region="湖北省孝感市云梦县", lat=31.02, lng=113.75, kind="excavated_text_site", note="1975年出土秦简；材料主要晚于商鞅最初变法，用于观察成熟秦制而非原令。"),
        ],
        source_refs=_course_sources(),
        facts=list(FACTS.values()),
        qa_points=[
            "《史记·商君列传》为什么重要，又为什么不能视为变法现场记录？",
            "徙木立信能够说明制度信用的什么问题，哪些细节仍不可核验？",
            "军功爵怎样同时带来身份机会和战争动员压力？",
            "商鞅方升能够直接证明什么，不能替其他改革措施证明什么？",
            "为什么睡虎地秦简不能直接称为商鞅亲自制定的法令？",
            "《商君书》的篇章层次怎样影响我们使用其中句子？",
            "用‘废井田、土地私有’一句话概括改革会遗漏哪些边界？",
            "秦国后来强盛为什么不能只归因于商鞅一个人或一次变法？",
        ],
        level_goals=[
            "能按形成年代区分《史记》《商君书》、商鞅方升和睡虎地秦简的证据能力。",
            "能说明军功、耕战、县政、户籍和度量衡之间怎样共同增强国家能力。",
            "能在六回合改革中同时追踪国家能力、制度信用、旧贵族阻力和社会压力。",
            "能用选择—变化—代价—来源完成史官卷宗，并写出多因解释和概念边界。",
        ],
        saga_material=content.MaterialPlaceholder(title="踏勘：三类材料中的商鞅变法", objective="在地图、器物和短片中辨认后世叙事、同时代实物与较晚出土文献。", notes="建议9分钟；每组材料先写可证结论，再写不可越过的年代边界。", assets=[SHANGYANG_PRESENTATION_ID]),
        sandbox_material=content.MaterialPlaceholder(title="抉择：六回合制度改革议事", objective="在公开规则、耕战激励、标准尺度、县政执行与社会承受之间形成可复盘方案。", notes="固定行动断网可用；变量不是秦国真实统计，结局不是对历史人物的道德裁决。", assets=[SHANGYANG_SCENARIO_ID]),
        seed_canvas=[
            content.SeedCanvasNode(id="evidence-chronology", label="证据年代", note="变法当时—战国晚期—西汉—现代研究分层"),
            content.SeedCanvasNode(id="state-capacity", label="国家能力", note="计量、户籍、县政、粮食与兵源如何连接"),
            content.SeedCanvasNode(id="institutional-credit", label="制度信用", note="公开规则与兑现赏罚为何影响执行"),
            content.SeedCanvasNode(id="mobility-and-war", label="身份机会与战争", note="军功爵的机会和军事化代价并存"),
            content.SeedCanvasNode(id="pressure-and-resistance", label="压力与阻力", note="旧特权、家庭负担和基层追责不可消失"),
            content.SeedCanvasNode(id="multi-causal-explanation", label="多因解释", note="改革是重要基础之一，不是统一的唯一原因"),
        ],
        teacher_notes=(
            "正式旗舰课。课堂总时长40分钟：踏勘9、抉择14、召见7、卷宗10。"
            "必须把《史记》标作西汉后世记载，把睡虎地秦简标作较晚成熟秦制；不得将《商君书》全部署名商鞅。"
            "正文与片段均为项目自写摘要，仅保留必要出处，不复制教材或研究文献章节。"
        ),
    )


def _evidence_sources() -> tuple[EvidenceSourceV1, ...]:
    rights = "仅保存项目自写摘要和必要短引，课堂展示时保留出处；不复制受版权保护的整章内容。"
    values = [
        EvidenceSourceV1(source_id="src-cambridge-shangjunshu", title="Dating a Pre-Imperial Text: The Case Study of the Book of Lord Shang", kind="research", author_or_institution="Yuri Pines", publisher="Early China / Cambridge University Press", published_year=2016, url_or_path="https://www.cambridge.org/core/journals/early-china/article/dating-a-preimperial-text-the-case-study-of-the-book-of-lord-shang/199B57467F51A62EBD492DE47DA3360A", locator="Textual history, dating criteria and conclusion", citation_note="用于累积成书与篇章分层边界。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-hanfeizi-dingfa", title="《韩非子·定法》", kind="primary_source", author_or_institution="传世文献；中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/hanfeizi/ding-fa/zh", locator="商鞅之法与申不害之术相关段落", citation_note="较晚战国思想评价，不是改革行政档案。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-hb-archaeology-slips", title="湖北简牍地理，一窥湖北简牍之风采", kind="archaeology", author_or_institution="湖北省文物考古研究院", publisher="湖北省文物考古研究院", published_year=2023, url_or_path="https://www.hbww.org.cn/yjy_mtbd/p/8892.html", locator="睡虎地秦简年代与内容概览", citation_note="用于战国晚期与秦始皇时期的书写年代边界。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-hubei-museum-slips", title="云梦睡虎地秦简", kind="museum", author_or_institution="湖北省博物馆", publisher="湖北省博物馆", url_or_path="https://www.hbww.org.cn/zgzb/p/6912.html", locator="出土信息与秦律范围", citation_note="用于出土地点和统一前后法律文献概览。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-moe-2022", title="义务教育历史课程标准（2022年版）", kind="curriculum", author_or_institution="中华人民共和国教育部", publisher="人民教育出版社", published_year=2022, url_or_path="https://www.moe.gov.cn/srcsite/A26/s8001/202204/t20220420_619921.html", locator="核心素养与学业质量要求", citation_note="用于适龄目标和有依据的历史解释。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-nopss-qin", title="秦文化的历史特点与当代价值", kind="research", author_or_institution="彭卫等 / 中国社会科学院", publisher="全国哲学社会科学工作办公室", published_year=2022, url_or_path="https://www.nopss.gov.cn/n1/2022/0706/c219544-32467522.html", locator="商鞅变法、县制、迁都与耕战部分", citation_note="现代综合解释；不代替原始材料。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-pep-seven-history", title="义务教育教科书·中国历史七年级上册目录与课程位置", kind="textbook", author_or_institution="人民教育出版社", publisher="人民教育出版社", url_or_path="https://www.pep.com.cn/products/jc/czjks/201802/t20180227_1922743.shtml", locator="七年级上册战国社会变革相关单元", citation_note="只用于学段定位，不复制教材正文。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-shanghaimuseum-fangsheng", title="商鞅方升——每月一珍", kind="museum", author_or_institution="上海博物馆", publisher="上海博物馆", published_year=2024, url_or_path="https://www.shanghaimuseum.net/mu/show/202411/4335e32d-3cce-4602-955b-17ed7e0b9e59/", locator="器形、容量、两组铭文与年代", citation_note="同时代标准量器的直接实物资料。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-shangjunshu", title="《商君书》", kind="primary_source", author_or_institution="传世文献；中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/shang-jun-shu/zh", locator="农战、法令、国家能力相关篇章", citation_note="累积文本，具体篇章须分别判断年代和作者。", reliability="disputed", rights_note=rights),
        EvidenceSourceV1(source_id="src-shiji-shangjun", title="《史记·商君列传》", kind="primary_source", author_or_institution="司马迁；中国哲学书电子化计划底本索引", publisher="传世文献", published_year=-90, url_or_path="https://ctext.org/shiji/shang-jun-lie-zhuan/zhs", locator="入秦、变法、徙木、施行与结局叙事", citation_note="西汉后世叙事，不作为逐字现场记录。", reliability="reviewed", rights_note=rights),
    ]
    return tuple(sorted(values, key=lambda item: item.source_id))


def _lookup_runtime_ids(package: CoursePackageV1):
    fact_ids = {item.statement: item.fact_id for item in package.facts}
    person_ids = {item.name: item.person_id for item in package.people}
    return fact_ids, person_ids


def build_shangyang_evidence_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> evidence_workflow.EvidenceCorpusDraftV1:
    package = course_package_from_legacy(course_draft or build_shangyang_course_draft())
    fact_ids, person_ids = _lookup_runtime_ids(package)

    def passage(
        passage_id: str,
        source_id: str,
        title: str,
        text: str,
        summary: str,
        fact_keys: tuple[str, ...],
        *,
        people: tuple[str, ...] = (),
        keywords: tuple[str, ...] = (),
        evidence_kind: str,
        certainty: str,
        chronology_note: str,
        teaching_note: str = "",
    ) -> EvidencePassageV1:
        return EvidencePassageV1(
            passage_id=passage_id,
            source_id=source_id,
            title=title,
            text=text,
            summary=summary,
            fact_ids=tuple(sorted(fact_ids[FACTS[key]] for key in fact_keys)),
            person_ids=tuple(sorted(person_ids[name] for name in people)),
            keywords=tuple(sorted(set(keywords))),
            evidence_kind=evidence_kind,
            certainty=certainty,
            chronology_note=chronology_note,
            teaching_note=teaching_note,
        )

    passages = [
        passage("shangyang-p001", "src-moe-2022", "课程目标：用证据解释社会变革", "本课依据义务教育历史课程核心素养取向，让学生在时空背景中比较材料，解释制度变革的原因、作用和代价。", "历史解释必须写明材料、推论与边界。", ("institutional_cost",), keywords=("历史解释", "证据边界"), evidence_kind="curriculum_goal", certainty="consensus", chronology_note="2022年现代课程标准，用于教学目标而非古代事实。"),
        passage("shangyang-p002", "src-pep-seven-history", "七年级内容位置", "七年级上册把战国时期的社会变革置于学生初次系统学习中国古代史的阶段，本课据此控制概念和阅读难度。", "课程定位于七年级战国变革主题，不复制教材章节。", ("warring_context",), keywords=("七年级", "战国"), evidence_kind="curriculum_goal", certainty="consensus", chronology_note="现代教材目录信息。"),
        passage("shangyang-p003", "src-shiji-shangjun", "卫鞅入秦与孝公求变", "《史记·商君列传》把秦孝公求贤、卫鞅入秦和宫廷论辩编为改革开端，呈现后世理解的政治窗口。", "支持改革关系和后世叙事框架，不提供逐字录音。", ("xiaogong_support", "shiji_later"), people=("商鞅", "秦孝公"), keywords=("求贤", "改革窗口"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="《史记》成书于西汉，晚于事件二百多年。"),
        passage("shangyang-p004", "src-shiji-shangjun", "两阶段改革的教学年代", "传世叙事把孝公时期多项改革按先后组织，现代教学常以约公元前356年和前350年前后概括两阶段。", "年代用于排序，不等于全部措施同日生效。", ("reform_chronology",), keywords=("公元前356年", "公元前350年"), evidence_kind="boundary_note", certainty="interpretation", chronology_note="现代教学约数建立于传世年代框架。"),
        passage("shangyang-p005", "src-shiji-shangjun", "徙木立信的故事", "《史记》记载法令将行时以徙木和兑现重赏取得信任，后世以此说明改革者重视信赏。", "故事能启发制度信用问题，现场细节不能逐项核验。", ("moving_wood", "law_publicity"), people=("商鞅",), keywords=("徙木立信", "制度信用"), evidence_kind="transmitted_text", certainty="legend", chronology_note="西汉文本保存的战国改革故事。"),
        passage("shangyang-p006", "src-shiji-shangjun", "军功与旧特权", "《史记》把依军功授爵、宗室无军功不得列入属籍等内容列为改革措施，呈现身份秩序的重大调整。", "军功提供新通道，也把身份和战争绑定。", ("military_merit",), people=("旧贵族代表", "军功士卒"), keywords=("军功爵", "世袭特权"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="西汉对战国制度传统的整理。"),
        passage("shangyang-p007", "src-shiji-shangjun", "耕织激励与家庭负担", "传世叙事以耕织成绩、粮帛产出和服役奖惩说明改革如何把家庭生产纳入国家目标。", "奖励和压力可能同时进入农耕家庭。", ("agriculture_war", "institutional_cost"), people=("农耕家庭代表",), keywords=("奖励耕战", "赋役"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="后世文本对战国制度的概括。"),
        passage("shangyang-p008", "src-shiji-shangjun", "什伍与相互追责", "《史记》相关段落把户籍编组、告发和连带处置写入变法叙事，反映后世所理解的严密基层控制。", "执行能力增强不取消惩罚外溢的代价。", ("collective_responsibility",), people=("农耕家庭代表", "县廷吏员"), keywords=("什伍", "连带责任"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="西汉传世叙事，具体执行须与较晚秦简互证。"),
        passage("shangyang-p009", "src-shiji-shangjun", "县政与地方治理", "传世叙事把合并小乡聚、设置县及令丞等官吏同改革联系起来，展示命令直接抵达地方的方向。", "县政强化地方执行，形成过程不是单日完成。", ("county_admin", "reform_chronology"), people=("县廷吏员",), keywords=("县制", "地方官吏"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="后世对公元前四世纪制度变化的记述。"),
        passage("shangyang-p010", "src-shiji-shangjun", "开阡陌的解释边界", "《史记》以开阡陌封疆等语言描述田制调整，现代叙述常进一步概括土地制度变化。", "不可直接等同于现代完整私有产权。", ("land_boundary",), people=("农耕家庭代表",), keywords=("开阡陌", "土地制度"), evidence_kind="boundary_note", certainty="disputed", chronology_note="传世记载及现代解释之间存在概念距离。"),
        passage("shangyang-p011", "src-shiji-shangjun", "商鞅之死与制度延续", "《史记》叙述孝公死后商鞅遭追捕和处死，同时呈现秦国继续沿用改革制度的历史张力。", "人物结局、支持联盟和制度存续需要分开评价。", ("shiji_later", "multi_causal_strength"), people=("商鞅", "秦孝公", "旧贵族代表"), keywords=("制度延续",), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="西汉史家对战国人物和制度的后世叙事。"),
        passage("shangyang-p012", "src-shanghaimuseum-fangsheng", "公元前344年的商鞅方升", "上海博物馆藏商鞅方升带秦孝公十八年与大良造鞅相关铭文，标准容量约202毫升。", "铭文与器物直接支持秦推行标准量器。", ("fangsheng_direct", "reform_chronology"), people=("商鞅",), keywords=("商鞅方升", "度量衡"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="器物第一组铭文明确对应公元前344年。"),
        passage("shangyang-p013", "src-shanghaimuseum-fangsheng", "尺度进入赋税与交换", "标准容量让粮食计量、交换和赋税拥有共同参照，显示国家权力能够介入日常尺度。", "统一尺度连接行政能力，但不能证明全部改革。", ("fangsheng_direct", "institutional_cost"), people=("农耕家庭代表", "县廷吏员"), keywords=("计量", "赋税"), evidence_kind="archaeological_evidence", certainty="interpretation", chronology_note="由战国量器形制、铭文和用途形成的历史解释。"),
        passage("shangyang-p014", "src-shanghaimuseum-fangsheng", "两次铭文与制度沿用", "方升后来又加刻秦始皇时期诏文，显示同一标准器跨越战国秦与统一时期被继续使用。", "器物可以观察制度延续和再次推广。", ("fangsheng_direct", "multi_causal_strength"), keywords=("秦始皇诏", "制度延续"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="第一组铭文为公元前344年，后刻文字晚一百多年。"),
        passage("shangyang-p015", "src-hubei-museum-slips", "睡虎地秦简的出土与内容", "1975年湖北云梦睡虎地秦墓出土大量秦简，其中包含秦统一前后法律文献，是系统观察秦律的重要材料。", "出土简文让成熟秦法可读，但不是商鞅原令合集。", ("slips_scope",), people=("县廷吏员",), keywords=("睡虎地秦简", "秦律"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="材料主要处于战国晚期和秦统一前后。"),
        passage("shangyang-p016", "src-hb-archaeology-slips", "秦简晚于最初变法", "湖北省文物考古研究院说明睡虎地秦简写于战国晚期及秦始皇时期，距离公元前四世纪中叶改革已有百余年。", "年代距离禁止把每条简文直接署名商鞅。", ("slips_date", "slips_scope"), people=("商鞅", "县廷吏员"), keywords=("年代边界",), evidence_kind="boundary_note", certainty="consensus", chronology_note="战国晚期至秦始皇时期，晚于约前356/350年。"),
        passage("shangyang-p017", "src-hb-archaeology-slips", "法律与行政进入日常", "睡虎地材料涵盖法律制度、行政文书和官吏相关内容，显示成熟秦制深入农业、市场、徭役和地方执行。", "可观察制度运行，不等于原初设计从未变化。", ("county_admin", "slips_scope"), people=("县廷吏员", "农耕家庭代表"), keywords=("行政", "官吏"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="较晚秦制的直接文字材料。"),
        passage("shangyang-p018", "src-shangjunshu", "《商君书》的农战思想", "《商君书》多篇强调农业、战争、赏罚和国家力量的连接，是理解商鞅学派政治思想的重要材料。", "思想主题相关，作者和篇章年代须分别判断。", ("agriculture_war", "shangjunshu_layers"), people=("商鞅",), keywords=("农战", "商鞅学派"), evidence_kind="transmitted_text", certainty="disputed", chronology_note="战国至后续传抄形成的累积文本。"),
        passage("shangyang-p019", "src-shangjunshu", "明法与官吏责任", "《商君书》相关篇章讨论法令公开、官吏掌握规则和追责，展示战国国家思想对可执行制度的重视。", "可讨论制度公开，不直接套用现代法治概念。", ("law_publicity", "modern_law_boundary", "shangjunshu_layers"), people=("县廷吏员",), keywords=("明法", "官吏"), evidence_kind="transmitted_text", certainty="disputed", chronology_note="具体篇章年代和作者存在研究讨论。"),
        passage("shangyang-p020", "src-cambridge-shangjunshu", "累积文本而非单一作者手稿", "Yuri Pines 的研究把《商君书》视为可分辨不同暂时层次、经增补和传抄演变的文本。", "不得把整部书逐句当成商鞅自述。", ("shangjunshu_layers",), people=("商鞅",), keywords=("累积文本", "作者边界"), evidence_kind="scholarly_interpretation", certainty="consensus", chronology_note="2016年现代文本史研究。"),
        passage("shangyang-p021", "src-cambridge-shangjunshu", "分篇判断年代", "现代研究不再把整部《商君书》强行定为一个日期，而是比较词汇、制度和思想线索判断各篇层次。", "材料年代需要逐篇判断，不能整书一刀切。", ("shangjunshu_layers",), keywords=("文本分层", "年代"), evidence_kind="scholarly_interpretation", certainty="interpretation", chronology_note="现代文献学方法说明。"),
        passage("shangyang-p022", "src-hanfeizi-dingfa", "《韩非子》对商鞅之法的评价", "《韩非子·定法》从较晚战国思想语境评说商鞅重法、申不害重术及其得失，反映战国末期的理论总结。", "这是后期评价，不是孝公朝行政档案。", ("hanfeizi_later", "law_publicity"), people=("商鞅",), keywords=("法", "术"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="较晚战国时期文本，晚于商鞅。"),
        passage("shangyang-p023", "src-nopss-qin", "县制、迁都与国家建设", "现代综合研究把县制、迁都咸阳、耕战政策和行政发展放入秦长期国家建设过程。", "改革措施需要理解为相互连接且逐步推进。", ("county_admin", "agriculture_war", "reform_chronology"), keywords=("咸阳", "国家建设"), evidence_kind="scholarly_interpretation", certainty="interpretation", chronology_note="现代研究对战国秦制度变迁的综合。"),
        passage("shangyang-p024", "src-nopss-qin", "富国强兵的多因解释", "秦的强盛还涉及地理、人口资源、历代政策、官僚执行、军事行动与统一过程，商鞅改革是重要基础而非唯一变量。", "人物中心叙事不能取代多代历史因果。", ("multi_causal_strength", "warring_context"), people=("商鞅", "秦孝公"), keywords=("富国强兵", "多因解释"), evidence_kind="scholarly_interpretation", certainty="consensus", chronology_note="现代历史综合解释。"),
        passage("shangyang-p025", "src-shiji-shangjun", "旧特权与改革阻力", "《史记》以廷议、太子犯法及孝公死后追究等情节表现改革触动旧利益和支持联盟变化。", "可研究阻力主题，不虚构所有贵族立场。", ("xiaogong_support", "military_merit", "shiji_later"), people=("旧贵族代表", "秦孝公", "商鞅"), keywords=("旧贵族", "改革阻力"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="西汉后世叙事。"),
        passage("shangyang-p026", "src-moe-2022", "现代法治概念不可直接倒置", "战国秦的法令服务君主国家、赏罚和动员；课堂比较规则公开与执行时，仍须区别于现代权利保障和宪政法治。", "相似词语不代表制度含义相同。", ("modern_law_boundary", "law_publicity"), keywords=("概念边界", "法治"), evidence_kind="boundary_note", certainty="consensus", chronology_note="现代概念史与课堂边界。"),
        passage("shangyang-p027", "src-moe-2022", "制度评价同时记录代价", "六项课堂变量让国家能力、军事准备、粮食供给、制度信用、社会压力和旧贵族阻力同时可见。", "变量训练权衡，不是秦国统计表。", ("institutional_cost", "multi_causal_strength"), keywords=("教学模型", "制度代价"), evidence_kind="teaching_explanation", certainty="interpretation", chronology_note="V0.10现代课堂设计。"),
        passage("shangyang-p028", "src-shiji-shangjun", "合成人群补回制度承受者", "传世人物叙事多集中于君主、改革者和反对者，课堂加入农耕家庭、士卒与吏员，观察制度如何进入日常。", "群体角色是教学建模，不是假造具名自述。", ("institutional_cost", "agriculture_war", "county_admin"), people=("农耕家庭代表", "军功士卒", "县廷吏员"), keywords=("普通人", "制度执行"), evidence_kind="teaching_explanation", certainty="interpretation", chronology_note="依据制度主题形成的现代课堂表达。"),
        passage("shangyang-p029", "src-shanghaimuseum-fangsheng", "不同材料具有不同证明力", "方升可直接证明标准量器与铭文，秦简可直接观察较晚法律行政，《史记》则直接证明汉代史家怎样组织改革叙事。", "材料真实不等于能证明同一件事。", ("fangsheng_direct", "slips_date", "shiji_later"), keywords=("证据强度", "年代"), evidence_kind="boundary_note", certainty="consensus", chronology_note="跨材料方法说明。"),
        passage("shangyang-p030", "src-moe-2022", "卷宗保存选择、代价与来源", "史官卷宗要求保存六次选择、状态轨迹、事件、主要代价、历史解释和来源，再以多因解释导入知识画板。", "学习成果记录推理过程而不只显示胜负。", ("institutional_cost", "multi_causal_strength"), keywords=("史官卷宗", "复盘"), evidence_kind="teaching_explanation", certainty="consensus", chronology_note="V0.10现代课堂评价设计。"),
    ]
    return evidence_workflow.EvidenceCorpusDraftV1(
        corpus_id=SHANGYANG_CORPUS_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="L103 商鞅变法正式证据库",
        scope_note=(
            "仅服务 C-prequin-state/L103 的精确发布。西汉传世叙事、累积思想文本、"
            "公元前344年器物和较晚秦简分层使用；角色不得越过当前片段或把教学变量当史实。"
        ),
        sources=_evidence_sources(),
        passages=tuple(sorted(passages, key=lambda item: item.passage_id)),
    )


def build_shangyang_scenario_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> scenario_authoring.ScenarioAuthorDraftV1:
    package = course_package_from_legacy(course_draft or build_shangyang_course_draft())
    fact_ids, person_ids = _lookup_runtime_ids(package)
    source_ids = {item.title: item.source_id for item in package.source_refs}

    def facts(*keys: str) -> list[str]:
        return sorted(fact_ids[FACTS[key]] for key in keys)

    shangyang = person_ids["商鞅"]
    xiaogong = person_ids["秦孝公"]
    aristocrats = person_ids["旧贵族代表"]
    households = person_ids["农耕家庭代表"]
    soldiers = person_ids["军功士卒"]
    officials = person_ids["县廷吏员"]
    C = scenario_authoring.ScenarioDraftConditionV1
    E = scenario_authoring.ScenarioDraftEffectV1
    A = scenario_authoring.ScenarioDraftActionV1

    def effects(**changes: float) -> list[scenario_authoring.ScenarioDraftEffectV1]:
        return [E(variable_id=key.replace("_", "-"), value=value) for key, value in changes.items()]

    return scenario_authoring.ScenarioAuthorDraftV1(
        scenario_id=SHANGYANG_SCENARIO_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="六回合变法议事：强国之法由谁承担",
        scenario_type="institutional_reform",
        student_role="秦国改革议事与执行记录者",
        objective="在六个制度节点中提高国家能力、粮食供给、军事准备和制度信用，同时控制社会压力与旧贵族阻力，并为每项选择写出证据边界。",
        opening="秦孝公希望改变秦国在列国竞争中的处境，旧贵族担心身份秩序被打破，农户与基层官吏则追问新法怎样兑现。你只能作六次节点选择。数值是课堂模型，不是战国秦国统计。",
        max_turns=6,
        variables=[
            scenario_authoring.ScenarioDraftVariableV1(variable_id="state-capacity", label="国家能力", description="登记、计量、地方执行和资源组织能力。", initial=38),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="military-readiness", label="军事准备", description="兵源、军功激励和组织动员的综合课堂指标。", initial=34),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="grain-supply", label="粮食供给", description="农业产出、储备和征发可持续性的课堂指标。", initial=48),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="legal-credibility", label="制度信用", description="规则是否公开、承诺是否兑现、执行是否可预期。", initial=34),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="social-pressure", label="社会压力", description="家庭负担、战争风险、监督惩罚和行政强度；越低越可承受。", initial=32),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="elite-resistance", label="旧贵族阻力", description="旧身份与既得利益受到调整后形成的反对；越低越利于持续。", initial=58),
        ],
        npcs=[
            scenario_authoring.ScenarioDraftNpcV1(person_id=shangyang, display_name="商鞅", role="改革主持者", persona="主张规则清楚、赏罚兑现与执行能力；角色化教学表达，不是史料原话。", boundaries=["不把《商君书》全部自称原话。", "不知道较晚秦简具体文字。"], initial_attitude=15, initial_trust=18, fact_refs=facts("shiji_later", "law_publicity", "shangjunshu_layers")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=xiaogong, display_name="秦孝公", role="改革支持者", persona="关注竞争窗口、支持联盟和政策延续；角色化教学表达，不是史料原话。", boundaries=["不虚构宫廷密谈。", "不预言统一必然发生。"], initial_attitude=18, initial_trust=20, fact_refs=facts("xiaogong_support", "multi_causal_strength")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=aristocrats, display_name="旧贵族代表", role="旧身份秩序的合成人群", persona="追问权力、程序和特权调整；角色化教学表达，不是史料原话。", boundaries=["不等同某位具名大臣。", "不把所有贵族写成同一立场。"], initial_attitude=-12, initial_trust=-5, fact_refs=facts("military_merit", "institutional_cost")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=households, display_name="农耕家庭代表", role="生产与赋役承担者", persona="从收成、征发和家庭安全评价政策；角色化教学表达，不是史料原话。", boundaries=["合成人群，不虚构田亩税额。", "变量不是历史账册。"], initial_attitude=0, initial_trust=2, fact_refs=facts("agriculture_war", "collective_responsibility")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=soldiers, display_name="军功士卒", role="身份机会与战争风险承担者", persona="同时陈述军功机会与战场代价；角色化教学表达，不是史料原话。", boundaries=["不虚构战役和斩首数。", "不把军功爵等同现代平等。"], initial_attitude=5, initial_trust=5, fact_refs=facts("military_merit", "modern_law_boundary")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=officials, display_name="县廷吏员", role="基层执行者", persona="要求制度可登记、可复核、可执行；角色化教学表达，不是史料原话。", boundaries=["较晚秦简只用于观察成熟秦制。", "不自称持有商鞅原令。"], initial_attitude=3, initial_trust=5, fact_refs=facts("county_admin", "slips_date", "slips_scope")),
        ],
        action_rules=[
            A(action_id="consult-interests", label="先听取各方陈述", description="让旧贵族、农户、士卒和吏员分别说明可执行条件。", aliases=["听取意见", "协商"], effects=effects(state_capacity=2, legal_credibility=12, social_pressure=-3, elite_resistance=-9) + [E(kind="npc", person_id=aristocrats, attitude_delta=5, trust_delta=7), E(kind="npc", person_id=households, attitude_delta=5, trust_delta=8)], feedback="改革速度没有明显提高，但分歧第一次被写成可检查的问题。", fact_refs=facts("institutional_cost", "xiaogong_support"), next_node_id="law-publication"),
            A(action_id="announce-reform-goal", label="公布富国强兵目标", description="明确改革方向，但先不处理执行规则和群体疑问。", aliases=["公布目标", "宣布变法"], effects=effects(state_capacity=5, military_readiness=5, legal_credibility=3, elite_resistance=5), feedback="方向得到宣布，支持者受到鼓舞；但目标还没有变成可兑现规则。", fact_refs=facts("warring_context", "multi_causal_strength"), next_node_id="law-publication"),
            A(action_id="silence-opposition", label="压下反对立即推进", description="以政治支持压下争论，把速度放在协商之前。", aliases=["强推", "压下反对"], effects=effects(state_capacity=10, military_readiness=5, legal_credibility=-7, social_pressure=11, elite_resistance=13), feedback="决策窗口被迅速利用，公开反对暂时沉默，抵触与不安却转入执行层。", fact_refs=facts("xiaogong_support", "institutional_cost"), next_node_id="law-publication"),
            A(action_id="publish-clear-rules", label="公开法令与申诉记录", description="把责任、尺度和执行步骤写清，并记录争议供复核。", aliases=["公开法令", "明法"], effects=effects(state_capacity=8, legal_credibility=17, social_pressure=3, elite_resistance=3) + [E(kind="npc", person_id=officials, attitude_delta=5, trust_delta=9, reveal_fact_refs=facts("law_publicity"))], feedback="规则开始可查、可解释；公开本身不消除强制，却减少了任意变化。", fact_refs=facts("law_publicity", "modern_law_boundary"), next_node_id="incentive-design"),
            A(action_id="stage-symbolic-promise", label="以公开赏格建立承诺", description="用一次清楚兑现的赏格展示新令会被执行。", aliases=["徙木立信", "兑现赏格"], effects=effects(state_capacity=4, legal_credibility=11, social_pressure=2, elite_resistance=5) + [E(kind="npc", person_id=shangyang, attitude_delta=4, trust_delta=6, reveal_fact_refs=facts("moving_wood"))], feedback="承诺得到一次兑现；史官同时注明这是借《史记》故事形成的课堂选择。", fact_refs=facts("moving_wood", "shiji_later"), next_node_id="incentive-design"),
            A(action_id="impose-collective-liability", label="先推什伍连带追责", description="以相互监督和连带处置迅速压实基层责任。", aliases=["连坐", "什伍追责"], effects=effects(state_capacity=14, legal_credibility=2, social_pressure=16, elite_resistance=8) + [E(kind="npc", person_id=households, attitude_delta=-9, trust_delta=-12, reveal_fact_refs=facts("collective_responsibility"))], feedback="追责网络提高了可见度，也让邻里与家庭承担他人行为的风险。", fact_refs=facts("collective_responsibility", "modern_law_boundary"), next_node_id="incentive-design"),
            A(action_id="balance-farming-and-merit", label="并列耕作保障与军功通道", description="给农业生产和服役立下清楚奖励，同时限制额外征发。", aliases=["平衡耕战", "耕战并举"], effects=effects(state_capacity=6, military_readiness=11, grain_supply=13, legal_credibility=5, social_pressure=7, elite_resistance=6) + [E(kind="npc", person_id=households, attitude_delta=4, trust_delta=6), E(kind="npc", person_id=soldiers, attitude_delta=5, trust_delta=7)], feedback="粮食与服役激励都得到推进，身份机会扩大，家庭仍感到战争目标正在进入生活。", fact_refs=facts("agriculture_war", "military_merit", "institutional_cost"), next_node_id="administration"),
            A(action_id="prioritize-military-merit", label="优先军功爵与战备", description="把身份上升和资源奖励主要系于军功。", aliases=["军功爵", "优先战备"], effects=effects(state_capacity=8, military_readiness=25, grain_supply=-4, legal_credibility=4, social_pressure=13, elite_resistance=10) + [E(kind="npc", person_id=soldiers, attitude_delta=9, trust_delta=9), E(kind="npc", person_id=aristocrats, attitude_delta=-8, trust_delta=-6)], feedback="士卒看到新通道，战备迅速提升；旧特权与社会军事化压力同时上升。", fact_refs=facts("military_merit", "institutional_cost"), next_node_id="administration"),
            A(action_id="reward-farming-first", label="先稳农业与家庭生产", description="优先保障耕作时间和产出奖励，放慢军事激励。", aliases=["奖励耕织", "先稳农业"], effects=effects(state_capacity=4, military_readiness=3, grain_supply=17, legal_credibility=4, social_pressure=3, elite_resistance=2) + [E(kind="npc", person_id=households, attitude_delta=8, trust_delta=9)], feedback="粮食与家庭预期改善，改革的军事目标推进较慢。", fact_refs=facts("agriculture_war",), next_node_id="administration"),
            A(action_id="standardize-measures", label="先统一计量与账册", description="以标准量器和共同账册连接粮食、交换与征收。", aliases=["统一度量衡", "商鞅方升"], effects=effects(state_capacity=16, grain_supply=6, legal_credibility=9, social_pressure=3, elite_resistance=3) + [E(kind="npc", person_id=officials, attitude_delta=7, trust_delta=9, reveal_fact_refs=facts("fangsheng_direct"))], feedback="标准尺度使记录可比较；这项选择有公元前344年方升铭文的直接实物支撑。", fact_refs=facts("fangsheng_direct"), next_node_id="enforcement"),
            A(action_id="build-county-offices", label="建设县廷并培训吏员", description="建立地方执行和复核环节，避免命令只停在都城。", aliases=["推行县制", "建设县廷"], effects=effects(state_capacity=14, legal_credibility=6, social_pressure=6, elite_resistance=8) + [E(kind="npc", person_id=officials, attitude_delta=7, trust_delta=8)], feedback="地方执行能力提高，也产生登记、征收和问责的新压力。", fact_refs=facts("county_admin", "slips_date", "slips_scope"), next_node_id="enforcement"),
            A(action_id="rapid-requisition-network", label="先建征发与追责网络", description="用户籍、基层编组和严密征发快速集中资源。", aliases=["严密征发", "基层追责"], effects=effects(state_capacity=19, military_readiness=8, grain_supply=7, legal_credibility=-4, social_pressure=16, elite_resistance=9), feedback="国家掌握资源的速度提高，家庭和基层执行者承受明显压力。", fact_refs=facts("collective_responsibility", "county_admin"), next_node_id="enforcement"),
            A(action_id="defer-local-implementation", label="暂留旧办法等待自愿采用", description="不建立统一执行机构，让地方自行选择是否跟进。", aliases=["暂缓县政", "地方自愿"], effects=effects(state_capacity=-3, legal_credibility=-5, social_pressure=-4, elite_resistance=-8), feedback="冲突暂时下降，规则却在不同地方呈现不同含义。", fact_refs=facts("county_admin", "law_publicity"), next_node_id="enforcement"),
            A(action_id="phase-and-audit", label="分阶段执行并公开复核", description="先在部分区域执行，记录负担与错误后修订步骤。", aliases=["分阶段", "审计修订"], effects=effects(state_capacity=9, legal_credibility=10, social_pressure=-7, elite_resistance=-6) + [E(kind="npc", person_id=officials, attitude_delta=5, trust_delta=8), E(kind="npc", person_id=households, attitude_delta=4, trust_delta=7)], feedback="推进略慢，但错误和负担被写进可复核记录，制度更有持续条件。", fact_refs=facts("institutional_cost", "law_publicity"), next_node_id="evaluation"),
            A(action_id="enforce-with-severe-penalties", label="以严罚完成全面执行", description="用高强度惩罚和连带责任压缩执行时间。", aliases=["严刑执行", "全面强推"], effects=effects(state_capacity=16, military_readiness=10, legal_credibility=-7, social_pressure=19, elite_resistance=10) + [E(kind="npc", person_id=households, attitude_delta=-11, trust_delta=-13), E(kind="npc", person_id=officials, attitude_delta=-3, trust_delta=-5)], feedback="命令迅速落实，压力、抵触和惩罚外溢也达到危险水平。", fact_refs=facts("collective_responsibility", "institutional_cost", "modern_law_boundary"), next_node_id="evaluation"),
            A(action_id="correct-burdens", label="纠正过重征发与含混条款", description="减少过量征发，解释含混规则并保护基本耕作时间。", aliases=["减轻负担", "纠错"], effects=effects(state_capacity=5, grain_supply=4, legal_credibility=12, social_pressure=-9, elite_resistance=-4), feedback="国家暂时放慢扩张，却换来更清楚规则和可持续执行。", fact_refs=facts("agriculture_war", "institutional_cost"), next_node_id="evaluation"),
            A(action_id="suspend-enforcement", label="暂停执行等待局势自行稳定", description="停止推进，但不解决规则冲突或建立替代方案。", aliases=["暂停变法", "继续等待"], effects=effects(state_capacity=-5, military_readiness=-3, legal_credibility=-8, social_pressure=-4, elite_resistance=-7), feedback="眼前压力下降，改革目标与执行承诺同时失去清晰度。", fact_refs=facts("xiaogong_support", "law_publicity"), next_node_id="evaluation"),
            A(action_id="consolidate-balanced-reform", label="封存规则并保留复核", description="把标准、县政、激励和负担修订写入可持续执行方案。", aliases=["平衡收束", "封存改革"], effects=effects(state_capacity=10, military_readiness=8, grain_supply=5, legal_credibility=6, social_pressure=3, elite_resistance=-3), feedback="六轮方案完成：国家能力、制度信用和社会承受将共同决定结局。", fact_refs=facts("institutional_cost", "multi_causal_strength"), next_node_id="evaluation"),
            A(action_id="drive-mobilization", label="以战备成果继续加速", description="把最后资源投入征发、军功和强制执行。", aliases=["继续强推", "加速动员"], effects=effects(state_capacity=12, military_readiness=16, grain_supply=4, legal_credibility=-4, social_pressure=11, elite_resistance=7), feedback="动员能力冲到高位，制度是否仍可承受将在卷宗中接受检验。", fact_refs=facts("military_merit", "institutional_cost"), next_node_id="evaluation"),
            A(action_id="negotiate-limited-reform", label="保留核心措施并继续协商", description="承认执行能力有限，先保留可兑现措施和后续复核。", aliases=["折中收束", "有限改革"], effects=effects(state_capacity=3, grain_supply=3, legal_credibility=8, social_pressure=-8, elite_resistance=-10), feedback="方案没有完成全部目标，但保住了继续执行和协商的条件。", fact_refs=facts("reform_chronology", "institutional_cost"), next_node_id="evaluation"),
            A(action_id="abandon-reform", label="撤回方案恢复旧序", description="因阻力与执行困难取消尚未稳固的改革措施。", aliases=["放弃变法", "恢复旧制"], effects=effects(state_capacity=-10, military_readiness=-8, grain_supply=-3, legal_credibility=-12, social_pressure=-5, elite_resistance=-15), feedback="眼前反对有所缓和，求变窗口和已作承诺一并失去。", fact_refs=facts("xiaogong_support", "warring_context"), next_node_id="reform-withdrawn"),
        ],
        event_rules=[
            scenario_authoring.ScenarioDraftEventV1(event_id="rules-become-visible", title="规则开始可核验", match="all", trigger=[C(kind="turn", operator="gte", value=2), C(variable_id="legal-credibility", operator="gte", value=55)], effects=[E(variable_id="state-capacity", value=4)], narrative="公开且兑现的规则减少了反复解释成本，基层执行能力小幅提高。", once=True, priority=10, fact_refs=facts("law_publicity")),
            scenario_authoring.ScenarioDraftEventV1(event_id="resistance-coalesces", title="旧利益联合阻挠", match="all", trigger=[C(variable_id="elite-resistance", operator="gte", value=78)], effects=[E(variable_id="state-capacity", value=-5), E(variable_id="social-pressure", value=6)], narrative="特权调整与强推方式使反对力量联合，改革执行出现额外摩擦。", once=True, priority=20, fact_refs=facts("military_merit", "institutional_cost")),
            scenario_authoring.ScenarioDraftEventV1(event_id="administrative-overload", title="基层执行过载", match="all", trigger=[C(variable_id="state-capacity", operator="gte", value=75), C(variable_id="social-pressure", operator="gte", value=72)], effects=[E(variable_id="legal-credibility", value=-6), E(variable_id="grain-supply", value=-4)], narrative="征发、登记和处罚同时加速，基层错误增加，国家能力的增长开始反噬制度信用。", once=True, priority=30, fact_refs=facts("county_admin", "institutional_cost")),
        ],
        ending_rules=[
            scenario_authoring.ScenarioDraftEndingV1(ending_id="ending-balanced-reform", title="法立而可续", match="all", conditions=[C(kind="turn", operator="gte", value=6), C(variable_id="state-capacity", operator="gte", value=75), C(variable_id="military-readiness", operator="gte", value=50), C(variable_id="grain-supply", operator="gte", value=60), C(variable_id="legal-credibility", operator="gte", value=65), C(variable_id="social-pressure", operator="lte", value=65)], summary="标准、地方执行、农业与军功激励形成连接，规则也保留复核；改革获得阶段成功而未把代价藏起来。", historical_explanation="这是课堂的平衡成功模型，不声称真实秦国曾按六项数值运行。秦的长期强盛仍需多代、多因素解释。", major_costs=["身份与资源更紧密地服务国家目标", "家庭仍承担赋役和战争压力", "旧特权调整需要持续政治支持"], source_ref_ids=sorted([source_ids["商鞅方升——每月一珍"], source_ids["《史记·商君列传》"], source_ids["义务教育历史课程标准（2022年版）"]]), fact_refs=facts("fangsheng_direct", "multi_causal_strength", "institutional_cost"), priority=10),
            scenario_authoring.ScenarioDraftEndingV1(ending_id="ending-coercive-strength", title="国强而压重", match="all", conditions=[C(kind="turn", operator="gte", value=6), C(variable_id="state-capacity", operator="gte", value=75), C(variable_id="military-readiness", operator="gte", value=65), C(variable_id="social-pressure", operator="gte", value=72)], summary="征发、战备和基层追责迅速增强，家庭、士卒与吏员承受高压，制度信用也受到侵蚀。", historical_explanation="富国强兵并不自动等于所有群体获益。本结局把国家能力与强制代价并列，但数值不是秦国史实统计。", major_costs=["连带责任和严罚扩大", "战争动员深入家庭生活", "基层过载与旧贵族阻力可能反噬改革"], source_ref_ids=sorted([source_ids["《史记·商君列传》"], source_ids["湖北简牍地理，一窥湖北简牍之风采"], source_ids["《韩非子·定法》"]]), fact_refs=facts("collective_responsibility", "military_merit", "institutional_cost"), priority=20),
            scenario_authoring.ScenarioDraftEndingV1(ending_id="ending-negotiated-compromise", title="新法初立，能力有限", match="all", conditions=[C(kind="turn", operator="gte", value=6), C(variable_id="state-capacity", operator="gte", value=50), C(variable_id="legal-credibility", operator="gte", value=50), C(variable_id="social-pressure", operator="lte", value=65)], summary="部分规则获得信用，粮食或地方治理有所改善，但军事和行政目标没有全部完成。改革进入继续协商和修订的阶段。", historical_explanation="制度变化常是长期过程。折中结局保留阶段成果，不把改革写成一次完成的清单。", major_costs=["国家能力仍不足以覆盖所有地区", "部分身份与土地问题没有解决", "支持联盟需要继续维持"], source_ref_ids=sorted([source_ids["《史记·商君列传》"], source_ids["秦文化的历史特点与当代价值"]]), fact_refs=facts("reform_chronology", "county_admin", "multi_causal_strength"), priority=30),
            scenario_authoring.ScenarioDraftEndingV1(ending_id="ending-reform-breakdown", title="承诺失信，窗口关闭", match="all", conditions=[C(kind="turn", operator="gte", value=6)], summary="六轮结束时执行能力或制度信用仍不足，改革目标在阻力、含混规则和迟疑中失去窗口。", historical_explanation="这是课堂规则的失败兜底，用于复盘支持、执行、资源与代价怎样相互作用，不对应某次真实廷议。", major_costs=["公开承诺未能稳定兑现", "已投入资源没有形成持续制度", "列国竞争压力仍在"], source_ref_ids=sorted([source_ids["《史记·商君列传》"], source_ids["义务教育历史课程标准（2022年版）"]]), fact_refs=facts("xiaogong_support", "warring_context", "institutional_cost"), priority=1000),
        ],
        start_node_id="court-debate",
        nodes=[
            scenario_authoring.ScenarioDraftNodeV1(node_id="court-debate", title="第一节点：改革是否启动", narration="求变窗口已经打开，先决定怎样面对目标与反对。", action_ids=["consult-interests", "announce-reform-goal", "silence-opposition"]),
            scenario_authoring.ScenarioDraftNodeV1(node_id="law-publication", title="第二节点：新令怎样取得信用", narration="方向已定，人们仍在等待规则是否公开、承诺是否兑现。", action_ids=["publish-clear-rules", "stage-symbolic-promise", "impose-collective-liability"]),
            scenario_authoring.ScenarioDraftNodeV1(node_id="incentive-design", title="第三节点：耕作、军功与身份", narration="改革进入利益分配，粮食、战备与身份机会不可能毫无冲突。", action_ids=["balance-farming-and-merit", "prioritize-military-merit", "reward-farming-first"]),
            scenario_authoring.ScenarioDraftNodeV1(node_id="administration", title="第四节点：规则怎样抵达地方", narration="没有计量、账册和地方执行，法令可能只停留在都城。", action_ids=["standardize-measures", "build-county-offices", "rapid-requisition-network", "defer-local-implementation"]),
            scenario_authoring.ScenarioDraftNodeV1(node_id="enforcement", title="第五节点：执行速度与纠错", narration="制度开始改变日常生活，必须选择执行强度和纠错方式。", action_ids=["phase-and-audit", "enforce-with-severe-penalties", "correct-burdens", "suspend-enforcement"]),
            scenario_authoring.ScenarioDraftNodeV1(node_id="evaluation", title="第六节点：封存、折中或撤回", narration="最后一次决定不会抹平之前的轨迹，只会决定怎样带着成果与代价进入卷宗。", action_ids=["consolidate-balanced-reform", "drive-mobilization", "negotiate-limited-reform", "abandon-reform"]),
            scenario_authoring.ScenarioDraftNodeV1(node_id="reform-withdrawn", title="终局节点：方案撤回", narration="改革承诺被撤回，求变窗口关闭，进入失败复盘。", action_ids=[], ending_id="ending-reform-breakdown"),
        ],
        fact_refs=sorted(fact_ids.values()),
        source_ref_ids=sorted(source_ids.values()),
        dossier_template=scenario_authoring.ScenarioDraftDossierV1(
            title_template="《{scenario_title}·史官卷宗》",
            reflection_questions=[
                "哪一次选择最改变国家能力或制度信用？请引用变量变化和事实来源。",
                "你的结局让哪些群体获得机会，又让哪些群体承担压力？",
                "卷宗中的《史记》、方升、秦简和《商君书》分别能证明到什么程度？",
                "秦国后来强盛还需要哪些因素，为什么不能只归因于商鞅？",
            ],
            knowledge_node_kinds=["evidence", "claim", "boundary", "institution", "cause", "consequence", "cost"],
        ),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_shangyang_presentation(
    content_root: Path,
    *,
    sealed_by: str,
    sealed_at: datetime | None = None,
    presentation_version: int = 1,
) -> LessonPresentationV1:
    root = Path(f"media/lessons/L103/v{presentation_version:03d}")
    video = root / "shangyang-intro.mp4"
    poster = root / "shangyang-poster.webp"
    transcript = root / "shangyang-transcript.md"
    provisional = LessonPresentationV1(
        presentation_id=SHANGYANG_PRESENTATION_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        presentation_version=presentation_version,
        title="商鞅变法：材料年代与制度代价导读",
        estimated_minutes=40,
        phase_minutes={"observe": 9, "decide": 14, "consult": 7, "dossier": 10},
        video_path=video.as_posix(),
        poster_path=poster.as_posix(),
        transcript_path=transcript.as_posix(),
        video_duration_seconds=45,
        video_sha256=_sha256(content_root / video),
        poster_sha256=_sha256(content_root / poster),
        transcript_sha256=_sha256(content_root / transcript),
        accessibility_note=(
            "无声 HyperFrames 中文动画；全部关键信息写入画面并提供本地 Markdown 文字稿，学生可随时跳过。"
            if presentation_version >= 2
            else "无声中文文字导读；全部关键信息写入画面并提供本地 Markdown 文字稿，学生可随时跳过。"
        ),
        sealed_at=sealed_at or datetime.now(timezone.utc),
        sealed_by=sealed_by,
        checksum="0" * 64,
    )
    return sign_evidence_contract(provisional)


__all__ = [
    "BODY",
    "COURSE_ID",
    "FACTS",
    "LESSON_ID",
    "SHANGYANG_CORPUS_ID",
    "SHANGYANG_PRESENTATION_ID",
    "SHANGYANG_SCENARIO_ID",
    "build_shangyang_course_draft",
    "build_shangyang_evidence_draft",
    "build_shangyang_presentation",
    "build_shangyang_scenario_draft",
]
