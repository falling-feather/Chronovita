from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import URL


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.auth import AuthError, AuthService, AuthServiceConfig, AuthStoreError
from services.persistence.student_assets import (
    StudentAssetMigrationError,
    migrate_legacy_student_assets,
)


_ACTOR_PASSWORD_ENV = "CHRONO_MIGRATION_ACTOR_PASSWORD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or apply an explicit legacy single-user student asset migration. "
            "Student assets are read-only unless --apply is supplied; every run "
            "still records administrator login/logout audit events."
        )
    )
    parser.add_argument("--database", required=True, help="Existing SQLite database path")
    parser.add_argument("--actor-username", required=True, help="Enabled administrator")
    parser.add_argument("--target-username", required=True, help="Target account")
    parser.add_argument(
        "--source-game-user-id",
        required=True,
        help="Exact legacy CHRONO_GAME_USER_ID used by the old data",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the planned migration atomically; omit for a dry run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database).expanduser().resolve()
    if not database.is_file():
        return _error(
            "student_asset_database_not_found",
            f"database file does not exist: {database}",
        )
    engine = create_engine(
        URL.create("sqlite", database=str(database)),
        connect_args={"check_same_thread": False},
        future=True,
    )
    issued = None
    operation_request_id = f"student-assets:{uuid4().hex}"
    try:
        identity = AuthService(
            engine,
            AuthServiceConfig(mode="accounts", session_ttl_seconds=300),
        )
        actor_password = _read_secret(
            _ACTOR_PASSWORD_ENV,
            "Administrator password: ",
        )
        issued = identity.login(
            args.actor_username,
            actor_password,
            request_id=f"{operation_request_id}:login",
            client_fingerprint="offline-student-asset-migration",
        )
        report = migrate_legacy_student_assets(
            engine,
            actor=issued.principal,
            request_id=operation_request_id,
            target_username=args.target_username,
            source_game_user_id=args.source_game_user_id,
            apply=args.apply,
        )
    except (AuthError, AuthStoreError, StudentAssetMigrationError, ValueError) as exc:
        return _error(getattr(exc, "code", "student_asset_command_invalid"), str(exc))
    finally:
        if issued is not None:
            try:
                identity.logout(
                    issued.principal,
                    request_id=f"{operation_request_id}:logout",
                )
            except (AuthError, AuthStoreError):
                pass
        engine.dispose()
    print(
        json.dumps(
            {"ok": True, **report.model_dump(mode="json")},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


def _read_secret(env_name: str, prompt: str) -> str:
    value = os.environ.pop(env_name, None)
    if value is None:
        if not sys.stdin.isatty():
            raise ValueError(
                f"set {env_name} when the command has no interactive terminal"
            )
        value = getpass.getpass(prompt)
    if not value:
        raise ValueError(f"{env_name} must not be empty")
    return value


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
