from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from services.content_history.archive import (
    ArchiveBuildError,
    BuiltCourseArchive,
    build_course_archive,
)
from services.content_history.github import (
    GitBranchHead,
    GitBranchUpdate,
    GitCommitObject,
    GitHubGitDataError,
    GitHubRepositoryIdentity,
    GitPullRequest,
)
from services.content_history.publication import (
    PublicationConfigurationError,
    PublicationConflict,
    PublicationStore,
    new_publication_record,
    publication_checkpoint,
)
from services.contracts.archive_v1 import (
    CourseArchivePublishRequestV1,
    GitPublicationRecordV1,
    GitRepositoryBindingV1,
    PublicationStatus,
    repository_archive_path,
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


class GitHubPublicationClient(Protocol):
    async def verify_repository(
        self,
        *,
        refresh: bool = False,
    ) -> GitHubRepositoryIdentity: ...

    async def get_branch_head(self, branch: str) -> GitBranchHead: ...

    async def get_commit(self, commit_sha: str) -> GitCommitObject: ...

    async def create_blob(self, content: bytes) -> str: ...

    async def create_tree(
        self,
        *,
        base_tree_sha: str,
        entries,
    ) -> str: ...

    async def create_commit(
        self,
        *,
        message: str,
        tree_sha: str,
        parent_sha: str,
        author_name: str,
        author_email: str,
        authored_at: datetime,
    ) -> str: ...

    async def create_or_update_branch(
        self,
        *,
        branch: str,
        target_sha: str,
        expected_sha: str | None = None,
    ) -> GitBranchUpdate: ...

    async def update_branch_non_force(
        self,
        *,
        branch: str,
        target_sha: str,
        expected_sha: str,
    ) -> GitBranchUpdate: ...

    async def create_or_find_pull_request(
        self,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str = "",
        draft: bool = False,
    ) -> GitPullRequest: ...


class PublicationArchiveChanged(PublicationConflict):
    code = "content_publication_archive_changed"


class PublicationRetryRejected(PublicationConflict):
    code = "content_publication_retry_rejected"


@dataclass(frozen=True)
class PublicationSubmission:
    publication: GitPublicationRecordV1
    reused: bool


class CoursePublicationService:
    def __init__(
        self,
        *,
        binding: GitRepositoryBindingV1,
        github: GitHubPublicationClient,
        store: PublicationStore | None = None,
        archive_builder: Callable[[str, str], BuiltCourseArchive] = build_course_archive,
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
        request: CourseArchivePublishRequestV1,
        *,
        requested_by: str,
    ) -> PublicationSubmission:
        archive = self.archive_builder(request.course_id, request.release_id)
        self._verify_archive_request(request, archive)
        proposed = new_publication_record(
            self.binding,
            request,
            requested_by=requested_by,
            requested_at=self._now(),
        )
        record, created = self.store.create_or_get(proposed)
        if not created:
            if not self._binding_matches_course_record(record):
                raise PublicationRetryRejected(
                    "repository binding changed; create a new publication"
                )
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
        if not isinstance(
            record.intent.request,
            CourseArchivePublishRequestV1,
        ):
            raise PublicationRetryRejected(
                "publication does not describe a course archive"
            )
        if not self._binding_matches_course_record(record):
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
            raise PublicationRetryRejected("publication retry lost a concurrent race") from None
        return await self._process(resumed)

    def get(self, publication_id: str) -> GitPublicationRecordV1:
        return self.store.get(publication_id)

    def list(
        self,
        *,
        course_id: str | None = None,
        release_id: str | None = None,
        status: PublicationStatus | None = None,
    ) -> tuple[GitPublicationRecordV1, ...]:
        return self.store.list(
            publication_kind="course",
            course_id=course_id,
            release_id=release_id,
            status=status,
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

    def _binding_matches_course_record(
        self,
        record: GitPublicationRecordV1,
    ) -> bool:
        existing = record.intent.binding.model_copy(
            update={
                "asset_root_prefix": self.binding.asset_root_prefix,
            }
        )
        return existing == self.binding

    def _resume_checkpoint(
        self,
        record: GitPublicationRecordV1,
    ) -> GitPublicationRecordV1:
        error_code = record.last_error_code
        if (
            record.intent.request.mode == "direct_commit"
            and error_code == "github_ref_conflict"
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
        archive: BuiltCourseArchive | None = None,
    ) -> GitPublicationRecordV1:
        try:
            request = record.intent.request
            if not isinstance(request, CourseArchivePublishRequestV1):
                raise PublicationRetryRejected(
                    "publication does not describe a course archive"
                )
            archive = archive or self.archive_builder(
                request.course_id,
                request.release_id,
            )
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
                    archive_root = repository_archive_path(
                        self.binding,
                        archive.manifest,
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
                    title=f"课程归档审核：{archive.manifest.course_title}",
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
            ArchiveBuildError,
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
        request: CourseArchivePublishRequestV1,
        archive: BuiltCourseArchive,
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
            request.course_id,
            request.release_id,
            request.expected_release_checksum,
            request.archive_id,
            request.expected_archive_checksum,
        ) != (
            manifest.course_id,
            manifest.release_id,
            manifest.release_checksum,
            manifest.archive_id,
            manifest.archive_checksum,
        ):
            raise PublicationArchiveChanged(
                "course archive changed after it was previewed"
            )

    @staticmethod
    def _commit_message(
        record: GitPublicationRecordV1,
        archive: BuiltCourseArchive,
    ) -> str:
        request = record.intent.request
        summary = request.change_summary.strip()
        lines = [
            f"课程归档：{archive.manifest.course_title}",
            "",
            f"course: {request.course_id}",
            f"release: {request.release_id}",
            f"archive: {request.archive_id}",
            f"requested-by: {record.intent.requested_by}",
        ]
        if summary:
            lines.extend(("", summary))
        return "\n".join(lines)

    @staticmethod
    def _pull_request_body(
        record: GitPublicationRecordV1,
        archive: BuiltCourseArchive,
    ) -> str:
        request = record.intent.request
        summary = request.change_summary.strip() or "未填写补充说明。"
        return "\n".join(
            (
                "## 课程归档",
                "",
                f"- 课程：{archive.manifest.course_title}",
                f"- 课程 ID：`{request.course_id}`",
                f"- 发布版本：`{request.release_id}`",
                f"- 归档：`{request.archive_id}`",
                f"- 文件数：{len(archive.files)}",
                "",
                "## 教师说明",
                "",
                summary,
                "",
                "> 本 Pull Request 由 Chronovita 课程内容发布服务生成。",
            )
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publication clock must return an aware datetime")
        return value


__all__ = [
    "CoursePublicationService",
    "GitHubPublicationClient",
    "PublicationArchiveChanged",
    "PublicationRetryRejected",
    "PublicationSubmission",
]
