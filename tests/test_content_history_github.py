import base64
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.content_history.github import (
    GitHubErrorCode,
    GitHubGitDataClient,
    GitHubGitDataError,
)


TOKEN = "github_pat_test-only-super-secret"
REPOSITORY_ID = 1311692460
FULL_NAME = "falling-feather/Chronovita-Course-Content"
API_BASE_URL = "https://api.github.com"
BASE_COMMIT_SHA = "1" * 40
BASE_TREE_SHA = "2" * 40
BLOB_SHA = "3" * 40
SECOND_BLOB_SHA = "4" * 40
TREE_SHA = "5" * 40
COMMIT_SHA = "6" * 40
DIRECT_COMMIT_SHA = "7" * 40


def repository_payload(**changes):
    payload = {
        "id": REPOSITORY_ID,
        "full_name": FULL_NAME,
        "private": True,
        "visibility": "private",
        "default_branch": "main",
    }
    payload.update(changes)
    return payload


def reference_payload(branch, sha):
    return {
        "ref": f"refs/heads/{branch}",
        "object": {"type": "commit", "sha": sha},
    }


def pull_request_payload(number, head_branch, base_branch):
    return {
        "number": number,
        "state": "open",
        "html_url": "https://attacker.invalid/not-trusted",
        "head": {
            "ref": head_branch,
            "repo": {"full_name": FULL_NAME},
        },
        "base": {
            "ref": base_branch,
            "repo": {"full_name": FULL_NAME},
        },
    }


class GitHubGitDataClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_rejects_untrusted_https_api_host_before_sending_token(self):
        with self.assertRaises(GitHubGitDataError) as caught:
            GitHubGitDataClient(
                token=TOKEN,
                repository_id=REPOSITORY_ID,
                full_name=FULL_NAME,
                api_base_url="https://collector.example",
                transport=httpx.MockTransport(
                    lambda request: self.fail("network request must not be sent")
                ),
            )

        self.assertEqual(
            caught.exception.code,
            GitHubErrorCode.INVALID_CONFIGURATION,
        )

    async def test_full_git_data_sequence_and_payloads(self):
        publication_branch = "content/C-001/rel-001"
        requests = []
        responses = [
            ("GET", f"/repos/{FULL_NAME}", 200, repository_payload()),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/main",
                200,
                reference_payload("main", BASE_COMMIT_SHA),
            ),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/commits/{BASE_COMMIT_SHA}",
                200,
                {
                    "sha": BASE_COMMIT_SHA,
                    "tree": {"sha": BASE_TREE_SHA},
                },
            ),
            (
                "POST",
                f"/repos/{FULL_NAME}/git/blobs",
                201,
                {"sha": BLOB_SHA},
            ),
            (
                "POST",
                f"/repos/{FULL_NAME}/git/trees",
                201,
                {"sha": TREE_SHA},
            ),
            (
                "POST",
                f"/repos/{FULL_NAME}/git/commits",
                201,
                {"sha": COMMIT_SHA, "tree": {"sha": TREE_SHA}},
            ),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/{publication_branch}",
                404,
                None,
            ),
            (
                "POST",
                f"/repos/{FULL_NAME}/git/refs",
                201,
                reference_payload(publication_branch, COMMIT_SHA),
            ),
            ("GET", f"/repos/{FULL_NAME}/pulls", 200, []),
            (
                "POST",
                f"/repos/{FULL_NAME}/pulls",
                201,
                {
                    "number": 17,
                    "html_url": "https://attacker.invalid/not-trusted",
                },
            ),
        ]

        def handler(request):
            index = len(requests)
            expected_method, expected_path, status, payload = responses[index]
            self.assertEqual(request.method, expected_method)
            self.assertEqual(request.url.path, expected_path)
            requests.append(request)
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)

        client = self._client(httpx.MockTransport(handler))
        async with client:
            head = await client.get_branch_head("main")
            blob_sha = await client.create_blob(b"\x00Chronovita\n")
            tree_sha = await client.create_tree(
                base_tree_sha=head.tree_sha,
                entries={
                    "z-last.json": blob_sha,
                    "a-first.json": SECOND_BLOB_SHA,
                },
            )
            commit_sha = await client.create_commit(
                message="V0.9.29 publish C-001",
                tree_sha=tree_sha,
                parent_sha=head.commit_sha,
                author_name="Chronovita Publisher",
                author_email="content-publisher@chronovita.local",
                authored_at=datetime(
                    2026,
                    7,
                    25,
                    10,
                    30,
                    45,
                    987654,
                    tzinfo=timezone.utc,
                ),
            )
            branch = await client.create_or_update_branch(
                branch=publication_branch,
                target_sha=commit_sha,
            )
            pull_request = await client.create_or_find_pull_request(
                head_branch=publication_branch,
                base_branch="main",
                title="课程发布 C-001",
                body="由 Chronovita 内容编辑器发布。",
            )

        self.assertTrue(client.is_closed)
        self.assertEqual(head.commit_sha, BASE_COMMIT_SHA)
        self.assertEqual(head.tree_sha, BASE_TREE_SHA)
        self.assertEqual(blob_sha, BLOB_SHA)
        self.assertEqual(tree_sha, TREE_SHA)
        self.assertEqual(commit_sha, COMMIT_SHA)
        self.assertEqual(branch.action, "created")
        self.assertEqual(
            pull_request.url,
            f"https://github.com/{FULL_NAME}/pull/17",
        )
        self.assertTrue(pull_request.created)
        self.assertEqual(len(requests), len(responses))

        blob_body = json.loads(requests[3].content)
        self.assertEqual(blob_body["encoding"], "base64")
        self.assertEqual(
            blob_body["content"],
            base64.b64encode(b"\x00Chronovita\n").decode("ascii"),
        )
        tree_body = json.loads(requests[4].content)
        self.assertEqual(tree_body["base_tree"], BASE_TREE_SHA)
        self.assertEqual(
            [entry["path"] for entry in tree_body["tree"]],
            ["a-first.json", "z-last.json"],
        )
        self.assertTrue(
            all(entry["type"] == "blob" for entry in tree_body["tree"])
        )
        commit_body = json.loads(requests[5].content)
        self.assertEqual(commit_body["tree"], TREE_SHA)
        self.assertEqual(commit_body["parents"], [BASE_COMMIT_SHA])
        self.assertEqual(
            commit_body["author"],
            {
                "name": "Chronovita Publisher",
                "email": "content-publisher@chronovita.local",
                "date": "2026-07-25T10:30:45Z",
            },
        )
        self.assertEqual(commit_body["committer"], commit_body["author"])
        create_ref_body = json.loads(requests[7].content)
        self.assertNotIn("force", create_ref_body)
        self.assertEqual(
            create_ref_body,
            {
                "ref": f"refs/heads/{publication_branch}",
                "sha": COMMIT_SHA,
            },
        )
        self.assertEqual(
            dict(requests[8].url.params),
            {
                "state": "open",
                "head": f"falling-feather:{publication_branch}",
                "base": "main",
                "per_page": "100",
            },
        )
        self._assert_token_only_in_authorization(requests)

    async def test_existing_refs_update_without_force_and_existing_pr_is_reused(self):
        publication_branch = "content/C-002/rel-002"
        previous_publication_sha = "8" * 40
        requests = []
        responses = [
            ("GET", f"/repos/{FULL_NAME}", repository_payload()),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/{publication_branch}",
                reference_payload(publication_branch, previous_publication_sha),
            ),
            (
                "PATCH",
                f"/repos/{FULL_NAME}/git/refs/heads/{publication_branch}",
                reference_payload(publication_branch, COMMIT_SHA),
            ),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/{publication_branch}",
                reference_payload(publication_branch, COMMIT_SHA),
            ),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/main",
                reference_payload("main", BASE_COMMIT_SHA),
            ),
            (
                "PATCH",
                f"/repos/{FULL_NAME}/git/refs/heads/main",
                reference_payload("main", DIRECT_COMMIT_SHA),
            ),
            (
                "GET",
                f"/repos/{FULL_NAME}/pulls",
                [pull_request_payload(23, publication_branch, "main")],
            ),
        ]

        def handler(request):
            expected_method, expected_path, payload = responses[len(requests)]
            self.assertEqual(request.method, expected_method)
            self.assertEqual(request.url.path, expected_path)
            requests.append(request)
            return httpx.Response(200, json=payload)

        async with self._client(httpx.MockTransport(handler)) as client:
            updated = await client.create_or_update_branch(
                branch=publication_branch,
                target_sha=COMMIT_SHA,
                expected_sha=previous_publication_sha,
            )
            unchanged = await client.create_or_update_branch(
                branch=publication_branch,
                target_sha=COMMIT_SHA,
            )
            direct = await client.update_branch_non_force(
                branch="main",
                target_sha=DIRECT_COMMIT_SHA,
                expected_sha=BASE_COMMIT_SHA,
            )
            pull_request = await client.create_or_find_pull_request(
                head_branch=publication_branch,
                base_branch="main",
                title="不会重复创建",
            )

        self.assertEqual(updated.action, "updated")
        self.assertEqual(updated.previous_sha, previous_publication_sha)
        self.assertEqual(unchanged.action, "unchanged")
        self.assertEqual(direct.action, "updated")
        self.assertFalse(pull_request.created)
        self.assertEqual(
            pull_request.url,
            f"https://github.com/{FULL_NAME}/pull/23",
        )
        patch_bodies = [
            json.loads(request.content)
            for request in requests
            if request.method == "PATCH"
        ]
        self.assertEqual(
            patch_bodies,
            [
                {"sha": COMMIT_SHA, "force": False},
                {"sha": DIRECT_COMMIT_SHA, "force": False},
            ],
        )
        self.assertFalse(
            any(
                request.method == "POST" and request.url.path.endswith("/pulls")
                for request in requests
            )
        )

    async def test_concurrent_branch_and_pull_request_creation_are_reconciled(self):
        publication_branch = "content/C-003/rel-003"
        requests = []
        responses = [
            ("GET", f"/repos/{FULL_NAME}", 200, repository_payload()),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/{publication_branch}",
                404,
                None,
            ),
            ("POST", f"/repos/{FULL_NAME}/git/refs", 422, None),
            (
                "GET",
                f"/repos/{FULL_NAME}/git/ref/heads/{publication_branch}",
                200,
                reference_payload(publication_branch, COMMIT_SHA),
            ),
            ("GET", f"/repos/{FULL_NAME}/pulls", 200, []),
            ("POST", f"/repos/{FULL_NAME}/pulls", 422, None),
            (
                "GET",
                f"/repos/{FULL_NAME}/pulls",
                200,
                [pull_request_payload(31, publication_branch, "main")],
            ),
        ]

        def handler(request):
            expected_method, expected_path, status, payload = responses[
                len(requests)
            ]
            self.assertEqual(request.method, expected_method)
            self.assertEqual(request.url.path, expected_path)
            requests.append(request)
            if payload is None:
                return httpx.Response(status)
            return httpx.Response(status, json=payload)

        async with self._client(httpx.MockTransport(handler)) as client:
            branch = await client.create_or_update_branch(
                branch=publication_branch,
                target_sha=COMMIT_SHA,
            )
            pull_request = await client.create_or_find_pull_request(
                head_branch=publication_branch,
                base_branch="main",
                title="并发发布",
            )

        self.assertEqual(branch.action, "unchanged")
        self.assertEqual(pull_request.number, 31)
        self.assertFalse(pull_request.created)

    async def test_error_codes_are_stable_and_secrets_are_sanitized(self):
        cases = [
            (
                "authentication",
                lambda request: httpx.Response(
                    401,
                    text=f"provider leaked {TOKEN}",
                ),
                GitHubErrorCode.AUTHENTICATION_FAILED,
                False,
            ),
            (
                "rate-limit",
                lambda request: httpx.Response(
                    403,
                    headers={"X-RateLimit-Remaining": "0"},
                    text=f"provider leaked {TOKEN}",
                ),
                GitHubErrorCode.RATE_LIMITED,
                True,
            ),
            (
                "unavailable",
                lambda request: httpx.Response(
                    503,
                    text=f"provider leaked {TOKEN}",
                ),
                GitHubErrorCode.UPSTREAM_UNAVAILABLE,
                True,
            ),
            (
                "timeout",
                self._timeout_response,
                GitHubErrorCode.TIMEOUT,
                True,
            ),
        ]

        for name, handler, expected_code, retryable in cases:
            with self.subTest(name=name):
                client = self._client(httpx.MockTransport(handler))
                self.assertNotIn(TOKEN, repr(client))
                try:
                    with self.assertRaises(GitHubGitDataError) as caught:
                        await client.verify_repository()
                finally:
                    await client.aclose()
                error = caught.exception
                self.assertEqual(error.code, expected_code)
                self.assertEqual(error.retryable, retryable)
                self.assertEqual(error.terminal, not retryable)
                self.assertNotIn(TOKEN, str(error))
                self.assertNotIn(TOKEN, repr(error))
                self.assertNotIn("provider leaked", str(error))
                self.assertNotIn("provider leaked", repr(error))

    async def test_repository_identity_validation_fails_closed(self):
        cases = [
            (
                repository_payload(id=REPOSITORY_ID + 1),
                GitHubErrorCode.REPOSITORY_ID_MISMATCH,
            ),
            (
                repository_payload(full_name="other-owner/other-repository"),
                GitHubErrorCode.REPOSITORY_NAME_MISMATCH,
            ),
            (
                repository_payload(private=False, visibility="public"),
                GitHubErrorCode.REPOSITORY_NOT_PRIVATE,
            ),
            (
                repository_payload(id=str(REPOSITORY_ID)),
                GitHubErrorCode.INVALID_RESPONSE,
            ),
            (
                repository_payload(default_branch="bad branch"),
                GitHubErrorCode.INVALID_RESPONSE,
            ),
        ]

        for payload, expected_code in cases:
            with self.subTest(code=expected_code):
                transport = httpx.MockTransport(
                    lambda request, payload=payload: httpx.Response(
                        200,
                        json=payload,
                    )
                )
                async with self._client(transport) as client:
                    with self.assertRaises(GitHubGitDataError) as caught:
                        await client.verify_repository()
                self.assertEqual(caught.exception.code, expected_code)
                self.assertTrue(caught.exception.terminal)

    async def test_invalid_tree_entries_use_the_sanitized_configuration_error(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=repository_payload())
        )
        async with self._client(transport) as client:
            with self.assertRaises(GitHubGitDataError) as caught:
                await client.create_tree(
                    base_tree_sha=BASE_TREE_SHA,
                    entries=None,
                )
        self.assertEqual(
            caught.exception.code,
            GitHubErrorCode.INVALID_CONFIGURATION,
        )
        self.assertTrue(caught.exception.terminal)

    async def test_sha_and_pull_request_number_are_strictly_parsed(self):
        branch = "content/C-004/rel-004"
        responses = [
            repository_payload(),
            reference_payload("main", "A" * 40),
        ]

        def bad_sha_handler(request):
            return httpx.Response(200, json=responses.pop(0))

        async with self._client(httpx.MockTransport(bad_sha_handler)) as client:
            with self.assertRaises(GitHubGitDataError) as sha_error:
                await client.get_branch_ref("main")
        self.assertEqual(
            sha_error.exception.code,
            GitHubErrorCode.INVALID_RESPONSE,
        )

        pull_responses = [
            repository_payload(),
            [pull_request_payload("19", branch, "main")],
        ]

        def bad_pr_handler(request):
            return httpx.Response(200, json=pull_responses.pop(0))

        async with self._client(httpx.MockTransport(bad_pr_handler)) as client:
            with self.assertRaises(GitHubGitDataError) as pr_error:
                await client.find_open_pull_request(
                    head_branch=branch,
                    base_branch="main",
                )
        self.assertEqual(
            pr_error.exception.code,
            GitHubErrorCode.INVALID_RESPONSE,
        )

    async def test_ref_conflict_is_retryable_and_never_forced(self):
        branch = "main"
        advanced_sha = "9" * 40
        requests = []
        responses = [
            repository_payload(),
            reference_payload(branch, advanced_sha),
        ]

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=responses.pop(0))

        async with self._client(httpx.MockTransport(handler)) as client:
            with self.assertRaises(GitHubGitDataError) as caught:
                await client.update_branch_non_force(
                    branch=branch,
                    target_sha=DIRECT_COMMIT_SHA,
                    expected_sha=BASE_COMMIT_SHA,
                )

        self.assertEqual(caught.exception.code, GitHubErrorCode.REF_CONFLICT)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual([request.method for request in requests], ["GET", "GET"])

    def _client(self, transport):
        return GitHubGitDataClient(
            token=TOKEN,
            repository_id=REPOSITORY_ID,
            full_name=FULL_NAME,
            api_base_url=API_BASE_URL,
            timeout_seconds=1,
            transport=transport,
        )

    def _timeout_response(self, request):
        raise httpx.ReadTimeout(
            f"transport leaked {TOKEN}",
            request=request,
        )

    def _assert_token_only_in_authorization(self, requests):
        for request in requests:
            self.assertEqual(
                request.headers["Authorization"],
                f"Bearer {TOKEN}",
            )
            self.assertNotIn(TOKEN, str(request.url))
            self.assertNotIn(TOKEN.encode("ascii"), request.content)
            for header, value in request.headers.items():
                if header.lower() != "authorization":
                    self.assertNotIn(TOKEN, value)


if __name__ == "__main__":
    unittest.main()
