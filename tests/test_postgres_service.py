from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts import manage_database as database_cli
from scripts.provision_postgres_test import (
    POSTGRES_CLI_SCHEMA,
    POSTGRES_LOCK_SCHEMA,
    POSTGRES_MIGRATOR_ROLE,
    POSTGRES_RUNTIME_ROLE,
    POSTGRES_RUNTIME_SCHEMA,
)
from services.auth import (
    AuthService,
    AuthServiceConfig,
    LastAdminRequired,
    Principal,
    SessionUnavailable,
)
from services.auth.store import AuditWrite, AuthStore
from services.persistence import db as persistence_db
from services.persistence.database import (
    DatabaseEngineOptions,
    create_database_engine,
    resolve_database_target,
)
from services.persistence.schema import (
    DatabaseMigrationBusy,
    LATEST_SCHEMA_VERSION,
    _POSTGRES_MIGRATION_LOCK_ID,
    ensure_current_schema,
    inspect_schema,
    schema_migrations_table,
)


POSTGRES_MIGRATION_URL = os.environ.get(
    "CHRONO_TEST_POSTGRES_MIGRATION_URL",
    "",
).strip()
POSTGRES_RUNTIME_URL = os.environ.get(
    "CHRONO_TEST_POSTGRES_RUNTIME_URL",
    "",
).strip()
POSTGRES_MATRIX_CONFIGURED = bool(POSTGRES_MIGRATION_URL or POSTGRES_RUNTIME_URL)
RUNTIME_TABLE_PRIVILEGES = {
    "chronovita_schema_migrations": frozenset({"SELECT"}),
    "kv": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "game_sessions": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "game_dossiers": frozenset({"SELECT", "INSERT"}),
    "auth_users": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "auth_sessions": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "auth_audit_head": frozenset({"SELECT", "UPDATE"}),
    "auth_audit_events": frozenset({"SELECT", "INSERT"}),
}
TABLE_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)


@unittest.skipUnless(
    POSTGRES_MATRIX_CONFIGURED,
    (
        "CHRONO_TEST_POSTGRES_MIGRATION_URL and "
        "CHRONO_TEST_POSTGRES_RUNTIME_URL are required for the dedicated "
        "PostgreSQL service matrix"
    ),
)
class PostgresServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not POSTGRES_MIGRATION_URL or not POSTGRES_RUNTIME_URL:
            raise AssertionError(
                "PostgreSQL service matrix requires both role-specific URLs"
            )
        if "CHRONO_TEST_POSTGRES_ADMIN_URL" in os.environ:
            raise AssertionError(
                "PostgreSQL service test process must not receive the admin URL"
            )
        cls.migration_url = POSTGRES_MIGRATION_URL
        cls.runtime_url = POSTGRES_RUNTIME_URL

    def test_postgres_migration_cli_and_application_runtime(self):
        target = resolve_database_target(
            database_url=self.migration_url,
            sqlite_path="ignored.db",
        )
        self.assertEqual(target.dialect, "postgresql")
        self.assertEqual(target.url.username, POSTGRES_MIGRATOR_ROLE)
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

        self._grant_runtime_privileges(first)
        self._verify_postgres_cli(target)
        self._verify_migration_lock_timeout(target)
        first.dispose()
        second.dispose()

        runtime_target = resolve_database_target(
            database_url=self.runtime_url,
            sqlite_path="ignored.db",
        )
        self.assertEqual(runtime_target.url.username, POSTGRES_RUNTIME_ROLE)
        self.assertEqual(runtime_target.url.host, target.url.host)
        self.assertEqual(runtime_target.url.port, target.url.port)
        self.assertEqual(runtime_target.url.database, target.url.database)
        runtime_first = create_database_engine(runtime_target, options=options)
        runtime_second = create_database_engine(runtime_target, options=options)
        self.addCleanup(runtime_first.dispose)
        self.addCleanup(runtime_second.dispose)
        self.assertTrue(inspect_schema(runtime_first).is_current)
        self._verify_role_boundaries(first=runtime_first, migration_target=target)
        self._verify_concurrent_audit(runtime_first, runtime_second)
        self._verify_identity_invariants(runtime_first, runtime_second)
        self._verify_kv_invariants()
        runtime_first.dispose()
        runtime_second.dispose()
        self._verify_application_runtime()

    def _verify_postgres_cli(self, target) -> None:
        schema_name = POSTGRES_CLI_SCHEMA
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

    def _verify_migration_lock_timeout(self, target) -> None:
        schema_name = POSTGRES_LOCK_SCHEMA
        lock_url = target.url.update_query_dict(
            {"options": f"-c search_path={schema_name}"}
        ).render_as_string(hide_password=False)
        lock_target = resolve_database_target(
            database_url=lock_url,
            sqlite_path="ignored.db",
        )
        lock_engine = create_database_engine(
            lock_target,
            options=DatabaseEngineOptions(
                pool_size=2,
                max_overflow=1,
                pool_timeout_seconds=5,
                pool_recycle_seconds=60,
                connect_timeout_seconds=3,
                migration_lock_timeout_seconds=0.2,
            ),
        )
        try:
            self.assertEqual(inspect(lock_engine).get_table_names(), [])
            with lock_engine.connect() as blocker:
                blocker.execute(
                    text("SELECT pg_advisory_lock(:lock_id)"),
                    {"lock_id": _POSTGRES_MIGRATION_LOCK_ID},
                )
                blocker.commit()
                started = monotonic()
                try:
                    with self.assertRaises(DatabaseMigrationBusy):
                        ensure_current_schema(
                            lock_engine,
                            migration_lock_timeout_seconds=0.2,
                        )
                    elapsed = monotonic() - started
                    self.assertGreaterEqual(elapsed, 0.15)
                    self.assertLess(elapsed, 2)
                    self.assertEqual(inspect(lock_engine).get_table_names(), [])
                finally:
                    released = blocker.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": _POSTGRES_MIGRATION_LOCK_ID},
                    ).scalar_one()
                    blocker.commit()
                    self.assertTrue(released)

            self.assertTrue(ensure_current_schema(lock_engine).is_current)
        finally:
            lock_engine.dispose()

    def _grant_runtime_privileges(self, migration_engine) -> None:
        with migration_engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            schema = quote(POSTGRES_RUNTIME_SCHEMA)
            runtime = quote(POSTGRES_RUNTIME_ROLE)
            connection.exec_driver_sql(
                f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} "
                f"FROM {runtime}"
            )
            connection.exec_driver_sql(
                f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} "
                f"FROM {runtime}"
            )
            connection.exec_driver_sql(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                f"REVOKE ALL ON TABLES FROM {runtime}"
            )
            connection.exec_driver_sql(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                f"REVOKE ALL ON SEQUENCES FROM {runtime}"
            )
            for table_name, privileges in RUNTIME_TABLE_PRIVILEGES.items():
                privilege_list = ", ".join(sorted(privileges))
                connection.exec_driver_sql(
                    f"GRANT {privilege_list} ON TABLE {quote(table_name)} "
                    f"TO {runtime}"
                )

    def _verify_role_boundaries(self, *, first, migration_target) -> None:
        migration_engine = create_database_engine(
            migration_target,
            options=DatabaseEngineOptions(
                pool_size=1,
                max_overflow=0,
                pool_timeout_seconds=5,
                pool_recycle_seconds=60,
                connect_timeout_seconds=3,
            ),
        )
        try:
            with migration_engine.connect() as connection:
                self._assert_role_flags(connection, POSTGRES_MIGRATOR_ROLE)
                self.assertTrue(
                    connection.execute(
                        text(
                            "SELECT has_schema_privilege("
                            "current_user, current_schema(), 'CREATE'"
                            ")"
                        )
                    ).scalar_one()
                )
                self.assertFalse(
                    connection.execute(
                        text(
                            "SELECT has_database_privilege("
                            "current_user, current_database(), 'CREATE'"
                            ")"
                        )
                    ).scalar_one()
                )
                self.assertFalse(
                    connection.execute(
                        text(
                            "SELECT has_database_privilege("
                            "current_user, current_database(), 'TEMP'"
                            ")"
                        )
                    ).scalar_one()
                )

            with first.connect() as connection:
                self._assert_role_flags(connection, POSTGRES_RUNTIME_ROLE)
                managed_tables = set(inspect(connection).get_table_names())
                self.assertEqual(
                    managed_tables,
                    set(RUNTIME_TABLE_PRIVILEGES),
                )
                self.assertTrue(
                    connection.execute(
                        text(
                            "SELECT has_schema_privilege("
                            "current_user, current_schema(), 'USAGE'"
                            ")"
                        )
                    ).scalar_one()
                )
                self.assertFalse(
                    connection.execute(
                        text(
                            "SELECT has_schema_privilege("
                            "current_user, current_schema(), 'CREATE'"
                            ")"
                        )
                    ).scalar_one()
                )
                for privilege in ("CREATE", "TEMP"):
                    self.assertFalse(
                        connection.execute(
                            text(
                                "SELECT has_database_privilege("
                                "current_user, current_database(), :privilege"
                                ")"
                            ),
                            {"privilege": privilege},
                        ).scalar_one()
                    )
                for table_name, expected in RUNTIME_TABLE_PRIVILEGES.items():
                    for privilege in TABLE_PRIVILEGES:
                        with self.subTest(
                            table=table_name,
                            privilege=privilege,
                        ):
                            actual = connection.execute(
                                text(
                                    "SELECT has_table_privilege("
                                    "current_user, :table_name, :privilege"
                                    ")"
                                ),
                                {
                                    "table_name": table_name,
                                    "privilege": privilege,
                                },
                            ).scalar_one()
                            self.assertEqual(actual, privilege in expected)
                owners = connection.execute(
                    text(
                        "SELECT DISTINCT pg_get_userbyid(c.relowner) "
                        "FROM pg_class AS c "
                        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = current_schema() "
                        "AND c.relkind IN ('r', 'p', 'S')"
                    )
                ).scalars().all()
                self.assertEqual(set(owners), {POSTGRES_MIGRATOR_ROLE})

            denied_statements = (
                "CREATE TABLE runtime_escape (id integer)",
                "CREATE TABLE public.runtime_escape (id integer)",
                "CREATE TEMP TABLE runtime_escape (id integer)",
                "CREATE SCHEMA runtime_escape",
                "ALTER TABLE kv ADD COLUMN runtime_escape integer",
                "DROP TABLE kv",
                "TRUNCATE TABLE kv",
                f"SET ROLE {POSTGRES_MIGRATOR_ROLE}",
                (
                    "UPDATE chronovita_schema_migrations "
                    "SET contract_checksum = contract_checksum "
                    "WHERE version = 1"
                ),
                "UPDATE auth_audit_events SET outcome = outcome",
                "DELETE FROM auth_audit_events",
                "DELETE FROM kv",
                "UPDATE game_dossiers SET data = data",
            )
            for statement in denied_statements:
                with self.subTest(statement=statement):
                    self._assert_permission_denied(first, statement)
            self._verify_future_objects_are_not_granted(
                migration_engine,
                first,
            )
        finally:
            migration_engine.dispose()

    def _verify_future_objects_are_not_granted(
        self,
        migration_engine,
        runtime_engine,
    ) -> None:
        table_name = "acl_future_canary"
        sequence_name = "acl_future_canary_seq"
        with migration_engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TABLE {table_name} (id integer)"
            )
            connection.exec_driver_sql(f"CREATE SEQUENCE {sequence_name}")
        try:
            self._assert_permission_denied(
                runtime_engine,
                f"SELECT * FROM {table_name}",
            )
            self._assert_permission_denied(
                runtime_engine,
                f"SELECT nextval('{sequence_name}')",
            )
        finally:
            with migration_engine.begin() as connection:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table_name}")
                connection.exec_driver_sql(
                    f"DROP SEQUENCE IF EXISTS {sequence_name}"
                )

    def _assert_permission_denied(self, engine, statement: str) -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with self.assertRaises(DBAPIError) as raised:
                    connection.exec_driver_sql(statement)
                self.assertEqual(
                    getattr(raised.exception.orig, "sqlstate", None),
                    "42501",
                )
            finally:
                transaction.rollback()
                try:
                    connection.exec_driver_sql("RESET ROLE")
                    connection.rollback()
                except BaseException:
                    connection.invalidate()
                    raise

    def _assert_role_flags(self, connection, expected_role: str) -> None:
        row = connection.execute(
            text(
                "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, "
                "rolinherit, rolreplication, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        self.assertEqual(row.rolname, expected_role)
        self.assertFalse(row.rolsuper)
        self.assertFalse(row.rolcreatedb)
        self.assertFalse(row.rolcreaterole)
        self.assertFalse(row.rolinherit)
        self.assertFalse(row.rolreplication)
        self.assertFalse(row.rolbypassrls)

    def _verify_concurrent_audit(self, first, second) -> None:
        write_count = 32
        start = threading.Event()
        stop = threading.Event()
        failures: list[str] = []
        failure_lock = threading.Lock()
        stores = tuple(
            AuthStore(first if index % 2 == 0 else second)
            for index in range(8)
        )
        verifier = AuthStore(second)

        def verify_while_writing() -> None:
            if not start.wait(timeout=10):
                raise AssertionError("concurrent audit start timed out")
            while not stop.is_set():
                try:
                    if not verifier.verify_audit_chain():
                        raise AssertionError("audit chain reported an invalid snapshot")
                    if not inspect_schema(second).is_current:
                        raise AssertionError("schema inspection reported a stale snapshot")
                except Exception as exc:
                    with failure_lock:
                        failures.append(f"{type(exc).__name__}: {exc}")
                    stop.set()

        def append_event(index: int):
            if not start.wait(timeout=10):
                raise AssertionError("concurrent audit start timed out")
            return stores[index % len(stores)].append_audit(
                occurred_at=datetime.now(timezone.utc),
                actor_user_id=None,
                actor_session_id=None,
                actor_roles=(),
                action="qa.audit.concurrent",
                resource_type="postgres-service",
                resource_id=f"event-{index:03d}",
                outcome="succeeded",
                request_id=f"postgres-audit-{index:03d}",
            )

        with ThreadPoolExecutor(max_workers=9) as executor:
            verification = executor.submit(verify_while_writing)
            writes = tuple(
                executor.submit(append_event, index)
                for index in range(write_count)
            )
            start.set()
            try:
                events = tuple(future.result(timeout=15) for future in writes)
            finally:
                stop.set()
            verification.result(timeout=15)

        self.assertEqual(failures, [])
        self.assertEqual(
            sorted(event.sequence for event in events),
            list(range(1, write_count + 1)),
        )
        self.assertTrue(verifier.verify_audit_chain())
        self.assertTrue(inspect_schema(first).is_current)

    def _verify_identity_invariants(self, first, second) -> None:
        config = AuthServiceConfig(
            mode="accounts",
            session_ttl_seconds=3600,
            session_idle_timeout_seconds=900,
            session_absolute_ttl_seconds=7200,
            bootstrap_username="ci.admin",
            bootstrap_password="CI admin password 123!",
            bootstrap_display_name="CI Admin",
        )
        bootstrap_barrier = threading.Barrier(4)

        def start_service(engine):
            bootstrap_barrier.wait(timeout=10)
            return AuthService(engine, config)

        with ThreadPoolExecutor(max_workers=4) as executor:
            services = tuple(
                executor.map(start_service, (first, second, first, second))
            )

        users = services[0].store.list_users()
        self.assertEqual([user.username for user in users], ["ci.admin"])
        self.assertEqual(
            len(
                [
                    event
                    for event in services[0].store.list_audit(limit=200)
                    if event.action == "auth.bootstrap"
                ]
            ),
            1,
        )
        root = users[0]
        root_actor = self._principal(root)
        second_admin = services[0].create_user(
            username="ci.admin.two",
            password="CI second admin password 123!",
            display_name="CI Admin Two",
            roles=("admin",),
            actor=root_actor,
            request_id="postgres-create-second-admin",
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
                    actor=root_actor,
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
                        (services[0], root.user_id, "postgres-demote-root"),
                        (
                            services[1],
                            second_admin.user_id,
                            "postgres-demote-second",
                        ),
                    ),
                )
            )

        self.assertEqual(sorted(results), ["blocked", "updated"])
        root = services[0].store.get_user(root.user_id)
        other = services[0].store.get_user(second_admin.user_id)
        self.assertIsNotNone(root)
        self.assertIsNotNone(other)
        if "admin" not in root.roles:
            services[0].update_user(
                root.user_id,
                display_name=None,
                roles=("admin",),
                enabled=None,
                actor=self._principal(other),
                request_id="postgres-restore-ci-admin",
            )
            root = services[0].store.get_user(root.user_id)
            services[0].update_user(
                other.user_id,
                display_name=None,
                roles=("teacher",),
                enabled=None,
                actor=self._principal(root),
                request_id="postgres-demote-temporary-admin",
            )

        enabled_admins = [
            user
            for user in services[0].store.list_users()
            if user.enabled and "admin" in user.roles
        ]
        self.assertEqual([user.username for user in enabled_admins], ["ci.admin"])

        issued = services[0].login(
            "ci.admin",
            "CI admin password 123!",
            request_id="postgres-session-login",
            transport="bearer",
        )
        refresh_barrier = threading.Barrier(2)

        def refresh_session(service, index: int):
            refresh_barrier.wait(timeout=10)
            try:
                return service.refresh(
                    issued.token,
                    issued.principal,
                    request_id=f"postgres-session-refresh-{index}",
                    transport="bearer",
                )
            except SessionUnavailable:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            refreshed = tuple(
                executor.map(
                    lambda args: refresh_session(*args),
                    ((services[0], 0), (services[1], 1)),
                )
            )
        winners = [session for session in refreshed if session is not None]
        self.assertEqual(len(winners), 1)
        self.assertIsNone(
            services[0].authenticate(issued.token, transport="bearer"),
        )
        self.assertIsNotNone(
            services[1].authenticate(winners[0].token, transport="bearer"),
        )

        extra = services[0].login(
            "ci.admin",
            "CI admin password 123!",
            request_id="postgres-session-extra",
            transport="bearer",
        )
        updated, revoked_count = services[1].revoke_user_sessions(
            root.user_id,
            actor=winners[0].principal,
            request_id="postgres-session-revoke-all",
        )
        self.assertGreaterEqual(revoked_count, 2)
        self.assertGreater(updated.auth_version, root.auth_version)
        for token in (winners[0].token, extra.token):
            self.assertIsNone(
                services[0].authenticate(token, transport="bearer"),
            )

        operator = services[0].login(
            "ci.admin",
            "CI admin password 123!",
            request_id="postgres-session-operator",
            transport="bearer",
        )
        target = services[0].create_user(
            username="ci.session.target",
            password="CI session target password 123!",
            display_name="CI Session Target",
            roles=("teacher",),
            actor=operator.principal,
            request_id="postgres-session-target-create",
        )

        def race_security_change(
            *,
            password: str,
            request_id: str,
            change,
        ) -> None:
            active = services[0].login(
                target.username,
                password,
                request_id=f"{request_id}-login",
                transport="bearer",
            )
            race_barrier = threading.Barrier(2)

            def refresh():
                race_barrier.wait(timeout=10)
                try:
                    return services[0].refresh(
                        active.token,
                        active.principal,
                        request_id=f"{request_id}-refresh",
                        transport="bearer",
                    )
                except SessionUnavailable:
                    return None

            def apply_change():
                race_barrier.wait(timeout=10)
                change()

            with ThreadPoolExecutor(max_workers=2) as executor:
                refresh_future = executor.submit(refresh)
                change_future = executor.submit(apply_change)
                rotated = refresh_future.result(timeout=15)
                change_future.result(timeout=15)

            self.assertIsNone(
                services[0].authenticate(active.token, transport="bearer"),
            )
            if rotated is not None:
                self.assertIsNone(
                    services[1].authenticate(
                        rotated.token,
                        transport="bearer",
                    ),
                )

        race_security_change(
            password="CI session target password 123!",
            request_id="postgres-refresh-vs-revoke",
            change=lambda: services[1].revoke_user_sessions(
                target.user_id,
                actor=operator.principal,
                request_id="postgres-refresh-vs-revoke-change",
            ),
        )
        race_security_change(
            password="CI session target password 123!",
            request_id="postgres-refresh-vs-disable",
            change=lambda: services[1].update_user(
                target.user_id,
                display_name=None,
                roles=None,
                enabled=False,
                actor=operator.principal,
                request_id="postgres-refresh-vs-disable-change",
            ),
        )
        services[0].update_user(
            target.user_id,
            display_name=None,
            roles=None,
            enabled=True,
            actor=operator.principal,
            request_id="postgres-session-target-reenable",
        )
        race_security_change(
            password="CI session target password 123!",
            request_id="postgres-refresh-vs-password",
            change=lambda: services[1].reset_password(
                target.user_id,
                password="CI session target password 456!",
                actor=operator.principal,
                request_id="postgres-refresh-vs-password-change",
            ),
        )
        self.assertTrue(services[0].store.verify_audit_chain())

    def _verify_kv_invariants(self) -> None:
        options = DatabaseEngineOptions(
            pool_size=4,
            max_overflow=4,
            pool_timeout_seconds=5,
            pool_recycle_seconds=60,
            connect_timeout_seconds=3,
        )
        persistence_db.init_engine(
            sqlite_path="ignored.db",
            database_url=self.runtime_url,
            migration_mode="validate",
            engine_options=options,
        )
        try:
            write_count = 16
            upsert_barrier = threading.Barrier(write_count)

            def set_shared(value: int) -> None:
                upsert_barrier.wait(timeout=10)
                persistence_db.kv_set(
                    "postgres-service-upsert",
                    "shared",
                    {"value": value},
                )

            with ThreadPoolExecutor(max_workers=write_count) as executor:
                tuple(executor.map(set_shared, range(write_count)))
            self.assertIn(
                persistence_db.kv_get("postgres-service-upsert", "shared")[
                    "value"
                ],
                range(write_count),
            )

            original = {"revision": 1, "nodes": []}
            persistence_db.kv_set("postgres-service-cas", "shared", original)
            cas_barrier = threading.Barrier(write_count)

            def replace_shared(revision: int) -> bool:
                cas_barrier.wait(timeout=10)
                return persistence_db.kv_compare_and_set(
                    "postgres-service-cas",
                    "shared",
                    original,
                    {"revision": revision, "nodes": []},
                    expected_present=True,
                )

            with ThreadPoolExecutor(max_workers=write_count) as executor:
                results = tuple(
                    executor.map(replace_shared, range(2, write_count + 2))
                )
            self.assertEqual(results.count(True), 1)

            persistence_db.kv_set(
                "postgres-service-cas",
                "legacy-format",
                original,
            )
            with persistence_db._engine().begin() as connection:
                connection.execute(
                    persistence_db.kv_table.update()
                    .where(
                        (
                            persistence_db.kv_table.c.namespace
                            == "postgres-service-cas"
                        )
                        & (persistence_db.kv_table.c.key == "legacy-format")
                    )
                    .values(data='{ "nodes": [ ], "revision": 1 }')
                )
            self.assertTrue(
                persistence_db.kv_compare_and_set(
                    "postgres-service-cas",
                    "legacy-format",
                    original,
                    {"revision": 2, "nodes": []},
                    expected_present=True,
                )
            )

            persistence_db.kv_set("postgres-service-cas", "null-value", None)
            self.assertTrue(
                persistence_db.kv_compare_and_set(
                    "postgres-service-cas",
                    "null-value",
                    None,
                    {"revision": 1},
                    expected_present=True,
                )
            )
        finally:
            persistence_db.close_engine()

    @staticmethod
    def _principal(user) -> Principal:
        return Principal(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            roles=user.roles,
            auth_version=user.auth_version,
        )

    def _verify_application_runtime(self) -> None:
        runtime_env = {
            "CHRONO_DISABLE_DOTENV": "true",
            "CHRONO_RUNTIME_PROFILE": "local",
            "CHRONO_DEBUG": "true",
            "CHRONO_DATABASE_URL": self.runtime_url,
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
            "/api/v1/auth/token",
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
