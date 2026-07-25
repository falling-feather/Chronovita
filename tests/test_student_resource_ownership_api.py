from __future__ import annotations

import copy
import shutil
import sys
import unittest
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import auth as auth_router
from routers import learning as learning_router
from routers import practice as practice_router
from settings import settings
from services import persistence
from services.auth import AuthServiceConfig, configure_identity, shutdown_identity


class StudentResourceOwnershipApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-student-resource-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.previous = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "game_user_id": settings.game_user_id,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_cookie_name = "chronovita_student_resource_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        settings.game_user_id = "local-student"
        database_path = self.tmp_root / "chronovita.db"
        persistence.close_engine()

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            engine = persistence.init_engine(str(database_path))
            try:
                configure_identity(
                    engine,
                    AuthServiceConfig(
                        mode="accounts",
                        session_ttl_seconds=settings.auth_session_ttl_seconds,
                        bootstrap_username=settings.auth_bootstrap_username,
                        bootstrap_password=settings.auth_bootstrap_password,
                        bootstrap_display_name=settings.auth_bootstrap_display_name,
                    ),
                )
                yield
            finally:
                shutdown_identity()
                persistence.close_engine()

        app = FastAPI(lifespan=lifespan)
        app.include_router(auth_router.router, prefix="/api/v1/auth")
        app.include_router(learning_router.router, prefix="/api/v1/learning")
        app.include_router(practice_router.router, prefix="/api/v1/practice")
        self.client = TestClient(app)
        self.client.__enter__()

        admin_token = self._login("root.admin", "Root password 123!")
        self.admin_headers = {"Authorization": f"Bearer {admin_token}"}
        self.client.cookies.clear()
        self.student_a = self._create_student(
            "student.a",
            "Student A password 123!",
            "Student A",
        )
        self.student_b = self._create_student(
            "student.b",
            "Student B password 123!",
            "Student B",
        )
        self.student_a_headers = self._login_headers(
            "student.a",
            "Student A password 123!",
        )
        self.student_b_headers = self._login_headers(
            "student.b",
            "Student B password 123!",
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

    def test_progress_lists_exact_owner_and_cas_merges_competing_layers(self):
        legacy_lesson = "lesson-legacy-progress"
        persistence.kv_set(
            "lesson_progress",
            f"default:{legacy_lesson}",
            {
                "user_id": "default",
                "lesson_id": legacy_lesson,
                "last_layer": "watch",
                "layers": {
                    "watch": True,
                    "practice": False,
                    "ask": False,
                    "create": False,
                },
                "updated_at": "2026-07-16T01:00:00+00:00",
            },
        )
        unauthenticated = self.client.get("/api/v1/learning/progress")
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        unmapped = self.client.get(
            f"/api/v1/learning/progress/{legacy_lesson}",
            headers=self.student_a_headers,
        )
        self.assertEqual(unmapped.status_code, 200, unmapped.text)
        self.assertIsNone(unmapped.json()["item"])

        shared_lesson = "lesson-owner-progress"
        first_a = self._touch(
            self.student_a_headers,
            shared_lesson,
            "watch",
        )
        first_b = self._touch(
            self.student_b_headers,
            shared_lesson,
            "practice",
        )
        self.assertTrue(first_a["layers"]["watch"])
        self.assertFalse(first_a["layers"]["practice"])
        self.assertTrue(first_b["layers"]["practice"])
        self.assertFalse(first_b["layers"]["watch"])

        spoof_owner = self.student_a["user_id"].replace("_", "x", 1)
        persistence.kv_set(
            "lesson_progress",
            f"{spoof_owner}:lesson-prefix-spoof",
            {
                "user_id": spoof_owner,
                "lesson_id": "lesson-prefix-spoof",
                "last_layer": "watch",
                "layers": {
                    "watch": True,
                    "practice": False,
                    "ask": False,
                    "create": False,
                },
                "updated_at": "2026-07-16T02:00:00+00:00",
            },
        )
        list_a = self.client.get(
            "/api/v1/learning/progress",
            headers=self.student_a_headers,
        )
        list_b = self.client.get(
            "/api/v1/learning/progress",
            headers=self.student_b_headers,
        )
        self.assertEqual(list_a.status_code, 200, list_a.text)
        self.assertEqual(list_b.status_code, 200, list_b.text)
        self.assertEqual(
            [item["lesson_id"] for item in list_a.json()["items"]],
            [shared_lesson],
        )
        self.assertEqual(
            [item["lesson_id"] for item in list_b.json()["items"]],
            [shared_lesson],
        )

        original_cas = persistence.kv_compare_and_set
        injected = False

        def inject_competing_layer(
            namespace,
            key,
            expected,
            data,
            *,
            expected_present=None,
        ):
            nonlocal injected
            if not injected:
                injected = True
                competitor = copy.deepcopy(expected)
                competitor["last_layer"] = "practice"
                competitor["layers"]["practice"] = True
                competitor["updated_at"] = "2026-07-16T03:00:00+00:00"
                self.assertTrue(
                    original_cas(
                        namespace,
                        key,
                        expected,
                        competitor,
                        expected_present=expected_present,
                    )
                )
                return False
            return original_cas(
                namespace,
                key,
                expected,
                data,
                expected_present=expected_present,
            )

        with patch.object(
            persistence,
            "kv_compare_and_set",
            side_effect=inject_competing_layer,
        ):
            merged = self._touch(
                self.student_a_headers,
                shared_lesson,
                "ask",
            )
        self.assertTrue(merged["layers"]["watch"])
        self.assertTrue(merged["layers"]["practice"])
        self.assertTrue(merged["layers"]["ask"])

        settings.auth_mode = "legacy-local"
        legacy_read = self.client.get(
            f"/api/v1/learning/progress/{legacy_lesson}"
        )
        self.assertEqual(legacy_read.status_code, 200, legacy_read.text)
        self.assertTrue(legacy_read.json()["item"]["layers"]["watch"])
        settings.auth_mode = "accounts"

    def test_canvas_revision_is_scoped_by_owner_and_legacy_key_stays_local(self):
        lesson_id = "lesson-owner-canvas"
        legacy_lesson = "lesson-legacy-canvas"
        persistence.kv_set(
            "canvas",
            legacy_lesson,
            {"nodes": [{"id": "legacy"}], "edges": []},
        )
        unauthenticated = self.client.get(
            f"/api/v1/practice/canvas/{lesson_id}"
        )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)

        saved_a = self._save_canvas(
            self.student_a_headers,
            lesson_id,
            "student-a-node",
        )
        saved_b = self._save_canvas(
            self.student_b_headers,
            lesson_id,
            "student-b-node",
        )
        self.assertEqual(saved_a["revision"], 1)
        self.assertEqual(saved_b["revision"], 1)

        fetched_a = self.client.get(
            f"/api/v1/practice/canvas/{lesson_id}",
            headers=self.student_a_headers,
        )
        fetched_b = self.client.get(
            f"/api/v1/practice/canvas/{lesson_id}",
            headers=self.student_b_headers,
        )
        self.assertEqual(fetched_a.json()["nodes"][0]["id"], "student-a-node")
        self.assertEqual(fetched_b.json()["nodes"][0]["id"], "student-b-node")
        self.assertIsNotNone(
            persistence.kv_get(
                "canvas",
                f"{self.student_a['user_id']}:{lesson_id}",
            )
        )
        self.assertIsNotNone(
            persistence.kv_get(
                "canvas",
                f"{self.student_b['user_id']}:{lesson_id}",
            )
        )

        legacy_hidden = self.client.get(
            f"/api/v1/practice/canvas/{legacy_lesson}",
            headers=self.student_a_headers,
        )
        self.assertEqual(legacy_hidden.status_code, 200, legacy_hidden.text)
        self.assertFalse(legacy_hidden.json()["found"])
        guessed_owner_key = self.client.get(
            f"/api/v1/practice/canvas/{self.student_b['user_id']}:{lesson_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(guessed_owner_key.status_code, 422, guessed_owner_key.text)

        generate_without_session = self.client.post(
            "/api/v1/practice/canvas/generate",
            json={
                "lesson_id": lesson_id,
                "lesson_title": "Test",
                "abstract": "Test",
                "keywords": [],
                "seed": [],
            },
        )
        self.assertEqual(
            generate_without_session.status_code,
            401,
            generate_without_session.text,
        )

        settings.auth_mode = "legacy-local"
        legacy_read = self.client.get(
            f"/api/v1/practice/canvas/{legacy_lesson}"
        )
        self.assertEqual(legacy_read.status_code, 200, legacy_read.text)
        self.assertTrue(legacy_read.json()["found"])
        self.assertEqual(legacy_read.json()["nodes"][0]["id"], "legacy")
        settings.auth_mode = "accounts"

    def _touch(self, headers: dict[str, str], lesson_id: str, layer: str) -> dict:
        response = self.client.post(
            "/api/v1/learning/progress/touch",
            headers=headers,
            json={
                "lesson_id": lesson_id,
                "layer": layer,
                "completed": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["item"]

    def _save_canvas(
        self,
        headers: dict[str, str],
        lesson_id: str,
        node_id: str,
    ) -> dict:
        response = self.client.put(
            f"/api/v1/practice/canvas/{lesson_id}",
            headers=headers,
            json={
                "expected_revision": 0,
                "nodes": [{"id": node_id}],
                "edges": [],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_student(
        self,
        username: str,
        password: str,
        display_name: str,
    ) -> dict:
        response = self.client.post(
            "/api/v1/auth/users",
            headers=self.admin_headers,
            json={
                "username": username,
                "password": password,
                "display_name": display_name,
                "roles": ["student"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _login_headers(self, username: str, password: str) -> dict[str, str]:
        token = self._login(username, password)
        self.client.cookies.clear()
        return {"Authorization": f"Bearer {token}"}

    def _login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/v1/auth/token",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]


if __name__ == "__main__":
    unittest.main()
