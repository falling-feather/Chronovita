from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, insert, select
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError

from scripts import manage_database as database_cli
from services.game_runtime.store import game_sessions_table
from services.persistence import backup as backup_module
from services.persistence.backup import (
    DatabaseBackupDestinationExists,
    DatabaseBackupError,
    DatabaseBackupIntegrityError,
    DatabaseBackupManifestError,
    DatabaseRestoreConflict,
    DatabaseRestoreSidecarsPresent,
    backup_sqlite_database,
    manifest_path_for,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from services.persistence.db import kv_table
from services.persistence.schema import (
    ensure_current_schema,
    inspect_schema,
    schema_migrations_table,
)
from services.version import APP_VERSION


NOW = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-database-backup-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_backup_verify_and_restore_round_trip_preserves_data(self):
        source = self._current_database("source.db", value="source-value")
        backup = self.tmp_root / "snapshots" / "source-backup.db"

        manifest = backup_sqlite_database(source, backup)
        verification = verify_sqlite_backup(backup)
        target = self.tmp_root / "restored" / "chronovita.db"
        restored = restore_sqlite_backup(backup, target)

        self.assertEqual(manifest.database_schema_version, 3)
        self.assertEqual(manifest.app_version, APP_VERSION)
        self.assertTrue(manifest.ledger_present)
        self.assertEqual(verification.manifest, manifest)
        self.assertEqual(restored.backup_id, manifest.backup_id)
        self.assertFalse(restored.replaced_existing)
        self.assertEqual(self._kv_value(target), "source-value")
        engine = self._engine(target)
        try:
            self.assertTrue(inspect_schema(engine).is_current)
        finally:
            engine.dispose()
        serialized = json.dumps(manifest.model_dump(mode="json"))
        self.assertNotIn(str(source), serialized)

    def test_valid_v08_database_can_be_backed_up_before_migration(self):
        source = self.tmp_root / "legacy-v08.db"
        engine = self._engine(source)
        try:
            kv_table.metadata.create_all(engine)
            game_sessions_table.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(
                    insert(kv_table).values(
                        namespace="qa",
                        key="legacy",
                        data='"legacy-value"',
                        updated_at=NOW,
                    )
                )
        finally:
            engine.dispose()

        backup = self.tmp_root / "legacy-backup.db"
        manifest = backup_sqlite_database(source, backup)
        restored = self.tmp_root / "legacy-restored.db"
        restore_sqlite_backup(backup, restored)

        self.assertEqual(manifest.database_schema_version, 0)
        self.assertFalse(manifest.ledger_present)
        engine = self._engine(restored)
        try:
            status = inspect_schema(engine)
            self.assertFalse(status.is_current)
            self.assertEqual(status.current_version, 0)
        finally:
            engine.dispose()
        self.assertEqual(self._kv_value(restored, key="legacy"), "legacy-value")

    def test_live_wal_source_produces_a_standalone_backup(self):
        source = self._current_database("wal-source.db", value="before-wal")
        writer = sqlite3.connect(str(source))
        try:
            mode = writer.execute("PRAGMA journal_mode=WAL").fetchone()
            self.assertEqual(str(mode[0]).lower(), "wal")
            writer.execute(
                "UPDATE kv SET data = ? WHERE namespace = ? AND key = ?",
                (json.dumps("from-wal"), "qa", "sample"),
            )
            writer.commit()
            backup = self.tmp_root / "wal-backup.db"
            backup_sqlite_database(source, backup)
        finally:
            writer.close()

        self.assertEqual(self._kv_value(backup), "from-wal")
        self.assertFalse(Path(f"{backup}-wal").exists())
        self.assertFalse(Path(f"{backup}-shm").exists())
        self.assertEqual(verify_sqlite_backup(backup).status, "verified")

    def test_tampered_backup_or_manifest_is_rejected(self):
        source = self._current_database("tamper-source.db", value="trusted")
        backup = self.tmp_root / "tampered.db"
        backup_sqlite_database(source, backup)
        with backup.open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaises(DatabaseBackupIntegrityError):
            verify_sqlite_backup(backup)

        second = self.tmp_root / "manifest-tampered.db"
        backup_sqlite_database(source, second)
        manifest_path = manifest_path_for(second)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["database_sha256"] = "f" * 64
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(DatabaseBackupIntegrityError):
            verify_sqlite_backup(second)

        manifest_path.write_text(
            '{"schema_version":"chronovita-backup-manifest/v1",'
            '"schema_version":"chronovita-backup-manifest/v1"}',
            encoding="utf-8",
        )
        with self.assertRaises(DatabaseBackupManifestError):
            verify_sqlite_backup(second)

    def test_backup_never_overwrites_and_pair_publish_failure_cleans_up(self):
        source = self._current_database("atomic-source.db", value="safe")
        occupied = self.tmp_root / "occupied.db"
        occupied.write_bytes(b"keep-me")
        with self.assertRaises(DatabaseBackupDestinationExists):
            backup_sqlite_database(source, occupied)
        self.assertEqual(occupied.read_bytes(), b"keep-me")
        self.assertFalse(manifest_path_for(occupied).exists())

        backup = self.tmp_root / "atomic.db"
        manifest = manifest_path_for(backup)
        real_link = os.link
        calls = 0

        def fail_manifest_publish(source_path, target_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected manifest publish failure")
            return real_link(source_path, target_path)

        with patch.object(backup_module.os, "link", side_effect=fail_manifest_publish):
            with self.assertRaises(DatabaseBackupError):
                backup_sqlite_database(source, backup)
        self.assertFalse(backup.exists())
        self.assertFalse(manifest.exists())

    def test_restore_requires_confirmation_and_replacement_has_safety_backup(self):
        source = self._current_database("restore-source.db", value="new-value")
        backup = self.tmp_root / "restore-input.db"
        backup_sqlite_database(source, backup)
        target = self._current_database("restore-target.db", value="old-value")

        with self.assertRaises(DatabaseRestoreConflict):
            restore_sqlite_backup(backup, target)
        self.assertEqual(self._kv_value(target), "old-value")

        safety = self.tmp_root / "pre-restore.db"
        report = restore_sqlite_backup(
            backup,
            target,
            replace_existing=True,
            safety_backup_path=safety,
        )
        self.assertTrue(report.replaced_existing)
        self.assertEqual(report.safety_backup_filename, safety.name)
        self.assertEqual(self._kv_value(target), "new-value")
        self.assertEqual(self._kv_value(safety), "old-value")
        self.assertEqual(verify_sqlite_backup(safety).status, "verified")

        alias = self.tmp_root / "backup-alias.db"
        os.link(backup, alias)
        with self.assertRaises(DatabaseBackupError):
            restore_sqlite_backup(backup, alias, replace_existing=True)

    def test_corrupt_restore_input_and_sidecars_never_change_target(self):
        source = self._current_database("guard-source.db", value="new")
        backup = self.tmp_root / "guard-backup.db"
        backup_sqlite_database(source, backup)
        target = self._current_database("guard-target.db", value="old")
        with backup.open("ab") as handle:
            handle.write(b"broken")
        with self.assertRaises(DatabaseBackupIntegrityError):
            restore_sqlite_backup(backup, target, replace_existing=True)
        self.assertEqual(self._kv_value(target), "old")

        clean_backup = self.tmp_root / "clean-backup.db"
        backup_sqlite_database(source, clean_backup)
        Path(f"{target}-wal").write_bytes(b"")
        with self.assertRaises(DatabaseRestoreSidecarsPresent):
            restore_sqlite_backup(clean_backup, target, replace_existing=True)
        self.assertEqual(self._kv_value(target), "old")

    def test_failed_post_restore_verification_rolls_back_original_target(self):
        source = self._current_database("rollback-source.db", value="new")
        backup = self.tmp_root / "rollback-input.db"
        source_manifest = backup_sqlite_database(source, backup)
        target = self._current_database("rollback-target.db", value="old")
        safety = self.tmp_root / "rollback-safety.db"
        original_verify = backup_module._verify_database_against_manifest

        def fail_new_target(path, manifest, *, require_filename):
            if path == target and manifest.backup_id == source_manifest.backup_id:
                raise DatabaseBackupIntegrityError("injected post-restore failure")
            return original_verify(
                path,
                manifest,
                require_filename=require_filename,
            )

        with patch.object(
            backup_module,
            "_verify_database_against_manifest",
            side_effect=fail_new_target,
        ):
            with self.assertRaisesRegex(DatabaseBackupIntegrityError, "injected"):
                restore_sqlite_backup(
                    backup,
                    target,
                    replace_existing=True,
                    safety_backup_path=safety,
                )
        self.assertEqual(self._kv_value(target), "old")
        self.assertEqual(verify_sqlite_backup(safety).status, "verified")

    def test_future_schema_backup_is_rejected(self):
        source = self._current_database("future.db", value="future")
        engine = self._engine(source)
        try:
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
        finally:
            engine.dispose()
        with self.assertRaises(DatabaseBackupIntegrityError):
            backup_sqlite_database(source, self.tmp_root / "future-backup.db")

    def test_database_cli_runs_the_offline_lifecycle_with_structured_output(self):
        database = self.tmp_root / "cli.db"
        code, _output, error = self._cli("migrate", "--database", str(database))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(error)["code"], "database_command_invalid")

        code, output, _error = self._cli(
            "migrate",
            "--database",
            str(database),
            "--initialize",
        )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["result"]["is_current"])

        backup = self.tmp_root / "cli-backup.db"
        code, output, _error = self._cli(
            "backup",
            "--database",
            str(database),
            "--output",
            str(backup),
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output)["result"]["schema_version"],
            "chronovita-backup-manifest/v1",
        )
        code, output, _error = self._cli("verify-backup", "--backup", str(backup))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["result"]["status"], "verified")

        restored = self.tmp_root / "cli-restored.db"
        code, output, _error = self._cli(
            "restore",
            "--backup",
            str(backup),
            "--target",
            str(restored),
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["result"]["status"], "restored")
        code, output, _error = self._cli("status", "--database", str(restored))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["result"]["is_current"])

    def test_database_cli_reads_postgres_url_only_from_named_env_and_redacts_errors(self):
        env_name = "CHRONO_TEST_DATABASE_URL"
        secret = "postgres-command-secret-must-not-leak"
        with patch.dict(
            os.environ,
            {env_name: f"postgresql://chrono:{secret}@db/chronovita"},
            clear=False,
        ), patch.object(
            database_cli,
            "inspect",
            side_effect=SQLAlchemyError(f"connection failed near {secret}"),
        ):
            code, _output, error = self._cli(
                "status",
                "--database-url-env",
                env_name,
            )

        self.assertEqual(code, 2)
        self.assertEqual(json.loads(error)["code"], "database_command_invalid")
        self.assertNotIn(secret, error)

        code, _output, missing_error = self._cli(
            "migrate",
            "--database-url-env",
            "CHRONO_MISSING_DATABASE_URL",
            "--initialize",
        )
        self.assertEqual(code, 2)
        self.assertNotIn("postgresql://", missing_error)

    def _current_database(self, filename: str, *, value: str) -> Path:
        path = self.tmp_root / filename
        engine = self._engine(path)
        try:
            ensure_current_schema(engine)
            with engine.begin() as connection:
                connection.execute(
                    insert(kv_table).values(
                        namespace="qa",
                        key="sample",
                        data=json.dumps(value),
                        updated_at=NOW,
                    )
                )
        finally:
            engine.dispose()
        return path

    def _kv_value(self, path: Path, *, key: str = "sample") -> str:
        engine = self._engine(path)
        try:
            with engine.connect() as connection:
                raw = connection.execute(
                    select(kv_table.c.data).where(
                        (kv_table.c.namespace == "qa") & (kv_table.c.key == key)
                    )
                ).scalar_one()
            return json.loads(raw)
        finally:
            engine.dispose()

    @staticmethod
    def _engine(path: Path) -> Engine:
        return create_engine(
            URL.create("sqlite", database=str(path)),
            connect_args={"check_same_thread": False},
            future=True,
        )

    @staticmethod
    def _cli(*args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = database_cli.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
