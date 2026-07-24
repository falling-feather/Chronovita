from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.persistence.database import resolve_database_target


POSTGRES_MIGRATOR_ROLE = "chronovita_migrator_test"
POSTGRES_RUNTIME_ROLE = "chronovita_runtime_test"
POSTGRES_TEST_ADMIN_ROLE = "chronovita_test_admin"
POSTGRES_TEST_DATABASE = "chronovita_test"
POSTGRES_TEST_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
POSTGRES_RUNTIME_SCHEMA = "chronovita_runtime_matrix"
POSTGRES_CLI_SCHEMA = "chronovita_cli_matrix"
POSTGRES_LOCK_SCHEMA = "chronovita_lock_timeout_matrix"
POSTGRES_TEST_SCHEMAS = (
    POSTGRES_CLI_SCHEMA,
    POSTGRES_LOCK_SCHEMA,
    POSTGRES_RUNTIME_SCHEMA,
)


@dataclass(frozen=True)
class ProvisionedPostgresTest:
    migration_url: str
    runtime_url: str
    migrator_password: str
    runtime_password: str


def provision_postgres_test(admin_url: str) -> ProvisionedPostgresTest:
    target = resolve_database_target(
        database_url=admin_url,
        sqlite_path="ignored.db",
    )
    if target.dialect != "postgresql":
        raise ValueError("PostgreSQL test provisioning requires a PostgreSQL URL")
    if target.url.host not in POSTGRES_TEST_HOSTS:
        raise ValueError("PostgreSQL test provisioning requires a loopback host")
    if target.url.database != POSTGRES_TEST_DATABASE:
        raise ValueError("PostgreSQL test provisioning requires its dedicated database")
    if target.url.username != POSTGRES_TEST_ADMIN_ROLE:
        raise ValueError("PostgreSQL test provisioning requires its disposable admin")

    from psycopg import connect, sql

    admin_dsn = target.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    migrator_password = token_urlsafe(32)
    runtime_password = token_urlsafe(32)
    with connect(admin_dsn, autocommit=True) as connection:
        _reset_test_objects(connection, sql)
        for role_name, password in (
            (POSTGRES_MIGRATOR_ROLE, migrator_password),
            (POSTGRES_RUNTIME_ROLE, runtime_password),
        ):
            connection.execute(
                sql.SQL(
                    "CREATE ROLE {} WITH LOGIN PASSWORD {} "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                    "NOREPLICATION NOBYPASSRLS"
                ).format(
                    sql.Identifier(role_name),
                    sql.Literal(password),
                )
            )

        database = sql.Identifier(POSTGRES_TEST_DATABASE)
        migrator = sql.Identifier(POSTGRES_MIGRATOR_ROLE)
        runtime = sql.Identifier(POSTGRES_RUNTIME_ROLE)
        connection.execute(
            sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                database
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                database,
                migrator,
                runtime,
            )
        )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        for schema_name in POSTGRES_TEST_SCHEMAS:
            schema = sql.Identifier(schema_name)
            connection.execute(
                sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                    schema,
                    migrator,
                )
            )
            connection.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(schema)
            )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(POSTGRES_RUNTIME_SCHEMA),
                runtime,
            )
        )

    return ProvisionedPostgresTest(
        migration_url=_role_url(
            target.url,
            role=POSTGRES_MIGRATOR_ROLE,
            password=migrator_password,
        ),
        runtime_url=_role_url(
            target.url,
            role=POSTGRES_RUNTIME_ROLE,
            password=runtime_password,
        ),
        migrator_password=migrator_password,
        runtime_password=runtime_password,
    )


def _reset_test_objects(connection, sql) -> None:
    for schema_name in POSTGRES_TEST_SCHEMAS:
        connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(schema_name)
            )
        )
    for role_name in (POSTGRES_RUNTIME_ROLE, POSTGRES_MIGRATOR_ROLE):
        exists = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
            (role_name,),
        ).fetchone()[0]
        if not exists:
            continue
        connection.execute(
            sql.SQL("DROP OWNED BY {} CASCADE").format(sql.Identifier(role_name))
        )
        connection.execute(
            sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name))
        )


def _role_url(base_url, *, role: str, password: str) -> str:
    return (
        base_url.set(username=role, password=password)
        .update_query_dict(
            {"options": f"-c search_path={POSTGRES_RUNTIME_SCHEMA}"}
        )
        .render_as_string(hide_password=False)
    )


def _write_github_environment(
    path: Path,
    provisioned: ProvisionedPostgresTest,
) -> None:
    values = {
        "CHRONO_TEST_POSTGRES_MIGRATION_URL": provisioned.migration_url,
        "CHRONO_TEST_POSTGRES_RUNTIME_URL": provisioned.runtime_url,
    }
    if any("\r" in value or "\n" in value for value in values.values()):
        raise ValueError("PostgreSQL test role URL contains a line break")
    payload = "".join(f"{key}={value}\n" for key, value in values.items())
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def _run_service_test(
    provisioned: ProvisionedPostgresTest,
    *,
    admin_url_env: str,
) -> int:
    child_env = {
        key: value
        for key, value in os.environ.items()
        if (
            not key.startswith("CHRONO_TEST_POSTGRES_")
            and key.casefold() != admin_url_env.casefold()
        )
    }
    child_env.update(
        {
            "CHRONO_DISABLE_DOTENV": "true",
            "CHRONO_TEST_POSTGRES_MIGRATION_URL": provisioned.migration_url,
            "CHRONO_TEST_POSTGRES_RUNTIME_URL": provisioned.runtime_url,
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_postgres_service",
            "-v",
        ],
        cwd=REPO_ROOT,
        env=child_env,
        check=False,
    )
    return int(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Provision isolated PostgreSQL roles for the dedicated Chronovita "
            "service matrix."
        )
    )
    parser.add_argument(
        "--admin-url-env",
        default="CHRONO_TEST_POSTGRES_ADMIN_URL",
        help="Environment variable containing the disposable test admin URL.",
    )
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument(
        "--github-env",
        action="store_true",
        help="Append generated role URLs to the GITHUB_ENV file.",
    )
    output.add_argument(
        "--run-tests",
        action="store_true",
        help=(
            "Run the PostgreSQL service test in a child process that receives "
            "role URLs but not the admin URL."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    admin_url = os.environ.get(args.admin_url_env, "").strip()
    if not admin_url:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "postgres_test_admin_url_missing",
                }
            ),
            file=sys.stderr,
        )
        return 2
    if args.github_env and os.environ.get("GITHUB_ACTIONS") != "true":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "postgres_github_environment_unavailable",
                }
            ),
            file=sys.stderr,
        )
        return 2

    try:
        provisioned = provision_postgres_test(admin_url)
        if args.github_env:
            output_path = Path(os.environ["GITHUB_ENV"])
            _write_github_environment(output_path, provisioned)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "postgres_test_provisioning_failed",
                    "exception_type": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        return 1

    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{provisioned.migrator_password}")
        print(f"::add-mask::{provisioned.runtime_password}")
    if args.run_tests:
        try:
            test_status = _run_service_test(
                provisioned,
                admin_url_env=args.admin_url_env,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "postgres_test_execution_failed",
                        "exception_type": type(exc).__name__,
                    }
                ),
                file=sys.stderr,
            )
            return 1
        if test_status != 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "postgres_service_test_failed",
                        "returncode": test_status,
                    },
                    separators=(",", ":"),
                ),
                file=sys.stderr,
            )
            return test_status
    print(
        json.dumps(
            {
                "ok": True,
                "migrator_role": POSTGRES_MIGRATOR_ROLE,
                "runtime_role": POSTGRES_RUNTIME_ROLE,
                "schemas": list(POSTGRES_TEST_SCHEMAS),
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
