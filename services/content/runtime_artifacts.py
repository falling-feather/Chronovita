from __future__ import annotations

import hashlib
import json
import os
import stat as stat_module
import uuid
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, ValidationError

from services import content as content_data
from services.contracts.evidence_v1 import (
    EvidenceCorpusV1,
    LessonPresentationV1,
    sign_evidence_contract,
    verify_evidence_checksum,
)
from services.contracts.release_v2 import (
    ReleaseSupplementDescriptorV1,
    RuntimeArtifactDescriptorV1,
    runtime_artifact_path,
    supplement_artifact_path,
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


MAX_PRESENTATION_ASSET_BYTES = 256 * 1024 * 1024


class RuntimeArtifactError(content_data.ContentIntegrityError):
    pass


class RuntimeScenarioRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptor: RuntimeArtifactDescriptorV1
    title: str
    scenario_type: str
    student_role: str
    objective: str


class RuntimeEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptor: ReleaseSupplementDescriptorV1
    title: str
    source_count: int
    passage_count: int


class RuntimePresentationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptor: ReleaseSupplementDescriptorV1
    title: str
    estimated_minutes: int
    video_duration_seconds: float


def stage_evidence_corpus(corpus: EvidenceCorpusV1) -> RuntimeEvidenceRecord:
    """Store a sealed evidence corpus without making it student-visible."""

    _validate_evidence_corpus(corpus)
    descriptor = descriptor_for_evidence(corpus)
    target = content_data.content_root() / Path(descriptor.path)
    _assert_runtime_path(target, content_data.runtime_evidence_dir(), must_exist=False)
    _require_unique_version(target, descriptor.version, "evidence corpus")
    _write_immutable_json(target, corpus)
    return _evidence_record(corpus, descriptor)


def descriptor_for_evidence(
    corpus: EvidenceCorpusV1,
) -> ReleaseSupplementDescriptorV1:
    _validate_evidence_corpus(corpus)
    return ReleaseSupplementDescriptorV1(
        kind="evidence-corpus",
        schema_version="evidence-corpus/v1",
        artifact_id=corpus.corpus_id,
        course_id=corpus.course_id,
        lesson_id=corpus.lesson_id,
        version=corpus.corpus_version,
        checksum=corpus.checksum,
        path=supplement_artifact_path(
            kind="evidence-corpus",
            artifact_id=corpus.corpus_id,
            course_id=corpus.course_id,
            lesson_id=corpus.lesson_id,
            version=corpus.corpus_version,
            checksum=corpus.checksum,
        ),
    )


def load_evidence_corpus(
    *,
    course_id: str,
    lesson_id: str,
    corpus_id: str,
    corpus_version: int,
    corpus_checksum: str,
) -> tuple[EvidenceCorpusV1, ReleaseSupplementDescriptorV1]:
    descriptor = ReleaseSupplementDescriptorV1(
        kind="evidence-corpus",
        schema_version="evidence-corpus/v1",
        artifact_id=corpus_id,
        course_id=course_id,
        lesson_id=lesson_id,
        version=corpus_version,
        checksum=corpus_checksum,
        path=supplement_artifact_path(
            kind="evidence-corpus",
            artifact_id=corpus_id,
            course_id=course_id,
            lesson_id=lesson_id,
            version=corpus_version,
            checksum=corpus_checksum,
        ),
    )
    target = content_data.content_root() / Path(descriptor.path)
    corpus, actual = load_evidence_corpus_path(target)
    if actual != descriptor:
        raise RuntimeArtifactError("evidence corpus descriptor changed while loading")
    return corpus, descriptor


def load_evidence_corpus_path(
    path: Path,
) -> tuple[EvidenceCorpusV1, ReleaseSupplementDescriptorV1]:
    _assert_runtime_path(path, content_data.runtime_evidence_dir())
    corpus = _read_contract(path, EvidenceCorpusV1)
    _validate_evidence_corpus(corpus)
    descriptor = descriptor_for_evidence(corpus)
    expected = content_data.content_root() / Path(descriptor.path)
    if path.absolute() != expected.absolute():
        raise RuntimeArtifactError(
            f"evidence corpus identity does not match its path: {path}"
        )
    return corpus, descriptor


def list_staged_evidence(
    *,
    corpus_id: str | None = None,
) -> list[RuntimeEvidenceRecord]:
    records: list[RuntimeEvidenceRecord] = []
    for path in _walk_runtime_json_files(content_data.runtime_evidence_dir()):
        corpus, descriptor = load_evidence_corpus_path(path)
        if corpus_id is None or descriptor.artifact_id == corpus_id:
            records.append(_evidence_record(corpus, descriptor))
    return sorted(records, key=_supplement_record_sort_key)


def stage_lesson_presentation(
    presentation: LessonPresentationV1,
    *,
    sealed_by: str | None = None,
) -> RuntimePresentationRecord:
    """Verify local media and store a sealed presentation descriptor."""

    _validate_lesson_presentation(presentation)
    if sealed_by is not None:
        payload = presentation.model_dump(mode="json")
        payload["sealed_by"] = sealed_by
        payload["checksum"] = "0" * 64
        presentation = sign_evidence_contract(
            LessonPresentationV1.model_validate(payload)
        )
    descriptor = descriptor_for_presentation(presentation)
    target = content_data.content_root() / Path(descriptor.path)
    _assert_runtime_path(
        target,
        content_data.runtime_presentation_dir(),
        must_exist=False,
    )
    _require_unique_version(target, descriptor.version, "lesson presentation")
    _write_immutable_json(target, presentation)
    return _presentation_record(presentation, descriptor)


def descriptor_for_presentation(
    presentation: LessonPresentationV1,
) -> ReleaseSupplementDescriptorV1:
    _validate_lesson_presentation(presentation)
    return ReleaseSupplementDescriptorV1(
        kind="lesson-presentation",
        schema_version="lesson-presentation/v1",
        artifact_id=presentation.presentation_id,
        course_id=presentation.course_id,
        lesson_id=presentation.lesson_id,
        version=presentation.presentation_version,
        checksum=presentation.checksum,
        path=supplement_artifact_path(
            kind="lesson-presentation",
            artifact_id=presentation.presentation_id,
            course_id=presentation.course_id,
            lesson_id=presentation.lesson_id,
            version=presentation.presentation_version,
            checksum=presentation.checksum,
        ),
    )


def load_lesson_presentation(
    *,
    course_id: str,
    lesson_id: str,
    presentation_id: str,
    presentation_version: int,
    presentation_checksum: str,
) -> tuple[LessonPresentationV1, ReleaseSupplementDescriptorV1]:
    descriptor = ReleaseSupplementDescriptorV1(
        kind="lesson-presentation",
        schema_version="lesson-presentation/v1",
        artifact_id=presentation_id,
        course_id=course_id,
        lesson_id=lesson_id,
        version=presentation_version,
        checksum=presentation_checksum,
        path=supplement_artifact_path(
            kind="lesson-presentation",
            artifact_id=presentation_id,
            course_id=course_id,
            lesson_id=lesson_id,
            version=presentation_version,
            checksum=presentation_checksum,
        ),
    )
    target = content_data.content_root() / Path(descriptor.path)
    presentation, actual = load_lesson_presentation_path(target)
    if actual != descriptor:
        raise RuntimeArtifactError(
            "lesson presentation descriptor changed while loading"
        )
    return presentation, descriptor


def load_lesson_presentation_path(
    path: Path,
) -> tuple[LessonPresentationV1, ReleaseSupplementDescriptorV1]:
    _assert_runtime_path(path, content_data.runtime_presentation_dir())
    presentation = _read_contract(path, LessonPresentationV1)
    _validate_lesson_presentation(presentation)
    descriptor = descriptor_for_presentation(presentation)
    expected = content_data.content_root() / Path(descriptor.path)
    if path.absolute() != expected.absolute():
        raise RuntimeArtifactError(
            f"lesson presentation identity does not match its path: {path}"
        )
    return presentation, descriptor


def list_staged_presentations(
    *,
    presentation_id: str | None = None,
) -> list[RuntimePresentationRecord]:
    records: list[RuntimePresentationRecord] = []
    for path in _walk_runtime_json_files(content_data.runtime_presentation_dir()):
        presentation, descriptor = load_lesson_presentation_path(path)
        if presentation_id is None or descriptor.artifact_id == presentation_id:
            records.append(_presentation_record(presentation, descriptor))
    return sorted(records, key=_supplement_record_sort_key)


def stage_scenario(
    scenario: ScenarioTemplateV1,
    *,
    sealed_by: str | None = None,
) -> RuntimeScenarioRecord:
    """Store a sealed scenario without making it visible to published readers."""

    if scenario.status != "sealed" or not verify_contract_checksum(scenario):
        raise ValueError("scenario must be sealed and checksum-valid")
    if len(scenario.title) > 160:
        raise ValueError("scenario title cannot exceed 160 characters")
    if sealed_by is not None:
        payload = scenario.model_dump(mode="json")
        payload["sealed_by"] = sealed_by
        payload["checksum"] = "0" * 64
        provisional = ScenarioTemplateV1.model_validate(payload)
        payload["checksum"] = calculate_contract_checksum(provisional)
        scenario = ScenarioTemplateV1.model_validate(payload)
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
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        scenario = ScenarioTemplateV1.model_validate(payload)
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
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


def load_release_evidence(
    descriptor: ReleaseSupplementDescriptorV1,
) -> EvidenceCorpusV1:
    if descriptor.kind != "evidence-corpus":
        raise RuntimeArtifactError("descriptor is not an evidence corpus")
    corpus, actual = load_evidence_corpus_path(
        content_data.content_root() / Path(descriptor.path)
    )
    if actual != descriptor:
        raise RuntimeArtifactError("runtime evidence does not match its descriptor")
    return corpus


def load_release_presentation(
    descriptor: ReleaseSupplementDescriptorV1,
) -> LessonPresentationV1:
    if descriptor.kind != "lesson-presentation":
        raise RuntimeArtifactError("descriptor is not a lesson presentation")
    presentation, actual = load_lesson_presentation_path(
        content_data.content_root() / Path(descriptor.path)
    )
    if actual != descriptor:
        raise RuntimeArtifactError(
            "runtime presentation does not match its descriptor"
        )
    return presentation


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


def _validate_evidence_corpus(corpus: EvidenceCorpusV1) -> None:
    if corpus.status != "sealed" or not verify_evidence_checksum(corpus):
        raise RuntimeArtifactError(
            "evidence corpus must be sealed and checksum-valid"
        )


def _validate_lesson_presentation(presentation: LessonPresentationV1) -> None:
    if presentation.status != "sealed" or not verify_evidence_checksum(
        presentation
    ):
        raise RuntimeArtifactError(
            "lesson presentation must be sealed and checksum-valid"
        )
    for relative_path, expected_checksum in (
        (presentation.video_path, presentation.video_sha256),
        (presentation.poster_path, presentation.poster_sha256),
        (presentation.transcript_path, presentation.transcript_sha256),
    ):
        path = content_data.content_root() / Path(relative_path)
        _assert_runtime_path(path, content_data.lesson_media_dir())
        if _hash_regular_file(
            path,
            root=content_data.lesson_media_dir(),
            maximum_bytes=MAX_PRESENTATION_ASSET_BYTES,
        ) != expected_checksum:
            raise RuntimeArtifactError(
                f"presentation asset checksum mismatch: {relative_path}"
            )


def _evidence_record(
    corpus: EvidenceCorpusV1,
    descriptor: ReleaseSupplementDescriptorV1,
) -> RuntimeEvidenceRecord:
    return RuntimeEvidenceRecord(
        descriptor=descriptor,
        title=corpus.title,
        source_count=len(corpus.sources),
        passage_count=len(corpus.passages),
    )


def _presentation_record(
    presentation: LessonPresentationV1,
    descriptor: ReleaseSupplementDescriptorV1,
) -> RuntimePresentationRecord:
    return RuntimePresentationRecord(
        descriptor=descriptor,
        title=presentation.title,
        estimated_minutes=presentation.estimated_minutes,
        video_duration_seconds=presentation.video_duration_seconds,
    )


def _supplement_record_sort_key(record) -> tuple[str, str, str, int, str]:
    descriptor = record.descriptor
    return (
        descriptor.course_id,
        descriptor.lesson_id,
        descriptor.artifact_id,
        descriptor.version,
        descriptor.checksum,
    )


def _require_unique_version(path: Path, version: int, label: str) -> None:
    if not path.parent.exists():
        return
    for sibling in path.parent.glob(f"v{version:03d}-*.json"):
        if sibling.name != path.name:
            raise FileExistsError(
                f"{label} id and version already identify different content"
            )


def _walk_runtime_json_files(root: Path) -> list[Path]:
    if not root.exists() and not root.is_symlink():
        return []
    if root.is_symlink() or not root.is_dir():
        raise RuntimeArtifactError(
            f"runtime supplement root must be a real directory: {root}"
        )
    paths: list[Path] = []
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
                    f"runtime supplement directory cannot be a symlink: {candidate}"
                )
        paths.extend(
            current_path / filename
            for filename in files
            if filename.endswith(".json")
        )
    return sorted(paths)


def _read_contract(path: Path, model: type[BaseModel]):
    try:
        return load_contract_file(path, model)
    except ScenarioFileError as exc:
        raise RuntimeArtifactError(f"cannot read runtime artifact: {path}") from exc


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


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


def _hash_regular_file(
    path: Path,
    *,
    root: Path,
    maximum_bytes: int,
) -> str:
    _assert_runtime_path(path, root)
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            opened_stat = os.fstat(handle.fileno())
            if not stat_module.S_ISREG(opened_stat.st_mode):
                raise RuntimeArtifactError(
                    f"presentation asset is not a regular file: {path}"
                )
            if opened_stat.st_size > maximum_bytes:
                raise RuntimeArtifactError(
                    f"presentation asset exceeds {maximum_bytes} bytes: {path}"
                )
            remaining = maximum_bytes + 1
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
            path_stat = os.lstat(path)
            if stat_module.S_ISLNK(path_stat.st_mode):
                raise RuntimeArtifactError(
                    f"presentation asset path cannot be a symlink: {path}"
                )
            if not os.path.samestat(opened_stat, path_stat):
                raise RuntimeArtifactError(
                    f"presentation asset changed while being verified: {path}"
                )
    except RuntimeArtifactError:
        raise
    except OSError as exc:
        raise RuntimeArtifactError(
            f"cannot verify presentation asset: {path}"
        ) from exc
    if remaining == 0:
        raise RuntimeArtifactError(
            f"presentation asset exceeds {maximum_bytes} bytes: {path}"
        )
    return digest.hexdigest()


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
    "RuntimeEvidenceRecord",
    "RuntimePresentationRecord",
    "RuntimeScenarioRecord",
    "bind_course_package",
    "descriptor_for_evidence",
    "descriptor_for_presentation",
    "descriptor_for_scenario",
    "list_staged_evidence",
    "list_staged_presentations",
    "list_staged_scenarios",
    "load_course_package",
    "load_evidence_corpus",
    "load_lesson_presentation",
    "load_release_evidence",
    "load_release_presentation",
    "load_runtime_scenario",
    "load_staged_scenario",
    "load_staged_scenario_bytes",
    "materialize_course_package",
    "stage_evidence_corpus",
    "stage_lesson_presentation",
    "stage_scenario",
]
