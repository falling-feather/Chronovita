from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class StoryboardRequest(BaseModel):
    chapter_id: str
    keywords: list[str]


class RenderRequest(BaseModel):
    storyboard_id: str
    style: str = "默认"


@router.post("/storyboard")
async def create_storyboard(payload: StoryboardRequest):
    return {"storyboard_id": "stub", "shots": []}


@router.post("/render")
async def submit_render(payload: RenderRequest):
    return {"job_id": "stub", "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return {"job_id": job_id, "status": "stub", "video_url": None}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    return {"asset_id": asset_id, "url": None}
