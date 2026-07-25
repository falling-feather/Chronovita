from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId, NonEmptyText


ReleaseOperation = Literal["bootstrap", "publish", "rollback"]
ArtifactKind = Literal["course-package", "scenario-template"]
ArtifactSchema = Literal["course-package/v1", "scenario-template/v1"]
_RELEASE_ID_PATTERN = re.compile(r"^rel-[0-9a-f]{10}-\d{4,}$")
_PATH_TEXT = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class ReleaseContractModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class CourseReleaseItemV1(ReleaseContractModel):
    """Frozen reader for course-release/v1 manifests already on disk."""

    lesson_id: ContractId
    course_id: ContractId
    content_version: int = Field(ge=1)
    source_path: NonEmptyText
    source_checksum: Checksum
    package_path: NonEmptyText
    package_checksum: Checksum
    package_schema: Literal["course-package/v1"] = "course-package/v1"


class CourseReleaseManifestV1(ReleaseContractModel):
    """Exact compatibility model for the BE-001 course-only manifest."""

    schema_version: Literal["course-release/v1"] = "course-release/v1"
    release_id: NonEmptyText
    release_no: int = Field(ge=1)
    course_id: ContractId
    operation: ReleaseOperation
    parent_release_id: str | None = None
    restored_from_release_id: str | None = None
    created_at: AwareDatetime
    created_by: NonEmptyText
    note: str = ""
    items: tuple[CourseReleaseItemV1, ...] = ()
    checksum: Checksum

    @model_validator(mode="after")
    def validate_manifest(self) -> "CourseReleaseManifestV1":
        _validate_manifest_identity(self)
        lesson_ids = [item.lesson_id for item in self.items]
        if lesson_ids != sorted(set(lesson_ids)):
            raise ValueError("release items must be unique and sorted by lesson_id")
        if any(item.course_id != self.course_id for item in self.items):
            raise ValueError("every release item must belong to manifest.course_id")
        return self


def runtime_artifact_path(
    *,
    kind: ArtifactKind,
    artifact_id: str,
    course_id: str,
    lesson_id: str,
    version: int,
    checksum: str,
) -> str:
    """Return the only canonical path accepted by a V2 runtime descriptor."""

    artifact_id = _contract_id(artifact_id)
    course_id = _contract_id(course_id)
    lesson_id = _contract_id(lesson_id)
    if version < 1:
        raise ValueError("runtime artifact version must be at least 1")
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("runtime artifact checksum must be lowercase SHA-256")
    filename = f"v{version:03d}-{checksum}.json"
    if kind == "course-package":
        return PurePosixPath(
            "runtime",
            "v1",
            "course-packages",
            course_id,
            lesson_id,
            filename,
        ).as_posix()
    if kind == "scenario-template":
        return PurePosixPath(
            "runtime",
            "v1",
            "scenarios",
            course_id,
            lesson_id,
            artifact_id,
            filename,
        ).as_posix()
    raise ValueError(f"unsupported runtime artifact kind: {kind}")


class RuntimeArtifactDescriptorV1(ReleaseContractModel):
    kind: ArtifactKind
    schema_version: ArtifactSchema
    artifact_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    version: int = Field(ge=1)
    checksum: Checksum
    path: _PATH_TEXT

    @model_validator(mode="after")
    def validate_descriptor(self) -> "RuntimeArtifactDescriptorV1":
        expected_schema = {
            "course-package": "course-package/v1",
            "scenario-template": "scenario-template/v1",
        }[self.kind]
        if self.schema_version != expected_schema:
            raise ValueError(
                f"{self.kind} descriptors require schema_version={expected_schema}"
            )
        expected_path = runtime_artifact_path(
            kind=self.kind,
            artifact_id=self.artifact_id,
            course_id=self.course_id,
            lesson_id=self.lesson_id,
            version=self.version,
            checksum=self.checksum,
        )
        if self.path != expected_path:
            raise ValueError(
                f"runtime artifact path must be canonical and content-addressed: {expected_path}"
            )
        return self


class CourseReleaseItemV2(ReleaseContractModel):
    lesson_id: ContractId
    course_id: ContractId
    content_version: int = Field(ge=1)
    source_path: _PATH_TEXT
    source_checksum: Checksum
    course_package: RuntimeArtifactDescriptorV1
    scenarios: tuple[RuntimeArtifactDescriptorV1, ...] = ()
    primary_scenario_id: ContractId | None = None
    audience: Literal["published"] = "published"

    @model_validator(mode="after")
    def validate_runtime_binding(self) -> "CourseReleaseItemV2":
        expected_source = f"sealed/{self.lesson_id}-v{self.content_version:03d}.json"
        if self.source_path != expected_source:
            raise ValueError(f"source_path must be canonical: {expected_source}")
        course = self.course_package
        if course.kind != "course-package":
            raise ValueError("course_package must use a course-package descriptor")
        if (
            course.course_id,
            course.lesson_id,
            course.version,
        ) != (self.course_id, self.lesson_id, self.content_version):
            raise ValueError("course package descriptor identity must match release item")

        scenario_ids = [item.artifact_id for item in self.scenarios]
        if scenario_ids != sorted(set(scenario_ids)):
            raise ValueError("scenario descriptors must be unique and sorted by artifact_id")
        if any(item.kind != "scenario-template" for item in self.scenarios):
            raise ValueError("scenarios must use scenario-template descriptors")
        if any(
            (item.course_id, item.lesson_id) != (self.course_id, self.lesson_id)
            for item in self.scenarios
        ):
            raise ValueError("scenario descriptor identity must match release item")
        if self.scenarios and self.primary_scenario_id not in set(scenario_ids):
            raise ValueError("a release item with scenarios requires one primary scenario")
        if not self.scenarios and self.primary_scenario_id is not None:
            raise ValueError("primary_scenario_id requires at least one scenario")
        return self


class CourseReleaseManifestV2(ReleaseContractModel):
    schema_version: Literal["course-release/v2"] = "course-release/v2"
    release_id: NonEmptyText
    release_no: int = Field(ge=1)
    course_id: ContractId
    operation: ReleaseOperation
    parent_release_id: str | None = None
    restored_from_release_id: str | None = None
    created_at: AwareDatetime
    created_by: NonEmptyText
    note: str = ""
    items: tuple[CourseReleaseItemV2, ...] = ()
    checksum: Checksum

    @model_validator(mode="after")
    def validate_manifest(self) -> "CourseReleaseManifestV2":
        _validate_manifest_identity(self)
        lesson_ids = [item.lesson_id for item in self.items]
        if lesson_ids != sorted(set(lesson_ids)):
            raise ValueError("release items must be unique and sorted by lesson_id")
        if any(item.course_id != self.course_id for item in self.items):
            raise ValueError("every release item must belong to manifest.course_id")

        descriptors = [
            descriptor
            for item in self.items
            for descriptor in (item.course_package, *item.scenarios)
        ]
        paths = [descriptor.path for descriptor in descriptors]
        if len(paths) != len(set(path.casefold() for path in paths)):
            raise ValueError("runtime artifact paths must be unique within a release")
        scenario_ids = [
            scenario.artifact_id
            for item in self.items
            for scenario in item.scenarios
        ]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario_id must be unique within a course release")
        return self


class ActiveReleasePointerV1(ReleaseContractModel):
    """The V1 pointer remains the single commit point for V1 and V2 manifests."""

    schema_version: Literal["course-release-pointer/v1"] = (
        "course-release-pointer/v1"
    )
    course_id: ContractId
    release_id: NonEmptyText
    release_no: int = Field(ge=1)
    manifest_path: _PATH_TEXT
    manifest_checksum: Checksum
    generation: int = Field(ge=1)
    previous_release_id: str | None = None
    activated_at: AwareDatetime
    activated_by: NonEmptyText
    checksum: Checksum

    @model_validator(mode="after")
    def validate_pointer(self) -> "ActiveReleasePointerV1":
        if not _RELEASE_ID_PATTERN.fullmatch(self.release_id):
            raise ValueError("invalid release_id")
        if int(self.release_id.rsplit("-", 1)[1]) != self.release_no:
            raise ValueError("release_id sequence must match release_no")
        expected_path = (
            PurePosixPath(
                "releases",
                "manifests",
                self.course_id,
                f"{self.release_id}.json",
            ).as_posix()
        )
        if self.manifest_path != expected_path:
            raise ValueError(f"manifest_path must be canonical: {expected_path}")
        if self.generation == 1 and self.previous_release_id is not None:
            raise ValueError("first pointer generation cannot have a previous release")
        if self.generation > 1 and self.previous_release_id is None:
            raise ValueError("later pointer generations require a previous release")
        return self


CourseReleaseManifestAny = Annotated[
    CourseReleaseManifestV1 | CourseReleaseManifestV2,
    Field(discriminator="schema_version"),
]
COURSE_RELEASE_MANIFEST_ADAPTER = TypeAdapter(CourseReleaseManifestAny)
ReleaseMetadataT = TypeVar("ReleaseMetadataT", bound=ReleaseContractModel)


def parse_course_release_manifest(payload: object) -> CourseReleaseManifestAny:
    return COURSE_RELEASE_MANIFEST_ADAPTER.validate_python(payload)


def parse_signed_course_release_manifest(payload: object) -> CourseReleaseManifestAny:
    manifest = parse_course_release_manifest(payload)
    if not verify_release_metadata_checksum(manifest):
        raise ValueError("course release manifest checksum mismatch")
    return manifest


def calculate_release_metadata_checksum(payload: BaseModel) -> str:
    data = payload.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("release metadata does not expose checksum")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sign_release_metadata(payload: ReleaseMetadataT) -> ReleaseMetadataT:
    data = payload.model_dump(mode="json")
    data["checksum"] = calculate_release_metadata_checksum(payload)
    return type(payload).model_validate(data)


def verify_release_metadata_checksum(payload: BaseModel) -> bool:
    checksum = getattr(payload, "checksum", None)
    return isinstance(checksum, str) and checksum == calculate_release_metadata_checksum(
        payload
    )


def release_schema_document() -> dict:
    generated = CourseReleaseManifestV2.model_json_schema(
        ref_template="#/$defs/{model}"
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://chronovita.local/schemas/releases/v2/course-release-manifest.schema.json",
        "$comment": (
            "Pydantic semantic validation additionally enforces content-addressed paths, "
            "cross-descriptor identities, ordering, primary scenario membership and release lineage."
        ),
        **generated,
    }


RELEASE_SCHEMA_DOCUMENTS = {
    "course-release-manifest.schema.json": release_schema_document,
}


def _validate_manifest_identity(
    manifest: CourseReleaseManifestV1 | CourseReleaseManifestV2,
) -> None:
    if not _RELEASE_ID_PATTERN.fullmatch(manifest.release_id):
        raise ValueError("invalid release_id")
    if int(manifest.release_id.rsplit("-", 1)[1]) != manifest.release_no:
        raise ValueError("release_id sequence must match release_no")
    for related_id in (manifest.parent_release_id, manifest.restored_from_release_id):
        if related_id is not None and not _RELEASE_ID_PATTERN.fullmatch(related_id):
            raise ValueError("release lineage contains an invalid release_id")
    if manifest.operation == "bootstrap" and manifest.parent_release_id is not None:
        raise ValueError("bootstrap releases cannot have a parent")
    if manifest.operation == "publish" and manifest.parent_release_id is None:
        raise ValueError("publish releases require a parent")
    if manifest.operation == "rollback" and manifest.parent_release_id is None:
        raise ValueError("rollback releases require a parent")
    if manifest.operation == "rollback" and manifest.restored_from_release_id is None:
        raise ValueError("rollback releases require restored_from_release_id")
    if manifest.operation != "rollback" and manifest.restored_from_release_id is not None:
        raise ValueError("only rollback releases may restore another release")


def _contract_id(value: str) -> str:
    return TypeAdapter(ContractId).validate_python(value)


__all__ = [
    "ActiveReleasePointerV1",
    "ArtifactKind",
    "COURSE_RELEASE_MANIFEST_ADAPTER",
    "CourseReleaseItemV1",
    "CourseReleaseItemV2",
    "CourseReleaseManifestAny",
    "CourseReleaseManifestV1",
    "CourseReleaseManifestV2",
    "RELEASE_SCHEMA_DOCUMENTS",
    "RuntimeArtifactDescriptorV1",
    "calculate_release_metadata_checksum",
    "parse_course_release_manifest",
    "parse_signed_course_release_manifest",
    "release_schema_document",
    "runtime_artifact_path",
    "sign_release_metadata",
    "verify_release_metadata_checksum",
]
