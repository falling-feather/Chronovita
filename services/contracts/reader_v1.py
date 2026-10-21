from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.contracts.learning_v1 import canonical_checksum
from services.contracts.v1 import Checksum


class ReaderQuoteRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    passage_id: str = Field(min_length=1, max_length=200)
    sentence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    text_variant: Literal["traditional", "simplified"] = "traditional"

    @model_validator(mode="after")
    def distinct_sentences(self):
        if len(self.sentence_ids) != len(set(self.sentence_ids)):
            raise ValueError("sentence_ids must be unique")
        return self


class ReaderQuoteV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["reader-quote/v1"] = "reader-quote/v1"
    quote_id: str
    book_id: Literal["shiji"] = "shiji"
    book_title: str
    volume_no: int = Field(ge=1, le=130)
    volume_title: str
    passage_id: str
    passage_title: str
    manifest_checksum: Checksum
    chapter_checksum: Checksum
    sentence_ids: tuple[str, ...]
    text_variant: Literal["traditional", "simplified"]
    quote_text: str = Field(min_length=1, max_length=2400)
    page_ids: tuple[str, ...] = ()
    review_notice: str = "OCR 转写与自动整理资料，保留人工待核状态；可对照真实书影。"
    checksum: Checksum

    @model_validator(mode="after")
    def verify_integrity(self):
        if self.checksum != canonical_checksum(self.model_dump(mode="json", exclude={"checksum"})):
            raise ValueError("reader quote checksum mismatch")
        return self
