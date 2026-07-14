from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, TYPE_CHECKING

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from services.contracts.rules_v1 import (
    RuleActionUnavailable,
    RuleEvaluationError,
    UnknownRuleAction,
    available_rule_action_ids,
    evaluate_rule_action,
    initial_rule_snapshot,
    select_rule_ending_id,
)

if TYPE_CHECKING:
    from services.content import LessonContentPackage


ContractId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PlayerInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=400),
]
Checksum = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ArtifactStatus = Literal["draft", "sealed"]
ComparisonOperator = Literal["lt", "lte", "eq", "gte", "gt"]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class LegacyMaterialSnapshotV1(ContractModel):
    kind: Literal["saga", "sandbox"]
    title: str = ""
    objective: str = ""
    notes: str = ""
    assets: list[str] = Field(default_factory=list)


class CompatibilitySourceV1(ContractModel):
    kind: Literal[
        "native-v1",
        "lesson-content-package",
        "saga-template",
        "sandbox-scenario",
    ] = "native-v1"
    source_id: str = ""
    source_version: str = ""
    source_checksum: Checksum | None = None
    notes: str = ""
    unresolved_refs: list[str] = Field(default_factory=list)
    legacy_materials: list[LegacyMaterialSnapshotV1] = Field(default_factory=list)
    legacy_id_map: dict[str, ContractId] = Field(default_factory=dict)


class SourceRefV1(ContractModel):
    source_id: ContractId
    title: NonEmptyText
    kind: Literal[
        "curriculum",
        "textbook",
        "primary_source",
        "research",
        "museum",
        "other",
    ] = "other"
    publisher: str = ""
    url_or_path: str = ""
    citation_note: str = ""
    reliability: Literal["pending", "reviewed", "disputed"] = "pending"


class FactV1(ContractModel):
    fact_id: ContractId
    statement: NonEmptyText
    source_ref_ids: list[ContractId] = Field(default_factory=list)
    certainty: Literal["consensus", "interpretation", "legend", "disputed"] = "consensus"
    teacher_note: str = ""


class KeywordV1(ContractModel):
    keyword_id: ContractId
    word: NonEmptyText
    pinyin: str = ""
    gloss: str = ""
    source_ref_ids: list[ContractId] = Field(default_factory=list)


class PersonV1(ContractModel):
    person_id: ContractId
    name: NonEmptyText
    role: str = ""
    summary: str = ""
    persona: str = ""
    boundaries: list[str] = Field(default_factory=list)
    fact_refs: list[ContractId] = Field(default_factory=list)
    source_ref_ids: list[ContractId] = Field(default_factory=list)


class MapPointV1(ContractModel):
    point_id: ContractId
    label: NonEmptyText
    region: str = ""
    lat: float | None = None
    lng: float | None = None
    note: str = ""
    kind: str = "site"


class SeedCanvasNodeV1(ContractModel):
    node_id: ContractId
    label: NonEmptyText
    note: str = ""


class ScenarioRefV1(ContractModel):
    scenario_id: ContractId
    scenario_version: int = Field(ge=0)
    checksum: Checksum | None = None
    primary: bool = False


class CoursePackageV1(ContractModel):
    schema_version: Literal["course-package/v1"] = "course-package/v1"
    package_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    content_version: int = Field(default=0, ge=0)
    status: ArtifactStatus = "draft"

    title: NonEmptyText
    unit: NonEmptyText
    era: NonEmptyText
    body: list[NonEmptyText] = Field(default_factory=list)
    abstract: str = ""
    course_title: str = ""
    era_id: str = "content"
    section: str = "内容包"
    lesson_no: str = ""
    duration: str = ""
    teaching_objectives: list[NonEmptyText] = Field(default_factory=list)

    keywords: list[KeywordV1] = Field(default_factory=list)
    people: list[PersonV1] = Field(default_factory=list)
    map_points: list[MapPointV1] = Field(default_factory=list)
    facts: list[FactV1] = Field(default_factory=list)
    source_refs: list[SourceRefV1] = Field(default_factory=list)
    qa_points: list[str] = Field(default_factory=list)
    level_goals: list[str] = Field(default_factory=list)
    scenario_refs: list[ScenarioRefV1] = Field(default_factory=list)
    seed_canvas: list[SeedCanvasNodeV1] = Field(default_factory=list)
    teacher_notes: str = ""

    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    sealed_at: AwareDatetime | None = None
    sealed_by: str | None = None
    checksum: Checksum | None = None
    compatibility: CompatibilitySourceV1 = Field(default_factory=CompatibilitySourceV1)

    @model_validator(mode="after")
    def validate_references(self) -> "CoursePackageV1":
        source_ids = _unique_ids(self.source_refs, "source_id", "source_refs")
        fact_ids = _unique_ids(self.facts, "fact_id", "facts")
        _unique_ids(self.keywords, "keyword_id", "keywords")
        _unique_ids(self.people, "person_id", "people")
        _unique_ids(self.map_points, "point_id", "map_points")
        _unique_ids(self.seed_canvas, "node_id", "seed_canvas")
        _unique_ids(self.scenario_refs, "scenario_id", "scenario_refs")
        if sum(1 for item in self.scenario_refs if item.primary) > 1:
            raise ValueError("scenario_refs can contain at most one primary scenario")

        for fact in self.facts:
            _require_known(fact.source_ref_ids, source_ids, f"fact {fact.fact_id} source_ref_ids")
        for keyword in self.keywords:
            _require_known(keyword.source_ref_ids, source_ids, f"keyword {keyword.keyword_id} source_ref_ids")
        for person in self.people:
            _require_known(person.fact_refs, fact_ids, f"person {person.person_id} fact_refs")
            _require_known(person.source_ref_ids, source_ids, f"person {person.person_id} source_ref_ids")

        if self.status == "draft" and (
            self.content_version != 0
            or self.sealed_at is not None
            or self.sealed_by is not None
            or self.checksum is not None
        ):
            raise ValueError(
                "draft course packages require version 0 and cannot carry seal metadata"
            )
        if self.status == "sealed" and (
            self.content_version < 1
            or not self.body
            or self.sealed_at is None
            or not self.sealed_by
            or self.checksum is None
        ):
            raise ValueError("sealed course packages require body, version, sealed_at, sealed_by and checksum")
        if self.status == "sealed" and any(
            item.scenario_version < 1 or item.checksum is None
            for item in self.scenario_refs
        ):
            raise ValueError("sealed course scenario_refs must pin version and checksum")
        return self


class StateConditionV1(ContractModel):
    kind: Literal["state"] = "state"
    variable_id: ContractId
    operator: ComparisonOperator
    value: float


class TurnConditionV1(ContractModel):
    kind: Literal["turn"] = "turn"
    operator: ComparisonOperator
    value: int = Field(ge=0)


class NpcConditionV1(ContractModel):
    kind: Literal["npc"] = "npc"
    person_id: ContractId
    field: Literal["attitude", "trust"]
    operator: ComparisonOperator
    value: float


RuleConditionV1 = Annotated[
    StateConditionV1 | TurnConditionV1 | NpcConditionV1,
    Field(discriminator="kind"),
]


class StateEffectV1(ContractModel):
    kind: Literal["state"] = "state"
    variable_id: ContractId
    operation: Literal["add", "set"] = "add"
    value: float


class NpcEffectV1(ContractModel):
    kind: Literal["npc"] = "npc"
    person_id: ContractId
    attitude_delta: float = 0
    trust_delta: float = 0
    reveal_fact_refs: list[ContractId] = Field(default_factory=list)


RuleEffectV1 = Annotated[StateEffectV1 | NpcEffectV1, Field(discriminator="kind")]


class StateVariableV1(ContractModel):
    variable_id: ContractId
    label: NonEmptyText
    description: str = ""
    initial: float
    minimum: float = 0
    maximum: float = 100

    @model_validator(mode="after")
    def validate_range(self) -> "StateVariableV1":
        if self.minimum >= self.maximum:
            raise ValueError("minimum must be lower than maximum")
        if not self.minimum <= self.initial <= self.maximum:
            raise ValueError("initial must stay inside [minimum, maximum]")
        return self


class NpcSpecV1(ContractModel):
    person_id: ContractId
    display_name: NonEmptyText
    role: str = ""
    persona: str = ""
    boundaries: list[str] = Field(default_factory=list)
    initial_attitude: float = Field(default=0, ge=-100, le=100)
    initial_trust: float = Field(default=0, ge=-100, le=100)
    fact_refs: list[ContractId] = Field(default_factory=list)


class ActionRuleV1(ContractModel):
    action_id: ContractId
    label: NonEmptyText
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    available_when: list[RuleConditionV1] = Field(default_factory=list)
    effects: list[RuleEffectV1] = Field(default_factory=list)
    feedback: str = ""
    fact_refs: list[ContractId] = Field(default_factory=list)
    next_node_id: ContractId | None = None


class EventRuleV1(ContractModel):
    event_id: ContractId
    title: NonEmptyText
    match: Literal["all", "any"] = "all"
    trigger: list[RuleConditionV1] = Field(min_length=1)
    effects: list[RuleEffectV1] = Field(default_factory=list)
    narrative: str = ""
    once: bool = True
    priority: int = 100
    fact_refs: list[ContractId] = Field(default_factory=list)


class EndingRuleV1(ContractModel):
    ending_id: ContractId
    title: NonEmptyText
    match: Literal["all", "any"] = "all"
    conditions: list[RuleConditionV1] = Field(min_length=1)
    summary: NonEmptyText
    historical_explanation: str = ""
    major_costs: list[str] = Field(default_factory=list)
    source_ref_ids: list[ContractId] = Field(default_factory=list)
    fact_refs: list[ContractId] = Field(default_factory=list)
    priority: int = 100


class DossierTemplateV1(ContractModel):
    title_template: str = "《{scenario_title}卷宗》"
    reflection_questions: list[str] = Field(default_factory=list)
    knowledge_node_kinds: list[str] = Field(default_factory=list)


class ScenarioNodeV1(ContractModel):
    node_id: ContractId
    title: NonEmptyText
    narration: str = ""
    action_ids: list[ContractId] = Field(default_factory=list)
    ending_id: ContractId | None = None


class ScenarioTemplateV1(ContractModel):
    schema_version: Literal["scenario-template/v1"] = "scenario-template/v1"
    scenario_id: ContractId
    scenario_version: int = Field(default=0, ge=0)
    status: ArtifactStatus = "draft"
    engine_family: Literal["rules_v1"] = "rules_v1"
    course_id: ContractId
    lesson_id: ContractId
    title: NonEmptyText
    scenario_type: Literal["crisis_governance", "institutional_reform", "council"]
    student_role: NonEmptyText
    objective: NonEmptyText
    opening: NonEmptyText
    max_turns: int = Field(default=6, ge=1, le=50)

    variables: list[StateVariableV1] = Field(default_factory=list)
    npcs: list[NpcSpecV1] = Field(default_factory=list)
    action_rules: list[ActionRuleV1] = Field(default_factory=list)
    event_rules: list[EventRuleV1] = Field(default_factory=list)
    ending_rules: list[EndingRuleV1] = Field(default_factory=list)
    start_node_id: ContractId | None = None
    nodes: list[ScenarioNodeV1] = Field(default_factory=list)
    fact_refs: list[ContractId] = Field(default_factory=list)
    source_ref_ids: list[ContractId] = Field(default_factory=list)
    dossier_template: DossierTemplateV1 = Field(default_factory=DossierTemplateV1)
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    sealed_at: AwareDatetime | None = None
    sealed_by: str | None = None
    checksum: Checksum | None = None
    compatibility: CompatibilitySourceV1 = Field(default_factory=CompatibilitySourceV1)

    @model_validator(mode="after")
    def validate_rule_references(self) -> "ScenarioTemplateV1":
        variable_ids = _unique_ids(self.variables, "variable_id", "variables")
        person_ids = _unique_ids(self.npcs, "person_id", "npcs")
        action_ids = _unique_ids(self.action_rules, "action_id", "action_rules")
        _unique_ids(self.event_rules, "event_id", "event_rules")
        ending_ids = _unique_ids(self.ending_rules, "ending_id", "ending_rules")
        node_ids = _unique_ids(self.nodes, "node_id", "nodes")

        for action in self.action_rules:
            _validate_conditions(action.available_when, variable_ids, person_ids, f"action {action.action_id}")
            _validate_effects(action.effects, variable_ids, person_ids, f"action {action.action_id}")
            if action.next_node_id is not None:
                _require_known([action.next_node_id], node_ids, f"action {action.action_id} next_node_id")
        for event in self.event_rules:
            _validate_conditions(event.trigger, variable_ids, person_ids, f"event {event.event_id}")
            _validate_effects(event.effects, variable_ids, person_ids, f"event {event.event_id}")
        for ending in self.ending_rules:
            _validate_conditions(ending.conditions, variable_ids, person_ids, f"ending {ending.ending_id}")

        if self.nodes:
            if self.start_node_id is None:
                raise ValueError("node-based scenarios require start_node_id")
            _require_known([self.start_node_id], node_ids, "start_node_id")
            for node in self.nodes:
                _require_known(node.action_ids, action_ids, f"node {node.node_id} action_ids")
                if node.ending_id is not None:
                    _require_known([node.ending_id], ending_ids, f"node {node.node_id} ending_id")
            self._validate_node_reachability()
        elif self.start_node_id is not None:
            raise ValueError("start_node_id requires nodes")
        if self.status == "draft" and (
            self.scenario_version != 0
            or self.sealed_at is not None
            or self.sealed_by is not None
            or self.checksum is not None
        ):
            raise ValueError(
                "draft scenarios require version 0 and cannot carry seal metadata"
            )
        if self.status == "sealed" and (
            self.scenario_version < 1
            or not self.variables
            or not self.action_rules
            or not self.ending_rules
            or self.sealed_at is None
            or not self.sealed_by
            or self.checksum is None
        ):
            raise ValueError(
                "sealed scenarios require variables, actions, endings, version, sealed_at, sealed_by and checksum"
            )
        return self

    def _validate_node_reachability(self) -> None:
        actions = {item.action_id: item for item in self.action_rules}
        nodes = {item.node_id: item for item in self.nodes}
        reachable: set[str] = set()
        pending = [str(self.start_node_id)]
        while pending:
            node_id = pending.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            for action_id in nodes[node_id].action_ids:
                next_node_id = actions[action_id].next_node_id
                if next_node_id is not None and next_node_id not in reachable:
                    pending.append(next_node_id)
        unreachable = sorted(set(nodes) - reachable)
        if unreachable:
            raise ValueError(f"nodes are unreachable from start_node_id: {', '.join(unreachable)}")
        if not any(nodes[node_id].ending_id is not None for node_id in reachable):
            raise ValueError("node-based scenarios require a reachable ending node")


class NpcStateV1(ContractModel):
    person_id: ContractId
    attitude: float = Field(default=0, ge=-100, le=100)
    trust: float = Field(default=0, ge=-100, le=100)
    known_fact_refs: list[ContractId] = Field(default_factory=list)
    last_basis_refs: list[ContractId] = Field(default_factory=list)
    flags: dict[str, str | int | float | bool] = Field(default_factory=dict)
    updated_turn: int = Field(default=0, ge=0)


class StateChangeV1(ContractModel):
    variable_id: ContractId
    before: float
    after: float
    delta: float

    @model_validator(mode="after")
    def validate_delta(self) -> "StateChangeV1":
        if abs((self.after - self.before) - self.delta) > 1e-9:
            raise ValueError("delta must equal after - before")
        return self


class NpcChangeV1(ContractModel):
    person_id: ContractId
    attitude_before: float = Field(ge=-100, le=100)
    attitude_after: float = Field(ge=-100, le=100)
    trust_before: float = Field(ge=-100, le=100)
    trust_after: float = Field(ge=-100, le=100)
    revealed_fact_refs: list[ContractId] = Field(default_factory=list)


class TurnV1(ContractModel):
    turn_id: ContractId
    session_id: ContractId
    client_action_id: ContractId
    turn_no: int = Field(ge=1)
    status: Literal["applied", "rejected", "failed"] = "applied"
    raw_input: PlayerInput
    action_source: Literal["fixed", "free_input", "fallback"]
    classified_action_id: ContractId
    classification_confidence: float | None = Field(default=None, ge=0, le=1)
    state_before: dict[ContractId, float]
    state_after: dict[ContractId, float]
    state_changes: list[StateChangeV1] = Field(default_factory=list)
    npc_changes: list[NpcChangeV1] = Field(default_factory=list)
    triggered_event_ids: list[ContractId] = Field(default_factory=list)
    fact_refs: list[ContractId] = Field(default_factory=list)
    narrative: str = ""
    narrative_source: Literal["rules", "llm", "mock", "fallback"] = "rules"
    narrative_model: str = ""
    narrative_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    ruleset_hash: str = ""
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_turn_snapshot(self) -> "TurnV1":
        if set(self.state_before) != set(self.state_after):
            raise ValueError("state_before and state_after must contain the same variables")
        _unique_ids(self.state_changes, "variable_id", "state_changes")
        _unique_ids(self.npc_changes, "person_id", "npc_changes")
        changed = {
            variable_id
            for variable_id, before in self.state_before.items()
            if self.state_after[variable_id] != before
        }
        recorded = {item.variable_id for item in self.state_changes}
        if changed != recorded:
            raise ValueError("state_changes must exactly describe the state snapshot difference")
        for change in self.state_changes:
            if (
                change.before != self.state_before[change.variable_id]
                or change.after != self.state_after[change.variable_id]
            ):
                raise ValueError("state_changes values must match state_before/state_after")
        return self


class NarrativeMessageV1(ContractModel):
    role: Literal["player", "narrator", "system"]
    text: NonEmptyText
    turn_no: int = Field(ge=0)


class ObservedEntityV1(ContractModel):
    entity_id: ContractId
    name: NonEmptyText
    kind: Literal["person", "place", "object", "event", "other"]
    description: str = ""
    first_seen_turn: int = Field(ge=0)


class GameSessionV1(ContractModel):
    schema_version: Literal["game-session/v1"] = "game-session/v1"
    session_id: ContractId
    user_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    scenario_id: ContractId
    scenario_version: int = Field(ge=1)
    course_content_version: int = Field(ge=1)
    course_checksum: Checksum
    scenario_checksum: Checksum
    engine_version: NonEmptyText
    random_seed: str = ""
    status: Literal["active", "completed", "abandoned", "failed"] = "active"
    revision: int = Field(default=1, ge=1)
    current_turn: int = Field(default=0, ge=0)
    current_state: dict[ContractId, float]
    current_node_id: ContractId | None = None
    npc_states: list[NpcStateV1] = Field(default_factory=list)
    turns: list[TurnV1] = Field(default_factory=list)
    triggered_event_ids: list[ContractId] = Field(default_factory=list)
    available_action_ids: list[ContractId] = Field(default_factory=list)
    available_choices: list[str] = Field(default_factory=list)
    summary: str = ""
    flags: dict[str, str | int | float | bool] = Field(default_factory=dict)
    narrative_flags: dict[str, str | int | float | bool] = Field(default_factory=dict)
    observed_entities: list[ObservedEntityV1] = Field(default_factory=list)
    history: list[NarrativeMessageV1] = Field(default_factory=list)
    ending_id: ContractId | None = None
    dossier_id: ContractId | None = None
    started_at: AwareDatetime
    updated_at: AwareDatetime
    ended_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_session_snapshot(self) -> "GameSessionV1":
        _unique_ids(self.npc_states, "person_id", "npc_states")
        _unique_ids(self.observed_entities, "entity_id", "observed_entities")
        _ensure_unique_values(self.available_action_ids, "available_action_ids")
        _unique_ids(self.turns, "turn_id", "turns")
        _unique_ids(self.turns, "client_action_id", "turn client_action_ids")
        turn_numbers = [turn.turn_no for turn in self.turns]
        if turn_numbers != list(range(1, len(self.turns) + 1)):
            raise ValueError("turns must be ordered and numbered from 1")
        if self.current_turn != len(self.turns):
            raise ValueError("current_turn must equal the number of stored turns")
        if any(turn.session_id != self.session_id for turn in self.turns):
            raise ValueError("all turns must reference this session_id")
        for previous, current in zip(self.turns, self.turns[1:]):
            if current.state_before != previous.state_after:
                raise ValueError("turn snapshots must form a continuous replay chain")
        if self.turns and self.current_state != self.turns[-1].state_after:
            raise ValueError("current_state must equal the latest turn state_after")
        turn_times = [turn.created_at for turn in self.turns]
        if turn_times != sorted(turn_times):
            raise ValueError("turn created_at values must be ordered")
        if self.updated_at < self.started_at:
            raise ValueError("updated_at cannot be earlier than started_at")
        if turn_times and (
            turn_times[0] < self.started_at
            or turn_times[-1] > self.updated_at
        ):
            raise ValueError("turn created_at values must stay inside the session time window")
        if self.status == "completed" and (self.ended_at is None or self.ending_id is None):
            raise ValueError("completed sessions require ended_at and ending_id")
        if self.status in {"completed", "abandoned", "failed"} and self.ended_at is None:
            raise ValueError("terminal sessions require ended_at")
        if self.status in {"abandoned", "failed"} and (
            self.ending_id is not None or self.dossier_id is not None
        ):
            raise ValueError("abandoned/failed sessions cannot carry ending or dossier metadata")
        if self.status == "active" and (
            self.ended_at is not None
            or self.ending_id is not None
            or self.dossier_id is not None
        ):
            raise ValueError("active sessions cannot have ending or dossier metadata")
        if self.ended_at is not None and (
            self.ended_at < self.started_at
            or self.ended_at > self.updated_at
            or (turn_times and self.ended_at < turn_times[-1])
        ):
            raise ValueError("ended_at must stay inside the session time window")
        return self


class DossierChoiceV1(ContractModel):
    turn_id: ContractId
    turn_no: int = Field(ge=1)
    action_id: ContractId
    choice: NonEmptyText
    consequence: str = ""


class StateSnapshotV1(ContractModel):
    turn_no: int = Field(ge=0)
    state: dict[ContractId, float]


class KnowledgeNodeV1(ContractModel):
    node_id: ContractId
    label: NonEmptyText
    kind: Literal["person", "event", "place", "concept", "cause", "consequence"]
    summary: str = ""
    source_ref_ids: list[ContractId] = Field(default_factory=list)


class KnowledgeEdgeV1(ContractModel):
    edge_id: ContractId
    source_node_id: ContractId
    target_node_id: ContractId
    relation: NonEmptyText
    explanation: str = ""
    source_ref_ids: list[ContractId] = Field(default_factory=list)


class DossierV1(ContractModel):
    schema_version: Literal["dossier/v1"] = "dossier/v1"
    dossier_id: ContractId
    session_id: ContractId
    user_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    scenario_id: ContractId
    course_content_version: int = Field(ge=1)
    scenario_version: int = Field(ge=1)
    course_checksum: Checksum
    scenario_checksum: Checksum
    status: Literal["draft", "final"] = "draft"
    title: NonEmptyText
    ending_id: ContractId
    strategy_summary: str = ""
    key_choices: list[DossierChoiceV1] = Field(default_factory=list)
    state_trajectory: list[StateSnapshotV1] = Field(default_factory=list)
    major_costs: list[str] = Field(default_factory=list)
    historical_explanation: str = ""
    knowledge_nodes: list[KnowledgeNodeV1] = Field(default_factory=list)
    knowledge_edges: list[KnowledgeEdgeV1] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    reflection_notes: list[str] = Field(default_factory=list)
    fact_refs: list[ContractId] = Field(default_factory=list)
    source_ref_ids: list[ContractId] = Field(default_factory=list)
    generated_at: AwareDatetime
    checksum: Checksum | None = None

    @model_validator(mode="after")
    def validate_dossier(self) -> "DossierV1":
        node_ids = _unique_ids(self.knowledge_nodes, "node_id", "knowledge_nodes")
        _unique_ids(self.knowledge_edges, "edge_id", "knowledge_edges")
        for edge in self.knowledge_edges:
            _require_known(
                [edge.source_node_id, edge.target_node_id],
                node_ids,
                f"knowledge edge {edge.edge_id}",
            )
        turn_numbers = [snapshot.turn_no for snapshot in self.state_trajectory]
        if turn_numbers != sorted(set(turn_numbers)):
            raise ValueError("state_trajectory turn numbers must be unique and ordered")
        if self.status == "final" and self.checksum is None:
            raise ValueError("final dossiers require checksum")
        if self.status == "draft" and self.checksum is not None:
            raise ValueError("draft dossiers cannot carry a checksum")
        return self


class RuntimeBundleV1(ContractModel):
    schema_version: Literal["runtime-bundle/v1"] = "runtime-bundle/v1"
    course: CoursePackageV1
    scenario: ScenarioTemplateV1
    session: GameSessionV1 | None = None
    dossier: DossierV1 | None = None

    @model_validator(mode="after")
    def validate_cross_references(self) -> "RuntimeBundleV1":
        course = self.course
        scenario = self.scenario
        if (scenario.course_id, scenario.lesson_id) != (course.course_id, course.lesson_id):
            raise ValueError("scenario course_id/lesson_id must match the course package")
        scenario_ref = next(
            (item for item in course.scenario_refs if item.scenario_id == scenario.scenario_id),
            None,
        )
        if scenario_ref is None:
            raise ValueError("course scenario_refs must include scenario.scenario_id")
        if course.status != "sealed" or scenario.status != "sealed":
            raise ValueError("runtime bundles require sealed course and scenario artifacts")
        if not verify_contract_checksum(course) or not verify_contract_checksum(scenario):
            raise ValueError("runtime bundle contains a sealed artifact with an invalid checksum")
        if (
            scenario_ref.scenario_version != scenario.scenario_version
            or scenario_ref.checksum != scenario.checksum
        ):
            raise ValueError("course scenario reference must pin the scenario version and checksum")

        fact_ids = {item.fact_id for item in course.facts}
        source_ids = {item.source_id for item in course.source_refs}
        person_ids = {item.person_id for item in course.people}
        variable_ids = {item.variable_id for item in scenario.variables}
        variable_ranges = {
            item.variable_id: (item.minimum, item.maximum)
            for item in scenario.variables
        }
        initial_state = {item.variable_id: item.initial for item in scenario.variables}
        scenario_person_ids = {item.person_id for item in scenario.npcs}
        action_ids = {item.action_id for item in scenario.action_rules}
        event_ids = {item.event_id for item in scenario.event_rules}
        ending_ids = {item.ending_id for item in scenario.ending_rules}
        node_ids = {item.node_id for item in scenario.nodes}

        _require_known(scenario.fact_refs, fact_ids, "scenario fact_refs")
        _require_known(scenario.source_ref_ids, source_ids, "scenario source_ref_ids")
        for npc in scenario.npcs:
            _require_known([npc.person_id], person_ids, f"scenario npc {npc.person_id}")
            _require_known(npc.fact_refs, fact_ids, f"scenario npc {npc.person_id} fact_refs")
        for action in scenario.action_rules:
            _require_known(action.fact_refs, fact_ids, f"action {action.action_id} fact_refs")
            _validate_effect_fact_refs(action.effects, fact_ids, f"action {action.action_id}")
        for event in scenario.event_rules:
            _require_known(event.fact_refs, fact_ids, f"event {event.event_id} fact_refs")
            _validate_effect_fact_refs(event.effects, fact_ids, f"event {event.event_id}")
        for ending in scenario.ending_rules:
            _require_known(ending.fact_refs, fact_ids, f"ending {ending.ending_id} fact_refs")
            _require_known(ending.source_ref_ids, source_ids, f"ending {ending.ending_id} source_ref_ids")

        if self.session is not None:
            session = self.session
            if session.current_turn > scenario.max_turns:
                raise ValueError("session cannot exceed scenario max_turns")
            if (session.course_id, session.lesson_id, session.scenario_id) != (
                course.course_id,
                course.lesson_id,
                scenario.scenario_id,
            ):
                raise ValueError("session references must match course and scenario")
            if (
                session.course_content_version != course.content_version
                or session.scenario_version != scenario.scenario_version
                or session.course_checksum != course.checksum
                or session.scenario_checksum != scenario.checksum
            ):
                raise ValueError("session must pin the exact course and scenario artifacts")
            _require_known(session.current_state.keys(), variable_ids, "session current_state")
            _validate_state_ranges(session.current_state, variable_ranges, "session current_state")
            _require_known(
                [item.person_id for item in session.npc_states],
                scenario_person_ids,
                "session npc_states",
            )
            for npc_state in session.npc_states:
                _require_known(npc_state.known_fact_refs, fact_ids, f"npc {npc_state.person_id} known facts")
                _require_known(npc_state.last_basis_refs, fact_ids, f"npc {npc_state.person_id} basis")
            _require_known(session.triggered_event_ids, event_ids, "session triggered_event_ids")
            _require_known(session.available_action_ids, action_ids, "session available_action_ids")
            if session.current_node_id is not None:
                _require_known([session.current_node_id], node_ids, "session current_node_id")
            if session.turns and session.turns[0].state_before != initial_state:
                raise ValueError("the first turn must start from the scenario initial state")
            if not session.turns and session.current_state != initial_state:
                raise ValueError("a zero-turn session must remain at the scenario initial state")
            if not session.turns and session.current_node_id != scenario.start_node_id:
                raise ValueError("a zero-turn session must remain at the scenario start node")
            for turn in session.turns:
                _require_known([turn.classified_action_id], action_ids, f"turn {turn.turn_no} action")
                _require_known(turn.state_before.keys(), variable_ids, f"turn {turn.turn_no} state_before")
                _require_known(turn.state_after.keys(), variable_ids, f"turn {turn.turn_no} state_after")
                _validate_state_ranges(turn.state_before, variable_ranges, f"turn {turn.turn_no} state_before")
                _validate_state_ranges(turn.state_after, variable_ranges, f"turn {turn.turn_no} state_after")
                _require_known(
                    [change.variable_id for change in turn.state_changes],
                    variable_ids,
                    f"turn {turn.turn_no} state_changes",
                )
                _require_known(
                    [change.person_id for change in turn.npc_changes],
                    scenario_person_ids,
                    f"turn {turn.turn_no} npc_changes",
                )
                for change in turn.npc_changes:
                    _require_known(
                        change.revealed_fact_refs,
                        fact_ids,
                        f"turn {turn.turn_no} npc revealed facts",
                    )
                _require_known(turn.triggered_event_ids, event_ids, f"turn {turn.turn_no} events")
                _require_known(turn.fact_refs, fact_ids, f"turn {turn.turn_no} fact_refs")
            if session.ending_id is not None:
                _require_known([session.ending_id], ending_ids, "session ending_id")
            _validate_turn_replay(
                scenario,
                session,
            )

        if self.dossier is not None:
            if self.session is None:
                raise ValueError("a dossier requires its game session in the bundle")
            dossier = self.dossier
            session = self.session
            if dossier.status != "final":
                raise ValueError("runtime bundles require a final dossier")
            if not verify_contract_checksum(dossier):
                raise ValueError("runtime bundle contains a dossier with an invalid checksum")
            if (dossier.session_id, dossier.user_id) != (session.session_id, session.user_id):
                raise ValueError("dossier session_id/user_id must match the session")
            if (dossier.course_id, dossier.lesson_id, dossier.scenario_id) != (
                course.course_id,
                course.lesson_id,
                scenario.scenario_id,
            ):
                raise ValueError("dossier references must match course and scenario")
            if (
                dossier.course_content_version != course.content_version
                or dossier.scenario_version != scenario.scenario_version
                or dossier.course_checksum != course.checksum
                or dossier.scenario_checksum != scenario.checksum
            ):
                raise ValueError("dossier must pin the exact course and scenario artifacts")
            if session.status != "completed" or session.dossier_id != dossier.dossier_id:
                raise ValueError("final dossier requires a completed session that references it")
            if dossier.ending_id != session.ending_id:
                raise ValueError("dossier ending_id must match the completed session")
            _require_known([dossier.ending_id], ending_ids, "dossier ending_id")
            _require_known(dossier.fact_refs, fact_ids, "dossier fact_refs")
            _require_known(dossier.source_ref_ids, source_ids, "dossier source_ref_ids")
            turns_by_id = {turn.turn_id: turn for turn in session.turns}
            for choice in dossier.key_choices:
                _require_known([choice.action_id], action_ids, f"dossier choice turn {choice.turn_no}")
                _require_known([choice.turn_id], set(turns_by_id), f"dossier choice turn_id {choice.turn_id}")
                turn = turns_by_id[choice.turn_id]
                if turn.turn_no != choice.turn_no or turn.classified_action_id != choice.action_id:
                    raise ValueError("dossier key choices must match their recorded turns")
                if turn.status != "applied" or choice.choice != turn.raw_input:
                    raise ValueError("dossier key choices must quote applied player input exactly")
            for snapshot in dossier.state_trajectory:
                _require_known(snapshot.state.keys(), variable_ids, f"dossier snapshot {snapshot.turn_no}")
                _validate_state_ranges(snapshot.state, variable_ranges, f"dossier snapshot {snapshot.turn_no}")
            expected_trajectory = [StateSnapshotV1(turn_no=0, state=initial_state)] + [
                StateSnapshotV1(turn_no=turn.turn_no, state=turn.state_after)
                for turn in session.turns
            ]
            if dossier.state_trajectory != expected_trajectory:
                raise ValueError("dossier trajectory must match every recorded session turn")
            for node in dossier.knowledge_nodes:
                _require_known(node.source_ref_ids, source_ids, f"knowledge node {node.node_id}")
            for edge in dossier.knowledge_edges:
                _require_known(edge.source_ref_ids, source_ids, f"knowledge edge {edge.edge_id}")
            if session.ended_at is None or dossier.generated_at < session.ended_at:
                raise ValueError("dossier generated_at cannot be earlier than session ended_at")
        return self


def course_package_from_legacy(payload: "LessonContentPackage") -> CoursePackageV1:
    if payload.status == "sealed" and (
        payload.checksum is None
        or payload.checksum != calculate_contract_checksum(payload)
    ):
        raise ValueError("legacy sealed content has a missing or invalid checksum")

    source_refs = _dedupe_models([
        SourceRefV1(
            source_id=_stable_id(
                "source",
                _legacy_seed(
                    item.title,
                    item.source,
                    item.url_or_path,
                    item.citation_note,
                    item.reliability,
                ),
            ),
            title=item.title or item.source or "未命名资料",
            publisher=item.source,
            url_or_path=item.url_or_path,
            citation_note=item.citation_note,
            reliability=(item.reliability if item.reliability in {"pending", "reviewed", "disputed"} else "pending"),
        )
        for item in payload.source_refs
    ], "source_id")
    facts = _dedupe_models([
        FactV1(
            fact_id=_stable_id("fact", statement),
            statement=statement,
            source_ref_ids=[],
            certainty="interpretation",
            teacher_note="Legacy content did not bind individual facts to sources; review before release.",
        )
        for statement in payload.facts
    ], "fact_id")
    keywords = _dedupe_models([
        KeywordV1(
            keyword_id=_stable_id(
                "keyword",
                _legacy_seed(item.word, item.pinyin, item.gloss),
            ),
            word=item.word,
            pinyin=item.pinyin,
            gloss=item.gloss,
            source_ref_ids=[],
        )
        for item in payload.keywords
    ], "keyword_id")
    people = _dedupe_models([
        PersonV1(
            person_id=_stable_id(
                "person",
                _legacy_seed(
                    item.name,
                    item.role,
                    item.summary,
                    item.persona,
                    item.boundaries,
                ),
            ),
            name=item.name,
            role=item.role,
            summary=item.summary,
            persona=item.persona,
            boundaries=item.boundaries,
            fact_refs=[],
            source_ref_ids=[],
        )
        for item in payload.people
    ], "person_id")
    map_points = _dedupe_models([
        MapPointV1(
            point_id=_stable_id(
                "map",
                _legacy_seed(
                    item.label,
                    item.region,
                    item.lat,
                    item.lng,
                    item.note,
                    item.kind,
                ),
            ),
            label=item.label,
            region=item.region,
            lat=item.lat,
            lng=item.lng,
            note=item.note,
            kind=item.kind,
        )
        for item in payload.map_points
    ], "point_id")
    seed_canvas, legacy_id_map = _adapt_legacy_seed_canvas(payload.seed_canvas)
    unresolved_refs = list(
        dict.fromkeys([*payload.saga_material.assets, *payload.sandbox_material.assets])
    )
    package = CoursePackageV1(
        package_id=_legacy_package_id(payload.lesson_id),
        course_id=payload.course_id,
        lesson_id=payload.lesson_id,
        content_version=payload.version,
        status=payload.status,
        title=payload.title,
        unit=payload.unit,
        era=payload.era,
        body=payload.body,
        abstract=payload.abstract,
        course_title=payload.course_title,
        era_id=payload.era_id,
        section=payload.section,
        lesson_no=payload.lesson_no,
        duration=payload.duration,
        teaching_objectives=(payload.level_goals or ["【教师待补】本课教学目标"]),
        keywords=keywords,
        people=people,
        map_points=map_points,
        facts=facts,
        source_refs=source_refs,
        qa_points=payload.qa_points,
        level_goals=payload.level_goals,
        scenario_refs=[],
        seed_canvas=seed_canvas,
        teacher_notes=payload.teacher_notes,
        created_at=payload.created_at,
        updated_at=payload.updated_at,
        sealed_at=payload.sealed_at,
        sealed_by=payload.sealed_by,
        checksum=("0" * 64 if payload.status == "sealed" else None),
        compatibility=CompatibilitySourceV1(
            kind="lesson-content-package",
            source_id=payload.lesson_id,
            source_version=str(payload.version),
            source_checksum=payload.checksum,
            notes="Normalized from the A1 LessonContentPackage without changing the source draft.",
            unresolved_refs=unresolved_refs,
            legacy_id_map=legacy_id_map,
            legacy_materials=[
                LegacyMaterialSnapshotV1(
                    kind="saga",
                    title=payload.saga_material.title,
                    objective=payload.saga_material.objective,
                    notes=payload.saga_material.notes,
                    assets=payload.saga_material.assets,
                ),
                LegacyMaterialSnapshotV1(
                    kind="sandbox",
                    title=payload.sandbox_material.title,
                    objective=payload.sandbox_material.objective,
                    notes=payload.sandbox_material.notes,
                    assets=payload.sandbox_material.assets,
                ),
            ],
        ),
    )
    if package.status == "sealed":
        data = package.model_dump(mode="json")
        data["checksum"] = calculate_contract_checksum(package)
        return CoursePackageV1.model_validate(data)
    return package


def calculate_contract_checksum(payload: BaseModel) -> str:
    if not isinstance(payload, BaseModel):
        raise TypeError("validate raw data with its Pydantic contract before calculating a checksum")
    data = payload.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("contract payload does not expose a top-level checksum field")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_contract_checksum(payload: BaseModel) -> bool:
    checksum = getattr(payload, "checksum", None)
    return bool(checksum) and checksum == calculate_contract_checksum(payload)


def schema_document(model: type[BaseModel], schema_id: str) -> dict:
    generated = model.model_json_schema(ref_template="#/$defs/{model}")
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "$comment": (
            "Lifecycle conditions are represented here when JSON Schema can express them. "
            "Cross-object references, checksums and replay invariants require the "
            "services.contracts RuntimeBundleV1 semantic validator."
        ),
        **generated,
    }
    conditions = _schema_lifecycle_conditions(model)
    if conditions:
        document["required"] = list(dict.fromkeys([*document.get("required", []), "status"]))
        document["allOf"] = conditions
    return document


SCHEMA_DOCUMENTS: dict[str, tuple[type[BaseModel], str]] = {
    "course-package.schema.json": (
        CoursePackageV1,
        "https://chronovita.local/schemas/v1/course-package.schema.json",
    ),
    "scenario-template.schema.json": (
        ScenarioTemplateV1,
        "https://chronovita.local/schemas/v1/scenario-template.schema.json",
    ),
    "game-session.schema.json": (
        GameSessionV1,
        "https://chronovita.local/schemas/v1/game-session.schema.json",
    ),
    "dossier.schema.json": (
        DossierV1,
        "https://chronovita.local/schemas/v1/dossier.schema.json",
    ),
    "runtime-bundle.schema.json": (
        RuntimeBundleV1,
        "https://chronovita.local/schemas/v1/runtime-bundle.schema.json",
    ),
}


def _schema_lifecycle_conditions(model: type[BaseModel]) -> list[dict]:
    if model is CoursePackageV1:
        return [
            {
                "if": {"properties": {"status": {"const": "draft"}}, "required": ["status"]},
                "then": {
                    "properties": {
                        "content_version": {"const": 0},
                        "sealed_at": {"const": None},
                        "sealed_by": {"const": None},
                        "checksum": {"const": None},
                    }
                },
            },
            {
                "if": {"properties": {"status": {"const": "sealed"}}, "required": ["status"]},
                "then": {
                    "required": [
                        "body",
                        "content_version",
                        "sealed_at",
                        "sealed_by",
                        "checksum",
                    ],
                    "properties": {
                        "body": {"minItems": 1},
                        "content_version": {"minimum": 1},
                        "sealed_at": {"type": "string"},
                        "sealed_by": {"type": "string", "minLength": 1},
                        "checksum": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
        ]
    if model is ScenarioTemplateV1:
        return [
            {
                "if": {"properties": {"status": {"const": "draft"}}, "required": ["status"]},
                "then": {
                    "properties": {
                        "scenario_version": {"const": 0},
                        "sealed_at": {"const": None},
                        "sealed_by": {"const": None},
                        "checksum": {"const": None},
                    }
                },
            },
            {
                "if": {"properties": {"status": {"const": "sealed"}}, "required": ["status"]},
                "then": {
                    "required": [
                        "variables",
                        "action_rules",
                        "ending_rules",
                        "scenario_version",
                        "sealed_at",
                        "sealed_by",
                        "checksum",
                    ],
                    "properties": {
                        "scenario_version": {"minimum": 1},
                        "variables": {"minItems": 1},
                        "action_rules": {"minItems": 1},
                        "ending_rules": {"minItems": 1},
                        "sealed_at": {"type": "string"},
                        "sealed_by": {"type": "string", "minLength": 1},
                        "checksum": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
        ]
    if model is GameSessionV1:
        return [
            {
                "if": {"properties": {"status": {"const": "active"}}, "required": ["status"]},
                "then": {
                    "properties": {
                        "ended_at": {"const": None},
                        "ending_id": {"const": None},
                        "dossier_id": {"const": None},
                    }
                },
            },
            {
                "if": {
                    "properties": {
                        "status": {"enum": ["completed", "abandoned", "failed"]}
                    },
                    "required": ["status"],
                },
                "then": {
                    "required": ["ended_at"],
                    "properties": {"ended_at": {"type": "string"}},
                },
            },
            {
                "if": {
                    "properties": {"status": {"enum": ["abandoned", "failed"]}},
                    "required": ["status"],
                },
                "then": {
                    "properties": {
                        "ending_id": {"const": None},
                        "dossier_id": {"const": None},
                    },
                },
            },
            {
                "if": {"properties": {"status": {"const": "completed"}}, "required": ["status"]},
                "then": {
                    "required": ["ended_at", "ending_id"],
                    "properties": {
                        "ended_at": {"type": "string"},
                        "ending_id": {"type": "string"},
                    }
                },
            },
        ]
    if model is DossierV1:
        return [
            {
                "if": {"properties": {"status": {"const": "draft"}}, "required": ["status"]},
                "then": {"properties": {"checksum": {"const": None}}},
            },
            {
                "if": {"properties": {"status": {"const": "final"}}, "required": ["status"]},
                "then": {
                    "required": ["checksum"],
                    "properties": {
                        "checksum": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
                    }
                },
            }
        ]
    return []


def _unique_ids(items: list[ContractModel], attr: str, label: str) -> set[str]:
    values = [str(getattr(item, attr)) for item in items]
    _ensure_unique_values(values, label)
    return set(values)


def _ensure_unique_values(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{label} contains duplicate ids: {', '.join(duplicates)}")


def _require_known(values, allowed: set[str], label: str) -> None:
    unknown = sorted({str(value) for value in values} - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown references: {', '.join(unknown)}")


def _validate_conditions(
    conditions: list[RuleConditionV1],
    variable_ids: set[str],
    person_ids: set[str],
    label: str,
) -> None:
    for condition in conditions:
        if isinstance(condition, StateConditionV1):
            _require_known([condition.variable_id], variable_ids, f"{label} condition")
        elif isinstance(condition, NpcConditionV1):
            _require_known([condition.person_id], person_ids, f"{label} condition")


def _validate_effects(
    effects: list[RuleEffectV1],
    variable_ids: set[str],
    person_ids: set[str],
    label: str,
) -> None:
    for effect in effects:
        if isinstance(effect, StateEffectV1):
            _require_known([effect.variable_id], variable_ids, f"{label} effect")
        else:
            _require_known([effect.person_id], person_ids, f"{label} effect")


def _validate_effect_fact_refs(effects: list[RuleEffectV1], fact_ids: set[str], label: str) -> None:
    for effect in effects:
        if isinstance(effect, NpcEffectV1):
            _require_known(effect.reveal_fact_refs, fact_ids, f"{label} reveal_fact_refs")


def _validate_turn_replay(
    scenario: ScenarioTemplateV1,
    session: GameSessionV1,
) -> None:
    snapshot = initial_rule_snapshot(scenario)

    for turn in session.turns:
        if not _states_match(snapshot.state_dict(), turn.state_before):
            raise ValueError(f"turn {turn.turn_no} state_before does not match replay")

        if turn.status != "applied":
            if (
                not _states_match(snapshot.state_dict(), turn.state_after)
                or turn.npc_changes
                or turn.triggered_event_ids
            ):
                raise ValueError(
                    f"turn {turn.turn_no} rejected/failed results cannot contain rule effects"
                )
            ending_id = select_rule_ending_id(scenario, snapshot, turn.turn_no)
            if ending_id is not None and turn.turn_no < session.current_turn:
                raise ValueError(f"session continues after ending {ending_id}")
            continue

        try:
            result = evaluate_rule_action(
                scenario,
                snapshot,
                turn.classified_action_id,
                turn.turn_no,
            )
        except (RuleActionUnavailable, UnknownRuleAction, RuleEvaluationError) as exc:
            raise ValueError(f"turn {turn.turn_no} {exc}") from exc

        expected_event_ids = list(result.triggered_event_ids)
        if turn.triggered_event_ids != expected_event_ids:
            raise ValueError(f"turn {turn.turn_no} triggered events do not match rule conditions")
        if not _states_match(result.snapshot.state_dict(), turn.state_after):
            raise ValueError(f"turn {turn.turn_no} state_after does not match rule effects")

        recorded_npcs = {item.person_id: item for item in turn.npc_changes}
        expected_npcs = {item.person_id: item for item in result.npc_changes}
        if set(recorded_npcs) != set(expected_npcs):
            raise ValueError(f"turn {turn.turn_no} npc_changes must match rule effects")
        for person_id, expected in expected_npcs.items():
            recorded = recorded_npcs[person_id]
            if (
                not _numbers_match(recorded.attitude_before, expected.attitude_before)
                or not _numbers_match(recorded.attitude_after, expected.attitude_after)
                or not _numbers_match(recorded.trust_before, expected.trust_before)
                or not _numbers_match(recorded.trust_after, expected.trust_after)
                or recorded.revealed_fact_refs != list(expected.revealed_fact_refs)
            ):
                raise ValueError(f"turn {turn.turn_no} npc change does not match rule effects")

        snapshot = result.snapshot
        if result.ending_id is not None and turn.turn_no < session.current_turn:
            raise ValueError(f"session continues after ending {result.ending_id}")

    if not _states_match(snapshot.state_dict(), session.current_state):
        raise ValueError("session current_state does not match the completed replay")
    if session.current_node_id != snapshot.current_node_id:
        raise ValueError("session current_node_id does not match node replay")
    if session.triggered_event_ids != list(snapshot.triggered_event_ids):
        raise ValueError("session triggered_event_ids do not match turn replay")
    if session.status == "active" and session.current_turn >= scenario.max_turns:
        raise ValueError("active session cannot remain open at scenario max_turns")

    next_turn_no = session.current_turn + 1
    expected_available_action_ids = (
        list(available_rule_action_ids(scenario, snapshot, next_turn_no))
        if session.status == "active" and session.current_turn < scenario.max_turns
        else []
    )
    if session.available_action_ids != expected_available_action_ids:
        raise ValueError("session available_action_ids do not match the replay state")

    snapshots = {item.person_id: item for item in session.npc_states}
    expected_npcs = snapshot.npc_dict()
    if set(snapshots) != set(expected_npcs):
        raise ValueError("session npc_states must include every scenario NPC exactly once")
    for person_id, expected in expected_npcs.items():
        npc_snapshot = snapshots[person_id]
        if (
            not _numbers_match(npc_snapshot.attitude, expected.attitude)
            or not _numbers_match(npc_snapshot.trust, expected.trust)
            or set(npc_snapshot.known_fact_refs) != set(expected.known_fact_refs)
            or npc_snapshot.updated_turn != expected.updated_turn
        ):
            raise ValueError(f"session NPC snapshot does not match replay: {person_id}")

    expected_ending_id = select_rule_ending_id(
        scenario,
        snapshot,
        session.current_turn,
    )
    if session.status == "completed":
        if session.ending_id != expected_ending_id:
            raise ValueError("completed session ending_id does not match ending rules")
    elif session.status == "active" and expected_ending_id is not None:
        raise ValueError("active session cannot remain open after an ending is reached")
    elif session.status in {"abandoned", "failed"} and expected_ending_id is not None:
        raise ValueError(
            f"{session.status} session cannot discard reached ending {expected_ending_id}"
        )


def _states_match(left: dict[str, float], right: dict[str, float]) -> bool:
    return set(left) == set(right) and all(
        _numbers_match(left[key], right[key])
        for key in left
    )


def _numbers_match(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9


def _validate_state_ranges(
    state: dict[str, float],
    variable_ranges: dict[str, tuple[float, float]],
    label: str,
) -> None:
    invalid = [
        variable_id
        for variable_id, value in state.items()
        if not variable_ranges[variable_id][0] <= value <= variable_ranges[variable_id][1]
    ]
    if invalid:
        raise ValueError(f"{label} contains values outside variable ranges: {', '.join(sorted(invalid))}")


def _stable_id(prefix: str, seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _legacy_seed(*parts: object) -> str:
    return json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _adapt_legacy_seed_canvas(items) -> tuple[list[SeedCanvasNodeV1], dict[str, str]]:
    nodes: list[SeedCanvasNodeV1] = []
    id_map: dict[str, str] = {}
    for item in items:
        original_id = item.id.strip()
        node_id = _legacy_id_or_stable(
            "node",
            original_id,
            _legacy_seed(item.id, item.label, item.note),
        )
        if original_id and original_id != node_id:
            map_key = f"seed_canvas:{original_id}"
            previous = id_map.get(map_key)
            if previous is not None and previous != node_id:
                raise ValueError(f"legacy seed_canvas id is ambiguous: {original_id}")
            id_map[map_key] = node_id
        nodes.append(
            SeedCanvasNodeV1(
                node_id=node_id,
                label=item.label,
                note=item.note,
            )
        )
    return _dedupe_models(nodes, "node_id"), id_map


def _legacy_id_or_stable(prefix: str, candidate: str, seed: str) -> str:
    if (
        2 <= len(candidate) <= 64
        and candidate.isascii()
        and candidate[0].isalnum()
        and all(character.isalnum() or character in "._-" for character in candidate)
    ):
        return candidate
    return _stable_id(prefix, seed)


def _dedupe_models(items: list[ContractModel], id_attr: str) -> list[ContractModel]:
    unique: dict[str, ContractModel] = {}
    for item in items:
        item_id = str(getattr(item, id_attr))
        previous = unique.get(item_id)
        if previous is not None and previous != item:
            raise ValueError(f"legacy content contains conflicting id: {item_id}")
        unique.setdefault(item_id, item)
    return list(unique.values())


def _legacy_package_id(lesson_id: str) -> str:
    candidate = f"pkg-{lesson_id}"
    return candidate if len(candidate) <= 64 else _stable_id("pkg", lesson_id)
