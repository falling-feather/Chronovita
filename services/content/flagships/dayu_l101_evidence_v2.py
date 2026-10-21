"""EvidenceCorpusV2 authoring source for L101 ``大禹治水``.

The V2 corpus is deliberately lesson-local.  It preserves all V1 passage IDs,
adds passage-level locators and answer slots, and records the boundary that must
travel with each claim.  Text in this module is an original classroom summary;
the registered sources remain the authority and no textbook chapter is copied.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.content.flagships.dayu_l101 import (
    COURSE_ID,
    DAYU_CORPUS_ID,
    LESSON_ID,
    _evidence_sources,
    build_dayu_course_draft,
    build_dayu_evidence_draft,
)
from services.contracts.evidence_v1 import sign_evidence_contract
from services.contracts.evidence_v2 import (
    EvidenceAnswerSlotV1,
    EvidenceBoundaryV1,
    EvidenceCorpusV2,
    EvidencePassageV2,
)


DAYU_V1_CHECKSUM = "ae736fd34b31fc99907e0a33b518dd2fd360530af95d2717e3a54832b2c1ff49"
DAYU_V2_CREATED_AT = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)


def _terms(*values: str) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


BOUNDARIES = (
    EvidenceBoundaryV1(
        boundary_id="dayu-b-absence",
        label="未发现不等于不存在",
        category="claim_limit",
        statement="当前没有可公认直读为禹的同时代文字，只能限制人物姓名层面的断言；它既不能证明禹必不存在，也不能把后世叙事自动变成事实。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-causation",
        label="治理与国家形成不是单线因果",
        category="causation",
        statement="公共工程需要协调资源，但不能据此断言一次治水直接创造了王朝；权威形成、聚落整合、生产与礼仪秩序需要多类证据共同解释。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-chronology",
        label="夏代年代采用约数",
        category="chronology",
        statement="约公元前21世纪至约公元前1600年是教学与研究采用的传统年代框架，不是同时代纪年，更不能精确到某年某月。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-erlitou-name",
        label="二里头文化不自动等于夏王朝",
        category="claim_limit",
        statement="二里头是考古学命名；年代、地域和聚落等级支持它与夏后期高度相关，但目前不能靠遗址复杂性直接读出王朝自名、禹或启。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-legend-detail",
        label="道德母题不能还原现场细节",
        category="claim_limit",
        statement="三过家门、个人对白和精确行程属于后世传承的叙事细节，可研究历史记忆与伦理评价，不能当作已被考古核验的现场记录。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-local-flood",
        label="局地洪水不能独证大禹治水",
        category="causation",
        statement="积石峡研究讨论的是特定地点、特定时段的自然事件；从局地溃决到全国洪水、禹的身份和夏王朝开端之间仍有独立证据缺口。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-memory-map",
        label="后世地图不是夏代测绘图",
        category="source_distance",
        statement="1136年的《禹迹图》与《禹贡》的空间叙述能够说明后人如何组织地理知识和大禹记忆，不能提供夏代工程的精确坐标与路线。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-modern-waterwork",
        label="古代叙事不等于现代工程方案",
        category="modern_concept",
        statement="疏、堵等词只能帮助理解治理思路，不能直接推出符合现代水文学的流量、坝高、工期、预算或唯一施工方案。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-persona",
        label="人物仅在已发布知识边界内发言",
        category="persona_knowledge",
        statement="禹、鲧、益及课堂合成人群不能知道后世考古、现代测年或课堂变量，也不得虚构私人生活、原话、数字和亲历见闻。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-teaching-model",
        label="关卡变量不是夏代统计",
        category="teaching_model",
        statement="风险、粮食、劳作、信任、地形认知和协作能力是用于比较选择与代价的课堂模型，不对应一份真实的夏代账册。",
    ),
    EvidenceBoundaryV1(
        boundary_id="dayu-b-transmitted-distance",
        label="传世文献晚于传统禹时代",
        category="source_distance",
        statement="《孟子》《尚书》相关篇章和《史记·夏本纪》的形成、编定或流传年代均晚于传统禹时代；它们直接证明的是后世记忆和解释。",
    ),
)


SLOT_PASSAGES: dict[str, tuple[str, ...]] = {
    "dayu-slot-erlitou-state": tuple(f"dayu-p{i:03d}" for i in (11, 12, 13, 14, 16, 18, 19, 35, 36, 37, 38, 44)),
    "dayu-slot-erlitou-xia-boundary": tuple(f"dayu-p{i:03d}" for i in (12, 15, 17, 18, 23, 26, 36, 44, 48)),
    "dayu-slot-governance-power-cost": tuple(f"dayu-p{i:03d}" for i in (2, 10, 11, 19, 27, 28, 43, 45, 46, 48)),
    "dayu-slot-jishi-flood": tuple(f"dayu-p{i:03d}" for i in (20, 21, 22, 23, 39, 40, 41, 44, 48)),
    "dayu-slot-memory-map": tuple(f"dayu-p{i:03d}" for i in (9, 24, 25, 34, 42, 44)),
    "dayu-slot-methods": tuple(f"dayu-p{i:03d}" for i in (7, 9, 27, 28, 43, 45, 46)),
    "dayu-slot-revise-with-new-evidence": tuple(f"dayu-p{i:03d}" for i in (1, 17, 21, 23, 26, 41, 43, 44, 48)),
    "dayu-slot-source-layers": tuple(f"dayu-p{i:03d}" for i in (1, 3, 4, 7, 9, 12, 20, 24, 43, 44, 47, 48)),
    "dayu-slot-succession": tuple(f"dayu-p{i:03d}" for i in (5, 10, 29, 32, 43, 46)),
    "dayu-slot-three-doors": tuple(f"dayu-p{i:03d}" for i in (4, 6, 7, 8, 33, 43, 47)),
}


ANSWER_SLOTS = (
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-erlitou-state",
        label="二里头材料怎样支持早期国家研究",
        status="supported",
        response_mode="topic",
        question_form="causality",
        term_groups=(_terms("二里头", "二里头遗址", "二里头文化"), _terms("国家", "早期国家", "王权", "都邑")),
        passage_ids=SLOT_PASSAGES["dayu-slot-erlitou-state"],
        boundary_ids=("dayu-b-causation", "dayu-b-erlitou-name"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-erlitou-xia-boundary",
        label="二里头与夏的对应边界",
        status="supported",
        response_mode="boundary",
        question_form="evidence_boundary",
        term_groups=(_terms("二里头", "二里头文化"), _terms("夏", "夏朝", "夏都", "禹")),
        passage_ids=SLOT_PASSAGES["dayu-slot-erlitou-xia-boundary"],
        boundary_ids=("dayu-b-absence", "dayu-b-chronology", "dayu-b-erlitou-name"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-governance-power-cost",
        label="公共治理、权威与社会代价",
        status="supported",
        response_mode="topic",
        question_form="causality",
        term_groups=(_terms("公共工程", "治水", "治理"), _terms("代价", "信任", "权威", "王权", "组织")),
        passage_ids=SLOT_PASSAGES["dayu-slot-governance-power-cost"],
        boundary_ids=("dayu-b-causation", "dayu-b-teaching-model"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-jishi-flood",
        label="积石峡洪水研究的支持范围",
        status="supported",
        response_mode="boundary",
        question_form="evidence_boundary",
        term_groups=(_terms("积石峡", "堰塞湖", "溃决洪水"), _terms("证明", "关系", "边界", "大禹", "夏")),
        passage_ids=SLOT_PASSAGES["dayu-slot-jishi-flood"],
        boundary_ids=("dayu-b-causation", "dayu-b-chronology", "dayu-b-local-flood"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-memory-map",
        label="《禹贡》与《禹迹图》的空间证据边界",
        status="supported",
        response_mode="boundary",
        question_form="evidence_boundary",
        term_groups=(_terms("禹贡", "禹迹图", "九州", "地图"), _terms("路线", "空间", "坐标", "证据")),
        passage_ids=SLOT_PASSAGES["dayu-slot-memory-map"],
        boundary_ids=("dayu-b-chronology", "dayu-b-memory-map", "dayu-b-transmitted-distance"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-methods",
        label="鲧堵禹疏与组合治理",
        status="supported",
        response_mode="topic",
        question_form="comparison",
        term_groups=(_terms("堵", "鲧", "筑堤"), _terms("疏", "疏导", "禹")),
        passage_ids=SLOT_PASSAGES["dayu-slot-methods"],
        boundary_ids=("dayu-b-modern-waterwork", "dayu-b-teaching-model", "dayu-b-transmitted-distance"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-private-biography",
        label="禹的私人生活与精确个人资料",
        status="unsupported",
        response_mode="boundary",
        question_form="any",
        term_groups=(_terms("大禹", "禹"), _terms("出生", "原话", "妻子", "生日", "相貌", "身高")),
        boundary_ids=("dayu-b-legend-detail", "dayu-b-persona"),
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-revise-with-new-evidence",
        label="新证据如何改变现有判断",
        status="supported",
        response_mode="topic",
        question_form="causality",
        term_groups=(_terms("新材料", "新发现", "新证据", "铭文"), _terms("判断", "修改", "结论", "解释")),
        passage_ids=SLOT_PASSAGES["dayu-slot-revise-with-new-evidence"],
        boundary_ids=("dayu-b-absence", "dayu-b-causation", "dayu-b-erlitou-name"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-source-layers",
        label="传说、文献、自然科学与考古怎样分层",
        status="supported",
        response_mode="overview",
        question_form="comparison",
        term_groups=(_terms("传世文献", "史记", "孟子", "禹贡", "传说"), _terms("材料", "自然科学", "考古", "证据")),
        passage_ids=SLOT_PASSAGES["dayu-slot-source-layers"],
        boundary_ids=("dayu-b-chronology", "dayu-b-local-flood", "dayu-b-transmitted-distance"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-succession",
        label="禹、益、启与继承秩序",
        status="supported",
        response_mode="topic",
        question_form="causality",
        term_groups=(_terms("启", "益", "禹"), _terms("世袭", "继承", "禅让", "王位")),
        passage_ids=SLOT_PASSAGES["dayu-slot-succession"],
        boundary_ids=("dayu-b-causation", "dayu-b-chronology", "dayu-b-transmitted-distance"),
        api_synthesis_allowed=True,
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-three-doors",
        label="三过家门的认识价值与边界",
        status="supported",
        response_mode="boundary",
        question_form="evidence_boundary",
        term_groups=(_terms("三次", "三过家门", "家门"), _terms("事实", "证明", "责任", "证据")),
        passage_ids=SLOT_PASSAGES["dayu-slot-three-doors"],
        boundary_ids=("dayu-b-legend-detail", "dayu-b-transmitted-distance"),
    ),
    EvidenceAnswerSlotV1(
        slot_id="dayu-slot-unknown-engineering",
        label="夏代治水的精确工程参数",
        status="unsupported",
        response_mode="boundary",
        question_form="any",
        term_groups=(_terms("大禹", "工程", "治水"), _terms("公里", "坝高", "工期", "施工图", "流量", "经费", "造价")),
        boundary_ids=("dayu-b-modern-waterwork", "dayu-b-transmitted-distance"),
    ),
)


# Precise locator plus an original extension for every stable V1 passage.
# The extension makes the retrieval unit independently useful without changing
# the historical claim represented by the V1 ID.
V1_ENRICHMENT: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "dayu-p001": ("附件《义务教育历史课程标准（2022年版）》‘课程目标—核心素养内涵’条目", "课程中的证据意识还要求学生说明材料的形成时间、观察对象和可支持的结论强度。因而同一个‘禹’主题下，文本、遗址和自然事件不能被压成一条无差别答案；回答必须先说明材料身份，再给出判断。", ("dayu-b-teaching-model",)),
    "dayu-p002": ("附件《义务教育历史课程标准（2022年版）》‘课程内容—中国古代史’与‘学业质量’条目", "早期国家并非只靠王朝名称来理解。都邑规划、资源集中、礼仪秩序、跨聚落协调和社会分化分别提供不同观察角度；课堂把它们并列，是为了避免把英雄故事直接替代国家形成的复杂过程。", ("dayu-b-causation", "dayu-b-teaching-model")),
    "dayu-p003": ("人民教育出版社产品页‘中国历史七年级上册’目录中的夏商周单元", "目录只能确认学段、单元和主题位置，不能承担史实证明。V2语料因此不摘录教材章节，而以已登记文献、考古与研究资料重新撰写适龄摘要，所有年代仍保留‘约’的性质。", ("dayu-b-chronology",)),
    "dayu-p004": ("《史记》卷二《夏本纪》开篇至禹受命治水叙事段", "《夏本纪》把更早的口传、谱系和政治记忆纳入西汉史学结构。它可用来比较鲧、禹与后继者在后世叙事中的位置，却没有消除近两千年的时间距离；具体对白、工程次序和地名仍需独立互证。", ("dayu-b-persona", "dayu-b-transmitted-distance")),
    "dayu-p005": ("《史记》卷二《夏本纪》禹举益、禹崩与启继位叙事段", "这段继承叙事同时出现禹对益的举荐、诸侯归启等内容，成为后世解释禅让与世袭转折的基础。它能支持‘后人怎样组织王朝起点’的问题，不能单独还原每次政治会议或证明继承只由一种原因决定。", ("dayu-b-causation", "dayu-b-persona", "dayu-b-transmitted-distance")),
    "dayu-p006": ("《史记》卷二《夏本纪》禹劳身焦思、居外十三年相关叙事段", "把长期离家与公共责任联系起来，是这类叙事最稳定的伦理功能。课堂可以分析为什么后世不断重述这种领导者形象，但不把‘三次’当成考古计数，也不为人物补写未经来源支持的家中对白与情感细节。", ("dayu-b-legend-detail", "dayu-b-persona", "dayu-b-transmitted-distance")),
    "dayu-p007": ("《孟子·滕文公上》第4章禹疏九河、八年于外相关段", "孟子借禹讨论治理责任，而不是编写水利工程验收报告。‘疏’在文本中构成与水势相应的治理形象；若要判断某一河段究竟应疏、应防还是迁居，还需要地形、季节、材料与人力信息。", ("dayu-b-modern-waterwork", "dayu-b-persona", "dayu-b-transmitted-distance")),
    "dayu-p008": ("《孟子·滕文公上》第4章‘三过其门而不入’相关句", "这条材料能够确认该母题在战国论说中已经被用来赞扬尽职，也能与西汉叙事比较其传播。它不能证明禹实际经过哪三处门、家人在场说了什么，或把伦理赞颂转换成逐日行程。", ("dayu-b-legend-detail", "dayu-b-persona", "dayu-b-transmitted-distance")),
    "dayu-p009": ("《尚书·夏书·禹贡》九州总叙及导山、导水次序", "九州、山脉、水道和贡赋在篇章中组成有秩序的天下图景。地名经历沿革，文本也有层累与成篇讨论，所以课程只用它研究空间观与政治秩序，不按篇章顺序绘制一条已经证实的夏代施工路线。", ("dayu-b-memory-map", "dayu-b-transmitted-distance")),
    "dayu-p010": ("《尚书·夏书·禹贡》各州田赋、贡物与交通叙述", "环境治理和贡赋秩序在同一文本中出现，说明后世作者倾向把治水功绩与政治整合联系起来。不过文本结构只能提示一种解释路径，不能证明某次洪水工程直接产生国家或所有地区同时接受同一制度。", ("dayu-b-causation", "dayu-b-transmitted-distance")),
    "dayu-p011": ("中国国家博物馆‘古代中国—夏商西周时期’第一单元总述", "博物馆展陈把早期国家放在长时段物质文化变化中呈现，强调政治结构、生产和礼仪相互联系。它适合作为课堂总框架；对某件遗物、某个遗址或王朝名称的判断仍需查看具体考古记录和论证强度。", ("dayu-b-causation",)),
    "dayu-p012": ("中国国家博物馆‘古代中国—夏朝的建立’二里头文化说明", "‘时空大体相合’是一种综合关系：年代可重叠、核心区域可接近、聚落等级可匹配。它显著提高二里头研究夏史的价值，却不等于遗址自报名称，更不能从相合直接推出禹曾在宫殿区生活。", ("dayu-b-chronology", "dayu-b-erlitou-name")),
    "dayu-p013": ("中国国家博物馆‘古代中国—夏商西周时期’经济与礼器展项说明", "专业作坊需要原料、技术、劳力和产品分配，高等级礼器又显示使用者之间并不平等。这些观察可以支持社会分化和资源集中，但不能由一件青铜器倒推出某位王的姓名或具体治水命令。", ("dayu-b-erlitou-name",)),
    "dayu-p014": ("国家发展改革委专题‘二里头文化’之‘最早的广域王权国家’与都邑要素段", "宫城、主干道路、作坊和高等级器物共同构成比单件文物更强的组织证据。它们说明都邑建设存在持续协调和资源集中；至于这些能力是否源于治水，只能作为课堂比较问题，不能直接写成考古结论。", ("dayu-b-causation", "dayu-b-erlitou-name")),
    "dayu-p015": ("国家发展改革委专题‘二里头文化’中‘夏都斟鄩’表述段", "机构文章采用较肯定的历史身份措辞，V2保留该出处，同时把‘考古观察’与‘王朝认定’拆开。学生引用时应写‘该机构据综合研究作此解释’，而不是声称宫殿、道路或方位本身写着‘夏都’。", ("dayu-b-absence", "dayu-b-erlitou-name")),
    "dayu-p016": ("全国哲学社会科学工作办公室文章‘中心区纵横道路与功能分区’段", "纵横道路、围垣和成组建筑的关系来自田野发掘与布局复原，属于可观察遗迹基础上的空间判断。多项遗迹相互配合，比孤立器物更能说明规划；其年代分期和功能解释仍应随新发掘修正。", ("dayu-b-erlitou-name",)),
    "dayu-p017": ("全国哲学社会科学工作办公室文章结语‘二里头与夏后期’判断段", "‘极可能’不是含糊逃避，而是对证据强度的准确标记。年代、地域、文明发展程度和文献传统可以共同增加解释力；缺少可读王朝自名则要求结论保留条件，后续新材料也可能提高或降低对应程度。", ("dayu-b-absence", "dayu-b-erlitou-name")),
    "dayu-p018": ("中国人大网‘中华文明探源工程’中伊洛河流域、二里头年代与中心聚落段", "约距今3800至3500年同样是综合测年形成的范围，而非某位人物的生卒年。区域中心地位可以和传世夏史框架比较，但比较必须分别列出考古年代、文献年代和传统王朝年代，不能相互替代。", ("dayu-b-chronology", "dayu-b-erlitou-name")),
    "dayu-p019": ("中国人大网‘中华文明探源工程’中宫城、作坊、高等级礼器段", "宫城和高等级作坊反映资源、技术与礼仪活动的集中，是解释国家能力的重要组合。公共工程同样需要组织，但目前材料没有把这些建筑直接标注为治水机关；两者之间只能做有边界的机制比较。", ("dayu-b-causation", "dayu-b-erlitou-name")),
    "dayu-p020": ("Science 353(6299), 579–582，摘要与‘Outburst flood’结果段", "研究把地震、滑坡堰塞、湖水积聚和溃决联系为一条自然事件链，并通过多种测年材料提出约公元前1920年的时间。每一步都有方法和误差范围，因此应称‘研究提出’而不是无条件事实。", ("dayu-b-chronology", "dayu-b-local-flood")),
    "dayu-p021": ("Science 353(6299), 579–582，讨论洪水传说与夏代年代的结论段", "论文从自然事件继续推到大洪水记忆和夏代开端，历史解释比地质判断多跨了几个环节。课堂回答应把‘积石峡发生什么’与‘它是否进入远古记忆’分开，再说明人物、传播和王朝仍缺哪些桥接证据。", ("dayu-b-causation", "dayu-b-local-flood")),
    "dayu-p022": ("Journal of Chinese Humanities 3(1), 23–34，对2016年积石峡论文的文本史反思段", "反思文章把新自然科学材料放回中国洪水叙事的长期文本传统中，提醒不同篇章的思想主题和形成过程并不由一个灾害点完全解释。它不是简单否认洪水，而是要求对自然事件和叙事传播分别举证。", ("dayu-b-local-flood", "dayu-b-transmitted-distance")),
    "dayu-p023": ("Journal of Chinese Humanities 3(1), 23–34，结论部分关于禹、洪水传说与夏史连接", "即使局地洪水获得更强地质支持，‘灾害存在’、‘禹组织治理’和‘夏王朝建立’仍是三个命题。每个命题需要不同材料；把其中一个成立写成三个都成立，是RAG回答必须阻止的越界推论。", ("dayu-b-absence", "dayu-b-causation", "dayu-b-local-flood", "dayu-b-persona")),
    "dayu-p024": ("Library of Congress item 2021668264，馆藏记录‘Date Created/Published: 1136’", "馆藏日期把这件地图材料固定在南宋，而不是传统禹时代。它能直接支持地图史、刻石和后世地理知识研究；与禹有关的题名和内容说明记忆延续，不把制作年代向前移动数千年。", ("dayu-b-chronology", "dayu-b-memory-map")),
    "dayu-p025": ("Library of Congress item 2021668264，地图图像及馆藏说明", "地图上的河流、海岸与行政空间体现制图者所处时代的知识整理。若课程把它和《禹贡》并置，目的是比较后世怎样给‘禹迹’赋形，而不是把所有线条转换成夏代河道与工程坐标。", ("dayu-b-memory-map",)),
    "dayu-p026": ("中国国家博物馆二里头展陈说明与公开器物、遗址信息中的文字证据边界", "丰富遗存证明二里头社会复杂，并不等于已经发现一件刻有‘禹’且年代、释读均获公认的器物。人物模式回答这类问题时必须承认自己不能知道后世发掘，也不能借角色口吻制造铭文。", ("dayu-b-absence", "dayu-b-erlitou-name", "dayu-b-persona")),
    "dayu-p027": ("附件《义务教育历史课程标准（2022年版）》‘学业质量—运用材料解释历史’条目及L101关卡变量定义", "模型把每次行动造成的短期收益与长期负担显性化：例如快速施工可能降水患却损耗粮食和体力。数值只保证游戏规则可反馈，不宣称古人曾按百分制记录信任，也不能用于现代工程计算。", ("dayu-b-modern-waterwork", "dayu-b-teaching-model")),
    "dayu-p028": ("《孟子·滕文公上》第4章任命、劳作与治水叙事；L101人物建模说明", "文本把成就集中于禹，公共工程在现实机制上却必然涉及观察、运输、开挖、粮食和聚落协商。课堂合成人群让这些成本可见，但他们不是有出土姓名的证人；人物回答只能解释权衡。", ("dayu-b-persona", "dayu-b-teaching-model")),
    "dayu-p029": ("中国国家博物馆‘古代中国—夏朝的建立’年代框架说明", "‘约公元前21世纪’用于把传统夏代框架放入通史顺序，与二里头测年范围也不是同一种来源。回答应分别标注‘传统王朝年代’和‘考古测年范围’，不能用前者替代遗址分期。", ("dayu-b-chronology", "dayu-b-erlitou-name")),
    "dayu-p030": ("附件《义务教育历史课程标准（2022年版）》‘学业质量’证据表达要求及L101卷宗模板", "卷宗中的选择记录来自学生会话，来源卡来自当前发布，解释句则由学生或受约束服务生成。三者要分栏保存，使教师能看见结论如何形成，也能在后端失败时保留本地推理过程。", ("dayu-b-teaching-model",)),
}


# (id, source, title, text, summary, locator, fact donor IDs, person donor ID,
#  keywords, evidence kind, certainty, chronology, boundaries)
ADDITIONAL_PASSAGES = (
    (
        "dayu-p031", "src-shiji-xia", "鲧失利与禹受命之间的叙事转换",
        "《史记·夏本纪》先叙鲧治水未成，再叙舜举禹续治，把两人安排进一条失败—接续—成功的王朝叙事。这个结构能够说明西汉史家怎样解释领导权转移，也促成后世‘鲧堵禹疏’的鲜明对比；但篇章没有提供可供现代复核的坝体剖面、流量记录和逐段工法，不能据此判定鲧在任何地点都只会筑堵，或禹从未使用防护措施。回答方法题时应先说明这种对照来自何时的文本，再把现代工程条件与文本评价分别列出。",
        "文本提供人物与评价结构，不提供现代工程参数。",
        "《史记》卷二《夏本纪》鲧受命、被殛与禹受荐治水叙事段",
        ("dayu-p004", "dayu-p007"), "dayu-p004", ("工程组合", "鲧", "禹"), "transmitted_text", "interpretation",
        "西汉文本整理的远古叙事。", ("dayu-b-modern-waterwork", "dayu-b-persona", "dayu-b-transmitted-distance"),
    ),
    (
        "dayu-p032", "src-shiji-xia", "禹、益、启继承叙事中的多重解释",
        "《夏本纪》同时保留禹举益、禹死后诸侯归启等环节，因此继承并不是一句‘父传子’就能完整概括。后世可把它解释为政治声望、支持联盟和家族继承共同作用的转折。课堂可以比较这些解释，却不能把诸侯态度、禹的真实意图或启取得位置的全过程当作西汉作者亲历的事实；更不能据此宣称王朝形成只有唯一原因。若要评价世袭转折，还应追问其他传世材料如何叙述，以及是否存在可对应的同时代制度记录。",
        "继承框架可讨论权力秩序，动机和过程仍需保留边界。",
        "《史记》卷二《夏本纪》禹荐益、十年禹崩及诸侯朝启相关叙事段",
        ("dayu-p005", "dayu-p010"), "dayu-p005", ("世袭", "启", "益", "禅让"), "transmitted_text", "interpretation",
        "西汉史家整理的王朝起源叙事。", ("dayu-b-causation", "dayu-b-persona", "dayu-b-transmitted-distance"),
    ),
    (
        "dayu-p033", "src-mengzi-tengwen", "责任伦理为何不能替代事实核验",
        "《孟子》把禹多年在外和过门不入用于论证治理者应以天下事务为重。作为思想史材料，它直接显示战国论辩如何调动大禹形象，也解释了这一故事为何在后世教育中持续有力量。可是伦理意义越鲜明，越需要区分修辞与现场：次数、路程、家庭对话、当时情绪都没有因此获得同时代证据，学生只能评价母题，不能假冒人物补述私人记忆。由此得到的稳妥结论是‘战国人已这样讲述和评价禹’，而不是‘每个动作已被当时记录’。",
        "可以分析责任伦理，不能把道德叙事改写成人物档案。",
        "《孟子·滕文公上》第4章‘八年于外，三过其门而不入’相关段",
        ("dayu-p006", "dayu-p008"), "dayu-p006", ("三过家门", "伦理记忆", "责任"), "transmitted_text", "legend",
        "战国论说中的后世记忆。", ("dayu-b-legend-detail", "dayu-b-persona", "dayu-b-transmitted-distance"),
    ),
    (
        "dayu-p034", "src-shangshu-yugong", "把《禹贡》画成施工路线会丢失什么",
        "《禹贡》的叙述在州域、山川、水道、土产和贡赋之间转换，目标是构造一个有层次的天下秩序。若只把地名依次连接，学生会误以为文本保存了同一时间完成的旅行或工程日志，也会忽略地名沿革和篇章层累。更稳妥的地图应分别标出文本空间、现代推定位置和不确定区，并在图例中明确它不是夏代测绘原图。地图交互还应让学生切换材料年代，使南宋制图、传世篇章和现代考古点不会在视觉上混为一层。",
        "《禹贡》适合研究空间秩序，不适合直接生成确定施工线。",
        "《尚书·夏书·禹贡》九州总叙、导山导水与贡道段落的结构对读",
        ("dayu-p009", "dayu-p025"), None, ("九州", "施工路线", "禹贡"), "boundary_note", "consensus",
        "传世篇章的空间表达，形成时间晚于传统禹时代。", ("dayu-b-memory-map", "dayu-b-transmitted-distance"),
    ),
    (
        "dayu-p035", "src-chnmuseum-early-state", "高等级器物必须放回生产与使用关系",
        "二里头出土的青铜礼器、玉器和绿松石制品具有较高制作要求，和专业手工业分工一起显示资源、技术与使用权存在集中。单列器物名称只能证明‘有物’，把作坊、原料、制作难度、出土空间和使用差异结合，才能讨论社会分化。即便如此，这些器物仍不直接回答谁组织过洪水治理，也不写出夏王朝的自称。学生引用器物时应同时写出出土空间或生产背景，避免用一张精美文物图片代替完整论证。",
        "器物组合支持社会分化与资源集中，不直接证明禹或治水机构。",
        "中国国家博物馆‘古代中国—夏商西周时期’青铜、玉石与绿松石器展项说明",
        ("dayu-p013", "dayu-p019"), None, ("专业分工", "礼器", "社会分化"), "archaeological_evidence", "consensus",
        "二里头文化考古材料的现代展陈说明。", ("dayu-b-causation", "dayu-b-erlitou-name"),
    ),
    (
        "dayu-p036", "src-ndrc-erlitou", "大型中心与周边聚落构成区域层级",
        "机构资料把二里头置于更广的区域聚落网络中理解：大型中心拥有宫殿、道路和高等级作坊，影响范围又超出核心区。这种中心—周边差异有助于研究广域政治整合，而不仅是说遗址面积很大。它增加二里头与早期国家讨论的相关性，但‘广域王权’仍是从聚落层级、资源流动和礼仪分布作出的综合解释。若只看到中心遗址而不比较周边聚落，就无法判断资源和礼仪影响是否真正超出都邑边界。",
        "区域层级是早期国家的重要组合证据，仍需与王朝自名分开。",
        "国家发展改革委专题‘二里头文化’之都邑规模、文化影响与广域王权段",
        ("dayu-p012", "dayu-p014"), None, ("区域层级", "广域王权", "聚落"), "scholarly_interpretation", "interpretation",
        "现代机构对二里头考古成果的综合解释。", ("dayu-b-causation", "dayu-b-erlitou-name"),
    ),
    (
        "dayu-p037", "src-nopss-erlitou-layout", "道路、围垣和院落的组合比单点发现更有解释力",
        "二里头中心区的道路并非孤立线段，它们与围垣、宫殿建筑基址、作坊区和墓葬空间形成相互关系。考古工作者依据叠压、打破与分期判断建设顺序，再复原功能分区。课堂回答应说明‘直接观察到遗迹’与‘据关系复原规划’是两层信息；规划能力可以支持政治组织研究，却不能自动确认规划者姓名。发掘揭示的先后关系还可能随新区揭露而调整，因此示意图必须标记分期和复原性质。",
        "布局证据包含遗迹观察和空间解释两层。",
        "全国哲学社会科学工作办公室文章‘中心区道路、围垣和分区’及考古判断说明段",
        ("dayu-p016", "dayu-p017"), None, ("功能分区", "围垣", "道路网"), "archaeological_evidence", "consensus",
        "二里头田野考古及现代布局复原。", ("dayu-b-erlitou-name",),
    ),
    (
        "dayu-p038", "src-npc-civilization", "探源工程为何强调多学科与多地点比较",
        "中华文明探源相关综合资料把年代测定、聚落考古、手工业、礼仪遗存和区域互动放在同一研究框架内。这样的证据链不依赖一件‘定名文物’，而通过多个可重复观察的指标讨论文明和早期国家。它也意味着单一故事、单一洪水点或单一都城不能承担全部结论，任何王朝对应都要接受新测年和新发掘的持续检验。多学科并不等于自动一致；若测年、空间分布和文本框架出现冲突，答案应展示冲突而不是挑选最顺耳的一项。",
        "多学科组合增强解释，也要求结论可随新材料修正。",
        "中国人大网‘中华文明起源与早期发展综合研究’多学科方法与二里头成果综述段",
        ("dayu-p018", "dayu-p019"), None, ("多学科", "探源工程", "证据链"), "scholarly_interpretation", "consensus",
        "现代多学科考古研究框架。", ("dayu-b-causation", "dayu-b-erlitou-name"),
    ),
    (
        "dayu-p039", "src-science-jishi", "积石峡洪水假说由多环节组成",
        "原研究不是只凭传说寻找地点，而是把地震活动、滑坡坝、被淹聚落材料、溃决沉积和下游文化年代连接起来。每一环节使用的材料和推断方式不同：沉积可支持洪水过程，测年给出范围，文化序列用于历史比较。将整条链简写成‘发现大禹洪水’会同时抹去自然科学不确定性与历史连接的额外假设。",
        "自然事件链可以检验，但不能省略跨到人物和王朝的推论。",
        "Science 353(6299), 579–582，研究设计、地震滑坡坝与溃决沉积结果段",
        ("dayu-p020", "dayu-p021"), None, ("地震", "积石峡", "证据链"), "scholarly_interpretation", "disputed",
        "对约公元前1920年局地自然事件的现代研究。", ("dayu-b-causation", "dayu-b-local-flood"),
    ),
    (
        "dayu-p040", "src-science-jishi", "约公元前1920年并非无误差的日历日期",
        "论文给出的年代来自放射性碳等材料和事件关系的综合，不是洪水当年留下的纪年牌。把它与传统夏代起点比较时，还要面对样品对应、校正区间、文化阶段和王朝框架并非同一尺度的问题。因此课堂写作应使用‘约’和‘研究提出’，不应把1920写成精确开工年份，更不能据此计算禹的年龄。",
        "测年范围用于比较事件，不提供禹的个人年表。",
        "Science 353(6299), 579–582，年代测定方法、校正结果与历史年代讨论段",
        ("dayu-p020", "dayu-p029"), None, ("公元前1920年", "测年", "积石峡"), "boundary_note", "disputed",
        "现代科学测年范围与传统王朝年代框架的比较。", ("dayu-b-chronology", "dayu-b-local-flood", "dayu-b-persona"),
    ),
    (
        "dayu-p041", "src-allan-jishi", "对洪水假说的质疑不是简单二选一",
        "学术反思可以接受积石峡存在重要洪水材料，同时质疑它是否足以解释大洪水传说和夏史。这不是在‘洪水发生’与‘洪水完全虚构’之间二选一，而是逐段检查：事件规模如何、传播链是否存在、文本母题何时形成、王朝年代如何对应。学生据此可以给出暂定判断，并明确哪条新证据会改变判断。",
        "争议要求拆分命题，而不是把资料分成全真与全假。",
        "Journal of Chinese Humanities 3(1), 23–34，对积石峡事件、传说结构与夏史对应的分项讨论",
        ("dayu-p022", "dayu-p023"), None, ("争议", "洪水传说", "积石峡"), "scholarly_interpretation", "interpretation",
        "2017年对2016年假说的学术反思。", ("dayu-b-causation", "dayu-b-local-flood", "dayu-b-transmitted-distance"),
    ),
    (
        "dayu-p042", "src-loc-yuji-map", "《禹迹图》的制作年代本身就是证据",
        "馆藏记录给出的1136年让地图首先成为南宋史料：可研究当时怎样表现河流、海岸、行政空间和大禹文化记忆。题名涉及禹，不代表图面来自禹手中；后世不断绘制‘禹迹’反而说明大禹叙事具有长久的空间想象力量。课堂地图应显示制作年代，并把它与二里头遗址点、积石峡自然事件点分层。",
        "先问地图何时制作，再问它能说明哪个时代。",
        "Library of Congress item 2021668264，日期、题名、图像与馆藏元数据",
        ("dayu-p024", "dayu-p025"), None, ("南宋", "地图史", "禹迹图"), "boundary_note", "consensus",
        "1136年地图材料，距传统禹时代数千年。", ("dayu-b-chronology", "dayu-b-memory-map"),
    ),
    (
        "dayu-p043", "src-moe-2022", "回答历史问题先写主张再核对材料",
        "证据推理可以用四步完成：先把问题改写成可检验主张，再列出材料类型与年代，接着说明每项材料支持到哪里，最后写出仍缺什么。这个方法使‘三过家门是真的吗’转化为‘哪些文本何时记录该母题，它能支持伦理记忆还是现场次数’，也使模型无权用流畅语言跨过证据缺口。",
        "主张—材料—边界—缺口是本课问答的基本结构。",
        "附件《义务教育历史课程标准（2022年版）》‘史料实证’‘历史解释’核心素养条目及L101问答规范",
        ("dayu-p001", "dayu-p030"), None, ("历史解释", "史料实证", "证据边界"), "curriculum_goal", "consensus",
        "现代课程标准与本课回答规范。", ("dayu-b-teaching-model",),
    ),
    (
        "dayu-p044", "src-moe-2022", "比较证据时不能只数来源数量",
        "多个网页重复同一种后世说法，不等于获得多种独立证据。L101比较时至少区分传世文本、遗址和器物、自然科学研究、现代教学解释；还要检查它们是否真的回答同一个命题。二里头布局可回答社会组织，积石峡沉积可回答局地灾害，《史记》可回答西汉夏史叙述，三者不能相互冒名，却能共同界定问题。",
        "证据多样性取决于材料能力，不取决于链接数量。",
        "附件《义务教育历史课程标准（2022年版）》史料实证要求及L101四层证据对照表",
        ("dayu-p001", "dayu-p012", "dayu-p020"), None, ("四层证据", "材料能力", "比较"), "teaching_explanation", "consensus",
        "现代课堂的证据比较方法。", ("dayu-b-causation", "dayu-b-teaching-model"),
    ),
    (
        "dayu-p045", "src-moe-2022", "组合治理比背诵唯一方法更接近历史思考",
        "课堂中的踏勘、局部加固、疏浚分流、轮换劳作、迁居和粮食调配不是声称禹实际依次做过这些事，而是把公共治理中的约束显性化。地形不同，疏和防的作用也不同；资源有限时，先保护谁、让谁承担劳作会影响信任。评价答案应看学生是否说明条件、代价和证据，而不是是否只按下‘疏’字。",
        "关卡练习条件与权衡，不复刻夏代施工。",
        "附件《义务教育历史课程标准（2022年版）》历史解释要求及L101六回合规则说明",
        ("dayu-p007", "dayu-p027"), None, ("组合治理", "疏导", "防护"), "teaching_explanation", "interpretation",
        "现代课堂情境，不是夏代工程记录。", ("dayu-b-modern-waterwork", "dayu-b-teaching-model"),
    ),
    (
        "dayu-p046", "src-moe-2022", "公共工程扩大权威也扩大责任",
        "跨聚落工程需要共享地形信息、调配粮食、组织劳力并让承诺得到执行，这些机制可能提高组织者的声望和命令能力。相同机制也可能造成强征、误工、分配不公与风险转移。课堂因此不把水位下降当作唯一胜利条件，而同时记录劳作者状态与公共信任；这是一种历史解释模型，不是‘治水必然建国’的公式。",
        "权威与代价要在同一因果链中评价。",
        "附件《义务教育历史课程标准（2022年版）》历史解释与责任意识要求及L101治理变量说明",
        ("dayu-p002", "dayu-p027"), None, ("公共工程", "权威", "社会代价"), "teaching_explanation", "interpretation",
        "现代课堂对公共治理机制的分析。", ("dayu-b-causation", "dayu-b-teaching-model"),
    ),
    (
        "dayu-p047", "src-moe-2022", "人物模式必须主动承认自己不知道后世材料",
        "角色化回答的价值是呈现立场差异，例如禹强调协作、劳作者追问口粮与轮换；它不是让模型假装穿越。人物不能说自己见过二里头发掘、放射性碳测年、1136年地图或现代课程标准。涉及这些材料时，系统应转为课程专家口吻或明确‘依据不足’，并始终显示‘角色化教学表达，不是史料原话’。",
        "人物语气不能扩大人物的知识年代。",
        "附件《义务教育历史课程标准（2022年版）》史料实证要求及L101人物档案知识边界",
        ("dayu-p026", "dayu-p028"), "dayu-p028", ("人物边界", "角色化表达", "依据不足"), "boundary_note", "consensus",
        "现代课堂人物建模规范。", ("dayu-b-persona", "dayu-b-teaching-model"),
    ),
    (
        "dayu-p048", "src-moe-2022", "新证据应改变哪一层结论",
        "如果未来发现年代、出土环境和释读都可靠的同时代文字，首先要看它写了什么：出现王朝自名可加强身份判断，出现人物名可加强人物对应，记录水患仍需判断地点和范围。新证据不会自动让所有传说细节同时成真。相反，新的测年或地层关系也可能削弱既有对应。好的卷宗应注明原判断、受影响的证据层和修改后的不确定性。",
        "新材料只改变它直接相关的命题，不给整套故事一次性盖章。",
        "附件《义务教育历史课程标准（2022年版）》证据意识与历史解释要求及L101卷宗修订提示",
        ("dayu-p023", "dayu-p026", "dayu-p030"), None, ("新证据", "结论修订", "证据层"), "teaching_explanation", "consensus",
        "面向未来发现的现代证据推理练习。", ("dayu-b-absence", "dayu-b-causation", "dayu-b-erlitou-name", "dayu-b-teaching-model"),
    ),
)


def _slot_ids_by_passage() -> dict[str, tuple[str, ...]]:
    values: dict[str, set[str]] = {}
    for slot_id, passage_ids in SLOT_PASSAGES.items():
        for passage_id in passage_ids:
            values.setdefault(passage_id, set()).add(slot_id)
    return {key: tuple(sorted(item)) for key, item in values.items()}


def build_dayu_evidence_v2(
    *,
    sealed_by: str = "chronovita-content-team",
    sealed_at: datetime | None = None,
    corpus_version: int = 2,
) -> EvidenceCorpusV2:
    """Build and sign the complete L101 V2 evidence corpus."""

    course = build_dayu_course_draft()
    v1 = build_dayu_evidence_draft(course)
    by_id = {item.passage_id: item for item in v1.passages}
    slot_ids_by_passage = _slot_ids_by_passage()
    passages: list[EvidencePassageV2] = []

    for passage_id in sorted(by_id):
        item = by_id[passage_id]
        locator, extension, boundary_ids = V1_ENRICHMENT[passage_id]
        passages.append(
            EvidencePassageV2(
                passage_id=item.passage_id,
                source_id=item.source_id,
                title=item.title,
                text=f"{item.text}{extension}",
                summary=item.summary,
                source_locator=locator,
                fact_ids=item.fact_ids,
                person_ids=item.person_ids,
                keywords=item.keywords,
                answer_slot_ids=slot_ids_by_passage.get(item.passage_id, ()),
                boundary_ids=tuple(sorted(boundary_ids)),
                persona_scope=("expert_and_listed_people" if item.person_ids else "expert_only"),
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
        locator,
        donor_ids,
        person_donor_id,
        keywords,
        evidence_kind,
        certainty,
        chronology_note,
        boundary_ids,
    ) in ADDITIONAL_PASSAGES:
        donors = [by_id[item] for item in donor_ids]
        fact_ids = tuple(sorted({fact_id for donor in donors for fact_id in donor.fact_ids}))
        person_ids = by_id[person_donor_id].person_ids if person_donor_id else ()
        passages.append(
            EvidencePassageV2(
                passage_id=passage_id,
                source_id=source_id,
                title=title,
                text=text,
                summary=summary,
                source_locator=locator,
                fact_ids=fact_ids,
                person_ids=person_ids,
                keywords=tuple(sorted(set(keywords))),
                answer_slot_ids=slot_ids_by_passage.get(passage_id, ()),
                boundary_ids=tuple(sorted(boundary_ids)),
                persona_scope=("expert_and_listed_people" if person_ids else "expert_only"),
                evidence_kind=evidence_kind,
                certainty=certainty,
                chronology_note=chronology_note,
            )
        )

    moment = sealed_at or DAYU_V2_CREATED_AT
    provisional = EvidenceCorpusV2(
        corpus_id=DAYU_CORPUS_ID,
        course_id=COURSE_ID,
        lesson_id=LESSON_ID,
        corpus_version=corpus_version,
        title="L101 大禹治水正式证据库 V2",
        scope_note=(
            "仅服务 C-prequin-state/L101 的精确发布。48个稳定片段把传说、传世文献、"
            "自然科学、考古观察和教学解释分层；回答先匹配封闭槽位，再受片段定位、"
            "人物范围和边界约束。不得用模型常识补写私人细节、工程参数或王朝自名。"
        ),
        supersedes_checksum=DAYU_V1_CHECKSUM,
        sources=_evidence_sources(),
        boundaries=BOUNDARIES,
        answer_slots=ANSWER_SLOTS,
        passages=tuple(sorted(passages, key=lambda item: item.passage_id)),
        created_at=moment,
        sealed_at=moment,
        sealed_by=sealed_by,
        checksum="0" * 64,
    )
    return sign_evidence_contract(provisional)


__all__ = [
    "ANSWER_SLOTS",
    "BOUNDARIES",
    "DAYU_V1_CHECKSUM",
    "DAYU_V2_CREATED_AT",
    "SLOT_PASSAGES",
    "build_dayu_evidence_v2",
]
