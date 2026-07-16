from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from services.persistence.schema import (
    DatabaseSchemaError,
    DatabaseSchemaStatus,
    inspect_schema,
)
from services.version import APP_VERSION


MANIFEST_SUFFIX = ".manifest.json"
_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class DatabaseBackupError(RuntimeError):
    code = "database_backup_error"


class DatabaseBackupSourceMissing(DatabaseBackupError):
    code = "database_backup_source_missing"


class DatabaseBackupDestinationExists(DatabaseBackupError):
    code = "database_backup_destination_exists"


class DatabaseBackupIntegrityError(DatabaseBackupError):
    code = "database_backup_integrity_error"


class DatabaseBackupManifestError(DatabaseBackupError):
    code = "database_backup_manifest_error"


class DatabaseRestoreConflict(DatabaseBackupError):
    code = "database_restore_conflict"


class DatabaseRestoreSidecarsPresent(DatabaseBackupError):
    code = "database_restore_sidecars_present"


class DatabaseBackupManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["chronovita-backup-manifest/v1"] = (
        "chronovita-backup-manifest/v1"
    )
    backup_id: str = Field(pattern=r"^bkp_[0-9a-f]{32}$")
    created_at: datetime
    app_version: str
    database_schema_version: int = Field(ge=0)
    ledger_present: bool
    backup_filename: str = Field(min_length=1, max_length=255)
    database_size_bytes: int = Field(gt=0)
    database_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sqlite_quick_check: Literal["ok"] = "ok"

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a UTC offset")
        return value

    @field_validator("backup_filename")
    @classmethod
    def require_plain_filename(cls, value: str) -> str:
        if Path(value).name != value or value in (".", ".."):
            raise ValueError("backup_filename must be a plain filename")
        return value


class DatabaseBackupVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["chronovita-backup-verification/v1"] = (
        "chronovita-backup-verification/v1"
    )
    status: Literal["verified"] = "verified"
    verified_at: datetime
    manifest: DatabaseBackupManifest


class DatabaseRestoreReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["chronovita-database-restore/v1"] = (
        "chronovita-database-restore/v1"
    )
    status: Literal["restored"] = "restored"
    restored_at: datetime
    backup_id: str
    target_filename: str
    replaced_existing: bool
    safety_backup_filename: str | None = None
    safety_manifest_filename: str | None = None
    database_schema_version: int


def manifest_path_for(backup_path: str | Path) -> Path:
    backup = _absolute_path(backup_path)
    return backup.with_name(f"{backup.name}{MANIFEST_SUFFIX}")


def backup_sqlite_database(
    source_path: str | Path,
    backup_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> DatabaseBackupManifest:
    source = _absolute_path(source_path)
    destination = _absolute_path(backup_path)
    manifest_destination = (
        _absolute_path(manifest_path)
        if manifest_path is not None
        else manifest_path_for(destination)
    )
    _require_regular_file(source, source=True)
    _require_distinct_paths(source, destination, manifest_destination)
    _require_absent(destination)
    _require_absent(manifest_destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)

    database_temp = _temp_path(destination)
    manifest_temp = _temp_path(manifest_destination)
    database_published = False
    try:
        _sqlite_backup(source, database_temp)
        status = _inspect_database(database_temp)
        size, checksum = _hash_regular_file(database_temp)
        manifest = DatabaseBackupManifest(
            backup_id=f"bkp_{uuid4().hex}",
            created_at=datetime.now(timezone.utc),
            app_version=APP_VERSION,
            database_schema_version=status.current_version,
            ledger_present=status.ledger_present,
            backup_filename=destination.name,
            database_size_bytes=size,
            database_sha256=checksum,
        )
        _write_json_temp(manifest_temp, manifest.model_dump(mode="json"))
        try:
            os.link(database_temp, destination)
            database_published = True
            os.link(manifest_temp, manifest_destination)
        except FileExistsError as exc:
            if database_published and _same_file(destination, database_temp):
                destination.unlink()
            raise DatabaseBackupDestinationExists(
                "backup database or manifest already exists"
            ) from exc
        except OSError as exc:
            if database_published and _same_file(destination, database_temp):
                destination.unlink()
            raise DatabaseBackupError("could not publish backup atomically") from exc
        return manifest
    finally:
        _cleanup_temp_database(database_temp)
        manifest_temp.unlink(missing_ok=True)


def verify_sqlite_backup(
    backup_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> DatabaseBackupVerification:
    backup = _absolute_path(backup_path)
    manifest_file = (
        _absolute_path(manifest_path)
        if manifest_path is not None
        else manifest_path_for(backup)
    )
    manifest = _load_manifest(manifest_file)
    _verify_database_against_manifest(
        backup,
        manifest,
        require_filename=True,
    )
    return DatabaseBackupVerification(
        verified_at=datetime.now(timezone.utc),
        manifest=manifest,
    )


def restore_sqlite_backup(
    backup_path: str | Path,
    target_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    replace_existing: bool = False,
    safety_backup_path: str | Path | None = None,
) -> DatabaseRestoreReport:
    backup = _absolute_path(backup_path)
    target = _absolute_path(target_path)
    manifest_file = (
        _absolute_path(manifest_path)
        if manifest_path is not None
        else manifest_path_for(backup)
    )
    verification = verify_sqlite_backup(
        backup,
        manifest_path=manifest_file,
    )
    manifest = verification.manifest
    _require_distinct_paths(backup, manifest_file, target)
    _reject_sqlite_sidecars(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    target_exists = target.exists() or target.is_symlink()
    safety_manifest: DatabaseBackupManifest | None = None
    safety_backup: Path | None = None
    if target_exists:
        _require_regular_file(target, source=False)
        if not replace_existing:
            raise DatabaseRestoreConflict(
                "restore target exists; explicit replacement is required"
            )
        safety_backup = (
            _absolute_path(safety_backup_path)
            if safety_backup_path is not None
            else _default_safety_backup_path(target)
        )
        safety_manifest_path = manifest_path_for(safety_backup)
        _require_distinct_paths(
            backup,
            manifest_file,
            target,
            safety_backup,
            safety_manifest_path,
        )
        safety_manifest = backup_sqlite_database(target, safety_backup)

    restore_temp = _temp_path(target)
    target_published = False
    try:
        _copy_regular_file(backup, restore_temp)
        _verify_database_against_manifest(
            restore_temp,
            manifest,
            require_filename=False,
        )
        _reject_sqlite_sidecars(target)
        try:
            if target_exists:
                os.replace(restore_temp, target)
            else:
                os.link(restore_temp, target)
            target_published = True
        except FileExistsError as exc:
            raise DatabaseRestoreConflict(
                "restore target appeared while publishing"
            ) from exc
        except OSError as exc:
            raise DatabaseBackupError("could not publish restored database") from exc

        try:
            _verify_database_against_manifest(
                target,
                manifest,
                require_filename=False,
            )
        except DatabaseBackupError:
            if target_exists and safety_backup is not None and safety_manifest is not None:
                _rollback_restore(target, safety_backup, safety_manifest)
            elif target_published and _same_file(target, restore_temp):
                target.unlink(missing_ok=True)
            raise
        return DatabaseRestoreReport(
            restored_at=datetime.now(timezone.utc),
            backup_id=manifest.backup_id,
            target_filename=target.name,
            replaced_existing=target_exists,
            safety_backup_filename=safety_backup.name if safety_backup else None,
            safety_manifest_filename=(
                manifest_path_for(safety_backup).name if safety_backup else None
            ),
            database_schema_version=manifest.database_schema_version,
        )
    finally:
        _cleanup_temp_database(restore_temp)


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = None
    destination_connection = None
    try:
        source_connection = sqlite3.connect(
            f"{source.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=30,
        )
        destination_connection = sqlite3.connect(str(destination), timeout=30)
        source_connection.backup(destination_connection)
        destination_connection.commit()
        journal_mode = destination_connection.execute(
            "PRAGMA journal_mode=DELETE"
        ).fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "delete":
            raise DatabaseBackupIntegrityError(
                "SQLite backup could not be normalized to a standalone file"
            )
        destination_connection.commit()
    except sqlite3.Error as exc:
        raise DatabaseBackupIntegrityError(
            "SQLite could not create a consistent backup"
        ) from exc
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
    _fsync_file(destination)


def _inspect_database(path: Path) -> DatabaseSchemaStatus:
    _quick_check(path)
    engine = create_engine(
        URL.create("sqlite", database=str(path)),
        connect_args={"check_same_thread": False},
        future=True,
    )
    try:
        return inspect_schema(engine)
    except DatabaseSchemaError as exc:
        raise DatabaseBackupIntegrityError(
            "backup database schema is invalid"
        ) from exc
    except SQLAlchemyError as exc:
        raise DatabaseBackupIntegrityError(
            "backup database could not be inspected"
        ) from exc
    finally:
        engine.dispose()


def _quick_check(path: Path) -> None:
    _require_regular_file(path, source=True)
    connection = None
    try:
        connection = sqlite3.connect(
            f"{path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=10,
        )
        rows = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as exc:
        raise DatabaseBackupIntegrityError(
            "SQLite quick_check could not be completed"
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    if rows != [("ok",)]:
        raise DatabaseBackupIntegrityError("SQLite quick_check failed")


def _verify_database_against_manifest(
    path: Path,
    manifest: DatabaseBackupManifest,
    *,
    require_filename: bool,
) -> DatabaseSchemaStatus:
    _require_regular_file(path, source=True)
    if require_filename and manifest.backup_filename != path.name:
        raise DatabaseBackupManifestError(
            "backup filename does not match its manifest"
        )
    size, checksum = _hash_regular_file(path)
    if size != manifest.database_size_bytes or checksum != manifest.database_sha256:
        raise DatabaseBackupIntegrityError(
            "backup database size or checksum does not match its manifest"
        )
    status = _inspect_database(path)
    if (
        status.current_version != manifest.database_schema_version
        or status.ledger_present != manifest.ledger_present
    ):
        raise DatabaseBackupManifestError(
            "backup schema status does not match its manifest"
        )
    return status


def _load_manifest(path: Path) -> DatabaseBackupManifest:
    try:
        _require_regular_file(path, source=True)
    except DatabaseBackupError as exc:
        raise DatabaseBackupManifestError(
            "backup manifest does not exist or is not a regular file"
        ) from exc
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DatabaseBackupManifestError("backup manifest could not be read") from exc
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise DatabaseBackupManifestError("backup manifest is too large")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(payload, dict):
            raise ValueError("manifest root must be an object")
        return DatabaseBackupManifest.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise DatabaseBackupManifestError("backup manifest is invalid") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _write_json_temp(path: Path, payload: dict) -> None:
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise DatabaseBackupError("backup manifest could not be written") from exc


def _copy_regular_file(source: Path, destination: Path) -> None:
    _require_regular_file(source, source=True)
    try:
        with source.open("rb") as source_handle, destination.open("xb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle, length=_HASH_CHUNK_BYTES)
            target_handle.flush()
            os.fsync(target_handle.fileno())
    except OSError as exc:
        raise DatabaseBackupError("database file could not be copied") from exc


def _rollback_restore(
    target: Path,
    safety_backup: Path,
    safety_manifest: DatabaseBackupManifest,
) -> None:
    rollback_temp = _temp_path(target)
    try:
        _copy_regular_file(safety_backup, rollback_temp)
        _verify_database_against_manifest(
            rollback_temp,
            safety_manifest,
            require_filename=False,
        )
        os.replace(rollback_temp, target)
        _verify_database_against_manifest(
            target,
            safety_manifest,
            require_filename=False,
        )
    except (OSError, DatabaseBackupError) as exc:
        raise DatabaseBackupIntegrityError(
            "restore verification failed and the safety rollback also failed"
        ) from exc
    finally:
        _cleanup_temp_database(rollback_temp)


def _hash_regular_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise DatabaseBackupIntegrityError("database path is not a regular file")
            size = 0
            while chunk := handle.read(_HASH_CHUNK_BYTES):
                size += len(chunk)
                digest.update(chunk)
            current = os.lstat(path)
            if stat.S_ISLNK(current.st_mode) or not os.path.samestat(opened, current):
                raise DatabaseBackupIntegrityError(
                    "database file changed while it was being verified"
                )
    except DatabaseBackupError:
        raise
    except OSError as exc:
        raise DatabaseBackupIntegrityError("database file could not be hashed") from exc
    return size, digest.hexdigest()


def _fsync_file(path: Path) -> None:
    try:
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())
    except OSError as exc:
        raise DatabaseBackupError("backup file could not be flushed") from exc


def _require_regular_file(path: Path, *, source: bool) -> None:
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError as exc:
        if source:
            raise DatabaseBackupSourceMissing(
                "database or backup file does not exist"
            ) from exc
        raise DatabaseRestoreConflict("restore target does not exist") from exc
    except OSError as exc:
        raise DatabaseBackupError("database path could not be inspected") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise DatabaseBackupIntegrityError(
            "database, backup, and manifest paths must be regular files"
        )


def _require_absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise DatabaseBackupDestinationExists(
            "backup database or manifest already exists"
        )


def _require_distinct_paths(*paths: Path) -> None:
    identities: set[str] = set()
    existing: list[Path] = []
    for path in paths:
        identity = os.path.normcase(str(path.resolve(strict=False)))
        if identity in identities:
            raise DatabaseBackupError("database operation paths must be distinct")
        for previous in existing:
            if _same_file(path, previous):
                raise DatabaseBackupError(
                    "database operation paths must not reference the same file"
                )
        identities.add(identity)
        if path.exists() or path.is_symlink():
            existing.append(path)


def _reject_sqlite_sidecars(target: Path) -> None:
    found = [
        Path(f"{target}{suffix}").name
        for suffix in _SQLITE_SIDECAR_SUFFIXES
        if Path(f"{target}{suffix}").exists()
        or Path(f"{target}{suffix}").is_symlink()
    ]
    if found:
        raise DatabaseRestoreSidecarsPresent(
            "restore target has SQLite sidecar files; stop the API and checkpoint it"
        )


def _default_safety_backup_path(target: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return target.with_name(
        f"{target.name}.pre-restore-{stamp}-{uuid4().hex[:8]}.db"
    )


def _temp_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")


def _cleanup_temp_database(path: Path) -> None:
    path.unlink(missing_ok=True)
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _absolute_path(value: str | Path) -> Path:
    return Path(value).expanduser().absolute()


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


__all__ = [
    "DatabaseBackupDestinationExists",
    "DatabaseBackupError",
    "DatabaseBackupIntegrityError",
    "DatabaseBackupManifest",
    "DatabaseBackupManifestError",
    "DatabaseBackupSourceMissing",
    "DatabaseBackupVerification",
    "DatabaseRestoreConflict",
    "DatabaseRestoreReport",
    "DatabaseRestoreSidecarsPresent",
    "backup_sqlite_database",
    "manifest_path_for",
    "restore_sqlite_backup",
    "verify_sqlite_backup",
]
