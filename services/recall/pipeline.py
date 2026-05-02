from __future__ import annotations

import uuid
from datetime import datetime

from .models import JobStage, JobStatus, RenderJob


_JOBS: dict[str, RenderJob] = {}


_STAGE_FLOW: list[JobStage] = [
    JobStage.QUEUED,
    JobStage.PROMPT_CHAIN,
    JobStage.STORYBOARD,
    JobStage.CONTROLNET,
    JobStage.DIFFUSION,
    JobStage.ANIMATION,
    JobStage.TTS,
    JobStage.COMPOSE,
    JobStage.DONE,
]


def submit_render(storyboard_id: str) -> RenderJob:
    job = RenderJob(
        job_id=f"job_{uuid.uuid4().hex[:10]}",
        storyboard_id=storyboard_id,
        status=JobStatus.PENDING,
        stage=JobStage.QUEUED,
        progress=0.0,
    )
    _JOBS[job.job_id] = job
    return job


def _advance(job: RenderJob) -> RenderJob:
    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        return job
    try:
        idx = _STAGE_FLOW.index(job.stage)
    except ValueError:
        idx = 0
    next_idx = min(idx + 1, len(_STAGE_FLOW) - 1)
    job.stage = _STAGE_FLOW[next_idx]
    job.progress = round(next_idx / (len(_STAGE_FLOW) - 1), 2)
    job.status = JobStatus.RUNNING
    if job.stage == JobStage.DONE:
        job.status = JobStatus.SUCCEEDED
        job.video_url = f"/static/recall/{job.job_id}.mp4"
    job.updated_at = datetime.utcnow()
    return job


def get_job(job_id: str) -> RenderJob | None:
    job = _JOBS.get(job_id)
    if job is None:
        return None
    return _advance(job)


def list_jobs() -> list[RenderJob]:
    return list(_JOBS.values())
