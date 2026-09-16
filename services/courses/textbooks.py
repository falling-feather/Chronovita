"""Teacher-authored reading content; interactive resources keep their own lifecycle."""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict

from services import content


class TextbookLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lesson_id: str
    lesson_no: str
    title: str
    abstract: str
    body: list[str]
    duration: str
    keywords: list[content.KeywordCard]
    people: list[content.PersonCard]
    map_points: list[content.MapPoint]
    source_refs: list[content.SourceRef]


class TextbookCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str
    title: str
    era: str
    era_id: str
    section: str
    source_pr: int
    source_commit: str
    source_checksums: dict[str, str]
    text_checksum: str
    lessons: list[TextbookLesson]


def text_checksum(payload: dict) -> str:
    values = {key: payload[key] for key in (
        "course_id", "title", "era", "era_id", "section", "lessons"
    )}
    return hashlib.sha256(json.dumps(
        values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def load_textbooks() -> dict[str, TextbookCourse]:
    result = {}
    for path in sorted((content.content_root() / "textbooks").glob("*.json")):
        book = TextbookCourse.model_validate_json(path.read_text(encoding="utf-8"))
        ids = [lesson.lesson_id for lesson in book.lessons]
        if (path.stem != book.course_id or len(ids) != len(set(ids))
                or book.text_checksum != text_checksum(book.model_dump(mode="json"))):
            raise content.ContentIntegrityError(f"Invalid textbook snapshot: {path.name}")
        result[book.course_id] = book
    return result


def lesson_reading_checksum(course_id: str, lesson: TextbookLesson) -> str:
    return hashlib.sha256(json.dumps(
        {"course_id": course_id, "lesson": lesson.model_dump(mode="json")},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
