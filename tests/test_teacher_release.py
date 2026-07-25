from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from zipfile import ZIP_STORED, ZipFile

from scripts.build_teacher_release import (
    CREDENTIAL_POLICY,
    PACKAGE_KIND,
    REQUIRED_PACKAGE_FILES,
    ROOT_COMMAND_FILES,
    SCHEMA_VERSION,
    TeacherPackageError,
    _scan_secret,
    build_teacher_release,
    verify_teacher_release,
)
from services.version import APP_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _create_minimal_source_repository(repository: Path) -> str:
    source_paths = {
        path
        for path in REQUIRED_PACKAGE_FILES
        if path != PurePosixPath("教师使用说明.txt")
    }
    source_paths.add(PurePosixPath("services/version.py"))
    source_paths.add(PurePosixPath("distribution/teacher/教师使用说明.txt"))
    for path in source_paths:
        absolute = repository.joinpath(*path.parts)
        absolute.parent.mkdir(parents=True, exist_ok=True)
        if path == PurePosixPath("services/version.py"):
            absolute.write_text('APP_VERSION = "1.2.3"\n', encoding="utf-8")
        elif path.suffix == ".cmd":
            absolute.write_bytes(b"@echo off\r\n")
        else:
            absolute.write_text(f"committed:{path.as_posix()}\n", encoding="utf-8")

    _run_git(repository, "init")
    _run_git(repository, "config", "user.name", "Teacher Package Test")
    _run_git(repository, "config", "user.email", "teacher-package@example.invalid")
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-m", "fixture")
    return _run_git(repository, "rev-parse", "HEAD")


def _write_minimal_forged_package(
    archive_path: Path,
    *,
    payload_path: str = "launch.cmd",
    credential_policy: object = CREDENTIAL_POLICY,
) -> None:
    package_root = "Chronovita-Teacher-Editor-v1.2.3"
    payload = b"@echo off\r\n"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_kind": PACKAGE_KIND,
        "app_version": "1.2.3",
        "source_commit": "working-tree",
        "created_at": "1980-01-01T00:00:00Z",
        "credential_policy": credential_policy,
        "payload_file_count": 1,
        "payload_size_bytes": len(payload),
        "files": [
            {
                "path": payload_path,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    with ZipFile(archive_path, mode="w", compression=ZIP_STORED) as bundle:
        bundle.writestr(
            f"{package_root}/{payload_path}",
            payload,
            compress_type=ZIP_STORED,
        )
        bundle.writestr(
            f"{package_root}/teacher-package-manifest.json",
            (json.dumps(manifest, ensure_ascii=False) + "\n").encode("utf-8"),
            compress_type=ZIP_STORED,
        )


class TeacherReleaseTests(unittest.TestCase):
    def test_release_shared_reader_preserves_empty_byte_arrays(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "teacher-release.yml"
        ).read_text("utf-8")
        self.assertIn("return ,$memory.ToArray()", workflow)
        self.assertNotIn("return $memory.ToArray()", workflow)

    def test_release_publication_can_complete_a_precreated_prerelease(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "teacher-release.yml"
        ).read_text("utf-8")
        view_index = workflow.index("gh release view")
        upload_index = workflow.index("gh release upload")
        edit_index = workflow.index("gh release edit")
        create_index = workflow.index("gh release create")
        self.assertLess(view_index, upload_index)
        self.assertLess(upload_index, edit_index)
        self.assertLess(edit_index, create_index)
        self.assertIn("--clobber", workflow[upload_index:edit_index])

    def test_cmd_launchers_reset_inherited_powershell_module_path(self):
        for relative_path in (
            Path("点我一键启动（部署）.cmd"),
            Path("点我一键关闭.cmd"),
            Path("scripts/teacher-editor.cmd"),
        ):
            with self.subTest(path=relative_path):
                source = (REPO_ROOT / relative_path).read_text("ascii")
                reset_index = source.index('set "PSModulePath="')
                powershell_index = source.index(
                    "powershell -NoProfile -ExecutionPolicy Bypass"
                )
                self.assertLess(reset_index, powershell_index)

    def test_build_is_deterministic_and_excludes_mutable_or_secret_state(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = build_teacher_release(
                source_root=REPO_ROOT,
                output_dir=Path(first_dir),
                version=APP_VERSION,
                commit="working-tree",
            )
            second = build_teacher_release(
                source_root=REPO_ROOT,
                output_dir=Path(second_dir),
                version=APP_VERSION,
                commit="working-tree",
            )

            self.assertEqual(first.archive_sha256, second.archive_sha256)
            self.assertEqual(
                hashlib.sha256(first.archive_path.read_bytes()).hexdigest(),
                first.archive_sha256,
            )
            self.assertIn(first.archive_sha256, first.checksum_path.read_text("ascii"))
            manifest = verify_teacher_release(first.archive_path)
            self.assertEqual(manifest["app_version"], APP_VERSION)
            self.assertFalse(
                manifest["credential_policy"]["bundled_credentials"]
            )
            paths = {
                PurePosixPath(record["path"])
                for record in manifest["files"]
            }
            self.assertIn(
                PurePosixPath("scripts/configure-content-history.ps1"),
                paths,
            )
            self.assertIn(
                PurePosixPath("scripts/stop-teacher-editor.ps1"),
                paths,
            )
            self.assertTrue(ROOT_COMMAND_FILES.issubset(paths))
            self.assertFalse(
                any(
                    part.casefold()
                    in {
                        ".chronovita-local",
                        ".git",
                        ".venv",
                        "data",
                        "drafts",
                        "node_modules",
                        "sealed",
                    }
                    for path in paths
                    for part in path.parts
                )
            )

    def test_root_stopper_delegates_without_duplicating_shutdown_logic(self):
        source = (REPO_ROOT / "点我一键关闭.cmd").read_text("ascii")
        self.assertIn("scripts\\stop-teacher-editor.ps1", source)
        self.assertIn("scripts\\stop-teacher-editor.cmd", source)
        self.assertNotIn("taskkill", source.casefold())

    def test_secret_scan_rejects_multiple_provider_and_database_credentials(self):
        samples = (
            b"sk-" + b"proj-" + b"abcdefghijklmnopqrstuvwxyz0123456789",
            b"xox" + b"b-" + b"123456789012-abcdefghijklmnopqrstuvwxyz",
            b"AI" + b"za" + (b"A" * 35),
            b"postgresql://" + b"teacher:correct-horse-battery-staple@db/chronovita",
            b"client_" + b'secret = "abcdefghijklmnopqrstuvwxyz012345"',
        )
        for sample in samples:
            with self.subTest(sample=sample[:16]), self.assertRaises(
                TeacherPackageError
            ):
                _scan_secret(PurePosixPath("apps/api/config.py"), sample)

    def test_verifier_rejects_unregistered_local_state(self):
        with tempfile.TemporaryDirectory() as output_dir:
            result = build_teacher_release(
                source_root=REPO_ROOT,
                output_dir=Path(output_dir),
                version=APP_VERSION,
                commit="working-tree",
            )
            with ZipFile(
                result.archive_path,
                mode="a",
                compression=ZIP_STORED,
            ) as bundle:
                root = bundle.namelist()[0].split("/", maxsplit=1)[0]
                bundle.writestr(
                    f"{root}/data/chronovita.db",
                    b"local-state",
                    compress_type=ZIP_STORED,
                )

            with self.assertRaisesRegex(
                TeacherPackageError,
                "unregistered files",
            ):
                verify_teacher_release(result.archive_path)

    def test_verifier_rejects_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as output_dir:
            result = build_teacher_release(
                source_root=REPO_ROOT,
                output_dir=Path(output_dir),
                version=APP_VERSION,
                commit="working-tree",
            )
            with ZipFile(
                result.archive_path,
                mode="a",
                compression=ZIP_STORED,
            ) as bundle:
                bundle.writestr(
                    "../outside.txt",
                    b"must-not-extract",
                    compress_type=ZIP_STORED,
                )

            with self.assertRaisesRegex(
                TeacherPackageError,
                "unsafe archive path",
            ):
                verify_teacher_release(result.archive_path)

    def test_verifier_rejects_windows_unsafe_archive_paths(self):
        unsafe_paths = (
            "CON.txt",
            "payload.txt:secret",
            "trailing.",
            "trailing ",
            "control-\x01.txt",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path), tempfile.TemporaryDirectory() as output_dir:
                archive_path = Path(output_dir) / "forged.zip"
                _write_minimal_forged_package(
                    archive_path,
                    payload_path=unsafe_path,
                )
                with self.assertRaisesRegex(
                    TeacherPackageError,
                    "unsafe archive path",
                ):
                    verify_teacher_release(archive_path)

    def test_verifier_rejects_package_missing_required_payload(self):
        with tempfile.TemporaryDirectory() as output_dir:
            archive_path = Path(output_dir) / "forged.zip"
            _write_minimal_forged_package(archive_path)
            with self.assertRaisesRegex(
                TeacherPackageError,
                "missing required files",
            ):
                verify_teacher_release(archive_path)

    def test_verifier_requires_exact_credential_policy(self):
        with tempfile.TemporaryDirectory() as output_dir:
            archive_path = Path(output_dir) / "forged.zip"
            _write_minimal_forged_package(
                archive_path,
                credential_policy={
                    **CREDENTIAL_POLICY,
                    "browser_receives_github_token": True,
                },
            )
            with self.assertRaisesRegex(
                TeacherPackageError,
                "credential policy is invalid",
            ):
                verify_teacher_release(archive_path)

    def test_full_commit_build_uses_git_blobs_not_working_tree_bytes(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
            source_root = Path(source_dir)
            commit = _create_minimal_source_repository(source_root)
            changed_path = source_root / "apps" / "api" / "main.py"
            committed_bytes = subprocess.run(
                ["git", "show", f"{commit}:apps/api/main.py"],
                cwd=source_root,
                check=True,
                capture_output=True,
            ).stdout
            changed_path.write_text("uncommitted-change\n", encoding="utf-8")

            result = build_teacher_release(
                source_root=source_root,
                output_dir=Path(output_dir),
                version="1.2.3",
                commit=commit,
            )

            with ZipFile(result.archive_path, mode="r") as bundle:
                package_root = bundle.namelist()[0].split("/", maxsplit=1)[0]
                packaged = bundle.read(f"{package_root}/apps/api/main.py")
            self.assertEqual(packaged, committed_bytes)
            self.assertNotEqual(packaged, changed_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
