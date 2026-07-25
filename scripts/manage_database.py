from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.persistence.backup import (
    DatabaseBackupError,
    backup_sqlite_database,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from services.persistence.database import (
    DatabaseConfigurationError,
    create_database_engine,
    resolve_database_target,
)
from services.persistence.schema import (
    DatabaseSchemaError,
    DatabaseSchemaStatus,
    ensure_current_schema,
    inspect_schema,
)


class DatabaseCommandError(RuntimeError):
    code = "database_command_invalid"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or migrate Chronovita databases; back up or restore SQLite."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Inspect schema without writing")
    _add_schema_database_arguments(status)

    migrate = commands.add_parser("migrate", help="Apply registered safe migrations")
    _add_schema_database_arguments(migrate)
    migrate.add_argument(
        "--initialize",
        action="store_true",
        help="Allow creation when the database file does not yet exist",
    )
    migrate.add_argument(
        "--migration-lock-timeout-seconds",
        type=float,
        default=30.0,
        help="Maximum PostgreSQL migration-lock wait (0.1 to 300 seconds)",
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
    except (
        DatabaseBackupError,
        DatabaseConfigurationError,
        DatabaseSchemaError,
        DatabaseCommandError,
    ) as exc:
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
        status, source = _schema_command(args, migrate=False)
        return {
            **source,
            **status.model_dump(mode="json"),
        }
    if args.command == "migrate":
        status, source = _schema_command(args, migrate=True)
        return {
            **source,
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


def _schema_command(
    args: argparse.Namespace,
    *,
    migrate: bool,
) -> tuple[DatabaseSchemaStatus, dict[str, str]]:
    if args.database is not None:
        database = (
            _database_for_migration(args.database, initialize=args.initialize)
            if migrate
            else _existing_database(args.database)
        )
        engine = create_engine(
            URL.create("sqlite", database=str(database)),
            connect_args={"check_same_thread": False},
            future=True,
        )
        source = {"database_filename": database.name}
    else:
        env_name = _database_url_env_name(args.database_url_env)
        raw_url = os.environ.get(env_name, "").strip()
        if not raw_url:
            raise DatabaseCommandError(
                "database URL environment variable is empty or missing"
            )
        target = resolve_database_target(
            database_url=raw_url,
            sqlite_path="ignored.db",
        )
        if target.dialect != "postgresql":
            raise DatabaseCommandError(
                "database URL environment variable must resolve to PostgreSQL"
            )
        engine = create_database_engine(target)
        source = {"database_url_env": env_name}

    try:
        table_names = tuple(inspect(engine).get_table_names())
        if migrate and not table_names and not args.initialize:
            raise DatabaseCommandError(
                "database is empty; pass --initialize to create the schema"
            )
        status = (
            ensure_current_schema(
                engine,
                migration_lock_timeout_seconds=args.migration_lock_timeout_seconds,
            )
            if migrate
            else inspect_schema(engine)
        )
        return status, source
    except (DatabaseCommandError, DatabaseSchemaError):
        raise
    except SQLAlchemyError as exc:
        raise DatabaseCommandError(
            "database connection or inspection failed"
        ) from exc
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


def _add_schema_database_arguments(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", help="SQLite database path")
    source.add_argument(
        "--database-url-env",
        help="Environment variable containing a PostgreSQL URL",
    )


def _database_url_env_name(value: str) -> str:
    candidate = (value or "").strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", candidate):
        raise DatabaseCommandError(
            "database URL environment variable name is invalid"
        )
    return candidate


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
