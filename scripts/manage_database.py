from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.persistence.backup import (
    DatabaseBackupError,
    backup_sqlite_database,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from services.persistence.schema import (
    DatabaseSchemaError,
    ensure_current_schema,
    inspect_schema,
)


class DatabaseCommandError(RuntimeError):
    code = "database_command_invalid"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect, migrate, back up, verify, or restore Chronovita SQLite."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Inspect schema without writing")
    _add_database_argument(status)

    migrate = commands.add_parser("migrate", help="Apply registered safe migrations")
    _add_database_argument(migrate)
    migrate.add_argument(
        "--initialize",
        action="store_true",
        help="Allow creation when the database file does not yet exist",
    )

    backup = commands.add_parser("backup", help="Create a verified SQLite snapshot")
    _add_database_argument(backup)
    backup.add_argument("--output", required=True, help="New backup database path")
    backup.add_argument("--manifest", help="Optional manifest output path")

    verify = commands.add_parser(
        "verify-backup",
        help="Verify manifest, checksum, quick_check, and schema",
    )
    verify.add_argument("--backup", required=True, help="Backup database path")
    verify.add_argument("--manifest", help="Optional manifest path")

    restore = commands.add_parser(
        "restore",
        help="Restore a verified backup while the API is stopped",
    )
    restore.add_argument("--backup", required=True, help="Backup database path")
    restore.add_argument("--manifest", help="Optional manifest path")
    restore.add_argument("--target", required=True, help="Restore target database path")
    restore.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly replace an existing target after a safety backup",
    )
    restore.add_argument(
        "--safety-backup",
        help="Optional path for the pre-restore safety backup",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run(args)
    except (DatabaseBackupError, DatabaseSchemaError, DatabaseCommandError) as exc:
        return _error(getattr(exc, "code", "database_command_failed"), str(exc))
    except (OSError, ValueError) as exc:
        return _error("database_command_invalid", str(exc))
    print(
        json.dumps(
            {"ok": True, "command": args.command, "result": result},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


def _run(args: argparse.Namespace) -> dict:
    if args.command == "status":
        database = _existing_database(args.database)
        status = _schema_operation(database, migrate=False)
        return {
            "database_filename": database.name,
            **status.model_dump(mode="json"),
        }
    if args.command == "migrate":
        database = _database_for_migration(args.database, initialize=args.initialize)
        status = _schema_operation(database, migrate=True)
        return {
            "database_filename": database.name,
            **status.model_dump(mode="json"),
        }
    if args.command == "backup":
        database = _existing_database(args.database)
        manifest = backup_sqlite_database(
            database,
            args.output,
            manifest_path=args.manifest,
        )
        return manifest.model_dump(mode="json")
    if args.command == "verify-backup":
        report = verify_sqlite_backup(
            args.backup,
            manifest_path=args.manifest,
        )
        return report.model_dump(mode="json")
    if args.command == "restore":
        report = restore_sqlite_backup(
            args.backup,
            args.target,
            manifest_path=args.manifest,
            replace_existing=args.replace,
            safety_backup_path=args.safety_backup,
        )
        return report.model_dump(mode="json")
    raise DatabaseCommandError("unknown database command")


def _schema_operation(database: Path, *, migrate: bool):
    engine = create_engine(
        URL.create("sqlite", database=str(database)),
        connect_args={"check_same_thread": False},
        future=True,
    )
    try:
        return ensure_current_schema(engine) if migrate else inspect_schema(engine)
    finally:
        engine.dispose()


def _existing_database(value: str) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise DatabaseCommandError("database file does not exist or is not regular")
    return path


def _database_for_migration(value: str, *, initialize: bool) -> Path:
    path = Path(value).expanduser().absolute()
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise DatabaseCommandError("database path is not a regular file")
        return path
    if not initialize:
        raise DatabaseCommandError(
            "database file does not exist; pass --initialize to create it"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _add_database_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", required=True, help="SQLite database path")


def _error(code: str, message: str) -> int:
    print(
        json.dumps(
            {"ok": False, "code": code, "message": message},
            ensure_ascii=True,
            indent=2,
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
