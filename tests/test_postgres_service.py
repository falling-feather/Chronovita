from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts import manage_database as database_cli
from services.persistence.database import (
    DatabaseEngineOptions,
    create_database_engine,
    resolve_database_target,
)
from services.persistence.schema import (
    LATEST_SCHEMA_VERSION,
    ensure_current_schema,
    inspect_schema,
    schema_migrations_table,
)


POSTGRES_URL = os.environ.get("CHRONO_TEST_POSTGRES_URL", "").strip()


@unittest.skipUnless(
    POSTGRES_URL,
    "CHRONO_TEST_POSTGRES_URL is required for the dedicated PostgreSQL service matrix",
)
class PostgresServiceTests(unittest.TestCase):
    def test_postgres_migration_cli_and_application_runtime(self):
        target = resolve_database_target(
            database_url=POSTGRES_URL,
            sqlite_path="ignored.db",
        )
        self.assertEqual(target.dialect, "postgresql")
        options = DatabaseEngineOptions(
            pool_size=3,
            max_overflow=2,
            pool_timeout_seconds=5,
            pool_recycle_seconds=60,
            connect_timeout_seconds=3,
        )
        first = create_database_engine(target, options=options)
        second = create_database_engine(target, options=options)
        self.addCleanup(first.dispose)
        self.addCleanup(second.dispose)

        self.assertEqual(inspect(first).get_table_names(), [])
        barrier = threading.Barrier(2)

        def migrate(engine):
            barrier.wait(timeout=10)
            return ensure_current_schema(engine)

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = tuple(executor.map(migrate, (first, second)))

        self.assertTrue(all(status.is_current for status in statuses))
        validated = inspect_schema(first)
        self.assertEqual(validated.dialect, "postgresql")
        self.assertEqual(validated.current_version, LATEST_SCHEMA_VERSION)
        with first.connect() as connection:
            versions = connection.execute(
                select(schema_migrations_table.c.version).order_by(
                    schema_migrations_table.c.version
                )
            ).scalars().all()
        self.assertEqual(versions, list(range(1, LATEST_SCHEMA_VERSION + 1)))

        self._verify_postgres_cli(first, target)
        first.dispose()
        second.dispose()
        self._verify_application_runtime()

    def _verify_postgres_cli(self, engine, target) -> None:
        schema_name = "chronovita_cli_matrix"
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA chronovita_cli_matrix")
        cli_url = target.url.update_query_dict(
            {"options": f"-c search_path={schema_name}"}
        ).render_as_string(hide_password=False)
        env_name = "CHRONO_TEST_POSTGRES_CLI_URL"

        with patch.dict(os.environ, {env_name: cli_url}, clear=False):
            migrated = self._run_cli(
                "migrate",
                "--database-url-env",
                env_name,
                "--initialize",
            )
            inspected = self._run_cli(
                "status",
                "--database-url-env",
                env_name,
            )

        for code, output, error in (migrated, inspected):
            self.assertEqual(code, 0, error)
            payload = json.loads(output)
            self.assertEqual(payload["result"]["dialect"], "postgresql")
            self.assertTrue(payload["result"]["is_current"])
            self.assertEqual(payload["result"]["database_url_env"], env_name)
            if target.url.password:
                self.assertNotIn(target.url.password, output)

    def _verify_application_runtime(self) -> None:
        runtime_env = {
            "CHRONO_DISABLE_DOTENV": "true",
            "CHRONO_RUNTIME_PROFILE": "local",
            "CHRONO_DEBUG": "true",
            "CHRONO_DATABASE_URL": POSTGRES_URL,
            "CHRONO_DATABASE_MIGRATION_MODE": "validate",
            "CHRONO_DATABASE_POOL_SIZE": "3",
            "CHRONO_DATABASE_MAX_OVERFLOW": "2",
            "CHRONO_DATABASE_POOL_TIMEOUT_SECONDS": "5",
            "CHRONO_DATABASE_POOL_RECYCLE_SECONDS": "60",
            "CHRONO_DATABASE_CONNECT_TIMEOUT_SECONDS": "3",
            "CHRONO_AUTH_MODE": "accounts",
            "CHRONO_AUTH_COOKIE_SECURE": "true",
            "CHRONO_AUTH_BOOTSTRAP_USERNAME": "ci.admin",
            "CHRONO_AUTH_BOOTSTRAP_PASSWORD": "CI admin password 123!",
            "CHRONO_AUTH_BOOTSTRAP_DISPLAY_NAME": "CI Admin",
            "CHRONO_CORS_ORIGINS": '["https://chronovita.example.test"]',
            "CHRONO_TRUSTED_HOSTS": '["chronovita.example.test"]',
            "CHRONO_CONTENT_ROOT": str(REPO_ROOT / "content"),
            "CHRONO_GAME_CATALOG_PATH": "scenarios/catalog.v1.json",
            "CHRONO_LLM_PROVIDER": "mock",
        }
        isolated_env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("CHRONO_")
        }
        isolated_env.update(runtime_env)
        with patch.dict(os.environ, isolated_env, clear=True):
            import main as api_main

            with TestClient(
                api_main.app,
                base_url="https://chronovita.example.test",
            ) as client:
                ready = client.get("/readyz")
                self.assertEqual(ready.status_code, 200, ready.text)
                self.assertEqual(ready.json()["status"], "ready")
                self.assertEqual(
                    ready.json()["checks"]["database"]["dialect"],
                    "postgresql",
                )
                self.assertEqual(
                    ready.json()["checks"]["schema"]["current_version"],
                    LATEST_SCHEMA_VERSION,
                )

                admin_token = self._login(
                    client,
                    username="ci.admin",
                    password="CI admin password 123!",
                )
                admin_headers = {"Authorization": f"Bearer {admin_token}"}
                created = client.post(
                    "/api/v1/auth/users",
                    headers=admin_headers,
                    json={
                        "username": "ci.student",
                        "password": "CI student password 123!",
                        "display_name": "CI Student",
                        "roles": ["student"],
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)

                student_token = self._login(
                    client,
                    username="ci.student",
                    password="CI student password 123!",
                )
                student_headers = {"Authorization": f"Bearer {student_token}"}
                progress = client.post(
                    "/api/v1/learning/progress/touch",
                    headers=student_headers,
                    json={
                        "lesson_id": "postgres-service-lesson",
                        "layer": "watch",
                        "completed": True,
                    },
                )
                self.assertEqual(progress.status_code, 200, progress.text)

                session = client.post(
                    "/api/v1/practice/game/sessions",
                    headers=student_headers,
                    json={
                        "scenario_id": "scenario-dayu-flood-control",
                        "client_request_id": "postgres-service-start-001",
                    },
                )
                self.assertEqual(session.status_code, 200, session.text)
                self.assertEqual(
                    session.json()["session"]["user_id"],
                    created.json()["user_id"],
                )

                client.cookies.clear()
                audit = client.get("/api/v1/auth/audit", headers=admin_headers)
                self.assertEqual(audit.status_code, 200, audit.text)
                self.assertTrue(audit.json()["valid_chain"])
                self.assertGreaterEqual(len(audit.json()["items"]), 4)

    @staticmethod
    def _login(client: TestClient, *, username: str, password: str) -> str:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return str(response.json()["access_token"])

    @staticmethod
    def _run_cli(*args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = database_cli.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
