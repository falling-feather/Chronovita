from __future__ import annotations

import uuid

from services import persistence

from .models import ClassroomTask, CreateClassroomTaskRequest


_TASKS: dict[str, ClassroomTask] = {}


def list_tasks() -> list[ClassroomTask]:
    return list(_TASKS.values())


def get_task(task_id: str) -> ClassroomTask | None:
    return _TASKS.get(task_id)


def create_task(req: CreateClassroomTaskRequest) -> ClassroomTask:
    task = ClassroomTask(
        task_id=f"task_{uuid.uuid4().hex[:10]}",
        title=req.title,
        scenario_id=req.scenario_id,
        teacher_notes=req.teacher_notes,
        preset_state=req.preset_state,
        must_visit_nodes=req.must_visit_nodes,
        accepted_terminals=req.accepted_terminals,
        recommended_path=req.recommended_path,
    )
    _TASKS[task.task_id] = task
    persistence.save_task(task)
    return task


def delete_task(task_id: str) -> bool:
    removed = _TASKS.pop(task_id, None)
    if removed is None:
        return False
    persistence.delete_task(task_id)
    return True


def hydrate_from_db() -> int:
    count = 0
    for raw in persistence.load_all_tasks():
        try:
            task = ClassroomTask.model_validate(raw)
        except Exception:
            continue
        _TASKS[task.task_id] = task
        count += 1
    return count
