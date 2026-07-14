from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    NpcEffectV1,
    NpcSpecV1,
    NpcStateV1,
    NarrativeMessageV1,
    ObservedEntityV1,
    PersonV1,
    RuntimeBundleV1,
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


def build_dayu_bundle() -> RuntimeBundleV1:
    scenario = _build_scenario()
    course = _build_course(str(scenario.checksum))
    states = _state_history()
    turns = _build_turns(states)
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


def example_documents() -> dict[str, object]:
    bundle = build_dayu_bundle()
    return {
        "dayu-course-package.json": bundle.course,
        "dayu-scenario-template.json": bundle.scenario,
        "dayu-game-session.json": bundle.session,
        "dayu-dossier.json": bundle.dossier,
        "dayu-runtime-bundle.json": bundle,
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


def _build_turns(states: list[dict[str, float]]) -> list[TurnV1]:
    specs = [
        ("survey-terrain", "先勘察地势和河道", [], ["fact-flood-method"]),
        ("explain-plan", "向各部族解释疏导计划", [], ["fact-cooperation"]),
        (
            "open-channels",
            "按勘察结果开挖疏导线",
            ["event-heavy-rain"],
            ["fact-flood-method", "fact-public-mobilization"],
        ),
        (
            "allocate-food",
            "分配粮食，保障参与工程的民众",
            ["event-cooperation"],
            ["fact-public-mobilization", "fact-cooperation"],
        ),
        (
            "open-channels",
            "扩大已经见效的疏导工程",
            [],
            ["fact-flood-method", "fact-public-mobilization"],
        ),
    ]
    turns: list[TurnV1] = []
    for index, (action_id, raw_input, event_ids, fact_refs) in enumerate(specs, start=1):
        before = states[index - 1]
        after = states[index]
        state_changes = [
            StateChangeV1(
                variable_id=variable_id,
                before=value,
                after=after[variable_id],
                delta=after[variable_id] - value,
            )
            for variable_id, value in before.items()
            if after[variable_id] != value
        ]
        npc_changes = []
        if index == 2:
            npc_changes.append(
                NpcChangeV1(
                    person_id="person-tribe-leader",
                    attitude_before=0,
                    attitude_after=20,
                    trust_before=0,
                    trust_after=15,
                    revealed_fact_refs=["fact-cooperation"],
                )
            )
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
                state_before=before,
                state_after=after,
                state_changes=state_changes,
                npc_changes=npc_changes,
                triggered_event_ids=event_ids,
                fact_refs=fact_refs,
                narrative="【技术样板】规则结果已生成；正式叙事由受约束的叙事层提供。",
                narrative_source="rules",
                ruleset_hash="dayu-rules-v1-demo",
                created_at=_BASE_TIME + timedelta(minutes=index * 5),
            )
        )
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


def _with_checksum(document, model):
    data = document.model_dump(mode="json")
    data["checksum"] = calculate_contract_checksum(document)
    return model.model_validate(data)
