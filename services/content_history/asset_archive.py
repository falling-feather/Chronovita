from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pydantic import TypeAdapter, ValidationError

from services import content as content_data
from services.content import runtime_artifacts
from services.content_history.archive import (
    ArchiveBuildError,
    _parse_json_model,
    _read_content_bytes,
)
from services.contracts.archive_v1 import (
    ASSET_ARCHIVE_MANIFEST_FILENAME,
    ContentAssetArchiveFileV1,
    ContentAssetArchiveManifestV1,
    ContentAssetArchivePayloadV1,
    ContentAssetKind,
    archive_id_for_checksum,
    calculate_content_asset_archive_payload_checksum,
    content_asset_archive_relative_path,
    content_asset_archive_source_path,
    safe_archive_filename,
    sign_content_asset_archive_manifest,
)
from services.contracts.v1 import (
    Checksum,
    ContractId,
    ScenarioTemplateV1,
    verify_contract_checksum,
)


class ContentAssetArchiveBuildError(ArchiveBuildError):
    code = "content_asset_archive_build_failed"


class ContentAssetArchiveChanged(RuntimeError):
    code = "content_asset_archive_changed"


_ASSET_ID_ADAPTER = TypeAdapter(ContractId)
_CHECKSUM_ADAPTER = TypeAdapter(Checksum)


@dataclass(frozen=True)
class BuiltContentAssetArchive:
    manifest: ContentAssetArchiveManifestV1
    files: Mapping[str, bytes]

    def __post_init__(self) -> None:
        expected = {
            ASSET_ARCHIVE_MANIFEST_FILENAME,
            *(item.path for item in self.manifest.files),
        }
        if set(self.files) != expected:
            raise ContentAssetArchiveBuildError(
                "asset archive files do not match the signed manifest"
            )
        for item in self.manifest.files:
            raw = self.files[item.path]
            if (
                len(raw) != item.size_bytes
                or hashlib.sha256(raw).hexdigest() != item.blob_sha256
            ):
                raise ContentAssetArchiveBuildError(
                    f"asset archive bytes do not match descriptor: {item.path}"
                )


def build_content_asset_archive(
    asset_kind: ContentAssetKind,
    asset_id: str,
    version: int,
    *,
    expected_source_checksum: str | None = None,
) -> BuiltContentAssetArchive:
    try:
        checked_asset_id = _ASSET_ID_ADAPTER.validate_python(asset_id)
        if checked_asset_id != asset_id:
            raise ValueError("asset_id must already be normalized")
        if version < 1:
            raise ValueError("content asset version must be at least 1")
        if expected_source_checksum is not None:
            checked_checksum = _CHECKSUM_ADAPTER.validate_python(
                expected_source_checksum
            )
            if checked_checksum != expected_source_checksum:
                raise ValueError(
                    "source checksum must already be normalized"
                )
    except ValidationError as exc:
        raise ValueError("invalid content asset archive identity") from exc

    try:
        source, raw = _load_source(asset_kind, checked_asset_id, version)
    except FileNotFoundError:
        raise
    except ContentAssetArchiveChanged:
        raise
    except ContentAssetArchiveBuildError:
        raise
    except Exception as exc:
        raise ContentAssetArchiveBuildError(
            "cannot verify the requested content asset"
        ) from exc

    checksum = str(source["checksum"])
    if expected_source_checksum is not None and checksum != expected_source_checksum:
        raise ContentAssetArchiveChanged(
            "content asset checksum changed after selection"
        )
    path = content_asset_archive_source_path(
        asset_kind,
        asset_id,
        str(source["title"]),
    )
    descriptor = ContentAssetArchiveFileV1(
        path=path,
        kind={
            "person": "sealed-person",
            "keyword": "sealed-keyword",
            "scenario": "sealed-scenario",
        }[asset_kind],
        size_bytes=len(raw),
        blob_sha256=hashlib.sha256(raw).hexdigest(),
        schema_version=str(source["schema_version"]),
        contract_checksum=checksum,
    )
    payload = ContentAssetArchivePayloadV1(
        asset_kind=asset_kind,
        asset_id=asset_id,
        title=str(source["title"]),
        version=version,
        source_schema_version=str(source["schema_version"]),
        source_checksum=checksum,
        sealed_at=source["sealed_at"],
        sealed_by=str(source["sealed_by"]),
        files=(descriptor,),
        file_count=1,
        total_size_bytes=len(raw),
    )
    archive_checksum = calculate_content_asset_archive_payload_checksum(payload)
    archive_id = archive_id_for_checksum(archive_checksum)
    manifest = sign_content_asset_archive_manifest(
        ContentAssetArchiveManifestV1(
            **payload.model_dump(mode="json"),
            archive_id=archive_id,
            archive_checksum=archive_checksum,
            archive_path=content_asset_archive_relative_path(
                asset_kind,
                asset_id,
                version,
                archive_id,
            ),
            manifest_checksum="0" * 64,
        )
    )
    files = {
        ASSET_ARCHIVE_MANIFEST_FILENAME: _json_bytes(
            manifest.model_dump(mode="json")
        ),
        path: raw,
    }
    return BuiltContentAssetArchive(
        manifest=manifest,
        files=MappingProxyType(
            dict(sorted(files.items(), key=lambda item: item[0].casefold()))
        ),
    )


def build_content_asset_archive_zip(
    archive: BuiltContentAssetArchive,
) -> bytes:
    output = BytesIO()
    with ZipFile(
        output,
        mode="w",
        compression=ZIP_DEFLATED,
        compresslevel=9,
    ) as bundle:
        for path, raw in sorted(
            archive.files.items(),
            key=lambda item: item[0].casefold(),
        ):
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            bundle.writestr(
                info,
                raw,
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def content_asset_archive_download_filename(
    manifest: ContentAssetArchiveManifestV1,
) -> str:
    title = safe_archive_filename(manifest.title, manifest.asset_id)
    label = {
        "person": "人物档案",
        "keyword": "关键词档案",
        "scenario": "关卡规则",
    }[manifest.asset_kind]
    return f"{title}-{label}-v{manifest.version:03d}-归档.zip"


def _load_source(
    asset_kind: ContentAssetKind,
    asset_id: str,
    version: int,
) -> tuple[dict[str, object], bytes]:
    if asset_kind == "person":
        content_data.get_sealed_person_profile(asset_id, version)
        path = (
            content_data.sealed_people_asset_dir()
            / f"{asset_id}-v{version:03d}.json"
        )
        raw = _read_content_bytes(path)
        item = _parse_json_model(
            raw,
            content_data.PersonProfilePackage,
            "sealed person profile",
        )
        if (
            item.asset_id != asset_id
            or item.version != version
            or item.status != "sealed"
            or not content_data.verify_package_checksum(item)
        ):
            raise ContentAssetArchiveBuildError(
                "sealed person profile identity or checksum changed"
            )
        return (
            {
                "schema_version": item.schema_version,
                "title": item.name,
                "checksum": item.checksum,
                "sealed_at": item.sealed_at,
                "sealed_by": item.sealed_by,
            },
            raw,
        )
    if asset_kind == "keyword":
        content_data.get_sealed_keyword_profile(asset_id, version)
        path = (
            content_data.sealed_keyword_asset_dir()
            / f"{asset_id}-v{version:03d}.json"
        )
        raw = _read_content_bytes(path)
        item = _parse_json_model(
            raw,
            content_data.KeywordProfilePackage,
            "sealed keyword profile",
        )
        if (
            item.asset_id != asset_id
            or item.version != version
            or item.status != "sealed"
            or not content_data.verify_package_checksum(item)
        ):
            raise ContentAssetArchiveBuildError(
                "sealed keyword profile identity or checksum changed"
            )
        return (
            {
                "schema_version": item.schema_version,
                "title": item.word,
                "checksum": item.checksum,
                "sealed_at": item.sealed_at,
                "sealed_by": item.sealed_by,
            },
            raw,
        )

    matching = [
        record
        for record in runtime_artifacts.list_staged_scenarios(
            scenario_id=asset_id
        )
        if record.descriptor.version == version
    ]
    if not matching:
        raise FileNotFoundError(
            f"sealed scenario was not found: {asset_id} v{version}"
        )
    if len(matching) != 1:
        raise ContentAssetArchiveBuildError(
            "sealed scenario identity is ambiguous"
        )
    record = matching[0]
    raw, descriptor = runtime_artifacts.load_staged_scenario_bytes(
        course_id=record.descriptor.course_id,
        lesson_id=record.descriptor.lesson_id,
        scenario_id=asset_id,
        scenario_version=version,
        scenario_checksum=record.descriptor.checksum,
    )
    scenario = _parse_json_model(
        raw,
        ScenarioTemplateV1,
        "sealed scenario",
    )
    if (
        scenario.scenario_id != asset_id
        or scenario.scenario_version != version
        or scenario.status != "sealed"
        or scenario.checksum != descriptor.checksum
        or not verify_contract_checksum(scenario)
    ):
        raise ContentAssetArchiveBuildError(
            "sealed scenario identity or checksum changed"
        )
    return (
        {
            "schema_version": scenario.schema_version,
            "title": scenario.title,
            "checksum": scenario.checksum,
            "sealed_at": scenario.sealed_at,
            "sealed_by": scenario.sealed_by,
        },
        raw,
    )


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


__all__ = [
    "BuiltContentAssetArchive",
    "ContentAssetArchiveBuildError",
    "ContentAssetArchiveChanged",
    "build_content_asset_archive",
    "build_content_asset_archive_zip",
    "content_asset_archive_download_filename",
]
