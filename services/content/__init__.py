from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTENT_ROOT = _REPO_ROOT / "content"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
_WRITE_LOCK = RLock()


class ContentIntegrityError(RuntimeError):
    pass


class DraftFingerprintMismatch(RuntimeError):
    pass


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


def workflow_dir() -> Path:
    return _CONTENT_ROOT / "workflows"


def release_dir() -> Path:
    return _CONTENT_ROOT / "releases"


def package_dir() -> Path:
    return _CONTENT_ROOT / "packages" / "v1"


def runtime_dir() -> Path:
    return _CONTENT_ROOT / "runtime" / "v1"


def runtime_course_package_dir() -> Path:
    return runtime_dir() / "course-packages"


def runtime_scenario_dir() -> Path:
    return runtime_dir() / "scenarios"


def scenario_draft_dir() -> Path:
    return _CONTENT_ROOT / "scenario-drafts"


def assets_dir() -> Path:
    return _CONTENT_ROOT / "assets"


def people_asset_dir() -> Path:
    return assets_dir() / "people"


def keyword_asset_dir() -> Path:
    return assets_dir() / "keywords"


def ensure_content_dirs() -> None:
    draft_dir().mkdir(parents=True, exist_ok=True)
    sealed_dir().mkdir(parents=True, exist_ok=True)
    workflow_dir().mkdir(parents=True, exist_ok=True)
    release_dir().mkdir(parents=True, exist_ok=True)
    package_dir().mkdir(parents=True, exist_ok=True)
    runtime_course_package_dir().mkdir(parents=True, exist_ok=True)
    runtime_scenario_dir().mkdir(parents=True, exist_ok=True)
    scenario_draft_dir().mkdir(parents=True, exist_ok=True)
    people_asset_dir().mkdir(parents=True, exist_ok=True)
    keyword_asset_dir().mkdir(parents=True, exist_ok=True)


class KeywordCard(ContentModel):
    word: str
    pinyin: str = ""
    gloss: str = ""


class PersonCard(ContentModel):
    name: str
    role: str = ""
    summary: str = ""
    persona: str = ""
    boundaries: list[str] = Field(default_factory=list)


class MapPoint(ContentModel):
    label: str
    region: str = ""
    lat: float | None = None
    lng: float | None = None
    note: str = ""
    kind: str = "site"


class SourceRef(ContentModel):
    title: str
    source: str = ""
    url_or_path: str = ""
    citation_note: str = ""
    reliability: Literal["pending", "reviewed", "disputed"] = "pending"


class MaterialPlaceholder(ContentModel):
    title: str = ""
    objective: str = ""
    notes: str = ""
    assets: list[str] = Field(default_factory=list)


class SeedCanvasNode(ContentModel):
    id: str = ""
    label: str
    note: str = ""


class LessonContentPackage(ContentModel):
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
    version: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sealed_at: datetime | None = None
    sealed_by: str | None = None
    checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("lesson_id", "course_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
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
        if self.status == "draft" and (
            self.version != 0
            or self.sealed_at is not None
            or self.sealed_by is not None
            or self.checksum is not None
        ):
            raise ValueError("Draft content cannot carry sealed version or metadata.")
        if self.status == "sealed" and (
            self.version < 1
            or self.sealed_at is None
            or not self.sealed_by
            or self.checksum is None
        ):
            raise ValueError("Sealed content requires version, actor, time and checksum.")
        return self


class ContentFileRecord(ContentModel):
    lesson_id: str
    title: str
    status: str
    version: int
    path: str
    updated_at: datetime | None = None
    sealed_at: datetime | None = None
    sealed_by: str | None = None
    checksum: str | None = None


class ContentAssetRecord(ContentModel):
    asset_id: str
    title: str
    kind: Literal["person", "keyword"]
    path: str
    updated_at: datetime | None = None


class PersonProfilePackage(ContentModel):
    asset_id: str
    name: str
    role: str = ""
    era: str = ""
    summary: str = ""
    persona: str = ""
    boundaries: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    related_lessons: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    teacher_notes: str = ""
    status: Literal["draft", "sealed"] = "draft"
    version: int = 0
    updated_at: datetime | None = None

    @field_validator("asset_id")
    @classmethod
    def _validate_asset_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("Use 2-64 characters: letters, numbers, dot, underscore or dash.")
        return value


class KeywordProfilePackage(ContentModel):
    asset_id: str
    word: str
    pinyin: str = ""
    gloss: str = ""
    era: str = ""
    category: str = ""
    examples: list[str] = Field(default_factory=list)
    related_people: list[str] = Field(default_factory=list)
    related_lessons: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    teacher_notes: str = ""
    status: Literal["draft", "sealed"] = "draft"
    version: int = 0
    updated_at: datetime | None = None

    @field_validator("asset_id")
    @classmethod
    def _validate_asset_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("Use 2-64 characters: letters, numbers, dot, underscore or dash.")
        return value


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


def person_template() -> PersonProfilePackage:
    return PersonProfilePackage(
        asset_id="person-sample",
        name="历史人物",
        role="身份或立场",
        era="示例时代",
        summary="教师给学生看的简明人物说明。",
        persona="后续 AI 人物智能体使用的语气、知识边界与立场提示。",
        boundaries=["不要让人物知道其身后才发生的事件。"],
        keywords=["关键词"],
        related_lessons=["lesson-sample"],
        source_refs=[SourceRef(title="资料标题", source="教材或史料", citation_note="页码或版本说明")],
    )


def keyword_template() -> KeywordProfilePackage:
    return KeywordProfilePackage(
        asset_id="keyword-sample",
        word="关键词",
        pinyin="",
        gloss="给学生看的简明解释。",
        era="示例时代",
        category="制度/人物/事件/概念",
        examples=["可放一条课堂中的典型用法。"],
        related_people=["历史人物"],
        related_lessons=["lesson-sample"],
        source_refs=[SourceRef(title="资料标题", source="教材或史料", citation_note="页码或版本说明")],
    )


def save_draft(payload: LessonContentPackage, saved_by: str | None = None) -> LessonContentPackage:
    ensure_content_dirs()
    from services.content import workflow as content_workflow

    with content_workflow.workflow_write_lock():
        with _WRITE_LOCK:
            now = _now()
            existing = get_draft(payload.lesson_id)
            data = payload.model_copy(deep=True)
            data.status = "draft"
            data.version = 0
            data.created_at = existing.created_at if existing else (data.created_at or now)
            data.updated_at = now
            data.sealed_at = None
            data.sealed_by = None
            data.checksum = None
            data = LessonContentPackage.model_validate(data.model_dump(mode="json"))
            _write_json(_draft_path(data.lesson_id), data)

        content_workflow.record_draft_saved(data, actor=saved_by or "admin")
    return data


def get_draft(lesson_id: str) -> LessonContentPackage | None:
    path = _draft_path(lesson_id)
    if not path.exists():
        return None
    package = _read_package(path)
    _verify_draft_path(package, path)
    return package


def list_drafts() -> list[ContentFileRecord]:
    ensure_content_dirs()
    records: list[ContentFileRecord] = []
    for path in sorted(draft_dir().glob("*.json")):
        package = _read_package(path)
        _verify_draft_path(package, path)
        records.append(_record_from_package(package, path))
    return records


def preview_package(payload: LessonContentPackage) -> LessonContentPackage:
    data = payload.model_copy(deep=True)
    data.status = "draft"
    data.version = 0
    data.updated_at = _now()
    data.sealed_at = None
    data.sealed_by = None
    data.checksum = None
    return LessonContentPackage.model_validate(data.model_dump())


def seal_draft(lesson_id: str, sealed_by: str) -> tuple[LessonContentPackage, Path]:
    from services.content import workflow as content_workflow

    sealed, path, _ = content_workflow.seal_approved_draft(
        lesson_id,
        actor=sealed_by,
    )
    return sealed, path


def _seal_draft_unchecked(
    lesson_id: str,
    sealed_by: str,
    *,
    expected_fingerprint: str,
) -> tuple[LessonContentPackage, Path]:
    """Materialize a seal after the workflow service has authorized it."""
    ensure_content_dirs()
    with _WRITE_LOCK:
        draft = get_draft(lesson_id)
        if draft is None:
            raise FileNotFoundError(f"Draft not found: {lesson_id}")
        if draft_fingerprint(draft) != expected_fingerprint:
            raise DraftFingerprintMismatch(
                "Draft changed after workflow approval and cannot be sealed."
            )

        version = _next_version(lesson_id)
        sealed = draft.model_copy(deep=True)
        sealed.status = "sealed"
        sealed.version = version
        sealed.updated_at = _now()
        sealed.sealed_at = sealed.updated_at
        sealed.sealed_by = sealed_by
        sealed.checksum = None
        sealed.checksum = package_checksum(sealed)
        sealed = LessonContentPackage.model_validate(sealed.model_dump(mode="json"))

        path = sealed_dir() / f"{lesson_id}-v{version:03d}.json"
        _write_json(path, sealed, overwrite=False)
        return sealed, path


def list_sealed() -> list[ContentFileRecord]:
    records: list[ContentFileRecord] = []
    for path in sorted(sealed_dir().glob("*.json")):
        package = _read_package(path, verify_checksum=True)
        _verify_sealed_path(package, path)
        records.append(_record_from_package(package, path))
    return records


def list_assets(kind: Literal["person", "keyword"] | None = None) -> list[ContentAssetRecord]:
    ensure_content_dirs()
    records: list[ContentAssetRecord] = []
    if kind in (None, "person"):
        for path in sorted(people_asset_dir().glob("*.json")):
            asset = _read_person(path)
            _verify_person_path(asset, path)
            records.append(_person_record(asset, path))
    if kind in (None, "keyword"):
        for path in sorted(keyword_asset_dir().glob("*.json")):
            asset = _read_keyword(path)
            _verify_keyword_path(asset, path)
            records.append(_keyword_record(asset, path))
    return sorted(records, key=lambda item: (item.kind, item.title, item.asset_id))


def get_person_profile(asset_id: str) -> PersonProfilePackage | None:
    path = _person_path(asset_id)
    if not path.exists():
        return None
    asset = _read_person(path)
    _verify_person_path(asset, path)
    return asset


def save_person_profile(payload: PersonProfilePackage) -> PersonProfilePackage:
    ensure_content_dirs()
    data = payload.model_copy(deep=True)
    data.updated_at = _now()
    data = PersonProfilePackage.model_validate(data.model_dump(mode="json"))
    with _WRITE_LOCK:
        _write_asset_json(_person_path(data.asset_id), data)
    return data


def get_keyword_profile(asset_id: str) -> KeywordProfilePackage | None:
    path = _keyword_path(asset_id)
    if not path.exists():
        return None
    asset = _read_keyword(path)
    _verify_keyword_path(asset, path)
    return asset


def save_keyword_profile(payload: KeywordProfilePackage) -> KeywordProfilePackage:
    ensure_content_dirs()
    data = payload.model_copy(deep=True)
    data.updated_at = _now()
    data = KeywordProfilePackage.model_validate(data.model_dump(mode="json"))
    with _WRITE_LOCK:
        _write_asset_json(_keyword_path(data.asset_id), data)
    return data


def record_for_package(pkg: LessonContentPackage, path: Path) -> ContentFileRecord:
    return _record_from_package(pkg, path)


def load_sealed_packages(latest_only: bool = True) -> list[LessonContentPackage]:
    ensure_content_dirs()
    packages: list[LessonContentPackage] = []
    for path in sorted(sealed_dir().glob("*.json")):
        package = _read_package(path, verify_checksum=True)
        _verify_sealed_path(package, path)
        packages.append(package)
    packages = [pkg for pkg in packages if pkg.status == "sealed"]
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


def get_sealed_package(lesson_id: str, version: int) -> LessonContentPackage:
    if version < 1:
        raise ValueError("version must be at least 1")
    path = sealed_dir() / f"{lesson_id}-v{version:03d}.json"
    if not path.exists():
        raise FileNotFoundError(f"Sealed package not found: {lesson_id} v{version}")
    package = _read_package(path, verify_checksum=True)
    _verify_sealed_path(package, path)
    if package.lesson_id != lesson_id or package.version != version or package.status != "sealed":
        raise ContentIntegrityError(f"Sealed package identity mismatch: {path}")
    return package


def load_published_packages():
    from services.content.workflow import load_published_packages as _load_published_packages

    return _load_published_packages()


def load_published_snapshots():
    from services.content.workflow import load_published_snapshots as _load_published_snapshots

    return _load_published_snapshots()


def _draft_path(lesson_id: str) -> Path:
    if not _ID_PATTERN.fullmatch(lesson_id):
        raise ValueError("Invalid lesson_id")
    return draft_dir() / f"{lesson_id}.json"


def _person_path(asset_id: str) -> Path:
    if not _ID_PATTERN.fullmatch(asset_id):
        raise ValueError("Invalid asset_id")
    return people_asset_dir() / f"{asset_id}.json"


def _keyword_path(asset_id: str) -> Path:
    if not _ID_PATTERN.fullmatch(asset_id):
        raise ValueError("Invalid asset_id")
    return keyword_asset_dir() / f"{asset_id}.json"


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


def _verify_draft_path(package: LessonContentPackage, path: Path) -> None:
    expected = draft_dir().resolve() / f"{package.lesson_id}.json"
    if path.resolve() != expected or package.status != "draft":
        raise ContentIntegrityError(f"Draft package path identity mismatch: {path}")


def _verify_sealed_path(package: LessonContentPackage, path: Path) -> None:
    expected = sealed_dir().resolve() / f"{package.lesson_id}-v{package.version:03d}.json"
    if path.resolve() != expected or package.status != "sealed" or package.version < 1:
        raise ContentIntegrityError(f"Sealed package path identity mismatch: {path}")


def _verify_person_path(asset: PersonProfilePackage, path: Path) -> None:
    expected = people_asset_dir().resolve() / f"{asset.asset_id}.json"
    if path.resolve() != expected:
        raise ContentIntegrityError(f"Person profile path identity mismatch: {path}")


def _verify_keyword_path(asset: KeywordProfilePackage, path: Path) -> None:
    expected = keyword_asset_dir().resolve() / f"{asset.asset_id}.json"
    if path.resolve() != expected:
        raise ContentIntegrityError(f"Keyword profile path identity mismatch: {path}")


def _read_package(path: Path, verify_checksum: bool = False) -> LessonContentPackage:
    try:
        package = LessonContentPackage.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ContentIntegrityError(f"Cannot read content package: {path}") from exc
    if verify_checksum and not verify_package_checksum(package):
        raise ContentIntegrityError(f"Content package checksum mismatch: {path}")
    return package


def _read_person(path: Path) -> PersonProfilePackage:
    try:
        return PersonProfilePackage.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ContentIntegrityError(f"Cannot read person profile: {path}") from exc


def _read_keyword(path: Path) -> KeywordProfilePackage:
    try:
        return KeywordProfilePackage.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ContentIntegrityError(f"Cannot read keyword profile: {path}") from exc


def _write_json(
    path: Path,
    payload: LessonContentPackage,
    *,
    overwrite: bool = True,
) -> None:
    _atomic_write_json(path, payload.model_dump(mode="json"), overwrite=overwrite)


def _write_asset_json(path: Path, payload: BaseModel) -> None:
    _atomic_write_json(path, payload.model_dump(mode="json"))


def _atomic_write_json(path: Path, payload: dict, *, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temp_path, path)
        else:
            try:
                os.link(temp_path, path)
            except FileExistsError:
                raise FileExistsError(f"File already exists: {path}") from None
    finally:
        temp_path.unlink(missing_ok=True)


def _person_record(asset: PersonProfilePackage, path: Path) -> ContentAssetRecord:
    return ContentAssetRecord(
        asset_id=asset.asset_id,
        title=asset.name,
        kind="person",
        path=str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
        updated_at=asset.updated_at,
    )


def _keyword_record(asset: KeywordProfilePackage, path: Path) -> ContentAssetRecord:
    return ContentAssetRecord(
        asset_id=asset.asset_id,
        title=asset.word,
        kind="keyword",
        path=str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
        updated_at=asset.updated_at,
    )


def package_checksum(payload: BaseModel) -> str:
    data = payload.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("payload does not expose a checksum field")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_package_checksum(payload: BaseModel) -> bool:
    checksum = getattr(payload, "checksum", None)
    return bool(checksum) and checksum == package_checksum(payload)


def draft_fingerprint(payload: LessonContentPackage) -> str:
    data = payload.model_dump(mode="json")
    for field in (
        "status",
        "version",
        "created_at",
        "updated_at",
        "sealed_at",
        "sealed_by",
        "checksum",
    ):
        data.pop(field, None)
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _checksum(payload: LessonContentPackage) -> str:
    return package_checksum(payload)


def _now() -> datetime:
    return datetime.now(timezone.utc)
