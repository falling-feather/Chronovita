from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.sandbox import (
    AdvanceRequest,
    BranchOption,
    PlaythroughSnapshot,
    Scenario,
    advance,
    get_playthrough,
    get_scenario,
    list_branches,
    list_playthroughs,
    list_scenarios,
    new_playthrough,
)

router = APIRouter()


@router.get("/scenarios", response_model=list[Scenario], summary="剧本列表")
async def fetch_scenarios() -> list[Scenario]:
    return list_scenarios()


@router.get("/scenarios/{scenario_id}", response_model=Scenario, summary="剧本详情")
async def fetch_scenario(scenario_id: str) -> Scenario:
    sc = get_scenario(scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return sc


@router.post("/playthroughs", response_model=PlaythroughSnapshot, summary="开始一次推演")
async def create_playthrough(scenario_id: str) -> PlaythroughSnapshot:
    sc = get_scenario(scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return new_playthrough(scenario_id)


@router.get("/playthroughs", response_model=list[PlaythroughSnapshot], summary="推演列表")
async def fetch_playthroughs() -> list[PlaythroughSnapshot]:
    return list_playthroughs()


@router.get("/playthroughs/{playthrough_id}", response_model=PlaythroughSnapshot, summary="推演详情")
async def fetch_playthrough(playthrough_id: str) -> PlaythroughSnapshot:
    snap = get_playthrough(playthrough_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="推演不存在")
    return snap


@router.get("/playthroughs/{playthrough_id}/branches", response_model=list[BranchOption], summary="当前候选分支")
async def fetch_branches(playthrough_id: str) -> list[BranchOption]:
    snap = get_playthrough(playthrough_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="推演不存在")
    sc = get_scenario(snap.scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="剧本不存在")
    return list_branches(sc, snap.current_node_id, snap.state)


@router.post("/playthroughs/{playthrough_id}/advance", response_model=PlaythroughSnapshot, summary="选择分支前进")
async def advance_playthrough(playthrough_id: str, payload: AdvanceRequest) -> PlaythroughSnapshot:
    snap = get_playthrough(playthrough_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="推演不存在")
    try:
        return advance(playthrough_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
