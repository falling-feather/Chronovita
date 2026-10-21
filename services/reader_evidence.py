"""Deterministic, source-bound quotes from the existing historical reader."""
from __future__ import annotations

import re

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
    anchors = chapter.get("source_anchors", [])
    source_pages = [anchor["page_id"] for anchor in anchors
                    if anchor.get("source_span_id") in spans and anchor.get("page_id")]
    # The migrated sentence layer uses :span:<edition>:pNNNN, while its
    # verified anchor layer uses <volume>-primary-pNNNN. Match only a unique
    # page of the same edition and current chapter, never a guessed global ID.
    for span in spans:
        match = re.search(r":span:([^:]+):p(\d+)$", span)
        if not match:
            continue
        edition, ordinal = match.groups()
        matches = [anchor for anchor in anchors if anchor.get("version_id") == edition
                   and re.search(r"(?:^|[-:])p0*" + str(int(ordinal)) + r"$", anchor.get("source_span_id", ""))]
        if len(matches) == 1 and matches[0].get("page_id"):
            source_pages.append(matches[0]["page_id"])
    pages = tuple(dict.fromkeys(source_pages))
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
