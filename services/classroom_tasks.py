"""One local classroom's teacher tasks; private student drafts never enter this store."""
from datetime import datetime, timezone

from services import persistence
from services.contracts.classroom_v1 import ClassroomTaskRequestV1, ClassroomTaskV1
from services.contracts.learning_v1 import canonical_checksum
from services.courses.textbooks import reading_lesson_index

CURRENT_NAMESPACE = "classroom_tasks"
HISTORY_NAMESPACE = "classroom_task_revisions"


class ClassroomTaskConflict(ValueError):
    pass


def load_task(task_id: str, checksum: str | None = None) -> ClassroomTaskV1:
    if checksum is None:
        pointer = persistence.kv_get(CURRENT_NAMESPACE, task_id)
        if pointer is None:
            raise KeyError(task_id)
        checksum = pointer['checksum']
    payload = persistence.kv_get(HISTORY_NAMESPACE, f"{task_id}/{checksum}")
    if payload is None:
        raise KeyError(task_id)
    task = ClassroomTaskV1.model_validate(payload)
    if task.task_id != task_id or task.checksum != checksum:
        raise ValueError("classroom task identity mismatch")
    return task


def list_tasks(course_id: str | None = None, lesson_id: str | None = None) -> list[ClassroomTaskV1]:
    tasks = [load_task(pointer['task_id'], pointer['checksum']) for pointer in persistence.kv_list(CURRENT_NAMESPACE)]
    return sorted((task for task in tasks if (not course_id or task.course_id == course_id)
                   and (not lesson_id or task.lesson_id == lesson_id)), key=lambda item: item.updated_at, reverse=True)[:100]


def save_task(request: ClassroomTaskRequestV1, *, teacher_id: str, teacher_display_name: str) -> ClassroomTaskV1:
    index = reading_lesson_index()
    lesson = index.get(request.lesson_id)
    if lesson is None or lesson.course_id != request.course_id:
        raise ValueError("任务课时不属于所选课程")
    task_id = 'task-' + canonical_checksum([teacher_id, request.client_task_id])[:24]
    pointer = persistence.kv_get(CURRENT_NAMESPACE, task_id)
    previous = load_task(task_id) if pointer else None
    fields = request.model_dump(mode="json", exclude={"expected_checksum"})
    if previous and all(getattr(previous, key) == value for key, value in fields.items()) and previous.teacher_text_checksum == lesson.teacher_text_checksum:
        return previous
    if (previous.checksum if previous else None) != request.expected_checksum:
        raise ClassroomTaskConflict("任务已更新，请重新读取后保存")
    now = datetime.now(timezone.utc)
    payload = dict(fields, schema_version="classroom-task/v1", task_id=task_id, teacher_id=teacher_id,
                   teacher_display_name=teacher_display_name, revision=(previous.revision + 1 if previous else 1),
                   teacher_text_checksum=lesson.teacher_text_checksum, created_at=(previous.created_at if previous else now), updated_at=now)
    # Validate datetimes before signing, preserving canonical JSON serialization.
    provisional = ClassroomTaskV1.model_construct(**payload, checksum="0" * 64)
    payload = provisional.model_dump(mode="json", exclude={"checksum"})
    payload['checksum'] = canonical_checksum(payload)
    task = ClassroomTaskV1.model_validate(payload)
    revision_key = f"{task_id}/{task.checksum}"
    if not persistence.kv_compare_and_set(HISTORY_NAMESPACE, revision_key, None, task.model_dump(mode="json")):
        existing = load_task(task_id, task.checksum)
        if existing != task:
            raise ClassroomTaskConflict("不可覆盖不同的任务版本")
    updated = {"task_id": task_id, "checksum": task.checksum}
    if not persistence.kv_compare_and_set(CURRENT_NAMESPACE, task_id, pointer, updated):
        raise ClassroomTaskConflict("任务同时被更新，请重新读取后保存")
    return task


def validate_task_submission(task: ClassroomTaskV1, *, course_id: str, lesson_id: str) -> None:
    saved = load_task(task.task_id, task.checksum)
    if saved != task or saved.course_id != course_id or saved.lesson_id != lesson_id:
        raise ValueError("成果中的任务身份不匹配")
    current = load_task(task.task_id)
    if task.status != 'open' or current.status != 'open' or current.checksum != task.checksum:
        raise ValueError("任务已关闭或修订，请重新读取当前任务；本机笔记不会丢失")
    lesson = reading_lesson_index().get(lesson_id)
    if not lesson or task.teacher_text_checksum != lesson.teacher_text_checksum:
        raise ValueError("任务对应课文已更新，请重新确认当前教师任务")
