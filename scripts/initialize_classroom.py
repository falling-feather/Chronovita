"""Initialize the local classroom database and its first administrator."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.auth import (
    AuthService,
    AuthServiceConfig,
    AuthStoreError,
    BootstrapRequired,
)
from services.persistence.database import (
    DatabaseConfigurationError,
    create_database_engine,
    resolve_database_target,
)
from services.persistence.schema import DatabaseSchemaError, ensure_current_schema


PASSWORD_ENV = "CHRONO_CLASSROOM_ADMIN_PASSWORD"
DEFAULT_DISPLAY_NAME = "Chronovita Classroom Administrator"


def initialize_classroom(
    database: Path,
    *,
    username: str = "admin",
    display_name: str = DEFAULT_DISPLAY_NAME,
    password_reader: Callable[[], str] | None = None,
) -> dict[str, object]:
    """Create the first admin only when the accounts database is empty."""

    target = database.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(
        resolve_database_target(database_url=None, sqlite_path=str(target))
    )
    try:
        ensure_current_schema(engine, mode="apply-safe")
        config = AuthServiceConfig(mode="accounts", session_ttl_seconds=300)
        try:
            AuthService(engine, config)
        except BootstrapRequired:
            password = (password_reader or _read_new_password)()
            AuthService(
                engine,
                AuthServiceConfig(
                    mode="accounts",
                    session_ttl_seconds=300,
                    bootstrap_username=username,
                    bootstrap_password=password,
                    bootstrap_display_name=display_name,
                ),
            )
            return {
                "ok": True,
                "status": "initialized",
                "username": username,
                "database": str(target),
            }
        return {
            "ok": True,
            "status": "already-initialized",
            "username": None,
            "database": str(target),
        }
    finally:
        engine.dispose()


def _read_new_password() -> str:
    value = os.environ.pop(PASSWORD_ENV, None)
    if value is not None:
        if not value:
            raise ValueError(f"{PASSWORD_ENV} must not be empty")
        return value
    if not sys.stdin.isatty():
        raise ValueError(
            f"set process-only {PASSWORD_ENV} when no interactive terminal is available"
        )
    first = getpass.getpass("Create classroom administrator password: ")
    second = getpass.getpass("Repeat classroom administrator password: ")
    if first != second:
        raise ValueError("administrator passwords do not match")
    if not first:
        raise ValueError("administrator password must not be empty")
    return first


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a local Chronovita accounts database. The first password "
            "is read securely and is never written to a config file."
        )
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = initialize_classroom(
            args.database,
            username=args.username,
            display_name=args.display_name,
        )
    except (
        AuthStoreError,
        DatabaseConfigurationError,
        DatabaseSchemaError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": getattr(exc, "code", "classroom_initialization_invalid"),
                    "message": str(exc),
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
