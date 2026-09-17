from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services import shiji_reader


router = APIRouter()


@router.get("/manifest")
async def reader_manifest() -> dict:
    try:
        return shiji_reader.navigation()
    except shiji_reader.ShijiReaderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/volumes/{volume_no}")
async def reader_volume(volume_no: int) -> dict:
    if volume_no < 1 or volume_no > 130:
        raise HTTPException(status_code=422, detail="卷号必须在 1—130 之间")
    try:
        return shiji_reader.volume(volume_no)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未找到该卷") from exc
    except shiji_reader.ShijiReaderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/chapters/{chapter_id}")
async def reader_chapter(
    chapter_id: str,
    sentence_limit: int = Query(default=5000, ge=1, le=20_000),
) -> dict:
    try:
        result = shiji_reader.chapter(chapter_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未找到该篇章") from exc
    except shiji_reader.ShijiReaderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    payload = result.get("payload")
    chapter = payload.get("chapter") if isinstance(payload, dict) else None
    if isinstance(chapter, dict) and isinstance(chapter.get("sentences"), list):
        chapter["sentences"] = chapter["sentences"][:sentence_limit]
    return result
