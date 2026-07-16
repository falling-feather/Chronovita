from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from settings import settings
from services.auth import Principal, get_identity, has_permission


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
    def dependency(context: AuthContext = Depends(require_auth_context)) -> AuthContext:
        if not has_permission(context.principal, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": "The authenticated account cannot perform this action.",
                },
            )
        return context

    return dependency


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
