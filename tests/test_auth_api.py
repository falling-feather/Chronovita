from __future__ import annotations

import shutil
import sys
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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
    SessionUnavailable,
    configure_identity,
    get_identity,
    shutdown_identity,
)
import services.auth.service as auth_service_module
from services.auth.service import (
    session_token_absolute_expires_at,
    token_digest,
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
            "auth_session_idle_timeout_seconds": (
                settings.auth_session_idle_timeout_seconds
            ),
            "auth_session_absolute_ttl_seconds": (
                settings.auth_session_absolute_ttl_seconds
            ),
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "admin_token": settings.admin_token,
            "admin_actor": settings.admin_actor,
            "runtime_profile": settings.runtime_profile,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_session_idle_timeout_seconds = 900
        settings.auth_session_absolute_ttl_seconds = 7200
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

    def test_browser_runtime_config_exposes_mode_without_secrets(self):
        response = self.client.get("/api/v1/auth/config")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "mode": "accounts",
                "browser_transport": "http-only-cookie",
            },
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("token", response.text.lower())
        self.assertNotIn("cookie_name", response.text.lower())

        settings.auth_mode = "legacy-local"
        try:
            legacy = self.client.get("/api/v1/auth/config")
        finally:
            settings.auth_mode = "accounts"
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["mode"], "legacy-local")

    def test_role_action_matrix_for_browser_workspaces(self):
        admin = self._login("root.admin", "Root password 123!")
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        accounts = (
            ("student.browser", "Student browser 123!", "student"),
            ("teacher.browser", "Teacher browser 123!", "teacher"),
            ("reviewer.browser", "Reviewer browser 123!", "reviewer"),
        )
        created: dict[str, tuple[str, str]] = {}
        for username, password, role in accounts:
            response = self.client.post(
                "/api/v1/auth/users",
                headers=admin_headers,
                json={
                    "username": username,
                    "password": password,
                    "display_name": role.title(),
                    "roles": [role],
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            created[role] = (response.json()["user_id"], password)

        self.client.cookies.clear()
        tokens = {
            role: self._login(f"{role}.browser", password)["access_token"]
            for role, (_, password) in created.items()
        }
        self.client.cookies.clear()

        for role, token in tokens.items():
            response = self.client.get(
                "/api/v1/auth/users",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(response.status_code, 403, f"{role}: {response.text}")

        allowed = self.client.get("/api/v1/auth/users", headers=admin_headers)
        self.assertEqual(allowed.status_code, 200, allowed.text)

        target_id = created["student"][0]
        denied = self.client.patch(
            f"/api/v1/auth/users/{target_id}",
            headers={"Authorization": f"Bearer {tokens['teacher']}"},
            json={"enabled": False},
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        revoked = self.client.post(
            f"/api/v1/auth/users/{target_id}/sessions/revoke",
            headers=admin_headers,
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)

    def test_cookie_and_bearer_sessions_are_transport_bound(self):
        denied = self.client.post(
            "/api/v1/auth/token",
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
        self.assertEqual(logged_in["transport"], "cookie")
        self.assertNotIn("access_token", logged_in)
        self.assertNotIn("token_type", logged_in)
        self.assertEqual(logged_in["principal"]["roles"], ["admin"])
        cookie = logged_in_response.headers.get("set-cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertNotIn("Secure", cookie)
        cookie_token = self.client.cookies.get(settings.auth_cookie_name)
        self.assertTrue(cookie_token.startswith("cvs_cookie_"))

        cookie_me = self.client.get("/api/v1/auth/me")
        self.assertEqual(cookie_me.status_code, 200, cookie_me.text)
        self.assertEqual(cookie_me.json()["source"], "cookie")
        self.assertEqual(cookie_me.headers["cache-control"], "no-store")

        with get_identity().store.engine.connect() as connection:
            stored_hashes = list(connection.execute(select(sessions_table.c.token_hash)).scalars())
        self.assertEqual(len(stored_hashes), 1)
        self.assertNotIn(cookie_token, stored_hashes)
        self.assertNotIn(
            cookie_token,
            self.sqlite_path.read_bytes().decode("utf-8", errors="ignore"),
        )

        audit = self.client.get("/api/v1/auth/audit")
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertTrue(audit.json()["valid_chain"])
        self.assertIn("auth.login", {item["action"] for item in audit.json()["items"]})
        login_event = next(
            item for item in audit.json()["items"] if item["action"] == "auth.login"
        )
        self.assertEqual(login_event["request_id"], login_request_id)

        duplicate_cookie_and_bearer = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {cookie_token}"},
        )
        self.assertEqual(
            duplicate_cookie_and_bearer.status_code,
            401,
            duplicate_cookie_and_bearer.text,
        )
        self.assertEqual(
            duplicate_cookie_and_bearer.json()["detail"]["code"],
            "credential_conflict",
        )
        self.client.cookies.clear()
        cookie_as_bearer = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {cookie_token}"},
        )
        self.assertEqual(cookie_as_bearer.status_code, 401, cookie_as_bearer.text)
        self.assertEqual(
            cookie_as_bearer.json()["detail"]["code"],
            "session_expired",
        )
        self.client.cookies.set(settings.auth_cookie_name, cookie_token)

        logout = self.client.post(
            "/api/v1/auth/logout",
            headers={"Origin": settings.cors_origins[0]},
        )
        self.assertEqual(logout.status_code, 204, logout.text)
        self.assertEqual(logout.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.client.cookies.clear()

        token = self._login("ROOT.ADMIN", "Root password 123!")["access_token"]
        self.assertTrue(token.startswith("cvs_bearer_"))
        bearer_me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bearer_me.status_code, 200, bearer_me.text)
        self.assertEqual(bearer_me.json()["source"], "bearer")

        self.client.cookies.set(settings.auth_cookie_name, token)
        bearer_as_cookie = self.client.get("/api/v1/auth/me")
        self.assertEqual(bearer_as_cookie.status_code, 401, bearer_as_cookie.text)
        self.assertEqual(
            bearer_as_cookie.json()["detail"]["code"],
            "session_expired",
        )
        self.client.cookies.clear()

    def test_refresh_rotates_cookie_and_bearer_sessions(self):
        first_bearer = self._login(
            "root.admin",
            "Root password 123!",
        )["access_token"]
        refreshed_bearer = self.client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {first_bearer}"},
        )
        self.assertEqual(
            refreshed_bearer.status_code,
            200,
            refreshed_bearer.text,
        )
        refreshed_body = refreshed_bearer.json()
        second_bearer = refreshed_body["access_token"]
        self.assertEqual(refreshed_body["transport"], "bearer")
        self.assertNotEqual(first_bearer, second_bearer)
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {first_bearer}"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {second_bearer}"},
            ).status_code,
            200,
        )

        self.client.cookies.clear()
        cookie_login = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "root.admin",
                "password": "Root password 123!",
            },
        )
        self.assertEqual(cookie_login.status_code, 200, cookie_login.text)
        first_cookie = self.client.cookies.get(settings.auth_cookie_name)
        rejected_refresh = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(
            rejected_refresh.status_code,
            403,
            rejected_refresh.text,
        )
        accepted_refresh = self.client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": settings.cors_origins[0]},
        )
        self.assertEqual(accepted_refresh.status_code, 200, accepted_refresh.text)
        self.assertEqual(accepted_refresh.json()["transport"], "cookie")
        self.assertNotIn("access_token", accepted_refresh.json())
        second_cookie = self.client.cookies.get(settings.auth_cookie_name)
        self.assertNotEqual(first_cookie, second_cookie)

        self.client.cookies.clear()
        self.client.cookies.set(settings.auth_cookie_name, first_cookie)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.client.cookies.clear()
        self.client.cookies.set(settings.auth_cookie_name, second_cookie)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)

        actions = {
            item["action"]
            for item in self.client.get(
                "/api/v1/auth/audit",
                headers={"Origin": settings.cors_origins[0]},
            ).json()["items"]
        }
        self.assertIn("auth.session.refresh", actions)

    def test_session_lifetimes_and_refresh_audit_are_enforced(self):
        first_session = self._login(
            "root.admin",
            "Root password 123!",
        )
        first_token = first_session["access_token"]
        first_absolute = datetime.fromisoformat(
            first_session["absolute_expires_at"],
        )
        self.assertEqual(
            session_token_absolute_expires_at(first_token),
            first_absolute,
        )

        refreshed = self.client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {first_token}"},
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        refreshed_expires_at = datetime.fromisoformat(
            refreshed.json()["expires_at"],
        )
        self.assertEqual(
            datetime.fromisoformat(refreshed.json()["absolute_expires_at"]),
            first_absolute,
        )
        self.assertLessEqual(refreshed_expires_at, first_absolute)
        refreshed_token = refreshed.json()["access_token"]
        self.assertEqual(
            session_token_absolute_expires_at(refreshed_token),
            first_absolute,
        )

        stale_last_seen = datetime.now(timezone.utc) - timedelta(
            seconds=settings.auth_session_idle_timeout_seconds + 1,
        )
        with get_identity().store.engine.begin() as connection:
            connection.execute(
                update(sessions_table)
                .where(
                    sessions_table.c.token_hash
                    == token_digest(refreshed_token)
                )
                .values(last_seen_at=stale_last_seen.isoformat())
            )
        idle_expired = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refreshed_token}"},
        )
        self.assertEqual(idle_expired.status_code, 401, idle_expired.text)

        rollback_token = self._login(
            "root.admin",
            "Root password 123!",
        )["access_token"]
        store = get_identity().store
        with patch.object(
            store,
            "_append_audit_event",
            side_effect=AuthStoreError("forced audit failure"),
        ):
            failed_refresh = self.client.post(
                "/api/v1/auth/refresh",
                headers={"Authorization": f"Bearer {rollback_token}"},
            )
        self.assertEqual(failed_refresh.status_code, 503, failed_refresh.text)
        old_token_still_valid = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {rollback_token}"},
        )
        self.assertEqual(
            old_token_still_valid.status_code,
            200,
            old_token_still_valid.text,
        )

        config_session = self._login(
            "root.admin",
            "Root password 123!",
        )
        config_token = config_session["access_token"]
        config_principal = get_identity().authenticate(
            config_token,
            transport="bearer",
        )
        self.assertIsNotNone(config_principal)
        fixed_absolute = datetime.fromisoformat(
            config_session["absolute_expires_at"],
        )
        near_deadline = fixed_absolute - timedelta(minutes=5)
        with get_identity().store.engine.begin() as connection:
            connection.execute(
                update(sessions_table)
                .where(
                    sessions_table.c.token_hash
                    == token_digest(config_token)
                )
                .values(
                    expires_at=fixed_absolute.isoformat(),
                    last_seen_at=near_deadline.isoformat(),
                )
            )

        expanded = AuthService(
            get_identity().store.engine,
            AuthServiceConfig(
                mode="accounts",
                session_ttl_seconds=3600,
                session_idle_timeout_seconds=900,
                session_absolute_ttl_seconds=14400,
            ),
        )
        with patch.object(
            auth_service_module,
            "_utc_now",
            return_value=near_deadline,
        ):
            rotated = expanded.refresh(
                config_token,
                config_principal,
                request_id="absolute-expanded-refresh",
                transport="bearer",
            )
        self.assertEqual(rotated.absolute_expires_at, fixed_absolute)
        self.assertEqual(rotated.record.expires_at, fixed_absolute)
        self.assertEqual(
            session_token_absolute_expires_at(rotated.token),
            fixed_absolute,
        )

        reduced = AuthService(
            get_identity().store.engine,
            AuthServiceConfig(
                mode="accounts",
                session_ttl_seconds=3600,
                session_idle_timeout_seconds=900,
                session_absolute_ttl_seconds=3600,
            ),
        )
        with patch.object(
            auth_service_module,
            "_utc_now",
            return_value=near_deadline,
        ):
            self.assertIsNotNone(
                reduced.authenticate(rotated.token, transport="bearer"),
            )
        with patch.object(
            auth_service_module,
            "_utc_now",
            return_value=fixed_absolute + timedelta(seconds=1),
        ):
            self.assertIsNone(
                expanded.authenticate(rotated.token, transport="bearer"),
            )

    def test_session_revoke_all_is_atomic_for_self_and_admin(self):
        admin_token = self._login(
            "root.admin",
            "Root password 123!",
        )["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created = self.client.post(
            "/api/v1/auth/users",
            headers=admin_headers,
            json={
                "username": "student.sessions",
                "password": "Student password 123!",
                "display_name": "Student Sessions",
                "roles": ["student"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        user_id = created.json()["user_id"]
        first = self._login(
            "student.sessions",
            "Student password 123!",
        )["access_token"]
        second = self._login(
            "student.sessions",
            "Student password 123!",
        )["access_token"]

        self_revoked = self.client.post(
            "/api/v1/auth/sessions/revoke-all",
            headers={"Authorization": f"Bearer {first}"},
        )
        self.assertEqual(self_revoked.status_code, 200, self_revoked.text)
        self.assertEqual(self_revoked.json()["revoked_sessions"], 2)
        for token in (first, second):
            self.assertEqual(
                self.client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                ).status_code,
                401,
            )

        third = self._login(
            "student.sessions",
            "Student password 123!",
        )["access_token"]
        admin_revoked = self.client.post(
            f"/api/v1/auth/users/{user_id}/sessions/revoke",
            headers=admin_headers,
        )
        self.assertEqual(admin_revoked.status_code, 200, admin_revoked.text)
        self.assertEqual(admin_revoked.json()["revoked_sessions"], 1)
        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {third}"},
            ).status_code,
            401,
        )

        rollback_token = self._login(
            "student.sessions",
            "Student password 123!",
        )["access_token"]
        store = get_identity().store
        with patch.object(
            store,
            "_append_audit_event",
            side_effect=AuthStoreError("forced audit failure"),
        ):
            failed_revoke = self.client.post(
                "/api/v1/auth/sessions/revoke-all",
                headers={"Authorization": f"Bearer {rollback_token}"},
            )
        self.assertEqual(failed_revoke.status_code, 503, failed_revoke.text)
        rollback_preserved = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {rollback_token}"},
        )
        self.assertEqual(
            rollback_preserved.status_code,
            200,
            rollback_preserved.text,
        )

    def test_logout_clears_invalid_cookie_and_cookie_login_checks_origin(self):
        settings.runtime_profile = "production"
        rejected = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "root.admin",
                "password": "Root password 123!",
            },
        )
        self.assertEqual(rejected.status_code, 403, rejected.text)
        accepted = self.client.post(
            "/api/v1/auth/login",
            headers={"Origin": settings.cors_origins[0]},
            json={
                "username": "root.admin",
                "password": "Root password 123!",
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)

        self.client.cookies.clear()
        self.client.cookies.set(
            settings.auth_cookie_name,
            "cvs_cookie_invalid-session-token-value",
        )
        logged_out = self.client.post(
            "/api/v1/auth/logout",
            headers={"Origin": settings.cors_origins[0]},
        )
        self.assertEqual(logged_out.status_code, 204, logged_out.text)
        self.assertIn("Max-Age=0", logged_out.headers["set-cookie"])

    def test_concurrent_refresh_allows_exactly_one_winner(self):
        identity = get_identity()
        issued = identity.login(
            "root.admin",
            "Root password 123!",
            request_id="concurrent-refresh-login",
            transport="bearer",
        )
        barrier = threading.Barrier(2)

        def refresh(index: int):
            barrier.wait(timeout=10)
            try:
                return identity.refresh(
                    issued.token,
                    issued.principal,
                    request_id=f"concurrent-refresh-{index}",
                    transport="bearer",
                )
            except SessionUnavailable:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(refresh, range(2)))

        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        self.assertIsNone(
            identity.authenticate(issued.token, transport="bearer"),
        )
        self.assertIsNotNone(
            identity.authenticate(winners[0].token, transport="bearer"),
        )
        self.assertTrue(identity.store.verify_audit_chain())

    def test_user_management_permissions_and_session_revocation(self):
        admin_token = self._login("root.admin", "Root password 123!")["access_token"]
        cookie_login = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "root.admin",
                "password": "Root password 123!",
            },
        )
        self.assertEqual(cookie_login.status_code, 200, cookie_login.text)
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
            "/api/v1/auth/token",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["transport"], "bearer")
        self.assertEqual(body["token_type"], "bearer")
        return body


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
