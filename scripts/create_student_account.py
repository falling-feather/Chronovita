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

from services.auth import (
    AuthError,
    AuthService,
    AuthServiceConfig,
    AuthStoreError,
    UserAlreadyExists,
)


_ACTOR_PASSWORD_ENV = "CHRONO_MIGRATION_ACTOR_PASSWORD"
_STUDENT_PASSWORD_ENV = "CHRONO_NEW_STUDENT_PASSWORD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create one enabled student account in an existing Chronovita "
            "accounts database. Passwords are read from the terminal or environment."
        )
    )
    parser.add_argument("--database", required=True, help="Existing SQLite database path")
    parser.add_argument("--actor-username", required=True, help="Enabled administrator")
    parser.add_argument("--username", required=True, help="New student username")
    parser.add_argument("--display-name", required=True, help="New student display name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database).expanduser().resolve()
    if not database.is_file():
        return _error(
            "student_account_database_not_found",
            f"database file does not exist: {database}",
        )
    engine = create_engine(
        URL.create("sqlite", database=str(database)),
        connect_args={"check_same_thread": False},
        future=True,
    )
    issued = None
    operation_request_id = f"student-account:{uuid4().hex}"
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
            client_fingerprint="offline-student-account-create",
        )
        if "admin" not in issued.principal.roles:
            raise ValueError("actor must be an enabled administrator")
        student_password = _read_new_student_password()
        user = identity.create_user(
            username=args.username,
            password=student_password,
            display_name=args.display_name,
            roles=("student",),
            actor=issued.principal,
            request_id=f"{operation_request_id}:create",
        )
    except (AuthError, AuthStoreError, UserAlreadyExists, ValueError) as exc:
        return _error(getattr(exc, "code", "student_account_invalid"), str(exc))
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
            {"ok": True, "user": user.model_dump(mode="json")},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


def _read_new_student_password() -> str:
    value = os.environ.pop(_STUDENT_PASSWORD_ENV, None)
    if value is not None:
        if not value:
            raise ValueError(f"{_STUDENT_PASSWORD_ENV} must not be empty")
        return value
    if not sys.stdin.isatty():
        raise ValueError(
            f"set {_STUDENT_PASSWORD_ENV} when the command has no interactive terminal"
        )
    first = getpass.getpass("New student password: ")
    second = getpass.getpass("Repeat new student password: ")
    if first != second:
        raise ValueError("new student passwords do not match")
    if not first:
        raise ValueError("new student password must not be empty")
    return first


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
