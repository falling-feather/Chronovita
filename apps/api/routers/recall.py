from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.recall import (
    Storyboard,
    StoryboardRequest,
    RenderJob,
    generate_storyboard,
    submit_render,
    get_job,
    list_jobs,
)

router = APIRouter()

_STORYBOARDS: dict[str, Storyboard] = {}


@router.post("/storyboard", response_model=Storyboard, summary="生成分镜（Prompt 链 + ControlNet 编排）")
async def create_storyboard(payload: StoryboardRequest) -> Storyboard:
    sb = generate_storyboard(payload)
    _STORYBOARDS[sb.storyboard_id] = sb
    return sb


@router.get("/storyboard/{storyboard_id}", response_model=Storyboard, summary="获取分镜详情")
async def fetch_storyboard(storyboard_id: str) -> Storyboard:
    sb = _STORYBOARDS.get(storyboard_id)
    if sb is None:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return sb


@router.post("/render", response_model=RenderJob, summary="提交视频生成任务")
async def submit_render_job(storyboard_id: str) -> RenderJob:
    if storyboard_id not in _STORYBOARDS:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return submit_render(storyboard_id)


@router.get("/jobs", response_model=list[RenderJob], summary="任务列表")
async def fetch_jobs() -> list[RenderJob]:
    return list_jobs()


@router.get("/jobs/{job_id}", response_model=RenderJob, summary="任务详情（自动推进阶段）")
async def fetch_job(job_id: str) -> RenderJob:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job
