from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Literal

if TYPE_CHECKING:
    from services.contracts.v1 import GameSessionV1, ScenarioTemplateV1


ComparisonOperator = Literal["lt", "lte", "eq", "gte", "gt"]


class RuleEvaluationError(ValueError):
    """Raised when a command cannot be evaluated against a valid ruleset."""


class UnknownRuleAction(RuleEvaluationError):
    pass


class RuleActionUnavailable(RuleEvaluationError):
    pass


@dataclass(frozen=True)
class NpcRuleStateV1:
    person_id: str
    attitude: float
    trust: float
    known_fact_refs: tuple[str, ...] = ()
    updated_turn: int = 0


@dataclass(frozen=True)
class RuleSnapshotV1:
    state: tuple[tuple[str, float], ...]
    npcs: tuple[NpcRuleStateV1, ...]
    current_node_id: str | None
    triggered_once_event_ids: tuple[str, ...] = ()
    triggered_event_ids: tuple[str, ...] = ()

    def state_dict(self) -> dict[str, float]:
        return dict(self.state)

    def npc_dict(self) -> dict[str, NpcRuleStateV1]:
        return {item.person_id: item for item in self.npcs}


@dataclass(frozen=True)
class RuleStateChangeV1:
    variable_id: str
    before: float
    after: float

    @property
    def delta(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class RuleNpcChangeV1:
    person_id: str
    attitude_before: float
    attitude_after: float
    trust_before: float
    trust_after: float
    revealed_fact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleTurnResultV1:
    action_id: str
    snapshot: RuleSnapshotV1
    state_changes: tuple[RuleStateChangeV1, ...]
    npc_changes: tuple[RuleNpcChangeV1, ...]
    triggered_event_ids: tuple[str, ...]
    ending_id: str | None
    available_action_ids: tuple[str, ...]
    fact_refs: tuple[str, ...]
    narrative_parts: tuple[str, ...]
    turn_limit_reached: bool


def initial_rule_snapshot(scenario: ScenarioTemplateV1) -> RuleSnapshotV1:
    return RuleSnapshotV1(
        state=tuple((item.variable_id, float(item.initial)) for item in scenario.variables),
        npcs=tuple(
            NpcRuleStateV1(
                person_id=item.person_id,
                attitude=float(item.initial_attitude),
                trust=float(item.initial_trust),
            )
            for item in scenario.npcs
        ),
        current_node_id=scenario.start_node_id,
    )


def rule_snapshot_from_session(
    scenario: ScenarioTemplateV1,
    session: GameSessionV1,
) -> RuleSnapshotV1:
    state_keys = {item.variable_id for item in scenario.variables}
    if set(session.current_state) != state_keys:
        raise RuleEvaluationError("session state does not match scenario variables")

    session_npcs = {item.person_id: item for item in session.npc_states}
    scenario_npc_ids = {item.person_id for item in scenario.npcs}
    if set(session_npcs) != scenario_npc_ids:
        raise RuleEvaluationError("session NPC state does not match scenario NPCs")

    once_ids = {
        item.event_id
        for item in scenario.event_rules
        if item.once
    }
    return RuleSnapshotV1(
        state=tuple(
            (item.variable_id, float(session.current_state[item.variable_id]))
            for item in scenario.variables
        ),
        npcs=tuple(
            NpcRuleStateV1(
                person_id=item.person_id,
                attitude=float(session_npcs[item.person_id].attitude),
                trust=float(session_npcs[item.person_id].trust),
                known_fact_refs=tuple(session_npcs[item.person_id].known_fact_refs),
                updated_turn=session_npcs[item.person_id].updated_turn,
            )
            for item in scenario.npcs
        ),
        current_node_id=session.current_node_id,
        triggered_once_event_ids=tuple(
            event_id
            for event_id in session.triggered_event_ids
            if event_id in once_ids
        ),
        triggered_event_ids=tuple(session.triggered_event_ids),
    )


def available_rule_action_ids(
    scenario: ScenarioTemplateV1,
    snapshot: RuleSnapshotV1,
    turn_no: int,
) -> tuple[str, ...]:
    actions = {item.action_id: item for item in scenario.action_rules}
    if snapshot.current_node_id is None:
        candidates = tuple(item.action_id for item in scenario.action_rules)
    else:
        nodes = {item.node_id: item for item in scenario.nodes}
        node = nodes.get(snapshot.current_node_id)
        if node is None:
            raise RuleEvaluationError(
                f"unknown current node {snapshot.current_node_id}"
            )
        candidates = tuple(node.action_ids)

    state = snapshot.state_dict()
    npcs = _mutable_npcs(snapshot)
    return tuple(
        action_id
        for action_id in candidates
        if _conditions_match(
            actions[action_id].available_when,
            "all",
            state,
            npcs,
            turn_no,
        )
    )


def select_rule_ending_id(
    scenario: ScenarioTemplateV1,
    snapshot: RuleSnapshotV1,
    turn_no: int,
) -> str | None:
    if snapshot.current_node_id is not None:
        nodes = {item.node_id: item for item in scenario.nodes}
        node = nodes.get(snapshot.current_node_id)
        if node is None:
            raise RuleEvaluationError(
                f"unknown current node {snapshot.current_node_id}"
            )
        if node.ending_id is not None:
            return node.ending_id

    state = snapshot.state_dict()
    npcs = _mutable_npcs(snapshot)
    matching = sorted(
        (
            ending
            for ending in scenario.ending_rules
            if _conditions_match(
                ending.conditions,
                ending.match,
                state,
                npcs,
                turn_no,
            )
        ),
        key=lambda item: (item.priority, item.ending_id),
    )
    return matching[0].ending_id if matching else None


def evaluate_rule_action(
    scenario: ScenarioTemplateV1,
    snapshot: RuleSnapshotV1,
    action_id: str,
    turn_no: int,
) -> RuleTurnResultV1:
    if turn_no < 1:
        raise RuleEvaluationError("turn_no must be at least 1")

    actions = {item.action_id: item for item in scenario.action_rules}
    action = actions.get(action_id)
    if action is None:
        raise UnknownRuleAction(f"unknown action {action_id}")

    if snapshot.current_node_id is not None:
        nodes = {item.node_id: item for item in scenario.nodes}
        node = nodes.get(snapshot.current_node_id)
        if node is None:
            raise RuleEvaluationError(
                f"unknown current node {snapshot.current_node_id}"
            )
        if action_id not in node.action_ids:
            raise RuleActionUnavailable(
                f"action is not available from node {snapshot.current_node_id}"
            )

    state_before = snapshot.state_dict()
    state = dict(state_before)
    npcs_before = snapshot.npc_dict()
    npcs = _mutable_npcs(snapshot)
    if not _conditions_match(
        action.available_when,
        "all",
        state,
        npcs,
        turn_no,
    ):
        raise RuleActionUnavailable("action conditions are not satisfied")

    ranges = {
        item.variable_id: (float(item.minimum), float(item.maximum))
        for item in scenario.variables
    }
    touched_npcs: set[str] = set()
    revealed_by_person: dict[str, list[str]] = {}
    _apply_effects(
        action.effects,
        state,
        npcs,
        ranges,
        touched_npcs,
        revealed_by_person,
    )

    triggered_once = set(snapshot.triggered_once_event_ids)
    matching_events = tuple(
        event
        for event in sorted(
            scenario.event_rules,
            key=lambda item: (item.priority, item.event_id),
        )
        if not (event.once and event.event_id in triggered_once)
        and _conditions_match(
            event.trigger,
            event.match,
            state,
            npcs,
            turn_no,
        )
    )
    for event in matching_events:
        _apply_effects(
            event.effects,
            state,
            npcs,
            ranges,
            touched_npcs,
            revealed_by_person,
        )
        if event.once:
            triggered_once.add(event.event_id)

    current_node_id = snapshot.current_node_id
    if current_node_id is not None and action.next_node_id is not None:
        current_node_id = action.next_node_id

    event_ids = tuple(item.event_id for item in matching_events)
    triggered_history = _stable_unique(
        (*snapshot.triggered_event_ids, *event_ids)
    )
    next_snapshot = RuleSnapshotV1(
        state=tuple(
            (item.variable_id, float(state[item.variable_id]))
            for item in scenario.variables
        ),
        npcs=tuple(
            NpcRuleStateV1(
                person_id=item.person_id,
                attitude=float(npcs[item.person_id]["attitude"]),
                trust=float(npcs[item.person_id]["trust"]),
                known_fact_refs=tuple(npcs[item.person_id]["known_fact_refs"]),
                updated_turn=(
                    turn_no
                    if item.person_id in touched_npcs
                    else int(npcs[item.person_id]["updated_turn"])
                ),
            )
            for item in scenario.npcs
        ),
        current_node_id=current_node_id,
        triggered_once_event_ids=tuple(
            item.event_id
            for item in scenario.event_rules
            if item.event_id in triggered_once
        ),
        triggered_event_ids=triggered_history,
    )
    ending_id = select_rule_ending_id(scenario, next_snapshot, turn_no)
    available = (
        available_rule_action_ids(scenario, next_snapshot, turn_no + 1)
        if ending_id is None and turn_no < scenario.max_turns
        else ()
    )

    state_changes = tuple(
        RuleStateChangeV1(
            variable_id=item.variable_id,
            before=float(state_before[item.variable_id]),
            after=float(state[item.variable_id]),
        )
        for item in scenario.variables
        if float(state_before[item.variable_id]) != float(state[item.variable_id])
    )
    npc_changes = tuple(
        RuleNpcChangeV1(
            person_id=item.person_id,
            attitude_before=float(npcs_before[item.person_id].attitude),
            attitude_after=float(npcs[item.person_id]["attitude"]),
            trust_before=float(npcs_before[item.person_id].trust),
            trust_after=float(npcs[item.person_id]["trust"]),
            revealed_fact_refs=tuple(revealed_by_person.get(item.person_id, ())),
        )
        for item in scenario.npcs
        if item.person_id in touched_npcs
    )

    ending = next(
        (item for item in scenario.ending_rules if item.ending_id == ending_id),
        None,
    )
    fact_refs = _stable_unique(
        (
            *action.fact_refs,
            *(ref for event in matching_events for ref in event.fact_refs),
            *((ending.fact_refs if ending is not None else ())),
        )
    )
    narrative_parts = tuple(
        text
        for text in (
            action.feedback,
            *(event.narrative for event in matching_events),
            (ending.summary if ending is not None else ""),
        )
        if text
    )
    return RuleTurnResultV1(
        action_id=action_id,
        snapshot=next_snapshot,
        state_changes=state_changes,
        npc_changes=npc_changes,
        triggered_event_ids=event_ids,
        ending_id=ending_id,
        available_action_ids=available,
        fact_refs=fact_refs,
        narrative_parts=narrative_parts,
        turn_limit_reached=turn_no >= scenario.max_turns,
    )


def render_rule_narrative(
    scenario: ScenarioTemplateV1,
    result: RuleTurnResultV1,
) -> str:
    narrative = "\n\n".join(result.narrative_parts)
    if narrative:
        return narrative
    action = next(
        item
        for item in scenario.action_rules
        if item.action_id == result.action_id
    )
    return f"已执行：{action.label}"


def _mutable_npcs(snapshot: RuleSnapshotV1) -> dict[str, dict[str, object]]:
    return {
        item.person_id: {
            "attitude": float(item.attitude),
            "trust": float(item.trust),
            "known_fact_refs": list(item.known_fact_refs),
            "updated_turn": item.updated_turn,
        }
        for item in snapshot.npcs
    }


def _apply_effects(
    effects,
    state: dict[str, float],
    npcs: dict[str, dict[str, object]],
    ranges: dict[str, tuple[float, float]],
    touched_npcs: set[str],
    revealed_by_person: dict[str, list[str]],
) -> None:
    for effect in effects:
        if effect.kind == "state":
            current = state[effect.variable_id]
            value = effect.value if effect.operation == "set" else current + effect.value
            minimum, maximum = ranges[effect.variable_id]
            state[effect.variable_id] = max(minimum, min(maximum, float(value)))
            continue

        npc = npcs[effect.person_id]
        npc["attitude"] = max(
            -100.0,
            min(100.0, float(npc["attitude"]) + effect.attitude_delta),
        )
        npc["trust"] = max(
            -100.0,
            min(100.0, float(npc["trust"]) + effect.trust_delta),
        )
        touched_npcs.add(effect.person_id)
        revealed = revealed_by_person.setdefault(effect.person_id, [])
        known = npc["known_fact_refs"]
        if not isinstance(known, list):
            raise RuleEvaluationError("NPC known facts must be a list")
        for fact_ref in effect.reveal_fact_refs:
            if fact_ref not in revealed:
                revealed.append(fact_ref)
            if fact_ref not in known:
                known.append(fact_ref)


def _conditions_match(
    conditions,
    match: Literal["all", "any"],
    state: dict[str, float],
    npcs: dict[str, dict[str, object]],
    turn_no: int,
) -> bool:
    results = [
        _condition_matches(condition, state, npcs, turn_no)
        for condition in conditions
    ]
    return any(results) if match == "any" else all(results)


def _condition_matches(
    condition,
    state: dict[str, float],
    npcs: dict[str, dict[str, object]],
    turn_no: int,
) -> bool:
    if condition.kind == "state":
        actual = state[condition.variable_id]
    elif condition.kind == "npc":
        actual = float(npcs[condition.person_id][condition.field])
    else:
        actual = turn_no
    return _compare_values(float(actual), condition.operator, float(condition.value))


def _compare_values(
    actual: float,
    operator: ComparisonOperator,
    expected: float,
) -> bool:
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "eq":
        return _numbers_match(actual, expected)
    if operator == "gte":
        return actual >= expected
    return actual > expected


def _stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _numbers_match(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9
