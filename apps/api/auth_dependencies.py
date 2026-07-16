from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import Annotated, Any, Callable
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, status

from settings import settings
from services.auth import AuthStoreError, Principal, get_identity, has_permission


@dataclass(frozen=True)
class AuthContext:
    principal: Principal
    raw_token: str | None
    source: str


def require_auth_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> AuthContext:
    bearer = _bearer_token(authorization)
    cookie = request.cookies.get(settings.auth_cookie_name)
    if settings.auth_mode == "legacy-local":
        candidates = [value for value in (bearer, x_admin_token) if value]
        if len(set(candidates)) > 1:
            raise _authentication_error("credential_conflict", "Conflicting credentials.")
        token = candidates[0] if candidates else None
        if not settings.admin_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "legacy_auth_unavailable",
                    "message": "Local administrator token is not configured.",
                },
            )
        if token is None or not secrets.compare_digest(token, settings.admin_token):
            raise _authentication_error()
        return AuthContext(
            principal=Principal(
                user_id="legacy-local-admin",
                username=settings.admin_actor,
                display_name=settings.admin_actor,
                roles=("teacher", "reviewer", "admin"),
                session_id=None,
                auth_version=1,
                synthetic=True,
            ),
            raw_token=token,
            source="legacy-local",
        )

    if x_admin_token:
        raise _authentication_error("legacy_credential_rejected", "Legacy credential rejected.")
    candidates = [value for value in (bearer, cookie) if value]
    if len(set(candidates)) > 1:
        raise _authentication_error("credential_conflict", "Conflicting credentials.")
    token = candidates[0] if candidates else None
    if token is None:
        raise _authentication_error()
    principal = get_identity().authenticate(token)
    if principal is None:
        raise _authentication_error("session_expired", "Session is invalid or expired.")
    return AuthContext(
        principal=principal,
        raw_token=token,
        source="bearer" if bearer else "cookie",
    )


def require_permission(permission: str) -> Callable[..., AuthContext]:
    def dependency(
        request: Request,
        context: AuthContext = Depends(require_auth_context),
    ) -> AuthContext:
        if not has_permission(context.principal, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": "The authenticated account cannot perform this action.",
                },
            )
        _require_cookie_write_origin(request, context)
        return context

    return dependency


def require_student_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> AuthContext:
    """Resolve the authoritative owner for student-scoped resources."""

    if settings.auth_mode == "legacy-local":
        return AuthContext(
            principal=Principal(
                user_id=settings.game_user_id,
                username=settings.game_user_id,
                display_name="Local student",
                roles=("student",),
                session_id=None,
                auth_version=1,
                synthetic=True,
            ),
            raw_token=None,
            source="legacy-local-student",
        )

    context = require_auth_context(
        request,
        authorization=authorization,
        x_admin_token=x_admin_token,
    )
    if not has_permission(context.principal, "student.own"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "message": "The authenticated account cannot perform this action.",
            },
        )
    _require_cookie_write_origin(request, context)
    return context


def trusted_actor(context: AuthContext) -> str:
    if context.principal.synthetic:
        return context.principal.username
    return context.principal.user_id


def audit_authorized_action(
    request: Request,
    context: AuthContext,
    *,
    permission: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    if not has_permission(context.principal, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "message": "The authenticated account cannot perform this action.",
            },
        )
    if context.principal.synthetic:
        return
    _require_cookie_write_origin(request, context)
    try:
        get_identity().record_authorized_action(
            principal=context.principal,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id(request),
            details={
                "permission": permission,
                "client": client_fingerprint(request),
                **(details or {}),
            },
        )
    except AuthStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.code,
                "message": "Required audit storage is unavailable.",
            },
        ) from exc


def request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    if supplied and re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", supplied):
        return supplied
    return f"req_{uuid4().hex}"


def client_fingerprint(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    agent = request.headers.get("User-Agent", "")[:200]
    return hashlib.sha256(f"{host}\x1f{agent}".encode("utf-8")).hexdigest()[:24]


def _require_cookie_write_origin(request: Request, context: AuthContext) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"} or context.source != "cookie":
        return
    origin = request.headers.get("Origin", "").strip()
    if not origin or origin not in settings.cors_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "csrf_origin_rejected",
                "message": "Cookie-authenticated writes require a trusted Origin.",
            },
        )


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise _authentication_error("invalid_authorization", "Invalid Authorization header.")
    return token.strip()


def _authentication_error(
    code: str = "authentication_required",
    message: str = "Authentication is required.",
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )
