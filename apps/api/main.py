import sys
from contextlib import asynccontextmanager
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (_API_ROOT, _REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from settings import settings
from routers import (
    admin_content,
    common,
    courses,
    game,
    home,
    learning,
    practice,
    profile,
)
from services import content, persistence
from services.content import workflow as content_workflow
from services.game_runtime.service import configure_game_runtime, shutdown_game_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    persistence.init_engine(settings.sqlite_path)
    try:
        content.configure(settings.content_root)
        content_workflow.recover_pending_release_transactions()
        configure_game_runtime(
            content_root=content.content_root(),
            catalog_path=settings.game_catalog_path,
        )
        yield
    finally:
        shutdown_game_runtime()
        persistence.close_engine()


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
app.include_router(game.router, prefix=f"{API_PREFIX}/practice/game", tags=["game"])
app.include_router(profile.router, prefix=f"{API_PREFIX}/profile", tags=["profile"])


@app.get("/", tags=["common"])
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "modules": [
            "home",
            "courses",
            "learning",
            "practice",
            "game-runtime",
            "profile",
            "admin-content",
        ],
    }


@app.get("/healthz", tags=["common"])
async def healthz():
    return {"status": "ok"}
