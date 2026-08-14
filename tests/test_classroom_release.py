from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from zipfile import ZIP_STORED, ZipFile

from scripts.build_classroom_release import (
    CREDENTIAL_POLICY,
    NETWORK_POLICY,
    OFFLINE_POLICY,
    ClassroomPackageError,
    build_classroom_release,
    verify_classroom_release,
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _write(repository: Path, relative: str, raw: bytes) -> None:
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _fixture(repository: Path) -> str:
    wheel_raw = b"fixture-wheel"
    wheel_hash = hashlib.sha256(wheel_raw).hexdigest()
    model_raw = b"fixture-model"
    model_hash = hashlib.sha256(model_raw).hexdigest()
    files = {
        "apps/api/main.py": b"app = 'classroom'\n",
        "apps/api/requirements.lock": (
            f"example-pkg==1.0 \\\n+    --hash=sha256:{wheel_hash}\n"
        ).encode("ascii"),
        "apps/web/package-lock.json": json.dumps(
            {
                "packages": {
                    "": {"version": "1.2.3"},
                    "node_modules/react": {"version": "18.3.1", "license": "MIT"},
                }
            }
        ).encode("utf-8"),
        "services/version.py": b'APP_VERSION = "1.2.3"\n',
        "content/scenarios/catalog.v1.json": b"{}\n",
        "scripts/classroom.cmd": b"@echo off\r\n",
        "scripts/classroom.ps1": b"param([switch] $Lan)\n",
        "scripts/stop-classroom.cmd": b"@echo off\r\n",
        "scripts/stop-classroom.ps1": b"param()\n",
        "scripts/initialize_classroom.py": b"# initialize\n",
        "scripts/prepare_rag_model.py": b"# verify model\n",
        "distribution/classroom/课堂使用说明.txt": "fixture instructions\n".encode(),
    }
    for relative, raw in files.items():
        _write(repository, relative, raw)
    model_manifest = {
        "schema_version": "rag-model-resource/v1",
        "model_id": "BAAI/bge-small-zh-v1.5",
        "source_revision": "fixture-revision",
        "license": "MIT",
        "license_url": "https://example.invalid/model",
        "files": [
            {
                "path": "model_optimized.onnx",
                "sha256": model_hash,
                "bytes": len(model_raw),
            }
        ],
    }
    _write(
        repository,
        "distribution/models/BAAI-bge-small-zh-v1.5/model-resource.json",
        (json.dumps(model_manifest) + "\n").encode(),
    )
    _write(
        repository,
        "distribution/models/BAAI-bge-small-zh-v1.5/model_optimized.onnx",
        model_raw,
    )
    _write(repository, "apps/web/dist/index.html", b"<title>Chronovita</title>")
    _write(repository, "apps/web/dist/assets/app-123.js", b"console.log('ok')")
    _write(
        repository,
        "distribution/wheelhouse/windows-py311/example_pkg-1.0-py3-none-any.whl",
        wheel_raw,
    )
    _git(repository, "init")
    _git(repository, "config", "user.name", "Classroom Package Test")
    _git(repository, "config", "user.email", "classroom@example.invalid")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "fixture")
    return _git(repository, "rev-parse", "HEAD")


class ClassroomReleaseTests(unittest.TestCase):
    def test_build_is_deterministic_and_contract_is_verifiable(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            root = Path(source)
            _fixture(root)
            one = build_classroom_release(
                source_root=root,
                output_dir=Path(first),
                version="1.2.3",
                commit="working-tree",
            )
            two = build_classroom_release(
                source_root=root,
                output_dir=Path(second),
                version="1.2.3",
                commit="working-tree",
            )
            self.assertEqual(one.archive_sha256, two.archive_sha256)
            manifest = verify_classroom_release(one.archive_path)
            self.assertEqual(manifest["credential_policy"], CREDENTIAL_POLICY)
            self.assertEqual(manifest["network_policy"], NETWORK_POLICY)
            self.assertEqual(manifest["offline_policy"], OFFLINE_POLICY)
            paths = {PurePosixPath(item["path"]) for item in manifest["files"]}
            self.assertIn(PurePosixPath("启动Chronovita课堂.cmd"), paths)
            self.assertIn(PurePosixPath("apps/web/dist/index.html"), paths)
            self.assertTrue(
                any(path.parts[:3] == ("distribution", "wheelhouse", "windows-py311") for path in paths)
            )
            self.assertFalse(
                any(part.casefold() in {"data", ".venv", ".git"} for path in paths for part in path.parts)
            )
            with ZipFile(one.archive_path) as bundle:
                packaged_licenses = bundle.read(
                    "Chronovita-Classroom-v1.2.3/依赖与模型许可清单.json"
                ).decode("utf-8")
            self.assertEqual(one.license_path.read_text("utf-8"), packaged_licenses)

    def test_full_commit_uses_committed_application_source(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            root = Path(source)
            commit = _fixture(root)
            committed = (root / "apps/api/main.py").read_bytes()
            (root / "apps/api/main.py").write_text("uncommitted = True\n", encoding="utf-8")
            result = build_classroom_release(
                source_root=root,
                output_dir=Path(output),
                version="1.2.3",
                commit=commit,
            )
            with ZipFile(result.archive_path) as bundle:
                packaged = bundle.read("Chronovita-Classroom-v1.2.3/apps/api/main.py")
            self.assertEqual(packaged, committed)

    def test_verifier_rejects_archive_traversal_and_unregistered_state(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            root = Path(source)
            _fixture(root)
            result = build_classroom_release(
                source_root=root,
                output_dir=Path(output),
                version="1.2.3",
                commit="working-tree",
            )
            with ZipFile(result.archive_path, "a", compression=ZIP_STORED) as bundle:
                bundle.writestr("../outside.txt", b"unsafe", compress_type=ZIP_STORED)
            with self.assertRaisesRegex(ClassroomPackageError, "unsafe archive path"):
                verify_classroom_release(result.archive_path)


if __name__ == "__main__":
    unittest.main()
