from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.contracts.rules_v1 import (
    evaluate_rule_action,
    initial_rule_snapshot,
    render_rule_narrative,
)
from services.contracts.v1 import (
    ActionRuleV1,
    CoursePackageV1,
    DossierChoiceV1,
    DossierTemplateV1,
    DossierV1,
    EndingRuleV1,
    EventRuleV1,
    FactV1,
    GameSessionV1,
    KeywordV1,
    KnowledgeEdgeV1,
    KnowledgeNodeV1,
    MapPointV1,
    NpcChangeV1,
    NpcConditionV1,
    NpcEffectV1,
    NpcSpecV1,
    NpcStateV1,
    NarrativeMessageV1,
    ObservedEntityV1,
    PersonV1,
    RuntimeBundleV1,
    ScenarioNodeV1,
    ScenarioTemplateV1,
    ScenarioRefV1,
    SourceRefV1,
    StateChangeV1,
    StateConditionV1,
    StateEffectV1,
    StateSnapshotV1,
    StateVariableV1,
    TurnConditionV1,
    TurnV1,
    calculate_contract_checksum,
)


_BASE_TIME = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
_SHANGYANG_NOTICE = "【教师待审/技术占位】"


def build_dayu_bundle() -> RuntimeBundleV1:
    scenario = _build_scenario()
    course = _build_course(str(scenario.checksum))
    states = _state_history()
    turns = _build_turns(states, scenario)
    dossier = _build_dossier(states, str(course.checksum), str(scenario.checksum))
    session = GameSessionV1(
        session_id="session-dayu-demo-001",
        user_id="student-demo",
        course_id=course.course_id,
        lesson_id=course.lesson_id,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        course_content_version=course.content_version,
        course_checksum=str(course.checksum),
        scenario_checksum=str(scenario.checksum),
        engine_version="rules-v1.0.0",
        random_seed="dayu-demo-seed",
        status="completed",
        revision=6,
        current_turn=len(turns),
        current_state=states[-1],
        npc_states=[
            NpcStateV1(
                person_id="person-yu",
                attitude=20,
                trust=25,
                known_fact_refs=[],
                last_basis_refs=["fact-flood-method"],
                updated_turn=0,
            ),
            NpcStateV1(
                person_id="person-people-representative",
                attitude=0,
                trust=0,
                known_fact_refs=[],
                updated_turn=0,
            ),
            NpcStateV1(
                person_id="person-tribe-leader",
                attitude=20,
                trust=15,
                known_fact_refs=["fact-cooperation"],
                last_basis_refs=["fact-cooperation"],
                updated_turn=2,
            ),
            NpcStateV1(
                person_id="person-artisan",
                attitude=0,
                trust=0,
                known_fact_refs=[],
                updated_turn=0,
            ),
        ],
        turns=turns,
        triggered_event_ids=["event-heavy-rain", "event-cooperation"],
        summary="勘察地势后争取部族协作，以疏导工程逐步降低水患。",
        flags={"success_candidate": True},
        narrative_flags={"legacy_demo_flag": "untrusted-narrative-metadata"},
        observed_entities=[
            ObservedEntityV1(
                entity_id="entity-heavy-rain",
                name="暴雨",
                kind="event",
                description="第三回合触发的规则事件。",
                first_seen_turn=3,
            )
        ],
        history=[
            NarrativeMessageV1(role="system", text="大禹治水技术样板开始。", turn_no=0),
            NarrativeMessageV1(role="player", text="先勘察地势和河道", turn_no=1),
            NarrativeMessageV1(
                role="narrator",
                text="【技术样板】规则层记录了第一回合状态变化。",
                turn_no=1,
            ),
        ],
        ending_id="ending-water-controlled",
        dossier_id=dossier.dossier_id,
        started_at=_BASE_TIME,
        updated_at=_BASE_TIME + timedelta(minutes=25),
        ended_at=_BASE_TIME + timedelta(minutes=25),
    )
    return RuntimeBundleV1(course=course, scenario=scenario, session=session, dossier=dossier)


def build_shangyang_bundle() -> RuntimeBundleV1:
    scenario = _build_shangyang_scenario()
    course = _build_shangyang_course(str(scenario.checksum))
    return RuntimeBundleV1(course=course, scenario=scenario, session=None, dossier=None)


def example_documents() -> dict[str, object]:
    dayu_bundle = build_dayu_bundle()
    shangyang_bundle = build_shangyang_bundle()
    return {
        "dayu-course-package.json": dayu_bundle.course,
        "dayu-scenario-template.json": dayu_bundle.scenario,
        "dayu-game-session.json": dayu_bundle.session,
        "dayu-dossier.json": dayu_bundle.dossier,
        "dayu-runtime-bundle.json": dayu_bundle,
        "shangyang-course-package.json": shangyang_bundle.course,
        "shangyang-scenario-template.json": shangyang_bundle.scenario,
    }


def _build_course(scenario_checksum: str) -> CoursePackageV1:
    package = CoursePackageV1(
        package_id="pkg-dayu-flood-control",
        course_id="C-early-civilization",
        lesson_id="dayu-flood-control",
        content_version=1,
        status="sealed",
        title="大禹治水（技术样板）",
        unit="文明起源与早期国家",
        era="传说时代",
        body=[
            "【教师待审】本段仅用于验证课程发布与关卡运行链路，正式课文由教师团队替换。",
            "【教师待审】样板围绕治水方法、公共动员和部族协作组织可计算的历史局势。",
        ],
        abstract="大禹治水端到端技术样板，内容结论均等待教师审校。",
        teaching_objectives=[
            "理解治水方案需要同时考虑工程方法、资源和公共协作。",
            "能够依据状态变化解释一次选择的收益与代价。",
        ],
        keywords=[
            KeywordV1(
                keyword_id="keyword-flood-control",
                word="治水",
                gloss="【教师待审】组织应对水患的工程与社会行动。",
                source_ref_ids=["source-dayu-placeholder"],
            ),
            KeywordV1(
                keyword_id="keyword-cooperation",
                word="部族协作",
                gloss="【教师待审】不同群体围绕共同目标进行资源与行动协调。",
                source_ref_ids=["source-dayu-placeholder"],
            ),
        ],
        people=[
            PersonV1(
                person_id="person-yu",
                name="禹",
                role="治水行动的主导者",
                persona="【教师待审】强调实地勘察、长期坚持和方法调整。",
                boundaries=["不得把传说细节表述成无争议的考古定论。"],
                fact_refs=["fact-flood-method"],
                source_ref_ids=["source-dayu-placeholder"],
            ),
            PersonV1(
                person_id="person-people-representative",
                name="百姓代表",
                role="表达劳役与生计压力",
                boundaries=["只表达样板设定中的群体处境，不虚构具体史料引文。"],
                fact_refs=["fact-public-mobilization"],
                source_ref_ids=["source-dayu-placeholder"],
            ),
            PersonV1(
                person_id="person-tribe-leader",
                name="部族首领",
                role="表达协作与资源分配压力",
                boundaries=["不得使用后世国家制度概念替代当时语境。"],
                fact_refs=["fact-cooperation"],
                source_ref_ids=["source-dayu-placeholder"],
            ),
            PersonV1(
                person_id="person-artisan",
                name="水利工匠",
                role="解释地势、河道与工程取舍",
                boundaries=["工程解释必须标注为教学模型，不伪装成出土原话。"],
                fact_refs=["fact-flood-method"],
                source_ref_ids=["source-dayu-placeholder"],
            ),
        ],
        map_points=[
            MapPointV1(
                point_id="map-yellow-river-middle",
                label="黄河中游技术样板点",
                region="黄河中游",
                note="【教师待审】仅作地图与状态引擎联调，不代表精确历史坐标。",
                kind="teaching-placeholder",
            )
        ],
        facts=[
            FactV1(
                fact_id="fact-flood-method",
                statement="【教师待审】关卡需要区分短期堵水与勘察疏导的工程后果。",
                source_ref_ids=["source-dayu-placeholder"],
                certainty="interpretation",
            ),
            FactV1(
                fact_id="fact-public-mobilization",
                statement="【教师待审】持续治水会消耗粮食、劳力并影响民众承受度。",
                source_ref_ids=["source-dayu-placeholder"],
                certainty="interpretation",
            ),
            FactV1(
                fact_id="fact-cooperation",
                statement="【教师待审】跨群体协作是样板局势中的关键约束变量。",
                source_ref_ids=["source-dayu-placeholder"],
                certainty="interpretation",
            ),
        ],
        source_refs=[
            SourceRefV1(
                source_id="source-dayu-placeholder",
                title="大禹治水样板资料占位",
                kind="other",
                citation_note="教师团队需要在正式发布前替换为教材、课程标准与审校资料。",
                reliability="pending",
            )
        ],
        qa_points=["为什么工程方案会同时改变水患、资源和民心？"],
        level_goals=["在六回合内控制水患，并保留基本民心、粮食与劳力。"],
        scenario_refs=[
            ScenarioRefV1(
                scenario_id="scenario-dayu-flood-control",
                scenario_version=1,
                checksum=scenario_checksum,
                primary=True,
            )
        ],
        teacher_notes="所有历史内容均为开发夹具，不承担正式教学结论。",
        created_at=_BASE_TIME - timedelta(days=1),
        updated_at=_BASE_TIME,
        sealed_at=_BASE_TIME,
        sealed_by="fixture-builder",
        checksum="0" * 64,
    )
    return _with_checksum(package, CoursePackageV1)


def _build_scenario() -> ScenarioTemplateV1:
    fact_refs = ["fact-flood-method", "fact-public-mobilization", "fact-cooperation"]
    scenario = ScenarioTemplateV1(
        scenario_id="scenario-dayu-flood-control",
        scenario_version=1,
        status="sealed",
        course_id="C-early-civilization",
        lesson_id="dayu-flood-control",
        title="大禹治水：疏堵与协作",
        scenario_type="crisis_governance",
        student_role="受命协助禹组织治水的行动者",
        objective="在六回合内降低水患，同时维持粮食、劳力、民心和部族信任。",
        opening="【教师待审】暴雨季将至，各部族正在等待你的第一项治水安排。",
        max_turns=6,
        variables=[
            StateVariableV1(variable_id="flood_risk", label="水患", initial=70),
            StateVariableV1(variable_id="public_support", label="民心", initial=55),
            StateVariableV1(variable_id="food", label="粮食", initial=70),
            StateVariableV1(variable_id="labor", label="劳力", initial=70),
            StateVariableV1(variable_id="tribal_trust", label="部族信任", initial=45),
            StateVariableV1(variable_id="engineering_knowledge", label="工程认知", initial=35),
        ],
        npcs=[
            NpcSpecV1(
                person_id="person-yu",
                display_name="禹",
                role="治水主导者",
                persona="【教师待审】要求行动者观察地势并承担长期工程代价。",
                initial_attitude=20,
                initial_trust=25,
                fact_refs=["fact-flood-method"],
            ),
            NpcSpecV1(
                person_id="person-people-representative",
                display_name="百姓代表",
                role="民生压力反馈者",
                fact_refs=["fact-public-mobilization"],
            ),
            NpcSpecV1(
                person_id="person-tribe-leader",
                display_name="部族首领",
                role="协作与资源谈判者",
                fact_refs=["fact-cooperation"],
            ),
            NpcSpecV1(
                person_id="person-artisan",
                display_name="水利工匠",
                role="工程方案解释者",
                fact_refs=["fact-flood-method"],
            ),
        ],
        action_rules=[
            ActionRuleV1(
                action_id="survey-terrain",
                label="勘察地势",
                aliases=["勘察河道", "查看地形"],
                effects=[
                    StateEffectV1(variable_id="engineering_knowledge", value=15),
                    StateEffectV1(variable_id="flood_risk", value=5),
                ],
                feedback="工程认知提升，但勘察期间水患仍在发展。",
                fact_refs=["fact-flood-method"],
            ),
            ActionRuleV1(
                action_id="reinforce-dam",
                label="抢修堤坝",
                effects=[
                    StateEffectV1(variable_id="flood_risk", value=-10),
                    StateEffectV1(variable_id="food", value=-5),
                    StateEffectV1(variable_id="public_support", value=-5),
                ],
                feedback="短期风险下降，但资源和民众承受度受损。",
                fact_refs=["fact-flood-method", "fact-public-mobilization"],
            ),
            ActionRuleV1(
                action_id="open-channels",
                label="开挖疏导线",
                available_when=[
                    StateConditionV1(variable_id="engineering_knowledge", operator="gte", value=50)
                ],
                effects=[
                    StateEffectV1(variable_id="flood_risk", value=-25),
                    StateEffectV1(variable_id="labor", value=-12),
                    StateEffectV1(variable_id="engineering_knowledge", value=10),
                ],
                feedback="疏导降低水患，但消耗劳力。",
                fact_refs=["fact-flood-method", "fact-public-mobilization"],
            ),
            ActionRuleV1(
                action_id="explain-plan",
                label="向部族解释计划",
                effects=[
                    StateEffectV1(variable_id="public_support", value=10),
                    StateEffectV1(variable_id="tribal_trust", value=15),
                    NpcEffectV1(
                        person_id="person-tribe-leader",
                        attitude_delta=20,
                        trust_delta=15,
                        reveal_fact_refs=["fact-cooperation"],
                    ),
                ],
                feedback="解释延缓工程，但提高了协作意愿。",
                fact_refs=["fact-cooperation"],
            ),
            ActionRuleV1(
                action_id="allocate-food",
                label="分配粮食保障",
                effects=[
                    StateEffectV1(variable_id="food", value=-15),
                    StateEffectV1(variable_id="public_support", value=10),
                    StateEffectV1(variable_id="tribal_trust", value=10),
                ],
                feedback="粮食储备下降，但民心与协作基础得到恢复。",
                fact_refs=["fact-public-mobilization", "fact-cooperation"],
            ),
        ],
        event_rules=[
            EventRuleV1(
                event_id="event-heavy-rain",
                title="暴雨将至",
                trigger=[
                    TurnConditionV1(operator="gte", value=3),
                    StateConditionV1(variable_id="flood_risk", operator="gte", value=50),
                ],
                effects=[StateEffectV1(variable_id="flood_risk", value=10)],
                narrative="【教师待审】暴雨使水患再次上升。",
                fact_refs=["fact-flood-method"],
                priority=10,
            ),
            EventRuleV1(
                event_id="event-cooperation",
                title="部族协作形成",
                trigger=[
                    StateConditionV1(variable_id="tribal_trust", operator="gte", value=70),
                    StateConditionV1(variable_id="public_support", operator="gte", value=70),
                ],
                effects=[StateEffectV1(variable_id="labor", value=10)],
                narrative="协作关系转化为可用劳力。",
                fact_refs=["fact-cooperation"],
                priority=20,
            ),
        ],
        ending_rules=[
            EndingRuleV1(
                ending_id="ending-water-controlled",
                title="疏导见效",
                conditions=[
                    TurnConditionV1(operator="gte", value=5),
                    StateConditionV1(variable_id="flood_risk", operator="lte", value=35),
                    StateConditionV1(variable_id="engineering_knowledge", operator="gte", value=60),
                ],
                summary="你以勘察、疏导和协作逐步控制水患。",
                historical_explanation="【教师待审】正式解释由教师团队依据教材与资料替换。",
                major_costs=["粮食与劳力消耗", "前期勘察带来的短期风险"],
                source_ref_ids=["source-dayu-placeholder"],
                fact_refs=fact_refs,
                priority=10,
            ),
            EndingRuleV1(
                ending_id="ending-system-collapse",
                title="动员体系失效",
                match="any",
                conditions=[
                    StateConditionV1(variable_id="flood_risk", operator="gte", value=95),
                    StateConditionV1(variable_id="public_support", operator="lte", value=10),
                    StateConditionV1(variable_id="food", operator="lte", value=5),
                ],
                summary="水患或资源压力突破了行动体系的承受边界。",
                historical_explanation="【教师待审】用于验证失败结局，不承担正式历史结论。",
                source_ref_ids=["source-dayu-placeholder"],
                fact_refs=fact_refs,
                priority=20,
            ),
            EndingRuleV1(
                ending_id="ending-timeout",
                title="汛期未决",
                conditions=[TurnConditionV1(operator="gte", value=6)],
                summary="六回合后仍未触发成功或失败结局。",
                historical_explanation="技术兜底结局。",
                source_ref_ids=["source-dayu-placeholder"],
                priority=1000,
            ),
        ],
        fact_refs=fact_refs,
        source_ref_ids=["source-dayu-placeholder"],
        dossier_template=DossierTemplateV1(
            reflection_questions=[
                "哪一次选择改变了治水方法？",
                "你为降低水患付出了哪些资源和社会代价？",
            ],
            knowledge_node_kinds=["cause", "consequence", "concept"],
        ),
        created_at=_BASE_TIME - timedelta(days=1),
        updated_at=_BASE_TIME,
        sealed_at=_BASE_TIME,
        sealed_by="fixture-builder",
        checksum="0" * 64,
    )
    return _with_checksum(scenario, ScenarioTemplateV1)


def _state_history() -> list[dict[str, float]]:
    return [
        {
            "flood_risk": 70,
            "public_support": 55,
            "food": 70,
            "labor": 70,
            "tribal_trust": 45,
            "engineering_knowledge": 35,
        },
        {
            "flood_risk": 75,
            "public_support": 55,
            "food": 70,
            "labor": 70,
            "tribal_trust": 45,
            "engineering_knowledge": 50,
        },
        {
            "flood_risk": 75,
            "public_support": 65,
            "food": 70,
            "labor": 70,
            "tribal_trust": 60,
            "engineering_knowledge": 50,
        },
        {
            "flood_risk": 60,
            "public_support": 65,
            "food": 70,
            "labor": 58,
            "tribal_trust": 60,
            "engineering_knowledge": 60,
        },
        {
            "flood_risk": 60,
            "public_support": 75,
            "food": 55,
            "labor": 68,
            "tribal_trust": 70,
            "engineering_knowledge": 60,
        },
        {
            "flood_risk": 35,
            "public_support": 75,
            "food": 55,
            "labor": 56,
            "tribal_trust": 70,
            "engineering_knowledge": 70,
        },
    ]


def _build_turns(
    states: list[dict[str, float]],
    scenario: ScenarioTemplateV1,
) -> list[TurnV1]:
    specs = [
        ("survey-terrain", "先勘察地势和河道"),
        ("explain-plan", "向各部族解释疏导计划"),
        ("open-channels", "按勘察结果开挖疏导线"),
        ("allocate-food", "分配粮食，保障参与工程的民众"),
        ("open-channels", "扩大已经见效的疏导工程"),
    ]
    turns: list[TurnV1] = []
    snapshot = initial_rule_snapshot(scenario)
    for index, (action_id, raw_input) in enumerate(specs, start=1):
        result = evaluate_rule_action(scenario, snapshot, action_id, index)
        if result.snapshot.state_dict() != states[index]:
            raise RuntimeError(f"dayu state fixture drifted at turn {index}")
        turns.append(
            TurnV1(
                turn_id=f"turn-dayu-{index:03d}",
                session_id="session-dayu-demo-001",
                client_action_id=f"client-action-dayu-{index:03d}",
                turn_no=index,
                status="applied",
                raw_input=raw_input,
                action_source="fixed",
                classified_action_id=action_id,
                classification_confidence=1,
                state_before=snapshot.state_dict(),
                state_after=result.snapshot.state_dict(),
                state_changes=[
                    StateChangeV1(
                        variable_id=item.variable_id,
                        before=item.before,
                        after=item.after,
                        delta=item.delta,
                    )
                    for item in result.state_changes
                ],
                npc_changes=[
                    NpcChangeV1(
                        person_id=item.person_id,
                        attitude_before=item.attitude_before,
                        attitude_after=item.attitude_after,
                        trust_before=item.trust_before,
                        trust_after=item.trust_after,
                        revealed_fact_refs=list(item.revealed_fact_refs),
                    )
                    for item in result.npc_changes
                ],
                triggered_event_ids=list(result.triggered_event_ids),
                fact_refs=list(result.fact_refs),
                narrative=render_rule_narrative(scenario, result),
                narrative_source="rules",
                ruleset_hash=str(scenario.checksum),
                created_at=_BASE_TIME + timedelta(minutes=index * 5),
            )
        )
        snapshot = result.snapshot
    return turns


def _build_dossier(
    states: list[dict[str, float]],
    course_checksum: str,
    scenario_checksum: str,
) -> DossierV1:
    dossier = DossierV1(
        dossier_id="dossier-dayu-demo-001",
        session_id="session-dayu-demo-001",
        user_id="student-demo",
        course_id="C-early-civilization",
        lesson_id="dayu-flood-control",
        scenario_id="scenario-dayu-flood-control",
        course_content_version=1,
        scenario_version=1,
        course_checksum=course_checksum,
        scenario_checksum=scenario_checksum,
        status="final",
        title="《大禹治水：疏堵与协作》卷宗",
        ending_id="ending-water-controlled",
        strategy_summary="先勘察，再争取协作与资源保障，最后扩大疏导工程。",
        key_choices=[
            DossierChoiceV1(
                turn_id="turn-dayu-001",
                turn_no=1,
                action_id="survey-terrain",
                choice="先勘察地势和河道",
                consequence="承受短期水患上升，换取工程认知。",
            ),
            DossierChoiceV1(
                turn_id="turn-dayu-003",
                turn_no=3,
                action_id="open-channels",
                choice="按勘察结果开挖疏导线",
                consequence="降低水患并消耗劳力，同时遭遇暴雨事件。",
            ),
            DossierChoiceV1(
                turn_id="turn-dayu-004",
                turn_no=4,
                action_id="allocate-food",
                choice="分配粮食，保障参与工程的民众",
                consequence="粮食下降，民心和协作提升并补充劳力。",
            ),
        ],
        state_trajectory=[
            StateSnapshotV1(turn_no=index, state=state)
            for index, state in enumerate(states)
        ],
        major_costs=["粮食消耗 15", "劳力净消耗 14", "前期水患短暂上升"],
        historical_explanation="【教师待审】本段只验证卷宗结构；正式历史解释必须由教师审校替换。",
        knowledge_nodes=[
            KnowledgeNodeV1(
                node_id="node-method-choice",
                label="工程方法选择",
                kind="cause",
                summary="勘察提高工程认知，使疏导行动可用。",
                source_ref_ids=["source-dayu-placeholder"],
            ),
            KnowledgeNodeV1(
                node_id="node-social-cost",
                label="公共动员代价",
                kind="consequence",
                summary="工程推进消耗粮食与劳力，需要维持民心和协作。",
                source_ref_ids=["source-dayu-placeholder"],
            ),
        ],
        knowledge_edges=[
            KnowledgeEdgeV1(
                edge_id="edge-method-to-cost",
                source_node_id="node-method-choice",
                target_node_id="node-social-cost",
                relation="伴随代价",
                explanation="工程方法的落实需要持续的公共动员和资源投入。",
                source_ref_ids=["source-dayu-placeholder"],
            )
        ],
        follow_up_questions=["如果只追求快速降低水患，哪些变量可能先失控？"],
        reflection_notes=["技术样板反思占位，后续由学生或教师填写。"],
        fact_refs=["fact-flood-method", "fact-public-mobilization", "fact-cooperation"],
        source_ref_ids=["source-dayu-placeholder"],
        generated_at=_BASE_TIME + timedelta(minutes=25),
        checksum="0" * 64,
    )
    return _with_checksum(dossier, DossierV1)


def _build_shangyang_course(scenario_checksum: str) -> CoursePackageV1:
    marked = _shangyang_text
    package = CoursePackageV1(
        package_id="pkg-shangyang-institutional-reform",
        course_id="C-warring-states-reform",
        lesson_id="shangyang-institutional-reform",
        content_version=1,
        status="sealed",
        title=marked("商鞅变法制度改革样例"),
        unit=marked("战国时期的制度变革"),
        era=marked("战国时期"),
        body=[
            marked(
                "本段只验证制度改革关卡的数据结构与规则链路；"
                "史实选取、表述与教学结论均须由教师审定。"
            ),
            marked(
                "状态变量、数值和分支均为技术联调设定，"
                "不代表对商鞅变法历史影响的教学评价。"
            ),
        ],
        abstract=marked(
            "用于验证节点式制度改革场景的课程内容占位，不提供正式历史结论。"
        ),
        course_title=marked("制度变革课程技术样例"),
        section=marked("课程内容包"),
        teaching_objectives=[
            marked("验证学习者可比较制度方案在规则模型中的不同状态后果。"),
            marked("验证学习者可依据占位事实引用说明选择与代价的关联。"),
        ],
        keywords=[
            KeywordV1(
                keyword_id="keyword-reform-rules",
                word=marked("法令规则"),
                gloss=marked(
                    "仅指本技术场景中用于驱动 law_clarity 状态的规则占位。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
            ),
            KeywordV1(
                keyword_id="keyword-local-administration",
                word=marked("地方行政"),
                gloss=marked(
                    "仅指本技术场景中用于驱动 administrative_capacity 状态的规则占位。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
            ),
        ],
        people=[
            PersonV1(
                person_id="person-shangyang",
                name=marked("商鞅"),
                role=marked("制度改革提议者角色占位"),
                summary=marked("人物定位与史实表述须由教师审定。"),
                persona=marked("仅用于测试制度方案说明与规则反馈。"),
                boundaries=[
                    marked("不得将技术场景台词当作史料原话或正式教学结论。")
                ],
                fact_refs=[
                    "fact-rule-publication",
                    "fact-merit-incentives",
                    "fact-local-administration",
                ],
                source_ref_ids=["source-shangyang-placeholder"],
            ),
            PersonV1(
                person_id="person-qin-ruler",
                name=marked("秦国君主角色"),
                role=marked("改革授权与政策取舍角色占位"),
                summary=marked("具体人物、称谓与年代关系须由教师审定。"),
                persona=marked("仅用于测试授权信任条件。"),
                boundaries=[
                    marked("不得补写未经教师审定的人物动机或对话。")
                ],
                fact_refs=["fact-rule-publication", "fact-local-administration"],
                source_ref_ids=["source-shangyang-placeholder"],
            ),
            PersonV1(
                person_id="person-old-nobility",
                name=marked("旧贵族代表角色"),
                role=marked("制度阻力反馈角色占位"),
                summary=marked("群体构成与立场均为规则测试抽象。"),
                persona=marked("仅用于测试态度、信任与阻力变量。"),
                boundaries=[
                    marked("不得将抽象角色表述为单一历史群体的完整立场。")
                ],
                fact_refs=["fact-merit-incentives"],
                source_ref_ids=["source-shangyang-placeholder"],
            ),
            PersonV1(
                person_id="person-local-official",
                name=marked("地方执行者角色"),
                role=marked("制度执行能力反馈角色占位"),
                summary=marked("职位名称和行政职责须由教师审定。"),
                persona=marked("仅用于测试执行条件和 NPC 效果。"),
                boundaries=[
                    marked("不得据此推导真实制度运行细节。")
                ],
                fact_refs=["fact-rule-publication", "fact-local-administration"],
                source_ref_ids=["source-shangyang-placeholder"],
            ),
        ],
        map_points=[
            MapPointV1(
                point_id="map-qin-reform-placeholder",
                label=marked("秦国制度改革地图点"),
                region=marked("空间范围待教师审定"),
                note=marked(
                    "仅用于地图与关卡引用联调，不表示精确历史边界或坐标。"
                ),
                kind="teaching-placeholder",
            )
        ],
        facts=[
            FactV1(
                fact_id="fact-rule-publication",
                statement=marked(
                    "法令公开与执行一致性的具体史实、范围及评价等待教师审校。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
                certainty="interpretation",
                teacher_note=marked("正式版本须补充教材依据并校正表述。"),
            ),
            FactV1(
                fact_id="fact-merit-incentives",
                statement=marked(
                    "军功与激励制度的具体内容、影响及争议等待教师审校。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
                certainty="interpretation",
                teacher_note=marked("本事实仅承担规则引用占位。"),
            ),
            FactV1(
                fact_id="fact-local-administration",
                statement=marked(
                    "地方行政制度变化的时间、范围及历史意义等待教师审校。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
                certainty="interpretation",
                teacher_note=marked("本事实仅承担节点与状态规则引用占位。"),
            ),
        ],
        source_refs=[
            SourceRefV1(
                source_id="source-shangyang-placeholder",
                title=marked("商鞅变法资料来源占位"),
                kind="other",
                citation_note=marked(
                    "正式发布前须由教师替换为教材、课程标准及经审校资料。"
                ),
                reliability="pending",
            )
        ],
        qa_points=[
            marked("哪些规则状态变化来自玩家选择，哪些来自事件触发？"),
            marked("不同优先级结局在技术模型中如何避免同时生效？"),
        ],
        level_goals=[
            marked(
                "在六回合技术上限内完成节点流转，并观察制度清晰度、"
                "执行能力、支持度与阻力的规则变化。"
            )
        ],
        scenario_refs=[
            ScenarioRefV1(
                scenario_id="scenario-shangyang-institutional-reform",
                scenario_version=1,
                checksum=scenario_checksum,
                primary=True,
            )
        ],
        teacher_notes=marked(
            "本包不承担教师职责；所有史实、人物、问题和结论必须经教师审核后方可教学使用。"
        ),
        created_at=_BASE_TIME - timedelta(days=1),
        updated_at=_BASE_TIME,
        sealed_at=_BASE_TIME,
        sealed_by="fixture-builder",
        checksum="0" * 64,
    )
    return _with_checksum(package, CoursePackageV1)


def _build_shangyang_scenario() -> ScenarioTemplateV1:
    marked = _shangyang_text
    fact_refs = [
        "fact-rule-publication",
        "fact-merit-incentives",
        "fact-local-administration",
    ]
    scenario = ScenarioTemplateV1(
        scenario_id="scenario-shangyang-institutional-reform",
        scenario_version=1,
        status="sealed",
        course_id="C-warring-states-reform",
        lesson_id="shangyang-institutional-reform",
        title=marked("商鞅变法节点式制度改革关卡"),
        scenario_type="institutional_reform",
        student_role=marked("制度方案记录与规则验证者，不承担历史裁判或教师职责"),
        objective=marked(
            "沿节点比较制度方案的规则后果，并在六回合上限内验证多结局判定。"
        ),
        opening=marked(
            "制度方案等待讨论；人物立场、史实叙述和数值均为待教师审定的技术占位。"
        ),
        max_turns=6,
        variables=[
            StateVariableV1(
                variable_id="law_clarity",
                label=marked("制度清晰度"),
                description=marked("仅供规则引擎测试的数值。"),
                initial=30,
            ),
            StateVariableV1(
                variable_id="reform_support",
                label=marked("改革支持度"),
                description=marked("仅供规则引擎测试的数值。"),
                initial=50,
            ),
            StateVariableV1(
                variable_id="noble_resistance",
                label=marked("旧贵族阻力"),
                description=marked("仅供规则引擎测试的抽象数值。"),
                initial=45,
            ),
            StateVariableV1(
                variable_id="administrative_capacity",
                label=marked("行政执行能力"),
                description=marked("仅供规则引擎测试的数值。"),
                initial=35,
            ),
            StateVariableV1(
                variable_id="public_order",
                label=marked("社会秩序"),
                description=marked("仅供规则引擎测试的抽象数值。"),
                initial=60,
            ),
        ],
        npcs=[
            NpcSpecV1(
                person_id="person-shangyang",
                display_name=marked("商鞅"),
                role=marked("制度改革提议者角色占位"),
                persona=marked("仅用于规则反馈，不作为历史人物还原。"),
                boundaries=[
                    marked("台词和立场不得作为史料或正式教学结论。")
                ],
                initial_attitude=20,
                initial_trust=25,
                fact_refs=fact_refs,
            ),
            NpcSpecV1(
                person_id="person-qin-ruler",
                display_name=marked("秦国君主角色"),
                role=marked("改革授权角色占位"),
                persona=marked("仅用于测试授权信任条件。"),
                boundaries=[
                    marked("具体身份、动机和对话等待教师审定。")
                ],
                initial_attitude=15,
                initial_trust=20,
                fact_refs=["fact-rule-publication", "fact-local-administration"],
            ),
            NpcSpecV1(
                person_id="person-old-nobility",
                display_name=marked("旧贵族代表角色"),
                role=marked("制度阻力角色占位"),
                persona=marked("仅用于测试态度与信任变化。"),
                boundaries=[
                    marked("抽象角色不代表真实群体的完整立场。")
                ],
                initial_attitude=-10,
                initial_trust=-15,
                fact_refs=["fact-merit-incentives"],
            ),
            NpcSpecV1(
                person_id="person-local-official",
                display_name=marked("地方执行者角色"),
                role=marked("制度执行角色占位"),
                persona=marked("仅用于测试行政执行条件。"),
                boundaries=[
                    marked("行政职责与制度细节等待教师审定。")
                ],
                initial_attitude=0,
                initial_trust=10,
                fact_refs=["fact-rule-publication", "fact-local-administration"],
            ),
        ],
        action_rules=[
            ActionRuleV1(
                action_id="consult-court",
                label=marked("征询改革意见"),
                description=marked("验证 NPC 信任变化及事实揭示效果。"),
                effects=[
                    StateEffectV1(variable_id="reform_support", value=5),
                    NpcEffectV1(
                        person_id="person-qin-ruler",
                        attitude_delta=10,
                        trust_delta=10,
                        reveal_fact_refs=["fact-rule-publication"],
                    ),
                ],
                feedback=marked("规则模型提高支持度和授权角色信任。"),
                fact_refs=["fact-rule-publication"],
                next_node_id="node-policy-design",
            ),
            ActionRuleV1(
                action_id="announce-principles",
                label=marked("公布制度原则"),
                description=marked("验证 state set 效果及阻力反馈。"),
                effects=[
                    StateEffectV1(
                        variable_id="law_clarity",
                        operation="set",
                        value=55,
                    ),
                    StateEffectV1(variable_id="noble_resistance", value=10),
                    NpcEffectV1(
                        person_id="person-old-nobility",
                        attitude_delta=-10,
                        trust_delta=-5,
                        reveal_fact_refs=["fact-merit-incentives"],
                    ),
                ],
                feedback=marked("规则模型将制度清晰度设为固定值，并提高阻力。"),
                fact_refs=["fact-rule-publication", "fact-merit-incentives"],
                next_node_id="node-policy-design",
            ),
            ActionRuleV1(
                action_id="standardize-rules",
                label=marked("统一规则文本"),
                description=marked("验证 NPC trust 条件与 state set 效果。"),
                available_when=[
                    NpcConditionV1(
                        person_id="person-local-official",
                        field="trust",
                        operator="gte",
                        value=10,
                    )
                ],
                effects=[
                    StateEffectV1(
                        variable_id="law_clarity",
                        operation="set",
                        value=75,
                    ),
                    StateEffectV1(variable_id="administrative_capacity", value=10),
                    NpcEffectV1(
                        person_id="person-local-official",
                        trust_delta=10,
                        reveal_fact_refs=["fact-local-administration"],
                    ),
                ],
                feedback=marked("规则模型提高制度清晰度、执行能力与执行者信任。"),
                fact_refs=["fact-rule-publication", "fact-local-administration"],
                next_node_id="node-local-implementation",
            ),
            ActionRuleV1(
                action_id="prepare-local-offices",
                label=marked("准备地方执行节点"),
                description=marked("验证行政能力与 NPC 效果。"),
                effects=[
                    StateEffectV1(variable_id="administrative_capacity", value=20),
                    StateEffectV1(variable_id="reform_support", value=-5),
                    NpcEffectV1(
                        person_id="person-local-official",
                        attitude_delta=10,
                        trust_delta=15,
                        reveal_fact_refs=["fact-local-administration"],
                    ),
                ],
                feedback=marked("规则模型以短期支持度代价换取执行能力。"),
                fact_refs=["fact-local-administration"],
                next_node_id="node-local-implementation",
            ),
            ActionRuleV1(
                action_id="apply-merit-system",
                label=marked("应用激励规则"),
                description=marked("验证制度清晰度条件、支持度与阻力变化。"),
                available_when=[
                    StateConditionV1(
                        variable_id="law_clarity",
                        operator="gte",
                        value=50,
                    )
                ],
                effects=[
                    StateEffectV1(variable_id="reform_support", value=10),
                    StateEffectV1(variable_id="noble_resistance", value=15),
                    NpcEffectV1(
                        person_id="person-old-nobility",
                        attitude_delta=-20,
                        trust_delta=-10,
                        reveal_fact_refs=["fact-merit-incentives"],
                    ),
                ],
                feedback=marked("规则模型同时提高支持度与旧贵族阻力。"),
                fact_refs=["fact-merit-incentives"],
                next_node_id="node-policy-evaluation",
            ),
            ActionRuleV1(
                action_id="phase-rollout",
                label=marked("分阶段执行"),
                description=marked("验证较缓和的执行路径。"),
                effects=[
                    StateEffectV1(variable_id="administrative_capacity", value=10),
                    StateEffectV1(variable_id="public_order", value=10),
                    StateEffectV1(variable_id="noble_resistance", value=-5),
                ],
                feedback=marked("规则模型提高执行能力和秩序，并降低部分阻力。"),
                fact_refs=["fact-local-administration"],
                next_node_id="node-policy-evaluation",
            ),
            ActionRuleV1(
                action_id="consolidate-rules",
                label=marked("确认制度方案"),
                description=marked("验证 NPC 条件与成功终点节点。"),
                available_when=[
                    NpcConditionV1(
                        person_id="person-local-official",
                        field="trust",
                        operator="gte",
                        value=10,
                    )
                ],
                effects=[
                    StateEffectV1(
                        variable_id="law_clarity",
                        operation="set",
                        value=85,
                    ),
                    StateEffectV1(variable_id="administrative_capacity", value=10),
                ],
                feedback=marked("规则模型进入制度确认终点，历史评价仍待教师审定。"),
                fact_refs=["fact-rule-publication", "fact-local-administration"],
                next_node_id="node-reform-recorded",
            ),
            ActionRuleV1(
                action_id="pause-and-review",
                label=marked("暂缓并复核"),
                description=marked("验证复核终点节点与固定状态值。"),
                effects=[
                    StateEffectV1(
                        variable_id="law_clarity",
                        operation="set",
                        value=45,
                    ),
                    StateEffectV1(variable_id="reform_support", value=5),
                    StateEffectV1(variable_id="noble_resistance", value=-10),
                ],
                feedback=marked("规则模型进入待复核终点，不生成教学结论。"),
                fact_refs=["fact-rule-publication"],
                next_node_id="node-review-pending",
            ),
            ActionRuleV1(
                action_id="force-rapid-rollout",
                label=marked("强行快速推行"),
                description=marked("验证阻力超限结局与规则事件叠加。"),
                effects=[
                    StateEffectV1(variable_id="noble_resistance", value=40),
                    StateEffectV1(variable_id="public_order", value=-20),
                    NpcEffectV1(
                        person_id="person-old-nobility",
                        attitude_delta=-30,
                        trust_delta=-15,
                        reveal_fact_refs=["fact-merit-incentives"],
                    ),
                ],
                feedback=marked("规则模型将阻力推至失败阈值，不输出历史归因。"),
                fact_refs=["fact-merit-incentives"],
                next_node_id="node-policy-evaluation",
            ),
            ActionRuleV1(
                action_id="continue-deliberation",
                label=marked("继续评估"),
                description=marked("验证评估节点自循环与回合上限兜底。"),
                effects=[],
                feedback=marked("规则模型保留当前状态并进入下一回合评估。"),
                fact_refs=["fact-rule-publication"],
                next_node_id="node-policy-evaluation",
            ),
        ],
        event_rules=[
            EventRuleV1(
                event_id="event-implementation-friction",
                title=marked("执行阻力事件"),
                match="any",
                trigger=[
                    StateConditionV1(
                        variable_id="noble_resistance",
                        operator="gte",
                        value=65,
                    ),
                    NpcConditionV1(
                        person_id="person-old-nobility",
                        field="attitude",
                        operator="lte",
                        value=-30,
                    ),
                ],
                effects=[
                    StateEffectV1(variable_id="public_order", value=-15),
                    NpcEffectV1(
                        person_id="person-local-official",
                        trust_delta=-5,
                    ),
                ],
                narrative=marked(
                    "任一阻力条件满足即触发技术事件；叙述与历史解释等待教师审定。"
                ),
                fact_refs=["fact-merit-incentives", "fact-local-administration"],
                priority=10,
            )
        ],
        ending_rules=[
            EndingRuleV1(
                ending_id="ending-reform-recorded",
                title=marked("制度方案形成"),
                conditions=[
                    TurnConditionV1(operator="gte", value=3),
                    StateConditionV1(
                        variable_id="law_clarity",
                        operator="gte",
                        value=75,
                    ),
                    StateConditionV1(
                        variable_id="administrative_capacity",
                        operator="gte",
                        value=55,
                    ),
                ],
                summary=marked("规则层记录制度方案形成，不代表历史评价或教学结论。"),
                historical_explanation=marked(
                    "正式历史解释须由教师依据教材与审校资料撰写。"
                ),
                major_costs=[
                    marked("数值代价仅用于规则验证。"),
                    marked("人物态度变化不代表真实历史群体立场。"),
                ],
                source_ref_ids=["source-shangyang-placeholder"],
                fact_refs=fact_refs,
                priority=10,
            ),
            EndingRuleV1(
                ending_id="ending-reform-backlash",
                title=marked("改革阻力超限"),
                match="any",
                conditions=[
                    StateConditionV1(
                        variable_id="noble_resistance",
                        operator="gte",
                        value=85,
                    ),
                    StateConditionV1(
                        variable_id="public_order",
                        operator="lte",
                        value=30,
                    ),
                    NpcConditionV1(
                        person_id="person-old-nobility",
                        field="attitude",
                        operator="lte",
                        value=-60,
                    ),
                ],
                summary=marked("任一失败阈值满足时结束规则流程，不承担历史归因。"),
                historical_explanation=marked(
                    "失败阈值和解释均为技术占位，须由教师审核。"
                ),
                major_costs=[marked("仅记录规则状态越界，不作教学评价。")],
                source_ref_ids=["source-shangyang-placeholder"],
                fact_refs=fact_refs,
                priority=20,
            ),
            EndingRuleV1(
                ending_id="ending-review-pending",
                title=marked("方案待复核"),
                conditions=[
                    TurnConditionV1(operator="gte", value=3),
                    StateConditionV1(
                        variable_id="law_clarity",
                        operator="lte",
                        value=50,
                    ),
                ],
                summary=marked("规则流程停在待复核节点，不输出正式结论。"),
                historical_explanation=marked(
                    "后续教学处理与历史解释由教师决定。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
                fact_refs=["fact-rule-publication"],
                priority=30,
            ),
            EndingRuleV1(
                ending_id="ending-max-turns-fallback",
                title=marked("回合上限兜底"),
                conditions=[TurnConditionV1(operator="gte", value=6)],
                summary=marked("达到 max_turns 后结束技术流程，不输出教学结论。"),
                historical_explanation=marked(
                    "该结局仅为规则引擎兜底，与历史判断无关。"
                ),
                source_ref_ids=["source-shangyang-placeholder"],
                fact_refs=[],
                priority=1000,
            ),
        ],
        start_node_id="node-court-deliberation",
        nodes=[
            ScenarioNodeV1(
                node_id="node-court-deliberation",
                title=marked("方案讨论节点"),
                narration=marked("仅验证起始节点和分支动作。"),
                action_ids=["consult-court", "announce-principles"],
            ),
            ScenarioNodeV1(
                node_id="node-policy-design",
                title=marked("制度设计节点"),
                narration=marked("仅验证 NPC 条件和 state set 效果。"),
                action_ids=["standardize-rules", "prepare-local-offices"],
            ),
            ScenarioNodeV1(
                node_id="node-local-implementation",
                title=marked("地方执行节点"),
                narration=marked("仅验证不同执行路径的状态变化。"),
                action_ids=["apply-merit-system", "phase-rollout"],
            ),
            ScenarioNodeV1(
                node_id="node-policy-evaluation",
                title=marked("方案评估节点"),
                narration=marked("仅验证多个终点节点的流转。"),
                action_ids=[
                    "consolidate-rules",
                    "pause-and-review",
                    "force-rapid-rollout",
                    "continue-deliberation",
                ],
            ),
            ScenarioNodeV1(
                node_id="node-reform-recorded",
                title=marked("制度方案形成终点"),
                narration=marked("终点文本不构成历史结论。"),
                ending_id="ending-reform-recorded",
            ),
            ScenarioNodeV1(
                node_id="node-review-pending",
                title=marked("方案待复核终点"),
                narration=marked("终点文本等待教师审核。"),
                ending_id="ending-review-pending",
            ),
        ],
        fact_refs=fact_refs,
        source_ref_ids=["source-shangyang-placeholder"],
        dossier_template=DossierTemplateV1(
            title_template=marked("《{scenario_title}技术卷宗》"),
            reflection_questions=[
                marked("哪条规则使用了固定值设置，产生了什么模型后果？"),
                marked("NPC 条件与事件条件如何改变可用动作和状态？"),
            ],
            knowledge_node_kinds=["cause", "consequence", "concept"],
        ),
        created_at=_BASE_TIME - timedelta(days=1),
        updated_at=_BASE_TIME,
        sealed_at=_BASE_TIME,
        sealed_by="fixture-builder",
        checksum="0" * 64,
    )
    return _with_checksum(scenario, ScenarioTemplateV1)


def _shangyang_text(text: str) -> str:
    return f"{_SHANGYANG_NOTICE}{text}"


def _with_checksum(document, model):
    data = document.model_dump(mode="json")
    data["checksum"] = calculate_contract_checksum(document)
    return model.model_validate(data)
