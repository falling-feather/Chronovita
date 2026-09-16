"""Teacher-authored reading catalogue; legacy interaction state is isolated."""
from __future__ import annotations

import json
import re
from pathlib import Path
from functools import lru_cache
from typing import Optional, TypeVar

from pydantic import BaseModel, Field, ValidationError

from services import content as content_data
from services.contracts.v1 import CoursePackageV1
from services.content.workflow import PublishedCourseSnapshot
from .textbooks import load_textbooks, TextbookCourse, lesson_reading_checksum
from services.content.asset_identity import identity, name_forms


ModelT = TypeVar("ModelT", bound=BaseModel)


def _project_content_model(
    model_type: type[ModelT],
    identity: str,
    **data,
) -> ModelT:
    try:
        return model_type(**data)
    except ValidationError as exc:
        raise content_data.ContentIntegrityError(
            f"Published content {identity} is incompatible with the student model."
        ) from exc


class Era(BaseModel):
    id: str
    name: str
    period: str
    summary: str


class CourseSummary(BaseModel):
    id: str
    era_id: str
    title: str
    subtitle: str
    cover_color: str
    section: str        # 板块：通史 / 思想 / 制度 / 文化
    lesson_count: int


class Keyword(BaseModel):
    word: str
    pinyin: str
    gloss: str


class LessonSummary(BaseModel):
    id: str
    num: str
    title: str
    duration: str        # 占位时长
    state: str = "open"  # open | done | lock


class LessonScenarioRef(BaseModel):
    scenario_id: str
    scenario_version: int
    checksum: str
    primary: bool = False


class Lesson(BaseModel):
    id: str
    course_id: str
    num: str
    title: str
    duration: str
    abstract: str
    body: list[str]                # 教材级正文段落
    keywords: list[Keyword] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)        # 关键人物
    sandbox_id: Optional[str] = None
    seed_canvas: list[dict] = Field(default_factory=list)   # 「创」层默认知识节点
    unit: str = ""
    era: str = ""
    people: list[dict] = Field(default_factory=list)
    interaction_people: list[dict] = Field(default_factory=list)
    interaction_figures: list[str] = Field(default_factory=list)
    map_points: list[dict] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    qa_points: list[str] = Field(default_factory=list)
    level_goals: list[str] = Field(default_factory=list)
    saga_material: dict | None = None
    sandbox_material: dict | None = None
    content_status: str = "builtin"
    content_version: int = 0
    sealed_at: str | None = None
    sealed_by: str | None = None
    content_checksum: str | None = None
    teacher_text_checksum: str | None = None
    rag_available: bool = False
    reading_media_available: bool = False
    release_id: str | None = None
    release_no: int | None = None
    release_checksum: str | None = None
    scenario_refs: list[LessonScenarioRef] = Field(default_factory=list)
    primary_scenario_id: str | None = None


class Course(BaseModel):
    summary: CourseSummary
    intro: str
    lessons: list[LessonSummary]



ERA_PERIODS = {
    "prequin": "约前2070 — 前221", "qinhan": "前221 — 220",
    "weijin": "220 — 589", "suitang": "581 — 907",
    "songyuan": "960 — 1368", "mingqing": "1368 — 1912",
}
ERA_COLORS = {
    "prequin": "#856c52", "qinhan": "#855f4e", "weijin": "#5b6e8b",
    "suitang": "#507a88", "songyuan": "#667b59", "mingqing": "#865653",
}
PRACTICE_FIELDS = (
    "sandbox_id", "seed_canvas", "facts", "qa_points", "level_goals",
    "saga_material", "sandbox_material", "release_id", "release_no",
    "release_checksum", "scenario_refs", "primary_scenario_id",
    "content_status", "content_version", "content_checksum",
    "rag_available",
)


def _ordered_books():
    return sorted(load_textbooks().values(), key=lambda book: (
        min((int(match.group(1)) if (match := re.fullmatch(r"L(\d+)", item.lesson_id)) else 10**9
             for item in book.lessons), default=0), book.course_id))


def list_eras() -> list[Era]:
    groups = {}
    for book in _ordered_books():
        groups.setdefault(book.era_id, []).append(book)
    return [Era(id=key, name=items[0].era, period=ERA_PERIODS.get(key, ""),
                summary=" · ".join(dict.fromkeys(book.title for book in items)))
            for key, items in groups.items()]


def list_courses(era_id: Optional[str] = None, section: Optional[str] = None,
                 q: Optional[str] = None) -> list[CourseSummary]:
    books = _ordered_books()
    if q and q.strip():
        terms = q.casefold().split()
        def matches(book):
            parts = [book.title]
            for lesson in book.lessons:
                parts.extend([lesson.title, lesson.abstract])
                parts.extend(k.word for k in lesson.keywords)
                parts.extend(p.name for p in lesson.people)
            haystack = "\n".join(parts).casefold()
            return all(term in haystack for term in terms)
        books = [book for book in books if matches(book)]
    items = [_textbook_course(book).summary for book in books]
    if era_id and era_id != "all":
        items = [item for item in items if item.era_id == era_id]
    if section and section != "all":
        items = [item for item in items if item.section == section]
    return items


def list_builtin_lessons() -> list[Lesson]:
    """Keep the editor's existing source endpoint, now backed only by teacher text."""
    return [get_lesson(lesson.lesson_id) for book in _ordered_books() for lesson in book.lessons]


def get_builtin_lesson(lesson_id: str) -> Optional[Lesson]:
    return get_lesson(lesson_id)


def course_summary_for_lesson(lesson: Lesson) -> CourseSummary | None:
    course = get_course(lesson.course_id)
    return course.summary if course else None


def get_course(course_id: str) -> Optional[Course]:
    book = load_textbooks().get(course_id)
    return _textbook_course(book) if book else None


def get_interactive_lesson(lesson_id: str) -> Optional[Lesson]:
    """Internal release projection for practice; never a reading fallback."""
    for snapshot in content_data.load_published_snapshots():
        if snapshot.package.lesson_id == lesson_id:
            return _lesson_from_content(snapshot)
    return None


@lru_cache(maxsize=1)
def _legacy_interactions() -> dict:
    return json.loads(Path(__file__).with_name("legacy_interactions.json").read_text(encoding="utf-8"))


def _reading_people(text) -> list[dict]:
    assets = content_data.list_assets("person")
    result = []
    for person in text.people:
        exact = [item for item in assets if identity(item.title) == identity(person.name)]
        matches = exact or [item for item in assets if name_forms(item.title) & name_forms(person.name)]
        profile = content_data.get_person_profile(matches[0].asset_id) if len(matches) == 1 else None
        entry = person.model_dump(mode="json")
        if profile and text.lesson_id in profile.related_lessons:
            entry.update(role=profile.role, summary=profile.summary,
                         asset_id=profile.asset_id,
                         source_refs=[ref.model_dump(mode="json") for ref in profile.source_refs],
                         supplemental="维基百科补充" in profile.teacher_notes)
        result.append(entry)
    return result


def get_lesson(lesson_id: str) -> Optional[Lesson]:
    for book in load_textbooks().values():
        for text in book.lessons:
            if text.lesson_id != lesson_id:
                continue
            practice = dict(_legacy_interactions().get(lesson_id, {}))
            legacy_figures = practice.pop("figures", [])
            release = get_interactive_lesson(lesson_id)
            if release:
                practice.update({key: release.model_dump(mode="json")[key] for key in PRACTICE_FIELDS})
            return Lesson(
                id=lesson_id, course_id=book.course_id, num=text.lesson_no,
                title=text.title, abstract=text.abstract, body=text.body,
                duration=text.duration, era=book.era, unit=book.title,
                keywords=[Keyword(**word.model_dump()) for word in text.keywords],
                people=_reading_people(text), figures=[person.name for person in text.people],
                interaction_people=release.people if release else [],
                interaction_figures=release.figures if release else legacy_figures,
                map_points=[point.model_dump(mode="json") for point in text.map_points],
                source_refs=[ref.model_dump(mode="json") for ref in text.source_refs],
                teacher_text_checksum=lesson_reading_checksum(book.course_id, text),
                reading_media_available=bool(release and release.rag_available and _reading_matches(text, release)),
                **practice,
            )
    return None


def _textbook_course(book: TextbookCourse) -> Course:
    titles = " · ".join(item.title for item in book.lessons)
    return Course(
        summary=CourseSummary(
            id=book.course_id, era_id=book.era_id, title=book.title,
            subtitle=titles, cover_color=ERA_COLORS.get(book.era_id, "#2f6f71"),
            section=book.section, lesson_count=len(book.lessons),
        ),
        intro="",
        lessons=[LessonSummary(id=item.lesson_id, num=item.lesson_no,
                               title=item.title, duration=item.duration) for item in book.lessons],
    )


def reading_media_matches(course_id: str, lesson_id: str, package: CoursePackageV1) -> bool:
    """Old media may not accompany a changed teacher text merely because IDs match."""
    book = load_textbooks().get(course_id)
    if book is None:
        return False
    text = next((item for item in book.lessons if item.lesson_id == lesson_id), None)
    return text is not None and _reading_matches(text, package)


def _reading_matches(text, package: CoursePackageV1 | Lesson) -> bool:
    return (
        text.title == package.title and text.abstract == package.abstract
        and text.body == list(package.body)
        and [k.model_dump(mode="json") for k in text.keywords]
        == [dict(word=k.word, pinyin=k.pinyin, gloss=k.gloss) for k in package.keywords]
    )

def _lesson_from_content(snapshot: PublishedCourseSnapshot) -> Lesson:
    pkg = snapshot.package
    legacy_materials = {item.kind: item for item in pkg.compatibility.legacy_materials}
    saga_material = legacy_materials.get("saga")
    sandbox_material = legacy_materials.get("sandbox")
    scenario_refs = [
        LessonScenarioRef(
            scenario_id=item.scenario_id,
            scenario_version=item.scenario_version,
            checksum=str(item.checksum),
            primary=item.primary,
        )
        for item in pkg.scenario_refs
        if item.checksum is not None
    ] if snapshot.release_schema_version in {
        "course-release/v2",
        "course-release/v3",
        "course-release/v4",
        "course-release/v5",
    } else []
    return _project_content_model(
        Lesson,
        f"lesson:{pkg.lesson_id}",
        id=pkg.lesson_id,
        course_id=pkg.course_id,
        num=pkg.lesson_no,
        title=pkg.title,
        duration=pkg.duration,
        abstract=pkg.abstract,
        body=pkg.body,
        keywords=[Keyword(word=k.word, pinyin=k.pinyin, gloss=k.gloss) for k in pkg.keywords],
        figures=[person.name for person in pkg.people],
        sandbox_id=(sandbox_material.title if sandbox_material else None),
        seed_canvas=[
            {"id": node.node_id, "label": node.label, "note": node.note}
            for node in pkg.seed_canvas
        ],
        unit=pkg.unit,
        era=pkg.era,
        people=[person.model_dump(mode="json") for person in pkg.people],
        map_points=[point.model_dump(mode="json") for point in pkg.map_points],
        source_refs=[
            {
                "title": ref.title,
                "source": ref.publisher,
                "url_or_path": ref.url_or_path,
                "citation_note": ref.citation_note,
                "reliability": ref.reliability,
                "kind": ref.kind,
            }
            for ref in pkg.source_refs
        ],
        facts=[fact.statement for fact in pkg.facts],
        qa_points=pkg.qa_points,
        level_goals=pkg.level_goals,
        saga_material=(saga_material.model_dump(mode="json") if saga_material else {}),
        sandbox_material=(sandbox_material.model_dump(mode="json") if sandbox_material else {}),
        content_status="published",
        rag_available=snapshot.release_schema_version in {
            "course-release/v3", "course-release/v4", "course-release/v5"
        },
        content_version=pkg.content_version,
        sealed_at=pkg.sealed_at.isoformat() if pkg.sealed_at else None,
        sealed_by=pkg.sealed_by,
        content_checksum=pkg.checksum,
        release_id=snapshot.release_id,
        release_no=snapshot.release_no,
        release_checksum=snapshot.release_checksum,
        scenario_refs=scenario_refs,
        primary_scenario_id=next(
            (item.scenario_id for item in scenario_refs if item.primary),
            None,
        ),
    )
