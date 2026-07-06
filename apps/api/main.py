import sys
from contextlib import asynccontextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from settings import settings
from routers import admin_content, common, courses, home, learning, practice, profile
from services import content, persistence


@asynccontextmanager
async def lifespan(app: FastAPI):
    persistence.init_engine(settings.sqlite_path)
    content.configure(settings.content_root)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Chronovita backend for course, practice and content production.",
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

app.include_router(common.router, prefix=API_PREFIX, tags=["common"])
app.include_router(admin_content.router, prefix=f"{API_PREFIX}/admin/content", tags=["admin-content"])
app.include_router(home.router, prefix=f"{API_PREFIX}/home", tags=["home"])
app.include_router(courses.router, prefix=f"{API_PREFIX}/courses", tags=["courses"])
app.include_router(learning.router, prefix=f"{API_PREFIX}/learning", tags=["learning"])
app.include_router(practice.router, prefix=f"{API_PREFIX}/practice", tags=["practice"])
app.include_router(profile.router, prefix=f"{API_PREFIX}/profile", tags=["profile"])


@app.get("/", tags=["common"])
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "modules": ["home", "courses", "learning", "practice", "profile", "admin-content"],
    }


@app.get("/healthz", tags=["common"])
async def healthz():
    return {"status": "ok"}
