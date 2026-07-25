from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import main as api_main
from settings import Settings, runtime_env_file, settings
from services import persistence
from services.operations import (
    RequestBodyLimitMiddleware,
    RuntimeConfigurationError,
    RuntimeReadinessError,
    probe_database_connectivity,
    probe_database_readiness,
    validate_runtime_configuration,
)
from services.persistence.schema import ensure_current_schema


class RuntimeConfigurationTests(unittest.TestCase):
    def test_production_profile_accepts_the_explicit_safe_baseline(self):
        configured = self._production_settings()

        validate_runtime_configuration(configured)

    def test_production_requires_a_single_declared_api_worker(self):
        configured = self._production_settings(api_worker_count=2)

        with self.assertRaises(RuntimeConfigurationError) as caught:
            validate_runtime_configuration(configured)

        self.assertEqual(
            {issue.code for issue in caught.exception.issues},
            {"runtime.production_single_worker_required"},
        )

    def test_session_lifetimes_must_be_monotonic(self):
        cases = (
            (
                {
                    "auth_session_idle_timeout_seconds": 3601,
                    "auth_session_ttl_seconds": 3600,
                },
                "runtime.session_idle_timeout_exceeds_ttl",
            ),
            (
                {
                    "auth_session_ttl_seconds": 7200,
                    "auth_session_absolute_ttl_seconds": 7199,
                },
                "runtime.session_ttl_exceeds_absolute_lifetime",
            ),
        )
        for overrides, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                configured = self._production_settings(**overrides)
                with self.assertRaises(RuntimeConfigurationError) as caught:
                    validate_runtime_configuration(configured)
                self.assertEqual(
                    {issue.code for issue in caught.exception.issues},
                    {expected_code},
                )

    def test_production_profile_rejects_unsafe_settings_without_secret_values(self):
        database_secret = "database-secret-must-not-leak"
        admin_secret = "admin-secret-must-not-leak"
        configured = self._production_settings(
            debug=True,
            auth_mode="legacy-local",
            auth_cookie_secure=False,
            database_migration_mode="apply-safe",
            database_url=f"postgresql://chrono:{database_secret}@db/chronovita",
            admin_token=admin_secret,
            cors_origins=["http://localhost:5173", "https://*.example.test"],
            trusted_hosts=["*", "localhost"],
        )

        with self.assertRaises(RuntimeConfigurationError) as caught:
            validate_runtime_configuration(configured)

        codes = {issue.code for issue in caught.exception.issues}
        self.assertEqual(
            codes,
            {
                "runtime.production_accounts_required",
                "runtime.production_cors_origin_invalid",
                "runtime.production_database_tls_required",
                "runtime.production_debug_disabled",
                "runtime.production_schema_validate_required",
                "runtime.production_secure_cookie_required",
                "runtime.production_shared_admin_token_forbidden",
                "runtime.trusted_host_invalid",
            },
        )
        self.assertNotIn(database_secret, str(caught.exception))
        self.assertNotIn(admin_secret, str(caught.exception))

    def test_production_requires_database_url_and_deepseek_key(self):
        configured = self._production_settings(
            database_url="",
            llm_provider="deepseek",
            deepseek_api_key="",
        )

        with self.assertRaises(RuntimeConfigurationError) as caught:
            validate_runtime_configuration(configured)

        self.assertEqual(
            {issue.code for issue in caught.exception.issues},
            {
                "runtime.production_database_url_required",
                "runtime.production_llm_key_required",
            },
        )

    def test_production_requires_postgres_with_verified_tls(self):
        cases = (
            (
                "sqlite:///data/chronovita.db",
                "runtime.production_postgres_required",
            ),
            (
                "postgresql://chrono:secret@db/chronovita?sslmode=require",
                "runtime.production_database_tls_required",
            ),
            (
                "not a database URL",
                "runtime.production_database_url_invalid",
            ),
        )

        for database_url, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                configured = self._production_settings(database_url=database_url)
                with self.assertRaises(RuntimeConfigurationError) as caught:
                    validate_runtime_configuration(configured)
                self.assertEqual(
                    {issue.code for issue in caught.exception.issues},
                    {expected_code},
                )

    def test_production_requires_a_trusted_https_deepseek_endpoint(self):
        configured = self._production_settings(
            llm_provider="deepseek",
            deepseek_api_key="model-key",
            deepseek_base_url="https://api.deepseek.com/v1",
        )
        validate_runtime_configuration(configured)

        cases = (
            (
                {"deepseek_base_url": "http://api.deepseek.com"},
                "runtime.production_llm_endpoint_untrusted",
            ),
            (
                {"deepseek_base_url": "https://untrusted.example.test"},
                "runtime.production_llm_endpoint_untrusted",
            ),
            (
                {
                    "deepseek_base_url": (
                        "https://operator:secret@api.deepseek.com"
                    )
                },
                "runtime.production_llm_endpoint_untrusted",
            ),
            (
                {"deepseek_base_url": "https://api.deepseek.com?target=other"},
                "runtime.production_llm_endpoint_untrusted",
            ),
            (
                {
                    "deepseek_allowed_hosts": [
                        "api.deepseek.com",
                        "api.deepseek.com",
                    ]
                },
                "runtime.production_llm_allowed_hosts_invalid",
            ),
        )
        for overrides, expected_code in cases:
            with self.subTest(expected_code=expected_code, overrides=overrides):
                candidate = self._production_settings(
                    llm_provider="deepseek",
                    deepseek_api_key="model-key",
                    **overrides,
                )
                with self.assertRaises(RuntimeConfigurationError) as caught:
                    validate_runtime_configuration(candidate)
                self.assertEqual(
                    {issue.code for issue in caught.exception.issues},
                    {expected_code},
                )
                self.assertNotIn("operator:secret", str(caught.exception))

    def test_local_legacy_mode_requires_debug_and_complete_bootstrap_pair(self):
        configured = Settings(
            runtime_profile="local",
            debug=False,
            auth_mode="legacy-local",
            auth_bootstrap_username="root.admin",
            auth_bootstrap_password="",
            _env_file=None,
        )

        with self.assertRaises(RuntimeConfigurationError) as caught:
            validate_runtime_configuration(configured)

        self.assertEqual(
            {issue.code for issue in caught.exception.issues},
            {
                "runtime.bootstrap_credentials_incomplete",
                "runtime.local_legacy_requires_debug",
            },
        )

    def test_runtime_profiles_reject_hosts_outside_their_trust_boundary(self):
        local = Settings(
            runtime_profile="local",
            debug=True,
            auth_mode="legacy-local",
            trusted_hosts=["teacher.example.test"],
            _env_file=None,
        )
        production = self._production_settings(trusted_hosts=["localhost"])

        with self.assertRaises(RuntimeConfigurationError) as local_error:
            validate_runtime_configuration(local)
        with self.assertRaises(RuntimeConfigurationError) as production_error:
            validate_runtime_configuration(production)

        self.assertEqual(
            {issue.code for issue in local_error.exception.issues},
            {"runtime.local_legacy_trusted_host_invalid"},
        )
        self.assertEqual(
            {issue.code for issue in production_error.exception.issues},
            {"runtime.production_trusted_host_invalid"},
        )

    def test_runtime_secrets_are_masked_by_settings(self):
        secrets = (
            "admin-token-must-not-leak",
            "bootstrap-password-must-not-leak",
            "model-key-must-not-leak",
            "github-token-must-not-leak",
        )
        configured = Settings(
            admin_token=secrets[0],
            auth_bootstrap_password=secrets[1],
            deepseek_api_key=secrets[2],
            github_publication_token=secrets[3],
            _env_file=None,
        )

        rendered = repr(configured)
        for secret in secrets:
            self.assertNotIn(secret, rendered)

    def test_github_publication_requires_server_secret_and_trusted_https_api(self):
        cases = (
            (
                {
                    "github_publication_enabled": True,
                    "github_publication_token": "",
                },
                "runtime.github_publication_token_required",
            ),
            (
                {
                    "github_publication_enabled": True,
                    "github_publication_token": "server-secret",
                    "github_api_base_url": "http://api.github.com",
                },
                "runtime.github_publication_endpoint_untrusted",
            ),
            (
                {
                    "github_publication_enabled": True,
                    "github_publication_token": "server-secret",
                    "github_api_base_url": "https://127.0.0.1",
                },
                "runtime.github_publication_endpoint_untrusted",
            ),
            (
                {
                    "github_publication_enabled": True,
                    "github_publication_token": "server-secret",
                    "github_api_base_url": "https://collector.example",
                },
                "runtime.github_publication_endpoint_untrusted",
            ),
        )
        for overrides, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                configured = Settings(**overrides, _env_file=None)
                with self.assertRaises(RuntimeConfigurationError) as caught:
                    validate_runtime_configuration(configured)
                self.assertIn(
                    expected_code,
                    {issue.code for issue in caught.exception.issues},
                )
                self.assertNotIn("server-secret", str(caught.exception))

    def test_dotenv_can_be_disabled_for_the_isolated_local_launcher(self):
        with patch.dict(
            "os.environ",
            {"CHRONO_DISABLE_DOTENV": "true"},
            clear=False,
        ):
            self.assertIsNone(runtime_env_file())
        with patch.dict(
            "os.environ",
            {"CHRONO_DISABLE_DOTENV": "false"},
            clear=False,
        ):
            self.assertEqual(runtime_env_file(), ".env")

    @staticmethod
    def _production_settings(**overrides) -> Settings:
        values = {
            "runtime_profile": "production",
            "debug": False,
            "auth_mode": "accounts",
            "auth_cookie_secure": True,
            "database_migration_mode": "validate",
            "database_url": (
                "postgresql://chrono:secret@db/chronovita?sslmode=verify-full"
            ),
            "admin_token": "",
            "cors_origins": ["https://chronovita.example.test"],
            "trusted_hosts": ["chronovita.example.test"],
            "auth_bootstrap_username": "",
            "auth_bootstrap_password": "",
            "llm_provider": "mock",
            "deepseek_api_key": "",
        }
        values.update(overrides)
        return Settings(**values, _env_file=None)


class RequestBodyLimitTests(unittest.TestCase):
    def test_fastapi_rejects_oversized_body_before_authentication(self):
        authentication_calls = 0

        async def authenticate() -> None:
            nonlocal authentication_calls
            authentication_calls += 1

        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=10)

        @app.post("/bounded", dependencies=[Depends(authenticate)])
        async def bounded(payload: dict) -> dict:
            return payload

        with TestClient(app) as client:
            response = client.post(
                "/bounded",
                content=b"x" * 11,
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(authentication_calls, 0)

    def test_declared_oversized_body_is_rejected_without_reading(self):
        receive_calls = 0
        sent: list[dict] = []

        async def downstream(scope, receive, send):
            del scope, receive, send
            self.fail("downstream application must not run")

        async def receive():
            nonlocal receive_calls
            receive_calls += 1
            self.fail("declared oversized body must not be read")

        async def send(message):
            sent.append(message)

        middleware = RequestBodyLimitMiddleware(
            downstream,
            max_body_bytes=10,
        )
        asyncio.run(
            middleware(
                self._scope(headers=[(b"content-length", b"11")]),
                receive,
                send,
            )
        )

        self.assertEqual(receive_calls, 0)
        self._assert_too_large(sent)

    def test_chunked_oversized_body_stops_at_the_first_excess_chunk(self):
        chunks = [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"abcdef", "more_body": True},
            {"type": "http.request", "body": b"ignored", "more_body": False},
        ]
        receive_calls = 0
        sent: list[dict] = []

        async def downstream(scope, receive, send):
            del scope, send
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    return

        async def receive():
            nonlocal receive_calls
            message = chunks[receive_calls]
            receive_calls += 1
            return message

        async def send(message):
            sent.append(message)

        middleware = RequestBodyLimitMiddleware(
            downstream,
            max_body_bytes=10,
        )
        asyncio.run(middleware(self._scope(), receive, send))

        self.assertEqual(receive_calls, 2)
        self._assert_too_large(sent)

    def test_body_within_limit_reaches_the_application(self):
        chunks = [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": False},
        ]
        sent: list[dict] = []

        async def downstream(scope, receive, send):
            del scope
            body = b""
            while True:
                message = await receive()
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    break
            self.assertEqual(body, b"12345678")
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        async def receive():
            return chunks.pop(0)

        async def send(message):
            sent.append(message)

        middleware = RequestBodyLimitMiddleware(
            downstream,
            max_body_bytes=10,
        )
        asyncio.run(middleware(self._scope(), receive, send))

        self.assertEqual(sent[0]["status"], 204)

    @staticmethod
    def _scope(*, headers: list[tuple[bytes, bytes]] | None = None) -> dict:
        return {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/practice/ask",
            "headers": headers or [],
            "state": {},
        }

    def _assert_too_large(self, sent: list[dict]) -> None:
        self.assertEqual(sent[0]["status"], 413)
        headers = dict(sent[0]["headers"])
        self.assertEqual(headers[b"cache-control"], b"no-store")
        payload = json.loads(sent[1]["body"])
        self.assertEqual(
            payload["detail"]["code"],
            "request_body_too_large",
        )


class RuntimeHealthTests(unittest.TestCase):
    def test_database_probe_reports_current_schema_and_fails_closed_on_drift(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(engine.dispose)
        ensure_current_schema(engine)

        healthy = probe_database_readiness(engine)
        self.assertEqual(healthy.dialect, "sqlite")
        self.assertEqual(
            healthy.current_schema_version,
            healthy.latest_schema_version,
        )

        with engine.begin() as connection:
            connection.execute(text("DROP TABLE kv"))
        with self.assertRaises(RuntimeReadinessError):
            probe_database_readiness(engine)

        with patch.object(
            engine,
            "connect",
            side_effect=RuntimeError("forced connection failure"),
        ):
            with self.assertRaises(RuntimeReadinessError):
                probe_database_connectivity(engine)

    def test_health_endpoints_separate_liveness_from_dependency_readiness(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        previous = {
            "runtime_profile": settings.runtime_profile,
            "debug": settings.debug,
            "auth_mode": settings.auth_mode,
            "sqlite_path": settings.sqlite_path,
            "database_url": settings.database_url,
            "database_migration_mode": settings.database_migration_mode,
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
        }
        self.addCleanup(self._restore_settings, previous)
        settings.runtime_profile = "local"
        settings.debug = True
        settings.auth_mode = "legacy-local"
        settings.sqlite_path = str(Path(temp_dir.name) / "chronovita.db")
        settings.database_url = type(settings.database_url)("")
        settings.database_migration_mode = "apply-safe"
        settings.content_root = str(REPO_ROOT / "content")
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        persistence.close_engine()
        self.addCleanup(persistence.close_engine)

        with TestClient(api_main.app) as client:
            live = client.get("/healthz")
            ready = client.get("/readyz")
            self.assertEqual(live.status_code, 200, live.text)
            self.assertRegex(live.headers["X-Request-ID"], r"^req_[0-9a-f]{32}$")
            self.assertEqual(live.json()["status"], "alive")
            self.assertEqual(ready.status_code, 200, ready.text)
            self.assertEqual(ready.json()["status"], "ready")
            self.assertEqual(ready.json()["checks"]["schema"]["status"], "ok")

            with patch.object(
                api_main,
                "probe_database_connectivity",
                side_effect=RuntimeReadinessError("forced failure"),
            ):
                unavailable = client.get("/readyz")
                still_live = client.get("/healthz")
            self.assertEqual(unavailable.status_code, 503, unavailable.text)
            self.assertEqual(
                unavailable.json(),
                {
                    "status": "not_ready",
                    "code": "runtime_dependency_unavailable",
                },
            )
            self.assertEqual(still_live.status_code, 200, still_live.text)

    @staticmethod
    def _restore_settings(previous: dict[str, object]) -> None:
        for key, value in previous.items():
            setattr(settings, key, value)
        persistence.close_engine()


if __name__ == "__main__":
    unittest.main()
