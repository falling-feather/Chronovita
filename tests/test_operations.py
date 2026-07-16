from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import main as api_main
from settings import Settings, settings
from services import persistence
from services.operations import (
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
        )

        with self.assertRaises(RuntimeConfigurationError) as caught:
            validate_runtime_configuration(configured)

        codes = {issue.code for issue in caught.exception.issues}
        self.assertEqual(
            codes,
            {
                "runtime.production_accounts_required",
                "runtime.production_cors_origin_invalid",
                "runtime.production_debug_disabled",
                "runtime.production_schema_validate_required",
                "runtime.production_secure_cookie_required",
                "runtime.production_shared_admin_token_forbidden",
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

    @staticmethod
    def _production_settings(**overrides) -> Settings:
        values = {
            "runtime_profile": "production",
            "debug": False,
            "auth_mode": "accounts",
            "auth_cookie_secure": True,
            "database_migration_mode": "validate",
            "database_url": "postgresql://chrono:secret@db/chronovita",
            "admin_token": "",
            "cors_origins": ["https://chronovita.example.test"],
            "auth_bootstrap_username": "",
            "auth_bootstrap_password": "",
            "llm_provider": "mock",
            "deepseek_api_key": "",
        }
        values.update(overrides)
        return Settings(**values, _env_file=None)


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
