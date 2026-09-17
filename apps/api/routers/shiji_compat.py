from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services import shiji_compat, shiji_ocr, shiji_reader


router = APIRouter()


@router.get("/books/shiji/application-manifest")
@router.get("/books/shiji/manifest")
async def application_manifest(view: str = Query(default="full")) -> dict:
    return shiji_compat.reader_manifest()


@router.get("/books/shiji/volumes/{volume_id}")
async def volume_navigation(volume_id: str) -> dict:
    items = shiji_compat.volume_entries(volume_id)
    if not items:
        raise HTTPException(404, detail="史记卷不存在")
    return {
        "schema_version": "shiji-application-reader/v2",
        "manifest_id": "shiji-application-reader",
        "book_id": "shiji",
        "book_title": "史记",
        "total_passages": len(items),
        "entries": items,
        "volumes": [{"id": volume_id, "volume_no": items[0]["volume_no"], "title": items[0]["volume_title"], "chapter_type": items[0]["chapter_type"], "status": "application_ready", "passages": [{"id": item["passage_id"], "title": item["title"], "sort_order": item["sequence"]} for item in items]}],
    }


@router.get("/books/shiji/volumes/{volume_id}/chapters/{chapter_id}")
async def volume_chapter(volume_id: str, chapter_id: str) -> dict:
    if not any(item["volume_id"] == volume_id and item["passage_id"] == chapter_id for item in shiji_compat.entries()):
        raise HTTPException(404, detail="史记篇章不存在")
    try:
        return shiji_compat.passage_payload(chapter_id)
    except (KeyError, shiji_reader.ShijiReaderError) as exc:
        raise HTTPException(404, detail="史记篇章资料不可用") from exc


@router.get("/passages/{passage_id}")
@router.get("/passages/{passage_id}/runtime")
async def passage(passage_id: str, mode: str = "segment", version_id: str | None = None) -> dict:
    try:
        return shiji_compat.passage_payload(passage_id)
    except (KeyError, shiji_reader.ShijiReaderError) as exc:
        raise HTTPException(404, detail="史记篇章不存在") from exc


@router.get("/passages/{passage_id}/sequence")
async def passage_sequence(passage_id: str, version_id: str | None = None) -> dict:
    try:
        return shiji_compat.passage_payload(passage_id)["reader_sequence"]
    except (KeyError, shiji_reader.ShijiReaderError) as exc:
        raise HTTPException(404, detail="史记篇章不存在") from exc


@router.get("/pages/count")
async def ocr_page_count(book_id: str | None = None, version_id: str | None = None) -> dict[str, int]:
    return {"count": int(shiji_ocr.index().get("page_count", 0))}


@router.get("/pages/{page_id}")
async def ocr_page(page_id: str) -> dict:
    payload = shiji_ocr.page_payload(page_id)
    if payload is None:
        raise HTTPException(404, detail="史记书影页不存在")
    return payload


@router.get("/pages/{page_id}/neighbors")
async def ocr_page_neighbors(page_id: str) -> dict:
    pages = list(shiji_ocr.page_map().values())
    ids = [str(item["id"]) for item in pages]
    if page_id not in ids:
        raise HTTPException(404, detail="史记书影页不存在")
    index = ids.index(page_id)
    return {"page_id": page_id, "position": index + 1, "total": len(ids), "previous_page_id": ids[index - 1] if index else None, "next_page_id": ids[index + 1] if index + 1 < len(ids) else None}


@router.get("/pages/{page_id}/parallels")
async def ocr_page_parallels(page_id: str) -> list[dict]:
    payload = shiji_ocr.page_payload(page_id)
    return [] if payload is None else []


@router.get("/pages/{page_id}/image")
async def ocr_page_image(page_id: str) -> FileResponse:
    path = shiji_ocr.get_image_path(page_id)
    if path is None:
        raise HTTPException(404, detail="史记书影包尚未安装；请先安装独立书影资料包")
    return FileResponse(path, media_type="image/webp")
