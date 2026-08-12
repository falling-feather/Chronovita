from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    model_validator,
)

from services import content as content_data
from services.content import runtime_artifacts
from services.contracts.release_v2 import (
    ActiveReleasePointerV1,
    CourseReleaseItemV2,
    CourseReleaseItemV3,
    CourseReleaseManifestAny,
    CourseReleaseManifestV2,
    CourseReleaseManifestV3,
    RuntimeArtifactDescriptorV1,
    parse_signed_course_release_manifest,
    verify_release_metadata_checksum,
)
from services.contracts.v1 import (
    Checksum,
    ContractId,
    RuntimeBundleV1,
)
from services.game_runtime import (
    ScenarioFileError,
    ScenarioIntegrityError,
    SituationEngineV1,
    load_contract_file,
)


class ScenarioCatalogEntryV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    scenario_id: ContractId
    scenario_version: int = Field(ge=1)
    scenario_checksum: Checksum
    course_id: ContractId
    lesson_id: ContractId
    course_content_version: int = Field(ge=1)
    course_checksum: Checksum
    course_path: str
    scenario_path: str
    active: bool = True
    audience: Literal["development", "published"] = "development"

    @model_validator(mode="after")
    def validate_paths(self) -> "ScenarioCatalogEntryV1":
        _validate_relative_json_path(self.course_path, "course_path")
        _validate_relative_json_path(self.scenario_path, "scenario_path")
        if _path_key(self.course_path) == _path_key(self.scenario_path):
            raise ValueError("course_path and scenario_path must be different")
        return self


class ScenarioCatalogV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["scenario-catalog/v1"] = "scenario-catalog/v1"
    entries: list[ScenarioCatalogEntryV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entries(self) -> "ScenarioCatalogV1":
        if any(entry.audience != "development" for entry in self.entries):
            raise ValueError(
                "static scenario catalog entries must use audience=development"
            )
        identities: set[tuple[str, int]] = set()
        course_paths: dict[str, tuple[str, str, int, str]] = {}
        scenario_paths: set[str] = set()
        active_ids: set[str] = set()
        for entry in self.entries:
            identity = (entry.scenario_id, entry.scenario_version)
            if identity in identities:
                raise ValueError(
                    f"duplicate scenario catalog identity: {entry.scenario_id} v{entry.scenario_version}"
                )
            identities.add(identity)
            course_path = _path_key(entry.course_path)
            scenario_path = _path_key(entry.scenario_path)
            course_identity = (
                entry.course_id,
                entry.lesson_id,
                entry.course_content_version,
                entry.course_checksum,
            )
            existing_course = course_paths.get(course_path)
            if existing_course is not None and existing_course != course_identity:
                raise ValueError(
                    f"course path is pinned to different course identities: {entry.course_path}"
                )
            if course_path in scenario_paths or scenario_path in course_paths:
                raise ValueError("course and scenario artifact paths cannot overlap")
            if scenario_path in scenario_paths:
                raise ValueError(
                    f"scenario catalog path is reused: {entry.scenario_path}"
                )
            course_paths[course_path] = course_identity
            scenario_paths.add(scenario_path)
            if entry.active:
                if entry.scenario_id in active_ids:
                    raise ValueError(
                        f"scenario catalog has multiple active versions: {entry.scenario_id}"
                    )
                active_ids.add(entry.scenario_id)
        return self


class ScenarioCatalogNotFound(ScenarioFileError):
    code = "scenario_catalog_not_found"


@dataclass(frozen=True)
class LoadedScenarioV1:
    entry: ScenarioCatalogEntryV1
    engine: SituationEngineV1
    release_id: str | None = None
    release_no: int | None = None
    release_checksum: str | None = None

    def __post_init__(self) -> None:
        release_identity = (
            self.release_id,
            self.release_no,
            self.release_checksum,
        )
        if self.entry.audience == "published" and any(
            item is None for item in release_identity
        ):
            raise ValueError("published scenarios require a complete release identity")
        if self.entry.audience == "development" and any(
            item is not None for item in release_identity
        ):
            raise ValueError("development scenarios cannot carry a release identity")


@dataclass(frozen=True)
class _CapturedReleaseV1:
    pointer: ActiveReleasePointerV1
    manifest: CourseReleaseManifestAny


class _ReleaseManifestDocument(RootModel[dict[str, object]]):
    pass


class ScenarioCatalogRepository:
    """Loads only explicitly allowlisted and checksum-pinned runtime artifacts."""

    def __init__(
        self,
        *,
        content_root: str | Path,
        catalog_path: str | Path,
    ) -> None:
        self.content_root = _resolve_path(Path(content_root), "content_root")
        requested_catalog = Path(catalog_path)
        self.catalog_path = Path(
            os.path.abspath(
                requested_catalog
                if requested_catalog.is_absolute()
                else self.content_root / requested_catalog
            )
        )
        _require_inside(
            _resolve_path(self.catalog_path, "catalog_path"),
            self.content_root,
            "catalog_path",
        )

    def load_catalog(self) -> ScenarioCatalogV1:
        return load_contract_file(self.catalog_path, ScenarioCatalogV1)

    def list_active(self) -> tuple[SituationEngineV1, ...]:
        return tuple(item.engine for item in self.list_active_records())

    def list_active_records(self) -> tuple[LoadedScenarioV1, ...]:
        catalog = self.load_catalog()
        static_records = tuple(
            LoadedScenarioV1(entry=entry, engine=self._load_entry(entry))
            for entry in catalog.entries
            if entry.active
        )
        published_records = tuple(
            record
            for captured in self._capture_active_releases()
            if isinstance(
                captured.manifest,
                (CourseReleaseManifestV2, CourseReleaseManifestV3),
            )
            for record in self._load_release_records(captured.manifest)
        )
        records = self._merge_active_records(static_records, published_records)
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.entry.course_id,
                    item.entry.lesson_id,
                    item.entry.scenario_id,
                ),
            )
        )

    def get_active(self, scenario_id: str) -> SituationEngineV1:
        return self.get_active_record(scenario_id).engine

    def get_active_record(self, scenario_id: str) -> LoadedScenarioV1:
        record = next(
            (
                item
                for item in self.list_active_records()
                if item.entry.scenario_id == scenario_id
            ),
            None,
        )
        if record is None:
            raise ScenarioCatalogNotFound(f"active scenario not found: {scenario_id}")
        return record

    def get_exact(
        self,
        scenario_id: str,
        scenario_version: int,
        scenario_checksum: str,
        *,
        course_id: str | None = None,
        lesson_id: str | None = None,
        course_content_version: int | None = None,
        course_checksum: str | None = None,
    ) -> SituationEngineV1:
        catalog = self.load_catalog()
        matches = [
            LoadedScenarioV1(entry=entry, engine=self._load_entry(entry))
            for entry in catalog.entries
            if _matches_exact_identity(
                entry,
                scenario_id=scenario_id,
                scenario_version=scenario_version,
                scenario_checksum=scenario_checksum,
                course_id=course_id,
                lesson_id=lesson_id,
                course_content_version=course_content_version,
                course_checksum=course_checksum,
            )
        ]

        captured_releases = self._capture_active_releases(course_id=course_id)
        for manifest in self._reachable_release_history(captured_releases):
            if not isinstance(
                manifest,
                (CourseReleaseManifestV2, CourseReleaseManifestV3),
            ):
                continue
            for item in manifest.items:
                for descriptor in item.scenarios:
                    entry = self._release_entry(item, descriptor)
                    if not _matches_exact_identity(
                        entry,
                        scenario_id=scenario_id,
                        scenario_version=scenario_version,
                        scenario_checksum=scenario_checksum,
                        course_id=course_id,
                        lesson_id=lesson_id,
                        course_content_version=course_content_version,
                        course_checksum=course_checksum,
                    ):
                        continue
                    matches.extend(
                        self._load_release_item_records(
                            manifest,
                            item,
                            (descriptor,),
                        )
                    )

        unique_matches = {
            _complete_identity(record.entry): record for record in matches
        }
        if not unique_matches:
            raise ScenarioCatalogNotFound(
                f"pinned scenario not found: {scenario_id} v{scenario_version}"
            )
        if len(unique_matches) != 1:
            raise ScenarioIntegrityError(
                f"pinned scenario identity is ambiguous: {scenario_id} v{scenario_version}"
            )
        return next(iter(unique_matches.values())).engine

    def get_published_record(
        self,
        scenario_id: str,
        scenario_version: int,
        scenario_checksum: str,
        *,
        release_id: str,
        release_no: int,
        release_checksum: str,
        course_id: str,
        lesson_id: str,
        course_content_version: int,
        course_checksum: str,
    ) -> LoadedScenarioV1:
        captured_releases = self._capture_active_releases(course_id=course_id)
        matches: list[LoadedScenarioV1] = []
        for manifest in self._reachable_release_history(captured_releases):
            if not isinstance(
                manifest,
                (CourseReleaseManifestV2, CourseReleaseManifestV3),
            ):
                continue
            if (
                manifest.course_id,
                manifest.release_id,
                manifest.release_no,
                manifest.checksum,
            ) != (
                course_id,
                release_id,
                release_no,
                release_checksum,
            ):
                continue
            for item in manifest.items:
                for descriptor in item.scenarios:
                    entry = self._release_entry(item, descriptor)
                    if not _matches_exact_identity(
                        entry,
                        scenario_id=scenario_id,
                        scenario_version=scenario_version,
                        scenario_checksum=scenario_checksum,
                        course_id=course_id,
                        lesson_id=lesson_id,
                        course_content_version=course_content_version,
                        course_checksum=course_checksum,
                    ):
                        continue
                    matches.extend(
                        self._load_release_item_records(
                            manifest,
                            item,
                            (descriptor,),
                        )
                    )

        unique_matches = {
            (
                record.release_id,
                record.release_no,
                record.release_checksum,
                *_complete_identity(record.entry),
            ): record
            for record in matches
        }
        if not unique_matches:
            raise ScenarioCatalogNotFound(
                "published scenario release pin was not found or is not reachable: "
                f"{scenario_id} v{scenario_version}"
            )
        if len(unique_matches) != 1:
            raise ScenarioIntegrityError(
                "published scenario release pin is ambiguous: "
                f"{scenario_id} v{scenario_version}"
            )
        return next(iter(unique_matches.values()))

    def _capture_active_releases(
        self,
        *,
        course_id: str | None = None,
    ) -> tuple[_CapturedReleaseV1, ...]:
        active_root = self.content_root / "releases" / "active"
        try:
            if not active_root.exists() and not active_root.is_symlink():
                return ()
            if active_root.is_symlink() or not active_root.is_dir():
                raise ScenarioFileError(
                    f"active release root must be a real directory: {active_root}"
                )
            pointer_paths = tuple(
                path
                for path in sorted(
                    active_root.glob("*.json"), key=lambda item: item.name
                )
                if course_id is None or path.name == f"{course_id}.json"
            )
        except ScenarioFileError:
            raise
        except OSError as exc:
            raise ScenarioFileError(
                f"cannot enumerate active release pointers: {exc}"
            ) from exc

        captured: list[_CapturedReleaseV1] = []
        course_ids: set[str] = set()
        for pointer_path in pointer_paths:
            pointer = load_contract_file(pointer_path, ActiveReleasePointerV1)
            if not verify_release_metadata_checksum(pointer):
                raise ScenarioIntegrityError(
                    f"active release pointer checksum mismatch: {pointer_path.name}"
                )
            expected_name = f"{pointer.course_id}.json"
            if pointer_path.name != expected_name:
                raise ScenarioIntegrityError(
                    f"active release pointer path identity mismatch: {pointer_path.name}"
                )
            if pointer.course_id in course_ids:
                raise ScenarioIntegrityError(
                    f"duplicate active release pointer for course: {pointer.course_id}"
                )
            course_ids.add(pointer.course_id)

            manifest = self._load_signed_manifest(
                self._artifact_path(pointer.manifest_path)
            )
            actual_identity = (
                manifest.course_id,
                manifest.release_id,
                manifest.release_no,
                manifest.checksum,
            )
            expected_identity = (
                pointer.course_id,
                pointer.release_id,
                pointer.release_no,
                pointer.manifest_checksum,
            )
            if actual_identity != expected_identity:
                raise ScenarioIntegrityError(
                    f"active pointer and release manifest disagree: {pointer.course_id}"
                )
            captured.append(_CapturedReleaseV1(pointer=pointer, manifest=manifest))
        return tuple(captured)

    def _reachable_release_history(
        self,
        captured_releases: tuple[_CapturedReleaseV1, ...],
    ) -> tuple[CourseReleaseManifestAny, ...]:
        history: list[CourseReleaseManifestAny] = []
        for captured in captured_releases:
            manifest = captured.manifest
            seen: set[str] = set()
            while True:
                if manifest.release_id in seen:
                    raise ScenarioIntegrityError(
                        f"release history contains a cycle: {manifest.course_id}"
                    )
                seen.add(manifest.release_id)
                history.append(manifest)
                parent_release_id = manifest.parent_release_id
                if parent_release_id is None:
                    break
                parent_path = self._artifact_path(
                    PurePosixPath(
                        "releases",
                        "manifests",
                        manifest.course_id,
                        f"{parent_release_id}.json",
                    ).as_posix()
                )
                parent = self._load_signed_manifest(parent_path)
                if (
                    parent.course_id != manifest.course_id
                    or parent.release_id != parent_release_id
                ):
                    raise ScenarioIntegrityError(
                        f"release parent identity mismatch: {parent_release_id}"
                    )
                if parent.release_no >= manifest.release_no:
                    raise ScenarioIntegrityError(
                        f"release parent does not precede child: {parent_release_id}"
                    )
                manifest = parent
        return tuple(history)

    @staticmethod
    def _merge_active_records(
        static_records: tuple[LoadedScenarioV1, ...],
        published_records: tuple[LoadedScenarioV1, ...],
    ) -> tuple[LoadedScenarioV1, ...]:
        published_by_id: dict[str, LoadedScenarioV1] = {}
        for record in published_records:
            scenario_id = record.entry.scenario_id
            if scenario_id in published_by_id:
                raise ScenarioIntegrityError(
                    f"duplicate published scenario_id: {scenario_id}"
                )
            published_by_id[scenario_id] = record
        return tuple(
            [
                record
                for record in static_records
                if record.entry.scenario_id not in published_by_id
            ]
            + list(published_by_id.values())
        )

    def _load_signed_manifest(self, path: Path) -> CourseReleaseManifestAny:
        document = load_contract_file(path, _ReleaseManifestDocument)
        try:
            return parse_signed_course_release_manifest(document.root)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ScenarioIntegrityError(
                f"invalid signed course release manifest {path}: {exc}"
            ) from exc

    def _load_release_records(
        self,
        manifest: CourseReleaseManifestV2 | CourseReleaseManifestV3,
    ) -> tuple[LoadedScenarioV1, ...]:
        records: list[LoadedScenarioV1] = []
        for item in manifest.items:
            records.extend(
                self._load_release_item_records(manifest, item, item.scenarios)
            )
        return tuple(records)

    def _load_release_item_records(
        self,
        manifest: CourseReleaseManifestV2 | CourseReleaseManifestV3,
        item: CourseReleaseItemV2 | CourseReleaseItemV3,
        scenario_descriptors: tuple[RuntimeArtifactDescriptorV1, ...],
    ) -> tuple[LoadedScenarioV1, ...]:
        configured_root = _resolve_path(
            content_data.content_root(),
            "runtime artifact content_root",
        )
        if configured_root != self.content_root:
            raise ScenarioFileError(
                "runtime artifact content_root does not match scenario repository"
            )
        course_descriptor = item.course_package
        try:
            course = runtime_artifacts.load_course_package(course_descriptor)
        except runtime_artifacts.RuntimeArtifactError as exc:
            raise ScenarioIntegrityError(
                f"published course package failed verification: {exc}"
            ) from exc

        records: list[LoadedScenarioV1] = []
        for scenario_descriptor in scenario_descriptors:
            try:
                scenario = runtime_artifacts.load_runtime_scenario(
                    scenario_descriptor
                )
            except runtime_artifacts.RuntimeArtifactError as exc:
                raise ScenarioIntegrityError(
                    f"published scenario failed verification: {exc}"
                ) from exc
            try:
                bundle = RuntimeBundleV1.model_validate(
                    {
                        "course": course.model_dump(mode="json"),
                        "scenario": scenario.model_dump(mode="json"),
                    }
                )
            except ValidationError as exc:
                raise ScenarioIntegrityError(
                    "published course and scenario cannot form a runtime bundle: "
                    f"{scenario_descriptor.artifact_id}: {exc}"
                ) from exc
            records.append(
                LoadedScenarioV1(
                    entry=self._release_entry(item, scenario_descriptor),
                    engine=SituationEngineV1(bundle.course, bundle.scenario),
                    release_id=manifest.release_id,
                    release_no=manifest.release_no,
                    release_checksum=str(manifest.checksum),
                )
            )
        return tuple(records)

    @staticmethod
    def _release_entry(
        item: CourseReleaseItemV2 | CourseReleaseItemV3,
        scenario_descriptor: RuntimeArtifactDescriptorV1,
    ) -> ScenarioCatalogEntryV1:
        course_descriptor = item.course_package
        return ScenarioCatalogEntryV1(
            scenario_id=scenario_descriptor.artifact_id,
            scenario_version=scenario_descriptor.version,
            scenario_checksum=scenario_descriptor.checksum,
            course_id=course_descriptor.course_id,
            lesson_id=course_descriptor.lesson_id,
            course_content_version=course_descriptor.version,
            course_checksum=course_descriptor.checksum,
            course_path=course_descriptor.path,
            scenario_path=scenario_descriptor.path,
            active=True,
            audience=item.audience,
        )

    def _load_entry(self, entry: ScenarioCatalogEntryV1) -> SituationEngineV1:
        course_path = self._artifact_path(entry.course_path)
        scenario_path = self._artifact_path(entry.scenario_path)
        engine = SituationEngineV1.from_files(course_path, scenario_path)
        course = engine.course
        scenario = engine.scenario
        actual = (
            scenario.scenario_id,
            scenario.scenario_version,
            scenario.checksum,
            course.course_id,
            course.lesson_id,
            course.content_version,
            course.checksum,
        )
        expected = (
            entry.scenario_id,
            entry.scenario_version,
            entry.scenario_checksum,
            entry.course_id,
            entry.lesson_id,
            entry.course_content_version,
            entry.course_checksum,
        )
        if actual != expected:
            raise ScenarioIntegrityError(
                f"scenario catalog identity does not match pinned artifacts: {entry.scenario_id}"
            )
        return engine

    def _artifact_path(self, relative_path: str) -> Path:
        path = self.content_root / Path(*PurePosixPath(relative_path).parts)
        _require_inside(
            _resolve_path(path, "artifact path"),
            self.content_root,
            "artifact path",
        )
        return path


def _matches_exact_identity(
    entry: ScenarioCatalogEntryV1,
    *,
    scenario_id: str,
    scenario_version: int,
    scenario_checksum: str,
    course_id: str | None,
    lesson_id: str | None,
    course_content_version: int | None,
    course_checksum: str | None,
) -> bool:
    required = (
        entry.scenario_id == scenario_id
        and entry.scenario_version == scenario_version
        and entry.scenario_checksum == scenario_checksum
    )
    optional = (
        (course_id is None or entry.course_id == course_id)
        and (lesson_id is None or entry.lesson_id == lesson_id)
        and (
            course_content_version is None
            or entry.course_content_version == course_content_version
        )
        and (course_checksum is None or entry.course_checksum == course_checksum)
    )
    return required and optional


def _complete_identity(
    entry: ScenarioCatalogEntryV1,
) -> tuple[str, int, str, str, str, int, str]:
    return (
        entry.scenario_id,
        entry.scenario_version,
        entry.scenario_checksum,
        entry.course_id,
        entry.lesson_id,
        entry.course_content_version,
        entry.course_checksum,
    )


def _validate_relative_json_path(value: str, label: str) -> None:
    if not value or "\\" in value or ":" in value:
        raise ValueError(f"{label} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must stay inside the content root")
    if value != path.as_posix():
        raise ValueError(f"{label} must use a canonical POSIX path")
    if path.suffix.lower() != ".json":
        raise ValueError(f"{label} must point to a JSON file")


def _path_key(value: str) -> str:
    return PurePosixPath(value).as_posix().casefold()


def _resolve_path(path: Path, label: str) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ScenarioFileError(f"cannot resolve {label}: {path}: {exc}") from exc


def _require_inside(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ScenarioFileError(f"{label} escapes content root: {path}") from exc


__all__ = [
    "LoadedScenarioV1",
    "ScenarioCatalogEntryV1",
    "ScenarioCatalogNotFound",
    "ScenarioCatalogRepository",
    "ScenarioCatalogV1",
]
