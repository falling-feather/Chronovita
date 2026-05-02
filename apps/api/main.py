import sys
from contextlib import asynccontextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from settings import settings
from routers import recall, sandbox, agent, canvas, common
from services import persistence
from services.canvas import store as canvas_store
from services.sandbox import engine as sandbox_engine
from services.agent import dialogue as agent_dialogue


@asynccontextmanager
async def lifespan(app: FastAPI):
    persistence.init_engine(settings.sqlite_path)
    canvas_store.hydrate_from_db()
    sandbox_engine.hydrate_from_db()
    agent_dialogue.hydrate_from_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="史脉 Chronovita 后端服务 · 看 练 问 创 四模块统一入口",
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
app.include_router(recall.router, prefix=f"{API_PREFIX}/recall", tags=["看 · 沉浸叙事"])
app.include_router(sandbox.router, prefix=f"{API_PREFIX}/sandbox", tags=["练 · 沙盘推演"])
app.include_router(agent.router, prefix=f"{API_PREFIX}/agent", tags=["问 · 双模智者"])
app.include_router(canvas.router, prefix=f"{API_PREFIX}/canvas", tags=["创 · 知识谱系"])


@app.get("/", tags=["通用"])
async def root():
    return {"name": settings.app_name, "version": settings.app_version, "modules": ["recall", "sandbox", "agent", "canvas"]}


@app.get("/healthz", tags=["通用"])
async def healthz():
    return {"status": "ok"}
