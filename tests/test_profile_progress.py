import base64
from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from routers import profile, learning, auth  # noqa: E402
from settings import settings  # noqa: E402
from services import persistence, courses  # noqa: E402
from services.auth import AuthServiceConfig, configure_identity, shutdown_identity  # noqa: E402
from services.auth.store import AuthStoreError  # noqa: E402


class ProfileProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.old_mode = settings.auth_mode
        settings.auth_mode = "accounts"
        persistence.close_engine()
        engine = persistence.init_engine(str(Path(self.temp.name) / "test.db"))
        self.identity = configure_identity(engine, AuthServiceConfig(
            mode="accounts", session_ttl_seconds=3600, bootstrap_username="admin",
            bootstrap_password="Profile test admin password!"))
        self.admin = self.identity.login("admin", "Profile test admin password!", request_id="test")
        for name in ("student.a", "student.b"):
            self.identity.create_user(username=name, password="Student test password!",
                display_name=name, roles=("student",), actor=self.admin.principal, request_id="test")
        self.a = self.identity.login("student.a", "Student test password!", request_id="test")
        self.b = self.identity.login("student.b", "Student test password!", request_id="test")
        app = FastAPI()
        app.include_router(profile.router, prefix="/api/v1/profile")
        app.include_router(learning.router, prefix="/api/v1/learning")
        app.include_router(auth.router, prefix="/api/v1/auth")
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer " + self.a.token}

    def tearDown(self):
        self.client.close()
        shutdown_identity()
        persistence.close_engine()
        settings.auth_mode = self.old_mode
        self.temp.cleanup()

    def test_profile_owns_identity_name_and_revision(self):
        self.assertEqual(self.client.get("/api/v1/profile/").status_code, 401)
        payload = {"display_name": "真实昵称", "bio": "喜欢历史", "expected_revision": 0}
        changed = self.client.put("/api/v1/profile/", headers=self.headers, json=payload)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["revision"], 1)
        me = self.client.get("/api/v1/auth/me", headers=self.headers).json()
        self.assertEqual(me["principal"]["display_name"], "真实昵称")
        other = self.client.get("/api/v1/profile/", headers={"Authorization": "Bearer " + self.b.token}).json()
        self.assertEqual(other["bio"], "")
        self.assertEqual(self.client.put("/api/v1/profile/", headers=self.headers, json=payload).status_code, 409)
        self.assertEqual(self.client.put("/api/v1/profile/", headers=self.headers,
                         json={**payload, "roles": ["admin"]}).status_code, 422)

    def test_profile_rolls_back_with_audit_failure(self):
        with patch.object(self.identity.store, "_append_audit_event", side_effect=AuthStoreError("failed")):
            result = self.client.put("/api/v1/profile/", headers=self.headers,
                json={"display_name": "Not saved", "expected_revision": 0, "bio": "Not saved"})
        self.assertEqual(result.status_code, 503)
        found = self.client.get("/api/v1/profile/", headers=self.headers).json()
        self.assertEqual(found["revision"], 0)
        self.assertEqual(found["display_name"], "student.a")
        self.assertEqual(found["bio"], "")

    def test_account_switch_and_admin_rename_cannot_overwrite_a_stale_form(self):
        wrong_owner = self.client.put("/api/v1/profile/", headers=self.headers, json={
            "display_name": "Wrong", "expected_revision": 0, "expected_user_id": self.b.principal.user_id})
        self.assertEqual(wrong_owner.status_code, 409)
        self.identity.update_user(self.a.principal.user_id, display_name="Admin assigned",
            roles=None, enabled=None, actor=self.admin.principal, request_id="test")
        stale = self.client.put("/api/v1/profile/", headers=self.headers, json={
            "display_name": "Old name", "expected_revision": 0})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client.get("/api/v1/profile/", headers=self.headers).json()["display_name"], "Admin assigned")

    def test_cookie_profile_write_requires_trusted_origin(self):
        session = self.identity.login("student.a", "Student test password!",
            request_id="test", transport="cookie")
        self.client.cookies.set(settings.auth_cookie_name, session.token)
        response = self.client.put("/api/v1/profile/", headers={"Origin": "https://evil.example"},
            json={"display_name": "Do not save", "expected_revision": 0})
        self.assertEqual(response.status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/profile/", headers=self.headers).json()["revision"], 0)

    def test_reading_checksum_only_changes_for_the_affected_lesson(self):
        from services.courses.textbooks import load_textbooks, lesson_reading_checksum
        book = load_textbooks()["C-prequin-state"]
        first = lesson_reading_checksum(book.course_id, book.lessons[0])
        changed = book.model_copy(deep=True)
        changed.lessons[1].body[0] += " 修改"
        self.assertEqual(first, lesson_reading_checksum(changed.course_id, changed.lessons[0]))
        changed.lessons[0].body[0] += " 修改"
        self.assertNotEqual(first, lesson_reading_checksum(changed.course_id, changed.lessons[0]))

    def test_course_search_includes_teacher_people_and_keywords(self):
        from services.courses.textbooks import load_textbooks
        book = load_textbooks()["C-prequin-state"]
        person = next(person for lesson in book.lessons for person in lesson.people)
        keyword = next(keyword for lesson in book.lessons for keyword in lesson.keywords)
        for query in (person.name, keyword.word):
            self.assertIn(book.course_id, [item.id for item in courses.list_courses(q=query)])
        self.assertEqual(courses.list_courses(q="不存在的课程 xyz987654321"), [])

    def test_password_requires_current_and_revokes_sessions(self):
        uri = "/api/v1/profile/password"
        self.assertEqual(self.client.post(uri, headers=self.headers, json={
            "current_password": "wrong", "new_password": "New test password 123!"}).status_code, 422)
        changed = self.client.post(uri, headers=self.headers, json={
            "current_password": "Student test password!", "new_password": "New test password 123!"})
        self.assertEqual(changed.status_code, 204, changed.text)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.headers).status_code, 401)
        self.identity.login("student.a", "New test password 123!", request_id="test")

    def test_avatar_is_validated_and_normalized(self):
        source = BytesIO()
        Image.new("RGB", (512, 400), "red").save(source, format="PNG")
        changed = self.client.put("/api/v1/profile/", headers=self.headers, json={
            "display_name": "Avatar", "expected_revision": 0,
            "avatar_data_url": "data:image/png;base64," + base64.b64encode(source.getvalue()).decode()})
        self.assertEqual(changed.status_code, 200, changed.text)
        data = changed.json()["avatar_data_url"]
        self.assertTrue(data.startswith("data:image/webp;base64,"))
        with Image.open(BytesIO(base64.b64decode(data.split(",")[1]))) as image:
            self.assertLessEqual(max(image.size), 256)
        invalid = self.client.put("/api/v1/profile/", headers=self.headers, json={
            "display_name": "Avatar", "expected_revision": 1, "avatar_data_url": "data:image/svg+xml;base64,AAAA"})
        self.assertEqual(invalid.status_code, 422)

    def test_reading_requires_confirmation_for_the_current_text(self):
        uri = "/api/v1/learning/progress/touch"
        data = {"lesson_id": "L101", "layer": "watch"}
        seen = self.client.post(uri, headers=self.headers, json=data)
        self.assertEqual(seen.status_code, 200, seen.text)
        self.assertEqual(seen.json()["item"]["reading_status"], "reading")
        checksum = courses.get_lesson("L101").teacher_text_checksum
        confirmed = self.client.post(uri, headers=self.headers, json={
            **data, "completed": True, "teacher_text_checksum": checksum})
        self.assertEqual(confirmed.json()["item"]["reading_status"], "completed")
        stale = self.client.post(uri, headers=self.headers, json={
            **data, "completed": True, "teacher_text_checksum": "0" * 64})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client.post(uri, headers=self.headers,
            json={"lesson_id": "L402", "layer": "watch"}).status_code, 404)

    def test_legacy_completion_is_not_current_reading_or_latest_removed_lesson(self):
        uid = self.a.principal.user_id
        for lesson_id, date in [("L101", "2026-01-01T00:00:00+00:00"), ("L402", "2026-01-02T00:00:00+00:00")]:
            persistence.kv_set("lesson_progress", f"{uid}:{lesson_id}", {
                "user_id": uid, "lesson_id": lesson_id, "last_layer": "watch",
                "layers": {"watch": True}, "updated_at": date})
        rows = self.client.get("/api/v1/learning/progress", headers=self.headers).json()
        self.assertEqual(rows["total_lessons"], 46)
        self.assertEqual(rows["items"][0]["reading_status"], "unavailable")
        self.assertEqual(rows["items"][1]["reading_status"], "unverified")
        latest = self.client.get("/api/v1/learning/progress/latest", headers=self.headers).json()
        self.assertEqual(latest["item"]["lesson_id"], "L101")
