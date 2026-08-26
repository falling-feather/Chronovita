from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import PurePosixPath
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId


MAX_ARCHIVE_FILE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_FILES = 128
ARCHIVE_MANIFEST_FILENAME = "课程归档清单.json"
ARCHIVE_RELEASE_MANIFEST_FILENAME = "课程发布清单.json"
DEFAULT_REPOSITORY_ROOT_PREFIX = "courses"
DEFAULT_ASSET_REPOSITORY_ROOT_PREFIX = "assets"
ASSET_ARCHIVE_MANIFEST_FILENAME = "内容资产归档清单.json"

ArchiveFileKind = Literal[
    "release-manifest",
    "sealed-lesson",
    "course-package",
    "scenario-template",
    "evidence-corpus",
    "lesson-presentation",
    "format-layer",
    "teacher-markdown",
    "preview-html",
]
ContentAssetKind = Literal["person", "keyword", "scenario"]
ContentAssetArchiveFileKind = Literal[
    "sealed-person",
    "sealed-keyword",
    "sealed-scenario",
]
ArchiveMediaType = Literal[
    "application/json",
    "text/markdown; charset=utf-8",
    "text/html; charset=utf-8",
]
PublicationMode = Literal["pull_request", "direct_commit"]
PublicationStatus = Literal[
    "requested",
    "preparing",
    "pushing",
    "commit_created",
    "ref_updated",
    "pr_open",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
]
ReleaseSchemaVersion = Literal[
    "course-release/v1",
    "course-release/v2",
    "course-release/v3",
]
ReleaseOperation = Literal["bootstrap", "publish", "rollback"]
CredentialKind = Literal["github_app", "fine_grained_token"]

_RELEASE_ID_PATTERN = re.compile(r"^rel-[0-9a-f]{10}-\d{4,}$")
_ARCHIVE_ID_PATTERN = re.compile(r"^arc-[0-9a-f]{32}$")
_PUBLICATION_ID_PATTERN = re.compile(r"^pub-[0-9a-f]{32}$")
_GIT_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SCHEMA_VERSION_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,47}/v[1-9]\d{0,5}$")
_REPOSITORY_OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
_REPOSITORY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_PULL_REQUEST_URL_PATTERN = re.compile(
    r"^https://github\.com/"
    r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/"
    r"[A-Za-z0-9._-]{1,100}/pull/[1-9]\d*$"
)
_WINDOWS_RESERVED_NAMES = {
    "aux",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "con",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
    "nul",
    "prn",
}
_MACHINE_FILE_KINDS = {
    "release-manifest",
    "sealed-lesson",
    "course-package",
    "scenario-template",
    "evidence-corpus",
    "lesson-presentation",
}
_PUBLICATION_MODE_ORDER = {
    "pull_request": 0,
    "direct_commit": 1,
}


def _validated_archive_path(value: str) -> str:
    if value != value.strip() or not value or len(value) > 512:
        raise ValueError("archive path must be 1-512 characters without outer whitespace")
    if unicodedata.normalize("NFKC", value) != value:
        raise ValueError("archive path must use NFKC-normalized Unicode")
    if "\\" in value or value.startswith("/") or value.endswith("/"):
        raise ValueError("archive path must be a relative POSIX path")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("archive path cannot contain control characters")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("archive path cannot contain empty, dot or parent segments")
    for part in parts:
        if (
            len(part) > 120
            or len(part.encode("utf-8")) > 240
            or len(part.encode("utf-16-le")) // 2 > 120
            or part != part.strip()
            or part.endswith((".", " "))
            or any(char in part for char in '<>:"|?*')
        ):
            raise ValueError("archive path components must be portable")
        stem = part.split(".", 1)[0].casefold()
        if stem in _WINDOWS_RESERVED_NAMES or part.casefold() == ".git":
            raise ValueError("archive path contains a reserved filesystem name")
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != value:
        raise ValueError("archive path must already be canonical")
    return value


def _validated_release_id(value: str) -> str:
    if not _RELEASE_ID_PATTERN.fullmatch(value):
        raise ValueError("invalid course release id")
    return value


def _validated_branch_name(value: str) -> str:
    if value != value.strip() or not value or len(value) > 200:
        raise ValueError("branch name must be 1-200 characters without outer whitespace")
    if (
        value == "@"
        or value.startswith(("/", "-"))
        or value.endswith(("/", ".", ".lock"))
        or "//" in value
        or ".." in value
        or "@{" in value
        or any(char in value for char in " ~^:?*[\\")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("branch name is not a safe Git reference")
    if any(part in {"", ".", ".."} or part.endswith(".lock") for part in value.split("/")):
        raise ValueError("branch name contains an invalid component")
    return value


def _validated_schema_version(value: str) -> str:
    if not _SCHEMA_VERSION_PATTERN.fullmatch(value):
        raise ValueError("schema_version must use the stable name/vN form")
    return value


ArchivePath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512),
    AfterValidator(_validated_archive_path),
]
ReleaseId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(_validated_release_id),
]
BranchName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200),
    AfterValidator(_validated_branch_name),
]
ArtifactSchemaVersion = Annotated[
    str,
    StringConstraints(min_length=4, max_length=56),
    AfterValidator(_validated_schema_version),
]
BoundedTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
BoundedSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=2000),
]
BoundedActor = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]


class ArchiveContractModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )


class ArchiveRendererV1(ArchiveContractModel):
    schema_version: Literal["archive-renderer/v1"] = "archive-renderer/v1"
    renderer_id: ContractId
    renderer_version: int = Field(ge=1)
    style_profile: ContractId


class CourseArchiveScenarioV1(ArchiveContractModel):
    scenario_id: ContractId
    scenario_version: int = Field(ge=1)
    scenario_checksum: Checksum
    primary: bool = False


class CourseArchiveLessonV1(ArchiveContractModel):
    lesson_id: ContractId
    title: BoundedTitle
    content_version: int = Field(ge=1)
    source_checksum: Checksum
    course_package_id: ContractId
    course_package_checksum: Checksum
    scenarios: tuple[CourseArchiveScenarioV1, ...] = ()
    files: tuple[ArchivePath, ...]

    @model_validator(mode="after")
    def validate_lesson(self) -> "CourseArchiveLessonV1":
        scenario_ids = [item.scenario_id for item in self.scenarios]
        if scenario_ids != sorted(set(scenario_ids)):
            raise ValueError("lesson scenarios must be unique and sorted by scenario_id")
        primary_count = sum(item.primary for item in self.scenarios)
        if self.scenarios and primary_count != 1:
            raise ValueError("a lesson with scenarios requires exactly one primary scenario")
        if not self.scenarios and primary_count:
            raise ValueError("a lesson without scenarios cannot identify a primary scenario")
        expected_files = list(lesson_archive_paths(self.lesson_id, self.title).values())
        expected_files.extend(
            scenario_archive_path(
                self.lesson_id,
                scenario.scenario_id,
                scenario.scenario_version,
            )
            for scenario in self.scenarios
        )
        expected = set(expected_files)
        extra = set(self.files) - expected
        evidence_prefix = f"lessons/{self.lesson_id}/evidence/"
        presentation_prefix = f"lessons/{self.lesson_id}/presentation/"
        if extra and (
            len(extra) != 2
            or sum(path.startswith(evidence_prefix) for path in extra) != 1
            or sum(path.startswith(presentation_prefix) for path in extra) != 1
        ):
            raise ValueError(
                "lesson supplemental files must contain one evidence corpus and one presentation"
            )
        expected.update(extra)
        if self.files != tuple(sorted(expected, key=str.casefold)):
            raise ValueError("lesson files must exactly match deterministic archive paths")
        return self


class CourseArchiveFileV1(ArchiveContractModel):
    path: ArchivePath
    kind: ArchiveFileKind
    media_type: ArchiveMediaType
    size_bytes: int = Field(ge=1, le=MAX_ARCHIVE_FILE_BYTES)
    blob_sha256: Checksum
    lesson_id: ContractId | None = None
    artifact_id: ContractId | None = None
    artifact_version: int | None = Field(default=None, ge=1)
    schema_version: ArtifactSchemaVersion | None = None
    contract_checksum: Checksum | None = None

    @model_validator(mode="after")
    def validate_file(self) -> "CourseArchiveFileV1":
        expected_media = {
            "release-manifest": "application/json",
            "sealed-lesson": "application/json",
            "course-package": "application/json",
            "scenario-template": "application/json",
            "evidence-corpus": "application/json",
            "lesson-presentation": "application/json",
            "format-layer": "application/json",
            "teacher-markdown": "text/markdown; charset=utf-8",
            "preview-html": "text/html; charset=utf-8",
        }[self.kind]
        expected_suffix = {
            "application/json": ".json",
            "text/markdown; charset=utf-8": ".md",
            "text/html; charset=utf-8": ".html",
        }[self.media_type]
        if self.media_type != expected_media or not self.path.endswith(expected_suffix):
            raise ValueError("archive file media type, kind and extension must agree")

        identity = (
            self.artifact_id,
            self.artifact_version,
            self.schema_version,
            self.contract_checksum,
        )
        if self.kind in _MACHINE_FILE_KINDS and any(item is None for item in identity):
            raise ValueError("machine-readable source files require a complete identity")
        if self.kind not in _MACHINE_FILE_KINDS and any(item is not None for item in identity):
            raise ValueError("derived presentation files cannot claim a source identity")

        if self.kind == "release-manifest":
            if self.lesson_id is not None:
                raise ValueError("the release manifest is course-scoped")
        elif self.lesson_id is None:
            raise ValueError("lesson archive files require lesson_id")
        return self


class CourseArchivePayloadV1(ArchiveContractModel):
    schema_version: Literal["course-archive/v1"] = "course-archive/v1"
    course_id: ContractId
    course_title: BoundedTitle
    release_schema_version: ReleaseSchemaVersion
    release_id: ReleaseId
    release_no: int = Field(ge=1)
    release_checksum: Checksum
    release_operation: ReleaseOperation
    release_created_at: AwareDatetime
    release_created_by: BoundedActor
    release_note: BoundedSummary = ""
    renderer: ArchiveRendererV1
    manifest_path: Literal[ARCHIVE_MANIFEST_FILENAME] = ARCHIVE_MANIFEST_FILENAME
    lessons: tuple[CourseArchiveLessonV1, ...]
    files: tuple[CourseArchiveFileV1, ...]
    file_count: int = Field(ge=1, le=MAX_ARCHIVE_FILES)
    total_size_bytes: int = Field(ge=1, le=MAX_ARCHIVE_TOTAL_BYTES)

    @model_validator(mode="after")
    def validate_payload(self) -> "CourseArchivePayloadV1":
        if int(self.release_id.rsplit("-", 1)[1]) != self.release_no:
            raise ValueError("release_id sequence must match release_no")

        lesson_ids = [lesson.lesson_id for lesson in self.lessons]
        if lesson_ids != sorted(set(lesson_ids)):
            raise ValueError("archive lessons must be unique and sorted by lesson_id")
        if not self.lessons:
            raise ValueError("a course archive must contain at least one lesson")

        paths = [item.path for item in self.files]
        if paths != sorted(paths, key=str.casefold):
            raise ValueError("archive files must be sorted by path")
        normalized_paths = [
            unicodedata.normalize("NFKC", path).casefold()
            for path in paths
        ]
        if len(normalized_paths) != len(set(normalized_paths)):
            raise ValueError("archive file paths must be unique after Unicode/case folding")
        if self.file_count != len(self.files):
            raise ValueError("file_count must equal files length")
        if self.total_size_bytes != sum(item.size_bytes for item in self.files):
            raise ValueError("total_size_bytes must equal the exact file sizes")

        release_files = [item for item in self.files if item.kind == "release-manifest"]
        if len(release_files) != 1:
            raise ValueError("an archive requires exactly one source release manifest")
        release_file = release_files[0]
        if (
            release_file.path != ARCHIVE_RELEASE_MANIFEST_FILENAME
            or release_file.artifact_id != self.release_id
            or release_file.artifact_version != self.release_no
            or release_file.schema_version != self.release_schema_version
            or release_file.contract_checksum != self.release_checksum
        ):
            raise ValueError("source release manifest identity must match the archive")

        lesson_by_id = {lesson.lesson_id: lesson for lesson in self.lessons}
        file_paths_by_lesson: dict[str, list[str]] = {
            lesson_id: [] for lesson_id in lesson_ids
        }
        scenario_ids: list[str] = []
        for item in self.files:
            if item.lesson_id is None:
                continue
            if item.lesson_id not in lesson_by_id:
                raise ValueError("archive file references an unknown lesson")
            expected_prefix = f"lessons/{item.lesson_id}/"
            if not item.path.startswith(expected_prefix):
                raise ValueError("archive file escaped its stable lesson directory")
            file_paths_by_lesson[item.lesson_id].append(item.path)

        required_lesson_kinds = {
            "sealed-lesson",
            "course-package",
            "format-layer",
            "teacher-markdown",
            "preview-html",
        }
        for lesson in self.lessons:
            lesson_files = [
                item for item in self.files if item.lesson_id == lesson.lesson_id
            ]
            kinds = [item.kind for item in lesson_files]
            for required_kind in required_lesson_kinds:
                if kinds.count(required_kind) != 1:
                    raise ValueError(
                        f"lesson {lesson.lesson_id} requires exactly one "
                        f"{required_kind} file"
                    )

            sealed_file = next(
                item for item in lesson_files if item.kind == "sealed-lesson"
            )
            package_file = next(
                item for item in lesson_files if item.kind == "course-package"
            )
            if (
                sealed_file.artifact_id != lesson.lesson_id
                or sealed_file.artifact_version != lesson.content_version
                or sealed_file.schema_version != "lesson-content-package/v1"
                or sealed_file.contract_checksum != lesson.source_checksum
            ):
                raise ValueError("sealed lesson identity must match archive lesson metadata")
            if (
                package_file.artifact_id != lesson.course_package_id
                or package_file.artifact_version != lesson.content_version
                or package_file.schema_version != "course-package/v1"
                or package_file.contract_checksum != lesson.course_package_checksum
            ):
                raise ValueError("course package identity must match archive lesson metadata")

            scenario_file_items = [
                item for item in lesson_files if item.kind == "scenario-template"
            ]
            scenario_files = {
                (
                    item.artifact_id,
                    item.artifact_version,
                    item.contract_checksum,
                )
                for item in scenario_file_items
                if item.schema_version == "scenario-template/v1"
            }
            scenario_refs = {
                (
                    item.scenario_id,
                    item.scenario_version,
                    item.scenario_checksum,
                )
                for item in lesson.scenarios
            }
            if (
                len(scenario_file_items) != len(scenario_refs)
                or scenario_files != scenario_refs
            ):
                raise ValueError("scenario files must exactly match lesson scenario references")
            scenario_ids.extend(item.scenario_id for item in lesson.scenarios)

            evidence_files = [
                item for item in lesson_files if item.kind == "evidence-corpus"
            ]
            presentation_files = [
                item for item in lesson_files if item.kind == "lesson-presentation"
            ]
            if self.release_schema_version == "course-release/v3":
                if len(evidence_files) != 1 or len(presentation_files) != 1:
                    raise ValueError(
                        "V3 archive lessons require one evidence corpus and one presentation"
                    )
                evidence_file = evidence_files[0]
                presentation_file = presentation_files[0]
                if (
                    evidence_file.schema_version != "evidence-corpus/v1"
                    or presentation_file.schema_version != "lesson-presentation/v1"
                ):
                    raise ValueError(
                        "V3 supplement archive schema identities are invalid"
                    )
                if evidence_file.path != supplement_archive_path(
                    lesson.lesson_id,
                    "evidence-corpus",
                    evidence_file.artifact_id or "",
                    evidence_file.artifact_version or 0,
                ):
                    raise ValueError(
                        "evidence corpus must use its deterministic archive path"
                    )
                if presentation_file.path != supplement_archive_path(
                    lesson.lesson_id,
                    "lesson-presentation",
                    presentation_file.artifact_id or "",
                    presentation_file.artifact_version or 0,
                ):
                    raise ValueError(
                        "lesson presentation must use its deterministic archive path"
                    )
            elif evidence_files or presentation_files:
                raise ValueError("V1/V2 archives cannot contain V3 supplements")

            expected_paths = tuple(
                sorted(file_paths_by_lesson[lesson.lesson_id], key=str.casefold)
            )
            if expected_paths != lesson.files:
                raise ValueError(
                    "lesson file list must exactly match archive file descriptors"
                )

        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario_id must be unique across the course archive")
        return self


class CourseArchiveManifestV1(CourseArchivePayloadV1):
    archive_id: str
    archive_checksum: Checksum
    archive_path: ArchivePath
    manifest_checksum: Checksum

    @field_validator("archive_id")
    @classmethod
    def validate_archive_id(cls, value: str) -> str:
        if not _ARCHIVE_ID_PATTERN.fullmatch(value):
            raise ValueError("invalid archive_id")
        return value

    @model_validator(mode="after")
    def validate_archive_identity(self) -> "CourseArchiveManifestV1":
        payload = CourseArchivePayloadV1.model_validate(
            self.model_dump(
                mode="json",
                exclude={
                    "archive_id",
                    "archive_checksum",
                    "archive_path",
                    "manifest_checksum",
                },
            )
        )
        expected_checksum = calculate_archive_payload_checksum(payload)
        if self.archive_checksum != expected_checksum:
            raise ValueError("archive_checksum must cover the exact logical archive payload")
        if self.archive_id != archive_id_for_checksum(expected_checksum):
            raise ValueError("archive_id must derive from archive_checksum")
        if self.archive_path != archive_relative_path(
            self.course_id,
            self.release_id,
            self.archive_id,
        ):
            raise ValueError(
                "archive_path must derive from course_id, release_id and archive_id"
            )
        return self


class ContentAssetArchiveFileV1(ArchiveContractModel):
    path: ArchivePath
    kind: ContentAssetArchiveFileKind
    media_type: Literal["application/json"] = "application/json"
    size_bytes: int = Field(ge=1, le=MAX_ARCHIVE_FILE_BYTES)
    blob_sha256: Checksum
    schema_version: ArtifactSchemaVersion
    contract_checksum: Checksum

    @model_validator(mode="after")
    def validate_file(self) -> "ContentAssetArchiveFileV1":
        if not self.path.endswith(".json"):
            raise ValueError("content asset files must use the JSON extension")
        expected_kind = {
            "person-profile/v1": "sealed-person",
            "keyword-profile/v1": "sealed-keyword",
            "scenario-template/v1": "sealed-scenario",
        }.get(self.schema_version)
        if self.kind != expected_kind:
            raise ValueError(
                "content asset file kind must match its source schema"
            )
        return self


class ContentAssetArchivePayloadV1(ArchiveContractModel):
    schema_version: Literal["content-asset-archive/v1"] = (
        "content-asset-archive/v1"
    )
    asset_kind: ContentAssetKind
    asset_id: ContractId
    title: BoundedTitle
    version: int = Field(ge=1)
    source_schema_version: Literal[
        "person-profile/v1",
        "keyword-profile/v1",
        "scenario-template/v1",
    ]
    source_checksum: Checksum
    sealed_at: AwareDatetime
    sealed_by: BoundedActor
    files: tuple[ContentAssetArchiveFileV1, ...]
    file_count: int = Field(ge=1, le=MAX_ARCHIVE_FILES)
    total_size_bytes: int = Field(ge=1, le=MAX_ARCHIVE_TOTAL_BYTES)

    @model_validator(mode="after")
    def validate_payload(self) -> "ContentAssetArchivePayloadV1":
        expected_schema = {
            "person": "person-profile/v1",
            "keyword": "keyword-profile/v1",
            "scenario": "scenario-template/v1",
        }[self.asset_kind]
        if self.source_schema_version != expected_schema:
            raise ValueError("asset kind must match source_schema_version")
        if len(self.files) != 1 or self.file_count != 1:
            raise ValueError("a content asset archive requires exactly one source file")
        source = self.files[0]
        if (
            source.path
            != content_asset_archive_source_path(
                self.asset_kind,
                self.asset_id,
                self.title,
            )
            or source.schema_version != self.source_schema_version
            or source.contract_checksum != self.source_checksum
        ):
            raise ValueError(
                "content asset file identity must match the archive source"
            )
        if self.total_size_bytes != source.size_bytes:
            raise ValueError("total_size_bytes must equal the source file size")
        return self


class ContentAssetArchiveManifestV1(ContentAssetArchivePayloadV1):
    archive_id: str
    archive_checksum: Checksum
    archive_path: ArchivePath
    manifest_checksum: Checksum

    @field_validator("archive_id")
    @classmethod
    def validate_archive_id(cls, value: str) -> str:
        if not _ARCHIVE_ID_PATTERN.fullmatch(value):
            raise ValueError("invalid archive_id")
        return value

    @model_validator(mode="after")
    def validate_archive_identity(self) -> "ContentAssetArchiveManifestV1":
        payload = ContentAssetArchivePayloadV1.model_validate(
            self.model_dump(
                mode="json",
                exclude={
                    "archive_id",
                    "archive_checksum",
                    "archive_path",
                    "manifest_checksum",
                },
            )
        )
        expected_checksum = calculate_content_asset_archive_payload_checksum(
            payload
        )
        if self.archive_checksum != expected_checksum:
            raise ValueError(
                "archive_checksum must cover the exact asset archive payload"
            )
        if self.archive_id != archive_id_for_checksum(expected_checksum):
            raise ValueError("archive_id must derive from archive_checksum")
        if self.archive_path != content_asset_archive_relative_path(
            self.asset_kind,
            self.asset_id,
            self.version,
            self.archive_id,
        ):
            raise ValueError(
                "archive_path must derive from asset identity and archive_id"
            )
        return self


class GitRepositoryBindingV1(ArchiveContractModel):
    schema_version: Literal["git-repository-binding/v1"] = (
        "git-repository-binding/v1"
    )
    binding_id: ContractId
    provider: Literal["github"] = "github"
    repository_id: int = Field(ge=1)
    owner: str
    repository: str
    visibility: Literal["private"] = "private"
    base_branch: BranchName = "main"
    root_prefix: ArchivePath = DEFAULT_REPOSITORY_ROOT_PREFIX
    asset_root_prefix: ArchivePath | None = None
    credential_kind: CredentialKind = "github_app"
    installation_id: int | None = Field(default=None, ge=1)
    allowed_modes: tuple[PublicationMode, ...] = ("pull_request",)

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        if not _REPOSITORY_OWNER_PATTERN.fullmatch(value):
            raise ValueError("invalid GitHub repository owner")
        return value

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        if (
            not _REPOSITORY_NAME_PATTERN.fullmatch(value)
            or value in {".", ".."}
            or value.endswith((".", ".lock"))
        ):
            raise ValueError("invalid GitHub repository name")
        return value

    @model_validator(mode="after")
    def validate_binding(self) -> "GitRepositoryBindingV1":
        expected_modes = tuple(
            sorted(set(self.allowed_modes), key=_PUBLICATION_MODE_ORDER.__getitem__)
        )
        if self.allowed_modes != expected_modes or "pull_request" not in self.allowed_modes:
            raise ValueError(
                "allowed_modes must be unique, ordered and include pull_request"
            )
        if self.credential_kind == "github_app" and self.installation_id is None:
            raise ValueError("github_app bindings require installation_id")
        if self.credential_kind == "fine_grained_token" and self.installation_id is not None:
            raise ValueError(
                "fine_grained_token bindings cannot claim a GitHub App installation"
            )
        if self.asset_root_prefix is not None and (
            self.asset_root_prefix == self.root_prefix
            or self.asset_root_prefix.startswith(f"{self.root_prefix}/")
            or self.root_prefix.startswith(f"{self.asset_root_prefix}/")
        ):
            raise ValueError(
                "course and content asset roots must not overlap"
            )
        return self

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repository}"


class CourseArchivePublishRequestV1(ArchiveContractModel):
    schema_version: Literal["course-archive-publish-request/v1"] = (
        "course-archive-publish-request/v1"
    )
    binding_id: ContractId
    course_id: ContractId
    release_id: ReleaseId
    expected_release_checksum: Checksum
    archive_id: str
    expected_archive_checksum: Checksum
    mode: PublicationMode = "pull_request"
    client_request_id: ContractId
    change_summary: BoundedSummary = ""
    direct_commit_confirmed: bool = False

    @field_validator("archive_id")
    @classmethod
    def validate_archive_id(cls, value: str) -> str:
        if not _ARCHIVE_ID_PATTERN.fullmatch(value):
            raise ValueError("invalid archive_id")
        return value

    @model_validator(mode="after")
    def validate_request(self) -> "CourseArchivePublishRequestV1":
        if self.archive_id != archive_id_for_checksum(
            self.expected_archive_checksum
        ):
            raise ValueError("archive_id must derive from expected_archive_checksum")
        if self.mode == "direct_commit" and not self.direct_commit_confirmed:
            raise ValueError("direct_commit mode requires explicit confirmation")
        if self.mode == "pull_request" and self.direct_commit_confirmed:
            raise ValueError("pull_request mode cannot carry direct commit confirmation")
        return self


class ContentAssetArchivePublishRequestV1(ArchiveContractModel):
    schema_version: Literal["content-asset-archive-publish-request/v1"] = (
        "content-asset-archive-publish-request/v1"
    )
    binding_id: ContractId
    asset_kind: ContentAssetKind
    asset_id: ContractId
    version: int = Field(ge=1)
    expected_source_checksum: Checksum
    archive_id: str
    expected_archive_checksum: Checksum
    mode: PublicationMode = "pull_request"
    client_request_id: ContractId
    change_summary: BoundedSummary = ""
    direct_commit_confirmed: bool = False

    @field_validator("archive_id")
    @classmethod
    def validate_archive_id(cls, value: str) -> str:
        if not _ARCHIVE_ID_PATTERN.fullmatch(value):
            raise ValueError("invalid archive_id")
        return value

    @model_validator(mode="after")
    def validate_request(self) -> "ContentAssetArchivePublishRequestV1":
        if self.archive_id != archive_id_for_checksum(
            self.expected_archive_checksum
        ):
            raise ValueError("archive_id must derive from expected_archive_checksum")
        if self.mode == "direct_commit" and not self.direct_commit_confirmed:
            raise ValueError("direct_commit mode requires explicit confirmation")
        if self.mode == "pull_request" and self.direct_commit_confirmed:
            raise ValueError("pull_request mode cannot carry direct commit confirmation")
        return self


PublicationRequestV1 = Annotated[
    CourseArchivePublishRequestV1 | ContentAssetArchivePublishRequestV1,
    Field(discriminator="schema_version"),
]


class GitPublicationIntentV1(ArchiveContractModel):
    schema_version: Literal["git-publication-intent/v1"] = (
        "git-publication-intent/v1"
    )
    publication_id: str
    operation_key: Checksum
    binding: GitRepositoryBindingV1
    request: PublicationRequestV1
    requested_at: AwareDatetime
    requested_by: BoundedActor
    checksum: Checksum

    @field_validator("publication_id")
    @classmethod
    def validate_publication_id(cls, value: str) -> str:
        if not _PUBLICATION_ID_PATTERN.fullmatch(value):
            raise ValueError("invalid publication_id")
        return value

    @model_validator(mode="after")
    def validate_intent(self) -> "GitPublicationIntentV1":
        if self.binding.binding_id != self.request.binding_id:
            raise ValueError("request binding_id must match the resolved binding")
        if self.request.mode not in self.binding.allowed_modes:
            raise ValueError("requested publication mode is disabled by the binding")
        if (
            isinstance(self.request, ContentAssetArchivePublishRequestV1)
            and self.binding.asset_root_prefix is None
        ):
            raise ValueError(
                "content asset publication requires an asset root binding"
            )
        expected_key = publication_operation_key(self.binding, self.request)
        if self.operation_key != expected_key:
            raise ValueError("operation_key does not match the immutable publication input")
        if self.publication_id != publication_id_for_key(expected_key):
            raise ValueError("publication_id must derive from operation_key")
        return self


class GitPublicationRecordV1(ArchiveContractModel):
    schema_version: Literal["git-publication-record/v1"] = (
        "git-publication-record/v1"
    )
    intent: GitPublicationIntentV1
    status: PublicationStatus
    attempt: int = Field(ge=0)
    revision: int = Field(ge=0)
    branch_ref: BranchName
    base_sha: str | None = None
    tree_sha: str | None = None
    commit_sha: str | None = None
    pull_request_number: int | None = Field(default=None, ge=1)
    pull_request_url: str | None = Field(default=None, max_length=512)
    last_error_code: str | None = None
    last_error_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    checksum: Checksum

    @field_validator("base_sha", "tree_sha", "commit_sha")
    @classmethod
    def validate_git_object_id(cls, value: str | None) -> str | None:
        if value is not None and not _GIT_OBJECT_ID_PATTERN.fullmatch(value):
            raise ValueError("Git object ids must be lowercase 40-character SHA-1 values")
        return value

    @field_validator("pull_request_url")
    @classmethod
    def validate_pull_request_url(cls, value: str | None) -> str | None:
        if value is not None and not _PULL_REQUEST_URL_PATTERN.fullmatch(value):
            raise ValueError("pull_request_url must be an exact HTTPS GitHub URL")
        return value

    @field_validator("last_error_code")
    @classmethod
    def validate_error_code(cls, value: str | None) -> str | None:
        if value is not None and not _ERROR_CODE_PATTERN.fullmatch(value):
            raise ValueError("last_error_code must be a stable lowercase identifier")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "GitPublicationRecordV1":
        request = self.intent.request
        binding = self.intent.binding
        expected_branch = (
            publication_branch_name_for_request(request)
            if request.mode == "pull_request"
            else binding.base_branch
        )
        if self.branch_ref != expected_branch:
            raise ValueError("branch_ref must derive from publication mode and archive identity")
        if self.updated_at < self.intent.requested_at:
            raise ValueError("updated_at cannot precede requested_at")
        if self.last_error_at is not None and not (
            self.intent.requested_at <= self.last_error_at <= self.updated_at
        ):
            raise ValueError(
                "last_error_at must fall between requested_at and updated_at"
            )
        if self.completed_at is not None and not (
            self.intent.requested_at <= self.completed_at <= self.updated_at
        ):
            raise ValueError(
                "completed_at must fall between requested_at and updated_at"
            )

        if self.tree_sha is not None and self.base_sha is None:
            raise ValueError("tree_sha requires base_sha")
        if self.commit_sha is not None and (
            self.base_sha is None or self.tree_sha is None
        ):
            raise ValueError("commit_sha requires base_sha and tree_sha")
        pr_fields = (self.pull_request_number, self.pull_request_url)
        if (self.pull_request_number is None) != (self.pull_request_url is None):
            raise ValueError("pull request number and URL must be recorded together")
        if self.pull_request_number is not None and self.commit_sha is None:
            raise ValueError("pull request identity requires commit_sha")
        if request.mode == "direct_commit" and any(
            item is not None for item in pr_fields
        ):
            raise ValueError("direct commits cannot carry pull request identity")
        if self.pull_request_number is not None:
            expected_url = (
                f"https://github.com/{binding.full_name}/pull/"
                f"{self.pull_request_number}"
            )
            if self.pull_request_url != expected_url:
                raise ValueError(
                    "pull request URL must match the configured repository and number"
                )

        has_error = self.last_error_code is not None or self.last_error_at is not None
        if has_error and (
            self.last_error_code is None or self.last_error_at is None
        ):
            raise ValueError("publication errors require code and timestamp together")

        no_remote_fields = all(
            item is None
            for item in (
                self.base_sha,
                self.tree_sha,
                self.commit_sha,
                *pr_fields,
            )
        )
        complete_commit = all(
            item is not None for item in (self.base_sha, self.tree_sha, self.commit_sha)
        )
        has_pr = all(item is not None for item in pr_fields)

        if self.status == "requested":
            if self.revision != 0:
                raise ValueError("requested records must start at revision zero")
        elif self.attempt < 1 or self.revision < 1:
            raise ValueError(
                "publication processing states require a positive attempt and revision"
            )

        if self.status == "requested":
            if self.attempt != 0 or not no_remote_fields or has_error:
                raise ValueError("requested records must be pristine and unattempted")
        elif self.status == "preparing":
            if self.attempt < 1 or not no_remote_fields or has_error:
                raise ValueError("preparing records cannot contain remote Git state")
        elif self.status == "pushing":
            if (
                self.attempt < 1
                or self.base_sha is None
                or self.commit_sha is not None
                or has_pr
                or has_error
            ):
                raise ValueError("pushing records require only base/tree progress")
        elif self.status == "commit_created":
            if not complete_commit or has_pr or has_error:
                raise ValueError("commit_created records require an exact commit checkpoint")
        elif self.status == "ref_updated":
            if not complete_commit or has_pr or has_error:
                raise ValueError("ref_updated records require an exact ref checkpoint")
        elif self.status == "pr_open":
            if request.mode != "pull_request" or not complete_commit or not has_pr or has_error:
                raise ValueError("pr_open records require a complete pull request checkpoint")
        elif self.status == "succeeded":
            if (
                not complete_commit
                or has_error
                or self.completed_at is None
                or (request.mode == "pull_request" and not has_pr)
                or (request.mode == "direct_commit" and has_pr)
            ):
                raise ValueError("succeeded records require the terminal remote result")
        elif self.status == "failed_retryable":
            if self.attempt < 1 or not has_error or self.completed_at is not None:
                raise ValueError(
                    "retryable failures require an error and remain incomplete"
                )
        elif self.status == "failed_terminal":
            if self.attempt < 1 or not has_error or self.completed_at is None:
                raise ValueError(
                    "terminal failures require error and completion metadata"
                )

        if self.status not in {"succeeded", "failed_terminal"} and self.completed_at:
            raise ValueError("only terminal records can carry completed_at")
        if self.status not in {"failed_retryable", "failed_terminal"} and has_error:
            raise ValueError("only failed records can carry error metadata")
        return self


PublicationMetadataT = TypeVar(
    "PublicationMetadataT",
    GitPublicationIntentV1,
    GitPublicationRecordV1,
)


def archive_relative_path(
    course_id: str,
    release_id: str,
    archive_id: str,
) -> str:
    if not _ARCHIVE_ID_PATTERN.fullmatch(archive_id):
        raise ValueError("invalid archive_id")
    path = PurePosixPath(
        _contract_id(course_id),
        "releases",
        _validated_release_id(release_id),
        archive_id,
    ).as_posix()
    return _validated_archive_path(path)


def repository_archive_path(
    binding: GitRepositoryBindingV1,
    manifest: CourseArchiveManifestV1,
) -> str:
    return _validated_archive_path(
        PurePosixPath(binding.root_prefix, manifest.archive_path).as_posix()
    )


def content_asset_repository_archive_path(
    binding: GitRepositoryBindingV1,
    manifest: ContentAssetArchiveManifestV1,
) -> str:
    if binding.asset_root_prefix is None:
        raise ValueError("content asset repository root is not configured")
    return _validated_archive_path(
        PurePosixPath(
            binding.asset_root_prefix,
            manifest.archive_path,
        ).as_posix()
    )


def safe_archive_filename(title: str, fallback: str) -> str:
    checked_fallback = _contract_id(fallback)
    normalized = unicodedata.normalize("NFKC", title)
    normalized = re.sub(r"[<>:\"/\\|?*\x00-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    candidate = _truncate_portable_component(normalized, max_characters=80).rstrip(
        " ."
    ) or checked_fallback
    if (
        candidate.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES
        or candidate.casefold() == ".git"
    ):
        candidate = f"_{candidate}"
    return _validated_archive_path(candidate)


def content_asset_archive_source_path(
    asset_kind: ContentAssetKind,
    asset_id: str,
    title: str,
) -> str:
    checked_asset_id = _contract_id(asset_id)
    filename = safe_archive_filename(title, checked_asset_id)
    suffix = {
        "person": "人物档案",
        "keyword": "关键词档案",
        "scenario": "关卡规则",
    }[asset_kind]
    return _validated_archive_path(f"{filename}-{suffix}.json")


def content_asset_archive_relative_path(
    asset_kind: ContentAssetKind,
    asset_id: str,
    version: int,
    archive_id: str,
) -> str:
    if version < 1:
        raise ValueError("asset archive version must be at least 1")
    if not _ARCHIVE_ID_PATTERN.fullmatch(archive_id):
        raise ValueError("invalid archive_id")
    plural = {
        "person": "people",
        "keyword": "keywords",
        "scenario": "scenarios",
    }[asset_kind]
    return _validated_archive_path(
        PurePosixPath(
            plural,
            _contract_id(asset_id),
            "versions",
            f"v{version:03d}",
            archive_id,
        ).as_posix()
    )


def lesson_archive_paths(lesson_id: str, title: str) -> dict[str, str]:
    checked_lesson_id = _contract_id(lesson_id)
    filename = safe_archive_filename(title, checked_lesson_id)
    root = PurePosixPath("lessons", checked_lesson_id)
    paths = {
        "sealed-lesson": (root / f"{filename}.json").as_posix(),
        "course-package": (root / f"{filename}-运行包.json").as_posix(),
        "format-layer": (root / f"{filename}-格式层.json").as_posix(),
        "teacher-markdown": (root / f"{filename}-教师稿.md").as_posix(),
        "preview-html": (root / f"{filename}-预览.html").as_posix(),
    }
    return {kind: _validated_archive_path(path) for kind, path in paths.items()}


def scenario_archive_path(
    lesson_id: str,
    scenario_id: str,
    scenario_version: int,
) -> str:
    checked_lesson_id = _contract_id(lesson_id)
    checked_scenario_id = _contract_id(scenario_id)
    if scenario_version < 1:
        raise ValueError("scenario_version must be at least 1")
    return _validated_archive_path(
        PurePosixPath(
            "lessons",
            checked_lesson_id,
            "scenarios",
            f"{checked_scenario_id}-v{scenario_version:03d}.json",
        ).as_posix()
    )


def supplement_archive_path(
    lesson_id: str,
    kind: Literal["evidence-corpus", "lesson-presentation"],
    artifact_id: str,
    version: int,
) -> str:
    checked_lesson_id = _contract_id(lesson_id)
    checked_artifact_id = _contract_id(artifact_id)
    if version < 1:
        raise ValueError("supplement version must be at least 1")
    segment = {
        "evidence-corpus": "evidence",
        "lesson-presentation": "presentation",
    }[kind]
    return _validated_archive_path(
        PurePosixPath(
            "lessons",
            checked_lesson_id,
            segment,
            f"{checked_artifact_id}-v{version:03d}.json",
        ).as_posix()
    )


def calculate_archive_payload_checksum(payload: CourseArchivePayloadV1) -> str:
    return _canonical_checksum(payload.model_dump(mode="json"))


def calculate_content_asset_archive_payload_checksum(
    payload: ContentAssetArchivePayloadV1,
) -> str:
    return _canonical_checksum(payload.model_dump(mode="json"))


def archive_id_for_checksum(archive_checksum: str) -> str:
    checksum = _checksum(archive_checksum)
    return f"arc-{checksum[:32]}"


def calculate_archive_manifest_checksum(
    manifest: CourseArchiveManifestV1,
) -> str:
    data = manifest.model_dump(mode="json")
    data["manifest_checksum"] = None
    return _canonical_checksum(data)


def sign_archive_manifest(
    manifest: CourseArchiveManifestV1,
) -> CourseArchiveManifestV1:
    data = manifest.model_dump(mode="json")
    data["manifest_checksum"] = calculate_archive_manifest_checksum(manifest)
    return CourseArchiveManifestV1.model_validate(data)


def parse_signed_archive_manifest(payload: object) -> CourseArchiveManifestV1:
    manifest = CourseArchiveManifestV1.model_validate(payload)
    if not verify_archive_manifest_checksum(manifest):
        raise ValueError("archive manifest checksum mismatch")
    return manifest


def verify_archive_manifest_checksum(manifest: CourseArchiveManifestV1) -> bool:
    return (
        manifest.archive_checksum
        == calculate_archive_payload_checksum(
            CourseArchivePayloadV1.model_validate(
                manifest.model_dump(
                    mode="json",
                    exclude={
                        "archive_id",
                        "archive_checksum",
                        "archive_path",
                        "manifest_checksum",
                    },
                )
            )
        )
        and manifest.manifest_checksum
        == calculate_archive_manifest_checksum(manifest)
    )


def calculate_content_asset_archive_manifest_checksum(
    manifest: ContentAssetArchiveManifestV1,
) -> str:
    data = manifest.model_dump(mode="json")
    data["manifest_checksum"] = None
    return _canonical_checksum(data)


def sign_content_asset_archive_manifest(
    manifest: ContentAssetArchiveManifestV1,
) -> ContentAssetArchiveManifestV1:
    data = manifest.model_dump(mode="json")
    data["manifest_checksum"] = (
        calculate_content_asset_archive_manifest_checksum(manifest)
    )
    return ContentAssetArchiveManifestV1.model_validate(data)


def parse_signed_content_asset_archive_manifest(
    payload: object,
) -> ContentAssetArchiveManifestV1:
    manifest = ContentAssetArchiveManifestV1.model_validate(payload)
    if not verify_content_asset_archive_manifest_checksum(manifest):
        raise ValueError("content asset archive manifest checksum mismatch")
    return manifest


def verify_content_asset_archive_manifest_checksum(
    manifest: ContentAssetArchiveManifestV1,
) -> bool:
    payload = ContentAssetArchivePayloadV1.model_validate(
        manifest.model_dump(
            mode="json",
            exclude={
                "archive_id",
                "archive_checksum",
                "archive_path",
                "manifest_checksum",
            },
        )
    )
    return (
        manifest.archive_checksum
        == calculate_content_asset_archive_payload_checksum(payload)
        and manifest.manifest_checksum
        == calculate_content_asset_archive_manifest_checksum(manifest)
    )


def publication_branch_name(
    course_id: str,
    release_id: str,
    archive_checksum: str,
) -> str:
    return _validated_branch_name(
        "chronovita/"
        f"{_contract_id(course_id)}/"
        f"{_validated_release_id(release_id)}-{_checksum(archive_checksum)[:12]}"
    )


def asset_publication_branch_name(
    asset_kind: ContentAssetKind,
    asset_id: str,
    version: int,
    archive_checksum: str,
) -> str:
    if version < 1:
        raise ValueError("asset version must be at least 1")
    return _validated_branch_name(
        "chronovita/assets/"
        f"{asset_kind}/"
        f"{_contract_id(asset_id)}-v{version:03d}-"
        f"{_checksum(archive_checksum)[:12]}"
    )


def publication_branch_name_for_request(
    request: PublicationRequestV1,
) -> str:
    if isinstance(request, CourseArchivePublishRequestV1):
        return publication_branch_name(
            request.course_id,
            request.release_id,
            request.expected_archive_checksum,
        )
    return asset_publication_branch_name(
        request.asset_kind,
        request.asset_id,
        request.version,
        request.expected_archive_checksum,
    )


def publication_operation_key(
    binding: GitRepositoryBindingV1,
    request: PublicationRequestV1,
) -> str:
    if binding.binding_id != request.binding_id:
        raise ValueError("request binding_id does not match binding")
    if request.mode not in binding.allowed_modes:
        raise ValueError("publication mode is disabled by binding")
    if isinstance(request, CourseArchivePublishRequestV1):
        identity = {
            "archive_checksum": request.expected_archive_checksum,
            "base_branch": binding.base_branch,
            "binding_id": binding.binding_id,
            "course_id": request.course_id,
            "mode": request.mode,
            "release_checksum": request.expected_release_checksum,
            "release_id": request.release_id,
            "repository_id": binding.repository_id,
            "root_prefix": binding.root_prefix,
        }
    else:
        identity = {
            "archive_checksum": request.expected_archive_checksum,
            "asset_id": request.asset_id,
            "asset_kind": request.asset_kind,
            "asset_version": request.version,
            "base_branch": binding.base_branch,
            "binding_id": binding.binding_id,
            "mode": request.mode,
            "repository_id": binding.repository_id,
            "root_prefix": binding.asset_root_prefix,
            "source_checksum": request.expected_source_checksum,
        }
    return _canonical_checksum(identity)


def publication_id_for_key(operation_key: str) -> str:
    checksum = _checksum(operation_key)
    return f"pub-{checksum[:32]}"


def calculate_publication_metadata_checksum(payload: BaseModel) -> str:
    data = payload.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("publication metadata does not expose checksum")
    data["checksum"] = None
    if isinstance(payload, GitPublicationIntentV1):
        _omit_legacy_asset_root(data["binding"])
    elif isinstance(payload, GitPublicationRecordV1):
        _omit_legacy_asset_root(data["intent"]["binding"])
    return _canonical_checksum(data)


def _omit_legacy_asset_root(binding: dict[str, object]) -> None:
    if binding.get("asset_root_prefix") is None:
        binding.pop("asset_root_prefix", None)


def sign_publication_metadata(
    payload: PublicationMetadataT,
) -> PublicationMetadataT:
    data = payload.model_dump(mode="json")
    data["checksum"] = calculate_publication_metadata_checksum(payload)
    return type(payload).model_validate(data)


def parse_signed_publication_intent(payload: object) -> GitPublicationIntentV1:
    intent = GitPublicationIntentV1.model_validate(payload)
    if not verify_publication_metadata_checksum(intent):
        raise ValueError("publication intent checksum mismatch")
    return intent


def parse_signed_publication_record(payload: object) -> GitPublicationRecordV1:
    record = GitPublicationRecordV1.model_validate(payload)
    if not verify_publication_metadata_checksum(record.intent):
        raise ValueError("publication record contains an invalid intent checksum")
    if not verify_publication_metadata_checksum(record):
        raise ValueError("publication record checksum mismatch")
    return record


def verify_publication_metadata_checksum(payload: BaseModel) -> bool:
    checksum = getattr(payload, "checksum", None)
    return (
        isinstance(checksum, str)
        and checksum == calculate_publication_metadata_checksum(payload)
    )


def schema_document(
    model: type[BaseModel],
    schema_id: str,
    comment: str,
) -> dict:
    generated = model.model_json_schema(ref_template="#/$defs/{model}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "$comment": comment,
        **generated,
    }


ARCHIVE_SCHEMA_DOCUMENTS = {
    "course-archive-manifest.schema.json": (
        CourseArchiveManifestV1,
        "https://chronovita.local/schemas/archive/v1/course-archive-manifest.schema.json",
        (
            "Pydantic semantic validation additionally enforces exact release identity, "
            "renderer identity, portable NFKC paths, file-size totals, source contract "
            "checksums and lesson/scenario cross-references. files excludes the "
            "self-referential archive manifest."
        ),
    ),
    "git-repository-binding.schema.json": (
        GitRepositoryBindingV1,
        "https://chronovita.local/schemas/archive/v1/git-repository-binding.schema.json",
        (
            "Bindings are immutable server configuration. Credentials, private keys and "
            "browser-provided repository overrides are intentionally absent."
        ),
    ),
    "course-archive-publish-request.schema.json": (
        CourseArchivePublishRequestV1,
        "https://chronovita.local/schemas/archive/v1/course-archive-publish-request.schema.json",
        (
            "Clients select a server binding_id and immutable archive identity only. Pull "
            "request mode is the default; direct commit requires explicit confirmation."
        ),
    ),
    "content-asset-archive-manifest.schema.json": (
        ContentAssetArchiveManifestV1,
        "https://chronovita.local/schemas/archive/v1/content-asset-archive-manifest.schema.json",
        (
            "A person, keyword or scenario archive contains one exact immutable "
            "JSON source plus signed identity, size and checksum metadata."
        ),
    ),
    "content-asset-archive-publish-request.schema.json": (
        ContentAssetArchivePublishRequestV1,
        "https://chronovita.local/schemas/archive/v1/content-asset-archive-publish-request.schema.json",
        (
            "Clients select one exact sealed content asset and a server-side "
            "repository binding. Pull requests remain the default."
        ),
    ),
    "git-publication-intent.schema.json": (
        GitPublicationIntentV1,
        "https://chronovita.local/schemas/archive/v1/git-publication-intent.schema.json",
        (
            "The operation key provides idempotency for one binding, release, archive and "
            "mode. Client request IDs and human summaries do not change that identity."
        ),
    ),
    "git-publication-record.schema.json": (
        GitPublicationRecordV1,
        "https://chronovita.local/schemas/archive/v1/git-publication-record.schema.json",
        (
            "Publication checkpoints preserve partial Git success for reconciliation. "
            "Records contain stable identifiers and error codes, never provider response "
            "bodies or credentials."
        ),
    ),
}


def _contract_id(value: str) -> str:
    from pydantic import TypeAdapter

    return TypeAdapter(ContractId).validate_python(value)


def _checksum(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("value must be a lowercase SHA-256 checksum")
    return value


def _canonical_checksum(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _truncate_portable_component(
    value: str,
    *,
    max_characters: int,
    max_utf8_bytes: int = 180,
    max_utf16_units: int = 80,
) -> str:
    result: list[str] = []
    utf8_bytes = 0
    utf16_units = 0
    for char in value:
        char_utf8_bytes = len(char.encode("utf-8"))
        char_utf16_units = len(char.encode("utf-16-le")) // 2
        if (
            len(result) >= max_characters
            or utf8_bytes + char_utf8_bytes > max_utf8_bytes
            or utf16_units + char_utf16_units > max_utf16_units
        ):
            break
        result.append(char)
        utf8_bytes += char_utf8_bytes
        utf16_units += char_utf16_units
    return "".join(result)


__all__ = [
    "ASSET_ARCHIVE_MANIFEST_FILENAME",
    "ARCHIVE_MANIFEST_FILENAME",
    "ARCHIVE_RELEASE_MANIFEST_FILENAME",
    "ARCHIVE_SCHEMA_DOCUMENTS",
    "DEFAULT_ASSET_REPOSITORY_ROOT_PREFIX",
    "DEFAULT_REPOSITORY_ROOT_PREFIX",
    "MAX_ARCHIVE_FILE_BYTES",
    "MAX_ARCHIVE_FILES",
    "MAX_ARCHIVE_TOTAL_BYTES",
    "ArchiveRendererV1",
    "ContentAssetArchiveFileV1",
    "ContentAssetArchiveManifestV1",
    "ContentAssetArchivePayloadV1",
    "ContentAssetArchivePublishRequestV1",
    "ContentAssetKind",
    "CourseArchiveFileV1",
    "CourseArchiveLessonV1",
    "CourseArchiveManifestV1",
    "CourseArchivePayloadV1",
    "CourseArchivePublishRequestV1",
    "CourseArchiveScenarioV1",
    "GitPublicationIntentV1",
    "GitPublicationRecordV1",
    "GitRepositoryBindingV1",
    "PublicationRequestV1",
    "asset_publication_branch_name",
    "archive_id_for_checksum",
    "archive_relative_path",
    "calculate_archive_manifest_checksum",
    "calculate_archive_payload_checksum",
    "calculate_content_asset_archive_manifest_checksum",
    "calculate_content_asset_archive_payload_checksum",
    "calculate_publication_metadata_checksum",
    "content_asset_archive_relative_path",
    "content_asset_archive_source_path",
    "content_asset_repository_archive_path",
    "lesson_archive_paths",
    "parse_signed_content_asset_archive_manifest",
    "parse_signed_archive_manifest",
    "parse_signed_publication_intent",
    "parse_signed_publication_record",
    "publication_branch_name",
    "publication_branch_name_for_request",
    "publication_id_for_key",
    "publication_operation_key",
    "repository_archive_path",
    "safe_archive_filename",
    "scenario_archive_path",
    "supplement_archive_path",
    "schema_document",
    "sign_archive_manifest",
    "sign_content_asset_archive_manifest",
    "sign_publication_metadata",
    "verify_archive_manifest_checksum",
    "verify_content_asset_archive_manifest_checksum",
    "verify_publication_metadata_checksum",
]
