from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.persistence.schema import inspect_schema


class RuntimeReadinessError(RuntimeError):
    code = "runtime_dependency_unavailable"


@dataclass(frozen=True)
class DatabaseReadiness:
    dialect: str
    current_schema_version: int
    latest_schema_version: int

    def public_checks(self) -> dict[str, dict[str, object]]:
        return {
            "database": {
                "status": "ok",
                "dialect": self.dialect,
            },
            "schema": {
                "status": "ok",
                "current_version": self.current_schema_version,
                "latest_version": self.latest_schema_version,
            },
        }


def probe_database_readiness(engine: Engine) -> DatabaseReadiness:
    """Read the schema and its invariants without returning dependency details."""

    try:
        status = inspect_schema(engine)
        if not status.is_current:
            raise RuntimeReadinessError("database schema is not current")
    except RuntimeReadinessError:
        raise
    except Exception as exc:
        raise RuntimeReadinessError("database readiness check failed") from exc
    return DatabaseReadiness(
        dialect=status.dialect,
        current_schema_version=status.current_version,
        latest_schema_version=status.latest_version,
    )


def probe_database_connectivity(engine: Engine) -> None:
    """Run the lightweight dependency check used by repeated readiness requests."""

    try:
        with engine.connect() as connection:
            if connection.execute(text("SELECT 1")).scalar_one() != 1:
                raise RuntimeReadinessError("database connectivity check failed")
    except RuntimeReadinessError:
        raise
    except Exception as exc:
        raise RuntimeReadinessError("database connectivity check failed") from exc
