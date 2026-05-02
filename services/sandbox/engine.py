from __future__ import annotations

import uuid
from datetime import datetime
from functools import lru_cache

from services import persistence

from .models import (
    AdvanceRequest,
    BranchOption,
    DagEdge,
    DagNode,
    PlaythroughSnapshot,
    Scenario,
    StateVar,
)
from .scenarios import get_scenario


def _layout(scenario: Scenario) -> tuple[list[StateVar], int]:
    layout: list[StateVar] = list(scenario.state_vars)
    total_bits = sum(v.bits for v in layout)
    if total_bits > 60:
        raise ValueError("状态位宽超出 60，超出 lru_cache 安全范围")
    return layout, total_bits


def encode_state(scenario: Scenario, state: dict[str, int]) -> int:
    layout, _ = _layout(scenario)
    bits = 0
    shift = 0
    for var in layout:
        value = state.get(var.key, var.initial) & var.max_value()
        bits |= value << shift
        shift += var.bits
    return bits


def decode_state(scenario: Scenario, bits: int) -> dict[str, int]:
    layout, _ = _layout(scenario)
    out: dict[str, int] = {}
    shift = 0
    for var in layout:
        mask = var.max_value()
        out[var.key] = (bits >> shift) & mask
        shift += var.bits
    return out


def _eval_condition(state: dict[str, int], var: str, op: str, value: int) -> bool:
    cur = state.get(var, 0)
    return {
        "eq": cur == value,
        "ne": cur != value,
        "ge": cur >= value,
        "le": cur <= value,
        "gt": cur > value,
        "lt": cur < value,
    }[op]


def _apply_effects(scenario: Scenario, state: dict[str, int], edge: DagEdge) -> dict[str, int]:
    layout, _ = _layout(scenario)
    var_map = {v.key: v for v in layout}
    new_state = dict(state)
    for eff in edge.effects:
        var = var_map.get(eff.var)
        if var is None:
            continue
        if eff.op == "set":
            new_state[eff.var] = eff.value & var.max_value()
        elif eff.op == "inc":
            new_state[eff.var] = min(new_state.get(eff.var, 0) + eff.value, var.max_value())
        elif eff.op == "dec":
            new_state[eff.var] = max(new_state.get(eff.var, 0) - eff.value, 0)
    return new_state


def _node_map(scenario: Scenario) -> dict[str, DagNode]:
    return {n.node_id: n for n in scenario.nodes}


@lru_cache(maxsize=4096)
def _branches_cached(
    scenario_id: str, node_id: str, state_bits: int
) -> tuple[BranchOption, ...]:
    scenario = get_scenario(scenario_id)
    if scenario is None:
        return ()
    state = decode_state(scenario, state_bits)
    nodes = _node_map(scenario)
    out: list[BranchOption] = []
    for edge in scenario.edges:
        if edge.from_node != node_id:
            continue
        if not all(_eval_condition(state, c.var, c.op, c.value) for c in edge.conditions):
            continue
        target = nodes.get(edge.to_node)
        if target is None:
            continue
        new_state = _apply_effects(scenario, state, edge)
        out.append(
            BranchOption(
                edge_id=edge.edge_id,
                label=edge.label,
                target_node_id=target.node_id,
                target_title=target.title,
                preview_narrative=edge.fallback_narrative or target.narrative[:60],
                state_after=new_state,
            )
        )
    return tuple(out)


def list_branches(scenario: Scenario, node_id: str, state: dict[str, int]) -> list[BranchOption]:
    bits = encode_state(scenario, state)
    return list(_branches_cached(scenario.scenario_id, node_id, bits))


_PLAYTHROUGHS: dict[str, PlaythroughSnapshot] = {}


def new_playthrough(scenario_id: str) -> PlaythroughSnapshot:
    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(scenario_id)
    nodes = _node_map(scenario)
    start = nodes[scenario.start_node]
    state = {v.key: v.initial for v in scenario.state_vars}
    snap = PlaythroughSnapshot(
        playthrough_id=f"play_{uuid.uuid4().hex[:10]}",
        scenario_id=scenario_id,
        current_node_id=start.node_id,
        current_node_title=start.title,
        current_narrative=start.narrative,
        state=state,
        state_bits=encode_state(scenario, state),
        history=[start.node_id],
        is_terminal=start.is_terminal,
    )
    _PLAYTHROUGHS[snap.playthrough_id] = snap
    persistence.save_playthrough(snap)
    return snap


def advance(playthrough_id: str, req: AdvanceRequest) -> PlaythroughSnapshot:
    snap = _PLAYTHROUGHS.get(playthrough_id)
    if snap is None:
        raise KeyError(playthrough_id)
    if snap.is_terminal:
        return snap
    scenario = get_scenario(snap.scenario_id)
    if scenario is None:
        raise KeyError(snap.scenario_id)
    nodes = _node_map(scenario)
    branches = list_branches(scenario, snap.current_node_id, snap.state)
    chosen = next((b for b in branches if b.edge_id == req.edge_id), None)
    if chosen is None:
        raise ValueError(f"边 {req.edge_id} 在当前节点不可用或不满足条件")
    target = nodes[chosen.target_node_id]
    snap.current_node_id = target.node_id
    snap.current_node_title = target.title
    snap.current_narrative = target.narrative
    snap.state = chosen.state_after
    snap.state_bits = encode_state(scenario, chosen.state_after)
    snap.history.append(target.node_id)
    snap.is_terminal = target.is_terminal
    snap.updated_at = datetime.utcnow()
    persistence.save_playthrough(snap)
    return snap


def get_playthrough(playthrough_id: str) -> PlaythroughSnapshot | None:
    return _PLAYTHROUGHS.get(playthrough_id)


def list_playthroughs() -> list[PlaythroughSnapshot]:
    return list(_PLAYTHROUGHS.values())


def hydrate_from_db() -> int:
    count = 0
    for raw in persistence.load_all_playthroughs():
        try:
            snap = PlaythroughSnapshot.model_validate(raw)
        except Exception:
            continue
        _PLAYTHROUGHS[snap.playthrough_id] = snap
        count += 1
    return count
