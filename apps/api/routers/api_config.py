from fastapi import APIRouter, Depends, HTTPException

from auth_dependencies import AuthContext, require_permission
from services.operations.api_config import (
    ApiConfigUpdate,
    ApiConfigView,
    apply_api_config,
)

router = APIRouter()


@router.get("/api-config", response_model=ApiConfigView)
async def get_api_config(
    _context: AuthContext = Depends(require_permission("auth.manage_users")),
) -> ApiConfigView:
    from services.operations.api_config import _view

    return _view()


@router.put("/api-config", response_model=ApiConfigView)
async def update_api_config(
    payload: ApiConfigUpdate,
    _context: AuthContext = Depends(require_permission("auth.manage_users")),
) -> ApiConfigView:
    try:
        return apply_api_config(payload)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
