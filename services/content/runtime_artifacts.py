from __future__ import annotations

import json
import os
import stat as stat_module
import uuid
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict

from services import content as content_data
from services.contracts.release_v2 import (
    RuntimeArtifactDescriptorV1,
    runtime_artifact_path,
)
from services.contracts.v1 import (
    CoursePackageV1,
    RuntimeBundleV1,
    ScenarioRefV1,
    ScenarioTemplateV1,
    calculate_contract_checksum,
    verify_contract_checksum,
)
from services.game_runtime import (
    MAX_CONTRACT_FILE_BYTES,
    ScenarioFileError,
    load_contract_file,
)


class RuntimeArtifactError(content_data.ContentIntegrityError):
    pass


class RuntimeScenarioRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptor: RuntimeArtifactDescriptorV1
    title: str
    scenario_type: str
    student_role: str
    objective: str


def stage_scenario(
    scenario: ScenarioTemplateV1,
) -> RuntimeScenarioRecord:
    """Store a sealed scenario without making it visible to published readers."""

    if scenario.status != "sealed" or not verify_contract_checksum(scenario):
        raise ValueError("scenario must be sealed and checksum-valid")
    _validate_sealed_scenario(scenario)
    descriptor = descriptor_for_scenario(scenario)
    root = content_data.content_root()
    target = root / Path(descriptor.path)
    _assert_runtime_path(target, content_data.runtime_scenario_dir(), must_exist=False)
    version_dir = target.parent
    if version_dir.exists():
        for sibling in version_dir.glob(f"v{scenario.scenario_version:03d}-*.json"):
            if sibling.name != target.name:
                raise FileExistsError(
                    "scenario_id and scenario_version already identify different content"
                )
    _write_immutable_json(target, scenario)
    return _scenario_record(scenario, descriptor)


def list_staged_scenarios(
    *,
    scenario_id: str | None = None,
) -> list[RuntimeScenarioRecord]:
    root = content_data.runtime_scenario_dir()
    if not root.exists() and not root.is_symlink():
        return []
    if root.is_symlink() or not root.is_dir():
        raise RuntimeArtifactError(
            f"runtime scenario root must be a real directory: {root}"
        )
    records: list[RuntimeScenarioRecord] = []
    for current, directories, files in os.walk(
        root,
        followlinks=False,
        onerror=_raise_walk_error,
    ):
        current_path = Path(current)
        for directory in tuple(directories):
            candidate = current_path / directory
            if candidate.is_symlink():
                raise RuntimeArtifactError(
                    f"runtime scenario directory cannot be a symlink: {candidate}"
                )
        for filename in files:
            if not filename.endswith(".json"):
                continue
            if scenario_id is not None and current_path.name != scenario_id:
                continue
            scenario, descriptor = load_staged_scenario_path(current_path / filename)
            records.append(_scenario_record(scenario, descriptor))
    return sorted(
        records,
        key=lambda item: (
            item.descriptor.course_id,
            item.descriptor.lesson_id,
            item.descriptor.artifact_id,
            item.descriptor.version,
            item.descriptor.checksum,
        ),
    )


def descriptor_for_scenario(
    scenario: ScenarioTemplateV1,
) -> RuntimeArtifactDescriptorV1:
    _validate_sealed_scenario(scenario)
    assert scenario.checksum is not None
    path = runtime_artifact_path(
        kind="scenario-template",
        artifact_id=scenario.scenario_id,
        course_id=scenario.course_id,
        lesson_id=scenario.lesson_id,
        version=scenario.scenario_version,
        checksum=scenario.checksum,
    )
    return RuntimeArtifactDescriptorV1(
        kind="scenario-template",
        schema_version="scenario-template/v1",
        artifact_id=scenario.scenario_id,
        course_id=scenario.course_id,
        lesson_id=scenario.lesson_id,
        version=scenario.scenario_version,
        checksum=scenario.checksum,
        path=path,
    )


def load_staged_scenario(
    *,
    course_id: str,
    lesson_id: str,
    scenario_id: str,
    scenario_version: int,
    scenario_checksum: str,
) -> tuple[ScenarioTemplateV1, RuntimeArtifactDescriptorV1]:
    descriptor = RuntimeArtifactDescriptorV1(
        kind="scenario-template",
        schema_version="scenario-template/v1",
        artifact_id=scenario_id,
        course_id=course_id,
        lesson_id=lesson_id,
        version=scenario_version,
        checksum=scenario_checksum,
        path=runtime_artifact_path(
            kind="scenario-template",
            artifact_id=scenario_id,
            course_id=course_id,
            lesson_id=lesson_id,
            version=scenario_version,
            checksum=scenario_checksum,
        ),
    )
    target = content_data.content_root() / Path(descriptor.path)
    _assert_runtime_path(
        target,
        content_data.runtime_scenario_dir(),
        must_exist=False,
    )
    if not target.exists() and not target.is_symlink():
        raise FileNotFoundError(
            f"staged scenario does not exist: {scenario_id} v{scenario_version}"
        )
    scenario, verified_descriptor = load_staged_scenario_path(target)
    if verified_descriptor != descriptor:
        raise RuntimeArtifactError("staged scenario descriptor changed while loading")
    return scenario, descriptor


def load_staged_scenario_bytes(
    *,
    course_id: str,
    lesson_id: str,
    scenario_id: str,
    scenario_version: int,
    scenario_checksum: str,
) -> tuple[bytes, RuntimeArtifactDescriptorV1]:
    """Return the verified immutable file bytes for an exact sealed scenario identity."""

    _, descriptor = load_staged_scenario(
        course_id=course_id,
        lesson_id=lesson_id,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        scenario_checksum=scenario_checksum,
    )
    target = content_data.content_root() / Path(descriptor.path)
    raw = _read_immutable_bytes(target)
    try:
        scenario = ScenarioTemplateV1.model_validate_json(raw)
    except ValueError as exc:
        raise RuntimeArtifactError(
            f"cannot read runtime artifact: {target}"
        ) from exc
    _validate_sealed_scenario(scenario)
    if descriptor_for_scenario(scenario) != descriptor:
        raise RuntimeArtifactError("staged scenario descriptor changed while downloading")
    return raw, descriptor


def load_staged_scenario_path(
    path: Path,
) -> tuple[ScenarioTemplateV1, RuntimeArtifactDescriptorV1]:
    _assert_runtime_path(path, content_data.runtime_scenario_dir())
    scenario = _read_contract(path, ScenarioTemplateV1)
    _validate_sealed_scenario(scenario)
    descriptor = descriptor_for_scenario(scenario)
    expected = content_data.content_root() / Path(descriptor.path)
    if path.absolute() != expected.absolute():
        raise RuntimeArtifactError(
            f"scenario content identity does not match its path: {path}"
        )
    return scenario, descriptor


def bind_course_package(
    package: CoursePackageV1,
    scenarios: Iterable[tuple[ScenarioTemplateV1, bool]],
) -> CoursePackageV1:
    if package.status != "sealed" or not verify_contract_checksum(package):
        raise RuntimeArtifactError("course package must be sealed and checksum-valid")

    selected = sorted(scenarios, key=lambda item: item[0].scenario_id)
    scenario_ids = [scenario.scenario_id for scenario, _ in selected]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise RuntimeArtifactError("scenario selections must use unique scenario_id values")
    primary_count = sum(1 for _, primary in selected if primary)
    if selected and primary_count != 1:
        raise RuntimeArtifactError("a published lesson with scenarios requires one primary")

    refs: list[ScenarioRefV1] = []
    for scenario, primary in selected:
        _validate_sealed_scenario(scenario)
        if (scenario.course_id, scenario.lesson_id) != (
            package.course_id,
            package.lesson_id,
        ):
            raise RuntimeArtifactError(
                "scenario course_id and lesson_id must match the course package"
            )
        assert scenario.checksum is not None
        refs.append(
            ScenarioRefV1(
                scenario_id=scenario.scenario_id,
                scenario_version=scenario.scenario_version,
                checksum=scenario.checksum,
                primary=primary,
            )
        )

    payload = package.model_dump(mode="json")
    payload["scenario_refs"] = [item.model_dump(mode="json") for item in refs]
    payload["checksum"] = "0" * 64
    provisional = CoursePackageV1.model_validate(payload)
    payload["checksum"] = calculate_contract_checksum(provisional)
    bound = CoursePackageV1.model_validate(payload)
    for scenario, _ in selected:
        RuntimeBundleV1(course=bound, scenario=scenario)
    return bound


def materialize_course_package(
    package: CoursePackageV1,
) -> RuntimeArtifactDescriptorV1:
    if package.status != "sealed" or not verify_contract_checksum(package):
        raise RuntimeArtifactError("course package must be sealed and checksum-valid")
    assert package.checksum is not None
    path = runtime_artifact_path(
        kind="course-package",
        artifact_id=package.package_id,
        course_id=package.course_id,
        lesson_id=package.lesson_id,
        version=package.content_version,
        checksum=package.checksum,
    )
    descriptor = RuntimeArtifactDescriptorV1(
        kind="course-package",
        schema_version="course-package/v1",
        artifact_id=package.package_id,
        course_id=package.course_id,
        lesson_id=package.lesson_id,
        version=package.content_version,
        checksum=package.checksum,
        path=path,
    )
    _write_immutable_json(content_data.content_root() / Path(path), package)
    return descriptor


def load_course_package(
    descriptor: RuntimeArtifactDescriptorV1,
) -> CoursePackageV1:
    if descriptor.kind != "course-package":
        raise RuntimeArtifactError("descriptor is not a course package")
    path = content_data.content_root() / Path(descriptor.path)
    _assert_runtime_path(path, content_data.runtime_course_package_dir())
    package = _read_contract(path, CoursePackageV1)
    if package.status != "sealed" or not verify_contract_checksum(package):
        raise RuntimeArtifactError("runtime course package failed checksum validation")
    identity = (
        package.package_id,
        package.course_id,
        package.lesson_id,
        package.content_version,
        package.checksum,
    )
    expected = (
        descriptor.artifact_id,
        descriptor.course_id,
        descriptor.lesson_id,
        descriptor.version,
        descriptor.checksum,
    )
    if identity != expected:
        raise RuntimeArtifactError("runtime course package does not match its descriptor")
    return package


def load_runtime_scenario(
    descriptor: RuntimeArtifactDescriptorV1,
) -> ScenarioTemplateV1:
    if descriptor.kind != "scenario-template":
        raise RuntimeArtifactError("descriptor is not a scenario template")
    scenario, actual = load_staged_scenario_path(
        content_data.content_root() / Path(descriptor.path)
    )
    if actual != descriptor:
        raise RuntimeArtifactError("runtime scenario does not match its descriptor")
    return scenario


def _scenario_record(
    scenario: ScenarioTemplateV1,
    descriptor: RuntimeArtifactDescriptorV1,
) -> RuntimeScenarioRecord:
    return RuntimeScenarioRecord(
        descriptor=descriptor,
        title=scenario.title,
        scenario_type=scenario.scenario_type,
        student_role=scenario.student_role,
        objective=scenario.objective,
    )


def _validate_sealed_scenario(scenario: ScenarioTemplateV1) -> None:
    if scenario.status != "sealed" or not verify_contract_checksum(scenario):
        raise RuntimeArtifactError("scenario must be sealed and checksum-valid")


def _read_contract(path: Path, model: type[BaseModel]):
    try:
        return load_contract_file(path, model)
    except ScenarioFileError as exc:
        raise RuntimeArtifactError(f"cannot read runtime artifact: {path}") from exc


def _write_immutable_json(path: Path, payload: BaseModel) -> None:
    root = content_data.runtime_dir()
    _assert_runtime_path(path, root, must_exist=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_runtime_path(path, root, must_exist=False)
    raw = (
        json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    if len(raw) > MAX_CONTRACT_FILE_BYTES:
        raise RuntimeArtifactError(
            f"runtime artifact exceeds {MAX_CONTRACT_FILE_BYTES} bytes: {path}"
        )
    if path.exists():
        if _read_immutable_bytes(path) != raw:
            raise RuntimeArtifactError(
                f"immutable runtime artifact already exists with different bytes: {path}"
            )
        return

    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            _write_immutable_json(path, payload)
    finally:
        temp.unlink(missing_ok=True)


def _read_immutable_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            opened_stat = os.fstat(handle.fileno())
            if not stat_module.S_ISREG(opened_stat.st_mode):
                raise RuntimeArtifactError(
                    f"runtime artifact is not a regular file: {path}"
                )
            if opened_stat.st_size > MAX_CONTRACT_FILE_BYTES:
                raise RuntimeArtifactError(
                    f"runtime artifact exceeds {MAX_CONTRACT_FILE_BYTES} bytes: {path}"
                )
            raw = handle.read(MAX_CONTRACT_FILE_BYTES + 1)
            path_stat = os.lstat(path)
            if stat_module.S_ISLNK(path_stat.st_mode):
                raise RuntimeArtifactError(
                    f"runtime artifact path cannot be a symlink: {path}"
                )
            if not os.path.samestat(opened_stat, path_stat):
                raise RuntimeArtifactError(
                    f"runtime artifact changed while being verified: {path}"
                )
    except RuntimeArtifactError:
        raise
    except OSError as exc:
        raise RuntimeArtifactError(f"cannot verify runtime artifact: {path}") from exc
    if len(raw) > MAX_CONTRACT_FILE_BYTES:
        raise RuntimeArtifactError(
            f"runtime artifact exceeds {MAX_CONTRACT_FILE_BYTES} bytes: {path}"
        )
    return raw


def _raise_walk_error(exc: OSError) -> None:
    raise RuntimeArtifactError("cannot enumerate runtime scenarios") from exc


def _assert_runtime_path(
    path: Path,
    root: Path,
    *,
    must_exist: bool = True,
) -> None:
    absolute_root = root.absolute()
    absolute_path = path.absolute()
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise RuntimeArtifactError(f"runtime artifact escapes its root: {path}") from exc
    current = absolute_root
    _assert_not_symlink(current)
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            _assert_not_symlink(current)
    if must_exist and not absolute_path.is_file():
        raise RuntimeArtifactError(f"runtime artifact does not exist: {path}")


def _assert_not_symlink(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeArtifactError(f"runtime artifact path cannot be a symlink: {path}")


__all__ = [
    "RuntimeArtifactError",
    "RuntimeScenarioRecord",
    "bind_course_package",
    "descriptor_for_scenario",
    "list_staged_scenarios",
    "load_course_package",
    "load_runtime_scenario",
    "load_staged_scenario",
    "load_staged_scenario_bytes",
    "materialize_course_package",
    "stage_scenario",
]
