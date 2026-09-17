"""Compatibility payloads for the migrated 史海 reader UI.

The embedded Vue reader still speaks the original reader contract. This adapter
maps the Chronovita 130-volume runtime archive into that contract while leaving
the course APIs and learning data untouched.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from services import shiji_reader


VERSION_ID = "baina-ia-mirror"
VERSION_NAME = "百衲本二十四史影印本（史记迁移包）"


def _manifest_source() -> dict[str, Any]:
    return shiji_reader.manifest()


@lru_cache(maxsize=1)
def entries() -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    sequence = 0
    volumes = _manifest_source().get("volumes", [])
    for volume in volumes:
        if not isinstance(volume, dict):
            continue
        chapters = volume.get("chapters", [])
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            sequence += 1
            result.append({
                "sequence": sequence,
                "passage_id": str(chapter.get("chapter_id", "")),
                "volume_id": str(volume.get("volume_id", "")),
                "volume_no": int(volume.get("juan_no", sequence)),
                "volume_title": str(volume.get("title_simplified") or volume.get("title_traditional") or ""),
                "work_type": str(volume.get("work_type", "")),
                "category_id": str(volume.get("category_id", "")),
                "category_title_simplified": str(volume.get("category_title_simplified", "")),
                "category_title_traditional": str(volume.get("category_title_traditional", "")),
                "chapter_id": str(chapter.get("chapter_id", "")),
                "chapter_title": str(chapter.get("title_simplified") or chapter.get("title_traditional") or ""),
                "chapter_type": str(volume.get("work_type") or volume.get("category_title_simplified") or "正文"),
                "title": str(chapter.get("title_simplified") or chapter.get("title_traditional") or ""),
                "preview_simplified": chapter.get("preview_simplified", ""),
                "preview_traditional": chapter.get("preview_traditional", ""),
                "commentary": chapter.get("commentary", {}),
                "mixed": chapter.get("mixed", {}),
                "runtime_path": chapter.get("runtime_path", ""),
            })
    for index, item in enumerate(result):
        item["previous_id"] = result[index - 1]["passage_id"] if index else None
        item["next_id"] = result[index + 1]["passage_id"] if index + 1 < len(result) else None
        item["available_versions"] = [{
            "id": VERSION_ID,
            "name": VERSION_NAME,
            "current": True,
            "page_ids": [],
            "ocr_batch_ids": [],
            "source_ref_ids": [],
        }]
    return tuple(result)


def clear_cache() -> None:
    entries.cache_clear()


def reader_manifest() -> dict[str, Any]:
    source = _manifest_source()
    all_entries = entries()
    volumes: list[dict[str, Any]] = []
    for volume in source.get("volumes", []):
        if not isinstance(volume, dict):
            continue
        volume_id = str(volume.get("volume_id", ""))
        volume_entries_list = [item for item in all_entries if item["volume_id"] == volume_id]
        volumes.append({
            "id": volume_id,
            "volume_id": volume_id,
            "volume_no": volume.get("juan_no"),
            "title": volume.get("title_simplified") or volume.get("title_traditional"),
            "title_simplified": volume.get("title_simplified"),
            "title_traditional": volume.get("title_traditional"),
            "chapter_type": volume.get("work_type") or volume.get("category_title_simplified") or "正文",
            "category_id": volume.get("category_id"),
            "category_title_simplified": volume.get("category_title_simplified"),
            "category_title_traditional": volume.get("category_title_traditional"),
            "status": "application_ready" if volume_entries_list else "not_applied",
            "chapter_count": len(volume.get("chapters", [])),
            "applied_chapter_count": len(volume_entries_list),
            "chapters": volume_entries_list,
        })
    return {
        "schema_version": "shiji-application-reader/v2",
        "manifest_id": "shiji-application-reader",
        "book_id": "shiji",
        "book_title": "史记",
        "total_passages": len(all_entries),
        "entries": list(all_entries),
        "total_volumes": 130,
        "volumes": volumes,
        "publication": {
            "ai_status": source.get("publication", {}).get("ai_status", "AI初筛完成"),
            "human_status": source.get("publication", {}).get("human_status", "人类待检查"),
            "formal_reader_mode": "application_ready",
        },
    }


def volume_entries(volume_id: str) -> list[dict[str, Any]]:
    return [item for item in entries() if item["volume_id"] == volume_id]


def _entity_type(candidate_id: str) -> str:
    return "person" if "person" in candidate_id else "concept"


def passage_payload(passage_id: str) -> dict[str, Any]:
    entry = next((item for item in entries() if item["passage_id"] == passage_id), None)
    if entry is None:
        raise KeyError(passage_id)
    source = shiji_reader.chapter(passage_id)["payload"]
    chapter = source.get("chapter", {}) if isinstance(source, dict) else {}
    sentences = chapter.get("sentences", []) if isinstance(chapter, dict) else []
    text_parts: list[str] = []
    normalized_sentences: list[dict[str, Any]] = []
    highlights: list[dict[str, Any]] = []
    entities: dict[str, dict[str, Any]] = {}
    candidates = source.get("entity_candidates", []) if isinstance(source, dict) else []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("candidate_id", ""))
        aliases = [str(item) for item in candidate.get("aliases", []) if isinstance(item, str)]
        display_name = aliases[0] if aliases else candidate_id
        entities[candidate_id] = {
            "id": candidate_id,
            "type": _entity_type(candidate_id),
            "name": display_name,
            "display_name": display_name,
            "aliases": aliases,
            "summary": str(candidate.get("association_note", "史记篇章中的待审校实体候选。")),
            "source_ref_ids": [str(item) for item in candidate.get("source_page_ids", [])],
            "confidence": float(candidate.get("confidence", 0.0) or 0.0),
            "status": "uncertain",
            "facts": [],
        }
    offset = 0
    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        simplified = str(sentence.get("simplified") or "")
        traditional = str(sentence.get("traditional") or simplified)
        translation = str(sentence.get("translation") or "")
        normalized_sentences.append({
            "sentence_id": sentence.get("sentence_id", ""),
            "content_layer": sentence.get("content_layer", "body"),
            "simplified": simplified,
            "traditional": traditional,
            "translation": translation,
            "raw_ocr": sentence.get("raw_ocr"),
            "raw_ocr_available": bool(sentence.get("raw_ocr_available")),
            "utf16_start": offset,
            "utf16_end": offset + len(simplified),
            "source_span_ids": sentence.get("source_span_ids", []),
            "entity_mentions": sentence.get("entity_mentions", []),
        })
        for mention in sentence.get("entity_mentions", []) if isinstance(sentence.get("entity_mentions"), list) else []:
            if not isinstance(mention, dict):
                continue
            entity_id = str(mention.get("entity_id", ""))
            if not entity_id:
                continue
            highlights.append({
                "id": str(mention.get("mention_id", f"{entity_id}-{offset}")),
                "type": entities.get(entity_id, {}).get("type", "concept"),
                "label": entities.get(entity_id, {}).get("display_name", entity_id),
                "start": offset + int(mention.get("start", 0) or 0),
                "end": offset + int(mention.get("end", 0) or 0),
                "text": str(mention.get("surface", "")),
                "target_id": entity_id,
                "color": "jade",
                "status": "uncertain",
            })
        text_parts.append(simplified)
        offset += len(simplified) + 1
    index = entry["sequence"] - 1
    previous_entry = entries()[index - 1] if index else None
    next_entry = entries()[index + 1] if index + 1 < len(entries()) else None
    page_ids = []
    for anchor in chapter.get("source_anchors", []) if isinstance(chapter, dict) else []:
        if isinstance(anchor, dict) and anchor.get("page_id"):
            page_ids.append(str(anchor["page_id"]))
    page_ids = list(dict.fromkeys(page_ids))
    sequence = {
        "manifest_id": "shiji-application-reader",
        "book_id": "shiji",
        "book_title": "史记",
        "position": entry["sequence"],
        "total": len(entries()),
        "volume": {"id": entry["volume_id"], "number": entry["volume_no"], "title": entry["volume_title"]},
        "chapter": {"id": entry["chapter_id"], "title": entry["title"], "type": entry["chapter_type"]},
        "current": {"passage_id": passage_id, "sequence": entry["sequence"], "title": entry["title"], "available_version_ids": [VERSION_ID]},
        "previous": ({"passage_id": previous_entry["passage_id"], "sequence": previous_entry["sequence"], "title": previous_entry["title"], "available_version_ids": [VERSION_ID]} if previous_entry else None),
        "next": ({"passage_id": next_entry["passage_id"], "sequence": next_entry["sequence"], "title": next_entry["title"], "available_version_ids": [VERSION_ID]} if next_entry else None),
        "selected_version_id": VERSION_ID,
        "available_version_ids": [VERSION_ID],
    }
    segments = []
    cursor = 0
    for item in normalized_sentences:
        end = int(item["utf16_end"])
        segments.append({"id": item["sentence_id"], "label": f"第 {len(segments) + 1} 段", "start": cursor, "end": end})
        cursor = end + 1
    return {
        "passage": {
            "id": passage_id, "book_id": "shiji", "book_title": "史记", "volume_id": entry["volume_id"],
            "title": entry["title"], "sort_order": entry["sequence"], "previous_id": entry["previous_id"], "next_id": entry["next_id"],
        },
        "current_version": {"id": VERSION_ID, "name": VERSION_NAME, "current": True, "page_ids": page_ids},
        "available_versions": [{"id": VERSION_ID, "name": VERSION_NAME, "current": True, "page_ids": page_ids}],
        "reading": {"mode": "segment", "page": {"page_id": page_ids[0] if page_ids else "", "page_no": 1, "total_pages": len(page_ids), "passage_ids": [passage_id]}, "segments": segments},
        "reader_sequence": sequence,
        "reader_config": {"default_mode": "segment", "available_modes": [{"id": "segment", "name": "分段", "description": "按句读或逻辑段阅读"}, {"id": "page", "name": "分页", "description": "按书影页阅读"}], "context_tabs": ["document", "encyclopedia"]},
        "text": "\n".join(text_parts),
        "highlights": highlights,
        "variants": [], "annotations": [], "mentions": {"persons": list(entities.values()), "places": [], "events": [], "concepts": []},
        "publication": {"ai_status": "AI初筛完成", "human_status": "人类待检查", "stages": [], "updated_at": ""},
        "sources": [{"id": "shiji-runtime", "title": "史海《史记》运行时资料包", "kind": "ocr_runtime", "url_or_path": "content/shiji/shiji-application-runtime.zip", "citation_note": "迁移资料，保留原始页引用与 OCR 层。"}],
        "entities": list(entities.values()),
        "uncertain_items": [],
        "chapter_runtime": {**chapter, "sentences": normalized_sentences, "historical_map": None},
    }
