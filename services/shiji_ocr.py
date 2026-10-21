"""Read the migrated Shiji OCR corpus; facsimile images are an optional install."""
from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any
from zipfile import BadZipFile, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = REPO_ROOT / "content" / "shiji"
INDEX_PATH = CONTENT_ROOT / "ocr-pages-index.json"
DEFAULT_ROOT = REPO_ROOT / "data" / "shiji" / "ocr-pages"
LEGACY_ROOT = CONTENT_ROOT / "ocr-pages"
_archive: ZipFile | None = None
_lock = RLock()


class ShijiOcrError(RuntimeError):
    pass


def image_root() -> Path:
    configured = os.environ.get("CHRONO_SHIJI_OCR_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    # Existing V1.2 installations stay readable without climbing above their root.
    return LEGACY_ROOT if not DEFAULT_ROOT.is_dir() and LEGACY_ROOT.is_dir() else DEFAULT_ROOT


@lru_cache(maxsize=1)
def index() -> dict[str, Any]:
    try:
        value = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShijiOcrError("《史记》OCR 索引缺少或损坏") from exc
    if not isinstance(value, dict) or value.get("book_id") != "shiji" or not isinstance(value.get("pages"), list):
        raise ShijiOcrError("《史记》OCR 索引格式错误")
    if value.get("page_count") != len(value["pages"]):
        raise ShijiOcrError("《史记》OCR 索引页数不一致")
    return value


def _natural_key(text: str) -> tuple:
    return tuple((0, int(part)) if part.isdigit() else (1, part)
                 for part in re.split(r"(\d+)", text.casefold()))


@lru_cache(maxsize=1)
def page_map() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in index()["pages"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in records:
            raise ShijiOcrError("《史记》OCR 页身份缺失或重复")
        records[item["id"]] = item
    return records


@lru_cache(maxsize=1)
def ordered_pages() -> tuple[dict[str, Any], ...]:
    return tuple(sorted(page_map().values(), key=lambda page: (
        str(page["version_id"]), _natural_key(str(page["source_file_label"])), int(page["pdf_page"]), page["id"])))


def filtered_pages(*, book_id: str | None = None, version_id: str | None = None) -> list[dict[str, Any]]:
    if book_id not in {None, "shiji"}:
        return []
    return [item for item in ordered_pages() if version_id is None or item["version_id"] == version_id]


def get_page(page_id: str) -> dict[str, Any] | None:
    return page_map().get(page_id)


def _relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ShijiOcrError("《史记》OCR 页路径无效")
    path = Path(value)
    if path.is_absolute() or path.drive or ".." in path.parts:
        raise ShijiOcrError("《史记》OCR 页路径越界")
    return path


def get_image_path(page_id: str) -> Path | None:
    record = get_page(page_id)
    if record is None:
        return None
    root = image_root().resolve()
    relative = _relative_path(record.get("relative_image"))
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ShijiOcrError("《史记》书影路径越界")
    # V1.2 accidentally stripped the version directory. This is its only legacy layout.
    if not path.is_file() and root == LEGACY_ROOT.resolve() and relative.parts[0] == record["version_id"]:
        path = root.joinpath(*relative.parts[1:]).resolve()
        if not path.is_relative_to(root):
            raise ShijiOcrError("旧书影路径越界")
    return path if path.is_file() else None


def _open_records() -> ZipFile:
    global _archive
    with _lock:
        if _archive is not None:
            return _archive
        relative = _relative_path(index().get("records_archive"))
        if len(relative.parts) != 1:
            raise ShijiOcrError("OCR 资料包名称无效")
        path = CONTENT_ROOT / relative
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != index().get("records_sha256"):
                raise ShijiOcrError("《史记》OCR 资料包校验失败")
            _archive = ZipFile(path, "r")
        except (OSError, BadZipFile) as exc:
            raise ShijiOcrError("《史记》OCR 资料包尚未安装或损坏") from exc
        return _archive


@lru_cache(maxsize=24)
def page_payload(page_id: str) -> dict[str, Any] | None:
    record = get_page(page_id)
    if record is None:
        return None
    relative = _relative_path(record.get("relative_record"))
    try:
        data = _open_records().read(relative.as_posix())
        if hashlib.sha256(data).hexdigest() != record.get("record_sha256"):
            raise ShijiOcrError("《史记》OCR 单页校验失败")
        payload = json.loads(data.decode("utf-8"))
        if (not isinstance(payload, dict) or payload.get("id") != page_id
                or payload.get("book", {}).get("id") != "shiji"
                or payload.get("version", {}).get("id") != record["version_id"]):
            raise ShijiOcrError("《史记》OCR 单页身份错误")
        for field in ("transcription", "ocr", "source", "mapping", "manual_content"):
            if not isinstance(payload.get(field), dict):
                raise ShijiOcrError("《史记》OCR 单页缺少阅读字段")
        return payload
    except (KeyError, BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise ShijiOcrError("《史记》OCR 页记录损坏") from exc


@lru_cache(maxsize=1)
def _neighbors() -> dict[str, dict[str, Any]]:
    groups: dict[str, list[str]] = {}
    for page in ordered_pages():
        groups.setdefault(page["version_id"], []).append(page["id"])
    return {page_id: {
        "page_id": page_id, "position": position + 1, "total": len(ids),
        "previous_page_id": ids[position - 1] if position else None,
        "next_page_id": ids[position + 1] if position + 1 < len(ids) else None,
    } for ids in groups.values() for position, page_id in enumerate(ids)}


def page_neighbors(page_id: str) -> dict[str, Any] | None:
    return _neighbors().get(page_id)


def page_parallels(page_id: str) -> list[dict[str, Any]] | None:
    page = get_page(page_id)
    if page is None:
        return None
    unit = page.get("canonical_unit_id")
    if not unit:
        return []
    return [item for item in ordered_pages() if item.get("canonical_unit_id") == unit
            and item["version_id"] != page["version_id"]]


def clear_cache() -> None:
    global _archive
    with _lock:
        if _archive is not None:
            _archive.close()
            _archive = None
    index.cache_clear()
    page_map.cache_clear()
    ordered_pages.cache_clear()
    _neighbors.cache_clear()
    page_payload.cache_clear()
