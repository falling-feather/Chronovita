from fastapi import APIRouter

from settings import settings

router = APIRouter()


@router.get("/version")
async def version():
    return {"name": settings.app_name, "version": settings.app_version}


@router.get("/modules")
async def modules():
    return {
        "items": [
            {"key": "home", "label": "首页", "path": "/"},
            {"key": "courses", "label": "课程中心", "path": "/courses"},
            {"key": "learning", "label": "我的学习", "path": "/learning"},
            {"key": "practice", "label": "实践课堂", "path": "/practice"},
            {"key": "profile", "label": "个人中心", "path": "/profile"},
        ]
    }
