import hashlib
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services import persistence
from services.content_history.archive import BuiltCourseArchive
from services.content_history.github import (
    GitBranchHead,
    GitBranchUpdate,
    GitCommitObject,
    GitHubErrorCode,
    GitHubGitDataError,
    GitHubRepositoryIdentity,
    GitPullRequest,
)
from services.content_history.publication import PublicationStore
from services.content_history.service import (
    CoursePublicationService,
    PublicationArchiveChanged,
    PublicationRetryRejected,
)
from services.contracts.archive_examples import (
    build_dayu_archive_package,
    build_dayu_publish_request,
    build_example_repository_binding,
)
from services.contracts.archive_v1 import CourseArchivePublishRequestV1


class _FakeGitHub:
    def __init__(
        self,
        binding,
        *,
        fail_pull_once=False,
        fail_direct_once=False,
        wrong_repository=False,
    ):
        self.binding = binding
        self.fail_pull_once = fail_pull_once
        self.fail_direct_once = fail_direct_once
        self.wrong_repository = wrong_repository
        self.calls = []
        self.commit_sha = "c" * 40
        self.base_sha = "a" * 40
        self.base_tree_sha = "b" * 40

    async def verify_repository(self, *, refresh=False):
        self.calls.append(("verify_repository", refresh))
        return GitHubRepositoryIdentity(
            repository_id=(
                self.binding.repository_id + 1
                if self.wrong_repository
                else self.binding.repository_id
            ),
            full_name=self.binding.full_name,
            default_branch=self.binding.base_branch,
        )

    async def get_branch_head(self, branch):
        self.calls.append(("get_branch_head", branch))
        return GitBranchHead(
            branch=branch,
            commit_sha=self.base_sha,
            tree_sha=self.base_tree_sha,
        )

    async def get_commit(self, commit_sha):
        self.calls.append(("get_commit", commit_sha))
        return GitCommitObject(sha=commit_sha, tree_sha=self.base_tree_sha)

    async def create_blob(self, content):
        self.calls.append(("create_blob", len(content)))
        return hashlib.sha1(b"blob " + content).hexdigest()

    async def create_tree(self, *, base_tree_sha, entries):
        self.calls.append(("create_tree", base_tree_sha, tuple(sorted(entries))))
        return "d" * 40

    async def create_commit(self, **kwargs):
        self.calls.append(("create_commit", kwargs))
        return self.commit_sha

    async def create_or_update_branch(self, **kwargs):
        self.calls.append(("create_or_update_branch", kwargs))
        return GitBranchUpdate(
            branch=kwargs["branch"],
            sha=kwargs["target_sha"],
            action="created",
            previous_sha=None,
        )

    async def update_branch_non_force(self, **kwargs):
        self.calls.append(("update_branch_non_force", kwargs))
        if self.fail_direct_once:
            self.fail_direct_once = False
            self.base_sha = "e" * 40
            raise GitHubGitDataError(GitHubErrorCode.REF_CONFLICT)
        return GitBranchUpdate(
            branch=kwargs["branch"],
            sha=kwargs["target_sha"],
            action="updated",
            previous_sha=kwargs["expected_sha"],
        )

    async def create_or_find_pull_request(self, **kwargs):
        self.calls.append(("create_or_find_pull_request", kwargs))
        if self.fail_pull_once:
            self.fail_pull_once = False
            raise GitHubGitDataError(GitHubErrorCode.UPSTREAM_UNAVAILABLE)
        return GitPullRequest(
            number=17,
            url=f"https://github.com/{self.binding.full_name}/pull/17",
            created=True,
        )


class ContentHistoryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_root = (
            Path.cwd() / ".tmp-content-history-service-tests" / uuid.uuid4().hex
        )
        self.tmp_root.mkdir(parents=True)
        persistence.init_engine(str(self.tmp_root / "publication.db"))
        self.binding = build_example_repository_binding()
        self.request = build_dayu_publish_request()
        manifest, files = build_dayu_archive_package()
        self.archive = BuiltCourseArchive(manifest=manifest, files=files)
        self.now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        persistence.close_engine()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    async def test_pull_request_publication_is_persisted_and_duplicate_is_reused(self):
        github = _FakeGitHub(self.binding)
        service = self._service(github)

        first = await service.submit(self.request, requested_by="teacher-a")
        calls_after_first = len(github.calls)
        second = await service.submit(self.request, requested_by="teacher-b")

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(second.publication, first.publication)
        self.assertEqual(first.publication.status, "succeeded")
        self.assertEqual(first.publication.pull_request_number, 17)
        self.assertEqual(first.publication.commit_sha, github.commit_sha)
        self.assertEqual(len(github.calls), calls_after_first)
        self.assertEqual(
            service.get(first.publication.intent.publication_id),
            first.publication,
        )
        commit_call = next(
            call for call in github.calls if call[0] == "create_commit"
        )
        self.assertEqual(
            commit_call[1]["authored_at"],
            first.publication.intent.requested_at,
        )
        self.assertEqual(
            commit_call[1]["author_email"],
            "content-publisher@chronovita.local",
        )

    async def test_retry_resumes_after_ref_update_without_recreating_commit(self):
        github = _FakeGitHub(self.binding, fail_pull_once=True)
        service = self._service(github)

        first = await service.submit(self.request, requested_by="teacher-a")
        self.assertEqual(first.publication.status, "failed_retryable")
        self.assertEqual(first.publication.commit_sha, github.commit_sha)
        self.assertEqual(
            sum(call[0] == "create_commit" for call in github.calls),
            1,
        )

        retried = await service.retry(
            first.publication.intent.publication_id,
            expected_revision=first.publication.revision,
        )

        self.assertEqual(retried.status, "succeeded")
        self.assertEqual(retried.attempt, 2)
        self.assertEqual(retried.pull_request_number, 17)
        self.assertEqual(
            sum(call[0] == "create_commit" for call in github.calls),
            1,
        )
        self.assertEqual(
            sum(call[0] == "create_or_update_branch" for call in github.calls),
            2,
        )

    async def test_retry_rejects_repository_binding_drift_without_network_calls(self):
        github = _FakeGitHub(self.binding, fail_pull_once=True)
        service = self._service(github)
        first = await service.submit(self.request, requested_by="teacher-a")
        self.assertEqual(first.publication.status, "failed_retryable")

        changed_binding = self.binding.model_copy(
            update={"repository_id": self.binding.repository_id + 1}
        )
        changed_github = _FakeGitHub(changed_binding)
        changed_service = CoursePublicationService(
            binding=changed_binding,
            github=changed_github,
            archive_builder=lambda course_id, release_id: self.archive,
            clock=lambda: self.now,
        )

        with self.assertRaisesRegex(
            PublicationRetryRejected,
            "repository binding changed",
        ):
            await changed_service.retry(
                first.publication.intent.publication_id,
                expected_revision=first.publication.revision,
            )

        self.assertEqual(changed_github.calls, [])
        self.assertEqual(
            PublicationStore().get(first.publication.intent.publication_id),
            first.publication,
        )

    async def test_direct_commit_updates_base_without_creating_pull_request(self):
        github = _FakeGitHub(self.binding)
        service = self._service(github)
        direct = CourseArchivePublishRequestV1.model_validate(
            {
                **self.request.model_dump(mode="json"),
                "mode": "direct_commit",
                "direct_commit_confirmed": True,
                "client_request_id": "direct-request-001",
            }
        )

        submitted = await service.submit(direct, requested_by="admin-a")

        self.assertEqual(submitted.publication.status, "succeeded")
        self.assertIsNone(submitted.publication.pull_request_number)
        self.assertEqual(
            sum(call[0] == "update_branch_non_force" for call in github.calls),
            1,
        )
        self.assertFalse(
            any(call[0] == "create_or_find_pull_request" for call in github.calls)
        )

    async def test_direct_commit_ref_conflict_rebuilds_on_latest_base(self):
        github = _FakeGitHub(self.binding, fail_direct_once=True)
        service = self._service(github)
        direct = CourseArchivePublishRequestV1.model_validate(
            {
                **self.request.model_dump(mode="json"),
                "mode": "direct_commit",
                "direct_commit_confirmed": True,
                "client_request_id": "direct-conflict-001",
            }
        )

        first = await service.submit(direct, requested_by="admin-a")
        self.assertEqual(first.publication.status, "failed_retryable")
        self.assertEqual(
            first.publication.last_error_code,
            "github_ref_conflict",
        )
        retried = await service.retry(
            first.publication.intent.publication_id,
            expected_revision=first.publication.revision,
        )

        self.assertEqual(retried.status, "succeeded")
        self.assertEqual(retried.attempt, 2)
        self.assertEqual(retried.base_sha, "e" * 40)
        self.assertEqual(
            sum(call[0] == "get_branch_head" for call in github.calls),
            2,
        )
        self.assertEqual(
            sum(call[0] == "create_commit" for call in github.calls),
            2,
        )

    async def test_archive_drift_is_rejected_before_a_task_or_network_call(self):
        github = _FakeGitHub(self.binding)
        service = self._service(github)
        changed = CourseArchivePublishRequestV1.model_validate(
            {
                **self.request.model_dump(mode="json"),
                "expected_release_checksum": "f" * 64,
            }
        )

        with self.assertRaises(PublicationArchiveChanged):
            await service.submit(changed, requested_by="teacher-a")

        self.assertEqual(github.calls, [])
        self.assertEqual(PublicationStore().list(), ())

    async def test_repository_identity_drift_is_saved_as_terminal_failure(self):
        github = _FakeGitHub(self.binding, wrong_repository=True)
        service = self._service(github)

        submitted = await service.submit(self.request, requested_by="teacher-a")

        self.assertEqual(submitted.publication.status, "failed_terminal")
        self.assertEqual(
            submitted.publication.last_error_code,
            "content_publication_configuration_invalid",
        )
        with self.assertRaises(PublicationRetryRejected):
            await service.retry(submitted.publication.intent.publication_id)

    def _service(self, github):
        return CoursePublicationService(
            binding=self.binding,
            github=github,
            archive_builder=lambda course_id, release_id: self.archive,
            clock=lambda: self.now,
        )


if __name__ == "__main__":
    unittest.main()
