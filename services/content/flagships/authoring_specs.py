"""Stable, private authoring inputs shared by per-lesson draft sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services import content
from services.contracts.v1 import course_package_from_legacy


@dataclass(frozen=True)
class LessonSourceSpec:
    key: str
    title: str
    kind: str
    author_or_institution: str
    publisher: str
    url_or_path: str
    locator: str
    citation_note: str
    reliability: str = "reviewed"
    published_year: int | None = None


@dataclass(frozen=True)
class EvidencePassageSpec:
    source_key: str
    title: str
    text: str
    summary: str
    fact_keys: tuple[str, ...]
    keywords: tuple[str, ...]
    evidence_kind: str
    certainty: str
    chronology_note: str
    people: tuple[str, ...] = ()
    teaching_note: str = ""


def load_teacher_lesson(
    course_id: str,
    lesson_id: str,
    expected_title: str,
    textbook_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read and identity-check one lesson from the current textbook snapshot."""

    path = textbook_path or (
        Path(__file__).resolve().parents[3]
        / "content"
        / "textbooks"
        / f"{course_id}.json"
    )
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("course_id") != course_id:
        raise ValueError(f"Unexpected teacher course identity in {path}.")
    lesson = next(
        (
            item
            for item in snapshot.get("lessons", [])
            if item.get("lesson_id") == lesson_id
        ),
        None,
    )
    if lesson is None or lesson.get("title") != expected_title:
        raise ValueError(f"Current teacher lesson {lesson_id} is missing or renamed.")
    return snapshot, lesson


def merge_lesson_source_refs(
    teacher_lesson: dict[str, Any],
    source_specs: tuple[LessonSourceSpec, ...],
) -> list[content.SourceRef]:
    """Retain teacher references and add checked sources by canonical URL."""

    by_url: dict[str, content.SourceRef] = {}
    for item in teacher_lesson.get("source_refs", []):
        by_url[item["url_or_path"]] = content.SourceRef(
            title=item["title"],
            source=item.get("source", ""),
            url_or_path=item["url_or_path"],
            citation_note=item.get("citation_note", ""),
            reliability=item.get("reliability", "pending"),
        )
    for spec in source_specs:
        by_url[spec.url_or_path] = content.SourceRef(
            title=spec.title,
            source=spec.publisher,
            url_or_path=spec.url_or_path,
            citation_note=f"定位：{spec.locator}。{spec.citation_note}",
            reliability=spec.reliability,
        )
    return sorted(by_url.values(), key=lambda item: (item.title, item.url_or_path))


def package_indexes(course_draft: content.LessonContentPackage):
    """Return stable fact, person and source IDs from the existing contract."""

    package = course_package_from_legacy(course_draft)
    fact_ids = {item.statement: item.fact_id for item in package.facts}
    person_ids = {item.name: item.person_id for item in package.people}
    source_ids = {item.title: item.source_id for item in package.source_refs}
    return package, fact_ids, person_ids, source_ids


def evidence_fact_refs(
    keys: tuple[str, ...],
    facts: dict[str, str],
    fact_ids: dict[str, str],
) -> list[str]:
    return sorted({fact_ids[facts[key]] for key in keys})


__all__ = [
    "EvidencePassageSpec",
    "LessonSourceSpec",
    "evidence_fact_refs",
    "load_teacher_lesson",
    "merge_lesson_source_refs",
    "package_indexes",
]
