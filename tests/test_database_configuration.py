from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL
from sqlalchemy.schema import CreateTable

from apps.api.settings import Settings
from services.auth.store import (
    audit_events_table,
    audit_head_table,
    sessions_table,
    users_table,
)
from services.game_runtime.store import game_dossiers_table, game_sessions_table
from services.persistence import db
from services.persistence.database import (
    DatabaseDriverUnavailable,
    DatabaseEngineConflict,
    DatabaseEngineOptions,
    DatabaseEngineOptionsInvalid,
    DatabaseUrlInvalid,
    UnsupportedDatabaseDialect,
    UnsupportedDatabaseDriver,
    create_database_engine,
    resolve_database_target,
)
from services.persistence.db import kv_table
from services.persistence.schema import schema_migrations_table


class DatabaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-database-config-tests" / uuid4().hex
        self.tmp_root.mkdir(parents=True)
        db.close_engine()

    def tearDown(self):
        db.close_engine()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_compatibility_sqlite_path_resolves_from_explicit_root(self):
        target = resolve_database_target(
            database_url="",
            sqlite_path="data/chronovita.db",
            relative_to=self.tmp_root,
        )

        self.assertEqual(target.dialect, "sqlite")
        self.assertEqual(target.source, "sqlite-path")
        self.assertEqual(
            target.sqlite_path,
            (self.tmp_root / "data" / "chronovita.db").resolve(),
        )

    def test_explicit_sqlite_url_takes_priority_and_resolves_relative_path(self):
        ignored = self.tmp_root / "ignored.db"
        target = resolve_database_target(
            database_url="sqlite:///selected/chronovita.db",
            sqlite_path=str(ignored),
            relative_to=self.tmp_root,
        )

        self.assertEqual(target.source, "database-url")
        self.assertEqual(
            target.sqlite_path,
            (self.tmp_root / "selected" / "chronovita.db").resolve(),
        )
        self.assertNotEqual(target.sqlite_path, ignored)

    def test_postgres_url_defaults_to_psycopg_without_exposing_secrets(self):
        password = "database-password-must-stay-secret"
        query_secret = "client-key-must-stay-secret"
        target = resolve_database_target(
            database_url=(
                "postgresql://chrono:"
                f"{password}@db.internal/chronovita?application_name={query_secret}"
            ),
            sqlite_path="ignored.db",
        )

        self.assertEqual(target.dialect, "postgresql")
        self.assertEqual(target.source, "database-url")
        self.assertEqual(target.url.drivername, "postgresql+psycopg")
        self.assertEqual(target.url.password, password)
        self.assertNotIn(password, repr(target))
        self.assertNotIn(query_secret, repr(target))

    def test_invalid_dialect_and_driver_fail_closed_without_raw_url(self):
        secret = "do-not-echo-this-password"
        with self.assertRaises(UnsupportedDatabaseDialect) as dialect_error:
            resolve_database_target(
                database_url=f"mysql://teacher:{secret}@db.internal/chronovita",
                sqlite_path="ignored.db",
            )
        self.assertNotIn(secret, str(dialect_error.exception))

        with self.assertRaises(UnsupportedDatabaseDriver):
            resolve_database_target(
                database_url="postgresql+psycopg2://db.internal/chronovita",
                sqlite_path="ignored.db",
            )
        with self.assertRaises(DatabaseUrlInvalid):
            resolve_database_target(
                database_url="not a valid database URL",
                sqlite_path="ignored.db",
            )

    def test_sqlite_url_rejects_network_credentials(self):
        with self.assertRaises(DatabaseUrlInvalid):
            resolve_database_target(
                database_url="sqlite://teacher:password@localhost/chronovita.db",
                sqlite_path="ignored.db",
            )

    def test_secret_setting_masks_database_url(self):
        password = "settings-password-must-stay-secret"
        configured = Settings(
            database_url=f"postgresql://chrono:{password}@db/chronovita",
            _env_file=None,
        )

        self.assertEqual(configured.database_url.get_secret_value().split(":")[0], "postgresql")
        self.assertNotIn(password, repr(configured))

    def test_init_engine_uses_database_url_before_compatibility_path(self):
        selected = self.tmp_root / "selected.db"
        ignored = self.tmp_root / "ignored.db"
        database_url = URL.create("sqlite", database=str(selected)).render_as_string(
            hide_password=False
        )

        engine = db.init_engine(
            str(ignored),
            database_url=database_url,
        )

        self.assertEqual(engine.dialect.name, "sqlite")
        self.assertTrue(selected.exists())
        self.assertFalse(ignored.exists())

    def test_initialized_engine_rejects_a_different_target(self):
        first = self.tmp_root / "first.db"
        second = self.tmp_root / "second.db"
        db.init_engine(str(first))

        with self.assertRaises(DatabaseEngineConflict):
            db.init_engine(str(second))
        self.assertFalse(second.exists())

    def test_memory_sqlite_uses_one_database_across_connections(self):
        target = resolve_database_target(
            database_url="sqlite:///:memory:",
            sqlite_path="ignored.db",
        )
        engine = create_database_engine(target)
        try:
            first = engine.connect()
            second = engine.connect()
            try:
                first.execute(text("CREATE TABLE shared_state (value INTEGER)"))
                first.execute(text("INSERT INTO shared_state VALUES (7)"))
                first.commit()
                self.assertEqual(
                    second.execute(text("SELECT value FROM shared_state")).scalar_one(),
                    7,
                )
            finally:
                second.close()
                first.close()
        finally:
            engine.dispose()

    def test_postgres_engine_can_be_built_without_connecting(self):
        target = resolve_database_target(
            database_url="postgresql://chrono:secret@127.0.0.1:1/chronovita",
            sqlite_path="ignored.db",
        )

        engine = create_database_engine(target)
        try:
            self.assertEqual(engine.dialect.name, "postgresql")
            self.assertEqual(engine.url.drivername, "postgresql+psycopg")
        finally:
            engine.dispose()

    def test_postgres_engine_applies_explicit_pool_and_connect_limits(self):
        target = resolve_database_target(
            database_url="postgresql://chrono:secret@db/chronovita",
            sqlite_path="ignored.db",
        )
        options = DatabaseEngineOptions(
            pool_size=7,
            max_overflow=3,
            pool_timeout_seconds=12.5,
            pool_recycle_seconds=900,
            connect_timeout_seconds=4,
        )
        fake_engine = Mock()
        fake_engine.dialect.name = "postgresql"

        with patch(
            "services.persistence.database.create_engine",
            return_value=fake_engine,
        ) as factory:
            created = create_database_engine(target, options=options)

        self.assertIs(created, fake_engine)
        kwargs = factory.call_args.kwargs
        self.assertTrue(kwargs["pool_pre_ping"])
        self.assertEqual(kwargs["pool_size"], 7)
        self.assertEqual(kwargs["max_overflow"], 3)
        self.assertEqual(kwargs["pool_timeout"], 12.5)
        self.assertEqual(kwargs["pool_recycle"], 900)
        self.assertEqual(kwargs["connect_args"], {"connect_timeout": 4})

    def test_database_engine_options_reject_invalid_bounds(self):
        invalid_options = (
            {"pool_size": 0},
            {"pool_size": 101},
            {"max_overflow": -1},
            {"max_overflow": 101},
            {"pool_timeout_seconds": 301},
            {"pool_recycle_seconds": 29},
            {"connect_timeout_seconds": 61},
        )
        for values in invalid_options:
            with self.subTest(values=values):
                with self.assertRaises(DatabaseEngineOptionsInvalid):
                    DatabaseEngineOptions(**values)

    def test_driver_load_failure_is_sanitized(self):
        secret = "driver-error-secret"
        target = resolve_database_target(
            database_url=f"postgresql://chrono:{secret}@db/chronovita",
            sqlite_path="ignored.db",
        )

        with patch(
            "services.persistence.database.create_engine",
            side_effect=ModuleNotFoundError(f"missing module near {secret}"),
        ):
            with self.assertRaises(DatabaseDriverUnavailable) as caught:
                create_database_engine(target)
        self.assertNotIn(secret, str(caught.exception))

    def test_all_registered_tables_compile_for_postgres(self):
        tables = (
            kv_table,
            game_sessions_table,
            game_dossiers_table,
            users_table,
            sessions_table,
            audit_head_table,
            audit_events_table,
            schema_migrations_table,
        )

        for table in tables:
            ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
            self.assertIn(f"CREATE TABLE {table.name}", ddl)
            self.assertNotIn("AUTOINCREMENT", ddl.upper())
            self.assertNotIn("PRAGMA", ddl.upper())


if __name__ == "__main__":
    unittest.main()
