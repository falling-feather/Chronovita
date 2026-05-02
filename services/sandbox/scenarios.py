from __future__ import annotations

from .models import DagEdge, DagNode, Scenario, StateVar, StateVarKind
from .models import Condition, Effect


_dayu = Scenario(
    scenario_id="xia-dayu-zhishui",
    title="大禹治水",
    period="夏 · 约公元前 2070 年",
    summary="禹承父业，需在「堵」与「疏」之间抉择，平衡民心与水患，最终划定九州。",
    state_vars=[
        StateVar(key="strategy", label="治水策略", kind=StateVarKind.SCALE, bits=2, initial=0,
                 description="0=未定 1=承父之堵 2=改弦疏导 3=堵疏并举"),
        StateVar(key="morale", label="民心", kind=StateVarKind.SCALE, bits=3, initial=4,
                 description="0~7，初始 4"),
        StateVar(key="flood", label="河患", kind=StateVarKind.SCALE, bits=3, initial=6,
                 description="0~7，初始 6"),
        StateVar(key="nine_zhou", label="九州划定", kind=StateVarKind.BOOL, bits=1, initial=0),
    ],
    start_node="n_call",
    nodes=[
        DagNode(node_id="n_call", title="受命继业",
                narrative="父鲧治水九年不成，被殛于羽山。舜命你承继治水大任，朝野观望。"),
        DagNode(node_id="n_inherit", title="承父之堵",
                narrative="你沿用父法，筑堤围堵。短期见效，但水势愈积愈高，民众疲于劳役。"),
        DagNode(node_id="n_reform", title="改弦疏导",
                narrative="你召集水工，主张顺水之性，开渠引流。族老质疑，你需以身作则。"),
        DagNode(node_id="n_combine", title="堵疏并举",
                narrative="你折中两策，重要城邑筑堤，下游开渠分洪。工程浩大，需多调民力。"),
        DagNode(node_id="n_collapse", title="溃堤之变",
                narrative="积水冲垮堤防，下游良田尽没，民心大丧。",
                is_terminal=True),
        DagNode(node_id="n_field_survey", title="行九州之野",
                narrative="你亲历山川，三过家门而不入，划定九州，定贡赋。民众感佩。"),
        DagNode(node_id="n_pacify", title="水患渐平",
                narrative="十三载寒暑，疏通九河，水患渐平。诸侯朝觐。"),
        DagNode(node_id="n_dynasty", title="开夏之基",
                narrative="禅让的传统在你这里停歇——子启继位。中国第一个王朝由此开启。",
                is_terminal=True),
    ],
    edges=[
        DagEdge(edge_id="e_call_inherit", from_node="n_call", to_node="n_inherit",
                label="沿用父法 · 筑堤围堵",
                effects=[Effect(var="strategy", op="set", value=1),
                         Effect(var="morale", op="dec", value=1)],
                fallback_narrative="你选择延续父亲的方法。"),
        DagEdge(edge_id="e_call_reform", from_node="n_call", to_node="n_reform",
                label="改弦更张 · 顺水疏导",
                effects=[Effect(var="strategy", op="set", value=2)],
                fallback_narrative="你决心另辟新路。"),
        DagEdge(edge_id="e_call_combine", from_node="n_call", to_node="n_combine",
                label="折中之策 · 堵疏并举",
                effects=[Effect(var="strategy", op="set", value=3),
                         Effect(var="morale", op="dec", value=2)],
                fallback_narrative="你采纳折中之议。"),

        DagEdge(edge_id="e_inherit_collapse", from_node="n_inherit", to_node="n_collapse",
                label="苦撑数年 · 终至溃堤",
                conditions=[Condition(var="flood", op="ge", value=5)],
                effects=[Effect(var="flood", op="set", value=7),
                         Effect(var="morale", op="set", value=0)],
                fallback_narrative="水患积重难返。"),

        DagEdge(edge_id="e_reform_survey", from_node="n_reform", to_node="n_field_survey",
                label="率众踏勘 · 三过家门",
                effects=[Effect(var="flood", op="dec", value=3),
                         Effect(var="morale", op="inc", value=2)],
                fallback_narrative="你以身作则，踏遍九州。"),

        DagEdge(edge_id="e_combine_survey", from_node="n_combine", to_node="n_field_survey",
                label="督工巡野 · 安抚民众",
                conditions=[Condition(var="morale", op="ge", value=2)],
                effects=[Effect(var="flood", op="dec", value=2),
                         Effect(var="morale", op="inc", value=1)],
                fallback_narrative="你两手抓，民心渐复。"),
        DagEdge(edge_id="e_combine_collapse", from_node="n_combine", to_node="n_collapse",
                label="民力枯竭 · 工程崩坏",
                conditions=[Condition(var="morale", op="lt", value=2)],
                effects=[Effect(var="flood", op="set", value=7),
                         Effect(var="morale", op="set", value=0)],
                fallback_narrative="民心既失，工程难以维系。"),

        DagEdge(edge_id="e_survey_pacify", from_node="n_field_survey", to_node="n_pacify",
                label="划定九州 · 定贡赋",
                effects=[Effect(var="nine_zhou", op="set", value=1),
                         Effect(var="morale", op="inc", value=2),
                         Effect(var="flood", op="dec", value=2)],
                fallback_narrative="九州既定，水患渐平。"),

        DagEdge(edge_id="e_pacify_dynasty", from_node="n_pacify", to_node="n_dynasty",
                label="禅让停歇 · 子启继位",
                conditions=[Condition(var="nine_zhou", op="eq", value=1),
                            Condition(var="morale", op="ge", value=5)],
                effects=[],
                fallback_narrative="时移势易，王朝由此开启。"),
    ],
)


_REGISTRY: dict[str, Scenario] = {_dayu.scenario_id: _dayu}


def list_scenarios() -> list[Scenario]:
    return list(_REGISTRY.values())


def get_scenario(scenario_id: str) -> Scenario | None:
    return _REGISTRY.get(scenario_id)


def register_scenario(scenario: Scenario) -> None:
    _REGISTRY[scenario.scenario_id] = scenario
