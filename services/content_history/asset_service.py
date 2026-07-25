from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from services.content_history.asset_archive import (
    BuiltContentAssetArchive,
    ContentAssetArchiveBuildError,
    ContentAssetArchiveChanged,
    build_content_asset_archive,
)
from services.content_history.github import GitHubGitDataError
from services.content_history.publication import (
    PublicationConfigurationError,
    PublicationConflict,
    PublicationStore,
    new_publication_record,
    publication_checkpoint,
)
from services.content_history.service import (
    GitHubPublicationClient,
    PublicationArchiveChanged,
    PublicationRetryRejected,
    PublicationSubmission,
)
from services.contracts.archive_v1 import (
    ContentAssetArchivePublishRequestV1,
    GitPublicationRecordV1,
    GitRepositoryBindingV1,
    PublicationStatus,
    content_asset_repository_archive_path,
)


_COMMIT_AUTHOR_NAME = "Chronovita Publisher"
_COMMIT_AUTHOR_EMAIL = "content-publisher@chronovita.local"
_IN_PROGRESS_STATUSES = {
    "preparing",
    "pushing",
    "commit_created",
    "ref_updated",
    "pr_open",
}


class ContentAssetPublicationService:
    def __init__(
        self,
        *,
        binding: GitRepositoryBindingV1,
        github: GitHubPublicationClient,
        store: PublicationStore | None = None,
        archive_builder: Callable[..., BuiltContentAssetArchive] = (
            build_content_asset_archive
        ),
        stale_after_seconds: int = 600,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if stale_after_seconds < 60:
            raise ValueError("stale_after_seconds must be at least 60")
        self.binding = binding
        self.github = github
        self.store = store or PublicationStore()
        self.archive_builder = archive_builder
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def submit(
        self,
        request: ContentAssetArchivePublishRequestV1,
        *,
        requested_by: str,
    ) -> PublicationSubmission:
        archive = self._build_archive(request)
        self._verify_archive_request(request, archive)
        proposed = new_publication_record(
            self.binding,
            request,
            requested_by=requested_by,
            requested_at=self._now(),
        )
        record, created = self.store.create_or_get(proposed)
        if not created:
            if record.status == "requested":
                claimed = self._claim_requested(record)
                if claimed is not None:
                    record = await self._process(claimed, archive=archive)
                else:
                    record = self.store.get(record.intent.publication_id)
            return PublicationSubmission(publication=record, reused=True)

        claimed = self._claim_requested(record)
        if claimed is None:
            return PublicationSubmission(
                publication=self.store.get(record.intent.publication_id),
                reused=True,
            )
        return PublicationSubmission(
            publication=await self._process(claimed, archive=archive),
            reused=False,
        )

    async def retry(
        self,
        publication_id: str,
        *,
        expected_revision: int | None = None,
    ) -> GitPublicationRecordV1:
        record = self.store.get(publication_id)
        request = record.intent.request
        if not isinstance(request, ContentAssetArchivePublishRequestV1):
            raise PublicationRetryRejected(
                "publication does not describe a content asset"
            )
        if record.intent.binding != self.binding:
            raise PublicationRetryRejected(
                "repository binding changed; create a new publication"
            )
        if expected_revision is not None and record.revision != expected_revision:
            raise PublicationRetryRejected("publication revision changed")
        if record.status in {"succeeded", "failed_terminal"}:
            raise PublicationRetryRejected(
                f"publication in {record.status} cannot be retried"
            )
        if record.status in _IN_PROGRESS_STATUSES and (
            self._now() - record.updated_at < self.stale_after
        ):
            raise PublicationRetryRejected("publication is still being processed")
        if record.status not in {"failed_retryable", *_IN_PROGRESS_STATUSES}:
            raise PublicationRetryRejected(
                f"publication in {record.status} cannot be retried"
            )

        resumed = self._resume_checkpoint(record)
        try:
            self.store.checkpoint(record, resumed)
        except PublicationConflict:
            raise PublicationRetryRejected(
                "publication retry lost a concurrent race"
            ) from None
        return await self._process(resumed)

    def list(
        self,
        *,
        asset_kind=None,
        asset_id: str | None = None,
        asset_version: int | None = None,
        status: PublicationStatus | None = None,
    ) -> tuple[GitPublicationRecordV1, ...]:
        return self.store.list(
            publication_kind="asset",
            asset_kind=asset_kind,
            asset_id=asset_id,
            asset_version=asset_version,
            status=status,
        )

    def _build_archive(
        self,
        request: ContentAssetArchivePublishRequestV1,
    ) -> BuiltContentAssetArchive:
        return self.archive_builder(
            request.asset_kind,
            request.asset_id,
            request.version,
            expected_source_checksum=request.expected_source_checksum,
        )

    def _claim_requested(
        self,
        record: GitPublicationRecordV1,
    ) -> GitPublicationRecordV1 | None:
        preparing = publication_checkpoint(
            record,
            status="preparing",
            attempt=1,
            updated_at=self._now(),
        )
        try:
            return self.store.checkpoint(record, preparing)
        except PublicationConflict:
            return None

    def _resume_checkpoint(
        self,
        record: GitPublicationRecordV1,
    ) -> GitPublicationRecordV1:
        request = record.intent.request
        assert isinstance(request, ContentAssetArchivePublishRequestV1)
        if (
            request.mode == "direct_commit"
            and record.last_error_code == "github_ref_conflict"
        ):
            return publication_checkpoint(
                record,
                status="preparing",
                attempt=record.attempt + 1,
                updated_at=self._now(),
                base_sha=None,
                tree_sha=None,
                commit_sha=None,
                pull_request_number=None,
                pull_request_url=None,
                last_error_code=None,
                last_error_at=None,
            )
        if record.pull_request_number is not None:
            status: PublicationStatus = "pr_open"
        elif record.commit_sha is not None:
            status = "commit_created"
        elif record.base_sha is not None:
            status = "pushing"
        else:
            status = "preparing"
        return publication_checkpoint(
            record,
            status=status,
            attempt=record.attempt + 1,
            updated_at=self._now(),
            last_error_code=None,
            last_error_at=None,
        )

    async def _process(
        self,
        record: GitPublicationRecordV1,
        *,
        archive: BuiltContentAssetArchive | None = None,
    ) -> GitPublicationRecordV1:
        request = record.intent.request
        if not isinstance(request, ContentAssetArchivePublishRequestV1):
            raise PublicationRetryRejected(
                "publication does not describe a content asset"
            )
        try:
            archive = archive or self._build_archive(request)
            self._verify_archive_request(request, archive)

            if record.status == "preparing":
                repository = await self.github.verify_repository()
                if (
                    repository.repository_id != self.binding.repository_id
                    or repository.full_name != self.binding.full_name
                    or (
                        repository.default_branch is not None
                        and repository.default_branch != self.binding.base_branch
                    )
                ):
                    raise PublicationConfigurationError(
                        "GitHub repository no longer matches its binding"
                    )
                head = await self.github.get_branch_head(self.binding.base_branch)
                record = self._save(
                    record,
                    status="pushing",
                    base_sha=head.commit_sha,
                )

            if record.status == "pushing":
                assert record.base_sha is not None
                if record.tree_sha is None:
                    base_commit = await self.github.get_commit(record.base_sha)
                    blobs: dict[str, str] = {}
                    archive_root = content_asset_repository_archive_path(
                        self.binding,
                        archive.manifest
                    )
                    for path, raw in sorted(
                        archive.files.items(),
                        key=lambda item: item[0].casefold(),
                    ):
                        blobs[f"{archive_root}/{path}"] = (
                            await self.github.create_blob(raw)
                        )
                    tree_sha = await self.github.create_tree(
                        base_tree_sha=base_commit.tree_sha,
                        entries=blobs,
                    )
                    record = self._save(
                        record,
                        status="pushing",
                        tree_sha=tree_sha,
                    )

                assert record.tree_sha is not None
                commit_sha = await self.github.create_commit(
                    message=self._commit_message(record, archive),
                    tree_sha=record.tree_sha,
                    parent_sha=record.base_sha,
                    author_name=_COMMIT_AUTHOR_NAME,
                    author_email=_COMMIT_AUTHOR_EMAIL,
                    authored_at=record.intent.requested_at,
                )
                record = self._save(
                    record,
                    status="commit_created",
                    commit_sha=commit_sha,
                )

            if record.status == "commit_created":
                assert record.base_sha is not None
                assert record.commit_sha is not None
                if request.mode == "pull_request":
                    await self.github.create_or_update_branch(
                        branch=record.branch_ref,
                        target_sha=record.commit_sha,
                        expected_sha=record.base_sha,
                    )
                else:
                    await self.github.update_branch_non_force(
                        branch=self.binding.base_branch,
                        target_sha=record.commit_sha,
                        expected_sha=record.base_sha,
                    )
                record = self._save(record, status="ref_updated")

            if record.status == "ref_updated":
                if request.mode == "direct_commit":
                    return self._save(
                        record,
                        status="succeeded",
                        completed_at=self._now(),
                    )
                pull_request = await self.github.create_or_find_pull_request(
                    head_branch=record.branch_ref,
                    base_branch=self.binding.base_branch,
                    title=(
                        f"{self._kind_label(request.asset_kind)}审核："
                        f"{archive.manifest.title}"
                    ),
                    body=self._pull_request_body(record, archive),
                )
                record = self._save(
                    record,
                    status="pr_open",
                    pull_request_number=pull_request.number,
                    pull_request_url=pull_request.url,
                )

            if record.status == "pr_open":
                return self._save(
                    record,
                    status="succeeded",
                    completed_at=self._now(),
                )
            return record
        except GitHubGitDataError as exc:
            return self._save_failure(
                record,
                error_code=exc.code.value,
                retryable=exc.retryable,
            )
        except (
            ContentAssetArchiveChanged,
            ContentAssetArchiveBuildError,
            PublicationArchiveChanged,
            PublicationConfigurationError,
        ) as exc:
            return self._save_failure(
                record,
                error_code=exc.code,
                retryable=False,
            )

    def _save(
        self,
        record: GitPublicationRecordV1,
        *,
        status: PublicationStatus,
        completed_at: datetime | None = None,
        **updates,
    ) -> GitPublicationRecordV1:
        current = publication_checkpoint(
            record,
            status=status,
            updated_at=self._now(),
            completed_at=completed_at,
            last_error_code=None,
            last_error_at=None,
            **updates,
        )
        return self.store.checkpoint(record, current)

    def _save_failure(
        self,
        record: GitPublicationRecordV1,
        *,
        error_code: str,
        retryable: bool,
    ) -> GitPublicationRecordV1:
        timestamp = self._now()
        failed = publication_checkpoint(
            record,
            status="failed_retryable" if retryable else "failed_terminal",
            updated_at=timestamp,
            completed_at=None if retryable else timestamp,
            last_error_code=error_code,
            last_error_at=timestamp,
        )
        try:
            return self.store.checkpoint(record, failed)
        except PublicationConflict:
            return self.store.get(record.intent.publication_id)

    def _verify_archive_request(
        self,
        request: ContentAssetArchivePublishRequestV1,
        archive: BuiltContentAssetArchive,
    ) -> None:
        manifest = archive.manifest
        if request.binding_id != self.binding.binding_id:
            raise PublicationConfigurationError(
                "publication request selected an unknown repository binding"
            )
        if request.mode not in self.binding.allowed_modes:
            raise PublicationConfigurationError(
                "publication mode is disabled by repository policy"
            )
        if (
            request.asset_kind,
            request.asset_id,
            request.version,
            request.expected_source_checksum,
            request.archive_id,
            request.expected_archive_checksum,
        ) != (
            manifest.asset_kind,
            manifest.asset_id,
            manifest.version,
            manifest.source_checksum,
            manifest.archive_id,
            manifest.archive_checksum,
        ):
            raise PublicationArchiveChanged(
                "content asset archive changed after it was previewed"
            )

    @classmethod
    def _commit_message(
        cls,
        record: GitPublicationRecordV1,
        archive: BuiltContentAssetArchive,
    ) -> str:
        request = record.intent.request
        assert isinstance(request, ContentAssetArchivePublishRequestV1)
        summary = request.change_summary.strip()
        lines = [
            f"{cls._kind_label(request.asset_kind)}：{archive.manifest.title}",
            "",
            f"asset: {request.asset_id}",
            f"version: {request.version}",
            f"archive: {request.archive_id}",
            f"requested-by: {record.intent.requested_by}",
        ]
        if summary:
            lines.extend(("", summary))
        return "\n".join(lines)

    @classmethod
    def _pull_request_body(
        cls,
        record: GitPublicationRecordV1,
        archive: BuiltContentAssetArchive,
    ) -> str:
        request = record.intent.request
        assert isinstance(request, ContentAssetArchivePublishRequestV1)
        summary = request.change_summary.strip() or "未填写补充说明。"
        return "\n".join(
            (
                f"## {cls._kind_label(request.asset_kind)}",
                "",
                f"- 标题：{archive.manifest.title}",
                f"- 内容 ID：`{request.asset_id}`",
                f"- 封存版本：`v{request.version:03d}`",
                f"- 归档：`{request.archive_id}`",
                f"- 文件数：{len(archive.files)}",
                "",
                "## 教师说明",
                "",
                summary,
                "",
                "> 本 Pull Request 由 Chronovita 内容资产发布服务生成。",
            )
        )

    @staticmethod
    def _kind_label(kind: str) -> str:
        return {
            "person": "人物档案",
            "keyword": "关键词档案",
            "scenario": "关卡规则",
        }[kind]

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publication clock must return an aware datetime")
        return value


__all__ = ["ContentAssetPublicationService"]
