from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.engine import Engine

from .models import (
    AuditEvent,
    IssuedSession,
    Principal,
    SessionRecord,
    SessionTransport,
    UserRecord,
    UserRole,
    UserView,
    normalize_roles,
)
from .passwords import DUMMY_PASSWORD_HASH, hash_password, validate_password, verify_password
from .store import (
    AuditWrite,
    AuthStore,
    AuthStoreError,
    BootstrapUserRequired,
    LastAdminInvariantViolation,
)


AuthMode = Literal["legacy-local", "accounts"]
_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_SESSION_TOKEN_PREFIXES: dict[SessionTransport, str] = {
    "cookie": "cvs_cookie_",
    "bearer": "cvs_bearer_",
}


class AuthError(RuntimeError):
    code = "authentication_failed"


class InvalidCredentials(AuthError):
    code = "invalid_credentials"


class SessionUnavailable(AuthError):
    code = "session_expired"


class AccountsModeRequired(AuthError):
    code = "accounts_mode_required"


class BootstrapRequired(AuthError):
    code = "bootstrap_admin_required"


class LastAdminRequired(AuthError):
    code = "last_admin_required"


@dataclass(frozen=True)
class AuthServiceConfig:
    mode: AuthMode
    session_ttl_seconds: int
    session_idle_timeout_seconds: int | None = None
    session_absolute_ttl_seconds: int | None = None
    bootstrap_username: str = ""
    bootstrap_password: str = ""
    bootstrap_display_name: str = "Chronovita Admin"

    def __post_init__(self) -> None:
        idle_timeout = self.resolved_idle_timeout_seconds
        absolute_ttl = self.resolved_absolute_ttl_seconds
        if (
            any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
                for value in (
                    idle_timeout,
                    self.session_ttl_seconds,
                    absolute_ttl,
                )
            )
            or idle_timeout > self.session_ttl_seconds
            or self.session_ttl_seconds > absolute_ttl
        ):
            raise ValueError(
                "session lifetime must satisfy idle <= ttl <= absolute"
            )

    @property
    def resolved_idle_timeout_seconds(self) -> int:
        return (
            self.session_idle_timeout_seconds
            if self.session_idle_timeout_seconds is not None
            else self.session_ttl_seconds
        )

    @property
    def resolved_absolute_ttl_seconds(self) -> int:
        return (
            self.session_absolute_ttl_seconds
            if self.session_absolute_ttl_seconds is not None
            else self.session_ttl_seconds
        )


class AuthService:
    def __init__(self, engine: Engine, config: AuthServiceConfig) -> None:
        self.store = AuthStore(engine)
        self.config = config
        if config.mode == "accounts":
            self._bootstrap_if_empty()

    def login(
        self,
        username: str,
        password: str,
        *,
        request_id: str,
        client_fingerprint: str = "unknown",
        transport: SessionTransport = "bearer",
    ) -> IssuedSession:
        self._require_accounts_mode()
        normalized = normalize_username(username)
        user = self.store.get_user_by_username(normalized)
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        password_ok = verify_password(password, password_hash)
        if user is None or not password_ok or not user.enabled:
            self.store.append_audit(
                occurred_at=_utc_now(),
                actor_user_id=user.user_id if user else None,
                actor_session_id=None,
                actor_roles=user.roles if user else (),
                action="auth.login",
                resource_type="account",
                resource_id=_username_fingerprint(normalized),
                outcome="denied",
                request_id=request_id,
                details={
                    "client": client_fingerprint,
                    "transport": transport,
                },
            )
            raise InvalidCredentials("username or password is invalid")

        now = _utc_now()
        absolute_expires_at = now + timedelta(
            seconds=self.config.resolved_absolute_ttl_seconds
        )
        raw_token = _new_session_token(
            transport,
            absolute_expires_at=absolute_expires_at,
        )
        session = SessionRecord(
            session_id=f"ses_{uuid4().hex}",
            token_hash=token_digest(raw_token),
            user_id=user.user_id,
            auth_version=user.auth_version,
            created_at=now,
            expires_at=min(
                now + timedelta(seconds=self.config.session_ttl_seconds),
                absolute_expires_at,
            ),
            last_seen_at=now,
        )
        principal = _principal(user, session.session_id)
        self.store.create_session(
            session,
            audit=AuditWrite(
                occurred_at=now,
                actor_user_id=user.user_id,
                actor_session_id=session.session_id,
                actor_roles=user.roles,
                action="auth.login",
                resource_type="account",
                resource_id=user.user_id,
                outcome="succeeded",
                request_id=request_id,
                details={
                    "client": client_fingerprint,
                    "transport": transport,
                    "absolute_expires_at": (
                        absolute_expires_at.isoformat()
                    ),
                },
            ),
        )
        return IssuedSession(
            token=raw_token,
            transport=transport,
            absolute_expires_at=absolute_expires_at,
            record=session,
            principal=principal,
        )

    def authenticate(
        self,
        raw_token: str,
        *,
        transport: SessionTransport = "bearer",
    ) -> Principal | None:
        absolute_expires_at = session_token_absolute_expires_at(raw_token)
        if (
            self.config.mode != "accounts"
            or not raw_token
            or session_token_transport(raw_token) != transport
            or absolute_expires_at is None
        ):
            return None
        found = self.store.authenticate(
            token_digest(raw_token),
            now=_utc_now(),
            idle_timeout_seconds=self.config.resolved_idle_timeout_seconds,
            absolute_expires_at=absolute_expires_at,
        )
        if found is None:
            return None
        user, session = found
        return _principal(user, session.session_id)

    def refresh(
        self,
        raw_token: str,
        principal: Principal,
        *,
        request_id: str,
        transport: SessionTransport,
    ) -> IssuedSession:
        self._require_accounts_mode()
        absolute_expires_at = session_token_absolute_expires_at(raw_token)
        if (
            principal.session_id is None
            or not raw_token
            or session_token_transport(raw_token) != transport
            or absolute_expires_at is None
        ):
            raise SessionUnavailable("session is invalid or expired")
        now = _utc_now()
        next_token = _new_session_token(
            transport,
            absolute_expires_at=absolute_expires_at,
        )
        rotated = self.store.rotate_session(
            principal.session_id,
            expected_token_hash=token_digest(raw_token),
            next_token_hash=token_digest(next_token),
            now=now,
            idle_timeout_seconds=self.config.resolved_idle_timeout_seconds,
            extension_seconds=self.config.session_ttl_seconds,
            absolute_expires_at=absolute_expires_at,
            audit=AuditWrite(
                occurred_at=now,
                actor_user_id=principal.user_id,
                actor_session_id=principal.session_id,
                actor_roles=principal.roles,
                action="auth.session.refresh",
                resource_type="session",
                resource_id=principal.session_id,
                outcome="succeeded",
                request_id=request_id,
            ),
        )
        if rotated is None:
            raise SessionUnavailable("session is invalid or expired")
        user, session = rotated
        return IssuedSession(
            token=next_token,
            transport=transport,
            absolute_expires_at=absolute_expires_at,
            record=session,
            principal=_principal(user, session.session_id),
        )

    def logout(self, principal: Principal, *, request_id: str) -> None:
        if principal.session_id is None:
            return
        now = _utc_now()
        self.store.revoke_session(
            principal.session_id,
            now=now,
            audit=AuditWrite(
                occurred_at=now,
                actor_user_id=principal.user_id,
                actor_session_id=principal.session_id,
                actor_roles=principal.roles,
                action="auth.logout",
                resource_type="session",
                resource_id=principal.session_id,
                outcome="succeeded",
                request_id=request_id,
            ),
        )

    def revoke_user_sessions(
        self,
        user_id: str,
        *,
        actor: Principal,
        request_id: str,
    ) -> tuple[UserView, int]:
        self._require_accounts_mode()
        updated, revoked_count = self.store.invalidate_user_sessions(
            user_id,
            now=_utc_now(),
            audit=self._admin_change_audit(
                actor=actor,
                action="auth.user.sessions_revoke",
                resource_id=user_id,
                request_id=request_id,
                details={},
            ),
        )
        return UserView.from_record(updated), revoked_count

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        roles: tuple[UserRole, ...],
        actor: Principal,
        request_id: str,
    ) -> UserView:
        self._require_accounts_mode()
        user = self._new_user(
            username=username,
            password=password,
            display_name=display_name,
            roles=roles,
        )
        self.store.create_user(
            user,
            audit=self._admin_change_audit(
                actor=actor,
                action="auth.user.create",
                resource_id=user.user_id,
                request_id=request_id,
                details={"roles": list(user.roles)},
            ),
        )
        return UserView.from_record(user)

    def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None,
        roles: tuple[UserRole, ...] | None,
        enabled: bool | None,
        actor: Principal,
        request_id: str,
    ) -> UserView:
        self._require_accounts_mode()
        if display_name is not None:
            display_name = normalize_display_name(display_name)
        normalized_roles = normalize_roles(roles) if roles is not None else None
        try:
            updated = self.store.update_user(
                user_id,
                display_name=display_name,
                roles=normalized_roles,
                enabled=enabled,
                audit=self._admin_change_audit(
                    actor=actor,
                    action="auth.user.update",
                    resource_id=user_id,
                    request_id=request_id,
                    details={},
                ),
            )
        except LastAdminInvariantViolation as exc:
            raise LastAdminRequired(
                "the final enabled administrator cannot be removed"
            ) from exc
        return UserView.from_record(updated)

    def reset_password(
        self,
        user_id: str,
        *,
        password: str,
        actor: Principal,
        request_id: str,
    ) -> UserView:
        self._require_accounts_mode()
        validate_password(password)
        updated = self.store.update_user(
            user_id,
            password_hash=hash_password(password),
            audit=self._admin_change_audit(
                actor=actor,
                action="auth.user.password_reset",
                resource_id=user_id,
                request_id=request_id,
                details={},
            ),
        )
        return UserView.from_record(updated)

    def list_users(self) -> list[UserView]:
        self._require_accounts_mode()
        return [UserView.from_record(user) for user in self.store.list_users()]

    def list_audit(self, *, limit: int) -> list[AuditEvent]:
        self._require_accounts_mode()
        return self.store.list_audit(limit=limit)

    def verify_audit_chain(self) -> bool:
        self._require_accounts_mode()
        return self.store.verify_audit_chain()

    def record_authorized_action(
        self,
        *,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: str,
        request_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        self._require_accounts_mode()
        return self.store.append_audit(
            occurred_at=_utc_now(),
            actor_user_id=principal.user_id,
            actor_session_id=principal.session_id,
            actor_roles=principal.roles,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome="succeeded",
            request_id=request_id,
            details=details,
        )

    def _bootstrap_if_empty(self) -> None:
        factory = None
        if self.config.bootstrap_username and self.config.bootstrap_password:
            factory = self._build_bootstrap_user
        try:
            self.store.create_bootstrap_user_if_empty(factory)
        except BootstrapUserRequired as exc:
            raise BootstrapRequired(
                "accounts mode requires bootstrap admin credentials for an empty database"
            ) from exc

    def _build_bootstrap_user(self) -> tuple[UserRecord, AuditWrite]:
        user = self._new_user(
            username=self.config.bootstrap_username,
            password=self.config.bootstrap_password,
            display_name=self.config.bootstrap_display_name,
            roles=("admin",),
        )
        return (
            user,
            AuditWrite(
                occurred_at=user.created_at,
                actor_user_id=user.user_id,
                actor_session_id=None,
                actor_roles=user.roles,
                action="auth.bootstrap",
                resource_type="account",
                resource_id=user.user_id,
                outcome="succeeded",
                request_id="startup-bootstrap",
                details={"roles": list(user.roles)},
            ),
        )

    def _new_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        roles: tuple[UserRole, ...],
    ) -> UserRecord:
        try:
            normalized_username = normalize_username(username)
        except InvalidCredentials as exc:
            raise ValueError(
                "username must use 3 to 64 ASCII letters, digits, dots, underscores or hyphens"
            ) from exc
        normalized_display_name = normalize_display_name(display_name)
        normalized_roles = normalize_roles(roles)
        now = _utc_now()
        return UserRecord(
            user_id=f"usr_{uuid4().hex}",
            username=normalized_username,
            display_name=normalized_display_name,
            password_hash=hash_password(password),
            roles=normalized_roles,
            enabled=True,
            auth_version=1,
            created_at=now,
            updated_at=now,
        )

    def _admin_change_audit(
        self,
        *,
        actor: Principal,
        action: str,
        resource_id: str,
        request_id: str,
        details: dict[str, Any],
    ) -> AuditWrite:
        return AuditWrite(
            occurred_at=_utc_now(),
            actor_user_id=actor.user_id,
            actor_session_id=actor.session_id,
            actor_roles=actor.roles,
            action=action,
            resource_type="account",
            resource_id=resource_id,
            outcome="succeeded",
            request_id=request_id,
            details=details,
        )

    def _require_accounts_mode(self) -> None:
        if self.config.mode != "accounts":
            raise AccountsModeRequired("account management is disabled in legacy-local mode")


_SERVICE: AuthService | None = None


def configure_identity(engine: Engine, config: AuthServiceConfig) -> AuthService:
    global _SERVICE
    _SERVICE = AuthService(engine, config)
    return _SERVICE


def shutdown_identity() -> None:
    global _SERVICE
    _SERVICE = None


def get_identity() -> AuthService:
    if _SERVICE is None:
        raise AuthStoreError("identity service is not configured")
    return _SERVICE


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not _USERNAME.fullmatch(normalized):
        raise InvalidCredentials("username or password is invalid")
    return normalized


def normalize_display_name(display_name: str) -> str:
    normalized = display_name.strip()
    if not normalized or len(normalized) > 80:
        raise ValueError("display name must contain 1 to 80 characters")
    return normalized


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def session_token_transport(raw_token: str) -> SessionTransport | None:
    if not 32 <= len(raw_token) <= 256:
        return None
    for transport, prefix in _SESSION_TOKEN_PREFIXES.items():
        if raw_token.startswith(prefix):
            return transport
    return None


def session_token_absolute_expires_at(
    raw_token: str,
) -> datetime | None:
    transport = session_token_transport(raw_token)
    if transport is None:
        return None
    encoded = raw_token[len(_SESSION_TOKEN_PREFIXES[transport]):]
    micros_text, separator, secret = encoded.partition("_")
    if (
        separator != "_"
        or not 1 <= len(micros_text) <= 20
        or not micros_text.isascii()
        or not micros_text.isdecimal()
        or len(secret) < 32
    ):
        return None
    try:
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=int(micros_text)
        )
    except (OverflowError, ValueError):
        return None


def _new_session_token(
    transport: SessionTransport,
    *,
    absolute_expires_at: datetime,
) -> str:
    if (
        absolute_expires_at.tzinfo is None
        or absolute_expires_at.utcoffset() is None
    ):
        raise ValueError("absolute_expires_at must include a timezone")
    utc_deadline = absolute_expires_at.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    epoch_micros = int((utc_deadline - epoch) // timedelta(microseconds=1))
    return (
        f"{_SESSION_TOKEN_PREFIXES[transport]}{epoch_micros}_"
        f"{secrets.token_urlsafe(32)}"
    )


def _principal(user: UserRecord, session_id: str) -> Principal:
    return Principal(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        roles=user.roles,
        session_id=session_id,
        auth_version=user.auth_version,
    )


def _username_fingerprint(username: str) -> str:
    return "username:" + hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
