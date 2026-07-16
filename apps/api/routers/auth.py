from __future__ import annotations

import hashlib
import re
from typing import Annotated, NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth_dependencies import AuthContext, require_auth_context, require_permission
from settings import settings
from services.auth import (
    AccountsModeRequired,
    AuthError,
    AuthStoreError,
    InvalidCredentials,
    LastAdminRequired,
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


class LoginResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    principal: dict


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


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    try:
        issued = get_identity().login(
            payload.username,
            payload.password,
            request_id=_request_id(request),
            client_fingerprint=_client_fingerprint(request),
        )
    except Exception as exc:
        _raise_auth_error(exc)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=issued.token,
        max_age=settings.auth_session_ttl_seconds,
        expires=issued.record.expires_at,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return LoginResponse(
        access_token=issued.token,
        expires_at=issued.record.expires_at.isoformat(),
        principal=issued.principal.model_dump(mode="json"),
    )


@router.get("/me")
async def me(context: AuthContext = Depends(require_auth_context)) -> dict:
    return {"principal": context.principal.model_dump(mode="json"), "source": context.source}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_auth_context),
) -> Response:
    try:
        if not context.principal.synthetic:
            get_identity().logout(context.principal, request_id=_request_id(request))
    except Exception as exc:
        _raise_auth_error(exc)
    response.delete_cookie(
        settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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
            request_id=_request_id(request),
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
            request_id=_request_id(request),
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
            request_id=_request_id(request),
        )
    except Exception as exc:
        _raise_auth_error(exc)


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


def _raise_auth_error(exc: Exception) -> NoReturn:
    if isinstance(exc, InvalidCredentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": "Username or password is invalid."},
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


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    if supplied and re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", supplied):
        return supplied
    return f"req_{uuid4().hex}"


def _client_fingerprint(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    agent = request.headers.get("User-Agent", "")[:200]
    return hashlib.sha256(f"{host}\x1f{agent}".encode("utf-8")).hexdigest()[:24]
