from __future__ import annotations

import hashlib
import html
import json
import os
import re
import stat as stat_module
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pydantic import BaseModel, ValidationError

from services import content as content_data
from services.content import LessonContentPackage, package_checksum
from services.content import runtime_artifacts
from services.content import workflow as content_workflow
from services.contracts.archive_v1 import (
    ARCHIVE_MANIFEST_FILENAME,
    ARCHIVE_RELEASE_MANIFEST_FILENAME,
    MAX_ARCHIVE_FILE_BYTES,
    MAX_ARCHIVE_FILES,
    MAX_ARCHIVE_TOTAL_BYTES,
    ArchiveRendererV1,
    CourseArchiveFileV1,
    CourseArchiveLessonV1,
    CourseArchiveManifestV1,
    CourseArchivePayloadV1,
    CourseArchiveScenarioV1,
    archive_id_for_checksum,
    archive_relative_path,
    calculate_archive_payload_checksum,
    lesson_archive_paths,
    safe_archive_filename,
    scenario_archive_path,
    supplement_archive_path,
    sign_archive_manifest,
)
from services.contracts.release_v2 import parse_signed_course_release_manifest
from services.contracts.v1 import (
    CoursePackageV1,
    ScenarioTemplateV1,
    verify_contract_checksum,
)


ARCHIVE_RENDERER_ID = "chronovita-teacher-export"
ARCHIVE_RENDERER_VERSION = 2
ARCHIVE_STYLE_PROFILE = "course-preview-default"
_JSON_MEDIA_TYPE = "application/json"
_MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"
_HTML_MEDIA_TYPE = "text/html; charset=utf-8"
_INLINE_TOKEN_MARKS = {
    "red": "red",
    "blue": "blue",
    "gold": "gold",
    "large": "large",
    "small": "small",
    "红色": "red",
    "蓝色": "blue",
    "金色": "gold",
    "大字": "large",
    "小字": "small",
}


class ArchiveBuildError(RuntimeError):
    code = "course_archive_build_failed"


@dataclass(frozen=True)
class BuiltCourseArchive:
    manifest: CourseArchiveManifestV1
    files: Mapping[str, bytes]

    def __post_init__(self) -> None:
        expected = {ARCHIVE_MANIFEST_FILENAME, *(item.path for item in self.manifest.files)}
        if set(self.files) != expected:
            raise ArchiveBuildError("archive files do not match the signed manifest")
        for item in self.manifest.files:
            raw = self.files[item.path]
            if (
                len(raw) != item.size_bytes
                or hashlib.sha256(raw).hexdigest() != item.blob_sha256
            ):
                raise ArchiveBuildError(
                    f"archive file bytes do not match descriptor: {item.path}"
                )


def build_course_archive(course_id: str, release_id: str) -> BuiltCourseArchive:
    try:
        release = content_workflow.get_release(course_id, release_id)
    except Exception as exc:
        raise ArchiveBuildError("cannot verify the requested course release") from exc
    if not release.items:
        raise ArchiveBuildError("a release without lessons cannot be archived")

    release_path = (
        content_data.release_dir()
        / "manifests"
        / release.course_id
        / f"{release.release_id}.json"
    )
    release_raw = _read_content_bytes(release_path)
    release_from_bytes = _parse_json_contract(
        release_raw,
        parse_signed_course_release_manifest,
        "course release manifest",
    )
    if release_from_bytes.model_dump(mode="json") != release.model_dump(mode="json"):
        raise ArchiveBuildError("release bytes changed after the release was verified")

    payloads: dict[str, bytes] = {
        ARCHIVE_RELEASE_MANIFEST_FILENAME: release_raw,
    }
    descriptors: list[CourseArchiveFileV1] = [
        _file_descriptor(
            path=ARCHIVE_RELEASE_MANIFEST_FILENAME,
            kind="release-manifest",
            media_type=_JSON_MEDIA_TYPE,
            payload=release_raw,
            artifact_id=release.release_id,
            artifact_version=release.release_no,
            schema_version=release.schema_version,
            contract_checksum=release.checksum,
        )
    ]
    lessons: list[CourseArchiveLessonV1] = []
    course_title: str | None = None

    for item in release.items:
        expected_source_path = (
            f"sealed/{item.lesson_id}-v{item.content_version:03d}.json"
        )
        if item.source_path != expected_source_path:
            raise ArchiveBuildError(
                f"release item has a non-canonical sealed path: {item.lesson_id}"
            )
        sealed_raw = _read_content_relative_bytes(item.source_path)
        sealed = _parse_json_model(
            sealed_raw,
            LessonContentPackage,
            f"sealed lesson {item.lesson_id}",
        )
        if (
            sealed.status != "sealed"
            or sealed.checksum != item.source_checksum
            or package_checksum(sealed) != sealed.checksum
            or (sealed.course_id, sealed.lesson_id, sealed.version)
            != (item.course_id, item.lesson_id, item.content_version)
        ):
            raise ArchiveBuildError(
                f"sealed lesson does not match release item: {item.lesson_id}"
            )

        lesson_course_title = sealed.course_title.strip() or sealed.unit
        if course_title is None:
            course_title = lesson_course_title
        elif course_title != lesson_course_title:
            raise ArchiveBuildError("release lessons disagree on course_title")

        package_path, expected_package_checksum = _course_package_reference(item)
        course_raw = _read_content_relative_bytes(package_path)
        course = _parse_json_model(
            course_raw,
            CoursePackageV1,
            f"course package {item.lesson_id}",
        )
        if (
            course.status != "sealed"
            or not verify_contract_checksum(course)
            or course.checksum != expected_package_checksum
            or (course.course_id, course.lesson_id, course.content_version)
            != (item.course_id, item.lesson_id, item.content_version)
        ):
            raise ArchiveBuildError(
                f"course package does not match release item: {item.lesson_id}"
            )

        paths = lesson_archive_paths(sealed.lesson_id, sealed.title)
        payloads[paths["sealed-lesson"]] = sealed_raw
        payloads[paths["course-package"]] = course_raw
        payloads[paths["format-layer"]] = _json_bytes(_format_layer(sealed))
        payloads[paths["teacher-markdown"]] = _teacher_markdown(sealed).encode("utf-8")
        payloads[paths["preview-html"]] = _preview_html(sealed).encode("utf-8")

        descriptors.extend(
            (
                _file_descriptor(
                    path=paths["sealed-lesson"],
                    kind="sealed-lesson",
                    media_type=_JSON_MEDIA_TYPE,
                    payload=sealed_raw,
                    lesson_id=sealed.lesson_id,
                    artifact_id=sealed.lesson_id,
                    artifact_version=sealed.version,
                    schema_version="lesson-content-package/v1",
                    contract_checksum=str(sealed.checksum),
                ),
                _file_descriptor(
                    path=paths["course-package"],
                    kind="course-package",
                    media_type=_JSON_MEDIA_TYPE,
                    payload=course_raw,
                    lesson_id=sealed.lesson_id,
                    artifact_id=course.package_id,
                    artifact_version=course.content_version,
                    schema_version=course.schema_version,
                    contract_checksum=str(course.checksum),
                ),
                _file_descriptor(
                    path=paths["format-layer"],
                    kind="format-layer",
                    media_type=_JSON_MEDIA_TYPE,
                    payload=payloads[paths["format-layer"]],
                    lesson_id=sealed.lesson_id,
                ),
                _file_descriptor(
                    path=paths["teacher-markdown"],
                    kind="teacher-markdown",
                    media_type=_MARKDOWN_MEDIA_TYPE,
                    payload=payloads[paths["teacher-markdown"]],
                    lesson_id=sealed.lesson_id,
                ),
                _file_descriptor(
                    path=paths["preview-html"],
                    kind="preview-html",
                    media_type=_HTML_MEDIA_TYPE,
                    payload=payloads[paths["preview-html"]],
                    lesson_id=sealed.lesson_id,
                ),
            )
        )

        scenarios: list[CourseArchiveScenarioV1] = []
        for scenario_descriptor, primary in _scenario_references(item):
            scenario_raw = _read_content_relative_bytes(scenario_descriptor.path)
            scenario = _parse_json_model(
                scenario_raw,
                ScenarioTemplateV1,
                f"scenario {scenario_descriptor.artifact_id}",
            )
            if (
                scenario.status != "sealed"
                or not verify_contract_checksum(scenario)
                or scenario.checksum != scenario_descriptor.checksum
                or (
                    scenario.scenario_id,
                    scenario.course_id,
                    scenario.lesson_id,
                    scenario.scenario_version,
                )
                != (
                    scenario_descriptor.artifact_id,
                    item.course_id,
                    item.lesson_id,
                    scenario_descriptor.version,
                )
            ):
                raise ArchiveBuildError(
                    "scenario does not match release descriptor: "
                    f"{scenario_descriptor.artifact_id}"
                )
            target = scenario_archive_path(
                item.lesson_id,
                scenario.scenario_id,
                scenario.scenario_version,
            )
            payloads[target] = scenario_raw
            descriptors.append(
                _file_descriptor(
                    path=target,
                    kind="scenario-template",
                    media_type=_JSON_MEDIA_TYPE,
                    payload=scenario_raw,
                    lesson_id=item.lesson_id,
                    artifact_id=scenario.scenario_id,
                    artifact_version=scenario.scenario_version,
                    schema_version=scenario.schema_version,
                    contract_checksum=str(scenario.checksum),
                )
            )
            scenarios.append(
                CourseArchiveScenarioV1(
                    scenario_id=scenario.scenario_id,
                    scenario_version=scenario.scenario_version,
                    scenario_checksum=str(scenario.checksum),
                    primary=primary,
                )
            )

        for supplement_descriptor in _supplement_references(item):
            try:
                if supplement_descriptor.kind == "evidence-corpus":
                    runtime_artifacts.load_release_evidence(
                        supplement_descriptor
                    )
                else:
                    runtime_artifacts.load_release_presentation(
                        supplement_descriptor
                    )
            except runtime_artifacts.RuntimeArtifactError as exc:
                raise ArchiveBuildError(
                    "supplement or presentation assets failed verification: "
                    f"{supplement_descriptor.artifact_id}"
                ) from exc
            supplement_raw = _read_content_relative_bytes(
                supplement_descriptor.path
            )
            supplement = _parse_supplement(
                supplement_raw,
                supplement_descriptor.kind,
                item.lesson_id,
            )
            if (
                supplement.checksum != supplement_descriptor.checksum
                or supplement.course_id != item.course_id
                or supplement.lesson_id != item.lesson_id
            ):
                raise ArchiveBuildError(
                    "supplement does not match release descriptor: "
                    f"{supplement_descriptor.artifact_id}"
                )
            target = supplement_archive_path(
                item.lesson_id,
                supplement_descriptor.kind,
                supplement_descriptor.artifact_id,
                supplement_descriptor.version,
            )
            payloads[target] = supplement_raw
            descriptors.append(
                _file_descriptor(
                    path=target,
                    kind=supplement_descriptor.kind,
                    media_type=_JSON_MEDIA_TYPE,
                    payload=supplement_raw,
                    lesson_id=item.lesson_id,
                    artifact_id=supplement_descriptor.artifact_id,
                    artifact_version=supplement_descriptor.version,
                    schema_version=supplement_descriptor.schema_version,
                    contract_checksum=supplement_descriptor.checksum,
                )
            )

        lesson_paths = tuple(
            sorted(
                (
                    descriptor.path
                    for descriptor in descriptors
                    if descriptor.lesson_id == item.lesson_id
                ),
                key=str.casefold,
            )
        )
        lessons.append(
            CourseArchiveLessonV1(
                lesson_id=item.lesson_id,
                title=sealed.title,
                content_version=item.content_version,
                source_checksum=item.source_checksum,
                course_package_id=course.package_id,
                course_package_checksum=str(course.checksum),
                scenarios=tuple(sorted(scenarios, key=lambda value: value.scenario_id)),
                files=lesson_paths,
            )
        )

    sorted_descriptors = tuple(
        sorted(descriptors, key=lambda descriptor: descriptor.path.casefold())
    )
    if len(sorted_descriptors) > MAX_ARCHIVE_FILES:
        raise ArchiveBuildError(f"archive exceeds {MAX_ARCHIVE_FILES} described files")
    total_size = sum(item.size_bytes for item in sorted_descriptors)
    if total_size > MAX_ARCHIVE_TOTAL_BYTES:
        raise ArchiveBuildError(
            f"archive exceeds {MAX_ARCHIVE_TOTAL_BYTES} described bytes"
        )

    archive_payload = CourseArchivePayloadV1(
        course_id=release.course_id,
        course_title=course_title or release.course_id,
        release_schema_version=release.schema_version,
        release_id=release.release_id,
        release_no=release.release_no,
        release_checksum=release.checksum,
        release_operation=release.operation,
        release_created_at=release.created_at,
        release_created_by=release.created_by,
        release_note=release.note,
        renderer=ArchiveRendererV1(
            renderer_id=ARCHIVE_RENDERER_ID,
            renderer_version=ARCHIVE_RENDERER_VERSION,
            style_profile=ARCHIVE_STYLE_PROFILE,
        ),
        lessons=tuple(sorted(lessons, key=lambda lesson: lesson.lesson_id)),
        files=sorted_descriptors,
        file_count=len(sorted_descriptors),
        total_size_bytes=total_size,
    )
    archive_checksum = calculate_archive_payload_checksum(archive_payload)
    archive_id = archive_id_for_checksum(archive_checksum)
    manifest = sign_archive_manifest(
        CourseArchiveManifestV1(
            **archive_payload.model_dump(mode="json"),
            archive_id=archive_id,
            archive_checksum=archive_checksum,
            archive_path=archive_relative_path(
                release.course_id,
                release.release_id,
                archive_id,
            ),
            manifest_checksum="0" * 64,
        )
    )
    files = {
        ARCHIVE_MANIFEST_FILENAME: _json_bytes(manifest.model_dump(mode="json")),
        **payloads,
    }
    if sum(len(raw) for raw in files.values()) > MAX_ARCHIVE_TOTAL_BYTES:
        raise ArchiveBuildError(
            f"archive including its manifest exceeds {MAX_ARCHIVE_TOTAL_BYTES} bytes"
        )
    return BuiltCourseArchive(
        manifest=manifest,
        files=MappingProxyType(dict(sorted(files.items(), key=lambda item: item[0].casefold()))),
    )


def build_course_archive_zip(archive: BuiltCourseArchive) -> bytes:
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for path, raw in sorted(archive.files.items(), key=lambda item: item[0].casefold()):
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            bundle.writestr(info, raw, compress_type=ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def archive_download_filename(manifest: CourseArchiveManifestV1) -> str:
    course_name = safe_archive_filename(manifest.course_title, manifest.course_id)
    return f"{course_name}-课程归档-{manifest.release_id}.zip"


def _course_package_reference(item) -> tuple[str, str]:
    if hasattr(item, "course_package"):
        return item.course_package.path, item.course_package.checksum
    return item.package_path, item.package_checksum


def _scenario_references(item) -> tuple[tuple[object, bool], ...]:
    if not hasattr(item, "scenarios"):
        return ()
    return tuple(
        (
            descriptor,
            descriptor.artifact_id == item.primary_scenario_id,
        )
        for descriptor in item.scenarios
    )


def _supplement_references(item) -> tuple[object, ...]:
    if not hasattr(item, "evidence_corpus"):
        return ()
    return (item.evidence_corpus, item.lesson_presentation)


def _parse_supplement(raw: bytes, kind: str, lesson_id: str):
    from services.contracts.evidence_v1 import (
        EvidenceCorpusV1,
        LessonPresentationV1,
        verify_evidence_checksum,
    )

    model = {
        "evidence-corpus": EvidenceCorpusV1,
        "lesson-presentation": LessonPresentationV1,
    }[kind]
    supplement = _parse_json_model(raw, model, f"{kind} {lesson_id}")
    if not verify_evidence_checksum(supplement):
        raise ArchiveBuildError(f"{kind} failed checksum verification")
    return supplement


def _file_descriptor(
    *,
    path: str,
    kind: str,
    media_type: str,
    payload: bytes,
    lesson_id: str | None = None,
    artifact_id: str | None = None,
    artifact_version: int | None = None,
    schema_version: str | None = None,
    contract_checksum: str | None = None,
) -> CourseArchiveFileV1:
    if not payload:
        raise ArchiveBuildError(f"archive file is empty: {path}")
    if len(payload) > MAX_ARCHIVE_FILE_BYTES:
        raise ArchiveBuildError(
            f"archive file exceeds {MAX_ARCHIVE_FILE_BYTES} bytes: {path}"
        )
    return CourseArchiveFileV1(
        path=path,
        kind=kind,
        media_type=media_type,
        size_bytes=len(payload),
        blob_sha256=hashlib.sha256(payload).hexdigest(),
        lesson_id=lesson_id,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        schema_version=schema_version,
        contract_checksum=contract_checksum,
    )


def _read_content_relative_bytes(relative_path: str) -> bytes:
    if (
        not relative_path
        or "\\" in relative_path
        or relative_path.startswith("/")
        or PurePosixPath(relative_path).as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in relative_path.split("/"))
    ):
        raise ArchiveBuildError("release references an unsafe content path")
    return _read_content_bytes(
        content_data.content_root().joinpath(*PurePosixPath(relative_path).parts)
    )


def _read_content_bytes(path: Path) -> bytes:
    root = content_data.content_root().absolute()
    target = path.absolute()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ArchiveBuildError("archive source escaped the content root") from exc
    if not relative.parts:
        raise ArchiveBuildError("archive source is not a regular file")
    if os.name == "nt":
        return _read_content_bytes_windows(root, relative, target)
    return _read_content_bytes_posix(root, relative, target)


def _read_content_bytes_posix(
    root: Path,
    relative: Path,
    target: Path,
) -> bytes:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if (
        no_follow is None
        or directory_flag is None
        or os.open not in os.supports_dir_fd
    ):
        raise ArchiveBuildError(
            "platform cannot safely open archive sources without following links"
        )

    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | directory_flag | no_follow | close_on_exec
    file_flags = os.O_RDONLY | no_follow | close_on_exec
    parent_fd: int | None = None
    try:
        parent_fd = os.open(root, directory_flags)
        for part in relative.parts[:-1]:
            child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd

        file_name = relative.parts[-1]
        file_fd = os.open(file_name, file_flags, dir_fd=parent_fd)
        with os.fdopen(file_fd, "rb", closefd=True) as handle:
            opened_stat = os.fstat(handle.fileno())
            raw = _read_opened_archive_source(handle, opened_stat, target)
            current_stat = os.stat(
                file_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if not os.path.samestat(opened_stat, current_stat):
                raise ArchiveBuildError(
                    f"archive source changed while being verified: {target}"
                )
            return raw
    except ArchiveBuildError:
        raise
    except OSError as exc:
        raise ArchiveBuildError(f"cannot read archive source: {target}") from exc
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _read_content_bytes_windows(
    root: Path,
    relative: Path,
    target: Path,
) -> bytes:
    components = [root]
    current = root
    for part in relative.parts:
        current /= part
        components.append(current)

    try:
        snapshots = tuple(os.lstat(component) for component in components)
        if any(_is_windows_reparse_point(item) for item in snapshots):
            raise ArchiveBuildError(
                f"archive source cannot traverse a reparse point: {target}"
            )

        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOINHERIT", 0)
        )
        file_fd = os.open(target, flags)
        with os.fdopen(file_fd, "rb", closefd=True) as handle:
            opened_stat = os.fstat(handle.fileno())
            opened_path = _windows_final_path(handle.fileno())
            expected_path = root.resolve(strict=True).joinpath(*relative.parts)
            if os.path.normcase(os.path.normpath(str(opened_path))) != os.path.normcase(
                os.path.normpath(str(expected_path))
            ):
                raise ArchiveBuildError(
                    f"archive source escaped through a reparse point: {target}"
                )
            raw = _read_opened_archive_source(handle, opened_stat, target)
            current_stats = tuple(os.lstat(component) for component in components)
            if any(
                _is_windows_reparse_point(current)
                or not os.path.samestat(previous, current)
                for previous, current in zip(snapshots, current_stats, strict=True)
            ):
                raise ArchiveBuildError(
                    f"archive source changed while being verified: {target}"
                )
            return raw
    except ArchiveBuildError:
        raise
    except OSError as exc:
        raise ArchiveBuildError(f"cannot read archive source: {target}") from exc


def _read_opened_archive_source(handle, opened_stat, target: Path) -> bytes:
    if not stat_module.S_ISREG(opened_stat.st_mode):
        raise ArchiveBuildError(f"archive source is not a regular file: {target}")
    if opened_stat.st_size > MAX_ARCHIVE_FILE_BYTES:
        raise ArchiveBuildError(
            f"archive source exceeds {MAX_ARCHIVE_FILE_BYTES} bytes: {target}"
        )
    raw = handle.read(MAX_ARCHIVE_FILE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_FILE_BYTES:
        raise ArchiveBuildError(
            f"archive source exceeds {MAX_ARCHIVE_FILE_BYTES} bytes: {target}"
        )
    return raw


def _is_windows_reparse_point(path_stat) -> bool:
    reparse_attribute = getattr(
        stat_module,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        0x400,
    )
    return stat_module.S_ISLNK(path_stat.st_mode) or bool(
        getattr(path_stat, "st_file_attributes", 0) & reparse_attribute
    )


def _windows_final_path(file_descriptor: int) -> Path:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    get_final_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(file_descriptor))
    required = get_final_path(handle, None, 0, 0)
    if required == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_final_path(handle, buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _parse_json_model(raw: bytes, model: type[BaseModel], label: str):
    return _parse_json_contract(raw, model.model_validate, label)


def _parse_json_contract(raw: bytes, validator, label: str):
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        return validator(payload)
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
        TypeError,
    ) as exc:
        raise ArchiveBuildError(f"cannot validate {label}") from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _format_layer(item: LessonContentPackage) -> dict[str, object]:
    paragraphs: list[dict[str, object]] = []
    for index, paragraph in enumerate(item.body):
        level, text = _content_block(paragraph)
        paragraphs.append(
            {
                "index": index,
                "raw": paragraph,
                "block": f"heading_{level}" if level else "paragraph",
                "text": text,
                "segments": [
                    segment
                    for segment in _parse_content_markup(text)
                    if segment["marks"]
                ],
            }
        )
    return {
        "schema_version": "teacher-format-layer/v1",
        "renderer_version": ARCHIVE_RENDERER_VERSION,
        "lesson_id": item.lesson_id,
        "source_checksum": item.checksum,
        "syntax": {
            "bold": "**文字**",
            "highlight": "==标红文字==",
            "keyword": "【关键词】",
            "heading": "# 一级标题 / ## 二级标题 / ### 三级标题",
            "colors": "{{红色:文字}} / {{蓝色:文字}} / {{金色:文字}}",
            "font_size": "{{大字:文字}} / {{小字:文字}}",
        },
        "paragraphs": paragraphs,
    }


def _teacher_markdown(item: LessonContentPackage) -> str:
    lines = [
        f"# {_strip_inline_markup(item.title)}",
        "",
        f"- lesson_id: {item.lesson_id}",
        f"- course_id: {item.course_id}",
        f"- unit: {item.unit}",
        f"- era: {item.era}",
        f"- status: {item.status}",
        "",
        "## 正文",
    ]
    lines.extend(f"\n{paragraph}" for paragraph in item.body)
    lines.extend(["", "## 关键词"])
    lines.extend(
        f"- {keyword.word}{f'：{keyword.gloss}' if keyword.gloss else ''}"
        for keyword in item.keywords
    )
    lines.extend(["", "## 重点块"])
    lines.extend(f"- {fact}" for fact in item.facts)
    return "\n".join(lines) + "\n"


def _preview_html(item: LessonContentPackage) -> str:
    body = "\n".join(_preview_block_html(paragraph) for paragraph in item.body)
    keywords = "".join(
        f"<li><strong>{html.escape(keyword.word)}</strong>"
        f"{'：' + html.escape(keyword.gloss) if keyword.gloss else ''}</li>"
        for keyword in item.keywords
    )
    people = "".join(
        f"<li><strong>{html.escape(person.name)}</strong>"
        f"{' · ' + html.escape(person.role) if person.role else ''}<br>"
        f"{html.escape(person.summary)}</li>"
        for person in item.people
    )
    title = html.escape(_strip_inline_markup(item.title))
    metadata = " · ".join(
        html.escape(value)
        for value in (item.lesson_no, item.unit, item.era, item.duration)
        if value
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ margin: 0; padding: 40px; background: #f7f1e6; color: #2e2418; font-family: "Noto Serif SC", "Microsoft YaHei", serif; }}
    main {{ max-width: 880px; margin: 0 auto; background: #fffdf7; border: 1px solid #e6d9c3; border-radius: 8px; padding: 34px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    h2, h3, h4 {{ margin: 24px 0 10px; line-height: 1.45; }}
    h2 {{ font-size: 24px; }} h3 {{ font-size: 21px; }} h4 {{ font-size: 18px; }}
    .meta {{ color: #796c5a; margin-bottom: 24px; }}
    p {{ font-size: 17px; line-height: 2; text-indent: 2em; }}
    .keyword {{ color: #9b642e; font-weight: 700; border-bottom: 1px solid rgba(155,100,46,.35); }}
    mark {{ color: #9f2d20; background: rgba(198,65,47,.14); border-radius: 3px; padding: 0 3px; }}
    .text-red {{ color: #9f2d20; }} .text-blue {{ color: #315f91; }} .text-gold {{ color: #8b641b; }}
    .text-large {{ font-size: 1.14em; }} .text-small {{ font-size: .88em; }}
    aside {{ margin-top: 28px; display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    section {{ background: #f8f2e8; border-radius: 6px; padding: 16px; }}
    li {{ margin: 8px 0; line-height: 1.6; }}
    @media (max-width: 640px) {{ body {{ padding: 12px; }} main {{ padding: 22px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <div class="meta">{metadata}</div>
    {body}
    <aside>
      <section><h2>关键词</h2><ul>{keywords}</ul></section>
      <section><h2>人物</h2><ul>{people}</ul></section>
    </aside>
  </main>
</body>
</html>
"""


def _preview_block_html(paragraph: str) -> str:
    level, text = _content_block(paragraph)
    if level:
        tag = {1: "h2", 2: "h3", 3: "h4"}[level]
        return f"<{tag}>{_render_markup_html(text)}</{tag}>"
    return f"<p>{_render_markup_html(paragraph)}</p>"


def _content_block(value: str) -> tuple[int, str]:
    match = re.match(r"^\s*(#{1,3})\s+(.+)$", value)
    if match is None:
        return 0, value
    return len(match.group(1)), match.group(2).strip()


def _strip_inline_markup(value: str) -> str:
    current = value
    previous = ""
    custom = re.compile(r"\{\{\s*([^:}]{1,12})\s*:\s*([^{}]*)\}\}")
    while current != previous:
        previous = current
        current = custom.sub(
            lambda match: (
                match.group(2)
                if match.group(1).strip() in _INLINE_TOKEN_MARKS
                else match.group(0)
            ),
            current,
        )
    return (
        re.sub(r"\*\*([^*]+)\*\*", r"\1", current)
        .replace("==", "")
        .replace("【", "")
        .replace("】", "")
    )


def _parse_content_markup(
    value: str,
    inherited_marks: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    active = list(inherited_marks)
    buffer: list[str] = []
    index = 0

    def flush() -> None:
        if buffer:
            segments.append({"text": "".join(buffer), "marks": list(dict.fromkeys(active))})
            buffer.clear()

    while index < len(value):
        if value.startswith("**", index):
            flush()
            active = _toggle_mark(active, "bold")
            index += 2
            continue
        if value.startswith("==", index):
            flush()
            active = _toggle_mark(active, "highlight")
            index += 2
            continue
        if value[index] == "【":
            end = value.find("】", index + 1)
            if end > index:
                flush()
                segments.extend(
                    _parse_content_markup(
                        value[index + 1 : end],
                        tuple(_append_mark(active, "keyword")),
                    )
                )
                index = end + 1
                continue
        custom = _read_custom_token(value, index)
        if custom is not None:
            end, mark, text = custom
            flush()
            segments.extend(
                _parse_content_markup(text, tuple(_append_mark(active, mark)))
            )
            index = end
            continue
        buffer.append(value[index])
        index += 1
    flush()

    merged: list[dict[str, object]] = []
    for segment in segments:
        marks = list(segment["marks"])
        if (
            merged
            and sorted(merged[-1]["marks"]) == sorted(marks)
        ):
            merged[-1]["text"] = str(merged[-1]["text"]) + str(segment["text"])
        else:
            merged.append({"text": segment["text"], "marks": marks})
    return merged


def _read_custom_token(
    value: str,
    start: int,
) -> tuple[int, str, str] | None:
    if not value.startswith("{{", start):
        return None
    end = value.find("}}", start + 2)
    if end < 0:
        return None
    content = value[start + 2 : end]
    separator = content.find(":")
    if separator < 0:
        return None
    mark = _INLINE_TOKEN_MARKS.get(content[:separator].strip())
    if mark is None:
        return None
    return end + 2, mark, content[separator + 1 :]


def _append_mark(marks: list[str], mark: str) -> list[str]:
    return marks if mark in marks else [*marks, mark]


def _toggle_mark(marks: list[str], mark: str) -> list[str]:
    return [value for value in marks if value != mark] if mark in marks else [*marks, mark]


def _render_markup_html(value: str) -> str:
    output: list[str] = []
    for segment in _parse_content_markup(value):
        rendered = html.escape(str(segment["text"]), quote=True)
        marks = segment["marks"]
        if "keyword" in marks:
            rendered = f'<span class="keyword">{rendered}</span>'
        if "highlight" in marks:
            rendered = f"<mark>{rendered}</mark>"
        for mark in ("red", "blue", "gold", "large", "small"):
            if mark in marks:
                rendered = f'<span class="text-{mark}">{rendered}</span>'
        if "bold" in marks:
            rendered = f"<strong>{rendered}</strong>"
        output.append(rendered)
    return "".join(output)


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
