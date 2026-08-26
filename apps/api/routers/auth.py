from __future__ import annotations

import math
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth_dependencies import (
    AuthContext,
    LogoutContext,
    client_fingerprint,
    require_auth_write_context,
    require_cookie_login_origin,
    request_id,
    require_auth_context,
    require_permission,
    resolve_logout_context,
)
from settings import settings
from services.auth import (
    AccountsModeRequired,
    AuthError,
    AuthStoreError,
    InvalidCredentials,
    LastAdminRequired,
    SessionUnavailable,
    SessionTransport,
    UserAlreadyExists,
    UserNotFound,
    UserRole,
    UserView,
    get_identity,
)


router = APIRouter()


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(ApiModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class SessionResponse(ApiModel):
    transport: SessionTransport
    access_token: str | None = None
    token_type: Literal["bearer"] | None = None
    expires_at: str
    absolute_expires_at: str
    principal: dict


class AuthRuntimeResponse(ApiModel):
    mode: Literal["accounts", "legacy-local"]
    browser_transport: Literal["http-only-cookie"] = "http-only-cookie"


class UserListResponse(ApiModel):
    items: list[UserView]


class UserCreateRequest(ApiModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=80)
    roles: tuple[UserRole, ...] = Field(min_length=1)


class UserUpdateRequest(ApiModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    roles: tuple[UserRole, ...] | None = Field(default=None, min_length=1)
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UserUpdateRequest":
        if self.display_name is None and self.roles is None and self.enabled is None:
            raise ValueError("at least one user field must be supplied")
        return self


class PasswordResetRequest(ApiModel):
    password: str = Field(min_length=12, max_length=256)


class AuditResponse(ApiModel):
    valid_chain: bool
    items: list[dict]


class SessionRevocationResponse(ApiModel):
    user: UserView
    revoked_sessions: int = Field(ge=0)


@router.get("/config", response_model=AuthRuntimeResponse)
async def auth_runtime(response: Response) -> AuthRuntimeResponse:
    """Expose only the browser-safe authentication mode, never credentials."""

    response.headers["Cache-Control"] = "no-store"
    return AuthRuntimeResponse(mode=settings.auth_mode)


@router.post(
    "/login",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    require_cookie_login_origin(request)
    return _login(
        payload,
        request=request,
        response=response,
        transport="cookie",
    )


@router.post(
    "/token",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def issue_bearer_token(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    return _login(
        payload,
        request=request,
        response=response,
        transport="bearer",
    )


def _login(
    payload: LoginRequest,
    *,
    request: Request,
    response: Response,
    transport: SessionTransport,
) -> SessionResponse:
    try:
        issued = get_identity().login(
            payload.username,
            payload.password,
            request_id=request_id(request),
            client_fingerprint=client_fingerprint(request),
            transport=transport,
        )
    except Exception as exc:
        _raise_auth_error(exc)
    return _render_session(
        issued,
        request=request,
        response=response,
    )


@router.get("/me")
async def me(
    response: Response,
    context: AuthContext = Depends(require_auth_context),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"principal": context.principal.model_dump(mode="json"), "source": context.source}


@router.post(
    "/refresh",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def refresh_session(
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_auth_write_context),
) -> SessionResponse:
    try:
        issued = get_identity().refresh(
            context.raw_token or "",
            context.principal,
            request_id=request_id(request),
            transport=context.source,
        )
    except Exception as exc:
        _raise_auth_error(exc)
    return _render_session(
        issued,
        request=request,
        response=response,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    context: LogoutContext = Depends(resolve_logout_context),
) -> Response:
    try:
        if context.principal is not None and not context.principal.synthetic:
            get_identity().logout(context.principal, request_id=request_id(request))
    except Exception as exc:
        _raise_auth_error(exc)
    _delete_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/sessions/revoke-all",
    response_model=SessionRevocationResponse,
)
async def revoke_own_sessions(
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_auth_write_context),
) -> SessionRevocationResponse:
    return _revoke_user_sessions(
        context.principal.user_id,
        request=request,
        response=response,
        context=context,
    )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _: AuthContext = Depends(require_permission("auth.manage_users")),
) -> UserListResponse:
    try:
        return UserListResponse(items=get_identity().list_users())
    except Exception as exc:
        _raise_auth_error(exc)


@router.post("/users", response_model=UserView, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("auth.manage_users")),
) -> UserView:
    try:
        return get_identity().create_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            roles=payload.roles,
            actor=context.principal,
            request_id=request_id(request),
        )
    except Exception as exc:
        _raise_auth_error(exc)


@router.patch("/users/{user_id}", response_model=UserView)
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("auth.manage_users")),
) -> UserView:
    try:
        return get_identity().update_user(
            user_id,
            display_name=payload.display_name,
            roles=payload.roles,
            enabled=payload.enabled,
            actor=context.principal,
            request_id=request_id(request),
        )
    except Exception as exc:
        _raise_auth_error(exc)


@router.post("/users/{user_id}/password", response_model=UserView)
async def reset_password(
    user_id: str,
    payload: PasswordResetRequest,
    request: Request,
    context: AuthContext = Depends(require_permission("auth.manage_users")),
) -> UserView:
    try:
        return get_identity().reset_password(
            user_id,
            password=payload.password,
            actor=context.principal,
            request_id=request_id(request),
        )
    except Exception as exc:
        _raise_auth_error(exc)


@router.post(
    "/users/{user_id}/sessions/revoke",
    response_model=SessionRevocationResponse,
)
async def revoke_user_sessions(
    user_id: str,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_permission("auth.manage_users")),
) -> SessionRevocationResponse:
    return _revoke_user_sessions(
        user_id,
        request=request,
        response=response,
        context=context,
    )


@router.get("/audit", response_model=AuditResponse)
async def audit_events(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    _: AuthContext = Depends(require_permission("audit.read")),
) -> AuditResponse:
    try:
        service = get_identity()
        return AuditResponse(
            valid_chain=service.verify_audit_chain(),
            items=[event.model_dump(mode="json") for event in service.list_audit(limit=limit)],
        )
    except Exception as exc:
        _raise_auth_error(exc)


def _revoke_user_sessions(
    user_id: str,
    *,
    request: Request,
    response: Response,
    context: AuthContext,
) -> SessionRevocationResponse:
    try:
        user, revoked_count = get_identity().revoke_user_sessions(
            user_id,
            actor=context.principal,
            request_id=request_id(request),
        )
    except Exception as exc:
        _raise_auth_error(exc)
    if user_id == context.principal.user_id:
        _delete_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return SessionRevocationResponse(
        user=user,
        revoked_sessions=revoked_count,
    )


def _render_session(
    issued,
    *,
    request: Request,
    response: Response,
) -> SessionResponse:
    response.headers["Cache-Control"] = "no-store"
    if issued.transport == "cookie":
        remaining_seconds = max(
            0,
            math.ceil(
                (
                    issued.record.expires_at
                    - issued.record.last_seen_at
                ).total_seconds()
            ),
        )
        response.set_cookie(
            key=settings.auth_cookie_name,
            value=issued.token,
            max_age=remaining_seconds,
            expires=issued.record.expires_at,
            path="/",
            secure=settings.auth_cookie_secure,
            httponly=True,
            samesite="lax",
        )
    elif settings.auth_cookie_name in request.cookies:
        _delete_session_cookie(response)
    return SessionResponse(
        transport=issued.transport,
        access_token=issued.token if issued.transport == "bearer" else None,
        token_type="bearer" if issued.transport == "bearer" else None,
        expires_at=issued.record.expires_at.isoformat(),
        absolute_expires_at=issued.absolute_expires_at.isoformat(),
        principal=issued.principal.model_dump(mode="json"),
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _raise_auth_error(exc: Exception) -> NoReturn:
    if isinstance(exc, InvalidCredentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": "Username or password is invalid."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if isinstance(exc, SessionUnavailable):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": exc.code,
                "message": "Session is invalid or expired.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if isinstance(exc, AccountsModeRequired):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    if isinstance(exc, UserAlreadyExists):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": "Username is unavailable."},
        ) from exc
    if isinstance(exc, UserNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": "User was not found."},
        ) from exc
    if isinstance(exc, LastAdminRequired):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    if isinstance(exc, (ValueError, AuthError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": getattr(exc, "code", "invalid_auth_request"), "message": str(exc)},
        ) from exc
    if isinstance(exc, AuthStoreError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": "Identity service is unavailable."},
        ) from exc
    raise exc
