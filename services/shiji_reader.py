"""《史记》只读阅读资料访问层。

资料以压缩运行时包保存，按请求读取目录或单篇章节，避免把 130 卷正文
全部展开到工作树或启动时载入内存。该层不提供 OCR 编辑、生产队列或写接口。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any
from zipfile import BadZipFile, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = REPO_ROOT / "content" / "shiji" / "shiji-application-runtime.zip"


class ShijiReaderError(RuntimeError):
    """Raised when the bundled 《史记》 reader package is unavailable or invalid."""


_lock = RLock()
_archive: ZipFile | None = None


def _open_archive() -> ZipFile:
    global _archive
    with _lock:
        if _archive is not None:
            return _archive
        if not ARCHIVE_PATH.is_file():
            raise ShijiReaderError("《史记》阅读资料包尚未安装")
        try:
            _archive = ZipFile(ARCHIVE_PATH, "r")
            _archive.testzip()
        except (OSError, BadZipFile) as exc:
            _archive = None
            raise ShijiReaderError("《史记》阅读资料包损坏") from exc
        return _archive


def _read_json(path: str) -> dict[str, Any]:
    try:
        raw = _open_archive().read(path)
        value = json.loads(raw.decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShijiReaderError(f"《史记》阅读资料缺少或无法解析：{path}") from exc
    if not isinstance(value, dict):
        raise ShijiReaderError(f"《史记》阅读资料格式错误：{path}")
    return value


@lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    return _read_json("manifest.json")


def _volumes() -> list[dict[str, Any]]:
    volumes = manifest().get("volumes")
    if not isinstance(volumes, list):
        raise ShijiReaderError("《史记》目录缺少卷列表")
    return [item for item in volumes if isinstance(item, dict)]


def navigation() -> dict[str, Any]:
    source = manifest()
    volumes = _volumes()
    return {
        "book_id": "shiji",
        "title": "史记",
        "application_status": source.get("application_status", "reader_available"),
        "publication": source.get("publication", {}),
        "manifest_sha256": source.get("manifest_sha256", ""),
        "total_volumes": len(volumes),
        "volumes": [
            {
                "volume_no": item.get("juan_no"),
                "volume_id": item.get("volume_id"),
                "title": item.get("title_simplified") or item.get("title_traditional"),
                "title_traditional": item.get("title_traditional"),
                "category": item.get("category_title_simplified"),
                "status": item.get("status"),
                "preview": item.get("preview_simplified") or item.get("preview_traditional"),
                "chapters": [
                    {
                        "id": chapter.get("chapter_id"),
                        "title": chapter.get("title_simplified") or chapter.get("title_traditional"),
                        "title_traditional": chapter.get("title_traditional"),
                        "preview": chapter.get("preview_simplified") or chapter.get("preview_traditional"),
                        "runtime_path": chapter.get("runtime_path"),
                    }
                    for chapter in item.get("chapters", [])
                    if isinstance(chapter, dict)
                ],
            }
            for item in volumes
        ],
    }


def volume(volume_no: int) -> dict[str, Any]:
    for item in navigation()["volumes"]:
        if item.get("volume_no") == volume_no:
            return item
    raise KeyError(volume_no)


@lru_cache(maxsize=512)
def chapter(chapter_id: str) -> dict[str, Any]:
    for item in _volumes():
        for entry in item.get("chapters", []):
            if isinstance(entry, dict) and entry.get("chapter_id") == chapter_id:
                path = entry.get("runtime_path")
                if not isinstance(path, str) or not path.startswith("chapters/"):
                    raise ShijiReaderError(f"篇章资料路径无效：{chapter_id}")
                payload = _read_json(path)
                return {
                    "book_id": "shiji",
                    "volume": {
                        "volume_no": item.get("juan_no"),
                        "volume_id": item.get("volume_id"),
                        "title": item.get("title_simplified") or item.get("title_traditional"),
                        "category": item.get("category_title_simplified"),
                    },
                    "manifest_sha256": manifest().get("manifest_sha256", ""),
                    "chapter_meta": entry,
                    "payload": payload,
                }
    raise KeyError(chapter_id)


def close() -> None:
    global _archive
    with _lock:
        if _archive is not None:
            _archive.close()
            _archive = None
        manifest.cache_clear()
        chapter.cache_clear()
