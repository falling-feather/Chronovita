from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import ArgumentError, NoSuchModuleError
from sqlalchemy.pool import StaticPool


DatabaseDialect = Literal["sqlite", "postgresql"]
DatabaseSource = Literal["database-url", "sqlite-path"]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORTED_DRIVERS = frozenset(
    {
        "sqlite",
        "sqlite+pysqlite",
        "postgresql",
        "postgresql+psycopg",
    }
)


class DatabaseConfigurationError(RuntimeError):
    code = "database_configuration_error"


class DatabaseUrlInvalid(DatabaseConfigurationError):
    code = "database_url_invalid"


class UnsupportedDatabaseDialect(DatabaseConfigurationError):
    code = "unsupported_database_dialect"


class UnsupportedDatabaseDriver(DatabaseConfigurationError):
    code = "unsupported_database_driver"


class DatabaseDriverUnavailable(DatabaseConfigurationError):
    code = "database_driver_unavailable"


class DatabaseEngineConflict(DatabaseConfigurationError):
    code = "database_engine_conflict"


class DatabaseEngineOptionsInvalid(DatabaseConfigurationError):
    code = "database_engine_options_invalid"


@dataclass(frozen=True)
class DatabaseTarget:
    dialect: DatabaseDialect
    source: DatabaseSource
    url: URL = field(repr=False)
    sqlite_path: Path | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DatabaseEngineOptions:
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout_seconds: float = 30.0
    pool_recycle_seconds: int = 1800
    connect_timeout_seconds: int = 10
    migration_lock_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if (
            not 1 <= self.pool_size <= 100
            or not 0 <= self.max_overflow <= 100
            or not 1 <= self.pool_timeout_seconds <= 300
            or not 30 <= self.pool_recycle_seconds <= 86_400
            or not 1 <= self.connect_timeout_seconds <= 60
            or not 0.1 <= self.migration_lock_timeout_seconds <= 300
        ):
            raise DatabaseEngineOptionsInvalid(
                "database engine options are outside supported bounds"
            )


def resolve_database_target(
    *,
    database_url: str | None,
    sqlite_path: str,
    relative_to: str | Path | None = None,
) -> DatabaseTarget:
    """Resolve one supported database target without exposing URL credentials."""

    root = _absolute_root(relative_to)
    raw_url = (database_url or "").strip()
    if raw_url:
        try:
            url = make_url(raw_url)
        except (ArgumentError, TypeError, ValueError) as exc:
            raise DatabaseUrlInvalid("database URL is invalid") from exc
        return _target_from_url(url, root=root)

    raw_path = sqlite_path.strip()
    if not raw_path:
        raise DatabaseUrlInvalid("SQLite database path is empty")
    path = _absolute_sqlite_path(raw_path, root=root)
    return DatabaseTarget(
        dialect="sqlite",
        source="sqlite-path",
        url=URL.create("sqlite", database=str(path)),
        sqlite_path=path,
    )


def create_database_engine(
    target: DatabaseTarget,
    *,
    options: DatabaseEngineOptions | None = None,
) -> Engine:
    resolved_options = options or DatabaseEngineOptions()
    if target.sqlite_path is not None:
        try:
            target.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseConfigurationError(
                "SQLite database directory could not be prepared"
            ) from exc

    kwargs: dict[str, object] = {"future": True}
    if target.dialect == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if target.sqlite_path is None:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_size": resolved_options.pool_size,
                "max_overflow": resolved_options.max_overflow,
                "pool_timeout": resolved_options.pool_timeout_seconds,
                "pool_recycle": resolved_options.pool_recycle_seconds,
                "connect_args": {
                    "connect_timeout": resolved_options.connect_timeout_seconds,
                },
            }
        )
    try:
        engine = create_engine(target.url, **kwargs)
    except (ImportError, ModuleNotFoundError, NoSuchModuleError) as exc:
        raise DatabaseDriverUnavailable(
            "configured database driver is unavailable"
        ) from exc
    except (ArgumentError, TypeError, ValueError) as exc:
        raise DatabaseUrlInvalid("database engine configuration is invalid") from exc

    if engine.dialect.name != target.dialect:
        engine.dispose()
        raise UnsupportedDatabaseDialect(
            "configured database engine resolved to an unsupported dialect"
        )
    return engine


def _target_from_url(url: URL, *, root: Path) -> DatabaseTarget:
    dialect = url.get_backend_name()
    if dialect not in ("sqlite", "postgresql"):
        raise UnsupportedDatabaseDialect(
            f"database dialect is not supported: {dialect}"
        )
    if url.drivername not in _SUPPORTED_DRIVERS:
        raise UnsupportedDatabaseDriver(
            f"database driver is not supported for {dialect}"
        )

    if dialect == "sqlite":
        if any(
            value is not None
            for value in (url.username, url.password, url.host, url.port)
        ):
            raise DatabaseUrlInvalid(
                "SQLite database URL must not contain network credentials"
            )
        if url.database in (None, "", ":memory:"):
            return DatabaseTarget(
                dialect="sqlite",
                source="database-url",
                url=url,
            )
        path = _absolute_sqlite_path(url.database, root=root)
        return DatabaseTarget(
            dialect="sqlite",
            source="database-url",
            url=url.set(database=str(path)),
            sqlite_path=path,
        )

    normalized = (
        url.set(drivername="postgresql+psycopg")
        if url.drivername == "postgresql"
        else url
    )
    return DatabaseTarget(
        dialect="postgresql",
        source="database-url",
        url=normalized,
    )


def _absolute_root(value: str | Path | None) -> Path:
    root = Path(value).expanduser() if value is not None else _REPO_ROOT
    try:
        return root.absolute()
    except OSError as exc:
        raise DatabaseUrlInvalid("database base directory is invalid") from exc


def _absolute_sqlite_path(value: str, *, root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve(strict=False)
    except OSError as exc:
        raise DatabaseUrlInvalid("SQLite database path is invalid") from exc


__all__ = [
    "DatabaseConfigurationError",
    "DatabaseDialect",
    "DatabaseDriverUnavailable",
    "DatabaseEngineConflict",
    "DatabaseEngineOptions",
    "DatabaseEngineOptionsInvalid",
    "DatabaseSource",
    "DatabaseTarget",
    "DatabaseUrlInvalid",
    "UnsupportedDatabaseDialect",
    "UnsupportedDatabaseDriver",
    "create_database_engine",
    "resolve_database_target",
]
