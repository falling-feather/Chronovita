from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def index():
    return {"module": "个人中心", "items": [], "note": "v0.1.0 占位接口"}
