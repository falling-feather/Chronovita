from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTENT_ROOT = _REPO_ROOT / "content"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")


def configure(content_root: str | os.PathLike[str] | None = None) -> None:
    global _CONTENT_ROOT
    root = content_root or os.getenv("CHRONO_CONTENT_ROOT") or "content"
    path = Path(root)
    _CONTENT_ROOT = path if path.is_absolute() else _REPO_ROOT / path
    ensure_content_dirs()


def content_root() -> Path:
    return _CONTENT_ROOT


def draft_dir() -> Path:
    return _CONTENT_ROOT / "drafts"


def sealed_dir() -> Path:
    return _CONTENT_ROOT / "sealed"


def ensure_content_dirs() -> None:
    draft_dir().mkdir(parents=True, exist_ok=True)
    sealed_dir().mkdir(parents=True, exist_ok=True)


class KeywordCard(BaseModel):
    word: str
    pinyin: str = ""
    gloss: str = ""


class PersonCard(BaseModel):
    name: str
    role: str = ""
    summary: str = ""
    persona: str = ""
    boundaries: list[str] = Field(default_factory=list)


class MapPoint(BaseModel):
    label: str
    region: str = ""
    lat: float | None = None
    lng: float | None = None
    note: str = ""
    kind: str = "site"


class SourceRef(BaseModel):
    title: str
    source: str = ""
    url_or_path: str = ""
    citation_note: str = ""
    reliability: str = "pending"


class MaterialPlaceholder(BaseModel):
    title: str = ""
    objective: str = ""
    notes: str = ""
    assets: list[str] = Field(default_factory=list)


class SeedCanvasNode(BaseModel):
    id: str = ""
    label: str
    note: str = ""


class LessonContentPackage(BaseModel):
    lesson_id: str
    title: str
    unit: str
    era: str
    body: list[str] = Field(default_factory=list)

    course_id: str = "C-content-studio"
    course_title: str = ""
    era_id: str = "content"
    section: str = "内容包"
    lesson_no: str = "A1"
    duration: str = "08:00"
    abstract: str = ""

    keywords: list[KeywordCard] = Field(default_factory=list)
    people: list[PersonCard] = Field(default_factory=list)
    map_points: list[MapPoint] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)

    facts: list[str] = Field(default_factory=list)
    qa_points: list[str] = Field(default_factory=list)
    level_goals: list[str] = Field(default_factory=list)
    saga_material: MaterialPlaceholder = Field(default_factory=MaterialPlaceholder)
    sandbox_material: MaterialPlaceholder = Field(default_factory=MaterialPlaceholder)
    seed_canvas: list[SeedCanvasNode] = Field(default_factory=list)
    teacher_notes: str = ""

    status: Literal["draft", "sealed"] = "draft"
    version: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sealed_at: datetime | None = None
    sealed_by: str | None = None
    checksum: str | None = None

    @field_validator("lesson_id", "course_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _ID_PATTERN.match(value):
            raise ValueError("Use 2-64 characters: letters, numbers, dot, underscore or dash.")
        return value

    @field_validator("body", mode="before")
    @classmethod
    def _coerce_body(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"\n\s*\n", value) if part.strip()]
        return value

    @model_validator(mode="after")
    def _fill_teacher_friendly_defaults(self) -> "LessonContentPackage":
        if not self.course_title:
            self.course_title = self.unit
        if not self.abstract and self.body:
            first = self.body[0].strip()
            self.abstract = first[:118] + ("..." if len(first) > 118 else "")
        if not self.seed_canvas:
            self.seed_canvas = [
                SeedCanvasNode(id=f"k{i + 1}", label=item.word)
                for i, item in enumerate(self.keywords[:6])
            ]
        return self


class ContentFileRecord(BaseModel):
    lesson_id: str
    title: str
    status: str
    version: int
    path: str
    updated_at: datetime | None = None
    sealed_at: datetime | None = None
    sealed_by: str | None = None
    checksum: str | None = None


def content_template() -> LessonContentPackage:
    return LessonContentPackage(
        lesson_id="lesson-sample",
        title="课程标题",
        unit="示例单元",
        era="示例时代",
        body=["第一段课文正文。", "第二段课文正文。"],
        keywords=[KeywordCard(word="关键词", pinyin="", gloss="给学生看的简明解释。")],
        people=[PersonCard(name="历史人物", role="身份", summary="人物与本课的关系。")],
        map_points=[MapPoint(label="地点", region="区域", note="与课程相关的空间信息。")],
        source_refs=[SourceRef(title="资料标题", source="教材或资料来源", citation_note="页码或版本说明")],
        facts=["不可违背的史实边界。"],
        qa_points=["学生可能追问的问题。"],
        level_goals=["本课关卡目标或学习目标。"],
        saga_material=MaterialPlaceholder(title="saga 占位", objective="后续互动叙事目标"),
        sandbox_material=MaterialPlaceholder(title="sandbox 占位", objective="后续参数化推演目标"),
    )


def save_draft(payload: LessonContentPackage, saved_by: str | None = None) -> LessonContentPackage:
    ensure_content_dirs()
    now = _now()
    existing = get_draft(payload.lesson_id)
    data = payload.model_copy(deep=True)
    data.status = "draft"
    data.version = existing.version if existing else max(data.version, 0)
    data.created_at = existing.created_at if existing else (data.created_at or now)
    data.updated_at = now
    data.sealed_at = None
    data.sealed_by = None
    data.checksum = None
    _write_json(_draft_path(data.lesson_id), data)
    return data


def get_draft(lesson_id: str) -> LessonContentPackage | None:
    path = _draft_path(lesson_id)
    if not path.exists():
        return None
    return _read_package(path)


def list_drafts() -> list[ContentFileRecord]:
    ensure_content_dirs()
    return [
        _record_from_package(pkg, path)
        for path in sorted(draft_dir().glob("*.json"))
        if (pkg := _safe_read_package(path)) is not None
    ]


def preview_package(payload: LessonContentPackage) -> LessonContentPackage:
    data = payload.model_copy(deep=True)
    data.status = "draft"
    data.updated_at = _now()
    data.checksum = None
    return LessonContentPackage.model_validate(data.model_dump())


def seal_draft(lesson_id: str, sealed_by: str) -> tuple[LessonContentPackage, Path]:
    ensure_content_dirs()
    draft = get_draft(lesson_id)
    if draft is None:
        raise FileNotFoundError(f"Draft not found: {lesson_id}")

    version = _next_version(lesson_id)
    sealed = draft.model_copy(deep=True)
    sealed.status = "sealed"
    sealed.version = version
    sealed.updated_at = _now()
    sealed.sealed_at = sealed.updated_at
    sealed.sealed_by = sealed_by
    sealed.checksum = None
    sealed.checksum = _checksum(sealed)

    path = sealed_dir() / f"{lesson_id}-v{version:03d}.json"
    if path.exists():
        raise FileExistsError(f"Sealed file already exists: {path}")
    _write_json(path, sealed)
    return sealed, path


def list_sealed() -> list[ContentFileRecord]:
    return [
        _record_from_package(pkg, path)
        for path in sorted(sealed_dir().glob("*.json"))
        if (pkg := _safe_read_package(path)) is not None
    ]


def record_for_package(pkg: LessonContentPackage, path: Path) -> ContentFileRecord:
    return _record_from_package(pkg, path)


def load_sealed_packages(latest_only: bool = True) -> list[LessonContentPackage]:
    ensure_content_dirs()
    packages = [
        pkg
        for path in sorted(sealed_dir().glob("*.json"))
        if (pkg := _safe_read_package(path)) is not None and pkg.status == "sealed"
    ]
    if not latest_only:
        return packages
    latest: dict[str, LessonContentPackage] = {}
    for pkg in packages:
        current = latest.get(pkg.lesson_id)
        if current is None or (pkg.version, pkg.sealed_at or datetime.min.replace(tzinfo=timezone.utc)) > (
            current.version,
            current.sealed_at or datetime.min.replace(tzinfo=timezone.utc),
        ):
            latest[pkg.lesson_id] = pkg
    return sorted(latest.values(), key=lambda item: (item.course_id, item.lesson_no, item.lesson_id))


def _draft_path(lesson_id: str) -> Path:
    if not _ID_PATTERN.match(lesson_id):
        raise ValueError("Invalid lesson_id")
    return draft_dir() / f"{lesson_id}.json"


def _next_version(lesson_id: str) -> int:
    versions: list[int] = []
    for path in sealed_dir().glob(f"{lesson_id}-v*.json"):
        match = re.search(r"-v(\d+)\.json$", path.name)
        if match:
            versions.append(int(match.group(1)))
    return (max(versions) + 1) if versions else 1


def _record_from_package(pkg: LessonContentPackage, path: Path) -> ContentFileRecord:
    return ContentFileRecord(
        lesson_id=pkg.lesson_id,
        title=pkg.title,
        status=pkg.status,
        version=pkg.version,
        path=str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
        updated_at=pkg.updated_at,
        sealed_at=pkg.sealed_at,
        sealed_by=pkg.sealed_by,
        checksum=pkg.checksum,
    )


def _safe_read_package(path: Path) -> LessonContentPackage | None:
    try:
        return _read_package(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _read_package(path: Path) -> LessonContentPackage:
    return LessonContentPackage.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, payload: LessonContentPackage) -> None:
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _checksum(payload: LessonContentPackage) -> str:
    data = payload.model_dump(mode="json")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)
