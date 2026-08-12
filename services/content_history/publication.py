from __future__ import annotations

import json
import os
import stat as stat_module
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services import persistence
from services.contracts.archive_v1 import (
    ContentAssetKind,
    CourseArchivePublishRequestV1,
    GitPublicationIntentV1,
    GitPublicationRecordV1,
    GitRepositoryBindingV1,
    PublicationMode,
    PublicationRequestV1,
    PublicationStatus,
    publication_branch_name_for_request,
    publication_id_for_key,
    publication_operation_key,
    sign_publication_metadata,
    parse_signed_publication_record,
)


PUBLICATION_NAMESPACE = "content-history-publications/v1"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAX_TARGET_CONFIG_BYTES = 64 * 1024


class PublicationError(RuntimeError):
    code = "content_publication_failed"


class PublicationConfigurationError(PublicationError):
    code = "content_publication_configuration_invalid"


class PublicationDisabled(PublicationConfigurationError):
    code = "content_publication_disabled"


class PublicationNotFound(PublicationError):
    code = "content_publication_not_found"


class PublicationConflict(PublicationError):
    code = "content_publication_conflict"


class PublicationStoreError(PublicationError):
    code = "content_publication_store_failed"


class _TargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetCredentialPolicy(_TargetModel):
    preferred: Literal["github_app"]
    transitional_fallback: Literal["fine_grained_token"]
    committed_credentials: Literal[False]


class TargetActivation(_TargetModel):
    repository_ready: bool
    runtime_publication_enabled: bool
    reason: str = ""


class ContentHistoryTargetV1(_TargetModel):
    schema_version: Literal["content-history-target/v1"]
    binding_id: str
    provider: Literal["github"]
    repository_id: int = Field(ge=1)
    owner: str
    repository: str
    visibility: Literal["private"]
    base_branch: str
    root_prefix: str
    asset_root_prefix: str
    default_publication_mode: PublicationMode
    allowed_publication_modes: tuple[PublicationMode, ...]
    direct_commit_requires_confirmation: Literal[True]
    credential_policy: TargetCredentialPolicy
    activation: TargetActivation
    contract_source: dict[str, object]
    remote_baseline: dict[str, object]
    publication_acceptance: dict[str, object] | None = None


class PublicationStore:
    def create_or_get(
        self,
        record: GitPublicationRecordV1,
    ) -> tuple[GitPublicationRecordV1, bool]:
        payload = record.model_dump(mode="json")
        if persistence.kv_compare_and_set(
            PUBLICATION_NAMESPACE,
            record.intent.operation_key,
            None,
            payload,
            expected_present=False,
        ):
            return record, True
        existing = self.get_by_operation_key(record.intent.operation_key)
        if existing.intent.publication_id != record.intent.publication_id:
            raise PublicationStoreError("publication identity collision")
        return existing, False

    def get_by_operation_key(self, operation_key: str) -> GitPublicationRecordV1:
        payload = persistence.kv_get(PUBLICATION_NAMESPACE, operation_key)
        if payload is None:
            raise PublicationNotFound("publication was not found")
        record = _parse_record(payload)
        if record.intent.operation_key != operation_key:
            raise PublicationStoreError("stored publication key does not match its record")
        return record

    def get(self, publication_id: str) -> GitPublicationRecordV1:
        matches = [
            record
            for record in self.list()
            if record.intent.publication_id == publication_id
        ]
        if not matches:
            raise PublicationNotFound(f"publication was not found: {publication_id}")
        if len(matches) != 1:
            raise PublicationStoreError("publication id is not unique")
        return matches[0]

    def list(
        self,
        *,
        publication_kind: Literal["course", "asset"] | None = None,
        course_id: str | None = None,
        release_id: str | None = None,
        asset_kind: ContentAssetKind | None = None,
        asset_id: str | None = None,
        asset_version: int | None = None,
        status: PublicationStatus | None = None,
    ) -> tuple[GitPublicationRecordV1, ...]:
        records = tuple(_parse_record(payload) for payload in persistence.kv_list(PUBLICATION_NAMESPACE))

        def matches(record: GitPublicationRecordV1) -> bool:
            request = record.intent.request
            if isinstance(request, CourseArchivePublishRequestV1):
                if publication_kind == "asset":
                    return False
                if asset_kind is not None or asset_id is not None or asset_version is not None:
                    return False
                return (
                    (course_id is None or request.course_id == course_id)
                    and (release_id is None or request.release_id == release_id)
                    and (status is None or record.status == status)
                )
            if publication_kind == "course":
                return False
            if course_id is not None or release_id is not None:
                return False
            return (
                (asset_kind is None or request.asset_kind == asset_kind)
                and (asset_id is None or request.asset_id == asset_id)
                and (asset_version is None or request.version == asset_version)
                and (status is None or record.status == status)
            )

        return tuple(
            sorted(
                (record for record in records if matches(record)),
                key=lambda record: (
                    record.intent.requested_at,
                    record.intent.publication_id,
                ),
                reverse=True,
            )
        )

    def checkpoint(
        self,
        previous: GitPublicationRecordV1,
        current: GitPublicationRecordV1,
    ) -> GitPublicationRecordV1:
        if (
            previous.intent.operation_key != current.intent.operation_key
            or previous.intent.checksum != current.intent.checksum
            or current.revision != previous.revision + 1
        ):
            raise PublicationStoreError("publication checkpoint is not a valid successor")
        if not persistence.kv_compare_and_set(
            PUBLICATION_NAMESPACE,
            previous.intent.operation_key,
            previous.model_dump(mode="json"),
            current.model_dump(mode="json"),
            expected_present=True,
        ):
            raise PublicationConflict("publication changed concurrently")
        return current


def load_repository_binding(
    target_path: str | Path,
) -> GitRepositoryBindingV1:
    configured = Path(target_path)
    path = configured if configured.is_absolute() else _REPO_ROOT / configured
    target = _read_target(path)
    if not target.activation.repository_ready:
        raise PublicationConfigurationError("content history repository is not ready")
    return GitRepositoryBindingV1(
        binding_id=target.binding_id,
        repository_id=target.repository_id,
        owner=target.owner,
        repository=target.repository,
        visibility=target.visibility,
        base_branch=target.base_branch,
        root_prefix=target.root_prefix,
        asset_root_prefix=target.asset_root_prefix,
        credential_kind="fine_grained_token",
        allowed_modes=target.allowed_publication_modes,
    )


def new_publication_record(
    binding: GitRepositoryBindingV1,
    request: PublicationRequestV1,
    *,
    requested_by: str,
    requested_at: datetime | None = None,
) -> GitPublicationRecordV1:
    timestamp = requested_at or datetime.now(timezone.utc)
    operation_key = publication_operation_key(binding, request)
    intent = sign_publication_metadata(
        GitPublicationIntentV1(
            publication_id=publication_id_for_key(operation_key),
            operation_key=operation_key,
            binding=binding,
            request=request,
            requested_at=timestamp,
            requested_by=requested_by,
            checksum="0" * 64,
        )
    )
    branch_ref = (
        publication_branch_name_for_request(request)
        if request.mode == "pull_request"
        else binding.base_branch
    )
    return sign_publication_metadata(
        GitPublicationRecordV1(
            intent=intent,
            status="requested",
            attempt=0,
            revision=0,
            branch_ref=branch_ref,
            updated_at=timestamp,
            checksum="0" * 64,
        )
    )


def publication_checkpoint(
    record: GitPublicationRecordV1,
    *,
    status: PublicationStatus,
    updated_at: datetime,
    attempt: int | None = None,
    completed_at: datetime | None = None,
    base_sha: str | None | object = ...,
    tree_sha: str | None | object = ...,
    commit_sha: str | None | object = ...,
    pull_request_number: int | None | object = ...,
    pull_request_url: str | None | object = ...,
    last_error_code: str | None | object = ...,
    last_error_at: datetime | None | object = ...,
) -> GitPublicationRecordV1:
    data = record.model_dump(mode="json")
    data.update(
        {
            "status": status,
            "attempt": record.attempt if attempt is None else attempt,
            "revision": record.revision + 1,
            "updated_at": max(updated_at, record.updated_at),
            "completed_at": completed_at,
            "checksum": "0" * 64,
        }
    )
    optional = {
        "base_sha": base_sha,
        "tree_sha": tree_sha,
        "commit_sha": commit_sha,
        "pull_request_number": pull_request_number,
        "pull_request_url": pull_request_url,
        "last_error_code": last_error_code,
        "last_error_at": last_error_at,
    }
    data.update({key: value for key, value in optional.items() if value is not ...})
    return sign_publication_metadata(GitPublicationRecordV1.model_validate(data))


def _read_target(path: Path) -> ContentHistoryTargetV1:
    try:
        with path.open("rb") as handle:
            opened_stat = os.fstat(handle.fileno())
            if (
                not stat_module.S_ISREG(opened_stat.st_mode)
                or opened_stat.st_size > _MAX_TARGET_CONFIG_BYTES
            ):
                raise PublicationConfigurationError(
                    "content history target must be a bounded regular file"
                )
            raw = handle.read(_MAX_TARGET_CONFIG_BYTES + 1)
            path_stat = os.lstat(path)
            if (
                stat_module.S_ISLNK(path_stat.st_mode)
                or not os.path.samestat(opened_stat, path_stat)
            ):
                raise PublicationConfigurationError(
                    "content history target changed while being verified"
                )
        if len(raw) > _MAX_TARGET_CONFIG_BYTES:
            raise PublicationConfigurationError("content history target is too large")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        return ContentHistoryTargetV1.model_validate(payload)
    except PublicationConfigurationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise PublicationConfigurationError(
            "cannot validate the content history target"
        ) from exc


def _parse_record(payload: object) -> GitPublicationRecordV1:
    try:
        return parse_signed_publication_record(payload)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PublicationStoreError("stored publication record failed validation") from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
