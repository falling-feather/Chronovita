from __future__ import annotations

import shutil
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    event,
    insert,
    inspect,
    select,
    update,
)
from sqlalchemy.engine import Engine, URL

from services.auth.store import (
    AuthStore,
    audit_head_table,
    users_table,
)
from services.game_runtime.store import (
    game_dossiers_table,
    game_sessions_table,
)
from services.persistence import db
from services.persistence import schema as schema_module
from services.persistence.db import kv_table
from services.persistence.schema import (
    DatabaseMigrationHistoryError,
    DatabaseMigrationPending,
    DatabaseSchemaDrift,
    DatabaseSchemaTooNew,
    ensure_current_schema,
    inspect_schema,
    migration_contract_checksums,
    schema_migrations_table,
)


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-database-schema-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        db.close_engine()

    def tearDown(self):
        db.close_engine()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_empty_database_reaches_current_schema_idempotently(self):
        engine = self._engine("empty.db")
        try:
            first = ensure_current_schema(engine)
            with engine.connect() as connection:
                first_rows = connection.execute(
                    select(schema_migrations_table).order_by(
                        schema_migrations_table.c.version
                    )
                ).mappings().all()

            statements = []

            def capture_statement(
                _connection,
                _cursor,
                statement,
                _parameters,
                _context,
                _executemany,
            ):
                statements.append(statement)

            event.listen(engine, "before_cursor_execute", capture_statement)
            try:
                second = ensure_current_schema(engine)
            finally:
                event.remove(engine, "before_cursor_execute", capture_statement)
            with engine.connect() as connection:
                second_rows = connection.execute(
                    select(schema_migrations_table).order_by(
                        schema_migrations_table.c.version
                    )
                ).mappings().all()

            self.assertTrue(first.is_current)
            self.assertEqual(first.current_version, 3)
            self.assertEqual(second, first)
            self.assertEqual(second_rows, first_rows)
            self.assertFalse(
                any("BEGIN IMMEDIATE" in statement.upper() for statement in statements)
            )
            self.assertEqual(
                [row["version"] for row in second_rows],
                [1, 2, 3],
            )
        finally:
            engine.dispose()

    def test_validate_mode_is_read_only_and_requires_current_ledger(self):
        engine = self._engine("validate.db")
        try:
            with self.assertRaises(DatabaseMigrationPending) as raised:
                ensure_current_schema(engine, mode="validate")
            self.assertEqual(raised.exception.status.current_version, 0)
            self.assertEqual(inspect(engine).get_table_names(), [])

            ensure_current_schema(engine)
            status = ensure_current_schema(engine, mode="validate")
            self.assertTrue(status.is_current)
        finally:
            engine.dispose()

    def test_v08_layout_is_adopted_without_rewriting_business_data(self):
        engine = self._engine("legacy-v08.db")
        try:
            kv_table.metadata.create_all(engine)
            game_sessions_table.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(
                    insert(kv_table).values(
                        namespace="lesson_progress",
                        key="default:legacy-lesson",
                        data='{"progress":2}',
                        updated_at=NOW,
                    )
                )
                connection.execute(
                    insert(game_sessions_table).values(
                        session_id="legacy-session",
                        data='{"schema_version":"legacy"}',
                        updated_at=NOW,
                    )
                )
                connection.execute(
                    insert(game_dossiers_table).values(
                        dossier_id="legacy-dossier",
                        data='{"schema_version":"legacy"}',
                        updated_at=NOW,
                    )
                )

            status = ensure_current_schema(engine)

            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        select(kv_table.c.data).where(
                            kv_table.c.key == "default:legacy-lesson"
                        )
                    ).scalar_one(),
                    '{"progress":2}',
                )
                self.assertEqual(
                    connection.execute(
                        select(game_sessions_table.c.data)
                    ).scalar_one(),
                    '{"schema_version":"legacy"}',
                )
                self.assertEqual(
                    connection.execute(
                        select(game_dossiers_table.c.data)
                    ).scalar_one(),
                    '{"schema_version":"legacy"}',
                )
                head = connection.execute(select(audit_head_table)).mappings().one()
            self.assertTrue(status.is_current)
            self.assertEqual(head["sequence"], 0)
            self.assertEqual(head["event_hash"], "0" * 64)
        finally:
            engine.dispose()

    def test_v095_layout_is_adopted_without_rewriting_identity_data(self):
        engine = self._engine("legacy-v095.db")
        try:
            kv_table.metadata.create_all(engine)
            game_sessions_table.metadata.create_all(engine)
            AuthStore(engine)
            with engine.begin() as connection:
                connection.execute(
                    insert(users_table).values(
                        user_id="usr_legacy",
                        username="legacy.admin",
                        display_name="Legacy Admin",
                        password_hash="scrypt$legacy",
                        roles='["admin"]',
                        enabled=True,
                        auth_version=1,
                        created_at="2026-07-16T12:00:00Z",
                        updated_at="2026-07-16T12:00:00Z",
                    )
                )

            ensure_current_schema(engine)

            with engine.connect() as connection:
                row = connection.execute(select(users_table)).mappings().one()
            self.assertEqual(row["username"], "legacy.admin")
            self.assertEqual(row["password_hash"], "scrypt$legacy")
            self.assertTrue(inspect_schema(engine).is_current)
        finally:
            engine.dispose()

    def test_strict_adoption_rejects_partial_unknown_and_drifted_layouts(self):
        cases = {
            "partial": self._create_partial_layout,
            "unknown": self._create_unknown_layout,
            "drifted": self._create_drifted_layout,
            "non-prefix": self._create_non_prefix_layout,
        }
        for name, arrange in cases.items():
            with self.subTest(name=name):
                engine = self._engine(f"{name}.db")
                try:
                    arrange(engine)
                    before = set(inspect(engine).get_table_names())
                    with self.assertRaises(DatabaseSchemaDrift):
                        ensure_current_schema(engine)
                    after = set(inspect(engine).get_table_names())
                    self.assertEqual(after, before)
                    self.assertNotIn(schema_migrations_table.name, after)
                finally:
                    engine.dispose()

    def test_rewritten_gapped_and_too_new_ledgers_fail_closed(self):
        cases = {
            "rewritten": self._rewrite_checksum,
            "gapped": self._delete_middle_version,
            "too-new": self._append_future_version,
            "unregistered": self._leave_unregistered_tables,
        }
        expected = {
            "rewritten": DatabaseMigrationHistoryError,
            "gapped": DatabaseMigrationHistoryError,
            "too-new": DatabaseSchemaTooNew,
            "unregistered": DatabaseSchemaDrift,
        }
        for name, corrupt in cases.items():
            with self.subTest(name=name):
                engine = self._engine(f"history-{name}.db")
                try:
                    ensure_current_schema(engine)
                    corrupt(engine)
                    with self.assertRaises(expected[name]):
                        inspect_schema(engine)
                finally:
                    engine.dispose()

    def test_audit_invariant_tampering_is_rejected(self):
        engine = self._engine("audit-tamper.db")
        try:
            ensure_current_schema(engine)
            with engine.begin() as connection:
                connection.execute(
                    update(audit_head_table)
                    .where(audit_head_table.c.head_id == 1)
                    .values(sequence=1)
                )
            with self.assertRaises(DatabaseSchemaDrift):
                inspect_schema(engine)
        finally:
            engine.dispose()

    def test_migration_failure_rolls_back_tables_and_ledger(self):
        engine = self._engine("rollback.db")

        def fail_initialization(_connection):
            raise RuntimeError("injected migration failure")

        migrations = (
            *schema_module._MIGRATIONS[:2],
            replace(
                schema_module._MIGRATIONS[2],
                initialize=fail_initialization,
            ),
        )
        try:
            with patch.object(schema_module, "_MIGRATIONS", migrations):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    ensure_current_schema(engine)
            self.assertEqual(inspect(engine).get_table_names(), [])
        finally:
            engine.dispose()

    def test_concurrent_migration_produces_one_contiguous_history(self):
        path = self.tmp_root / "concurrent.db"
        engines = [self._engine_at(path), self._engine_at(path)]
        barrier = Barrier(2)

        def migrate(engine: Engine):
            barrier.wait(timeout=5)
            return ensure_current_schema(engine)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(migrate, engines))
            self.assertTrue(all(status.is_current for status in statuses))
            with engines[0].connect() as connection:
                versions = connection.execute(
                    select(schema_migrations_table.c.version).order_by(
                        schema_migrations_table.c.version
                    )
                ).scalars().all()
            self.assertEqual(versions, [1, 2, 3])
        finally:
            for engine in engines:
                engine.dispose()

    def test_persistence_engine_initialization_uses_schema_manager(self):
        path = self.tmp_root / "application.db"
        engine = db.init_engine(str(path))
        self.assertTrue(inspect_schema(engine).is_current)
        self.assertIn(schema_migrations_table.name, inspect(engine).get_table_names())

    def test_published_migration_contract_checksums_are_stable(self):
        self.assertEqual(
            migration_contract_checksums(),
            (
                "ef442876bcc86dde1d951c12c7fd7b9112ac47d635bdff4b51f580b4f3834230",
                "6088af90a040f4890eb682d9528bb443458af2d8ef467662fd9a0a0a9538912d",
                "94d49ee4d1e5e05bad4fc0f69cd394298c3789c1461df9f2b6205b69bb8652fe",
            ),
        )

        class PostgresInspector:
            @staticmethod
            def get_columns(_table_name):
                return [
                    {
                        "name": column.name,
                        "type": column.type,
                        "nullable": column.nullable,
                        "primary_key": int(column.primary_key),
                    }
                    for column in users_table.columns
                ]

            @staticmethod
            def get_pk_constraint(_table_name):
                return {"constrained_columns": ["user_id"]}

            @staticmethod
            def get_unique_constraints(_table_name):
                return [{"column_names": ["username"]}]

            @staticmethod
            def get_indexes(_table_name):
                return [
                    {
                        "column_names": ["username"],
                        "unique": True,
                        "duplicates_constraint": "uq_auth_users_username",
                    }
                ]

        with patch.object(
            schema_module,
            "inspect",
            return_value=PostgresInspector(),
        ):
            schema_module._validate_table(object(), users_table)

    def _engine(self, filename: str) -> Engine:
        return self._engine_at(self.tmp_root / filename)

    @staticmethod
    def _engine_at(path: Path) -> Engine:
        return create_engine(
            URL.create("sqlite", database=str(path)),
            connect_args={"check_same_thread": False},
            future=True,
        )

    @staticmethod
    def _create_partial_layout(engine: Engine) -> None:
        users_table.create(engine)

    @staticmethod
    def _create_unknown_layout(engine: Engine) -> None:
        metadata = MetaData()
        Table(
            "unmanaged_application_data",
            metadata,
            Column("id", Integer, primary_key=True),
        ).create(engine)

    @staticmethod
    def _create_drifted_layout(engine: Engine) -> None:
        metadata = MetaData()
        Table(
            "kv",
            metadata,
            Column("namespace", String, primary_key=True),
        ).create(engine)

    @staticmethod
    def _create_non_prefix_layout(engine: Engine) -> None:
        AuthStore(engine)

    @staticmethod
    def _rewrite_checksum(engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                update(schema_migrations_table)
                .where(schema_migrations_table.c.version == 1)
                .values(contract_checksum="f" * 64)
            )

    @staticmethod
    def _delete_middle_version(engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                delete(schema_migrations_table).where(
                    schema_migrations_table.c.version == 2
                )
            )

    @staticmethod
    def _append_future_version(engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                insert(schema_migrations_table).values(
                    version=4,
                    migration_id="future-v4",
                    contract_checksum="4" * 64,
                    applied_at=NOW,
                    app_version="99.0.0",
                )
            )
        metadata = MetaData()
        Table(
            "future_feature",
            metadata,
            Column("id", Integer, primary_key=True),
        ).create(engine)

    @staticmethod
    def _leave_unregistered_tables(engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                delete(schema_migrations_table).where(
                    schema_migrations_table.c.version.in_((2, 3))
                )
            )


if __name__ == "__main__":
    unittest.main()
