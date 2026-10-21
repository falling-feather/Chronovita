"""Unreviewed authoring draft for C-prequin-state / L102.

The teacher's current textbook JSON remains the sole source for the lesson
body, keywords, people and map points. This module adds a bounded evidence
exercise and its draft evidence corpus; it does not seal or publish artifacts.
"""

from __future__ import annotations

from typing import Any

from services import content
from services.content import evidence_workflow, scenario_authoring
from services.contracts.evidence_v1 import EvidencePassageV1, EvidenceSourceV1
from services.content.flagships.authoring_specs import (
    EvidencePassageSpec as _PassageSpec,
    LessonSourceSpec as _SourceSpec,
    evidence_fact_refs,
    load_teacher_lesson,
    merge_lesson_source_refs,
    package_indexes,
)


COURSE_ID = "C-prequin-state"
LESSON_ID = "L102"
SCENARIO_ID = "shang-l102-evidence-curation"
CORPUS_ID = "shang-l102-evidence"
TEACHER_SOURCE_ID = "teacher-l102"

SOURCE_SPECS = (
    _SourceSpec(
        "shiji-yin",
        "《史记·殷本纪》",
        "primary_source",
        "司马迁；中国哲学书电子化计划底本索引",
        "中国哲学书电子化计划",
        "https://ctext.org/wiki.pl?chapter=977439&if=gb&remap=gb",
        "卷3《殷本纪》第21段（盘庚渡河南段）及商末叙述",
        "后世传世叙事；可研究汉代历史记忆，不作商代现场逐字记录。",
    ),
    _SourceSpec(
        "shiji-zhou",
        "《史记·周本纪》",
        "primary_source",
        "司马迁；中国哲学书电子化计划底本索引",
        "中国哲学书电子化计划",
        "https://ctext.org/shiji/zhou-ben-ji/zhs",
        "《周本纪》武王伐商、牧野誓师叙述",
        "西汉传世叙事；用于核对后世记录如何讲述周人伐商。",
    ),
    _SourceSpec(
        "shangshu-pan-geng",
        "《尚书·商书·盘庚上》",
        "primary_source",
        "传世文献；中国哲学书电子化计划底本索引",
        "中国哲学书电子化计划",
        "https://ctext.org/shang-shu/pan-geng-i/zhs",
        "《盘庚上》开篇及迁殷叙述",
        "传世篇章；文本层次与形成时间不能等同于商代现场记录。",
    ),
    _SourceSpec(
        "nopss-early-writing",
        "商代前期：中国步入成熟文字时代",
        "research",
        "袁广阔；首都师范大学历史学院",
        "全国哲学社会科学工作办公室（原载《光明日报》）",
        "https://www.nopss.gov.cn/n1/2023/0327/c219544-32651861.html",
        "“书迹都垣”及“卜祀鼎新”两节，特别是商代前后期文字载体差异",
        "现代考古研究综述；涉及早商文字材料及殷墟时期甲骨使用。",
        published_year=2023,
    ),
    _SourceSpec(
        "nopss-oracle",
        "甲骨文研究的继往开来",
        "research",
        "宋镇豪；中国社会科学院历史研究所",
        "全国哲学社会科学工作办公室（原载《光明日报》）",
        "https://www.nopss.gov.cn/n1/2019/1104/c219457-31435711.html",
        "“甲骨文的历史文化魅力”部分，卜辞结构、内容范围与材料视角",
        "现代甲骨学研究综述；本文仅采用概述，不把推论改写成卜辞原话。",
        published_year=2019,
    ),
    _SourceSpec(
        "ihp-oracle-207",
        "甲骨文拓片 fsnrb188491-0207",
        "archaeology",
        "中央研究院历史语言研究所傅斯年图书馆",
        "傅斯年图書館數位典藏計畫",
        "https://dap.ihp.sinica.edu.tw/en/material/12/",
        "藏品号 fsnrb188491-0207；Item Description",
        "馆藏拓片目录记录；该单件材料只支持页面明确列出的来源、分期与内容。",
    ),
    _SourceSpec(
        "mct-houwu-ding",
        "司母戊大方鼎亮相河南安阳",
        "museum",
        "中华人民共和国文化和旅游部（转引《光明日报》）",
        "中华人民共和国文化和旅游部",
        "https://www.mct.gov.cn/whzx/tpxw/200509/t20050920_828201.htm",
        "正文第2段；1939年出土地点、商代后期王室青铜祭器属性",
        "报道支持出土地点、时代和器物用途；页面未给精确重量或完整铸造流程。",
        published_year=2005,
    ),
    _SourceSpec(
        TEACHER_SOURCE_ID,
        "教师课文：早期国家与社会变革·L102",
        "textbook",
        "Chronovita-Course-Content PR #49",
        "教师课程稿（当前快照）",
        "content/textbooks/C-prequin-state.json#L102",
        "L102 当前教师课文；迁殷、青铜器、甲骨文与商周更替段落",
        "只证明本课采用了哪些教学表述，不是独立历史史料；正文保持教师原文。",
    ),
)


FACTS = {
    "migration_texts": "【传世文献】《尚书·盘庚上》和《史记·殷本纪》保存盘庚迁殷叙事；须标出篇名和文本层次，不能当成现场录音。",
    "migration_site_boundary": "【考古边界】传世迁殷叙事与具体考古遗址的对应需要分开核验；本课配套不把两者未经说明地画等号。",
    "late_shang_period": "【年代边界】现代考古分期为商代前后期及殷墟文化提供研究框架，但一件甲骨不能单独给迁都事件定年。",
    "early_writing_media": "【考古研究】商代文字材料不只见于晚商甲骨；早商也发现骨刻、金文与陶文等不同载体。",
    "oracle_record_sample": "【具体拓片】史语所藏 fsnrb188491-0207 被目录定为武丁时期材料，页面说明内容涉及祖先祭祀及天象。",
    "oracle_scope": "【材料范围】单件卜辞只能说明这件材料记录了什么；不能代表商代所有人的经历、观点或全部文字使用。",
    "oracle_royal_view": "【视角边界】殷墟甲骨大量涉及王室占卜与王事，适合研究王室相关活动，普通人生活在材料中的可见度有限。",
    "city_remains": "【考古材料】殷墟研究结合宫殿区、墓葬、作坊与器物等遗存讨论都邑功能和社会组织。",
    "city_inference": "【解释边界】遗址功能分区可以支持对组织和分工的谨慎解释，不能仅凭一处遗迹补出完整行政制度或人口数字。",
    "bronze_object_record": "【馆藏报道】文旅部2005年报道记载司母戊大方鼎1939年出土于安阳武官村，属商代后期王室青铜祭器。",
    "bronze_source_gap": "【待核缺项】文旅部报道未给后母戊鼎精确重量或完整铸造流程；教师课文所列数字和工艺细节需要另找馆藏或考古出处。",
    "shang_fall_texts": "【传世叙事】商末君主品行与王朝灭亡的道德解释主要见于后世传世文本，应与考古材料所能说明的内容分开。",
    "muye_texts": "【传世叙事】牧野之战的叙述可在《史记·周本纪》等传世篇章中定位；具体时间采用课程年代框架时仍需注明年代学口径。",
    "class_text_dates": "【课程口径】当前教师课文采用约公元前1300年和约公元前1046年的时间表述；配套把它们标作课程时间框架，不伪称拓片本身给出该日期。",
    "simulation_boundary": "【教学模拟】关卡分值、行动反馈和成果状态是现代课堂工具，不是商代统计、真实会议或历史人物原话。",
}


QA_POINTS = [
    "《尚书·盘庚上》和《史记·殷本纪》怎样记述迁殷？这两篇材料分别能证明什么、不能证明什么？",
    "拓片 fsnrb188491-0207 的目录记录了哪些信息？为什么不能用一件拓片代表整个商代社会？",
    "早商文字材料和殷墟晚商甲骨材料有什么不同？“甲骨文”能否直接说成中国文字的起点？",
    "宫殿区、王陵和作坊等遗存合在一起能支持怎样的判断？哪些结论仍是现代研究推论？",
    "甲骨文保存了哪些王室活动？它的记录视角会让哪些人的生活不容易被看见？",
    "关于帝辛的道德评价与商周更替叙事，怎样区分传世文献、考古材料和后世解释？",
    "文旅部报道能支持后母戊鼎的哪些信息？精确重量和铸造流程还缺哪类来源？",
    "为本课一条关键词制作证据卡：写出原文或实物定位、材料类型、可以支持的判断和一个不能越过的边界。",
]


LEVEL_GOALS = [
    "能按材料类型区分传世文本、考古遗存、甲骨拓片、现代研究和课堂模拟。",
    "能从一条可定位材料写出有限结论，并说明它不能代表什么。",
    "能指出殷墟甲骨的王室视角，以及早商与晚商文字材料的区别。",
    "能完成一张证据卡：主张、出处、材料年代、解释和待核缺项齐全。",
]


_PASSAGES = (
    _PassageSpec(
        "shiji-yin",
        "盘庚迁殷的传世叙述",
        "《史记·殷本纪》写到盘庚即位时殷都所在位置及其渡河迁居的叙述。",
        "这是西汉史家保存的迁都叙事，可定位到《殷本纪》第21段。",
        ("migration_texts",),
        ("盘庚", "盘庚迁殷"),
        "transmitted_text",
        "interpretation",
        "后世文本叙述商代事件。",
        ("盘庚",),
        "不把这段当作同时代现场记录。",
    ),
    _PassageSpec(
        "shangshu-pan-geng",
        "《盘庚上》的迁居劝告",
        "《尚书·盘庚上》以迁居和对民众的告诫为主题，保存了关于迁殷的传世文本。",
        "该篇能显示后世所传的迁居叙述，不足以逐字还原商代讲话。",
        ("migration_texts", "migration_site_boundary"),
        ("盘庚", "迁都"),
        "transmitted_text",
        "disputed",
        "传世篇章，其形成和传承层次需区别于商代现场材料。",
        ("盘庚",),
    ),
    _PassageSpec(
        "shiji-yin",
        "迁都原因与文本层次",
        "《史记》提供盘庚迁殷的叙事框架；具体原因、地点对应和事件细节需要结合其他材料核对。",
        "故事内容与现代考古判断应并列标注，不能互相冒充。",
        ("migration_texts", "migration_site_boundary"),
        ("迁都", "殷墟"),
        "boundary_note",
        "disputed",
        "传世叙事与考古遗址解释分属不同材料层次。",
        ("盘庚",),
    ),
    _PassageSpec(
        "nopss-early-writing",
        "盘庚与殷墟分期问题",
        "现代研究以考古分期讨论早商都邑和殷墟；对盘庚迁都所指地点的判断还需看具体遗址与文本解释。",
        "迁殷叙事不能直接替代遗址分期论证。",
        ("migration_site_boundary", "late_shang_period"),
        ("盘庚迁殷", "殷墟", "考古分期"),
        "scholarly_interpretation",
        "disputed",
        "现代研究讨论，不是传世篇章自身给出的结论。",
        ("盘庚",),
    ),
    _PassageSpec(
        "shiji-yin",
        "商代都邑多次迁徙的叙述",
        "《史记·殷本纪》在盘庚段落前后串联商王世系与都邑迁徙，反映史家组织商代历史的方式。",
        "可用于分析传世历史叙事，不能单独绘制精确迁都路线。",
        ("migration_texts", "migration_site_boundary"),
        ("商朝", "都城"),
        "transmitted_text",
        "interpretation",
        "西汉对更早王朝的追述。",
    ),
    _PassageSpec(
        "nopss-early-writing",
        "早商文字载体不止甲骨",
        "现代考古综述列举早商骨刻、青铜器铭文、陶文等材料，说明商代文字材料在载体和内容上有变化。",
        "甲骨文不应被说成商代或中国文字唯一的早期载体。",
        ("early_writing_media", "late_shang_period"),
        ("甲骨文", "金文", "陶文"),
        "scholarly_interpretation",
        "consensus",
        "论文讨论早商材料与商代前后期变化。",
    ),
    _PassageSpec(
        "nopss-early-writing",
        "晚商殷墟甲骨记录增多",
        "现代考古综述把殷墟文化分期与甲骨卜辞大量出现的阶段联系起来，并区分早段与后续阶段。",
        "分期是现代考古研究框架，不是某块甲骨自带的公历日期。",
        ("late_shang_period", "class_text_dates"),
        ("殷墟", "甲骨文", "年代"),
        "scholarly_interpretation",
        "interpretation",
        "按论文引用的考古文化分期理解。",
    ),
    _PassageSpec(
        "nopss-early-writing",
        "商代文字与都邑遗址",
        "文章讨论郑州商城、小双桥、洹北商城和殷墟等遗址中的文字材料，强调文字发现与都邑考古背景的联系。",
        "可以比较不同遗址，不宜把所有文字材料都归入殷墟甲骨。",
        ("early_writing_media", "city_remains"),
        ("都邑", "文字材料"),
        "scholarly_interpretation",
        "interpretation",
        "以文章所述遗址与材料类型为限。",
    ),
    _PassageSpec(
        "nopss-early-writing",
        "关于殷墟与盘庚迁殷的学术讨论",
        "文章指出学者对洹北商城与殷墟的关系及其历史对应有不同判断。",
        "遇到迁殷地点问题，应标出研究分歧，不用一个未经论证的等号结案。",
        ("migration_site_boundary", "city_inference"),
        ("洹北商城", "殷墟", "盘庚"),
        "boundary_note",
        "disputed",
        "现代考古和历史解释仍需结合具体研究。",
        ("盘庚",),
    ),
    _PassageSpec(
        "nopss-early-writing",
        "晚商甲骨的记录范围",
        "文章概述殷墟甲骨涉及占卜、王室、外交征伐、祭祀和社会经济等内容。",
        "可以据材料研究晚商王室及其相关活动，但不能据此断言每个群体都留下同等记录。",
        ("oracle_royal_view", "oracle_scope"),
        ("甲骨文", "商王室"),
        "scholarly_interpretation",
        "consensus",
        "现代研究对出土材料内容的概括。",
    ),
    _PassageSpec(
        "nopss-oracle",
        "卜辞与记事刻辞",
        "研究综述区分占卜文例和记事文例，并说明完整卜辞可能包含不同信息部分。",
        "释读应区分材料上实际保留的字句与研究者的解释。",
        ("oracle_record_sample", "oracle_scope"),
        ("卜辞", "甲骨文"),
        "scholarly_interpretation",
        "interpretation",
        "文章概述甲骨学术语和材料结构。",
    ),
    _PassageSpec(
        "nopss-oracle",
        "甲骨文涉及的主题",
        "研究综述列举甲骨记录涉及气象、祭祀、征伐、农业等主题。",
        "这些主题说明研究范围，不代表每类材料数量相同，也不覆盖所有人的日常生活。",
        ("oracle_royal_view", "oracle_scope"),
        ("祭祀", "农业", "征伐"),
        "scholarly_interpretation",
        "interpretation",
        "现代研究对已发现材料的归纳。",
    ),
    _PassageSpec(
        "nopss-oracle",
        "材料的王室视角",
        "文章指出殷墟甲骨的内容大量关联商王室及贵族活动。",
        "研究者要说明记录者和记录目的，不能把王室材料说成全体商人的自述。",
        ("oracle_royal_view",),
        ("商王室", "甲骨文"),
        "boundary_note",
        "interpretation",
        "由现存出土材料的主题分布形成的研究判断。",
    ),
    _PassageSpec(
        "ihp-oracle-207",
        "武丁时期的甲骨拓片",
        "傅斯年图书馆目录将 fsnrb188491-0207 标为商后期第一期材料，来源说明为安阳小屯127号坑出土。",
        "这是可回到具体馆藏记录的一件拓片。",
        ("oracle_record_sample", "late_shang_period"),
        ("fsnrb188491-0207", "武丁", "甲骨拓片"),
        "archaeological_evidence",
        "consensus",
        "馆藏条目给出考古分期与出土地点。",
    ),
    _PassageSpec(
        "ihp-oracle-207",
        "拓片目录记载的内容",
        "目录说明这件龟腹甲拓片的卜辞涉及祖先祭祀及天象。",
        "只能将目录说明用于这一件材料，不能扩大成所有甲骨的共同内容。",
        ("oracle_record_sample", "oracle_scope"),
        ("祖先祭祀", "天象", "甲骨文"),
        "archaeological_evidence",
        "consensus",
        "页面对具体拓片的目录说明。",
    ),
    _PassageSpec(
        "ihp-oracle-207",
        "从拓片到研究结论",
        "馆藏目录提供编号、尺寸、分期、地点和内容说明；更大的历史判断要由多件材料和研究共同支持。",
        "具体编号可以复核，宏观解释仍要列出依据。",
        ("oracle_record_sample", "city_inference"),
        ("馆藏号", "拓片"),
        "teaching_explanation",
        "interpretation",
        "这是对目录字段与解释层次的课堂说明。",
    ),
    _PassageSpec(
        "nopss-oracle",
        "甲骨卜辞并非完整商代档案",
        "文章指出出土甲骨常有残缺，卜辞有时只保留部分信息。",
        "缺字和残片必须标出，不应由模型补成确定原文。",
        ("oracle_scope",),
        ("残片", "卜辞"),
        "boundary_note",
        "consensus",
        "以文章对出土与整理情况的概述为限。",
    ),
    _PassageSpec(
        "nopss-oracle",
        "从卜辞记录到社会解释",
        "甲骨文字可研究商代政治和社会活动，但把一条卜辞扩展为整套制度时还需要其他证据。",
        "材料中的记录和现代解释不是同一层。",
        ("oracle_scope", "city_inference"),
        ("历史解释", "甲骨文"),
        "boundary_note",
        "interpretation",
        "从个别材料到整体解释需要多项材料。",
    ),
    _PassageSpec(
        "nopss-early-writing",
        "都邑遗存的功能组合",
        "现代研究结合宫殿区、道路、遗迹和出土器物讨论不同商代都邑的空间功能。",
        "可以说遗址显示出不同功能区域，具体社会组织仍须说明推理过程。",
        ("city_remains", "city_inference"),
        ("都邑", "宫殿区", "遗址"),
        "scholarly_interpretation",
        "interpretation",
        "这是依据考古遗迹作出的现代解释。",
    ),
    _PassageSpec(
        TEACHER_SOURCE_ID,
        "教师课文中的殷墟材料",
        "当前教师课文把宫殿区、王陵和手工业作坊并列，用来认识晚商都邑和社会组织。",
        "该段是课程教学表述；引用历史结论时仍应回到考古来源。",
        ("city_remains", "city_inference"),
        ("殷墟", "王陵", "手工业作坊"),
        "teaching_explanation",
        "interpretation",
        "教师课文 L102 第2段；不是独立考古报告。",
    ),
    _PassageSpec(
        TEACHER_SOURCE_ID,
        "青铜生产的课堂推理",
        "教师课文将青铜器的原料、燃料、制范和工匠分工用于讨论生产组织。",
        "过程说明帮助形成问题；精确工艺、产量和劳力数字需另有考古或博物馆来源。",
        ("city_inference", "bronze_source_gap"),
        ("青铜器", "生产组织"),
        "teaching_explanation",
        "interpretation",
        "教师课文 L102 第3段；配套外部来源待核。",
    ),
    _PassageSpec(
        "mct-houwu-ding",
        "方鼎的出土信息与用途",
        "文旅部2005年报道记载司母戊大方鼎1939年出土于安阳武官村，属于商代后期王室青铜祭器。",
        "报道支持出土地点、时代和器物用途；它没有列出精确重量或完整铸造流程。",
        ("bronze_object_record", "bronze_source_gap"),
        ("后母戊鼎", "司母戊大方鼎", "武官村"),
        "archaeological_evidence",
        "consensus",
        "文化和旅游部2005年9月20日报道；使用当时的器物名称。",
        teaching_note="教师课文使用‘后母戊鼎’一名；此来源沿用报道旧称，正文按教师原文保留。",
    ),
    _PassageSpec(
        TEACHER_SOURCE_ID,
        "后母戊鼎精确数据待核",
        "教师课文提到后母戊鼎的重量和铸造复杂性；当前文旅部报道只给出出土信息、时代和用途。",
        "另找馆藏或考古材料核实重量和工艺前，不补造精确数据。",
        ("bronze_object_record", "bronze_source_gap"),
        ("后母戊鼎", "青铜器"),
        "boundary_note",
        "interpretation",
        "教师课文 L102 第3段；精确数据外部出处待补。",
    ),
    _PassageSpec(
        "shiji-yin",
        "帝辛形象的传世叙事",
        "《史记·殷本纪》保存对帝辛及商亡过程的后世叙述。",
        "可研究传世文本怎样评价帝辛，不能把道德标签当作甲骨上的自述。",
        ("shang_fall_texts", "oracle_royal_view"),
        ("帝辛", "商朝灭亡"),
        "transmitted_text",
        "interpretation",
        "西汉史家对商末人物和事件的记述。",
        ("帝辛",),
    ),
    _PassageSpec(
        "shiji-zhou",
        "《周本纪》中的牧野叙事",
        "《史记·周本纪》叙述武王伐商和牧野誓师，是研究后世商周更替记忆的传世材料。",
        "篇章能定位叙事，不等于战场现场逐字记录。",
        ("muye_texts", "shang_fall_texts"),
        ("周武王", "牧野之战"),
        "transmitted_text",
        "interpretation",
        "西汉传世文本叙述商周战争。",
    ),
    _PassageSpec(
        "nopss-early-writing",
        "商代前后期的年代框架",
        "研究综述引用商代前期与后期的年代划分，并讨论各阶段的文字材料变化。",
        "课程时间轴是教学框架；某件拓片的目录分期与具体事件日期不可混用。",
        ("late_shang_period", "class_text_dates"),
        ("商代", "年代"),
        "scholarly_interpretation",
        "interpretation",
        "现代年代学和考古分期。",
    ),
    _PassageSpec(
        TEACHER_SOURCE_ID,
        "本课时间轴的使用边界",
        "当前教师课文以约公元前1300年和约公元前1046年组织商代叙述。",
        "这是课程时间轴，不是拓片原文；引用时应沿用“约”并保留来源说明。",
        ("class_text_dates", "late_shang_period"),
        ("公元前1300年", "公元前1046年"),
        "curriculum_goal",
        "interpretation",
        "教师课文 L102 第1、6段；具体年代学来源待教师审校。",
    ),
    _PassageSpec(
        "shiji-yin",
        "历史叙事不能代替考古材料",
        "传世文本能保存王朝谱系和事件叙述，考古遗存则以不同方式记录物质、文字和空间信息。",
        "对同一问题并列材料时，先标明各自年代和可证明范围。",
        ("migration_texts", "shang_fall_texts", "oracle_scope"),
        ("传世文献", "考古材料"),
        "teaching_explanation",
        "interpretation",
        "这是课堂方法说明，不是对某一历史事件的新增事实。",
    ),
    _PassageSpec(
        TEACHER_SOURCE_ID,
        "关卡分值不是商代统计",
        "本课练习用分值呈现材料覆盖、来源辨析和过度推断风险。",
        "所有数值与反馈均为课堂模拟，不表示商王朝的真实统计或历史人物选择。",
        ("simulation_boundary",),
        ("教学模拟", "学习成果"),
        "boundary_note",
        "consensus",
        "现代教学设计；不是历史材料。",
    ),
)


def _read_teacher_lesson() -> tuple[dict[str, Any], dict[str, Any]]:
    return load_teacher_lesson(
        COURSE_ID,
        LESSON_ID,
        "商朝兴衰与甲骨文",
    )


def _source_refs(teacher_lesson: dict[str, Any]) -> list[content.SourceRef]:
    return merge_lesson_source_refs(teacher_lesson, SOURCE_SPECS)


def build_l102_course_draft() -> content.LessonContentPackage:
    """Build a draft around the unchanged current teacher text."""

    snapshot, lesson = _read_teacher_lesson()
    people = [
        content.PersonCard(
            name=item["name"],
            role=item.get("role", ""),
            summary=item.get("summary", ""),
            persona=item.get("persona", ""),
            boundaries=list(item.get("boundaries", [])),
        )
        for item in lesson.get("people", [])
    ]
    return content.LessonContentPackage(
        lesson_id=LESSON_ID,
        title=lesson["title"],
        unit=snapshot.get("title", "早期国家与社会变革"),
        era=snapshot.get("era", "先秦"),
        body=list(lesson["body"]),
        course_id=COURSE_ID,
        course_title=snapshot.get("title", "早期国家与社会变革"),
        era_id=snapshot.get("era_id", "C-prequin"),
        section=snapshot.get("section", "早期国家与社会变革"),
        lesson_no=lesson.get("lesson_no", "1.2"),
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
        people=people,
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
        source_refs=_source_refs(lesson),
        facts=list(FACTS.values()),
        qa_points=list(QA_POINTS),
        level_goals=list(LEVEL_GOALS),
        saga_material=content.MaterialPlaceholder(
            title="看：殷墟与甲骨材料",
            objective="从具体拓片和遗址线索开始，区分材料本身与现代解释。",
            notes="拓片例证定位到 fsnrb188491-0207；商代文字载体和遗址对应问题保留年代边界。",
        ),
        sandbox_material=content.MaterialPlaceholder(
            title="练：整理一张商代证据卡",
            objective="在五轮有限选择中，给材料标出处、年代、可支持的判断和待核问题。",
            notes="这是现代课堂材料整理模拟；不还原商代廷议，不生成古人原话。",
        ),
        seed_canvas=[
            content.SeedCanvasNode(
                id="source-layer",
                label="材料类型",
                note="传世文本、考古遗存、拓片目录、现代研究、课堂模拟分别标注。",
            ),
            content.SeedCanvasNode(
                id="migration-boundary",
                label="迁殷与遗址",
                note="写出传世篇章，并把地点与考古遗址的对应列为待核问题。",
            ),
            content.SeedCanvasNode(
                id="oracle-sample",
                label="一件甲骨拓片",
                note="编号、地点、分期、目录所述内容；不由一片推断全部社会。",
            ),
            content.SeedCanvasNode(
                id="royal-perspective",
                label="记录者与视角",
                note="甲骨材料多关联王室活动，标出普通人生活的材料缺口。",
            ),
            content.SeedCanvasNode(
                id="evidence-card",
                label="证据卡成果",
                note="主张、出处、材料年代、解释、边界与待核缺项。",
            ),
        ],
        teacher_notes=(
            "开发初稿，待教师审校；不提交、不封存、不发布。教师正文、关键词、人物和地图点直接取自当前教师快照，未改写。"
            "活动是现代证据整理模拟，不设置古人对话。盘庚迁殷与具体考古遗址的对应、教师所列时间依据、后母戊鼎精确数据和工艺细节仍待核。"
            "教师原话、传世文本、考古材料、现代研究和教学解释须分别标注；未审校内容不称为教师审定结论。"
        ),
    )


_ACTION_GROUPS = (
    (
        "migration",
        "先给迁殷材料标来源",
        "展签采用哪种写法？",
        (
            (
                "compare-texts",
                "并列篇名和年代",
                "把《尚书·盘庚上》《史记·殷本纪》标作传世文本，注明各自篇名。",
                ("比较两篇", "标出传世文献"),
                "两篇材料都有出处，读者能看见这是传世叙述。",
                (12, 14, -8, 8),
                ("migration_texts",),
            ),
            (
                "equate-site",
                "直接画等号",
                "把迁殷地点直接标成今天确认的殷墟遗址，不写依据。",
                ("确定就是殷墟", "不需要核对"),
                "一个解释被写成定论，来源和考古对应没有交代。",
                (4, -5, 14, 2),
                ("migration_site_boundary",),
            ),
            (
                "flag-location",
                "保留待核标记",
                "按教师课文保留时间轴，同时注明迁殷地点与考古遗址的对应待复核。",
                ("写待核", "保留课文表述并标注"),
                "保留了课程说法，也把仍需核对的地点问题交给读者。",
                (9, 16, -5, 10),
                ("migration_texts", "migration_site_boundary", "class_text_dates"),
            ),
            (
                "pause-for-source",
                "先暂停并登记缺项",
                "先不制作结论展签，把迁殷地点对应问题交给教师和史料复核。",
                ("先暂停", "交给教师复核"),
                "暂停发布并记录缺项也是合格的证据处理选择。",
                (0, 2, -2, 0),
                ("migration_site_boundary",),
            ),
        ),
    ),
    (
        "city",
        "用遗址线索解释都邑",
        "哪些发现适合放在一张图里？",
        (
            (
                "combine-remains",
                "并列不同遗存",
                "把宫殿区、墓葬和作坊放在一起，并写明社会分工是依据组合线索作出的解释。",
                ("组合多类遗存", "说明是推论"),
                "多类遗存互相补充，结论也标出了推理层次。",
                (16, 13, -7, 5),
                ("city_remains", "city_inference"),
            ),
            (
                "single-tomb",
                "只凭一座大墓",
                "用一座王陵直接代表全体商人的生活和社会等级。",
                ("一座墓代表所有人", "直接概括全社会"),
                "单件材料被扩大成全社会结论，证据范围不够。",
                (4, -7, 13, 1),
                ("city_inference",),
            ),
            (
                "map-with-limit",
                "画图并写限制",
                "标出遗址线索的空间位置，再写明平面图不能自动证明完整行政制度。",
                ("标记材料限制", "不推成行政体系"),
                "空间信息清楚，制度解释没有越过遗址能够支持的范围。",
                (11, 15, -4, 4),
                ("city_remains", "city_inference"),
            ),
        ),
    ),
    (
        "bronze",
        "整理青铜器展签",
        "怎样谈生产组织才不会补造数字？",
        (
            (
                "label-inference",
                "把过程写成推论",
                "把教师课文提到的原料、制范和工匠协作标作教学解释；引用报道支持的出土信息，并标注重量和工艺细节待核。",
                ("标明待核", "不写具体人数"),
                "课文观点保留下来，尚缺独立来源的细节也被标出。",
                (13, 15, -5, 3),
                ("bronze_object_record", "bronze_source_gap"),
            ),
            (
                "invent-workforce",
                "填入想象数字",
                "为铸造过程补上工匠人数和每天产量，让展签看起来更具体。",
                ("猜人数", "补造产量"),
                "数字没有来源，不能因为写得具体就变成证据。",
                (2, -8, 15, 0),
                ("bronze_object_record", "bronze_source_gap"),
            ),
            (
                "use-object-limit",
                "只写器物能说明的内容",
                "按报道写出方鼎的出土地点、时代和用途；另查馆藏资料核实重量与铸造工艺。",
                ("先找馆藏资料", "暂不下结论"),
                "器物用途与外部来源缺项被分开处理。",
                (10, 14, -4, 2),
                ("bronze_object_record", "bronze_source_gap"),
            ),
        ),
    ),
    (
        "oracle",
        "用一件甲骨说明甲骨文",
        "怎样把具体拓片带回课堂？",
        (
            (
                "cite-item",
                "引用具体拓片目录",
                "写出 fsnrb188491-0207 的编号、地点、分期和目录说明的内容。",
                ("列出拓片编号", "引用馆藏记录"),
                "学生可以回到具体馆藏记录逐项核验。",
                (16, 16, -8, 5),
                ("oracle_record_sample", "oracle_scope"),
            ),
            (
                "generalize-bone",
                "一片代表全部",
                "把这件拓片的内容写成所有商人共同的想法和生活。",
                ("所有人都这样", "全体商人"),
                "一件王室相關记录不能代表每个群体。",
                (3, -8, 15, 0),
                ("oracle_scope", "oracle_royal_view"),
            ),
            (
                "show-perspective",
                "说明王室视角",
                "说明卜辞内容，并提醒甲骨记录更容易留下王室关注的事情。",
                ("标出王室视角", "说明记录偏向"),
                "材料内容和记录视角同时呈现，缺失部分没有被猜写。",
                (12, 17, -6, 4),
                ("oracle_royal_view", "oracle_scope"),
            ),
        ),
    ),
    (
        "fall",
        "整理商周更替说明",
        "怎样区分传世叙事和遗址材料？",
        (
            (
                "compare-layers",
                "并列材料层次",
                "把《殷本纪》《周本纪》标作传世叙事，另列考古材料能观察到的遗址和器物。",
                ("分开写来源", "对照文本和遗址"),
                "文献叙事和考古发现各自保留了位置。",
                (15, 15, -7, 8),
                ("shang_fall_texts", "muye_texts", "oracle_scope"),
            ),
            (
                "single-moral-cause",
                "只写道德结论",
                "把帝辛的后世道德形象直接写成商亡的唯一原因。",
                ("只归因纣王", "唯一原因"),
                "后世评价被当成了同时代记录，也把复杂变化压成单一原因。",
                (3, -8, 15, 2),
                ("shang_fall_texts",),
            ),
            (
                "mark-date-frame",
                "沿用约数并留问题",
                "按课程时间轴写约数，注明需要继续查证年代口径和多种材料。",
                ("保留约数", "注明年代口径"),
                "课程时间轴保留了“约”，具体年代来源仍留在核验清单。",
                (10, 16, -5, 12),
                ("class_text_dates", "muye_texts", "shang_fall_texts"),
            ),
        ),
    ),
)


def _package_indexes(course_draft: content.LessonContentPackage):
    return package_indexes(course_draft)


def _fact_refs(keys: tuple[str, ...], fact_ids: dict[str, str]) -> list[str]:
    return evidence_fact_refs(keys, FACTS, fact_ids)


def build_l102_scenario_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> scenario_authoring.ScenarioAuthorDraftV1:
    """Build a five-round modern evidence-curation simulation draft."""

    course_draft = course_draft or build_l102_course_draft()
    _, fact_ids, _, source_ids = _package_indexes(course_draft)
    nodes: list[scenario_authoring.ScenarioDraftNodeV1] = []
    actions: list[scenario_authoring.ScenarioDraftActionV1] = []
    node_ids = [f"l102-{group[0]}" for group in _ACTION_GROUPS]
    for index, (topic, title, prompt, choices) in enumerate(_ACTION_GROUPS):
        next_node = node_ids[index + 1] if index + 1 < len(node_ids) else None
        action_ids: list[str] = []
        for suffix, label, description, aliases, feedback, deltas, fact_keys in choices:
            action_id = f"l102-{topic}-{suffix}"
            action_ids.append(action_id)
            effects = [
                scenario_authoring.ScenarioDraftEffectV1(
                    variable_id=variable_id,
                    operation="add",
                    value=value,
                )
                for variable_id, value in zip(
                    (
                        "source-coverage",
                        "boundary-awareness",
                        "overreach-risk",
                        "timeline-care",
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
                    fact_refs=_fact_refs(fact_keys, fact_ids),
                    next_node_id=(
                        "l102-evidence-hold"
                        if action_id == "l102-migration-pause-for-source"
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
            node_id="l102-evidence-hold",
            title="提前结束：来源待补",
            narration="尚有关键对应关系需要核验，先保存问题清单。",
            action_ids=[],
            ending_id="ending-more-sources-needed",
        )
    )

    return scenario_authoring.ScenarioAuthorDraftV1(
        scenario_id=SCENARIO_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        title="殷墟材料整理台",
        scenario_type="council",
        student_role="商代材料展签整理员（现代课堂角色）",
        objective="用五次有限选择整理材料出处、能支持的判断、解释边界和待核缺项。",
        opening=(
            "这是现代课堂材料整理模拟，不还原商代会议，也没有古人角色对白。你有五轮，每轮只能选择当前列出的行动；"
            "自由输入只用于匹配现有行动，不能新增史实、改规则或改结局，无法匹配时请改选。分值是学习观察工具，不是商代统计。"
        ),
        max_turns=5,
        variables=[
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="source-coverage",
                label="出处覆盖",
                description="不同材料是否写出可复核的篇名、编号或来源位置。",
                initial=35,
            ),
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="boundary-awareness",
                label="边界辨析",
                description="是否区分原始材料、后世叙事和现代解释。",
                initial=35,
            ),
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="overreach-risk",
                label="过度推断风险",
                description="是否把单件材料扩大成全体社会的确定结论。",
                initial=45,
            ),
            scenario_authoring.ScenarioDraftVariableV1(
                variable_id="timeline-care",
                label="年代标注",
                description="是否保留年代口径和需要复核的时间边界。",
                initial=35,
            ),
        ],
        action_rules=sorted(actions, key=lambda item: item.action_id),
        ending_rules=[
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-evidence-card-ready",
                title="证据卡可以复核",
                conditions=[
                    scenario_authoring.ScenarioDraftConditionV1(
                        kind="turn", operator="gte", value=5
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="source-coverage", operator="gte", value=75
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="boundary-awareness", operator="gte", value=70
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="overreach-risk", operator="lte", value=35
                    ),
                ],
                summary="这张课堂证据卡写出了出处，也把材料能够说明的范围留在了纸面上。",
                historical_explanation="这是学习成果状态，不代表商代曾发生这场展签整理活动。",
                major_costs=[
                    "仍有时间和外部来源需要补查",
                    "不确定问题不能用漂亮结论替代",
                ],
                source_ref_ids=sorted(
                    {source_ids[item.title] for item in SOURCE_SPECS}
                ),
                fact_refs=_fact_refs(("simulation_boundary", "oracle_scope"), fact_ids),
                priority=10,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-overclaim-review",
                title="展签需要改写",
                conditions=[
                    scenario_authoring.ScenarioDraftConditionV1(
                        kind="turn", operator="gte", value=5
                    ),
                    scenario_authoring.ScenarioDraftConditionV1(
                        variable_id="overreach-risk", operator="gte", value=70
                    ),
                ],
                summary="展签写得很肯定，但有些句子超过了材料范围。回到出处，把推断和原文分开再提交。",
                historical_explanation="这是教学反馈，不是对历史人物或商代结局的评价。",
                major_costs=["单件材料被推广到全体社会", "后世评价被误当成现场记录"],
                source_ref_ids=sorted(
                    {source_ids[item.title] for item in SOURCE_SPECS}
                ),
                fact_refs=_fact_refs(("oracle_scope", "shang_fall_texts"), fact_ids),
                priority=20,
            ),
            scenario_authoring.ScenarioDraftEndingV1(
                ending_id="ending-more-sources-needed",
                title="补齐出处后再提交",
                conditions=[
                    scenario_authoring.ScenarioDraftConditionV1(
                        kind="turn", operator="gte", value=5
                    ),
                ],
                summary="当前材料还不够支撑完整展签。保留已核内容，把缺少的来源和问题列出来。",
                historical_explanation="这是课堂复核状态；未核内容保持待查，不由模型补成史实。",
                major_costs=["青铜器精确数据待核", "迁殷地点与遗址对应需要继续查证"],
                source_ref_ids=sorted(
                    {source_ids[item.title] for item in SOURCE_SPECS}
                ),
                fact_refs=_fact_refs(
                    ("bronze_source_gap", "migration_site_boundary"), fact_ids
                ),
                priority=1000,
            ),
        ],
        start_node_id=node_ids[0],
        nodes=nodes,
        fact_refs=sorted(set(fact_ids.values())),
        source_ref_ids=sorted(set(source_ids.values())),
        dossier_template=scenario_authoring.ScenarioDraftDossierV1(
            title_template="《{scenario_title}·证据卡》",
            reflection_questions=[
                "你选了哪件材料？写出可以复核的篇名或馆藏编号。",
                "这件材料直接记录了什么？你的解释从哪里开始？",
                "哪项结论还缺来源？你会到哪类机构资料中继续查？",
                "请分别标出传世叙事、考古材料、现代解释和课堂模拟。",
            ],
            knowledge_node_kinds=[
                "evidence",
                "claim",
                "boundary",
                "interpretation",
                "open_question",
            ],
        ),
    )


def build_l102_evidence_draft(
    course_draft: content.LessonContentPackage | None = None,
) -> evidence_workflow.EvidenceCorpusDraftV1:
    """Build a versioned-workflow evidence draft without sealing it."""

    course_draft = course_draft or build_l102_course_draft()
    _, fact_ids, person_ids, source_ids = _package_indexes(course_draft)
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
            rights_note="本草稿只保存自写摘要和必要的出处定位；不复制古籍或馆藏页面全文。",
        )
        for spec in SOURCE_SPECS
    )
    passages = tuple(
        EvidencePassageV1(
            passage_id=f"l102-p{index:03d}",
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
        title="L102 商朝兴衰与甲骨文：证据边界草稿",
        scope_note=(
            "供 L102 开发审阅。传世文本、具体拓片、现代研究和教师教学解释分层保存；"
            "后母戊鼎精确数据与迁殷地点对应保留待核，不用于扩写成确定答案。"
        ),
        sources=sources,
        passages=passages,
    )


def build_l102_authoring_bundle() -> tuple[
    content.LessonContentPackage,
    scenario_authoring.ScenarioAuthorDraftV1,
    evidence_workflow.EvidenceCorpusDraftV1,
]:
    course = build_l102_course_draft()
    return course, build_l102_scenario_draft(course), build_l102_evidence_draft(course)


__all__ = [
    "CORPUS_ID",
    "COURSE_ID",
    "FACTS",
    "LESSON_ID",
    "QA_POINTS",
    "SCENARIO_ID",
    "SOURCE_SPECS",
    "build_l102_authoring_bundle",
    "build_l102_course_draft",
    "build_l102_evidence_draft",
    "build_l102_scenario_draft",
]
