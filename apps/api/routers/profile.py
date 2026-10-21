from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auth_dependencies import AuthContext, require_auth_context, require_auth_write_context
from services.auth import get_identity
from services.auth.profile import ProfileUpdate, ProfileView, read_profile, save_profile, change_password
from services.auth.store import AccountConflict
from .auth import _delete_session_cookie, _raise_auth_error

router = APIRouter()


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
    expected_user_id: str | None = None


def _error(exc: Exception):
    if isinstance(exc, AccountConflict):
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    if isinstance(exc, ValidationError):
        raise HTTPException(503, detail="资料存储校验失败，请联系管理员") from exc
    _raise_auth_error(exc)


@router.get("/", response_model=ProfileView)
async def profile(response: Response, context: AuthContext = Depends(require_auth_context)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return read_profile(get_identity(), context.principal)
    except Exception as exc:
        _error(exc)


@router.put("/", response_model=ProfileView)
async def update_profile(payload: ProfileUpdate, request: Request, response: Response,
                         context: AuthContext = Depends(require_auth_write_context)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return save_profile(get_identity(), context.principal, payload,
                            getattr(request.state, "request_id", "profile-update"))
    except Exception as exc:
        _error(exc)


@router.post("/password", status_code=204)
async def password(payload: PasswordChange, request: Request, response: Response,
                   context: AuthContext = Depends(require_auth_write_context)):
    try:
        if payload.expected_user_id is not None and payload.expected_user_id != context.principal.user_id:
            raise AccountConflict("当前登录账号已切换，请重新载入资料。")
        change_password(get_identity(), context.principal, payload.current_password,
                        payload.new_password, getattr(request.state, "request_id", "profile-password"))
    except Exception as exc:
        _error(exc)
    _delete_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
