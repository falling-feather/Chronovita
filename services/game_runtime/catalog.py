from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.contracts.v1 import Checksum, ContractId
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
        entries = sorted(
            (entry for entry in catalog.entries if entry.active),
            key=lambda item: (item.course_id, item.lesson_id, item.scenario_id),
        )
        return tuple(
            LoadedScenarioV1(entry=entry, engine=self._load_entry(entry))
            for entry in entries
        )

    def get_active(self, scenario_id: str) -> SituationEngineV1:
        return self.get_active_record(scenario_id).engine

    def get_active_record(self, scenario_id: str) -> LoadedScenarioV1:
        catalog = self.load_catalog()
        entry = next(
            (
                item
                for item in catalog.entries
                if item.active and item.scenario_id == scenario_id
            ),
            None,
        )
        if entry is None:
            raise ScenarioCatalogNotFound(f"active scenario not found: {scenario_id}")
        return LoadedScenarioV1(entry=entry, engine=self._load_entry(entry))

    def get_exact(
        self,
        scenario_id: str,
        scenario_version: int,
        scenario_checksum: str,
    ) -> SituationEngineV1:
        catalog = self.load_catalog()
        entry = next(
            (
                item
                for item in catalog.entries
                if item.scenario_id == scenario_id
                and item.scenario_version == scenario_version
                and item.scenario_checksum == scenario_checksum
            ),
            None,
        )
        if entry is None:
            raise ScenarioCatalogNotFound(
                f"pinned scenario not found: {scenario_id} v{scenario_version}"
            )
        return self._load_entry(entry)

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
