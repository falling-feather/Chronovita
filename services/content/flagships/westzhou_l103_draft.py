"""Unreviewed authoring draft for the current teacher lesson C-prequin-state/L103.

This source describes Western Zhou enfeoffment and lineage relations. It is
separate from the historically named ``shangyang_l103`` files, which remain
the source for the old Shang Yang lesson now bound to L105.
"""

from __future__ import annotations

from services import content
from services.content import evidence_workflow, scenario_authoring
from services.content.flagships.authoring_specs import (
    EvidencePassageSpec,
    LessonSourceSpec,
    evidence_fact_refs,
    load_teacher_lesson,
    merge_lesson_source_refs,
    package_indexes,
)
from services.contracts.evidence_v1 import EvidencePassageV1, EvidenceSourceV1


COURSE_ID = "C-prequin-state"
LESSON_ID = "L103"
LESSON_TITLE = "西周分封与宗法"
SCENARIO_ID = "westzhou-l103-relationship-map"
CORPUS_ID = "westzhou-l103-evidence"
TEACHER_SOURCE_ID = "teacher-l103"


SOURCE_SPECS = (
    LessonSourceSpec(
        "shiji-zhou",
        "《史记·周本纪》",
        "primary_source",
        "司马迁；中国哲学书电子化计划底本索引",
        "中国哲学书电子化计划",
        "https://ctext.org/shiji/zhou-ben-ji/zhs",
        "武王克商、周初分封及周公相关叙述；篇章定位见《史记·周本纪》",
        "西汉传世叙事；用来分析后世史家怎样讲周初事件，不作现场记录。",
    ),
    LessonSourceSpec(
        "nopss-zhou-rites",
        "周代礼制发展史",
        "research",
        "胡新生课题组；山东大学",
        "全国哲学社会科学工作办公室",
        "https://www.nopss.gov.cn/n1/2024/0509/c373410-40232165.html",
        "“成果的主要内容”及“西周早期礼制的基本认识”",
        "国家社科基金项目成果摘要；概述宗法观念、分封礼仪和礼制变化，不是西周现场档案。",
        published_year=2024,
    ),
    LessonSourceSpec(
        "moj-selection",
        "中国古代选官标准和方式的演变",
        "research",
        "郝铁川；河南大学法学院",
        "中华人民共和国司法部智慧普法平台（原载《法治日报》）",
        "https://legalinfo.moj.gov.cn/zhfxfzwh/fzwhfsgs/202303/t20230308_473682.html",
        "第111—114段；血缘姻缘标准及西周世卿世禄是否普遍的学术分歧",
        "法史综述明确记录不同研究观点；不能把单一概括说成无争议定论。",
        published_year=2023,
    ),
    LessonSourceSpec(
        "bjfsh-liulihe",
        "印记·琉璃河遗址 | 西周分封制的力证",
        "archaeology",
        "首都博物馆馆长、北京房山琉璃河遗址考古项目负责人",
        "北京市房山区人民政府（原载《北京日报》）",
        "https://www.bjfsh.gov.cn/zhxw/fsdt/202507/t20250725_40091097_fs.shtml",
        "“营城与治理”段落及克盉、克罍、作册奂器铭文说明",
        "考古项目负责人介绍遗址城圈与铭文；地面遗迹和铭文各自支持不同层次的判断。",
        published_year=2025,
    ),
    LessonSourceSpec(
        "chnmuseum-yan-hou-bowl",
        "“匽侯”青铜盂",
        "museum",
        "中国国家博物馆",
        "中国国家博物馆",
        "https://www.chnmuseum.cn/zp/zpml/kgfjp/202108/t20210802_250933.shtml",
        "藏品说明；器内五字铭文“匽侯作馈盂”及燕国封地说明",
        "馆藏器物页面支持该器物的铭文及馆方解释；单件器物不能独自证明所有封国规则。",
    ),
    LessonSourceSpec(
        "beijing-liulihe",
        "琉璃河西周燕都遗址",
        "archaeology",
        "房山区政务服务管理局",
        "北京市人民政府门户网站",
        "https://www.beijing.gov.cn/renwen/bjgk/fsgk/fswl/202303/t20230302_2927684.html",
        "遗址简介；城址、墓葬、建筑和出土材料概述",
        "政府门户的遗址简介；用于地点与遗迹类型概览，不代替发掘报告。",
        published_year=2025,
    ),
    LessonSourceSpec(
        "pku-liulihe",
        "北大考古与“百年百大考古发现”——北京琉璃河遗址",
        "research",
        "北京大学考古文博学院",
        "北京大学考古文博学院",
        "https://archaeology.pku.edu.cn/info/1030/3485.htm",
        "琉璃河考古队及1973—1977年西周墓地发掘回顾",
        "考古院系对发掘史的回顾；关于遗址性质仍按现有发掘资料表述。",
    ),
    LessonSourceSpec(
        TEACHER_SOURCE_ID,
        "教师课文：早期国家与社会变革·L103",
        "textbook",
        "Chronovita-Course-Content PR #49",
        "教师课程稿（当前快照）",
        "content/textbooks/C-prequin-state.json#L103",
        "L103 当前教师课文；地方治理、分封、宗法、礼制、燕国遗址与东迁段落",
        "只记录本课教学表述，不是独立历史史料；正文保持教师原文。",
    ),
)


FACTS = {
    "shiji-enfeoffment": "【传世叙事】《史记·周本纪》记述周初分封燕等诸侯；这是西汉史家对早周制度的追述。",
    "liulihe-location": "【考古地点】琉璃河遗址位于今北京房山；考古发掘发现城址、建筑、墓葬和西周青铜器。",
    "yan-hou-inscription": "【具体铭文】中国国家博物馆藏“匽侯”青铜盂内有五字铭文“匽侯作馈盂”；馆方据相关材料说明燕为周初封国。",
    "liulihe-inscriptions": "【考古材料】琉璃河出土多件带“匽侯”等铭文的青铜器，城址和墓葬材料共同支持该地与西周燕国的关联。",
    "city-layout": "【遗址解释】城圈、宫殿区、墓葬和其他设施可帮助讨论封国都城的规划；具体功能仍须依据发掘材料分别说明。",
    "fief-network": "【课程关系图】教师课文把周王、诸侯、卿大夫和士安排为政治等级；各层权力和职责不能被说成完全相同。",
    "vassal-duties": "【教学口径】朝贡、出兵和礼仪活动是当前教师课文列出的诸侯义务；逐项制度细节仍需对应具体史料。",
    "kinship-ritual": "【研究概括】研究者将西周早期部分礼制与宗法、族类观念联系起来，属于现代研究的概括。",
    "eldest-son": "【课程口径】教师课文以嫡长子继承说明宗法次序；该教学概括不等于每一封国或每个官职都只有一种实际继承方式。",
    "hereditary-office-debate": "【研究分歧】法史综述指出，西周是否普遍实行世卿世官制度存在学术争论，不能从血缘继承一项直接推出所有官职均世袭。",
    "ritual-rank": "【研究概括】礼制文本和现代研究讨论祭祀、朝会等身份秩序；具体器物和礼仪适用范围需要分材料核实。",
    "bronze-limits": "【材料边界】青铜器铭文可提供名称、册命或制作信息；单件铭文不能代替完整封国制度档案。",
    "east-move-dates": "【课程口径】当前教师课文以公元前771年镐京失守、约公元前770年迁都洛邑组织时间轴；年代与事件仍需按课程史料口径标注。",
    "central-local-change": "【历史解释】教师课文把诸侯力量发展与周王室控制力减弱联系起来；不能只用一条制度或一个事件解释西周结束。",
    "classroom-model": "【教学模拟】关系图分值、选项反馈和结束状态是现代学习工具，不是西周朝廷实况或人物对白。",
}


QA_POINTS = [
    "《史记·周本纪》与琉璃河遗址的青铜铭文分别能说明什么？它们形成的时间和材料类型一样吗？",
    "“匽侯作馈盂”这件器物能够直接告诉我们什么？哪些西周制度结论还要靠其他材料？",
    "周王、诸侯、卿大夫和士在教师课文的关系图中分别处于哪一层？诸侯拥有哪些地方权力？",
    "分封制与宗法制怎样连接土地、政治关系和家族次序？为什么不能把它们压成一个概念？",
    "嫡长子继承的课程说法，能否直接证明所有官员和封国都按同一方式继承？",
    "琉璃河遗址的城址、墓葬和铭文各自提供哪些证据？哪些结论属于考古解释？",
    "礼制怎样表达身份次序？后世礼书的总结能否当作每一次西周仪式的现场记录？",
    "怎样用“制度网络—材料出处—边界—变化”完成一张西周地方治理关系图？",
]


LEVEL_GOALS = [
    "能画出周王、诸侯、卿大夫、士的关系，并用教师课文中的职责区别各层。",
    "能说明分封与宗法分别处理哪些关系，以及它们怎样在西周政治中相连。",
    "能用琉璃河遗址和一条青铜铭文支持有限结论，并区分原物信息与研究解释。",
    "能标出世卿世官、礼仪细节和东迁年代中需要继续核对的来源边界。",
]


_PASSAGES = (
    EvidencePassageSpec(
        "shiji-zhou",
        "周初分封的传世叙述",
        "《史记·周本纪》把周初封诸侯写进武王克商后的政治安排。",
        "该篇可以定位后世对早周分封的叙述，不能当作同时代会谈记录。",
        ("shiji-enfeoffment", "bronze-limits"),
        ("周初分封", "《周本纪》"),
        "transmitted_text",
        "interpretation",
        "西汉史家对早周事件的追述。",
        people=("姬发（周武王）",),
    ),
    EvidencePassageSpec(
        "bjfsh-liulihe",
        "文献叙述中的燕国始封",
        "房山区考古文章转述《史记·周本纪》关于周初分封燕国的记载，并说明“北燕”地点曾是研究问题。",
        "传世记载提供名称和叙事，遗址材料帮助讨论地望。",
        ("shiji-enfeoffment", "liulihe-location"),
        ("燕国", "周初分封"),
        "scholarly_interpretation",
        "interpretation",
        "北京日报文章第17段；作者说明文献与考古的关系。",
        people=("姬发（周武王）",),
    ),
    EvidencePassageSpec(
        "beijing-liulihe",
        "琉璃河遗址的位置",
        "北京市政府页面将琉璃河遗址定位在北京房山区，并概述城址、墓葬、建筑等发现。",
        "这是遗址位置和材料类型的入口。",
        ("liulihe-location",),
        ("琉璃河遗址", "房山"),
        "archaeological_evidence",
        "consensus",
        "遗址简介，具体结论仍应回到发掘和馆藏材料。",
    ),
    EvidencePassageSpec(
        "beijing-liulihe",
        "从多类遗迹理解封国都城",
        "遗址简介列出城址、墓葬、车马坑和夯土建筑等不同遗迹。",
        "组合材料能支撑对城市功能的讨论，不能单凭简介复原完整行政流程。",
        ("liulihe-location", "city-layout"),
        ("城址", "墓葬", "夯土建筑"),
        "archaeological_evidence",
        "interpretation",
        "北京市政府遗址简介。",
    ),
    EvidencePassageSpec(
        "pku-liulihe",
        "琉璃河考古发掘与遗址性质",
        "北京大学考古文博学院回顾1973—1977年墓葬发掘，并说明出土青铜器等证据帮助确定遗址为西周早期燕都。",
        "考古判断依赖墓葬和青铜器等材料组合，不只依赖后世传说。",
        ("liulihe-location", "liulihe-inscriptions"),
        ("燕都", "西周早期", "考古发掘"),
        "scholarly_interpretation",
        "consensus",
        "院系对早期发掘工作的回顾。",
    ),
    EvidencePassageSpec(
        "bjfsh-liulihe",
        "多件“匽侯”铭文",
        "房山区考古文章提到多件青铜器铭文出现“匽侯”，这些材料参与了确认遗址性质的考古论证。",
        "多件器物和城址互相支持；一条铭文不能单独代表完整制度。",
        ("liulihe-inscriptions", "bronze-limits"),
        ("匽侯", "青铜器铭文"),
        "archaeological_evidence",
        "consensus",
        "房山区考古文章第27段。",
    ),
    EvidencePassageSpec(
        "bjfsh-liulihe",
        "城墙、宫殿和地方组织",
        "文章介绍遗址中发现城墙、城壕、建筑基址和墓葬，研究者据空间布局讨论燕都营建与地方治理。",
        "遗迹能够说明城邑规划线索；制度解释须标成研究推论。",
        ("city-layout", "fief-network"),
        ("城圈", "宫殿", "地方治理"),
        "scholarly_interpretation",
        "interpretation",
        "文章“营城与治理”部分。",
    ),
    EvidencePassageSpec(
        "bjfsh-liulihe",
        "克盉、克罍铭文",
        "文章转述克盉、克罍铭文中有关周王命令克在燕地受封的信息。",
        "铭文提供册命和封燕线索；它不自动说明每个诸侯义务的完整清单。",
        ("liulihe-inscriptions", "fief-network", "vassal-duties"),
        ("克盉", "克罍", "册命"),
        "archaeological_evidence",
        "consensus",
        "文章“营城与治理”第55段；现代释读由考古研究者提供。",
    ),
    EvidencePassageSpec(
        "chnmuseum-yan-hou-bowl",
        "“匽侯作馈盂”铭文",
        "中国国家博物馆介绍一件“匽侯”青铜盂，器内铸有五字铭文“匽侯作馈盂”。",
        "编号和铭文可以回到具体馆藏页面核对。",
        ("yan-hou-inscription", "bronze-limits"),
        ("匽侯", "馈盂", "铭文"),
        "archaeological_evidence",
        "consensus",
        "中国国家博物馆藏品说明第38—39段。",
    ),
    EvidencePassageSpec(
        "chnmuseum-yan-hou-bowl",
        "燕国封地与馆方说明",
        "馆方把燕视为周初分封诸侯，并结合琉璃河城址、贵族墓地和“匽侯”铭文说明遗址性质。",
        "这是馆方依据相关材料给出的解释；该盂在辽宁出土，不是琉璃河出土的那一件。",
        ("yan-hou-inscription", "liulihe-inscriptions", "bronze-limits"),
        ("燕国", "封国", "琉璃河"),
        "scholarly_interpretation",
        "interpretation",
        "中国国家博物馆藏品说明第38—39段。",
    ),
    EvidencePassageSpec(
        "nopss-zhou-rites",
        "西周礼制与宗法观念",
        "研究项目摘要将西周早期礼制中的部分变化与族类意识、宗法观念联系起来。",
        "这是现代研究的概括，不是某一次仪式的原始记录。",
        ("kinship-ritual", "ritual-rank"),
        ("宗法", "礼制"),
        "scholarly_interpretation",
        "interpretation",
        "成果摘要第38—43段。",
    ),
    EvidencePassageSpec(
        "nopss-zhou-rites",
        "分封和册命的礼仪关系",
        "研究摘要把分封诸侯、册命公卿、诸侯助祭等纳入周代礼制讨论。",
        "可以说明政治身份与礼仪相连；具体等级细则仍需相应材料。",
        ("kinship-ritual", "fief-network", "ritual-rank"),
        ("分封", "册命", "助祭"),
        "scholarly_interpretation",
        "interpretation",
        "研究项目对西周早期礼制的理论概括。",
    ),
    EvidencePassageSpec(
        "nopss-zhou-rites",
        "亲属次序和政治次序",
        "研究摘要讨论宗族伦理与政治伦理相连，并把西周礼制变化放在商周礼俗差异的研究框架中。",
        "这是一种学术解释，不能据此断言所有地方实践完全一致。",
        ("kinship-ritual", "fief-network"),
        ("亲亲", "尊尊", "宗族伦理"),
        "scholarly_interpretation",
        "interpretation",
        "研究项目成果摘要。",
    ),
    EvidencePassageSpec(
        "nopss-zhou-rites",
        "礼制发展不是同一时刻定型",
        "该研究把周代礼制的发展分作若干阶段，指出规范化和经典化发生在后续时期。",
        "不要把后来的礼书制度全部倒推成西周初年的统一规定。",
        ("ritual-rank", "classroom-model"),
        ("周代礼制", "年代层次"),
        "boundary_note",
        "interpretation",
        "研究项目提出的阶段解释。",
    ),
    EvidencePassageSpec(
        "moj-selection",
        "血缘与周代选官的概述",
        "法史综述把夏商周选官概括为较重血缘姻缘关系，并引用周初分封和亲属关系讨论政治身份。",
        "这是一篇现代概述，不能替代西周官职和家族个案材料。",
        ("kinship-ritual", "hereditary-office-debate"),
        ("血缘", "选官", "分封"),
        "scholarly_interpretation",
        "interpretation",
        "法史综述第111—112段。",
    ),
    EvidencePassageSpec(
        "moj-selection",
        "世卿世官说存在分歧",
        "文章第113段指出，学者对西周是否普遍实行世卿世官制度并非意见一致。",
        "血缘继承的教学概念不能直接推出每个官职都按同一种方式世袭。",
        ("hereditary-office-debate", "eldest-son"),
        ("世卿世官", "继承"),
        "boundary_note",
        "disputed",
        "法史综述第113段；记录作者所述学术争议。",
    ),
    EvidencePassageSpec(
        "moj-selection",
        "亲属关系不等于具体任命记录",
        "法史综述讨论宗法与选官，也提到《尚书·立政》中的择士说法。",
        "现有摘录不能代替对具体王命、铭文和封国实践的逐件核查。",
        ("hereditary-office-debate", "fief-network"),
        ("任官", "亲属关系"),
        "scholarly_interpretation",
        "interpretation",
        "作者对不同观点的比较。",
    ),
    EvidencePassageSpec(
        "teacher-l103",
        "教师课文中的地方治理网络",
        "当前教师课文把周王、诸侯、卿大夫、士和封国义务放进同一治理关系中。",
        "这是本课采用的教学框架；引用具体义务时应补上可返回的史料定位。",
        ("fief-network", "vassal-duties"),
        ("周王", "诸侯", "卿大夫", "士"),
        "teaching_explanation",
        "interpretation",
        "教师课文 L103 第3—4段；不是独立史料。",
    ),
    EvidencePassageSpec(
        "teacher-l103",
        "嫡长子继承的课程说法",
        "教师课文用嫡长子继承说明宗法次序，并联系贵族身份和封地。",
        "这是教学概括，不能由此断定每个地方官职都由同一继承规则决定。",
        ("eldest-son", "hereditary-office-debate"),
        ("宗法制", "嫡长子继承制"),
        "teaching_explanation",
        "interpretation",
        "教师课文 L103 第5段；任官范围需另核。",
    ),
    EvidencePassageSpec(
        "teacher-l103",
        "礼仪与等级的课程框架",
        "教师课文列举祭祀、朝会、婚丧、宴享等活动，说明礼仪与身份次序相连。",
        "课程框架不是每次西周礼仪的逐字记录。",
        ("ritual-rank", "kinship-ritual"),
        ("礼制", "身份等级"),
        "teaching_explanation",
        "interpretation",
        "教师课文 L103 第6段。",
    ),
    EvidencePassageSpec(
        "teacher-l103",
        "周公辅政与成王继位",
        "当前教师课文记述姬旦辅佐姬诵处理政务，并将其与周初治理东方相连。",
        "人物资料应回到教师段落和传世叙事，不补写未见于材料的密谈。",
        ("shiji-enfeoffment", "fief-network"),
        ("周公", "周成王", "辅政"),
        "teaching_explanation",
        "interpretation",
        "教师课文 L103 第2段；不是人物现场对白。",
        people=("姬旦（周公）", "姬诵（周成王）"),
    ),
    EvidencePassageSpec(
        "teacher-l103",
        "西周到东周的时间轴",
        "教师课文以约公元前771年和约公元前770年组织镐京失守与迁都洛邑的叙述。",
        "这些时间按课程时间轴保留；不能由一件燕国青铜器直接推出。",
        ("east-move-dates", "central-local-change"),
        ("镐京", "洛邑", "东周"),
        "curriculum_goal",
        "interpretation",
        "教师课文 L103 第7段；具体年代学出处待教师审校。",
        people=("姬宫湦（周幽王）",),
    ),
    EvidencePassageSpec(
        "bjfsh-liulihe",
        "西周燕都的城址与王族墓地",
        "考古文章概述琉璃河发现西周早期城址、墓葬和宫殿居址。",
        "遗址材料支持讨论地方政治中心，不会自行解释封国内的所有职权。",
        ("liulihe-location", "city-layout"),
        ("城址", "墓葬", "燕都"),
        "archaeological_evidence",
        "consensus",
        "考古文章第22—27段。",
    ),
    EvidencePassageSpec(
        "pku-liulihe",
        "出土材料确认燕国都城性质",
        "北京大学考古文博学院回顾，1970年代墓葬和铜器发掘帮助确定琉璃河遗址为西周早期燕都。",
        "考古结论依靠多类出土材料，不由一个后世地名传说得出。",
        ("liulihe-location", "liulihe-inscriptions"),
        ("燕国", "燕都", "铜器"),
        "scholarly_interpretation",
        "consensus",
        "院系对发掘工作的历史回顾。",
    ),
    EvidencePassageSpec(
        "bjfsh-liulihe",
        "铭文与周王命令的联系",
        "考古文章转述克盉、克罍铭文，指出其包含王命克在燕地受封的内容。",
        "铭文能支持具体册命线索，不等于完整记下每个诸侯的所有义务。",
        ("liulihe-inscriptions", "fief-network", "vassal-duties"),
        ("克盉", "克罍", "周王命令"),
        "archaeological_evidence",
        "consensus",
        "考古文章第55段；释文以该文为定位入口。",
    ),
    EvidencePassageSpec(
        "beijing-liulihe",
        "多类遗迹共同呈现燕都",
        "北京市政府遗址介绍列出城址、墓葬、车马坑和夯土建筑等材料。",
        "可以比较多类证据的用途，不能把旅游简介当作完整发掘报告。",
        ("liulihe-location", "city-layout"),
        ("城址", "墓葬", "车马坑"),
        "archaeological_evidence",
        "interpretation",
        "北京市政府门户遗址简介。",
    ),
    EvidencePassageSpec(
        "chnmuseum-yan-hou-bowl",
        "馆藏“匽侯”盂的铭文",
        "中国国家博物馆说明这件青铜盂的器内铸有“匽侯作馈盂”五字。",
        "铭文可以核验器物制作关系，不等同于一份封国制度总表。",
        ("yan-hou-inscription", "bronze-limits"),
        ("匽侯", "馈盂"),
        "archaeological_evidence",
        "consensus",
        "中国国家博物馆藏品页第38—39段。",
    ),
    EvidencePassageSpec(
        "teacher-l103",
        "关卡数值不是西周统计",
        "课堂活动用数值表现关系图、证据来源和过度概括风险。",
        "所有分值和情景均为现代学习工具，不是西周朝廷或人物对白。",
        ("classroom-model",),
        ("教学模拟", "关系图"),
        "boundary_note",
        "consensus",
        "现代课堂设计，不是历史材料。",
    ),
)


def _teacher_lesson():
    return load_teacher_lesson(COURSE_ID, LESSON_ID, LESSON_TITLE)


def build_l103_course_draft() -> content.LessonContentPackage:
    snapshot, lesson = _teacher_lesson()
    return content.LessonContentPackage(
        lesson_id=LESSON_ID,
        title=lesson["title"],
        unit=snapshot["title"],
        era=snapshot["era"],
        body=list(lesson["body"]),
        course_id=COURSE_ID,
        course_title=snapshot["title"],
        era_id=snapshot["era_id"],
        section=snapshot["section"],
        lesson_no=lesson.get("lesson_no", "1.3"),
        duration=lesson.get("duration", "09:10"),
        abstract=lesson.get("abstract", ""),
        keywords=[
            content.KeywordCard(
                word=item["word"],
                pinyin=item.get("pinyin", ""),
                gloss=item.get("gloss", ""),
            )
            for item in lesson.get("keywords", [])
        ],
        people=[
            content.PersonCard(
                name=item["name"],
                role=item.get("role", ""),
                summary=item.get("summary", ""),
                persona=item.get("persona", ""),
                boundaries=list(item.get("boundaries", [])),
            )
            for item in lesson.get("people", [])
        ],
        map_points=[
            content.MapPoint(
                label=item["label"],
                region=item.get("region", ""),
                lat=item.get("lat"),
                lng=item.get("lng"),
                note=item.get("note", ""),
                kind=item.get("kind", "site"),
            )
            for item in lesson.get("map_points", [])
        ],
        source_refs=merge_lesson_source_refs(lesson, SOURCE_SPECS),
        facts=list(FACTS.values()),
        qa_points=list(QA_POINTS),
        level_goals=list(LEVEL_GOALS),
        saga_material=content.MaterialPlaceholder(
            title="看：琉璃河燕国遗址与青铜铭文",
            objective="从具体城址和馆藏铭文辨认文献叙述、考古材料与制度解释。",
            notes="重点定位“匽侯作馈盂”和克盉、克罍相关报道；材料各自支持的范围不同。",
        ),
        sandbox_material=content.MaterialPlaceholder(
            title="练：画一张西周地方治理关系图",
            objective="用有限回合区分周王、诸侯、卿大夫、宗法关系和礼制证据。",
            notes="现代课堂关系图模拟；不模拟周王朝廷议，也不生成古人对白。",
        ),
        seed_canvas=[
            content.SeedCanvasNode(
                id="zhou-king",
                label="周王与王都",
                note="标记王都位置及课程中周王与封国的关系。",
            ),
            content.SeedCanvasNode(
                id="vassal-state",
                label="诸侯与封国",
                note="写出封地、地方事务及教师课文列出的义务。",
            ),
            content.SeedCanvasNode(
                id="lineage-relations",
                label="宗法与继承",
                note="标记血缘次序，并区分宗法概念与具体官职继承证据。",
            ),
            content.SeedCanvasNode(
                id="ritual-order",
                label="礼制与等级",
                note="说明礼仪如何表达身份次序，同时标注文献和研究年代。",
            ),
            content.SeedCanvasNode(
                id="yan-evidence",
                label="燕国证据",
                note="城址、墓葬、青铜器和铭文；分别写明直接记录与解释。",
            ),
            content.SeedCanvasNode(
                id="transition",
                label="西周结束与东迁",
                note="按教师时间轴记录事件，并把年代出处留在来源栏。",
            ),
        ],
        teacher_notes=(
            "开发初稿，待教师审校；教师正文、关键词、人物和地图点直接取自当前快照，未改写。"
            "活动是现代关系图整理模拟，不设置历史人物对话。分封、宗法、礼制和世卿世官须区分课程概括、传世文本、考古材料与现代研究。"
            "关于西周世卿世官制度是否普遍存在，法史综述指出有学术争论；不得把嫡长子继承直接推广到所有官职。"
        ),
    )


_ACTION_GROUPS = (
    (
        "capital",
        "先标出王都和地方",
        "关系图要怎样表现王都与远方封国的距离？",
        (
            (
                "map-caution",
                "标出位置和距离问题",
                "依教师课文标记镐京与东方地区，并写出远距离治理是本课提出的问题。",
                ("标出王都", "说明距离"),
                "地图表现出治理需要把王都和地方联系起来。",
                (12, 10, 7, -6),
                ("fief-network", "liulihe-location"),
            ),
            (
                "king-alone",
                "只画一条王命",
                "把地方治理画成周王一人直接管理所有家庭，不显示封国层级。",
                ("全部由周王管理", "不需要诸侯"),
                "关系图忽略了课程提到的地方贵族和封国层级。",
                (3, 2, -4, 14),
                ("fief-network",),
            ),
            (
                "show-questions",
                "列出三类治理问题",
                "把王都距离、地方势力和商人聚居地列为周王室需要处理的问题。",
                ("列出地方问题", "不急着下制度结论"),
                "先把课程的问题背景列清楚，再进入制度关系。",
                (9, 7, 10, -4),
                ("fief-network", "classroom-model"),
            ),
            (
                "pause-source",
                "先停下补出处",
                "暂不画制度结论，先把“东方地区情况”需要核对的材料列入清单。",
                ("先暂停", "请老师补材料"),
                "记录来源缺项并暂停提交，也是可靠的整理选择。",
                (0, 2, 2, -3),
                ("fief-network",),
            ),
        ),
    ),
    (
        "yan",
        "用燕国遗址核对封国",
        "哪一件材料最容易回到原物？",
        (
            (
                "cite-bowl",
                "定位馆藏青铜盂",
                "写出国家博物馆“匽侯”青铜盂的五字铭文和馆方解释。",
                ("写匽侯作馈盂", "查国家博物馆"),
                "器物和铭文有具体页面，读者可以回到馆藏条目核对。",
                (10, 18, 8, -8),
                ("yan-hou-inscription", "bronze-limits"),
            ),
            (
                "equate-one-inscription",
                "一条铭文解释全部制度",
                "用一件青铜盂直接写出所有封国的完整规则。",
                ("一件器物证明全部规则", "所有诸侯都一样"),
                "一件器物不能替代多地材料或制度档案。",
                (2, 5, -5, 15),
                ("yan-hou-inscription", "bronze-limits"),
            ),
            (
                "combine-site",
                "并列城址和墓葬",
                "把城墙、宫殿区、贵族墓和铭文放在一起，并标出这是考古解释。",
                ("结合遗址材料", "标注是推论"),
                "多种材料互相补充，结论也保留了考古推理层。",
                (13, 16, 10, -7),
                ("liulihe-location", "liulihe-inscriptions", "city-layout"),
            ),
        ),
    ),
    (
        "fief",
        "区分封国层级和义务",
        "如何避免把所有人的权力画成一样？",
        (
            (
                "distinguish-levels",
                "区分不同层级",
                "分别画出周王、诸侯、卿大夫和士，并只填入教师课文明确列出的关系与职责。",
                ("分层画图", "区分周王诸侯"),
                "图上有层级，也没有把每一层的权力说成相同。",
                (13, 9, 18, -8),
                ("fief-network", "vassal-duties"),
            ),
            (
                "same-everywhere",
                "每个封国都完全相同",
                "把所有封国的面积、义务和地方安排画成同一模板，不标来源。",
                ("所有封国都一样", "统一照搬"),
                "相同模板掩盖了地方差异，也没有证据说明各地执行完全一致。",
                (5, 2, -8, 13),
                ("fief-network", "vassal-duties"),
            ),
            (
                "mark-teacher-claims",
                "标注课程义务口径",
                "把朝贡、出兵和礼仪活动标成教师课文所列义务，并注明具体制度实例待查。",
                ("标注教师课文", "义务实例待补"),
                "课程框架和可返回的具体制度材料分开记录。",
                (9, 12, 12, -5),
                ("vassal-duties", "classroom-model"),
            ),
        ),
    ),
    (
        "lineage",
        "连接宗法和政治身份",
        "血缘次序能说明到哪一步？",
        (
            (
                "separate-rules",
                "区分宗法与任官",
                "呈现教师课文的嫡长子继承概念，同时标出它不能证明所有官职都按同一种方式世袭。",
                ("宗法不等于全部任官", "标出范围"),
                "家族继承和官职安排有关联，但仍需各自找证据。",
                (10, 12, 17, -8),
                ("eldest-son", "hereditary-office-debate"),
            ),
            (
                "all-offices-hereditary",
                "所有官职都写成世袭",
                "把嫡长子继承规则直接扩展为西周所有官位和所有地方的统一事实。",
                ("官职全部世袭", "没有学术争议"),
                "这个结论超过本课材料，且忽略了研究分歧。",
                (2, 4, -8, 16),
                ("eldest-son", "hereditary-office-debate"),
            ),
            (
                "mark-ritual-layer",
                "把礼书和研究分层",
                "说明后世礼制文献如何整理宗法观念，再把西周实践的材料需求列出来。",
                ("标出后世整理", "区分礼书与实物"),
                "思想总结和西周遗址材料没有被当成同一年代。",
                (8, 14, 15, -6),
                ("kinship-ritual", "ritual-rank"),
            ),
        ),
    ),
    (
        "ritual",
        "整理制度变化的成果图",
        "怎样解释西周秩序与后来的变化？",
        (
            (
                "show-transition",
                "并列秩序和变化",
                "把礼制的身份表达、诸侯发展和周王室控制变化分成不同层次说明。",
                ("比较制度变化", "写出多种因素"),
                "作品保留了制度关系，也显示后续力量变化不是一条单因果线。",
                (12, 12, 13, -8),
                ("ritual-rank", "central-local-change", "east-move-dates"),
            ),
            (
                "ritual-only-cause",
                "只用礼制解释灭亡",
                "把西周结束完全归因于礼制或单一人物，不说明时间和材料。",
                ("唯一原因", "只归因礼制"),
                "一个解释被扩大成唯一原因，关键时间和材料层次消失了。",
                (3, 5, -7, 15),
                ("central-local-change", "east-move-dates"),
            ),
            (
                "keep-dates-open",
                "保留约年和来源栏",
                "按教师课文标出约年，并把具体年代依据列入继续核对清单。",
                ("写约数", "补年代出处"),
                "课程时间轴没有冒充同时代铭文给出的日期。",
                (8, 10, 9, -4),
                ("east-move-dates", "classroom-model"),
            ),
        ),
    ),
)


def build_l103_scenario_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> scenario_authoring.ScenarioAuthorDraftV1:
    course_draft = course_draft or build_l103_course_draft()
    _, fact_ids, _, source_ids = package_indexes(course_draft)
    nodes: list[scenario_authoring.ScenarioDraftNodeV1] = []
    actions: list[scenario_authoring.ScenarioDraftActionV1] = []
    node_ids = [f"l103-{group[0]}" for group in _ACTION_GROUPS]
    for index, (topic, title, prompt, choices) in enumerate(_ACTION_GROUPS):
        next_node = node_ids[index + 1] if index + 1 < len(node_ids) else None
        action_ids: list[str] = []
        for suffix, label, description, aliases, feedback, deltas, fact_keys in choices:
            action_id = f"l103-{topic}-{suffix}"
            action_ids.append(action_id)
            effects = [
                scenario_authoring.ScenarioDraftEffectV1(
                    variable_id=variable_id,
                    operation="add",
                    value=value,
                )
                for variable_id, value in zip(
                    (
                        "network-coverage",
                        "source-anchors",
                        "role-distinction",
                        "overreach-risk",
                    ),
                    deltas,
                    strict=True,
                )
            ]
            actions.append(
                scenario_authoring.ScenarioDraftActionV1(
                    action_id=action_id,
                    label=label,
                    description=description,
                    aliases=list(aliases),
                    effects=effects,
                    feedback=feedback,
                    fact_refs=evidence_fact_refs(fact_keys, FACTS, fact_ids),
                    next_node_id=(
                        "l103-evidence-hold"
                        if action_id == "l103-capital-pause-source"
                        else next_node
                    ),
                )
            )
        nodes.append(
            scenario_authoring.ScenarioDraftNodeV1(
                node_id=node_ids[index],
                title=f"第{index + 1}轮：{title}",
                narration=prompt,
                action_ids=action_ids,
            )
        )
    nodes.append(
        scenario_authoring.ScenarioDraftNodeV1(
            node_id="l103-evidence-hold",
            title="提前结束：来源待补",
            narration="现有材料还不能支持完整关系图，先留下复核清单。",
            action_ids=[],
            ending_id="ending-review-sources",
        )
    )
    fact_refs = sorted({fact_ids[statement] for statement in FACTS.values()})
    source_refs = sorted(set(source_ids.values()))
    return scenario_authoring.ScenarioAuthorDraftV1(
        scenario_id=SCENARIO_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="西周地方治理关系图工作台",
        scenario_type="council",
        student_role="西周制度材料整理员（现代课堂角色）",
        objective="在五轮整理中区分地方层级、宗法关系、礼制表达和遗址证据。",
        opening=(
            "这是现代课堂关系图整理模拟，不还原西周朝会，也没有古人对白。你有五轮，每轮只选择当前列出的行动；"
            "自由输入只映射到预设行动，不能新增制度事实或改变结果。分值是学习观察工具，不是西周统计。"
        ),
        max_turns=5,
        variables=[
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="network-coverage",
                label="关系图覆盖",
                description="是否把王室、封国及地方层级放到同一张图中。",
                initial=25,
            ),
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="source-anchors",
                label="来源锚点",
                description="是否写出可返回的铭文、馆藏或研究出处。",
                initial=25,
            ),
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="role-distinction",
                label="关系区分",
                description="是否分清封国关系、家族继承和礼仪表达。",
                initial=25,
            ),
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="overreach-risk",
                label="过度概括风险",
                description="是否把教师概括或单件材料扩展成所有地区的唯一规则。",
                initial=45,
            ),
        ],
        action_rules=sorted(actions, key=lambda item: item.action_id),
        ending_rules=[
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-network-supported",
                title="关系图有出处也有边界",
                conditions=[
                    scenario_authoring.ScenarioDraftConditionV1(
                        kind="turn", operator="gte", value=5
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="network-coverage", operator="gte", value=70
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="source-anchors", operator="gte", value=70
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="role-distinction", operator="gte", value=70
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="overreach-risk", operator="lte", value=40
                    ),
                ],
                summary="关系图显示了不同政治和家族联系，也留下了能返回的遗址与铭文来源。",
                historical_explanation="这是学习成果状态，不代表西周曾进行这场课堂整理。",
                major_costs=[
                    "仍有制度细节需要具体篇章或铭文支持",
                    "研究解释没有替代原始材料",
                ],
                source_ref_ids=source_refs,
                fact_refs=evidence_fact_refs(
                    ("liulihe-inscriptions", "hereditary-office-debate"),
                    FACTS,
                    fact_ids,
                ),
                priority=10,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-oversimplified-network",
                title="关系图需要分层重画",
                conditions=[
                    scenario_authoring.ScenarioDraftConditionV1(
                        kind="turn", operator="gte", value=5
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="overreach-risk", operator="gte", value=70
                    ),
                ],
                summary="图把血缘、封国职责和礼仪规则混成一条线。先回到具体材料，再标出哪些是研究概括。",
                historical_explanation="这是教学反馈，不是对历史人物或西周制度的唯一评价。",
                major_costs=["单件铭文被当作制度总表", "亲属继承被扩大为所有官职规则"],
                source_ref_ids=source_refs,
                fact_refs=evidence_fact_refs(
                    ("bronze-limits", "hereditary-office-debate"), FACTS, fact_ids
                ),
                priority=20,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-review-sources",
                title="补齐史料后再提交",
                conditions=[
                    scenario_authoring.ScenarioDraftConditionV1(
                        kind="turn", operator="gte", value=5
                    ),
                ],
                summary="关系图保留了已核线索，并把具体职责、礼制范围或年代出处列入待查清单。",
                historical_explanation="缺少材料时应保留问题，不由模型补成史实。",
                major_costs=[
                    "诸侯义务实例需要进一步定位",
                    "西周官职继承范围存在研究分歧",
                ],
                source_ref_ids=source_refs,
                fact_refs=evidence_fact_refs(
                    ("vassal-duties", "east-move-dates"), FACTS, fact_ids
                ),
                priority=1000,
            ),
        ],
        start_node_id=node_ids[0],
        nodes=nodes,
        fact_refs=fact_refs,
        source_ref_ids=source_refs,
        dossier_template=scenario_authoring.ScenarioDraftDossierV1(
            title_template="《{scenario_title}·关系图》",
            reflection_questions=[
                "图中的每一条线分别表示封地、家族关系还是礼仪身份？",
                "哪件考古材料能回到具体器物或遗址？它能说明到哪里？",
                "哪一项关于嫡长子或世卿世禄的结论需要标注研究分歧？",
                "请写出一个课程结论、一个来源定位和一个待核问题。",
            ],
            knowledge_node_kinds=[
                "institution",
                "evidence",
                "kinship",
                "boundary",
                "open_question",
            ],
        ),
    )


def build_l103_evidence_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> evidence_workflow.EvidenceCorpusDraftV1:
    course_draft = course_draft or build_l103_course_draft()
    _, fact_ids, person_ids, source_ids = package_indexes(course_draft)
    source_titles = {spec.key: spec.title for spec in SOURCE_SPECS}
    sources = tuple(
        EvidenceSourceV1(
            source_id=source_ids[spec.title],
            title=spec.title,
            kind=spec.kind,
            author_or_institution=spec.author_or_institution,
            publisher=spec.publisher,
            published_year=spec.published_year,
            url_or_path=spec.url_or_path,
            locator=spec.locator,
            citation_note=spec.citation_note,
            reliability=spec.reliability,
            rights_note="本草稿保存项目自写摘要和出处定位，不复制古籍或馆藏页面全文。",
        )
        for spec in SOURCE_SPECS
    )
    passages = tuple(
        EvidencePassageV1(
            passage_id=f"l103-p{index:03d}",
            source_id=source_ids[source_titles[item.source_key]],
            title=item.title,
            text=item.text,
            summary=item.summary,
            fact_ids=tuple(sorted({fact_ids[FACTS[key]] for key in item.fact_keys})),
            person_ids=tuple(sorted({person_ids[name] for name in item.people})),
            keywords=tuple(sorted(set(item.keywords))),
            evidence_kind=item.evidence_kind,
            certainty=item.certainty,
            chronology_note=item.chronology_note,
            teaching_note=item.teaching_note,
        )
        for index, item in enumerate(_PASSAGES, start=1)
    )
    return evidence_workflow.EvidenceCorpusDraftV1(
        corpus_id=CORPUS_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="L103 西周分封与宗法：关系图证据草稿",
        scope_note=(
            "供 L103 开发审阅。传世记载、馆藏铭文、遗址考古、现代研究和教师教学框架分层保存；"
            "嫡长子继承与官职世袭的关系、课程年代和诸侯义务实例保留待核。"
        ),
        sources=sources,
        passages=passages,
    )


def build_l103_authoring_bundle() -> tuple[
    content.LessonContentPackage,
    scenario_authoring.ScenarioAuthorDraftV1,
    evidence_workflow.EvidenceCorpusDraftV1,
]:
    course = build_l103_course_draft()
    return course, build_l103_scenario_draft(course), build_l103_evidence_draft(course)


__all__ = [
    "CORPUS_ID",
    "COURSE_ID",
    "FACTS",
    "LESSON_ID",
    "QA_POINTS",
    "SCENARIO_ID",
    "SOURCE_SPECS",
    "build_l103_authoring_bundle",
    "build_l103_course_draft",
    "build_l103_evidence_draft",
    "build_l103_scenario_draft",
]
