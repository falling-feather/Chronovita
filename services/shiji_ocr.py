from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "content" / "shiji" / "ocr-pages-index.json"
DEFAULT_ROOT = REPO_ROOT / "content" / "shiji" / "ocr-pages"


def image_root() -> Path:
    return Path(os.environ.get("CHRONO_SHIJI_OCR_ROOT", str(DEFAULT_ROOT))).expanduser().resolve()


@lru_cache(maxsize=1)
def index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"pages": [], "page_count": 0}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def page_map() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in index().get("pages", []) if isinstance(item, dict) and item.get("id")}


def get_page(page_id: str) -> dict[str, Any] | None:
    return page_map().get(page_id)


def get_image_path(page_id: str) -> Path | None:
    record = get_page(page_id)
    if not record:
        return None
    root = image_root()
    relative = str(record.get("relative_image", ""))
    path = (root / relative).resolve()
    if not path.is_file() and relative.startswith(f"{root.name}/"):
        path = (root.parent / relative).resolve()
    allowed_roots = [root, root.parent] if root.name in {"baina-ia-mirror", "siku-quanshu-ia-zju"} else [root]
    if not any(str(path).startswith(str(candidate)) for candidate in allowed_roots) or not path.is_file():
        return None
    return path


def page_payload(page_id: str) -> dict[str, Any] | None:
    record = get_page(page_id)
    if not record:
        return None
    return {
        "id": page_id,
        "batch_id": "shiji-migrated-baina-v1",
        "status": record.get("ocr_status", "completed"),
        "book": {"id": "shiji", "title": "史记"},
        "version": {
            "id": record.get("version_id", "baina-ia-mirror"),
            "label": record.get("version_label", "百衲本史记"),
            "source_key": record.get("source_pdf", ""),
            "provider": "史海 OCR 运行时迁移",
        },
        "source": {
            "record_id": record.get("id", page_id),
            "catalog_url": "",
            "item_url": "",
            "file_label": record.get("source_file_label", ""),
            "pdf_path": record.get("source_pdf", ""),
            "pdf_page": record.get("pdf_page", 0),
            "pdf_page_count": 0,
            "checksum_algorithm": "sha256",
            "checksum": "",
            "license": "按史海原资料清单使用",
        },
        "sample_id": page_id,
        "generated_at": "",
        "normalization": "史海 OCR 运行时迁移",
        "summary": {"sample_pages": 1, "evaluated_pages": 1, "approved_pages": 0, "pending_pages": 1, "zero_reference_pages": 0, "missing_pages": 0, "provisional_cer": None, "approved_cer": None},
        "transcription": {
            "raw_text": "",
            "corrected_text": "",
            "status": record.get("review_status", "unreviewed"),
        },
        "ocr": {
            "metrics": {"character_count": record.get("character_count", 0), "average_confidence": record.get("average_confidence", 0)},
            "blocks": [],
        },
        "mapping": {"status": "unmapped", "canonical_unit_id": "", "volume_no": None, "volume_title": "", "chapter_title": "", "source_leaf_label": ""},
        "manual_content": {"page_id": page_id, "summary": "", "keywords": [], "editor": "", "updated_at": "", "revisions": []},
        "reader": {"display_label": f"《史记》· {record.get('source_file_label', '')} · PDF 第 {record.get('pdf_page', 0)} 页"},
    }


def clear_cache() -> None:
    index.cache_clear()
    page_map.cache_clear()
