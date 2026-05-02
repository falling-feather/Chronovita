from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.classroom import (
    ClassroomTask,
    CreateClassroomTaskRequest,
    TaskCheckResult,
    create_task,
    delete_task,
    get_task,
    list_tasks,
)
from services.sandbox import get_playthrough, get_scenario, list_playthroughs_by_task

router = APIRouter()


def _check_one(task, snap) -> TaskCheckResult:
    visited = list(snap.history)
    visited_set = set(visited)
    must_hit = [nid for nid in task.must_visit_nodes if nid in visited_set]
    must_miss = [nid for nid in task.must_visit_nodes if nid not in visited_set]
    terminal_id = snap.current_node_id if snap.is_terminal else None
    terminal_accepted = (
        snap.is_terminal
        and (not task.accepted_terminals or snap.current_node_id in task.accepted_terminals)
    )
    if task.recommended_path:
        rec = set(task.recommended_path)
        sc = get_scenario(task.scenario_id)
        edge_lookup = {(e.from_node, e.to_node): e.edge_id for e in (sc.edges if sc else [])}
        traversed_edges = {
            edge_lookup.get((visited[i], visited[i + 1]))
            for i in range(len(visited) - 1)
        }
        traversed_edges.discard(None)
        match = len(rec & traversed_edges) / max(1, len(rec))
    else:
        match = 0.0
    if not snap.is_terminal:
        summary = "推演尚未抵达终局，继续吧。"
    elif terminal_accepted and not must_miss:
        summary = "已圆满达成本任务的全部老师预设。"
    elif terminal_accepted:
        summary = f"已抵达合格终局，但缺漏了 {len(must_miss)} 个必经节点。"
    elif not task.accepted_terminals:
        summary = "已抵达终局，老师未指定合格终局，由学生自评。"
    else:
        summary = "已抵达终局，但不在老师预设的合格终局列表内。"
    return TaskCheckResult(
        task_id=task.task_id,
        playthrough_id=snap.playthrough_id,
        is_terminal=snap.is_terminal,
        terminal_node_id=terminal_id,
        visited_nodes=visited,
        must_visit_hit=must_hit,
        must_visit_miss=must_miss,
        terminal_accepted=terminal_accepted,
        recommended_match_ratio=round(match, 2),
        summary=summary,
    )


@router.get("/tasks", response_model=list[ClassroomTask], summary="课堂任务列表")
async def fetch_tasks() -> list[ClassroomTask]:
    return list_tasks()


@router.post("/tasks", response_model=ClassroomTask, summary="创建课堂任务")
async def create(req: CreateClassroomTaskRequest) -> ClassroomTask:
    sc = get_scenario(req.scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail=f"剧本 {req.scenario_id} 不存在")
    valid_node_ids = {n.node_id for n in sc.nodes}
    bad_must = [nid for nid in req.must_visit_nodes if nid not in valid_node_ids]
    bad_term = [nid for nid in req.accepted_terminals if nid not in valid_node_ids]
    if bad_must or bad_term:
        raise HTTPException(
            status_code=400,
            detail=f"节点 id 不存在：必经 {bad_must}，终局 {bad_term}",
        )
    return create_task(req)


@router.get("/tasks/{task_id}", response_model=ClassroomTask, summary="任务详情")
async def fetch(task_id: str) -> ClassroomTask:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.delete("/tasks/{task_id}", summary="删除任务")
async def remove(task_id: str) -> dict:
    if not delete_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@router.get("/tasks/{task_id}/check", response_model=TaskCheckResult, summary="按推演快照验收任务")
async def check(task_id: str, playthrough_id: str) -> TaskCheckResult:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    snap = get_playthrough(playthrough_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="推演快照不存在")
    if snap.scenario_id != task.scenario_id:
        raise HTTPException(status_code=400, detail="推演剧本与任务剧本不一致")
    return _check_one(task, snap)


class SubmissionItem(BaseModel):
    playthrough_id: str
    student_name: str | None
    is_terminal: bool
    terminal_node_id: str | None
    terminal_accepted: bool
    must_visit_hit_count: int
    must_visit_total: int
    recommended_match_ratio: float
    history: list[str]
    created_at: datetime
    updated_at: datetime
    summary: str


class SubmissionsAggregate(BaseModel):
    task: ClassroomTask
    submissions: list[SubmissionItem]
    node_visit_counts: dict[str, int]
    edge_traverse_counts: dict[str, int]
    terminal_distribution: dict[str, int]
    total_count: int
    accepted_count: int


@router.get(
    "/tasks/{task_id}/submissions",
    response_model=SubmissionsAggregate,
    summary="按任务聚合所有学生推演与验收报告",
)
async def submissions(task_id: str) -> SubmissionsAggregate:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    snaps = list_playthroughs_by_task(task_id)
    sc = get_scenario(task.scenario_id)
    edge_lookup = {(e.from_node, e.to_node): e.edge_id for e in (sc.edges if sc else [])}

    items: list[SubmissionItem] = []
    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    terminal_dist: dict[str, int] = {}
    accepted = 0
    for snap in snaps:
        result = _check_one(task, snap)
        if result.terminal_accepted:
            accepted += 1
        for nid in snap.history:
            node_counts[nid] = node_counts.get(nid, 0) + 1
        for i in range(len(snap.history) - 1):
            eid = edge_lookup.get((snap.history[i], snap.history[i + 1]))
            if eid:
                edge_counts[eid] = edge_counts.get(eid, 0) + 1
        if snap.is_terminal:
            terminal_dist[snap.current_node_id] = terminal_dist.get(snap.current_node_id, 0) + 1
        items.append(
            SubmissionItem(
                playthrough_id=snap.playthrough_id,
                student_name=snap.student_name,
                is_terminal=snap.is_terminal,
                terminal_node_id=result.terminal_node_id,
                terminal_accepted=result.terminal_accepted,
                must_visit_hit_count=len(result.must_visit_hit),
                must_visit_total=len(task.must_visit_nodes),
                recommended_match_ratio=result.recommended_match_ratio,
                history=snap.history,
                created_at=snap.created_at,
                updated_at=snap.updated_at,
                summary=result.summary,
            )
        )
    items.sort(key=lambda x: x.updated_at, reverse=True)
    return SubmissionsAggregate(
        task=task,
        submissions=items,
        node_visit_counts=node_counts,
        edge_traverse_counts=edge_counts,
        terminal_distribution=terminal_dist,
        total_count=len(items),
        accepted_count=accepted,
    )
