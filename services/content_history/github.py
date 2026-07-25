from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from urllib.parse import quote

import httpx


_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s<>]+@[^@\s<>]+$")
_REPOSITORY_OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
_REPOSITORY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_COMMIT_MESSAGE_BYTES = 16 * 1024
_MAX_PULL_REQUEST_BODY_BYTES = 64 * 1024
_API_VERSION = "2022-11-28"


class GitHubErrorCode(str, Enum):
    INVALID_CONFIGURATION = "github_invalid_configuration"
    AUTHENTICATION_FAILED = "github_authentication_failed"
    PERMISSION_DENIED = "github_permission_denied"
    REPOSITORY_NOT_FOUND = "github_repository_not_found"
    REPOSITORY_ID_MISMATCH = "github_repository_id_mismatch"
    REPOSITORY_NAME_MISMATCH = "github_repository_name_mismatch"
    REPOSITORY_NOT_PRIVATE = "github_repository_not_private"
    REF_NOT_FOUND = "github_ref_not_found"
    GIT_OBJECT_NOT_FOUND = "github_git_object_not_found"
    REF_CONFLICT = "github_ref_conflict"
    REQUEST_REJECTED = "github_request_rejected"
    RATE_LIMITED = "github_rate_limited"
    TIMEOUT = "github_timeout"
    UPSTREAM_UNAVAILABLE = "github_upstream_unavailable"
    INVALID_RESPONSE = "github_invalid_response"


_RETRYABLE_ERROR_CODES = frozenset(
    {
        GitHubErrorCode.REF_CONFLICT,
        GitHubErrorCode.RATE_LIMITED,
        GitHubErrorCode.TIMEOUT,
        GitHubErrorCode.UPSTREAM_UNAVAILABLE,
    }
)


class GitHubGitDataError(RuntimeError):
    """A sanitized GitHub failure suitable for persistence and API responses."""

    __slots__ = ("code", "retryable", "status_code")

    def __init__(
        self,
        code: GitHubErrorCode,
        *,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.retryable = code in _RETRYABLE_ERROR_CODES
        self.status_code = status_code
        super().__init__(code.value)

    @property
    def terminal(self) -> bool:
        return not self.retryable

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code.value!r}, "
            f"retryable={self.retryable!r}, status_code={self.status_code!r})"
        )


@dataclass(frozen=True, slots=True)
class GitHubRepositoryIdentity:
    repository_id: int
    full_name: str
    default_branch: str | None


@dataclass(frozen=True, slots=True)
class GitReference:
    branch: str
    sha: str


@dataclass(frozen=True, slots=True)
class GitCommitObject:
    sha: str
    tree_sha: str


@dataclass(frozen=True, slots=True)
class GitBranchHead:
    branch: str
    commit_sha: str
    tree_sha: str


@dataclass(frozen=True, slots=True)
class GitTreeEntry:
    path: str
    blob_sha: str
    mode: Literal["100644"] = "100644"


@dataclass(frozen=True, slots=True)
class GitBranchUpdate:
    branch: str
    sha: str
    action: Literal["created", "updated", "unchanged"]
    previous_sha: str | None


@dataclass(frozen=True, slots=True)
class GitPullRequest:
    number: int
    url: str
    created: bool


class GitHubGitDataClient:
    """Minimal async GitHub Git Data client with fail-closed identity checks."""

    __slots__ = (
        "_client",
        "_owner",
        "_repository",
        "_repository_identity",
        "_repository_lock",
        "_token",
        "api_base_url",
        "full_name",
        "repository_id",
    )

    def __init__(
        self,
        *,
        token: str,
        repository_id: int,
        full_name: str,
        api_base_url: str = "https://api.github.com",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        try:
            owner, repository = _validate_repository_binding(
                repository_id,
                full_name,
            )
            _validate_token(token)
            normalized_base_url = _validate_api_base_url(api_base_url)
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not 0.1 <= timeout_seconds <= 120
            ):
                raise ValueError("invalid timeout")
            client = httpx.AsyncClient(
                base_url=f"{normalized_base_url}/",
                timeout=httpx.Timeout(float(timeout_seconds)),
                transport=transport,
                follow_redirects=False,
            )
        except (TypeError, ValueError):
            raise GitHubGitDataError(
                GitHubErrorCode.INVALID_CONFIGURATION
            ) from None

        self._token = token
        self.repository_id = repository_id
        self.full_name = full_name
        self._owner = owner
        self._repository = repository
        self.api_base_url = normalized_base_url
        self._client = client
        self._repository_identity: GitHubRepositoryIdentity | None = None

        self._repository_lock = asyncio.Lock()

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(repository_id={self.repository_id!r}, "
            f"full_name={self.full_name!r}, "
            f"api_base_url={self.api_base_url!r}, "
            f"is_closed={self.is_closed!r})"
        )

    async def __aenter__(self) -> GitHubGitDataClient:
        if self.is_closed:
            raise GitHubGitDataError(
                GitHubErrorCode.INVALID_CONFIGURATION
            ) from None
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()
        self._token = ""

    async def verify_repository(
        self,
        *,
        refresh: bool = False,
    ) -> GitHubRepositoryIdentity:
        if self._repository_identity is not None and not refresh:
            return self._repository_identity

        async with self._repository_lock:
            if self._repository_identity is not None and not refresh:
                return self._repository_identity
            if refresh:
                self._repository_identity = None
            status, payload = await self._request_json(
                "GET",
                self._repo_path(),
                success_statuses={200},
                passthrough_statuses={404},
            )
            if status == 404:
                raise self._error(
                    GitHubErrorCode.REPOSITORY_NOT_FOUND,
                    status_code=status,
                )
            repository = _require_object(payload)
            actual_id = _require_positive_int(repository, "id")
            actual_full_name = _require_string(repository, "full_name")
            is_private = repository.get("private")
            visibility = repository.get("visibility")

            if actual_id != self.repository_id:
                raise self._error(GitHubErrorCode.REPOSITORY_ID_MISMATCH)
            if actual_full_name != self.full_name:
                raise self._error(GitHubErrorCode.REPOSITORY_NAME_MISMATCH)
            if is_private is not True or (
                visibility is not None and visibility != "private"
            ):
                raise self._error(GitHubErrorCode.REPOSITORY_NOT_PRIVATE)

            default_branch_value = repository.get("default_branch")
            if default_branch_value is None:
                default_branch = None
            elif isinstance(default_branch_value, str):
                try:
                    default_branch = _validate_branch(default_branch_value)
                except ValueError:
                    raise self._error(
                        GitHubErrorCode.INVALID_RESPONSE
                    ) from None
            else:
                raise self._error(GitHubErrorCode.INVALID_RESPONSE)

            identity = GitHubRepositoryIdentity(
                repository_id=actual_id,
                full_name=actual_full_name,
                default_branch=default_branch,
            )
            self._repository_identity = identity
            return identity

    async def get_branch_ref(self, branch: str) -> GitReference:
        await self.verify_repository()
        validated_branch = self._validated_branch(branch)
        reference = await self._get_branch_ref_optional(validated_branch)
        if reference is None:
            raise self._error(GitHubErrorCode.REF_NOT_FOUND, status_code=404)
        return reference

    async def get_commit(self, commit_sha: str) -> GitCommitObject:
        await self.verify_repository()
        validated_sha = self._validated_sha(commit_sha)
        status, payload = await self._request_json(
            "GET",
            self._repo_path(f"git/commits/{validated_sha}"),
            success_statuses={200},
            passthrough_statuses={404},
        )
        if status == 404:
            raise self._error(
                GitHubErrorCode.GIT_OBJECT_NOT_FOUND,
                status_code=status,
            )
        commit = _require_object(payload)
        actual_sha = _require_sha(commit, "sha")
        tree = _require_object(commit.get("tree"))
        tree_sha = _require_sha(tree, "sha")
        if actual_sha != validated_sha:
            raise self._error(GitHubErrorCode.INVALID_RESPONSE)
        return GitCommitObject(sha=actual_sha, tree_sha=tree_sha)

    async def get_branch_head(self, branch: str) -> GitBranchHead:
        reference = await self.get_branch_ref(branch)
        commit = await self.get_commit(reference.sha)
        return GitBranchHead(
            branch=reference.branch,
            commit_sha=commit.sha,
            tree_sha=commit.tree_sha,
        )

    async def create_blob(self, content: bytes) -> str:
        await self.verify_repository()
        if not isinstance(content, bytes):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        _, payload = await self._request_json(
            "POST",
            self._repo_path("git/blobs"),
            success_statuses={201},
            json_body={
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        return _require_sha(_require_object(payload), "sha")

    async def create_tree(
        self,
        *,
        base_tree_sha: str,
        entries: Mapping[str, str] | Iterable[GitTreeEntry],
    ) -> str:
        await self.verify_repository()
        validated_base = self._validated_sha(base_tree_sha)
        normalized_entries = self._normalize_tree_entries(entries)
        _, payload = await self._request_json(
            "POST",
            self._repo_path("git/trees"),
            success_statuses={201},
            json_body={
                "base_tree": validated_base,
                "tree": [
                    {
                        "path": entry.path,
                        "mode": entry.mode,
                        "type": "blob",
                        "sha": entry.blob_sha,
                    }
                    for entry in normalized_entries
                ],
            },
        )
        return _require_sha(_require_object(payload), "sha")

    async def create_commit(
        self,
        *,
        message: str,
        tree_sha: str,
        parent_sha: str,
        author_name: str,
        author_email: str,
        authored_at: datetime,
    ) -> str:
        await self.verify_repository()
        validated_message = self._validated_commit_message(message)
        validated_tree = self._validated_sha(tree_sha)
        validated_parent = self._validated_sha(parent_sha)
        signature = self._validated_commit_signature(
            name=author_name,
            email=author_email,
            authored_at=authored_at,
        )
        _, payload = await self._request_json(
            "POST",
            self._repo_path("git/commits"),
            success_statuses={201},
            json_body={
                "message": validated_message,
                "tree": validated_tree,
                "parents": [validated_parent],
                "author": signature,
                "committer": signature,
            },
        )
        commit = _require_object(payload)
        commit_sha = _require_sha(commit, "sha")
        returned_tree = commit.get("tree")
        if returned_tree is not None:
            returned_tree_sha = _require_sha(
                _require_object(returned_tree),
                "sha",
            )
            if returned_tree_sha != validated_tree:
                raise self._error(GitHubErrorCode.INVALID_RESPONSE)
        return commit_sha

    async def create_or_update_branch(
        self,
        *,
        branch: str,
        target_sha: str,
        expected_sha: str | None = None,
    ) -> GitBranchUpdate:
        """Create a publication branch or move it without ever forcing a ref."""

        await self.verify_repository()
        validated_branch = self._validated_branch(branch)
        validated_target = self._validated_sha(target_sha)
        validated_expected = (
            None if expected_sha is None else self._validated_sha(expected_sha)
        )
        current = await self._get_branch_ref_optional(validated_branch)

        if current is None:
            status, payload = await self._request_json(
                "POST",
                self._repo_path("git/refs"),
                success_statuses={201},
                passthrough_statuses={422},
                json_body={
                    "ref": f"refs/heads/{validated_branch}",
                    "sha": validated_target,
                },
            )
            if status == 201:
                created = self._parse_reference(payload, validated_branch)
                if created.sha != validated_target:
                    raise self._error(GitHubErrorCode.INVALID_RESPONSE)
                return GitBranchUpdate(
                    branch=validated_branch,
                    sha=created.sha,
                    action="created",
                    previous_sha=None,
                )

            # A concurrent retry may have created the same ref after our lookup.
            current = await self._get_branch_ref_optional(validated_branch)
            if current is None:
                raise self._error(
                    GitHubErrorCode.REQUEST_REJECTED,
                    status_code=status,
                )

        if current.sha == validated_target:
            return GitBranchUpdate(
                branch=validated_branch,
                sha=validated_target,
                action="unchanged",
                previous_sha=current.sha,
            )
        if validated_expected is not None and current.sha != validated_expected:
            raise self._error(GitHubErrorCode.REF_CONFLICT, status_code=409)

        return await self._patch_branch_non_force(
            branch=validated_branch,
            target_sha=validated_target,
            previous_sha=current.sha,
        )

    async def update_branch_non_force(
        self,
        *,
        branch: str,
        target_sha: str,
        expected_sha: str,
    ) -> GitBranchUpdate:
        """Move an existing direct-commit branch after checking its base SHA."""

        await self.verify_repository()
        validated_branch = self._validated_branch(branch)
        validated_target = self._validated_sha(target_sha)
        validated_expected = self._validated_sha(expected_sha)
        current = await self._get_branch_ref_optional(validated_branch)
        if current is None:
            raise self._error(GitHubErrorCode.REF_NOT_FOUND, status_code=404)
        if current.sha == validated_target:
            return GitBranchUpdate(
                branch=validated_branch,
                sha=validated_target,
                action="unchanged",
                previous_sha=current.sha,
            )
        if current.sha != validated_expected:
            raise self._error(GitHubErrorCode.REF_CONFLICT, status_code=409)
        return await self._patch_branch_non_force(
            branch=validated_branch,
            target_sha=validated_target,
            previous_sha=current.sha,
        )

    async def find_open_pull_request(
        self,
        *,
        head_branch: str,
        base_branch: str,
    ) -> GitPullRequest | None:
        await self.verify_repository()
        validated_head = self._validated_branch(head_branch)
        validated_base = self._validated_branch(base_branch)
        _, payload = await self._request_json(
            "GET",
            self._repo_path("pulls"),
            success_statuses={200},
            params={
                "state": "open",
                "head": f"{self._owner}:{validated_head}",
                "base": validated_base,
                "per_page": "100",
            },
        )
        pulls = _require_list(payload)
        matches: list[GitPullRequest] = []
        for candidate in pulls:
            pull = _require_object(candidate)
            if not self._pull_matches(
                pull,
                head_branch=validated_head,
                base_branch=validated_base,
            ):
                continue
            number = _require_positive_int(pull, "number")
            matches.append(self._pull_request(number=number, created=False))

        if len(matches) > 1:
            raise self._error(GitHubErrorCode.INVALID_RESPONSE)
        return matches[0] if matches else None

    async def create_or_find_pull_request(
        self,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str = "",
        draft: bool = False,
    ) -> GitPullRequest:
        await self.verify_repository()
        validated_head = self._validated_branch(head_branch)
        validated_base = self._validated_branch(base_branch)
        validated_title = self._validated_pull_request_title(title)
        validated_body = self._validated_pull_request_body(body)
        if not isinstance(draft, bool):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)

        existing = await self.find_open_pull_request(
            head_branch=validated_head,
            base_branch=validated_base,
        )
        if existing is not None:
            return existing

        status, payload = await self._request_json(
            "POST",
            self._repo_path("pulls"),
            success_statuses={201},
            passthrough_statuses={422},
            json_body={
                "title": validated_title,
                "head": validated_head,
                "base": validated_base,
                "body": validated_body,
                "draft": draft,
            },
        )
        if status == 201:
            number = _require_positive_int(_require_object(payload), "number")
            return self._pull_request(number=number, created=True)

        # GitHub returns 422 when another worker opens the same PR first.
        existing = await self.find_open_pull_request(
            head_branch=validated_head,
            base_branch=validated_base,
        )
        if existing is not None:
            return existing
        raise self._error(
            GitHubErrorCode.REQUEST_REJECTED,
            status_code=status,
        )

    async def _get_branch_ref_optional(
        self,
        branch: str,
    ) -> GitReference | None:
        encoded_branch = quote(branch, safe="")
        status, payload = await self._request_json(
            "GET",
            self._repo_path(f"git/ref/heads/{encoded_branch}"),
            success_statuses={200},
            passthrough_statuses={404},
        )
        if status == 404:
            return None
        return self._parse_reference(payload, branch)

    async def _patch_branch_non_force(
        self,
        *,
        branch: str,
        target_sha: str,
        previous_sha: str,
    ) -> GitBranchUpdate:
        encoded_branch = quote(branch, safe="")
        status, payload = await self._request_json(
            "PATCH",
            self._repo_path(f"git/refs/heads/{encoded_branch}"),
            success_statuses={200},
            passthrough_statuses={409, 422},
            json_body={"sha": target_sha, "force": False},
        )
        if status == 200:
            updated = self._parse_reference(payload, branch)
            if updated.sha != target_sha:
                raise self._error(GitHubErrorCode.INVALID_RESPONSE)
            return GitBranchUpdate(
                branch=branch,
                sha=target_sha,
                action="updated",
                previous_sha=previous_sha,
            )

        # The update may have succeeded before a proxy emitted a conflict.
        current = await self._get_branch_ref_optional(branch)
        if current is not None and current.sha == target_sha:
            return GitBranchUpdate(
                branch=branch,
                sha=target_sha,
                action="unchanged",
                previous_sha=current.sha,
            )
        raise self._error(
            GitHubErrorCode.REF_CONFLICT,
            status_code=status,
        )

    def _parse_reference(self, payload: object, branch: str) -> GitReference:
        reference = _require_object(payload)
        if _require_string(reference, "ref") != f"refs/heads/{branch}":
            raise self._error(GitHubErrorCode.INVALID_RESPONSE)
        git_object = _require_object(reference.get("object"))
        if _require_string(git_object, "type") != "commit":
            raise self._error(GitHubErrorCode.INVALID_RESPONSE)
        return GitReference(
            branch=branch,
            sha=_require_sha(git_object, "sha"),
        )

    def _pull_matches(
        self,
        payload: dict[str, object],
        *,
        head_branch: str,
        base_branch: str,
    ) -> bool:
        if payload.get("state") != "open":
            return False
        head = payload.get("head")
        base = payload.get("base")
        if not isinstance(head, dict) or not isinstance(base, dict):
            return False
        if head.get("ref") != head_branch or base.get("ref") != base_branch:
            return False
        return self._pull_repository_matches(head) and self._pull_repository_matches(
            base
        )

    def _pull_repository_matches(self, endpoint: dict[str, object]) -> bool:
        repository = endpoint.get("repo")
        if not isinstance(repository, dict):
            return False
        return repository.get("full_name") == self.full_name

    def _pull_request(self, *, number: int, created: bool) -> GitPullRequest:
        return GitPullRequest(
            number=number,
            url=f"https://github.com/{self.full_name}/pull/{number}",
            created=created,
        )

    def _normalize_tree_entries(
        self,
        entries: Mapping[str, str] | Iterable[GitTreeEntry],
    ) -> tuple[GitTreeEntry, ...]:
        if isinstance(entries, Mapping):
            candidates = (
                GitTreeEntry(path=path, blob_sha=blob_sha)
                for path, blob_sha in entries.items()
            )
        else:
            try:
                candidates = iter(entries)
            except TypeError:
                raise self._error(
                    GitHubErrorCode.INVALID_CONFIGURATION
                ) from None

        normalized: list[GitTreeEntry] = []
        seen_paths: set[str] = set()
        try:
            for entry in candidates:
                if not isinstance(entry, GitTreeEntry):
                    raise ValueError("invalid tree entry")
                path = _validate_tree_path(entry.path)
                blob_sha = _validate_sha(entry.blob_sha)
                if entry.mode != "100644" or path in seen_paths:
                    raise ValueError("invalid tree entry")
                seen_paths.add(path)
                normalized.append(
                    GitTreeEntry(
                        path=path,
                        blob_sha=blob_sha,
                        mode="100644",
                    )
                )
        except (TypeError, ValueError):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION) from None
        if not normalized:
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        return tuple(sorted(normalized, key=lambda item: item.path))

    def _validated_sha(self, value: str) -> str:
        try:
            return _validate_sha(value)
        except (TypeError, ValueError):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION) from None

    def _validated_branch(self, value: str) -> str:
        try:
            return _validate_branch(value)
        except (TypeError, ValueError):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION) from None

    def _validated_commit_message(self, value: str) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or "\x00" in value
            or len(value.encode("utf-8")) > _MAX_COMMIT_MESSAGE_BYTES
        ):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        return value

    def _validated_pull_request_title(self, value: str) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or "\x00" in value
            or len(value) > 256
        ):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        return value

    def _validated_commit_signature(
        self,
        *,
        name: str,
        email: str,
        authored_at: datetime,
    ) -> dict[str, str]:
        if (
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or len(name.encode("utf-8")) > 160
            or not isinstance(email, str)
            or not email.isascii()
            or not _EMAIL_PATTERN.fullmatch(email)
            or len(email) > 254
            or not isinstance(authored_at, datetime)
            or authored_at.tzinfo is None
            or authored_at.utcoffset() is None
        ):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        timestamp = (
            authored_at.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        return {
            "name": name,
            "email": email,
            "date": timestamp,
        }

    def _validated_pull_request_body(self, value: str) -> str:
        if (
            not isinstance(value, str)
            or "\x00" in value
            or len(value.encode("utf-8")) > _MAX_PULL_REQUEST_BODY_BYTES
        ):
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        return value

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        success_statuses: set[int],
        passthrough_statuses: set[int] | None = None,
        params: Mapping[str, str] | None = None,
        json_body: object | None = None,
    ) -> tuple[int, object | None]:
        passthrough = passthrough_statuses or set()
        if self.is_closed or not self._token:
            raise self._error(GitHubErrorCode.INVALID_CONFIGURATION)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "Chronovita-content-publisher",
            "X-GitHub-Api-Version": _API_VERSION,
        }
        try:
            async with self._client.stream(
                method,
                path,
                headers=headers,
                params=params,
                json=json_body,
            ) as response:
                status = response.status_code
                if status in passthrough:
                    return status, None
                if status not in success_statuses:
                    raise self._status_error(status, response.headers)
                body = await self._read_limited_response(response)
        except GitHubGitDataError:
            raise
        except httpx.TimeoutException:
            raise self._error(GitHubErrorCode.TIMEOUT) from None
        except (httpx.HTTPError, TypeError, ValueError):
            raise self._error(GitHubErrorCode.UPSTREAM_UNAVAILABLE) from None

        try:
            payload = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_non_finite,
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise self._error(GitHubErrorCode.INVALID_RESPONSE) from None
        return status, payload

    async def _read_limited_response(self, response: httpx.Response) -> bytes:
        declared_length = response.headers.get("content-length")
        if declared_length is not None:
            try:
                parsed_length = int(declared_length)
            except ValueError:
                raise self._error(GitHubErrorCode.INVALID_RESPONSE) from None
            if parsed_length < 0 or parsed_length > _MAX_RESPONSE_BYTES:
                raise self._error(GitHubErrorCode.INVALID_RESPONSE)

        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                raise self._error(GitHubErrorCode.INVALID_RESPONSE)
            body.extend(chunk)
        return bytes(body)

    def _status_error(
        self,
        status_code: int,
        headers: httpx.Headers,
    ) -> GitHubGitDataError:
        if status_code == 401:
            code = GitHubErrorCode.AUTHENTICATION_FAILED
        elif status_code == 403 and (
            headers.get("x-ratelimit-remaining") == "0"
            or headers.get("retry-after") is not None
        ):
            code = GitHubErrorCode.RATE_LIMITED
        elif status_code == 403:
            code = GitHubErrorCode.PERMISSION_DENIED
        elif status_code in {408, 504}:
            code = GitHubErrorCode.TIMEOUT
        elif status_code == 429:
            code = GitHubErrorCode.RATE_LIMITED
        elif status_code in {409, 423}:
            code = GitHubErrorCode.REF_CONFLICT
        elif status_code >= 500:
            code = GitHubErrorCode.UPSTREAM_UNAVAILABLE
        elif 400 <= status_code < 500:
            code = GitHubErrorCode.REQUEST_REJECTED
        else:
            code = GitHubErrorCode.INVALID_RESPONSE
        return self._error(code, status_code=status_code)

    def _repo_path(self, suffix: str | None = None) -> str:
        base = (
            f"repos/{quote(self._owner, safe='')}/"
            f"{quote(self._repository, safe='')}"
        )
        return base if suffix is None else f"{base}/{suffix}"

    @staticmethod
    def _error(
        code: GitHubErrorCode,
        *,
        status_code: int | None = None,
    ) -> GitHubGitDataError:
        return GitHubGitDataError(code, status_code=status_code)


def _validate_repository_binding(
    repository_id: int,
    full_name: str,
) -> tuple[str, str]:
    if (
        isinstance(repository_id, bool)
        or not isinstance(repository_id, int)
        or repository_id < 1
        or not isinstance(full_name, str)
        or full_name != full_name.strip()
        or full_name.count("/") != 1
    ):
        raise ValueError("invalid repository binding")
    owner, repository = full_name.split("/", 1)
    if not _REPOSITORY_OWNER_PATTERN.fullmatch(owner):
        raise ValueError("invalid repository owner")
    if (
        not _REPOSITORY_NAME_PATTERN.fullmatch(repository)
        or repository in {".", ".."}
        or repository.endswith((".", ".lock"))
    ):
        raise ValueError("invalid repository name")
    return owner, repository


def _validate_token(token: str) -> None:
    if (
        not isinstance(token, str)
        or not 1 <= len(token) <= 4096
        or not token.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
    ):
        raise ValueError("invalid token")


def _validate_api_base_url(value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("invalid API base URL")
    parsed = httpx.URL(value)
    if (
        parsed.scheme != "https"
        or not parsed.host
        or parsed.userinfo
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid API base URL")
    return str(parsed).rstrip("/")


def _validate_sha(value: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_PATTERN.fullmatch(value):
        raise ValueError("invalid Git SHA")
    return value


def _validate_branch(value: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 200
        or value == "@"
        or value.startswith(("/", "-"))
        or value.endswith(("/", ".", ".lock"))
        or "//" in value
        or ".." in value
        or "@{" in value
        or any(char in value for char in " ~^:?*[\\")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(
            part in {"", ".", ".."} or part.endswith(".lock")
            for part in value.split("/")
        )
    ):
        raise ValueError("invalid branch")
    return value


def _validate_tree_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 512
        or value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("invalid tree path")
    parts = value.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part.casefold() == ".git"
        or any(ord(char) < 32 or ord(char) == 127 for char in part)
        for part in parts
    ):
        raise ValueError("invalid tree path")
    return value


def _require_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise GitHubGitDataError(GitHubErrorCode.INVALID_RESPONSE)
    return value


def _require_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise GitHubGitDataError(GitHubErrorCode.INVALID_RESPONSE)
    return value


def _require_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise GitHubGitDataError(GitHubErrorCode.INVALID_RESPONSE)
    return value


def _require_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GitHubGitDataError(GitHubErrorCode.INVALID_RESPONSE)
    return value


def _require_sha(payload: Mapping[str, object], key: str) -> str:
    try:
        return _validate_sha(_require_string(payload, key))
    except ValueError:
        raise GitHubGitDataError(GitHubErrorCode.INVALID_RESPONSE) from None


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("duplicate JSON key")
        payload[key] = value
    return payload


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


__all__ = [
    "GitBranchHead",
    "GitBranchUpdate",
    "GitCommitObject",
    "GitHubErrorCode",
    "GitHubGitDataClient",
    "GitHubGitDataError",
    "GitHubRepositoryIdentity",
    "GitPullRequest",
    "GitReference",
    "GitTreeEntry",
]
