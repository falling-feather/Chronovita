"""Deterministic, source-bound quotes from the existing historical reader."""
from __future__ import annotations

from services import shiji_reader
from services.contracts.learning_v1 import canonical_checksum
from services.contracts.reader_v1 import ReaderQuoteRequestV1, ReaderQuoteV1


def make_quote(request: ReaderQuoteRequestV1) -> ReaderQuoteV1:
    record = shiji_reader.chapter(request.passage_id)
    payload = record["payload"]
    chapter = payload["chapter"]
    requested = set(request.sentence_ids)
    selected = [sentence for sentence in chapter.get("sentences", []) if sentence.get("sentence_id") in requested]
    if len(selected) != len(requested):
        raise KeyError("The requested sentence is not in this chapter")
    text = "\n".join(str(sentence.get(request.text_variant) or sentence.get("simplified") or "") for sentence in selected).strip()
    if not text:
        raise ValueError("The selected sentences have no transcribed text")
    spans = {span for sentence in selected for span in sentence.get("source_span_ids", [])}
    pages = tuple(dict.fromkeys(anchor["page_id"] for anchor in chapter.get("source_anchors", [])
                                if anchor.get("source_span_id") in spans and anchor.get("page_id")))
    data = {
        "schema_version": "reader-quote/v1", "book_id": "shiji", "book_title": "史记",
        "volume_no": record["volume"]["volume_no"], "volume_title": record["volume"]["title"],
        "passage_id": request.passage_id,
        "passage_title": record["chapter_meta"].get("title_simplified") or record["chapter_meta"].get("title_traditional"),
        "manifest_checksum": record["manifest_sha256"], "chapter_checksum": payload["chapter_sha256"],
        "sentence_ids": [sentence["sentence_id"] for sentence in selected],
        "text_variant": request.text_variant, "quote_text": text, "page_ids": list(pages),
        "review_notice": "OCR 转写与自动整理资料，保留人工待核状态；可对照真实书影。",
    }
    data["quote_id"] = "quote-" + canonical_checksum(data)[:24]
    data["checksum"] = canonical_checksum(data)
    return ReaderQuoteV1.model_validate(data)
