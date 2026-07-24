from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .models import AuditEvent, SessionRecord, UserRecord, UserRole, normalize_roles


ZERO_HASH = "0" * 64


class AuthStoreError(RuntimeError):
    code = "auth_storage_unavailable"


class UserAlreadyExists(AuthStoreError):
    code = "username_unavailable"


class UserNotFound(AuthStoreError):
    code = "user_not_found"


class BootstrapUserRequired(AuthStoreError):
    code = "bootstrap_admin_required"


class LastAdminInvariantViolation(AuthStoreError):
    code = "last_admin_required"


class AuditHeadBusy(AuthStoreError):
    code = "audit_head_busy"


@dataclass(frozen=True)
class AuditWrite:
    occurred_at: datetime
    actor_user_id: str | None
    actor_session_id: str | None
    actor_roles: tuple[UserRole, ...]
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    request_id: str
    details: dict[str, Any] | None = None


_METADATA = MetaData()
_POSTGRES_IDENTITY_INVARIANT_LOCK_ID = 0x4348524F4E4F4155

users_table = Table(
    "auth_users",
    _METADATA,
    Column("user_id", String(36), primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("display_name", String(80), nullable=False),
    Column("password_hash", String(512), nullable=False),
    Column("roles", Text, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("auth_version", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

sessions_table = Table(
    "auth_sessions",
    _METADATA,
    Column("session_id", String(36), primary_key=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("user_id", String(36), nullable=False, index=True),
    Column("auth_version", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("last_seen_at", String(40), nullable=False),
    Column("revoked_at", String(40), nullable=True),
)

audit_head_table = Table(
    "auth_audit_head",
    _METADATA,
    Column("head_id", Integer, primary_key=True),
    Column("sequence", Integer, nullable=False),
    Column("event_hash", String(64), nullable=False),
)

audit_events_table = Table(
    "auth_audit_events",
    _METADATA,
    Column("sequence", Integer, primary_key=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("occurred_at", String(40), nullable=False),
    Column("actor_user_id", String(36), nullable=True),
    Column("actor_session_id", String(36), nullable=True),
    Column("actor_roles", Text, nullable=False),
    Column("action", String(100), nullable=False),
    Column("resource_type", String(80), nullable=False),
    Column("resource_id", String(160), nullable=False),
    Column("outcome", String(16), nullable=False),
    Column("request_id", String(100), nullable=False),
    Column("details", Text, nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("event_hash", String(64), nullable=False),
)


class AuthStore:
    """Identity persistence over an engine already validated by the schema manager."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._write_lock = threading.RLock()

    def count_users(self) -> int:
        try:
            with self.engine.connect() as connection:
                return len(connection.execute(select(users_table.c.user_id)).fetchall())
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity user count failed") from exc

    def create_user(
        self,
        user: UserRecord,
        *,
        audit: AuditWrite | None = None,
    ) -> UserRecord:
        values = _user_values(user)
        try:
            with self._identity_change_transaction() as connection:
                try:
                    connection.execute(insert(users_table).values(**values))
                except IntegrityError as exc:
                    raise UserAlreadyExists("username is already in use") from exc
                if audit is not None:
                    self._append_audit_event(connection, audit)
        except UserAlreadyExists:
            raise
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity user write failed") from exc
        return user

    def create_bootstrap_user_if_empty(
        self,
        factory: Callable[[], tuple[UserRecord, AuditWrite]] | None,
    ) -> UserRecord | None:
        """Create exactly one bootstrap user while serializing independent workers."""

        try:
            with self._identity_change_transaction() as connection:
                existing = connection.execute(
                    select(users_table.c.user_id).limit(1)
                ).first()
                if existing is not None:
                    return None
                if factory is None:
                    raise BootstrapUserRequired(
                        "accounts mode requires bootstrap admin credentials for an empty database"
                    )
                user, audit = factory()
                try:
                    connection.execute(
                        insert(users_table).values(**_user_values(user))
                    )
                except IntegrityError as exc:
                    raise UserAlreadyExists("username is already in use") from exc
                self._append_audit_event(connection, audit)
                return user
        except (BootstrapUserRequired, UserAlreadyExists):
            raise
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity bootstrap write failed") from exc

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._find_user(users_table.c.user_id == user_id)

    def get_user_by_username(self, username: str) -> UserRecord | None:
        return self._find_user(users_table.c.username == username)

    def list_users(self) -> list[UserRecord]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(users_table).order_by(users_table.c.username)
                ).mappings().fetchall()
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity user list failed") from exc
        return [_user_from_row(row) for row in rows]

    def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        roles: tuple[UserRole, ...] | None = None,
        enabled: bool | None = None,
        password_hash: str | None = None,
        audit: AuditWrite | None = None,
    ) -> UserRecord:
        now = _utc_now()
        try:
            with self._identity_change_transaction() as connection:
                row = connection.execute(
                    select(users_table)
                    .where(users_table.c.user_id == user_id)
                    .with_for_update()
                ).mappings().first()
                if row is None:
                    raise UserNotFound(f"user not found: {user_id}")
                current = _user_from_row(row)
                next_roles = (
                    normalize_roles(roles) if roles is not None else current.roles
                )
                next_enabled = enabled if enabled is not None else current.enabled
                removes_admin = (
                    current.enabled
                    and "admin" in current.roles
                    and (not next_enabled or "admin" not in next_roles)
                )
                if removes_admin and _count_enabled_admins(connection) <= 1:
                    raise LastAdminInvariantViolation(
                        "the final enabled administrator cannot be removed"
                    )
                security_change = any(
                    (
                        roles is not None and next_roles != current.roles,
                        enabled is not None and enabled != current.enabled,
                        password_hash is not None and password_hash != current.password_hash,
                    )
                )
                values: dict[str, Any] = {"updated_at": _dt_string(now)}
                if display_name is not None:
                    values["display_name"] = display_name
                if roles is not None:
                    values["roles"] = _json_dump(list(next_roles))
                if enabled is not None:
                    values["enabled"] = enabled
                if password_hash is not None:
                    values["password_hash"] = password_hash
                if security_change:
                    values["auth_version"] = current.auth_version + 1
                connection.execute(
                    update(users_table)
                    .where(users_table.c.user_id == user_id)
                    .values(**values)
                )
                if security_change:
                    connection.execute(
                        update(sessions_table)
                        .where(
                            (sessions_table.c.user_id == user_id)
                            & sessions_table.c.revoked_at.is_(None)
                        )
                        .values(revoked_at=_dt_string(now))
                    )
                updated_row = connection.execute(
                    select(users_table).where(users_table.c.user_id == user_id)
                ).mappings().one()
                updated = _user_from_row(updated_row)
                if audit is not None:
                    self._append_audit_event(
                        connection,
                        replace(
                            audit,
                            details={
                                **(audit.details or {}),
                                "roles": list(updated.roles),
                                "enabled": updated.enabled,
                                "auth_version": updated.auth_version,
                            },
                        ),
                    )
        except (LastAdminInvariantViolation, UserNotFound):
            raise
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity user update failed") from exc
        return updated

    def create_session(
        self,
        session: SessionRecord,
        *,
        audit: AuditWrite | None = None,
    ) -> SessionRecord:
        try:
            with self._write_lock, self.engine.begin() as connection:
                try:
                    connection.execute(
                        insert(sessions_table).values(**_session_values(session))
                    )
                except IntegrityError as exc:
                    raise AuthStoreError("identity session collision") from exc
                if audit is not None:
                    self._append_audit_event(connection, audit)
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity session write failed") from exc
        return session

    def authenticate(
        self,
        token_hash: str,
        *,
        now: datetime,
        idle_timeout_seconds: int,
        absolute_expires_at: datetime,
    ) -> tuple[UserRecord, SessionRecord] | None:
        if (
            not isinstance(idle_timeout_seconds, int)
            or isinstance(idle_timeout_seconds, bool)
            or idle_timeout_seconds < 1
        ):
            raise ValueError("idle_timeout_seconds must be positive")
        now = _require_aware_utc(now, name="now")
        absolute_expires_at = _require_aware_utc(
            absolute_expires_at,
            name="absolute_expires_at",
        )
        try:
            with self.engine.begin() as connection:
                row = connection.execute(
                    select(sessions_table).where(sessions_table.c.token_hash == token_hash)
                ).mappings().first()
                if row is None:
                    return None
                session = _session_from_row(row)
                if (
                    session.revoked_at is not None
                    or session.expires_at <= now
                    or absolute_expires_at <= now
                    or session.created_at >= absolute_expires_at
                    or session.expires_at > absolute_expires_at
                    or session.last_seen_at
                    + timedelta(seconds=idle_timeout_seconds)
                    <= now
                ):
                    return None
                user_row = connection.execute(
                    select(users_table).where(users_table.c.user_id == session.user_id)
                ).mappings().first()
                if user_row is None:
                    return None
                user = _user_from_row(user_row)
                if not user.enabled or user.auth_version != session.auth_version:
                    return None
                if (now - session.last_seen_at).total_seconds() >= 60:
                    connection.execute(
                        update(sessions_table)
                        .where(sessions_table.c.session_id == session.session_id)
                        .values(last_seen_at=_dt_string(now))
                    )
                    session = session.model_copy(update={"last_seen_at": now})
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity session read failed") from exc
        return user, session

    def rotate_session(
        self,
        session_id: str,
        *,
        expected_token_hash: str,
        next_token_hash: str,
        now: datetime,
        idle_timeout_seconds: int,
        extension_seconds: int,
        absolute_expires_at: datetime,
        audit: AuditWrite | None = None,
    ) -> tuple[UserRecord, SessionRecord] | None:
        if (
            any(
                not isinstance(value, int)
                or isinstance(value, bool)
                for value in (
                    idle_timeout_seconds,
                    extension_seconds,
                )
            )
            or not 0 < idle_timeout_seconds <= extension_seconds
        ):
            raise ValueError("session lifetime must satisfy idle <= extension")
        now = _require_aware_utc(now, name="now")
        absolute_expires_at = _require_aware_utc(
            absolute_expires_at,
            name="absolute_expires_at",
        )
        try:
            with self._session_write_transaction() as connection:
                locator = connection.execute(
                    select(sessions_table.c.user_id).where(
                        sessions_table.c.session_id == session_id
                    )
                ).scalar_one_or_none()
                if locator is None:
                    return None
                user_row = connection.execute(
                    select(users_table)
                    .where(users_table.c.user_id == locator)
                    .with_for_update()
                ).mappings().first()
                if user_row is None:
                    return None
                user = _user_from_row(user_row)
                row = connection.execute(
                    select(sessions_table)
                    .where(
                        (sessions_table.c.session_id == session_id)
                        & (sessions_table.c.user_id == locator)
                    )
                    .with_for_update()
                ).mappings().first()
                if row is None:
                    return None
                session = _session_from_row(row)
                if (
                    session.token_hash != expected_token_hash
                    or session.revoked_at is not None
                    or session.expires_at <= now
                    or absolute_expires_at <= now
                    or session.created_at >= absolute_expires_at
                    or session.expires_at > absolute_expires_at
                    or session.last_seen_at
                    + timedelta(seconds=idle_timeout_seconds)
                    <= now
                ):
                    return None
                if not user.enabled or user.auth_version != session.auth_version:
                    return None

                next_expires_at = min(
                    now + timedelta(seconds=extension_seconds),
                    absolute_expires_at,
                )
                if next_expires_at <= now:
                    return None
                result = connection.execute(
                    update(sessions_table)
                    .where(
                        (sessions_table.c.session_id == session_id)
                        & (
                            sessions_table.c.token_hash
                            == expected_token_hash
                        )
                        & sessions_table.c.revoked_at.is_(None)
                    )
                    .values(
                        token_hash=next_token_hash,
                        expires_at=_dt_string(next_expires_at),
                        last_seen_at=_dt_string(now),
                    )
                )
                if result.rowcount != 1:
                    return None
                rotated = session.model_copy(
                    update={
                        "token_hash": next_token_hash,
                        "expires_at": next_expires_at,
                        "last_seen_at": now,
                    }
                )
                if audit is not None:
                    self._append_audit_event(
                        connection,
                        replace(
                            audit,
                            details={
                                **(audit.details or {}),
                                "expires_at": _dt_string(next_expires_at),
                                "absolute_expires_at": _dt_string(
                                    absolute_expires_at
                                ),
                            },
                        ),
                    )
                return user, rotated
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity session rotation failed") from exc

    def revoke_session(
        self,
        session_id: str,
        *,
        now: datetime,
        audit: AuditWrite | None = None,
    ) -> bool:
        try:
            with self._write_lock, self.engine.begin() as connection:
                result = connection.execute(
                    update(sessions_table)
                    .where(
                        (sessions_table.c.session_id == session_id)
                        & sessions_table.c.revoked_at.is_(None)
                    )
                    .values(revoked_at=_dt_string(now))
                )
                revoked = result.rowcount == 1
                if audit is not None:
                    self._append_audit_event(
                        connection,
                        replace(
                            audit,
                            details={**(audit.details or {}), "revoked": revoked},
                        ),
                    )
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity session revocation failed") from exc
        return revoked

    def invalidate_user_sessions(
        self,
        user_id: str,
        *,
        now: datetime,
        audit: AuditWrite | None = None,
    ) -> tuple[UserRecord, int]:
        try:
            with self._identity_change_transaction() as connection:
                row = connection.execute(
                    select(users_table)
                    .where(users_table.c.user_id == user_id)
                    .with_for_update()
                ).mappings().first()
                if row is None:
                    raise UserNotFound(f"user not found: {user_id}")
                current = _user_from_row(row)
                next_auth_version = current.auth_version + 1
                connection.execute(
                    update(users_table)
                    .where(users_table.c.user_id == user_id)
                    .values(
                        auth_version=next_auth_version,
                        updated_at=_dt_string(now),
                    )
                )
                result = connection.execute(
                    update(sessions_table)
                    .where(
                        (sessions_table.c.user_id == user_id)
                        & sessions_table.c.revoked_at.is_(None)
                    )
                    .values(revoked_at=_dt_string(now))
                )
                revoked_count = max(0, int(result.rowcount or 0))
                updated_row = connection.execute(
                    select(users_table).where(users_table.c.user_id == user_id)
                ).mappings().one()
                updated = _user_from_row(updated_row)
                if audit is not None:
                    self._append_audit_event(
                        connection,
                        replace(
                            audit,
                            details={
                                **(audit.details or {}),
                                "revoked_sessions": revoked_count,
                                "roles": list(updated.roles),
                                "enabled": updated.enabled,
                                "auth_version": updated.auth_version,
                            },
                        ),
                    )
                return updated, revoked_count
        except UserNotFound:
            raise
        except SQLAlchemyError as exc:
            raise AuthStoreError(
                "identity session invalidation failed"
            ) from exc

    def append_audit(
        self,
        *,
        occurred_at: datetime,
        actor_user_id: str | None,
        actor_session_id: str | None,
        actor_roles: tuple[UserRole, ...],
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        audit = AuditWrite(
            occurred_at=occurred_at,
            actor_user_id=actor_user_id,
            actor_session_id=actor_session_id,
            actor_roles=actor_roles,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            request_id=request_id,
            details=details,
        )
        try:
            with self._write_lock, self.engine.begin() as connection:
                return self._append_audit_event(connection, audit)
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity audit write failed") from exc

    def append_audit_in_transaction(
        self,
        connection: Connection,
        audit: AuditWrite,
    ) -> AuditEvent:
        """Append an audit event inside a caller-owned business transaction."""

        return self._append_audit_event(connection, audit)

    def list_audit(self, *, limit: int = 100) -> list[AuditEvent]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    select(audit_events_table)
                    .order_by(audit_events_table.c.sequence.desc())
                    .limit(limit)
                ).mappings().fetchall()
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity audit read failed") from exc
        return [_audit_from_row(row) for row in rows]

    def verify_audit_chain(self) -> bool:
        try:
            with self.engine.connect() as connection:
                if connection.dialect.name == "postgresql":
                    connection.execution_options(
                        isolation_level="REPEATABLE READ"
                    )
                rows = connection.execute(
                    select(audit_events_table).order_by(audit_events_table.c.sequence)
                ).mappings().fetchall()
                head = connection.execute(
                    select(audit_head_table).where(audit_head_table.c.head_id == 1)
                ).mappings().one()
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity audit verification failed") from exc
        previous_hash = ZERO_HASH
        expected_sequence = 1
        for row in rows:
            event = _audit_from_row(row)
            payload = {
                "sequence": event.sequence,
                "event_id": event.event_id,
                "occurred_at": _dt_string(event.occurred_at),
                "actor_user_id": event.actor_user_id,
                "actor_session_id": event.actor_session_id,
                "actor_roles": list(event.actor_roles),
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "outcome": event.outcome,
                "request_id": event.request_id,
                "details": event.details,
                "previous_hash": event.previous_hash,
            }
            if event.sequence != expected_sequence or event.previous_hash != previous_hash:
                return False
            if event.event_hash != _checksum(payload):
                return False
            previous_hash = event.event_hash
            expected_sequence += 1
        return int(head["sequence"]) == len(rows) and str(head["event_hash"]) == previous_hash

    def _find_user(self, condition: Any) -> UserRecord | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(
                    select(users_table).where(condition)
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise AuthStoreError("identity user read failed") from exc
        return _user_from_row(row) if row is not None else None

    @contextmanager
    def _identity_change_transaction(self) -> Iterator[Connection]:
        with self._write_lock, self.engine.connect() as connection:
            try:
                dialect = connection.dialect.name
                if dialect == "sqlite":
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                elif dialect == "postgresql":
                    connection.begin()
                    connection.execute(
                        text("SELECT pg_advisory_xact_lock(:lock_id)"),
                        {"lock_id": _POSTGRES_IDENTITY_INVARIANT_LOCK_ID},
                    )
                else:
                    raise AuthStoreError(
                        f"identity transactions do not support dialect: {dialect}"
                    )
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @contextmanager
    def _session_write_transaction(self) -> Iterator[Connection]:
        with self._write_lock, self.engine.connect() as connection:
            try:
                if connection.dialect.name == "sqlite":
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                elif connection.dialect.name == "postgresql":
                    connection.begin()
                else:
                    raise AuthStoreError(
                        "session transactions do not support this database"
                    )
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _append_audit_event(
        self,
        connection: Connection,
        audit: AuditWrite,
    ) -> AuditEvent:
        event_id = f"aud_{uuid4().hex}"
        safe_details = audit.details or {}
        head = connection.execute(
            select(audit_head_table)
            .where(audit_head_table.c.head_id == 1)
            .with_for_update()
        ).mappings().one()
        sequence = int(head["sequence"]) + 1
        previous_hash = str(head["event_hash"])
        payload = {
            "sequence": sequence,
            "event_id": event_id,
            "occurred_at": _dt_string(audit.occurred_at),
            "actor_user_id": audit.actor_user_id,
            "actor_session_id": audit.actor_session_id,
            "actor_roles": list(normalize_roles(audit.actor_roles)) if audit.actor_roles else [],
            "action": audit.action,
            "resource_type": audit.resource_type,
            "resource_id": audit.resource_id,
            "outcome": audit.outcome,
            "request_id": audit.request_id,
            "details": safe_details,
            "previous_hash": previous_hash,
        }
        event_hash = _checksum(payload)
        result = connection.execute(
            update(audit_head_table)
            .where(
                (audit_head_table.c.head_id == 1)
                & (audit_head_table.c.sequence == int(head["sequence"]))
                & (audit_head_table.c.event_hash == previous_hash)
            )
            .values(sequence=sequence, event_hash=event_hash)
        )
        if result.rowcount != 1:
            raise AuditHeadBusy("identity audit head changed during write")
        connection.execute(
            insert(audit_events_table).values(
                **{
                    **payload,
                    "actor_roles": _json_dump(payload["actor_roles"]),
                    "details": _json_dump(safe_details),
                    "event_hash": event_hash,
                }
            )
        )
        return AuditEvent(**payload, event_hash=event_hash)

def _user_values(user: UserRecord) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "password_hash": user.password_hash,
        "roles": _json_dump(list(user.roles)),
        "enabled": user.enabled,
        "auth_version": user.auth_version,
        "created_at": _dt_string(user.created_at),
        "updated_at": _dt_string(user.updated_at),
    }


def _count_enabled_admins(connection: Connection) -> int:
    rows = connection.execute(
        select(users_table.c.enabled, users_table.c.roles)
    ).mappings()
    return sum(
        1
        for row in rows
        if bool(row["enabled"]) and "admin" in tuple(json.loads(row["roles"]))
    )


def _session_values(session: SessionRecord) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "token_hash": session.token_hash,
        "user_id": session.user_id,
        "auth_version": session.auth_version,
        "created_at": _dt_string(session.created_at),
        "expires_at": _dt_string(session.expires_at),
        "last_seen_at": _dt_string(session.last_seen_at),
        "revoked_at": _dt_string(session.revoked_at) if session.revoked_at else None,
    }


def _user_from_row(row: RowMapping) -> UserRecord:
    return UserRecord(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        password_hash=row["password_hash"],
        roles=tuple(json.loads(row["roles"])),
        enabled=bool(row["enabled"]),
        auth_version=int(row["auth_version"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _session_from_row(row: RowMapping) -> SessionRecord:
    return SessionRecord(
        session_id=row["session_id"],
        token_hash=row["token_hash"],
        user_id=row["user_id"],
        auth_version=int(row["auth_version"]),
        created_at=_parse_dt(row["created_at"]),
        expires_at=_parse_dt(row["expires_at"]),
        last_seen_at=_parse_dt(row["last_seen_at"]),
        revoked_at=_parse_dt(row["revoked_at"]) if row["revoked_at"] else None,
    )


def _audit_from_row(row: RowMapping) -> AuditEvent:
    return AuditEvent(
        sequence=int(row["sequence"]),
        event_id=row["event_id"],
        occurred_at=_parse_dt(row["occurred_at"]),
        actor_user_id=row["actor_user_id"],
        actor_session_id=row["actor_session_id"],
        actor_roles=tuple(json.loads(row["actor_roles"])),
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        outcome=row["outcome"],
        request_id=row["request_id"],
        details=json.loads(row["details"]),
        previous_hash=row["previous_hash"],
        event_hash=row["event_hash"],
    )


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_string(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _require_aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
