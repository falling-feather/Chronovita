from __future__ import annotations

import shutil
import sys
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import URL


API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import auth as auth_router
from settings import settings
from services import persistence
from services.auth import (
    AuthService,
    AuthServiceConfig,
    BootstrapRequired,
    LastAdminRequired,
    Principal,
    configure_identity,
    get_identity,
    shutdown_identity,
)
from services.auth.passwords import hash_password, verify_password
from services.persistence.schema import ensure_current_schema
from services.auth.store import AuthStoreError, audit_events_table, sessions_table


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-auth-api-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.sqlite_path = self.tmp_root / "chronovita.db"
        self.previous = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "admin_token": settings.admin_token,
            "admin_actor": settings.admin_actor,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_cookie_name = "chronovita_test_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        settings.admin_token = "legacy-test-token"
        settings.admin_actor = "legacy-admin"

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            engine = persistence.init_engine(str(self.sqlite_path))
            try:
                configure_identity(
                    engine,
                    AuthServiceConfig(
                        mode=settings.auth_mode,
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
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for key, value in self.previous.items():
            setattr(settings, key, value)
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_login_cookie_bearer_logout_and_hashed_storage(self):
        denied = self.client.post(
            "/api/v1/auth/login",
            json={"username": "root.admin", "password": "wrong password"},
        )
        self.assertEqual(denied.status_code, 401, denied.text)
        self.assertEqual(denied.json()["detail"]["code"], "invalid_credentials")

        login_request_id = "auth-login-request-001"
        logged_in_response = self.client.post(
            "/api/v1/auth/login",
            headers={"X-Request-ID": login_request_id},
            json={"username": "root.admin", "password": "Root password 123!"},
        )
        self.assertEqual(logged_in_response.status_code, 200, logged_in_response.text)
        logged_in = logged_in_response.json()
        token = logged_in["access_token"]
        self.assertEqual(logged_in["principal"]["roles"], ["admin"])
        cookie = logged_in_response.headers.get("set-cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertNotIn("Secure", cookie)

        cookie_me = self.client.get("/api/v1/auth/me")
        self.assertEqual(cookie_me.status_code, 200, cookie_me.text)
        self.assertEqual(cookie_me.json()["source"], "cookie")

        with get_identity().store.engine.connect() as connection:
            stored_hashes = list(connection.execute(select(sessions_table.c.token_hash)).scalars())
        self.assertEqual(len(stored_hashes), 1)
        self.assertNotIn(token, stored_hashes)
        self.assertNotIn(token, self.sqlite_path.read_bytes().decode("utf-8", errors="ignore"))

        audit = self.client.get("/api/v1/auth/audit")
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertTrue(audit.json()["valid_chain"])
        self.assertIn("auth.login", {item["action"] for item in audit.json()["items"]})
        login_event = next(
            item for item in audit.json()["items"] if item["action"] == "auth.login"
        )
        self.assertEqual(login_event["request_id"], login_request_id)

        logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout.status_code, 204, logout.text)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

        token = self._login("ROOT.ADMIN", "Root password 123!")["access_token"]
        self.client.cookies.clear()
        bearer_me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bearer_me.status_code, 200, bearer_me.text)
        self.assertEqual(bearer_me.json()["source"], "bearer")

    def test_user_management_permissions_and_session_revocation(self):
        admin_token = self._login("root.admin", "Root password 123!")["access_token"]
        rejected_cookie_write = self.client.post(
            "/api/v1/auth/users",
            json={
                "username": "cookie.rejected",
                "password": "Cookie password 123!",
                "display_name": "Cookie Rejected",
                "roles": ["teacher"],
            },
        )
        self.assertEqual(rejected_cookie_write.status_code, 403, rejected_cookie_write.text)
        self.assertEqual(
            rejected_cookie_write.json()["detail"]["code"],
            "csrf_origin_rejected",
        )
        accepted_cookie_write = self.client.post(
            "/api/v1/auth/users",
            headers={"Origin": settings.cors_origins[0]},
            json={
                "username": "cookie.accepted",
                "password": "Cookie password 123!",
                "display_name": "Cookie Accepted",
                "roles": ["teacher"],
            },
        )
        self.assertEqual(accepted_cookie_write.status_code, 201, accepted_cookie_write.text)
        self.client.cookies.clear()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        created = self.client.post(
            "/api/v1/auth/users",
            headers=admin_headers,
            json={
                "username": "teacher.one",
                "password": "Teacher password 123!",
                "display_name": "Teacher One",
                "roles": ["teacher"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        teacher_id = created.json()["user_id"]

        duplicate = self.client.post(
            "/api/v1/auth/users",
            headers=admin_headers,
            json={
                "username": "TEACHER.ONE",
                "password": "Another password 123!",
                "display_name": "Duplicate",
                "roles": ["teacher"],
            },
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        teacher_token = self._login("teacher.one", "Teacher password 123!")["access_token"]
        self.client.cookies.clear()
        teacher_headers = {"Authorization": f"Bearer {teacher_token}"}
        forbidden = self.client.get("/api/v1/auth/users", headers=teacher_headers)
        self.assertEqual(forbidden.status_code, 403, forbidden.text)
        self.assertEqual(forbidden.json()["detail"]["code"], "permission_denied")

        changed = self.client.patch(
            f"/api/v1/auth/users/{teacher_id}",
            headers=admin_headers,
            json={"roles": ["teacher", "reviewer"]},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["roles"], ["teacher", "reviewer"])
        self.assertEqual(
            self.client.get("/api/v1/auth/me", headers=teacher_headers).status_code,
            401,
        )

        teacher_token = self._login("teacher.one", "Teacher password 123!")["access_token"]
        self.client.cookies.clear()
        disabled = self.client.patch(
            f"/api/v1/auth/users/{teacher_id}",
            headers=admin_headers,
            json={"enabled": False},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertFalse(disabled.json()["enabled"])
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {teacher_token}"},
            ).status_code,
            401,
        )

        users = self.client.get("/api/v1/auth/users", headers=admin_headers).json()["items"]
        root_id = next(item["user_id"] for item in users if item["username"] == "root.admin")
        last_admin = self.client.patch(
            f"/api/v1/auth/users/{root_id}",
            headers=admin_headers,
            json={"enabled": False},
        )
        self.assertEqual(last_admin.status_code, 409, last_admin.text)
        self.assertEqual(last_admin.json()["detail"]["code"], "last_admin_required")

    def test_password_reset_invalidates_existing_sessions_and_audit_detects_tampering(self):
        admin_token = self._login("root.admin", "Root password 123!")["access_token"]
        self.client.cookies.clear()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created = self.client.post(
            "/api/v1/auth/users",
            headers=admin_headers,
            json={
                "username": "student.one",
                "password": "Student password 123!",
                "display_name": "Student One",
                "roles": ["student"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        student_id = created.json()["user_id"]
        student_token = self._login("student.one", "Student password 123!")["access_token"]
        self.client.cookies.clear()

        reset = self.client.post(
            f"/api/v1/auth/users/{student_id}/password",
            headers=admin_headers,
            json={"password": "New student password 456!"},
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {student_token}"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"username": "student.one", "password": "Student password 123!"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"username": "student.one", "password": "New student password 456!"},
            ).status_code,
            200,
        )
        self.client.cookies.clear()

        valid = self.client.get("/api/v1/auth/audit", headers=admin_headers)
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertTrue(valid.json()["valid_chain"])
        with get_identity().store.engine.begin() as connection:
            connection.execute(
                update(audit_events_table)
                .where(audit_events_table.c.sequence == 1)
                .values(details='{"tampered":true}')
            )
        tampered = self.client.get("/api/v1/auth/audit", headers=admin_headers)
        self.assertEqual(tampered.status_code, 200, tampered.text)
        self.assertFalse(tampered.json()["valid_chain"])

    def test_audit_failure_rolls_back_session_and_user_creation(self):
        store = get_identity().store
        with patch.object(
            store,
            "_append_audit_event",
            side_effect=AuthStoreError("forced audit failure"),
        ):
            failed_login = self.client.post(
                "/api/v1/auth/login",
                json={"username": "root.admin", "password": "Root password 123!"},
            )
        self.assertEqual(failed_login.status_code, 503, failed_login.text)
        with store.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(sessions_table)).fetchall()), 0)

        admin_token = self._login("root.admin", "Root password 123!")["access_token"]
        self.client.cookies.clear()
        with patch.object(
            store,
            "_append_audit_event",
            side_effect=AuthStoreError("forced audit failure"),
        ):
            failed_create = self.client.post(
                "/api/v1/auth/users",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "username": "should.rollback",
                    "password": "Rollback password 123!",
                    "display_name": "Rollback User",
                    "roles": ["teacher"],
                },
            )
        self.assertEqual(failed_create.status_code, 503, failed_create.text)
        self.assertIsNone(store.get_user_by_username("should.rollback"))
        self.assertTrue(store.verify_audit_chain())

    def test_legacy_local_auth_is_explicit_and_rejects_conflicting_headers(self):
        settings.auth_mode = "legacy-local"
        accepted = self.client.get(
            "/api/v1/auth/me",
            headers={"X-Admin-Token": settings.admin_token},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertTrue(accepted.json()["principal"]["synthetic"])
        self.assertEqual(accepted.json()["source"], "legacy-local")

        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        conflict = self.client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {settings.admin_token}",
                "X-Admin-Token": "different-token",
            },
        )
        self.assertEqual(conflict.status_code, 401, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "credential_conflict")
        settings.auth_mode = "accounts"

    def _login(self, username: str, password: str) -> dict:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class AuthPrimitiveTests(unittest.TestCase):
    def test_scrypt_hash_is_salted_and_rejects_bad_values(self):
        first = hash_password("Long password 123!")
        second = hash_password("Long password 123!")
        self.assertNotEqual(first, second)
        self.assertNotIn("Long password 123!", first)
        self.assertTrue(verify_password("Long password 123!", first))
        self.assertFalse(verify_password("Wrong password 123!", first))
        self.assertFalse(verify_password("Long password 123!", "not-a-hash"))
        self.assertFalse(verify_password("Long password 123!", first + "!"))
        with self.assertRaisesRegex(ValueError, "invalid Unicode"):
            hash_password("\ud800" * 12)

    def test_accounts_mode_empty_database_requires_explicit_bootstrap(self):
        tmp_root = Path.cwd() / ".tmp-auth-bootstrap-tests" / uuid.uuid4().hex
        tmp_root.mkdir(parents=True)
        engine = create_engine(URL.create("sqlite", database=str(tmp_root / "auth.db")))
        try:
            ensure_current_schema(engine)
            with self.assertRaises(BootstrapRequired):
                AuthService(
                    engine,
                    AuthServiceConfig(mode="accounts", session_ttl_seconds=3600),
                )
        finally:
            engine.dispose()
            shutil.rmtree(tmp_root, ignore_errors=True)
            try:
                tmp_root.parent.rmdir()
            except OSError:
                pass

    def test_concurrent_bootstrap_and_last_admin_changes_are_serialized(self):
        tmp_root = Path.cwd() / ".tmp-auth-invariant-tests" / uuid.uuid4().hex
        tmp_root.mkdir(parents=True)
        url = URL.create("sqlite", database=str(tmp_root / "auth.db"))
        engines = [
            create_engine(
                url,
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            for _ in range(4)
        ]
        try:
            ensure_current_schema(engines[0])
            config = AuthServiceConfig(
                mode="accounts",
                session_ttl_seconds=3600,
                bootstrap_username="race.admin",
                bootstrap_password="Race admin password 123!",
                bootstrap_display_name="Race Admin",
            )
            bootstrap_barrier = threading.Barrier(len(engines))

            def start_service(engine):
                bootstrap_barrier.wait(timeout=10)
                return AuthService(engine, config)

            with ThreadPoolExecutor(max_workers=len(engines)) as executor:
                services = tuple(executor.map(start_service, engines))

            users = services[0].store.list_users()
            self.assertEqual([user.username for user in users], ["race.admin"])
            bootstrap_events = [
                event
                for event in services[0].store.list_audit(limit=20)
                if event.action == "auth.bootstrap"
            ]
            self.assertEqual(len(bootstrap_events), 1)

            root = users[0]
            actor = Principal(
                user_id=root.user_id,
                username=root.username,
                display_name=root.display_name,
                roles=root.roles,
                auth_version=root.auth_version,
            )
            second = services[0].create_user(
                username="race.admin.two",
                password="Race second password 123!",
                display_name="Race Admin Two",
                roles=("admin",),
                actor=actor,
                request_id="sqlite-create-second-admin",
            )
            change_barrier = threading.Barrier(2)

            def remove_admin(service, user_id: str, request_id: str) -> str:
                change_barrier.wait(timeout=10)
                try:
                    service.update_user(
                        user_id,
                        display_name=None,
                        roles=("teacher",),
                        enabled=None,
                        actor=actor,
                        request_id=request_id,
                    )
                except LastAdminRequired:
                    return "blocked"
                return "updated"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = tuple(
                    executor.map(
                        lambda args: remove_admin(*args),
                        (
                            (services[0], root.user_id, "sqlite-demote-root"),
                            (services[1], second.user_id, "sqlite-demote-second"),
                        ),
                    )
                )

            self.assertEqual(sorted(results), ["blocked", "updated"])
            enabled_admins = [
                user
                for user in services[0].store.list_users()
                if user.enabled and "admin" in user.roles
            ]
            self.assertEqual(len(enabled_admins), 1)
            self.assertTrue(services[0].store.verify_audit_chain())
        finally:
            for engine in engines:
                engine.dispose()
            shutil.rmtree(tmp_root, ignore_errors=True)
            try:
                tmp_root.parent.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
