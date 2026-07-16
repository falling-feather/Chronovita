from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UserRole = Literal["student", "teacher", "reviewer", "admin"]

ROLE_ORDER: tuple[UserRole, ...] = (
    "student",
    "teacher",
    "reviewer",
    "admin",
)


class AuthModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class UserRecord(AuthModel):
    user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    password_hash: str = Field(min_length=32, max_length=512)
    roles: tuple[UserRole, ...] = Field(min_length=1)
    enabled: bool = True
    auth_version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: tuple[UserRole, ...]) -> tuple[UserRole, ...]:
        return normalize_roles(value)


class Principal(AuthModel):
    user_id: str
    username: str
    display_name: str
    roles: tuple[UserRole, ...] = Field(min_length=1)
    session_id: str | None = None
    auth_version: int = Field(ge=1)
    synthetic: bool = False

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: tuple[UserRole, ...]) -> tuple[UserRole, ...]:
        return normalize_roles(value)


class UserView(AuthModel):
    user_id: str
    username: str
    display_name: str
    roles: tuple[UserRole, ...]
    enabled: bool
    auth_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, user: UserRecord) -> "UserView":
        return cls(**user.model_dump(exclude={"password_hash"}))


class SessionRecord(AuthModel):
    session_id: str = Field(pattern=r"^ses_[a-f0-9]{32}$")
    token_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    user_id: str = Field(pattern=r"^usr_[a-f0-9]{32}$")
    auth_version: int = Field(ge=1)
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None


class IssuedSession(AuthModel):
    token: str = Field(min_length=32, max_length=256)
    record: SessionRecord
    principal: Principal


class AuditEvent(AuthModel):
    sequence: int = Field(ge=1)
    event_id: str = Field(pattern=r"^aud_[a-f0-9]{32}$")
    occurred_at: datetime
    actor_user_id: str | None = None
    actor_session_id: str | None = None
    actor_roles: tuple[UserRole, ...] = ()
    action: str = Field(min_length=3, max_length=100, pattern=r"^[a-z][a-z0-9._-]+$")
    resource_type: str = Field(min_length=1, max_length=80)
    resource_id: str = Field(min_length=1, max_length=160)
    outcome: Literal["succeeded", "denied", "failed"]
    request_id: str = Field(min_length=1, max_length=100)
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


PERMISSIONS_BY_ROLE: dict[UserRole, frozenset[str]] = {
    "student": frozenset({"student.own"}),
    "teacher": frozenset({"content.read", "content.author", "student.summary"}),
    "reviewer": frozenset({"content.read", "content.review", "audit.review"}),
    "admin": frozenset(
        {
            "auth.manage_users",
            "audit.read",
            "content.read",
            "content.author",
            "content.review",
            "content.publish",
            "student.summary",
        }
    ),
}


def normalize_roles(roles: tuple[UserRole, ...] | list[UserRole]) -> tuple[UserRole, ...]:
    unique = set(roles)
    if not unique:
        raise ValueError("at least one role is required")
    return tuple(role for role in ROLE_ORDER if role in unique)


def has_permission(principal: Principal, permission: str) -> bool:
    return any(permission in PERMISSIONS_BY_ROLE[role] for role in principal.roles)
