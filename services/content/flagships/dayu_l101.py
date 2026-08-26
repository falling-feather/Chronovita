"""Reviewed authoring source for C-prequin-state / L101.

The module deliberately keeps four layers separate: inherited legend, transmitted
texts, archaeological observations, and modern classroom interpretation.  Runtime
JSON is generated through the ordinary content/evidence/scenario workflows; this
file is the human-reviewable source used to reproduce and test that publication.
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
LESSON_ID = "L101"
DAYU_SCENARIO_ID = "dayu-crisis-governance"
DAYU_CORPUS_ID = "dayu-evidence"
DAYU_PRESENTATION_ID = "dayu-classroom-intro"


BODY = [
    (
        "如果一场持续的洪水冲毁田地、道路和聚落，人们为什么愿意把粮食、劳力与决定权交给一个共同的组织者？"
        "“大禹治水”常被讲成英雄战胜洪水的故事，本课却要多追问一步：这个故事由哪些时代留下，哪些内容能由考古材料"
        "观察，哪些只是后人的解释？我们将把传说、传世文献、考古发现和课堂推演分开标注，再讨论灾害治理怎样可能改变"
        "人与人之间的协作方式、首领权威和早期国家秩序。"
    ),
    (
        "先从洪水本身说起。黄河及其支流含沙量高、河道摆动明显，不同流域在史前时期也经历过各自的水患。对没有现代"
        "堤坝、预报与机械的聚落而言，连续降雨、河道改道或局地堰塞湖溃决，都可能同时威胁住房、种子、牲畜和饮水。"
        "但“许多地方可能发生过洪水”并不等于“曾有一场覆盖天下、时间与路线完全确定的洪水”。课堂中的危机背景是依据"
        "常见风险建立的教学情境，不是一份可以还原某一年天气的记录。"
    ),
    (
        "关于禹的故事主要保存在后世传世文献中。《孟子》《尚书》相关篇章和《史记·夏本纪》成书、编定或流传的时代，"
        "都晚于传统叙事所说的禹生活年代。它们能够说明战国、秦汉及后世的人怎样记忆和解释远古，却不能自动等同于事件"
        "发生当时的现场记录。读这些文字时，我们既不应把它们全部丢进“虚构”一栏，也不能因为文字写得具体，就把每一个"
        "地名、年数和动作都当作已经被同时代材料证实。"
    ),
    (
        "在传世叙事中，鲧先受命治理洪水，后来禹接续其事；禹长期在外，疏通河道，使水有所归，最终因治水声望成为联盟"
        "首领。“三过家门而不入”把公共责任推到极致，成为后世反复讲述的道德形象。它适合帮助我们理解古人赞赏怎样的"
        "领导者，却没有对应的考古材料能核验“三次”这一细节。本课人物卡中的禹、鲧和益，也都是依照传世叙事建立的"
        "有边界角色，不会假装说出未经文献支持的“原话”。"
    ),
    (
        "“鲧用堵、禹用疏”是常见的课堂概括。传世文献确实把鲧的失利与禹顺水势、疏川导流相对照，但真实水利从来不是"
        "一道单选题：局部护岸、临时围挡、疏浚、分洪、迁居和粮食调配可能同时需要。把一种方法说成永远错误、另一种说成"
        "处处正确，会掩盖地形、季节和资源差异。因此六回合关卡允许勘察、加固、疏导、轮换劳作、公开方案和赈济并用，"
        "评价的是组合、时机与代价，而不是背诵唯一按钮。"
    ),
    (
        "治水不只需要技术，还需要组织。上游开口可能影响下游聚落，今天投入劳力会减少耕作时间，谁先得到粮食、谁承担"
        "危险、谁能改变方案，都会影响信任。一个首领若能协调多个聚落、记录地形、分配物资并让承诺得到执行，权威就可能"
        "在共同事务中扩大；若只强迫劳作，即使水位暂时下降，也可能留下饥饿、逃离和怨恨。这里的“权威从治理中形成”是"
        "现代教学解释，不是考古学家在某件器物上直接读到的一句话。"
    ),
    (
        "传世叙事还把治水与政治继承连在一起：禹之后，其子启取得首领位置，后世用“禅让转向世袭”或“公天下转向家天下”"
        "概括这一变化。这个框架有助于七年级学生观察权力秩序的转折，却仍来自较晚文献整理的王朝谱系。约公元前21世纪、"
        "约公元前1600年等日期，是教学和研究中使用的年代框架，不是精确到某年的同时代纪年。我们可以讨论继承秩序怎样"
        "被解释，却不能声称已经找到禹或启亲自留下的文字档案。"
    ),
    (
        "考古学提供了另一种观察窗口。河南偃师二里头遗址位于伊洛河流域，遗址年代、分布中心和发展阶段与传世文献所述"
        "夏后期活动范围有较高重合，因此它是探索夏史最重要的材料之一。考古人员发现了大规模都邑、成组道路、宫殿区、"
        "祭祀区、铸铜与绿松石作坊，以及等级有别的建筑和墓葬。这些可观察遗存说明当时存在集中规划、专业生产、礼仪秩序"
        "和明显的社会分化，为讨论广域王权与早期国家提供了坚实材料。"
    ),
    (
        "不过，考古学首先命名的是“二里头遗址”和“二里头文化”。把它们进一步解释为夏后期都城或夏文化，是综合年代、"
        "地域、聚落等级和传世文献作出的历史判断。国家博物馆等公共机构把二里头称为探索夏人历史面貌的主要遗存，部分"
        "研究者使用更肯定的“夏都”表述，也有学者提醒目前尚无二里头同时代文字明确写出“禹”或“夏”。本课保留这种证据"
        "强弱差别：可以说“高度相关、重要对象”，不把解释写成无条件的一一对应。"
    ),
    (
        "判断证据时还要分清“没有发现”与“证明不存在”。目前没有可公认直读为禹的同时代铭文，只能限制我们对人物姓名的"
        "断言，不能反过来证明后世叙事必定毫无历史基础；二里头显示出复杂都邑，也不能单靠复杂性就确认王朝名称。历史研究"
        "经常处在两种急切之间：一种急着让遗物给故事盖章，另一种因缺少直接文字便否定所有记忆。更稳妥的方法，是把每项"
        "材料能回答的问题写出来：器物和布局回答社会怎样组织，传世文本回答后人怎样记忆，自然科学回答何时何地可能发生"
        "灾害；只有证据链相接时，结论才向前一步。"
    ),
    (
        "2016年发表在《Science》的研究提出，黄河上游积石峡约公元前1920年可能发生过大型堰塞湖溃决，并讨论它与洪水"
        "传说及夏代年代的关系。这项研究让自然科学证据进入讨论，也很快引发对测年、洪水范围和文化联系的复核。即使接受"
        "那里曾有灾害，也只能先证明特定地点与时段的自然事件；从局地洪水跨到“就是大禹治理的洪水”，还缺少人物、路线"
        "和连续传播链的直接证据。积石峡因此被放在地图上作为争议案例，而不是禹的“考古打卡点”。"
    ),
    (
        "后世地图也需要放回自己的时代。南宋《禹迹图》以石刻地图表现河流、山川和“禹迹”，距离传统所说的禹时代已有"
        "数千年。它珍贵地展示了十二世纪的人如何用地图组织疆域知识和文化记忆，却不能当作夏代测绘原件。同样，《禹贡》"
        "中的九州、山川和贡赋结构，适合研究古人怎样想象空间与秩序；文本层次和地名沿革复杂，不能把每条线直接画成禹"
        "实际施工路线。地图踏勘会同时显示“遗址点”“自然事件点”和“记忆地图”，避免把三者混成一张证据图。"
    ),
    (
        "现在回到课堂危机。你不是扮演无所不知的神话英雄，而是作为治水共同体的议事记录者，在六个回合中协调勘察、"
        "工程、粮食和劳作。洪水风险下降只是一个指标；地形认知、聚落信任、劳作者状态、粮食储备与协作能力同样可见。"
        "快速强征可能形成“有功但代价沉重”的结局，照顾所有人却迟迟不处理水势也可能失败。规则不是历史复刻，而是让"
        "“公共工程为何会产生权力、权力又应承担什么责任”变成可以观察、干预、反馈和复盘的问题。"
    ),
    (
        "召见人物时，禹、益、聚落代表或劳作者只能依据本课当前发布的证据片段回答，并会标明“角色化教学表达，不是史料"
        "原话”。如果材料不足，他们应说“依据不足”，而不是用模型常识补齐。你也可以召见历史研究助教，比较传世文本与"
        "考古材料的年代距离。每一张回答卡都应带来源、片段、发布版本和不确定性，让“我听到一个有说服力的故事”转化为"
        "“我知道这句话依据什么、还能追问什么”。"
    ),
    (
        "最后生成的史官卷宗不会只宣布成败。它会保存六次选择、变量轨迹、触发事件、主要代价、历史解释和来源，再幂等"
        "导入知识画板。复盘时请用四句话完成证据链：我观察到什么材料；我作出了什么判断；还有哪一种解释可能成立；如果"
        "增加一条新证据，我会怎样修改结论。理解大禹治水的价值，不在于把传说简单判成“真”或“假”，而在于学会尊重"
        "不同证据的时间、能力与边界，并看见共同治理、政治权威和社会代价之间的复杂联系。"
    ),
]


FACTS = {
    "later_memory": "【传世文献】现存关于禹治水的主要文字形成或编定年代晚于传统叙事所指事件，能证明后世记忆，不能自动视为同时代记录。",
    "shiji_date": "【传世文献】《史记·夏本纪》由西汉司马迁撰成，距离传统所说的禹时代很远，具体叙事需要与其他材料互证。",
    "mengzi_date": "【传世文献】《孟子》反映战国时期的论说语境，其中疏河与三过家门叙事首先是后人理解禹的重要证据。",
    "yugong_boundary": "【传世文献】《尚书·禹贡》的文本层次、九州地名和成篇年代存在研究讨论，不宜直接当作夏代施工地图。",
    "three_doors": "【传说】“三过家门而不入”是影响深远的责任伦理叙事，目前不能由考古材料核验次数与现场细节。",
    "block_dredge": "【教学概括】“鲧堵禹疏”来自传世叙事的对照，真实治水可能同时使用防护、疏导、分洪、迁居和物资调配。",
    "jishi_event": "【自然科学研究】积石峡约公元前1920年大型溃决洪水是一项有争议的研究判断，局地灾害不能直接证明禹、全国洪水或夏王朝。",
    "no_yu_inscription": "【考古边界】目前二里头材料中没有得到学界公认、可同时代直读为“禹”的铭文，人物与遗址不能直接绑定。",
    "erlitou_overlap": "【考古判断】二里头文化的年代与核心分布同传世文献所述夏后期时空范围高度重合，是探索夏史的关键材料。",
    "erlitou_state": "【考古观察】二里头的大型都邑、道路网、宫殿区、祭祀区、官营作坊和等级差异支持早期国家与广域王权研究。",
    "erlitou_identity": "【解释边界】“二里头文化”是考古学命名；进一步称其为夏文化或夏都需要综合论证，不应写成无条件同义词。",
    "governance_model": "【教学解释】以洪水治理说明跨聚落协作和首领权威形成，是基于材料的课堂分析模型，不是某件遗物直接陈述的事实。",
    "succession": "【传世叙事】禹后启继位以及禅让转向世袭的框架来自后世王朝叙事，适合讨论权力秩序但不是同时代档案。",
    "costs": "【教学解释】公共工程会占用耕作、粮食与人身安全；成功、代价和信任必须同时进入历史评价。",
    "map_layers": "【空间边界】遗址、自然事件地点与后世记忆地图属于不同证据层，不能拼成一条确定的禹治水路线。",
    "chronology": "【年代边界】约公元前21世纪至约公元前1600年的夏代框架是教学与研究使用的约数，不是精确到年的同时代纪年。",
}


def _course_sources() -> list[content.SourceRef]:
    return [
        content.SourceRef(
            title="义务教育历史课程标准（2022年版）",
            source="中华人民共和国教育部",
            url_or_path="https://www.moe.gov.cn/srcsite/A26/s8001/202204/t20220420_619921.html",
            citation_note="用于确定七年级历史核心素养、证据意识与适龄表达；只保存自写摘要。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="义务教育教科书·中国历史七年级上册目录与课程位置",
            source="人民教育出版社",
            url_or_path="https://www.pep.com.cn/products/jc/czjks/201802/t20180227_1922743.shtml",
            citation_note="用于确认早期国家单元的年级与主题位置；不复制教材章节。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="《史记·夏本纪》",
            source="中国哲学书电子化计划（传世文献底本索引）",
            url_or_path="https://ctext.org/shiji/xia-ben-ji/zh",
            citation_note="西汉成书的传世叙事；用于研究后世夏史记忆，不视为禹时代现场记录。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="《孟子·滕文公上》",
            source="中国哲学书电子化计划（传世文献底本索引）",
            url_or_path="https://ctext.org/mengzi/teng-wen-gong-i/zh",
            citation_note="战国论说语境中的治水与公共责任叙事。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="《尚书·禹贡》",
            source="中国哲学书电子化计划（传世文献底本索引）",
            url_or_path="https://ctext.org/shang-shu/tribute-of-yu/zh",
            citation_note="用于观察九州、山川与贡赋秩序的后世文本表达；成篇与地名边界需提示。",
            reliability="disputed",
        ),
        content.SourceRef(
            title="古代中国：夏商西周时期",
            source="中国国家博物馆",
            url_or_path="https://www.chnmuseum.cn/portals/0/web/zt/gudai/detail2.html",
            citation_note="用于早期国家、二里头与夏史关系及手工业观察的公共机构资料。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="中华文明总进程的引领者：二里头文化",
            source="国家发展和改革委员会",
            url_or_path="https://www.ndrc.gov.cn/xwdt/ztzl/dyhgjwhgy/202209/t20220920_1335799_ext.html",
            citation_note="用于二里头都邑、宫城、道路与作坊资料；对“夏都”的认定作为机构性解释呈现。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="二里头都城布局的新发现及其意义",
            source="全国哲学社会科学工作办公室",
            url_or_path="https://www.nopss.gov.cn/n1/2021/0208/c219544-32025885.html",
            citation_note="考古工作者对道路网、功能分区、等级结构及夏史对应关系的研究说明。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="中华文明起源与早期发展综合研究",
            source="中国人大网",
            url_or_path="https://www.npc.gov.cn/npc/c2/c30834/202309/t20230901_431407.html",
            citation_note="用于伊洛河流域、二里头年代、宫城和高等级手工业的综合研究摘要。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="Outburst flood at 1920 BCE supports historicity of China's Great Flood and the Xia dynasty",
            source="Science",
            url_or_path="https://doi.org/10.1126/science.aaf0842",
            citation_note="积石峡洪水假说的原始研究；从自然事件到历史人物的推论需要与质疑研究并列。",
            reliability="disputed",
        ),
        content.SourceRef(
            title="The Jishi Outburst Flood of 1920 BCE and the Great Flood Legend in Ancient China: Preliminary Reflections",
            source="Journal of Chinese Humanities / 山东大学《文史哲》",
            url_or_path="https://doi.org/10.1163/23521341-12340041",
            citation_note="对积石峡洪水、洪水传说与夏史连接方式的学术反思。",
            reliability="reviewed",
        ),
        content.SourceRef(
            title="Yu ji tu（禹迹图，1136年石刻地图拓本）",
            source="美国国会图书馆",
            url_or_path="https://www.loc.gov/item/2021668264/",
            citation_note="用于观察南宋时期的地理知识和大禹文化记忆，不能作为夏代地图。",
            reliability="reviewed",
        ),
    ]


def build_dayu_course_draft() -> content.LessonContentPackage:
    return content.LessonContentPackage(
        lesson_id=LESSON_ID,
        course_id=COURSE_ID,
        title="大禹治水：洪水记忆与早期国家",
        unit="早期国家与权力秩序",
        course_title="先秦·早期国家与社会变革",
        era="约公元前21世纪—约公元前1600年（传统夏代年代框架）",
        era_id="preqin",
        section="通史",
        lesson_no="1.1",
        duration="40:00",
        abstract=(
            "从传说、传世文献、自然科学研究与二里头考古四层证据出发，"
            "在六回合危机治理中讨论公共协作、权威形成及其社会代价。"
        ),
        body=BODY,
        keywords=[
            content.KeywordCard(word="大禹治水", pinyin="dà yǔ zhì shuǐ", gloss="后世关于禹组织治理洪水的核心叙事；需区分传说记忆与可核验证据。"),
            content.KeywordCard(word="疏导", pinyin="shū dǎo", gloss="顺应水势、疏通或分导水流的治理思路，不等于任何地点都只用一种工程。"),
            content.KeywordCard(word="传世文献", pinyin="chuán shì wén xiàn", gloss="经后世抄传保存至今的文字材料，必须追问成书、编定和流传年代。"),
            content.KeywordCard(word="考古学文化", pinyin="kǎo gǔ xué wén huà", gloss="考古学依据遗物、遗迹组合划分的时空共同体，不自动等同于文献中的族群或王朝。"),
            content.KeywordCard(word="二里头", pinyin="èr lǐ tóu", gloss="河南偃师的重要都邑遗址与考古学文化，是探索夏史和早期国家的关键材料。"),
            content.KeywordCard(word="早期国家", pinyin="zǎo qī guó jiā", gloss="具有集中权力、社会分化、公共组织和区域影响等特征的早期政治形态。"),
            content.KeywordCard(word="公共动员", pinyin="gōng gòng dòng yuán", gloss="为共同事务组织跨聚落劳力、粮食、技术和信息，同时伴随权利与代价问题。"),
            content.KeywordCard(word="证据边界", pinyin="zhèng jù biān jiè", gloss="一项材料能够支持到什么程度、不能推出什么结论的清晰范围。"),
        ],
        people=[
            content.PersonCard(
                name="禹",
                role="传世叙事中的治水组织者",
                summary="后世文献把禹塑造为长期治水、协调众人并由此取得政治声望的首领。",
                persona="以审慎、重视地形和公共责任的口吻讨论选择；每次回答都承认材料年代。角色化教学表达，不是史料原话。",
                boundaries=[
                    "只依据本课关于《史记》《孟子》《禹贡》与考古边界的已发布片段回答。",
                    "不得声称亲眼见过二里头遗址、积石峡测年或后世王朝。",
                    "不得把三过家门的次数、具体施工路线或个人原话说成考古事实。",
                ],
            ),
            content.PersonCard(
                name="鲧",
                role="传世叙事中的前任治水者",
                summary="后世叙事常以鲧的失利与禹的治理相对照，但简单的“只堵不疏”不能代替复杂水利分析。",
                persona="从防护聚落、资源紧迫与方案受限的角度提出异议；不把后世评价当作本人供词。角色化教学表达，不是史料原话。",
                boundaries=[
                    "承认鲧的具体工程、失败原因与个人动机缺乏同时代记录。",
                    "不能断言所有筑堤或围挡都错误，也不能虚构刑罚现场。",
                    "回答只限课程片段，不知道二里头考古与现代水利术语。",
                ],
            ),
            content.PersonCard(
                name="益（伯益）",
                role="传世叙事中的协作者与观察者",
                summary="作为帮助组织、观察地形和连接聚落意见的教学角色，用于呈现协作而非单一英雄。",
                persona="强调记录、复核与跨聚落协商，主动区分亲历角色口吻和后世材料。角色化教学表达，不是史料原话。",
                boundaries=[
                    "人物关系依据传世叙事作有限表达，不补写私人对话、精确年龄与行程。",
                    "不能把课堂变量当作真实历史统计。",
                    "遇到超出已发布证据的问题回答“依据不足”。",
                ],
            ),
            content.PersonCard(
                name="聚落代表",
                role="受水患影响的多聚落意见群体",
                summary="汇集上游、下游与低地聚落对安全、粮食、公平和信息公开的不同诉求。",
                persona="以群体而非单一历史人物发言，追问谁承担风险、谁得到保护。角色化教学表达，不是史料原话。",
                boundaries=[
                    "这是为课堂推演设置的合成人群，不对应一位有姓名的历史人物。",
                    "不得声称代表所有史前居民，也不得给出虚构人口和伤亡数字。",
                    "观点只能解释治理权衡，不能证明禹故事的真伪。",
                ],
            ),
            content.PersonCard(
                name="治水劳作者",
                role="承担勘察、开渠、加固和运输的劳动群体",
                summary="提醒决策者看到公共工程背后的耕作时间、口粮、伤病与轮换问题。",
                persona="从劳动安全、家庭生计和任务可执行性出发回应。角色化教学表达，不是史料原话。",
                boundaries=[
                    "这是课堂合成人群，不假冒出土文字中的自述。",
                    "不提供未经来源支持的工具、工期或伤亡细节。",
                    "可以评价关卡中的代价，但必须说明变量是教学模型。",
                ],
            ),
        ],
        map_points=[
            content.MapPoint(
                label="二里头遗址",
                region="河南省洛阳市偃师区",
                lat=34.69,
                lng=112.69,
                kind="archaeological_site",
                note="约距今3800—3500年的大型都邑遗址；是探索夏史的重要考古材料，不等同于发现了禹的铭文。",
            ),
            content.MapPoint(
                label="伊洛河流域",
                region="河南西部",
                lat=34.68,
                lng=112.45,
                kind="region",
                note="二里头文化核心区域，也与传世文献所述夏人主要活动区域有较高重合。",
            ),
            content.MapPoint(
                label="积石峡",
                region="青海省黄河上游",
                lat=35.84,
                lng=102.72,
                kind="research_case",
                note="约公元前1920年溃决洪水假说的研究地点；只能作为有争议的自然事件案例，不是已证实的禹治水地点。",
            ),
            content.MapPoint(
                label="《禹迹图》所见天下",
                region="1136年南宋石刻地图的知识空间",
                kind="memory_map",
                note="用于观察后世地理知识与大禹记忆；不提供夏代坐标，也不绘制确定施工路线。",
            ),
        ],
        source_refs=_course_sources(),
        facts=list(FACTS.values()),
        qa_points=[
            "为什么传世文献很重要，却不能直接当作禹时代的现场记录？",
            "“三过家门而不入”能够支持哪类历史认识，不能证明什么？",
            "“鲧堵禹疏”为什么只是教学概括，关卡为何保留多种工程组合？",
            "二里头有哪些可直接观察的考古材料，它们如何支持早期国家研究？",
            "为什么“二里头文化”与“夏文化”不能不加说明地写成同义词？",
            "积石峡洪水研究证明了什么，又没有证明什么？",
            "公共工程怎样可能扩大首领权威，又会给普通劳作者带来哪些代价？",
            "如果新发现一条可确认年代的文字材料，你会怎样修改现有结论？",
        ],
        level_goals=[
            "能把课程材料标注为传说、传世文献、考古观察、研究判断或教学解释。",
            "能用至少两种不同类型证据说明二里头为何重要，并写出结论边界。",
            "能在六回合治理中同时追踪风险、粮食、劳作、信任、知识与协作。",
            "能用选择—变化—代价—证据链完成史官卷宗并导入知识画板。",
        ],
        saga_material=content.MaterialPlaceholder(
            title="踏勘：四层证据中的大禹治水",
            objective="在地图与短片中辨认遗址、自然事件、传世文本和后世记忆的不同身份。",
            notes="建议9分钟；先观察材料标签，再提出一条可证与一条不可证结论。",
            assets=["dayu-classroom-intro"],
        ),
        sandbox_material=content.MaterialPlaceholder(
            title="抉择：六回合洪水危机治理",
            objective="协调地形勘察、工程、粮食、劳作与公共信任，比较成功、代价、折中和失败。",
            notes="固定行动在断网时仍可完成；规则变量是教学模型，不是历史统计。",
            assets=[DAYU_SCENARIO_ID],
        ),
        seed_canvas=[
            content.SeedCanvasNode(id="evidence-layers", label="四层证据", note="传说—文献—考古—解释不可混写"),
            content.SeedCanvasNode(id="flood-and-governance", label="洪水与治理", note="自然风险需要技术和组织共同回应"),
            content.SeedCanvasNode(id="cooperation-and-power", label="协作与权威", note="公共动员可能扩大权力，也产生责任"),
            content.SeedCanvasNode(id="erlitou-state", label="二里头与早期国家", note="从可观察遗存走向有边界的历史判断"),
            content.SeedCanvasNode(id="cost-and-trust", label="代价与信任", note="工程结果不能遮蔽粮食、劳作和公平"),
            content.SeedCanvasNode(id="claim-evidence-boundary", label="结论—证据—边界", note="卷宗复盘的核心论证结构"),
        ],
        teacher_notes=(
            "正式旗舰课。课堂总时长40分钟：踏勘9、抉择14、召见7、卷宗10。"
            "禁止把角色对白当史料原话；积石峡研究必须与质疑并列；二里头采用“关键材料/高度相关”措辞。"
            "正文与片段均为项目自写摘要，仅保留必要短引和出处，不复制教材章节。"
        ),
    )


def _evidence_sources() -> tuple[EvidenceSourceV1, ...]:
    rights = "仅保存项目自写摘要和必要短引，课堂展示时保留出处；不复制受版权保护的整章内容。"
    values = [
        EvidenceSourceV1(source_id="src-allan-jishi", title="The Jishi Outburst Flood of 1920 BCE and the Great Flood Legend in Ancient China: Preliminary Reflections", kind="research", author_or_institution="Sarah Allan", publisher="Journal of Chinese Humanities", published_year=2017, url_or_path="https://doi.org/10.1163/23521341-12340041", locator="Vol. 3, Issue 1, pp. 23–34", citation_note="对自然事件与传说、夏史之间推论链的反思。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-chnmuseum-early-state", title="古代中国：夏商西周时期", kind="museum", author_or_institution="中国国家博物馆", publisher="中国国家博物馆", url_or_path="https://www.chnmuseum.cn/portals/0/web/zt/gudai/detail2.html", locator="第一单元‘夏朝的建立’及经济部分", citation_note="公共机构关于早期国家与二里头主要遗存的说明。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-loc-yuji-map", title="Yu ji tu（禹迹图）", kind="museum", author_or_institution="美国国会图书馆", publisher="Library of Congress", published_year=1136, url_or_path="https://www.loc.gov/item/2021668264/", locator="1136年石刻地图拓本馆藏记录", citation_note="用于讨论南宋地理知识与大禹记忆。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-mengzi-tengwen", title="《孟子·滕文公上》", kind="primary_source", author_or_institution="传世文献；中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/mengzi/teng-wen-gong-i/zh", locator="治水、疏河与三过家门相关段落", citation_note="战国论说语境中的后世记忆。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-moe-2022", title="义务教育历史课程标准（2022年版）", kind="curriculum", author_or_institution="中华人民共和国教育部", publisher="人民教育出版社", published_year=2022, url_or_path="https://www.moe.gov.cn/srcsite/A26/s8001/202204/t20220420_619921.html", locator="历史课程核心素养与学业质量要求", citation_note="用于适龄目标、证据意识和历史解释。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-ndrc-erlitou", title="中华文明总进程的引领者：二里头文化", kind="archaeology", author_or_institution="国家发展和改革委员会社会发展司", publisher="国家发展和改革委员会", published_year=2022, url_or_path="https://www.ndrc.gov.cn/xwdt/ztzl/dyhgjwhgy/202209/t20220920_1335799_ext.html", locator="二里头遗址与都邑布局部分", citation_note="机构性综合说明；更肯定的夏都措辞按解释层呈现。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-nopss-erlitou-layout", title="二里头都城布局的新发现及其意义", kind="archaeology", author_or_institution="赵海涛 / 中国社会科学院考古研究所", publisher="全国哲学社会科学工作办公室", published_year=2021, url_or_path="https://www.nopss.gov.cn/n1/2021/0208/c219544-32025885.html", locator="中心区道路、宫殿、作坊与等级结构", citation_note="考古工作者对可观察遗存和历史解释的区分。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-npc-civilization", title="中华文明起源与早期发展综合研究", kind="research", author_or_institution="中华文明探源工程相关研究团队", publisher="中国人大网", published_year=2023, url_or_path="https://www.npc.gov.cn/npc/c2/c30834/202309/t20230901_431407.html", locator="二里头与伊洛河流域部分", citation_note="用于年代、区域、宫城和高等级产品作坊概览。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-pep-seven-history", title="义务教育教科书·中国历史七年级上册目录与课程位置", kind="textbook", author_or_institution="人民教育出版社", publisher="人民教育出版社", url_or_path="https://www.pep.com.cn/products/jc/czjks/201802/t20180227_1922743.shtml", locator="七年级上册早期国家相关单元", citation_note="仅用于主题与学段定位，不复制教材正文。", reliability="reviewed", rights_note=rights),
        EvidenceSourceV1(source_id="src-science-jishi", title="Outburst flood at 1920 BCE supports historicity of China's Great Flood and the Xia dynasty", kind="research", author_or_institution="Qinglong Wu et al.", publisher="Science", published_year=2016, url_or_path="https://doi.org/10.1126/science.aaf0842", locator="Science 353 (6299), pp. 579–582", citation_note="积石峡洪水与夏史连接的原始研究，结论存在后续争议。", reliability="disputed", rights_note=rights),
        EvidenceSourceV1(source_id="src-shangshu-yugong", title="《尚书·禹贡》", kind="primary_source", author_or_institution="传世文献；中国哲学书电子化计划底本索引", url_or_path="https://ctext.org/shang-shu/tribute-of-yu/zh", locator="九州、山川、贡赋相关文本", citation_note="文本层次和成篇问题需保留学术边界。", reliability="disputed", rights_note=rights),
        EvidenceSourceV1(source_id="src-shiji-xia", title="《史记·夏本纪》", kind="primary_source", author_or_institution="司马迁；中国哲学书电子化计划底本索引", publisher="传世文献", published_year=-90, url_or_path="https://ctext.org/shiji/xia-ben-ji/zh", locator="禹、治水、启继位相关叙事", citation_note="西汉成书，作为后世夏史叙事使用。", reliability="reviewed", rights_note=rights),
    ]
    return tuple(sorted(values, key=lambda item: item.source_id))


def _lookup_runtime_ids(package: CoursePackageV1):
    fact_ids = {item.statement: item.fact_id for item in package.facts}
    person_ids = {item.name: item.person_id for item in package.people}
    return fact_ids, person_ids


def build_dayu_evidence_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> evidence_workflow.EvidenceCorpusDraftV1:
    package = course_package_from_legacy(course_draft or build_dayu_course_draft())
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
        passage("dayu-p001", "src-moe-2022", "课程目标：从材料形成历史认识", "本课依据义务教育历史课程的核心素养取向，引导学生辨认材料类型、建立时序空间观念，并用证据支持有边界的历史解释。", "课堂不是判断故事好不好听，而是练习材料—判断—边界的论证链。", ("governance_model",), keywords=("历史解释", "证据边界"), evidence_kind="curriculum_goal", certainty="consensus", chronology_note="2022年公布的现代课程标准，用于教学目标而非古代事实。"),
        passage("dayu-p002", "src-moe-2022", "课程目标：理解早期国家", "早期国家主题应把政治权力、社会组织和物质遗存联系起来，避免只背王朝名称与年代。", "用公共治理与二里头材料连接权力秩序和社会代价。", ("erlitou_state", "costs"), keywords=("早期国家", "公共动员"), evidence_kind="curriculum_goal", certainty="consensus", chronology_note="现代课程目标。"),
        passage("dayu-p003", "src-pep-seven-history", "七年级内容位置", "人民教育出版社七年级上册把夏商周与早期国家置于学生初次系统学习中国古代史的阶段；本课据此控制概念数量和阅读难度。", "课程身份属于七年级早期国家学习，不复制教材章节。", ("chronology",), keywords=("七年级", "早期国家"), evidence_kind="curriculum_goal", certainty="consensus", chronology_note="现代教材目录和学段信息。"),
        passage("dayu-p004", "src-shiji-xia", "《夏本纪》的禹治水叙事", "《史记·夏本纪》系统叙述鲧、禹与洪水治理，是理解秦汉以来夏史框架的重要传世文本；它的成书年代远晚于传统禹时代。", "可证明西汉史家如何组织禹的故事，不能单独证明现场细节。", ("later_memory", "shiji_date"), people=("禹", "鲧"), keywords=("传世文献",), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="《史记》成书于西汉，晚于传统所述事件约两千年。"),
        passage("dayu-p005", "src-shiji-xia", "禹后启继位的王朝叙事", "《夏本纪》把禹、益与启的继承关系编入夏王朝开端，为后世讨论禅让与世袭转换提供了叙事框架。", "继承框架来自后世整理的王朝谱系。", ("succession",), people=("禹", "益（伯益）"), keywords=("世袭", "权力秩序"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="西汉文本对更早传统的整理。"),
        passage("dayu-p006", "src-shiji-xia", "公共责任的道德形象", "后世夏史叙事突出禹长期在外、以公共事务为先的形象，形成影响深远的政治伦理记忆。", "道德记忆重要，但具体次数和对白不可考古核验。", ("three_doors",), people=("禹",), keywords=("三过家门", "公共责任"), evidence_kind="transmitted_text", certainty="legend", chronology_note="后世传承的英雄叙事，不是同时代工作日志。"),
        passage("dayu-p007", "src-mengzi-tengwen", "战国论说中的疏河", "《孟子·滕文公上》以禹疏河、长期在外说明公共责任，把治水放进关于治理者职责的论辩。", "这段材料首先说明战国思想语境如何使用禹的形象。", ("mengzi_date", "block_dredge"), people=("禹",), keywords=("疏导", "公共责任"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="战国时期文本语境，晚于传统所述禹时代。"),
        passage("dayu-p008", "src-mengzi-tengwen", "三过家门的传承层", "《孟子》相关叙事包含禹在外多年、经过家门而不入的说法，展示这一母题在战国时期已经用于赞扬尽职。", "可研究母题传播，不能据此复原准确行程。", ("three_doors", "later_memory"), people=("禹",), keywords=("传说", "责任伦理"), evidence_kind="transmitted_text", certainty="legend", chronology_note="战国论说留下的后世记忆。"),
        passage("dayu-p009", "src-shangshu-yugong", "九州、山川与空间秩序", "《禹贡》以九州、山川、水道和贡赋组织天下空间，反映文本编纂者对地理与政治秩序的系统表达。", "它是空间思想材料，不是可直接套用的夏代施工图。", ("yugong_boundary", "map_layers"), keywords=("九州", "记忆地图"), evidence_kind="transmitted_text", certainty="disputed", chronology_note="传世文本的成篇与层累问题存在讨论。"),
        passage("dayu-p010", "src-shangshu-yugong", "治水与贡赋叙事", "《禹贡》把山川治理、土地差异和贡赋安排放进同一结构，说明后世叙事常把环境整治与政治秩序联系起来。", "从水土治理走向权力秩序是一种文本结构和教学解释。", ("governance_model", "yugong_boundary"), keywords=("贡赋", "权力秩序"), evidence_kind="transmitted_text", certainty="interpretation", chronology_note="后世传世文本，不作为禹时代制度清单。"),
        passage("dayu-p011", "src-chnmuseum-early-state", "博物馆的早期国家框架", "中国国家博物馆把夏商西周概括为早期国家形态形成和初步发展的阶段，并强调王权、政治结构与物质文化的变化。", "公共展陈提供课程结构，但具体判断仍需回到材料层级。", ("erlitou_state",), keywords=("早期国家", "王权"), evidence_kind="teaching_explanation", certainty="consensus", chronology_note="现代博物馆展陈说明。"),
        passage("dayu-p012", "src-chnmuseum-early-state", "二里头与夏史的时空重合", "国家博物馆说明二里头文化的分布地域和延续年代与传世文献中的夏人活动时空大体相合，因此是探索夏史的主要遗存。", "时空重合支持高度相关，不等于发现王朝自名。", ("erlitou_overlap", "erlitou_identity"), keywords=("二里头", "夏史"), evidence_kind="archaeological_evidence", certainty="interpretation", chronology_note="现代考古综合判断，材料年代约距今3800—3500年。"),
        passage("dayu-p013", "src-chnmuseum-early-state", "专业分工与高等级器物", "国家博物馆资料显示二里头时期已出现专业手工业分工、青铜礼器、玉石加工与绿松石镶嵌等复杂生产。", "专业生产和高等级器物帮助观察权力集中与社会分化。", ("erlitou_state",), keywords=("青铜", "专业分工"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="二里头文化时期的考古观察。"),
        passage("dayu-p014", "src-ndrc-erlitou", "大型都邑与广域影响", "国家发展改革委资料概述二里头大型都邑、宫城、城市道路、宫殿建筑、青铜礼器和官营作坊等发现。", "这些遗存支持集中规划和广域王权研究。", ("erlitou_state",), keywords=("都邑", "宫城", "道路网"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="对持续考古发现的现代综合。"),
        passage("dayu-p015", "src-ndrc-erlitou", "“夏都”措辞的解释层", "该机构资料采用“夏都斟鄩”等较肯定表述；课堂同时保留考古学命名与历史身份认定之间的推论步骤。", "公共机构结论也要标明它属于综合解释。", ("erlitou_identity", "no_yu_inscription"), keywords=("夏都", "解释边界"), evidence_kind="boundary_note", certainty="interpretation", chronology_note="现代机构性历史解释，不是遗物自证名称。"),
        passage("dayu-p016", "src-nopss-erlitou-layout", "井字形道路与功能分区", "二里头中心区的主干道路把都邑划分为规整区域，宫殿、作坊、祭祀与贵族居住墓葬空间呈现明确组织。", "城市布局是讨论统治能力和等级秩序的直接材料。", ("erlitou_state",), keywords=("道路网", "功能分区"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="现代田野考古对二里头遗迹的观察与复原。"),
        passage("dayu-p017", "src-nopss-erlitou-layout", "从遗址到夏史的综合判断", "考古研究者依据年代、地域、发展程度和文献对应关系，认为二里头极可能与夏后期王朝遗存相关。", "“极可能”呈现证据强度，仍区别于直接文字确认。", ("erlitou_overlap", "erlitou_identity"), keywords=("考古判断", "二里头"), evidence_kind="scholarly_interpretation", certainty="interpretation", chronology_note="现代考古与文献综合判断。"),
        passage("dayu-p018", "src-npc-civilization", "伊洛河流域与年代范围", "探源工程综合资料把二里头置于伊洛河流域，并概述其约距今3800—3500年的年代和大型中心地位。", "区域和年代重合是重要联系证据。", ("erlitou_overlap", "chronology"), keywords=("伊洛河", "年代"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="现代测年与区域研究的概括。"),
        passage("dayu-p019", "src-npc-civilization", "宫城、作坊与礼器", "综合研究资料列出宫城、高等级产品作坊、青铜与玉礼器及广泛影响，显示资源和礼仪活动存在集中控制。", "可用于解释早期国家能力，不直接说明具体治水组织。", ("erlitou_state", "governance_model"), keywords=("宫城", "作坊", "礼器"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="二里头文化考古材料及现代解释。"),
        passage("dayu-p020", "src-science-jishi", "积石峡堰塞湖溃决假说", "2016年研究提出黄河上游积石峡曾形成堰塞湖并发生大型溃决洪水，给出约公元前1920年的时间判断。", "这是特定地点自然事件的研究假说。", ("jishi_event",), keywords=("积石峡", "溃决洪水"), evidence_kind="scholarly_interpretation", certainty="disputed", chronology_note="现代地质与考古测年研究，事件约公元前1920年。"),
        passage("dayu-p021", "src-science-jishi", "从洪水到夏史的推论", "原研究进一步讨论积石峡洪水与中国大洪水传说、夏代年代之间的可能联系，这一步超出了单纯确认自然事件。", "自然事件、文化记忆和王朝身份是三段不同推论。", ("jishi_event", "map_layers"), keywords=("推论链", "夏史"), evidence_kind="scholarly_interpretation", certainty="disputed", chronology_note="2016年研究提出的历史连接假说。"),
        passage("dayu-p022", "src-allan-jishi", "洪水传说不能由单点独占解释", "Sarah Allan 的讨论肯定新材料值得重视，同时提醒洪水传说有复杂的文本与思想传统，单个局地事件不能自动解释全部叙事。", "应把地质证据与文本传播分别检验。", ("jishi_event", "later_memory"), keywords=("洪水传说", "证据边界"), evidence_kind="scholarly_interpretation", certainty="interpretation", chronology_note="2017年对2016年研究的学术反思。"),
        passage("dayu-p023", "src-allan-jishi", "人物与王朝仍需独立证据", "即使接受积石峡发生过大洪水，从灾害到禹这一人物、再到夏王朝开端，仍需要各自的材料与年代链支持。", "不得把“有洪水”缩写成“禹和夏已被证明”。", ("jishi_event", "no_yu_inscription"), people=("禹",), keywords=("人物证据", "王朝证据"), evidence_kind="boundary_note", certainty="consensus", chronology_note="现代方法论边界。"),
        passage("dayu-p024", "src-loc-yuji-map", "1136年的《禹迹图》", "美国国会图书馆馆藏记录把《禹迹图》标为1136年石刻地图相关拓本，它属于南宋时期的地图传统。", "地图本身比传统禹时代晚数千年。", ("map_layers",), keywords=("禹迹图", "南宋"), evidence_kind="archaeological_evidence", certainty="consensus", chronology_note="地图刻制年代为1136年。"),
        passage("dayu-p025", "src-loc-yuji-map", "记忆地图而非施工图", "《禹迹图》展示后世如何把河流、疆域与大禹文化记忆结合，是研究地图史和历史记忆的材料。", "不能据此给夏代工程标注精确坐标。", ("map_layers", "yugong_boundary"), keywords=("记忆地图", "空间边界"), evidence_kind="boundary_note", certainty="consensus", chronology_note="南宋材料用于研究南宋及其继承的知识传统。"),
        passage("dayu-p026", "src-chnmuseum-early-state", "没有同时代“禹”铭文的边界", "二里头的都邑、器物和空间结构十分丰富，但当前公开材料并未提供一条得到学界公认、可同时代直读为“禹”的铭文。", "物质复杂性不能替代人物姓名证据。", ("no_yu_inscription", "erlitou_identity"), people=("禹",), keywords=("铭文", "考古边界"), evidence_kind="boundary_note", certainty="consensus", chronology_note="针对当前公开考古证据状况的边界说明。"),
        passage("dayu-p027", "src-moe-2022", "治理模型不是历史统计", "六项变量把洪水风险、粮食、劳作者状态、信任、地形知识和协作并列，帮助学生看见决策关系。它们没有对应的夏代统计表。", "关卡用结构化模型练习因果与权衡。", ("governance_model", "costs"), keywords=("变量", "教学模型"), evidence_kind="teaching_explanation", certainty="interpretation", chronology_note="V0.10现代课堂设计。"),
        passage("dayu-p028", "src-mengzi-tengwen", "英雄叙事之外的协作", "传世文本常把功绩集中到禹，但治水叙事本身包含任命、协作者与广泛劳作。课堂据此加入益、聚落代表和劳作者，避免把公共工程缩成一人动作。", "群体角色是有依据的教学建模，不是假造具名人物。", ("governance_model", "costs"), people=("益（伯益）", "聚落代表", "治水劳作者"), keywords=("协作", "劳动"), evidence_kind="teaching_explanation", certainty="interpretation", chronology_note="由传世叙事主题形成的现代教学表达。"),
        passage("dayu-p029", "src-chnmuseum-early-state", "年代使用约数", "国家博物馆以约公元前21世纪等框架介绍夏朝建立，并以二里头材料探索夏史。课堂沿用约数，同时提醒这不是同时代精确纪年。", "年代框架用于排序，不应伪装成某年某日。", ("chronology", "erlitou_overlap"), keywords=("年代框架",), evidence_kind="boundary_note", certainty="interpretation", chronology_note="现代研究和教学使用的约数。"),
        passage("dayu-p030", "src-moe-2022", "卷宗的证据链", "史官卷宗要求保存选择、状态变化、代价、历史解释与来源，并用“观察—判断—边界—修正”完成复盘。", "学习成果记录推理过程，而不只记录胜负。", ("governance_model", "costs"), keywords=("史官卷宗", "复盘"), evidence_kind="teaching_explanation", certainty="consensus", chronology_note="V0.10现代课堂评价设计。"),
    ]
    return evidence_workflow.EvidenceCorpusDraftV1(
        corpus_id=DAYU_CORPUS_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="L101 大禹治水正式证据库",
        scope_note=(
            "仅服务 C-prequin-state/L101 的精确发布。材料分为课程目标、传世文本、"
            "考古观察、学术解释与边界说明；角色回答不得越过当前片段，也不得把教学模型当史实。"
        ),
        sources=_evidence_sources(),
        passages=tuple(sorted(passages, key=lambda item: item.passage_id)),
    )


def build_dayu_scenario_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> scenario_authoring.ScenarioAuthorDraftV1:
    package = course_package_from_legacy(course_draft or build_dayu_course_draft())
    fact_ids, person_ids = _lookup_runtime_ids(package)
    source_ids = {item.title: item.source_id for item in package.source_refs}

    def facts(*keys: str) -> list[str]:
        return sorted(fact_ids[FACTS[key]] for key in keys)

    yu = person_ids["禹"]
    yi = person_ids["益（伯益）"]
    representatives = person_ids["聚落代表"]
    workers = person_ids["治水劳作者"]

    C = scenario_authoring.ScenarioDraftConditionV1
    E = scenario_authoring.ScenarioDraftEffectV1
    return scenario_authoring.ScenarioAuthorDraftV1(
        scenario_id=DAYU_SCENARIO_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="六回合治水议事：水退之后，秩序如何留下",
        scenario_type="crisis_governance",
        student_role="跨聚落治水共同体的议事记录者",
        objective="在六回合内降低洪水风险，同时守住粮食、劳作者状态、公共信任、地形知识与协作能力，并解释每次取舍的证据与代价。",
        opening="连日降雨后，河道漫出旧岸。低地聚落请求立刻加固，上游观察者主张先看地形，粮仓管理者提醒播种期将近。你必须记录并协调六次共同决策。数值是课堂模型，不是夏代统计。",
        max_turns=6,
        variables=[
            scenario_authoring.ScenarioDraftVariableV1(variable_id="flood-risk", label="洪水风险", description="越低越安全；极端工程也可能把风险转移到别处。", initial=82, minimum=0, maximum=100),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="grain-reserve", label="粮食储备", description="工程与赈济都会消耗口粮；越高越能维持聚落。", initial=62, minimum=0, maximum=100),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="labor-wellbeing", label="劳作者状态", description="综合轮换、伤病风险与家庭生计；越高越可持续。", initial=66, minimum=0, maximum=100),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="public-trust", label="聚落信任", description="不同聚落对方案公平、透明与兑现程度的判断。", initial=48, minimum=0, maximum=100),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="terrain-knowledge", label="地形认知", description="对支流、低地和分洪方向的共同记录。", initial=22, minimum=0, maximum=100),
            scenario_authoring.ScenarioDraftVariableV1(variable_id="coordination", label="协作能力", description="跨聚落分工、信息共享与执行承诺的能力。", initial=34, minimum=0, maximum=100),
        ],
        npcs=[
            scenario_authoring.ScenarioDraftNpcV1(person_id=yu, display_name="禹", role="治水组织者", persona="重视地形、协作和公共责任；角色化教学表达，不是史料原话。", boundaries=["不把传说细节说成同时代事实。", "不知道后世考古和现代数值。"], initial_attitude=15, initial_trust=25, fact_refs=facts("later_memory", "block_dredge")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=yi, display_name="益（伯益）", role="勘察与协作顾问", persona="要求先记录、再复核、后行动；角色化教学表达，不是史料原话。", boundaries=["不虚构行程和对话。", "证据不足时明确停下。"], initial_attitude=10, initial_trust=20, fact_refs=facts("later_memory", "governance_model")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=representatives, display_name="聚落代表", role="多聚落意见群体", persona="追问风险与资源分配是否公平；角色化教学表达，不是史料原话。", boundaries=["合成群体，不代表全部史前居民。", "不虚构人口数字。"], initial_attitude=0, initial_trust=5, fact_refs=facts("costs", "governance_model")),
            scenario_authoring.ScenarioDraftNpcV1(person_id=workers, display_name="治水劳作者", role="工程劳动群体", persona="关注轮换、口粮与安全；角色化教学表达，不是史料原话。", boundaries=["合成群体，不是假冒出土自述。", "不虚构工具和伤亡。"], initial_attitude=0, initial_trust=5, fact_refs=facts("costs", "block_dredge")),
        ],
        action_rules=[
            scenario_authoring.ScenarioDraftActionV1(
                action_id="survey-waterways", label="踏勘支流与低地", description="暂缓大工程，分组记录水势、低地和可分流方向。", aliases=["踏勘", "勘察水道", "先看地形"],
                effects=[E(variable_id="flood-risk", value=3), E(variable_id="grain-reserve", value=-3), E(variable_id="terrain-knowledge", value=20), E(variable_id="public-trust", value=2), E(kind="npc", person_id=yi, attitude_delta=3, trust_delta=6, reveal_fact_refs=facts("map_layers"))],
                feedback="勘察占用了时间和口粮，水势仍在上涨；但支流、低地和受影响聚落第一次出现在同一张记录上。", fact_refs=facts("map_layers", "governance_model"),
            ),
            scenario_authoring.ScenarioDraftActionV1(
                action_id="dredge-diversion", label="依地形疏浚分流", description="依据已经形成的地形记录开挖、清障并分导水流。", aliases=["疏导", "开渠分洪", "疏浚"], available_when=[C(variable_id="terrain-knowledge", operator="gte", value=40)],
                effects=[E(variable_id="flood-risk", value=-20), E(variable_id="grain-reserve", value=-7), E(variable_id="labor-wellbeing", value=-10), E(variable_id="coordination", value=4), E(kind="npc", person_id=yu, attitude_delta=4, trust_delta=5, reveal_fact_refs=facts("block_dredge")), E(kind="npc", person_id=workers, attitude_delta=-2, trust_delta=-4)],
                feedback="有地形记录的疏浚显著降低了水患，但连续施工消耗口粮与体力。方法有效不等于代价可以忽略。", fact_refs=facts("block_dredge", "costs"),
            ),
            scenario_authoring.ScenarioDraftActionV1(
                action_id="reinforce-settlements", label="加固聚落关键岸段", description="优先保护住房、粮仓和饮水点，给后续方案争取时间。", aliases=["加固河岸", "护住聚落", "修临时堤"],
                effects=[E(variable_id="flood-risk", value=-10), E(variable_id="grain-reserve", value=-5), E(variable_id="labor-wellbeing", value=-7), E(variable_id="public-trust", value=8), E(kind="npc", person_id=representatives, attitude_delta=4, trust_delta=7, reveal_fact_refs=facts("block_dredge"))],
                feedback="关键岸段暂时稳住，居民看到直接保护；但这只是组合措施，不能证明所有地方都应一味筑堵。", fact_refs=facts("block_dredge", "costs"),
            ),
            scenario_authoring.ScenarioDraftActionV1(
                action_id="rotate-labor", label="轮换劳作并设安全线", description="减少连续强征，让各聚落轮换施工、耕作和照料家庭。", aliases=["轮换", "让劳作者休整", "安全施工"],
                effects=[E(variable_id="flood-risk", value=5), E(variable_id="grain-reserve", value=-5), E(variable_id="labor-wellbeing", value=15), E(variable_id="coordination", value=8), E(kind="npc", person_id=workers, attitude_delta=7, trust_delta=10, reveal_fact_refs=facts("costs"))],
                feedback="工程速度暂时下降，但轮换让劳作者恢复，也让跨聚落分工更可持续。", fact_refs=facts("costs", "governance_model"),
            ),
            scenario_authoring.ScenarioDraftActionV1(
                action_id="share-map-plan", label="公开水图并共同议事", description="把地形记录、粮食消耗和风险方向公开，由各聚落共同修订方案。", aliases=["公开方案", "共同议事", "分享水图"],
                effects=[E(variable_id="flood-risk", value=2), E(variable_id="terrain-knowledge", value=8), E(variable_id="public-trust", value=13), E(variable_id="coordination", value=16), E(kind="npc", person_id=representatives, attitude_delta=8, trust_delta=12, reveal_fact_refs=facts("governance_model")), E(kind="npc", person_id=yi, attitude_delta=3, trust_delta=5)],
                feedback="议事没有立刻退水，却减少了上下游猜疑；方案、代价和承诺开始可以共同检查。", fact_refs=facts("governance_model", "costs"),
            ),
            scenario_authoring.ScenarioDraftActionV1(
                action_id="release-emergency-grain", label="开仓赈济受灾家庭", description="优先维持饮食与迁居，让受灾家庭和劳作者不必在生存压力下退出协作。", aliases=["赈济", "开仓", "发放口粮"],
                effects=[E(variable_id="flood-risk", value=4), E(variable_id="grain-reserve", value=-15), E(variable_id="labor-wellbeing", value=10), E(variable_id="public-trust", value=12), E(kind="npc", person_id=representatives, attitude_delta=6, trust_delta=10), E(kind="npc", person_id=workers, attitude_delta=5, trust_delta=8)],
                feedback="粮仓明显下降，但最脆弱的家庭得到喘息。治理是否公正，也会影响方案能否继续执行。", fact_refs=facts("costs", "governance_model"),
            ),
            scenario_authoring.ScenarioDraftActionV1(
                action_id="force-emergency-dikes", label="强征人力抢筑长堤", description="不等待充分勘察，集中人力在主河段抢筑防线。", aliases=["强征筑堤", "抢筑长堤", "集中人力"],
                effects=[E(variable_id="flood-risk", value=-18), E(variable_id="grain-reserve", value=-4), E(variable_id="labor-wellbeing", value=-18), E(variable_id="public-trust", value=-9), E(variable_id="coordination", value=2), E(kind="npc", person_id=workers, attitude_delta=-10, trust_delta=-12, reveal_fact_refs=facts("costs")), E(kind="npc", person_id=representatives, attitude_delta=-5, trust_delta=-7)],
                feedback="水位压力迅速缓解，但强征透支劳作者并损害信任。水退不等于治理没有留下伤痕。", fact_refs=facts("block_dredge", "costs"),
            ),
        ],
        event_rules=[
            scenario_authoring.ScenarioDraftEventV1(
                event_id="seasonal-rain-surge", title="第三轮强降雨", match="all", trigger=[C(kind="turn", operator="gte", value=3)], effects=[E(variable_id="flood-risk", value=8), E(variable_id="grain-reserve", value=-4)], narrative="第三轮后强降雨抵达：水势反弹，部分储粮受潮。任何方案都必须经受环境变化。", once=True, priority=10, fact_refs=facts("governance_model"),
            ),
            scenario_authoring.ScenarioDraftEventV1(
                event_id="coordinated-workfront", title="协作工段形成", match="all", trigger=[C(variable_id="coordination", operator="gte", value=65), C(variable_id="terrain-knowledge", operator="gte", value=50)], effects=[E(variable_id="flood-risk", value=-10), E(variable_id="labor-wellbeing", value=5), E(variable_id="public-trust", value=4)], narrative="公开地图与分工让多个工段互相衔接：重复劳动减少，风险进一步下降。", once=True, priority=20, fact_refs=facts("governance_model", "costs"),
            ),
            scenario_authoring.ScenarioDraftEventV1(
                event_id="exhaustion-warning", title="劳作透支", match="all", trigger=[C(variable_id="labor-wellbeing", operator="lte", value=25)], effects=[E(variable_id="flood-risk", value=7), E(variable_id="public-trust", value=-5)], narrative="连续劳作造成伤病与离队，未完成的工段开始反噬水势；短期强度变成新的风险。", once=True, priority=30, fact_refs=facts("costs"),
            ),
        ],
        ending_rules=[
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-balanced-success", title="共治成渠", match="all", conditions=[C(kind="turn", operator="gte", value=6), C(variable_id="flood-risk", operator="lte", value=30), C(variable_id="public-trust", operator="gte", value=68), C(variable_id="labor-wellbeing", operator="gte", value=38), C(variable_id="terrain-knowledge", operator="gte", value=55), C(variable_id="coordination", operator="gte", value=60)],
                summary="洪水风险降到可控范围，地形记录、公开议事和可持续分工也留下来。共同体记住的不只是一位首领，还有一套可复核的协作方法。",
                historical_explanation="这是课堂中的平衡成功模型：它帮助解释公共治理怎样可能增加权威，同时以信任、记录和责任约束权力；不能反推真实禹时代拥有同样制度。",
                major_costs=["消耗部分粮食与耕作时间", "疏浚仍给劳作者带来压力", "各聚落必须持续兑现公开承诺"],
                source_ref_ids=sorted([source_ids["《孟子·滕文公上》"], source_ids["古代中国：夏商西周时期"], source_ids["义务教育历史课程标准（2022年版）"]]), fact_refs=facts("governance_model", "costs", "erlitou_state"), priority=10,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-costly-success", title="水退而人疲", match="all", conditions=[C(kind="turn", operator="gte", value=6), C(variable_id="flood-risk", operator="lte", value=32), C(variable_id="labor-wellbeing", operator="lte", value=37)],
                summary="主要水患被压下，但强征与连续工程透支了劳作者，聚落之间留下怨气。史官必须同时写下功绩与代价。",
                historical_explanation="英雄叙事常聚焦治水成功；本结局用教学变量补回普通劳作者和资源消耗，但这些数值不是夏代统计。",
                major_costs=["劳作者状态严重下降", "信任可能受损", "短期工程成果需要长期修复社会关系"],
                source_ref_ids=sorted([source_ids["《史记·夏本纪》"], source_ids["《孟子·滕文公上》"], source_ids["义务教育历史课程标准（2022年版）"]]), fact_refs=facts("costs", "three_doors", "governance_model"), priority=20,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-negotiated-compromise", title="分段退水，留下争议", match="all", conditions=[C(kind="turn", operator="gte", value=6), C(variable_id="flood-risk", operator="lte", value=55), C(variable_id="public-trust", operator="gte", value=52)],
                summary="关键聚落暂时安全，协商避免了共同体瓦解，但部分河段仍需后续治理。你保住了继续合作的条件，没有制造完美神话。",
                historical_explanation="折中结局提示历史行动常是不完整的阶段成果。后世把复杂过程集中到英雄身上，课堂复盘则保留未解决问题。",
                major_costs=["部分地区仍承受较高水患", "粮食和时间已被消耗", "下一阶段仍需重新协商"],
                source_ref_ids=sorted([source_ids["《尚书·禹贡》"], source_ids["义务教育历史课程标准（2022年版）"]]), fact_refs=facts("later_memory", "costs", "governance_model"), priority=30,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-governance-failure", title="洪水与失序并行", match="all", conditions=[C(kind="turn", operator="gte", value=6)],
                summary="六轮结束时水患仍未进入可控范围，或共同体已无力持续执行方案。失败不归咎于一个按钮，而要回看信息、资源、时机与公平怎样相互作用。",
                historical_explanation="这是规则兜底的失败结局，用于训练因果复盘；它不声称对应某次真实史前灾害。",
                major_costs=["洪水风险仍高", "资源被消耗却未形成稳定方案", "聚落可能退出共同治理"],
                source_ref_ids=sorted([source_ids["义务教育历史课程标准（2022年版）"], source_ids["Outburst flood at 1920 BCE supports historicity of China's Great Flood and the Xia dynasty"]]), fact_refs=facts("jishi_event", "costs", "governance_model"), priority=1000,
            ),
        ],
        fact_refs=sorted(fact_ids.values()),
        source_ref_ids=sorted(source_ids.values()),
        dossier_template=scenario_authoring.ScenarioDraftDossierV1(
            title_template="《{scenario_title}·史官卷宗》",
            reflection_questions=[
                "哪一次选择最改变水患走势？请引用该回合的变量变化和事实依据。",
                "你的结局保护了谁、让谁承担了代价？还有哪一种组合可能更公平？",
                "卷宗中的哪一段属于传说、传世文献、考古判断或教学解释？",
                "如果新增一条同时代文字或新的洪水测年，你会修改哪项结论，为什么？",
            ],
            knowledge_node_kinds=["evidence", "claim", "boundary", "cause", "consequence", "cost"],
        ),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_dayu_presentation(
    content_root: Path,
    *,
    sealed_by: str,
    sealed_at: datetime | None = None,
    presentation_version: int = 1,
) -> LessonPresentationV1:
    root = Path(f"media/lessons/L101/v{presentation_version:03d}")
    video = root / "dayu-intro.mp4"
    poster = root / "dayu-poster.webp"
    transcript = root / "dayu-transcript.md"
    provisional = LessonPresentationV1(
        presentation_id=DAYU_PRESENTATION_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        presentation_version=presentation_version,
        title="大禹治水：四层证据课堂导读",
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
            "无声 HyperFrames 中文动画；关键信息全部写入画面并提供本地 Markdown 文字稿，学生可随时跳过。"
            if presentation_version >= 2
            else "无声中文文字导读；关键信息全部写入画面并提供本地 Markdown 文字稿，学生可随时跳过。"
        ),
        sealed_at=sealed_at or datetime.now(timezone.utc),
        sealed_by=sealed_by,
        checksum="0" * 64,
    )
    return sign_evidence_contract(provisional)


__all__ = [
    "BODY",
    "COURSE_ID",
    "DAYU_CORPUS_ID",
    "DAYU_PRESENTATION_ID",
    "DAYU_SCENARIO_ID",
    "FACTS",
    "LESSON_ID",
    "build_dayu_course_draft",
    "build_dayu_evidence_draft",
    "build_dayu_presentation",
    "build_dayu_scenario_draft",
]
