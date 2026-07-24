from __future__ import annotations

import sys
import shutil
import unittest
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import auth as auth_router
from routers import game as game_router
from settings import settings
from services.auth import (
    AuthServiceConfig,
    AuthStoreError,
    configure_identity,
    get_identity,
    shutdown_identity,
)
from services.game_runtime.service import configure_game_runtime, shutdown_game_runtime
from services.persistence.schema import ensure_current_schema


class GameOwnershipApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-game-ownership-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.previous = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "admin_token": settings.admin_token,
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
            "game_user_id": settings.game_user_id,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_cookie_name = "chronovita_game_owner_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        settings.admin_token = "legacy-game-admin-token"
        settings.content_root = str(REPO_ROOT / "content")
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        settings.game_user_id = "legacy-student"
        database_path = self.tmp_root / "chronovita.db"

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            engine = create_engine(
                URL.create("sqlite", database=str(database_path)),
                future=True,
            )
            try:
                ensure_current_schema(engine)
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
                configure_game_runtime(
                    content_root=settings.content_root,
                    catalog_path=settings.game_catalog_path,
                    engine=engine,
                )
                yield
            finally:
                shutdown_game_runtime()
                shutdown_identity()
                engine.dispose()

        app = FastAPI(lifespan=lifespan)
        app.include_router(auth_router.router, prefix="/api/v1/auth")
        app.include_router(game_router.router, prefix="/api/v1/practice/game")
        self.client = TestClient(app)
        self.client.__enter__()

        admin_token = self._login("root.admin", "Root password 123!")
        self.admin_headers = {"Authorization": f"Bearer {admin_token}"}
        self.client.cookies.clear()
        self.student_a = self._create_user(
            "student.a",
            "Student A password 123!",
            "Student A",
            ["student"],
        )
        self.student_b = self._create_user(
            "student.b",
            "Student B password 123!",
            "Student B",
            ["student"],
        )
        self.teacher = self._create_user(
            "teacher.one",
            "Teacher password 123!",
            "Teacher One",
            ["teacher"],
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
            "teacher.one",
            "Teacher password 123!",
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

    def test_accounts_mode_scopes_every_exact_game_resource_to_its_owner(self):
        self.assertEqual(
            self.client.get("/api/v1/practice/game/scenarios").status_code,
            200,
        )
        request = {
            "scenario_id": "scenario-dayu-flood-control",
            "client_request_id": "owner-start-shared-001",
        }
        unauthenticated = self.client.post(
            "/api/v1/practice/game/sessions",
            json=request,
        )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        forbidden_teacher = self.client.post(
            "/api/v1/practice/game/sessions",
            headers=self.teacher_headers,
            json=request,
        )
        self.assertEqual(forbidden_teacher.status_code, 403, forbidden_teacher.text)

        cookie_login = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "student.a",
                "password": "Student A password 123!",
            },
        )
        self.assertEqual(cookie_login.status_code, 200, cookie_login.text)
        cookie_request = {
            **request,
            "client_request_id": "owner-cookie-start-001",
        }
        rejected_cookie_write = self.client.post(
            "/api/v1/practice/game/sessions",
            json=cookie_request,
        )
        self.assertEqual(rejected_cookie_write.status_code, 403, rejected_cookie_write.text)
        self.assertEqual(
            rejected_cookie_write.json()["detail"]["code"],
            "csrf_origin_rejected",
        )
        accepted_cookie_write = self.client.post(
            "/api/v1/practice/game/sessions",
            headers={"Origin": settings.cors_origins[0]},
            json=cookie_request,
        )
        self.assertEqual(accepted_cookie_write.status_code, 200, accepted_cookie_write.text)
        self.client.cookies.clear()

        spoofed_owner = self.client.post(
            "/api/v1/practice/game/sessions",
            headers=self.student_a_headers,
            json={**request, "user_id": self.student_b["user_id"]},
        )
        self.assertEqual(spoofed_owner.status_code, 422, spoofed_owner.text)

        started_a = self.client.post(
            "/api/v1/practice/game/sessions",
            headers=self.student_a_headers,
            json=request,
        )
        self.assertEqual(started_a.status_code, 200, started_a.text)
        session_a = started_a.json()["session"]
        session_id = session_a["session_id"]
        self.assertEqual(session_a["user_id"], self.student_a["user_id"])

        started_b = self.client.post(
            "/api/v1/practice/game/sessions",
            headers=self.student_b_headers,
            json=request,
        )
        self.assertEqual(started_b.status_code, 200, started_b.text)
        self.assertEqual(
            started_b.json()["session"]["user_id"],
            self.student_b["user_id"],
        )
        self.assertNotEqual(started_b.json()["session"]["session_id"], session_id)

        owner_read = self.client.get(
            f"/api/v1/practice/game/sessions/{session_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(owner_read.status_code, 200, owner_read.text)

        cross_user_requests = [
            self.client.get(
                f"/api/v1/practice/game/sessions/{session_id}",
                headers=self.student_b_headers,
            ),
            self.client.get(
                f"/api/v1/practice/game/sessions/{session_id}/replay",
                headers=self.student_b_headers,
            ),
            self.client.get(
                f"/api/v1/practice/game/sessions/{session_id}/dossier",
                headers=self.student_b_headers,
            ),
            self.client.post(
                f"/api/v1/practice/game/sessions/{session_id}/dossier",
                headers=self.student_b_headers,
            ),
            self.client.post(
                f"/api/v1/practice/game/sessions/{session_id}/turns",
                headers=self.student_b_headers,
                json={
                    "client_action_id": "cross-user-turn-001",
                    "action_id": "survey-terrain",
                    "expected_revision": 1,
                },
            ),
            self.client.post(
                f"/api/v1/practice/game/sessions/{session_id}/free-input",
                headers=self.student_b_headers,
                json={
                    "client_action_id": "cross-user-free-001",
                    "raw_input": "勘察河道",
                    "expected_revision": 1,
                },
            ),
        ]
        for response in cross_user_requests:
            self.assertEqual(response.status_code, 404, response.text)
            self.assertEqual(response.json()["detail"]["code"], "resource_not_found")

        missing = self.client.get(
            "/api/v1/practice/game/sessions/session-does-not-exist",
            headers=self.student_a_headers,
        )
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["detail"]["code"], "resource_not_found")
        unchanged = self.client.get(
            f"/api/v1/practice/game/sessions/{session_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(unchanged.json()["revision"], 1)

        student_summary = self.client.get(
            f"/api/v1/practice/game/sessions/{session_id}/summary",
            headers=self.student_a_headers,
        )
        self.assertEqual(student_summary.status_code, 403, student_summary.text)
        teacher_summary = self.client.get(
            f"/api/v1/practice/game/sessions/{session_id}/summary",
            headers=self.teacher_headers,
        )
        self.assertEqual(teacher_summary.status_code, 200, teacher_summary.text)
        self.assertEqual(teacher_summary.json()["user_id"], self.student_a["user_id"])
        audit = self.client.get(
            "/api/v1/auth/audit",
            headers=self.admin_headers,
        )
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertIn(
            "student.summary.read",
            {item["action"] for item in audit.json()["items"]},
        )
        with patch.object(
            get_identity().store,
            "_append_audit_event",
            side_effect=AuthStoreError("forced audit failure"),
        ):
            unaudited_summary = self.client.get(
                f"/api/v1/practice/game/sessions/{session_id}/summary",
                headers=self.teacher_headers,
            )
        self.assertEqual(unaudited_summary.status_code, 503, unaudited_summary.text)
        self.assertEqual(
            unaudited_summary.json()["detail"]["code"],
            "auth_storage_unavailable",
        )

    def test_unmapped_legacy_session_is_not_adopted_by_first_account(self):
        settings.auth_mode = "legacy-local"
        legacy = self.client.post(
            "/api/v1/practice/game/sessions",
            json={
                "scenario_id": "scenario-dayu-flood-control",
                "client_request_id": "legacy-owner-start-001",
            },
        )
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["session"]["user_id"], "legacy-student")
        legacy_session_id = legacy.json()["session"]["session_id"]

        settings.auth_mode = "accounts"
        account_read = self.client.get(
            f"/api/v1/practice/game/sessions/{legacy_session_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(account_read.status_code, 404, account_read.text)
        self.assertEqual(
            account_read.json()["detail"]["code"],
            "resource_not_found",
        )

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
