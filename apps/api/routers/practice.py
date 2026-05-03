from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def index():
    return {"module": "实践课堂", "items": [], "note": "v0.1.0 占位接口"}
