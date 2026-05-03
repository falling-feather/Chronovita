import sys
from contextlib import asynccontextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from settings import settings
from routers import common, home, courses, learning, practice, profile
from services import persistence


@asynccontextmanager
async def lifespan(app: FastAPI):
    persistence.init_engine(settings.sqlite_path)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="历史未来课堂 Chronovita 后端 · 五模块平台壳",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(common.router, prefix=API_PREFIX, tags=["通用"])
app.include_router(home.router, prefix=f"{API_PREFIX}/home", tags=["首页"])
app.include_router(courses.router, prefix=f"{API_PREFIX}/courses", tags=["课程中心"])
app.include_router(learning.router, prefix=f"{API_PREFIX}/learning", tags=["我的学习"])
app.include_router(practice.router, prefix=f"{API_PREFIX}/practice", tags=["实践课堂"])
app.include_router(profile.router, prefix=f"{API_PREFIX}/profile", tags=["个人中心"])


@app.get("/", tags=["通用"])
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "modules": ["home", "courses", "learning", "practice", "profile"],
    }


@app.get("/healthz", tags=["通用"])
async def healthz():
    return {"status": "ok"}
