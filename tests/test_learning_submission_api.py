from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import auth as auth_router
from routers import learning as learning_router
from routers import practice as practice_router
from settings import settings
from services import persistence
from services.auth import AuthServiceConfig, configure_identity, get_identity, shutdown_identity
from services.learning_assets import (
    configure_learning_assets,
    learning_submissions_table,
    shutdown_learning_assets,
)


class LearningSubmissionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-learning-submission-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.previous = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_session_idle_timeout_seconds": settings.auth_session_idle_timeout_seconds,
            "auth_session_absolute_ttl_seconds": settings.auth_session_absolute_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3_600
        settings.auth_session_idle_timeout_seconds = 3_600
        settings.auth_session_absolute_ttl_seconds = 3_600
        settings.auth_cookie_name = "chronovita_learning_submission_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        database_path = self.tmp_root / "chronovita.db"
        persistence.close_engine()

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            engine = persistence.init_engine(str(database_path))
            self.engine = engine
            configure_identity(
                engine,
                AuthServiceConfig(
                    mode="accounts",
                    session_ttl_seconds=settings.auth_session_ttl_seconds,
                    session_idle_timeout_seconds=(
                        settings.auth_session_idle_timeout_seconds
                    ),
                    session_absolute_ttl_seconds=(
                        settings.auth_session_absolute_ttl_seconds
                    ),
                    bootstrap_username=settings.auth_bootstrap_username,
                    bootstrap_password=settings.auth_bootstrap_password,
                    bootstrap_display_name=settings.auth_bootstrap_display_name,
                ),
            )
            configure_learning_assets(engine)
            try:
                yield
            finally:
                shutdown_learning_assets()
                shutdown_identity()
                persistence.close_engine()

        app = FastAPI(lifespan=lifespan)
        app.include_router(auth_router.router, prefix="/api/v1/auth")
        app.include_router(learning_router.router, prefix="/api/v1/learning")
        app.include_router(practice_router.router, prefix="/api/v1/practice")
        self.client = TestClient(app)
        self.client.__enter__()

        self.admin_headers = self._login_headers("root.admin", "Root password 123!")
        self.student_a = self._create_user(
            "student.a",
            "Student A password 123!",
            "学生甲",
            ["student"],
        )
        self.student_b = self._create_user(
            "student.b",
            "Student B password 123!",
            "学生乙",
            ["student"],
        )
        self.teacher = self._create_user(
            "teacher.a",
            "Teacher A password 123!",
            "张老师",
            ["teacher"],
        )
        self.reviewer = self._create_user(
            "reviewer.a",
            "Reviewer A password 123!",
            "审校员",
            ["reviewer"],
        )
        self.student_a_headers = self._login_headers(
            "student.a",
            "Student A password 123!",
        )
        self.student_b_headers = self._login_headers(
            "student.b",
            "Student B password 123!",
        )
        self.teacher_headers = self._login_headers(
            "teacher.a",
            "Teacher A password 123!",
        )
        self.reviewer_headers = self._login_headers(
            "reviewer.a",
            "Reviewer A password 123!",
        )

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for key, value in self.previous.items():
            setattr(settings, key, value)
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_explicit_submission_versions_owner_scope_and_canvas_snapshot(self):
        unauthenticated = self.client.post(
            "/api/v1/learning/submissions",
            json=self._submission_payload("submit-l101-a"),
        )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)

        mismatched = self._submission_payload("submit-mismatch")
        mismatched["course_id"] = "C-prequin-thought"
        response = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=mismatched,
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "lesson_course_mismatch")

        saved_canvas = self.client.put(
            "/api/v1/practice/canvas/L101",
            headers=self.student_a_headers,
            json={
                "expected_revision": 0,
                "nodes": [{"id": "student-a-node", "data": {"label": "疏导"}}],
                "edges": [],
            },
        )
        self.assertEqual(saved_canvas.status_code, 200, saved_canvas.text)

        payload = self._submission_payload("submit-l101-a")
        first = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=payload,
        )
        self.assertEqual(first.status_code, 201, first.text)
        first_body = first.json()
        submission = first_body["submission"]
        self.assertFalse(first_body["reused"])
        self.assertEqual(submission["student_id"], self.student_a["user_id"])
        self.assertEqual(submission["version"], 1)
        self.assertTrue(submission["canvas"]["found"])
        self.assertEqual(submission["canvas"]["revision"], 1)
        self.assertEqual(submission["canvas"]["nodes"][0]["id"], "student-a-node")
        self.assertEqual(len(submission["checksum"]), 64)

        replay = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=payload,
        )
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["reused"])
        self.assertEqual(
            replay.json()["submission"]["submission_id"],
            submission["submission_id"],
        )

        conflicting = dict(payload)
        conflicting["body_markdown"] = "同一个客户端编号不能覆盖新正文。"
        response = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=conflicting,
        )
        self.assertEqual(response.status_code, 409, response.text)

        second = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=self._submission_payload("submit-l101-b", title="第二次整理"),
        )
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["submission"]["version"], 2)

        owner_list = self.client.get(
            "/api/v1/learning/submissions?lesson_id=L101",
            headers=self.student_a_headers,
        )
        self.assertEqual(owner_list.status_code, 200, owner_list.text)
        self.assertEqual([item["version"] for item in owner_list.json()["items"]], [2, 1])
        self.assertEqual(owner_list.json()["items"][0]["student_display_name"], "学生甲")

        other_owner = self.client.get(
            f"/api/v1/learning/submissions/{submission['submission_id']}",
            headers=self.student_b_headers,
        )
        self.assertEqual(other_owner.status_code, 404, other_owner.text)
        other_list = self.client.get(
            "/api/v1/learning/submissions",
            headers=self.student_b_headers,
        )
        self.assertEqual(other_list.json()["items"], [])

    def test_teacher_feedback_is_append_only_and_visible_to_student(self):
        created = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=self._submission_payload("submit-feedback-a"),
        )
        self.assertEqual(created.status_code, 201, created.text)
        submission_id = created.json()["submission"]["submission_id"]

        denied_student = self.client.get(
            "/api/v1/learning/review/submissions",
            headers=self.student_a_headers,
        )
        denied_reviewer = self.client.get(
            "/api/v1/learning/review/submissions",
            headers=self.reviewer_headers,
        )
        self.assertEqual(denied_student.status_code, 403, denied_student.text)
        self.assertEqual(denied_reviewer.status_code, 403, denied_reviewer.text)

        queue = self.client.get(
            "/api/v1/learning/review/submissions?course_id=C-prequin-state",
            headers=self.teacher_headers,
        )
        self.assertEqual(queue.status_code, 200, queue.text)
        self.assertEqual(len(queue.json()["items"]), 1)
        self.assertEqual(queue.json()["items"][0]["student_username"], "student.a")

        first_payload = {
            "schema_version": "learning-feedback-request/v1",
            "client_feedback_id": "feedback-a-1",
            "completion_status": "changes_requested",
            "comment": "请把疏导路线与聚落协作的关系再写具体一些。",
        }
        first = self.client.post(
            f"/api/v1/learning/review/submissions/{submission_id}/feedback",
            headers=self.teacher_headers,
            json=first_payload,
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["feedback"]["sequence"], 1)
        self.assertEqual(first.json()["feedback"]["teacher_display_name"], "张老师")

        replay = self.client.post(
            f"/api/v1/learning/review/submissions/{submission_id}/feedback",
            headers=self.teacher_headers,
            json=first_payload,
        )
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["reused"])

        conflicting = dict(first_payload)
        conflicting["comment"] = "试图覆盖原反馈。"
        response = self.client.post(
            f"/api/v1/learning/review/submissions/{submission_id}/feedback",
            headers=self.teacher_headers,
            json=conflicting,
        )
        self.assertEqual(response.status_code, 409, response.text)

        denied_feedback = self.client.post(
            f"/api/v1/learning/review/submissions/{submission_id}/feedback",
            headers=self.reviewer_headers,
            json={
                **first_payload,
                "client_feedback_id": "feedback-reviewer-denied",
            },
        )
        self.assertEqual(denied_feedback.status_code, 403, denied_feedback.text)

        completed = self.client.post(
            f"/api/v1/learning/review/submissions/{submission_id}/feedback",
            headers=self.teacher_headers,
            json={
                **first_payload,
                "client_feedback_id": "feedback-a-2",
                "completion_status": "completed",
                "comment": "论证已经补全，本课成果完成。",
            },
        )
        self.assertEqual(completed.status_code, 201, completed.text)
        self.assertEqual(completed.json()["feedback"]["sequence"], 2)

        student_detail = self.client.get(
            f"/api/v1/learning/submissions/{submission_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(student_detail.status_code, 200, student_detail.text)
        self.assertEqual(
            [item["completion_status"] for item in student_detail.json()["feedback"]],
            ["changes_requested", "completed"],
        )
        queue = self.client.get(
            "/api/v1/learning/review/submissions",
            headers=self.teacher_headers,
        )
        self.assertEqual(
            queue.json()["items"][0]["latest_feedback"]["completion_status"],
            "completed",
        )

        actions = [item.action for item in get_identity().list_audit(limit=100)]
        self.assertIn("student.submission.create", actions)
        self.assertIn("student.submission.list", actions)
        self.assertIn("student.submission.feedback", actions)

    def test_tampered_submission_fails_closed(self):
        created = self.client.post(
            "/api/v1/learning/submissions",
            headers=self.student_a_headers,
            json=self._submission_payload("submit-tamper-a"),
        )
        self.assertEqual(created.status_code, 201, created.text)
        submission_id = created.json()["submission"]["submission_id"]
        with self.engine.begin() as connection:
            raw = connection.execute(
                select(learning_submissions_table.c.data).where(
                    learning_submissions_table.c.submission_id == submission_id
                )
            ).scalar_one()
            payload = json.loads(raw)
            payload["title"] = "被篡改的标题"
            connection.execute(
                update(learning_submissions_table)
                .where(learning_submissions_table.c.submission_id == submission_id)
                .values(data=json.dumps(payload, ensure_ascii=False))
            )

        response = self.client.get(
            f"/api/v1/learning/submissions/{submission_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "learning_submission_integrity_error",
        )

    def test_legacy_local_student_cannot_create_orphaned_submission(self):
        settings.auth_mode = "legacy-local"
        try:
            response = self.client.post(
                "/api/v1/learning/submissions",
                json=self._submission_payload("submit-legacy-local"),
            )
        finally:
            settings.auth_mode = "accounts"

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "accounts_mode_required")

    def _create_user(
        self,
        username: str,
        password: str,
        display_name: str,
        roles: list[str],
    ) -> dict:
        response = self.client.post(
            "/api/v1/auth/users",
            headers=self.admin_headers,
            json={
                "username": username,
                "password": password,
                "display_name": display_name,
                "roles": roles,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _login_headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/token",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.cookies.clear()
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    @staticmethod
    def _submission_payload(
        client_submission_id: str,
        *,
        title: str = "大禹治水学习书案",
    ) -> dict:
        return {
            "schema_version": "learning-submission-request/v1",
            "client_submission_id": client_submission_id,
            "course_id": "C-prequin-state",
            "lesson_id": "L101",
            "title": title,
            "body_markdown": "## 我的判断\n疏导与协作共同影响治水结果。",
            "sticky_notes": [
                {"note_id": "note-1", "body": "比较堵与疏的代价", "color": "ochre"}
            ],
            "drawing_strokes": [
                {
                    "stroke_id": "stroke-1",
                    "color": "#24302f",
                    "width": 3,
                    "mode": "ink",
                    "points": [{"x": 0.1, "y": 0.2}, {"x": 0.4, "y": 0.6}],
                }
            ],
            "learning_events": [
                {
                    "event_id": "event-1",
                    "kind": "keyword_opened",
                    "title": "查看关键词：疏导",
                    "summary": "让水沿河道有序下泄。",
                    "metadata": {"keyword": "疏导"},
                    "occurred_at": "2026-08-24T00:00:00Z",
                }
            ],
            "local_draft_updated_at": "2026-08-24T00:30:00Z",
        }


if __name__ == "__main__":
    unittest.main()
