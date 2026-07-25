import hashlib
import json
import unicodedata
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from services.contracts.archive_examples import (
    ARCHIVE_EXAMPLE_PACKAGE_DIRECTORY,
    archive_example_documents,
    archive_example_package_files,
    build_dayu_archive_package,
    build_dayu_publication_intent,
    build_dayu_publication_record,
    build_dayu_publish_request,
    build_example_repository_binding,
)
from services.contracts.archive_v1 import (
    ARCHIVE_MANIFEST_FILENAME,
    ARCHIVE_SCHEMA_DOCUMENTS,
    CourseArchiveFileV1,
    CourseArchiveManifestV1,
    CourseArchivePublishRequestV1,
    GitPublicationRecordV1,
    GitRepositoryBindingV1,
    archive_id_for_checksum,
    lesson_archive_paths,
    parse_signed_archive_manifest,
    parse_signed_publication_intent,
    parse_signed_publication_record,
    publication_branch_name,
    publication_operation_key,
    repository_archive_path,
    safe_archive_filename,
    schema_document,
    sign_publication_metadata,
    verify_archive_manifest_checksum,
    verify_publication_metadata_checksum,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "archive" / "v1"
EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "archive" / "v1"
PACKAGE_DIR = EXAMPLE_DIR / ARCHIVE_EXAMPLE_PACKAGE_DIRECTORY
CONTENT_HISTORY_TARGET = REPO_ROOT / "infra" / "content-history-target.json"


class ArchiveContractTests(unittest.TestCase):
    def test_committed_schemas_examples_and_package_match_builders(self):
        for filename, (model, schema_id, comment) in ARCHIVE_SCHEMA_DOCUMENTS.items():
            with self.subTest(schema=filename):
                self.assertEqual(
                    _read_json(SCHEMA_DIR / filename),
                    schema_document(model, schema_id, comment),
                )

        examples = archive_example_documents()
        for filename, example in examples.items():
            with self.subTest(example=filename):
                self.assertEqual(
                    _read_json(EXAMPLE_DIR / filename),
                    example.model_dump(mode="json"),
                )
        self.assertEqual(
            {path.name for path in SCHEMA_DIR.glob("*.json")},
            set(ARCHIVE_SCHEMA_DOCUMENTS),
        )
        self.assertEqual(
            {path.name for path in EXAMPLE_DIR.glob("*.json")},
            set(examples),
        )

        expected_package = archive_example_package_files()
        committed_paths = {
            path.relative_to(PACKAGE_DIR).as_posix()
            for path in PACKAGE_DIR.rglob("*")
            if path.is_file()
        }
        self.assertEqual(committed_paths, set(expected_package))
        for relative_path, expected_bytes in expected_package.items():
            with self.subTest(package_file=relative_path):
                self.assertEqual(
                    PACKAGE_DIR.joinpath(*Path(relative_path).parts).read_bytes(),
                    expected_bytes,
                )

    def test_manifest_describes_exact_package_bytes(self):
        manifest, package_files = build_dayu_archive_package()
        self.assertTrue(verify_archive_manifest_checksum(manifest))
        self.assertNotIn(ARCHIVE_MANIFEST_FILENAME, {item.path for item in manifest.files})
        self.assertEqual(manifest.file_count, len(package_files) - 1)
        self.assertEqual(
            manifest.total_size_bytes,
            sum(
                len(package_files[item.path])
                for item in manifest.files
            ),
        )
        for descriptor in manifest.files:
            with self.subTest(path=descriptor.path):
                payload = package_files[descriptor.path]
                self.assertEqual(descriptor.size_bytes, len(payload))
                self.assertEqual(
                    descriptor.blob_sha256,
                    hashlib.sha256(payload).hexdigest(),
                )

    def test_archive_identity_binds_renderer_and_file_tree(self):
        first, _ = build_dayu_archive_package()
        second, _ = build_dayu_archive_package()
        self.assertEqual(first.archive_id, second.archive_id)
        self.assertEqual(first.archive_checksum, second.archive_checksum)
        self.assertEqual(first.manifest_checksum, second.manifest_checksum)

        changed_renderer = first.model_dump(mode="json")
        changed_renderer["renderer"]["renderer_version"] += 1
        with self.assertRaisesRegex(
            ValidationError,
            "archive_checksum must cover",
        ):
            CourseArchiveManifestV1.model_validate(changed_renderer)

        changed_file = first.model_dump(mode="json")
        changed_file["files"][0]["blob_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            ValidationError,
            "archive_checksum must cover",
        ):
            CourseArchiveManifestV1.model_validate(changed_file)

    def test_manifest_rejects_contract_identity_and_path_collisions(self):
        manifest, _ = build_dayu_archive_package()
        wrong_release = manifest.model_dump(mode="json")
        release_file = next(
            item
            for item in wrong_release["files"]
            if item["kind"] == "release-manifest"
        )
        release_file["contract_checksum"] = "a" * 64
        with self.assertRaisesRegex(
            ValidationError,
            "source release manifest identity",
        ):
            CourseArchiveManifestV1.model_validate(wrong_release)

        collision = manifest.model_dump(mode="json")
        duplicate = deepcopy(collision["files"][0])
        duplicate["path"] = duplicate["path"].replace("lessons/", "LESSONS/", 1)
        collision["files"].append(duplicate)
        collision["files"].sort(key=lambda item: item["path"].casefold())
        collision["file_count"] += 1
        collision["total_size_bytes"] += duplicate["size_bytes"]
        with self.assertRaisesRegex(
            ValidationError,
            "unique after Unicode/case folding",
        ):
            CourseArchiveManifestV1.model_validate(collision)

    def test_archive_paths_are_portable_and_normalized(self):
        invalid_paths = (
            "../escape.json",
            "lessons\\lesson-a\\file.json",
            "/absolute.json",
            "lessons/CON/file.json",
            "lessons/.git/config.json",
            "lessons/lesson-a/bad?.json",
            f"lessons/lesson-a/{unicodedata.normalize('NFD', 'é')}.json",
            f"lessons/lesson-a/{'😀' * 100}.json",
        )
        for path in invalid_paths:
            with self.subTest(path=path), self.assertRaises(ValidationError):
                CourseArchiveFileV1(
                    path=path,
                    kind="format-layer",
                    media_type="application/json",
                    size_bytes=2,
                    blob_sha256="a" * 64,
                    lesson_id="lesson-a",
                )

        self.assertEqual(safe_archive_filename(" CON ", "lesson-a"), "_CON")
        self.assertEqual(safe_archive_filename("标题：测试", "lesson-a"), "标题测试")
        emoji_filename = safe_archive_filename("😀" * 100, "lesson-a")
        self.assertLessEqual(len(emoji_filename.encode("utf-8")), 180)
        self.assertLessEqual(len(emoji_filename.encode("utf-16-le")) // 2, 80)
        paths = lesson_archive_paths("lesson-a", "同名课程")
        self.assertTrue(all(path.startswith("lessons/lesson-a/") for path in paths.values()))

    def test_repository_binding_is_server_owned_and_secret_free(self):
        binding = build_example_repository_binding()
        self.assertEqual(binding.visibility, "private")
        self.assertEqual(binding.allowed_modes, ("pull_request", "direct_commit"))

        raw = binding.model_dump(mode="json")
        raw["token"] = "credential-must-not-be-accepted"
        with self.assertRaises(ValidationError):
            GitRepositoryBindingV1.model_validate(raw)

        missing_installation = binding.model_dump(mode="json")
        missing_installation["installation_id"] = None
        with self.assertRaisesRegex(ValidationError, "require installation_id"):
            GitRepositoryBindingV1.model_validate(missing_installation)

        token_binding = binding.model_dump(mode="json")
        token_binding["credential_kind"] = "fine_grained_token"
        with self.assertRaisesRegex(ValidationError, "cannot claim"):
            GitRepositoryBindingV1.model_validate(token_binding)

        unordered_modes = binding.model_dump(mode="json")
        unordered_modes["allowed_modes"] = ["direct_commit", "pull_request"]
        with self.assertRaisesRegex(ValidationError, "unique, ordered"):
            GitRepositoryBindingV1.model_validate(unordered_modes)

        public_repo = binding.model_dump(mode="json")
        public_repo["visibility"] = "public"
        with self.assertRaises(ValidationError):
            GitRepositoryBindingV1.model_validate(public_repo)

    def test_publish_request_cannot_override_repository_or_skip_confirmation(self):
        request = build_dayu_publish_request()
        raw = request.model_dump(mode="json")
        raw["repository"] = "attacker/other"
        with self.assertRaises(ValidationError):
            CourseArchivePublishRequestV1.model_validate(raw)

        direct = request.model_copy(
            update={
                "mode": "direct_commit",
                "direct_commit_confirmed": False,
            }
        ).model_dump(mode="json")
        with self.assertRaisesRegex(ValidationError, "explicit confirmation"):
            CourseArchivePublishRequestV1.model_validate(direct)

        wrong_archive = request.model_dump(mode="json")
        wrong_archive["archive_id"] = archive_id_for_checksum("f" * 64)
        with self.assertRaisesRegex(ValidationError, "must derive"):
            CourseArchivePublishRequestV1.model_validate(wrong_archive)

    def test_operation_key_is_idempotent_but_target_and_mode_specific(self):
        binding = build_example_repository_binding()
        request = build_dayu_publish_request()
        key = publication_operation_key(binding, request)
        retry = request.model_copy(
            update={
                "client_request_id": "request-dayu-archive-002",
                "change_summary": "重试时调整给审校者看的说明。",
            }
        )
        self.assertEqual(publication_operation_key(binding, retry), key)

        direct = request.model_copy(
            update={
                "mode": "direct_commit",
                "direct_commit_confirmed": True,
            }
        )
        self.assertNotEqual(publication_operation_key(binding, direct), key)

        other_target = binding.model_copy(update={"repository_id": 987654321})
        self.assertNotEqual(publication_operation_key(other_target, request), key)

    def test_publication_record_preserves_partial_success_for_retry(self):
        intent = build_dayu_publication_intent()
        request = intent.request
        branch = publication_branch_name(
            request.course_id,
            request.release_id,
            request.expected_archive_checksum,
        )
        failed_at = intent.requested_at + timedelta(seconds=10)
        unsigned = GitPublicationRecordV1(
            intent=intent,
            status="failed_retryable",
            attempt=1,
            revision=4,
            branch_ref=branch,
            base_sha="1" * 40,
            tree_sha="2" * 40,
            commit_sha="3" * 40,
            last_error_code="github_pr_timeout",
            last_error_at=failed_at,
            updated_at=failed_at,
            checksum="0" * 64,
        )
        record = sign_publication_metadata(unsigned)
        self.assertEqual(record.commit_sha, "3" * 40)
        self.assertTrue(verify_publication_metadata_checksum(record))

        missing_error_time = record.model_dump(mode="json")
        missing_error_time["last_error_at"] = None
        with self.assertRaisesRegex(ValidationError, "code and timestamp"):
            GitPublicationRecordV1.model_validate(missing_error_time)

    def test_publication_record_rejects_wrong_branch_and_pr_repository(self):
        record = build_dayu_publication_record()
        self.assertTrue(verify_publication_metadata_checksum(record.intent))
        self.assertTrue(verify_publication_metadata_checksum(record))

        wrong_branch = record.model_dump(mode="json")
        wrong_branch["branch_ref"] = "chronovita/forged"
        with self.assertRaisesRegex(ValidationError, "branch_ref must derive"):
            GitPublicationRecordV1.model_validate(wrong_branch)

        wrong_url = record.model_dump(mode="json")
        wrong_url["pull_request_url"] = "https://github.com/other/repository/pull/17"
        with self.assertRaisesRegex(ValidationError, "configured repository"):
            GitPublicationRecordV1.model_validate(wrong_url)

    def test_publication_checksums_detect_tampering(self):
        record = build_dayu_publication_record()
        self.assertEqual(
            parse_signed_publication_intent(
                record.intent.model_dump(mode="json")
            ),
            record.intent,
        )
        self.assertEqual(
            parse_signed_publication_record(record.model_dump(mode="json")),
            record,
        )
        tampered = record.model_copy(update={"revision": record.revision + 1})
        self.assertFalse(verify_publication_metadata_checksum(tampered))

        manifest, _ = build_dayu_archive_package()
        self.assertEqual(
            parse_signed_archive_manifest(manifest.model_dump(mode="json")),
            manifest,
        )
        tampered_manifest = manifest.model_copy(
            update={"manifest_checksum": "f" * 64}
        )
        self.assertFalse(verify_archive_manifest_checksum(tampered_manifest))
        with self.assertRaisesRegex(ValueError, "archive manifest checksum mismatch"):
            parse_signed_archive_manifest(
                tampered_manifest.model_dump(mode="json")
            )

        nested_tampering = record.model_dump(mode="json")
        nested_tampering["intent"]["request"]["change_summary"] = "changed"
        outer_resigned = sign_publication_metadata(
            GitPublicationRecordV1.model_validate(nested_tampering)
        )
        with self.assertRaisesRegex(ValueError, "invalid intent checksum"):
            parse_signed_publication_record(
                outer_resigned.model_dump(mode="json")
            )

    def test_repository_path_combines_binding_root_exactly_once(self):
        binding = build_example_repository_binding()
        manifest, _ = build_dayu_archive_package()
        self.assertEqual(
            repository_archive_path(binding, manifest),
            (
                "courses/C-early-civilization/releases/"
                f"rel-01a2b3c4d5-0001/{manifest.archive_id}"
            ),
        )
        self.assertNotIn("courses/courses/", repository_archive_path(binding, manifest))

    def test_examples_do_not_contain_credentials(self):
        forbidden_fragments = (
            "gh" + "p_",
            "github_" + "pat_",
            "private_key",
            "client_secret",
        )
        serialized = json.dumps(
            {
                name: document.model_dump(mode="json")
                for name, document in archive_example_documents().items()
            },
            ensure_ascii=False,
        ).casefold()
        serialized += b"".join(archive_example_package_files().values()).decode(
            "utf-8"
        ).casefold()
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, serialized)

    def test_real_content_history_target_is_private_explicit_and_inactive(self):
        target = _read_json(CONTENT_HISTORY_TARGET)
        self.assertEqual(target["schema_version"], "content-history-target/v1")
        self.assertEqual(target["binding_id"], "content-history-primary")
        self.assertEqual(target["repository_id"], 1311692460)
        self.assertEqual(target["owner"], "falling-feather")
        self.assertEqual(target["repository"], "Chronovita-Course-Content")
        self.assertEqual(target["visibility"], "private")
        self.assertEqual(target["base_branch"], "main")
        self.assertEqual(target["root_prefix"], "courses")
        self.assertEqual(target["default_publication_mode"], "pull_request")
        self.assertEqual(
            target["allowed_publication_modes"],
            ["pull_request", "direct_commit"],
        )
        self.assertTrue(target["direct_commit_requires_confirmation"])
        self.assertTrue(target["activation"]["repository_ready"])
        self.assertFalse(target["activation"]["runtime_publication_enabled"])

        binding = GitRepositoryBindingV1.model_validate(
            {
                "binding_id": target["binding_id"],
                "provider": target["provider"],
                "repository_id": target["repository_id"],
                "owner": target["owner"],
                "repository": target["repository"],
                "visibility": target["visibility"],
                "base_branch": target["base_branch"],
                "root_prefix": target["root_prefix"],
                "credential_kind": "fine_grained_token",
                "installation_id": None,
                "allowed_modes": target["allowed_publication_modes"],
            }
        )
        self.assertEqual(binding.full_name, "falling-feather/Chronovita-Course-Content")

        serialized = json.dumps(target, ensure_ascii=False).casefold()
        for fragment in (
            "gh" + "p_",
            "github_" + "pat_",
            "private_key",
            "client_secret",
            "access_token",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, serialized)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
