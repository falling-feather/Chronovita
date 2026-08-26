from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from packaging.utils import canonicalize_name, parse_wheel_filename

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_teacher_release import _scan_secret, _validate_path_text


SCHEMA_VERSION = "chronovita-classroom-package/v1"
LICENSE_SCHEMA_VERSION = "chronovita-classroom-licenses/v1"
PACKAGE_KIND = "windows-lan-classroom"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_ROOT_PATTERN = re.compile(
    r"^Chronovita-Classroom-v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$"
)
MAX_PACKAGE_FILES = 8192
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024

SOURCE_PREFIXES = (
    PurePosixPath("apps/api"),
    PurePosixPath("services"),
    PurePosixPath("content"),
)
EXACT_SOURCE_FILES = {
    PurePosixPath("scripts/classroom.cmd"),
    PurePosixPath("scripts/classroom.ps1"),
    PurePosixPath("scripts/stop-classroom.cmd"),
    PurePosixPath("scripts/stop-classroom.ps1"),
    PurePosixPath("scripts/initialize_classroom.py"),
    PurePosixPath("scripts/prepare_rag_model.py"),
}
INSTRUCTION_SOURCE = PurePosixPath("distribution/classroom/课堂使用说明.txt")
INSTRUCTION_DESTINATION = PurePosixPath("课堂使用说明.txt")
LICENSE_DESTINATION = PurePosixPath("依赖与模型许可清单.json")
ROOT_START = PurePosixPath("启动Chronovita课堂.cmd")
ROOT_STOP = PurePosixPath("关闭Chronovita课堂.cmd")
ROOT_COMMAND_FILES = frozenset({ROOT_START, ROOT_STOP})
MODEL_DESTINATION = PurePosixPath(
    "distribution/models/BAAI-bge-small-zh-v1.5"
)
WHEELHOUSE_DESTINATION = PurePosixPath(
    "distribution/wheelhouse/windows-py311"
)
WEB_DIST_DESTINATION = PurePosixPath("apps/web/dist")
MANIFEST_NAME = "classroom-package-manifest.json"

REQUIRED_PACKAGE_FILES = {
    ROOT_START,
    ROOT_STOP,
    INSTRUCTION_DESTINATION,
    LICENSE_DESTINATION,
    PurePosixPath("scripts/classroom.cmd"),
    PurePosixPath("scripts/classroom.ps1"),
    PurePosixPath("scripts/stop-classroom.cmd"),
    PurePosixPath("scripts/stop-classroom.ps1"),
    PurePosixPath("scripts/initialize_classroom.py"),
    PurePosixPath("scripts/prepare_rag_model.py"),
    PurePosixPath("apps/api/main.py"),
    PurePosixPath("apps/api/requirements.lock"),
    PurePosixPath("services/version.py"),
    PurePosixPath("content/scenarios/catalog.v1.json"),
    PurePosixPath("apps/web/dist/index.html"),
    MODEL_DESTINATION / "model-resource.json",
    MODEL_DESTINATION / "model_optimized.onnx",
}

CREDENTIAL_POLICY = {
    "bundled_credentials": False,
    "first_admin_password": "secure-prompt-or-process-environment",
    "password_persisted_in_config": False,
    "browser_session": "httponly-cookie",
}
NETWORK_POLICY = {
    "ports": 1,
    "default_bind": "127.0.0.1",
    "lan_bind": "0.0.0.0",
    "lan_requires_explicit_switch": "-Lan",
}
OFFLINE_POLICY = {
    "python_wheelhouse": "windows-py311-hash-locked",
    "vector_model_bundled": True,
    "fts_fallback": True,
    "extractive_answer_fallback": True,
}
FORBIDDEN_PARTS = {
    ".chronovita-classroom",
    ".chronovita-local",
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "node_modules",
    "storage",
    "uploads",
}
TEXT_SUFFIXES = {
    ".cmd",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".svg",
    ".txt",
    ".yaml",
    ".yml",
}


class ClassroomPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageFile:
    path: PurePosixPath
    size_bytes: int
    sha256: str
    raw: bytes | None = None
    source: Path | None = None

    def write_to(self, destination: BinaryIO) -> None:
        if self.raw is not None:
            destination.write(self.raw)
            return
        if self.source is None:
            raise ClassroomPackageError(f"package file has no source: {self.path}")
        with self.source.open("rb") as handle:
            shutil.copyfileobj(handle, destination, length=1024 * 1024)


@dataclass(frozen=True)
class ClassroomPackageBuild:
    archive_path: Path
    checksum_path: Path
    license_path: Path
    archive_sha256: str
    manifest: dict[str, object]


def _git_entries(
    source_root: Path, commit: str
) -> tuple[tuple[PurePosixPath, str | None], ...]:
    arguments = (
        ["git", "ls-files", "-z"]
        if commit == "working-tree"
        else ["git", "ls-tree", "-r", "-z", commit]
    )
    result = subprocess.run(arguments, cwd=source_root, capture_output=True)
    if result.returncode != 0:
        raise ClassroomPackageError(
            "git tracked-file discovery failed: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    entries: list[tuple[PurePosixPath, str | None]] = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        if commit == "working-tree":
            path_raw, mode = item, None
        else:
            try:
                metadata, path_raw = item.split(b"\t", maxsplit=1)
                mode = metadata.split(b" ", maxsplit=1)[0].decode("ascii")
            except (UnicodeDecodeError, ValueError) as exc:
                raise ClassroomPackageError("git tree entry is invalid") from exc
        entries.append((PurePosixPath(path_raw.decode("utf-8")), mode))
    if not entries:
        raise ClassroomPackageError("repository has no tracked files")
    return tuple(entries)


def _is_under(path: PurePosixPath, prefix: PurePosixPath) -> bool:
    return path == prefix or prefix in path.parents


def _is_source_file(path: PurePosixPath) -> bool:
    if path in EXACT_SOURCE_FILES or path == INSTRUCTION_SOURCE:
        return True
    if any(part.casefold() in FORBIDDEN_PARTS for part in path.parts):
        return False
    if path.name.casefold().startswith(".env"):
        return False
    if path.name in {".gitignore", ".gitkeep"}:
        return False
    return any(_is_under(path, prefix) for prefix in SOURCE_PREFIXES)


def _validate_relative_path(path: PurePosixPath) -> None:
    try:
        _validate_path_text(path.as_posix())
    except RuntimeError as exc:
        raise ClassroomPackageError(str(exc)) from exc
    if any(part.casefold() in FORBIDDEN_PARTS for part in path.parts):
        raise ClassroomPackageError(f"forbidden classroom package path: {path}")
    if path.name.casefold().startswith(".env"):
        raise ClassroomPackageError(f"environment file cannot enter package: {path}")


def _read_git_file(
    source_root: Path,
    path: PurePosixPath,
    *,
    commit: str,
    mode: str | None,
) -> bytes:
    if commit == "working-tree":
        absolute = source_root.joinpath(*path.parts)
        if absolute.is_symlink() or not absolute.is_file():
            raise ClassroomPackageError(f"invalid tracked source: {path}")
        raw = absolute.read_bytes()
    else:
        if mode not in {"100644", "100755"}:
            raise ClassroomPackageError(f"non-regular Git source is not allowed: {path}")
        result = subprocess.run(
            ["git", "show", f"{commit}:{path.as_posix()}"],
            cwd=source_root,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ClassroomPackageError(f"cannot read source commit file: {path}")
        raw = result.stdout
    if len(raw) > MAX_SINGLE_FILE_BYTES:
        raise ClassroomPackageError(f"package source is too large: {path}")
    return raw


def _bytes_file(path: PurePosixPath, raw: bytes) -> PackageFile:
    _validate_relative_path(path)
    if len(raw) > MAX_SINGLE_FILE_BYTES:
        raise ClassroomPackageError(f"package file is too large: {path}")
    if path.suffix.casefold() == ".cmd" and not raw.isascii():
        raise ClassroomPackageError(f"CMD must remain ASCII-only: {path}")
    if path.suffix.casefold() in TEXT_SUFFIXES:
        _scan_package_secret(path, raw)
    return PackageFile(path, len(raw), hashlib.sha256(raw).hexdigest(), raw=raw)


def _path_file(path: PurePosixPath, source: Path) -> PackageFile:
    _validate_relative_path(path)
    if source.is_symlink() or not source.is_file():
        raise ClassroomPackageError(f"generated package source is invalid: {source}")
    size = source.stat().st_size
    if size > MAX_SINGLE_FILE_BYTES:
        raise ClassroomPackageError(f"package file is too large: {path}")
    digest = _hash_path(source)
    if path.suffix.casefold() in TEXT_SUFFIXES:
        raw = source.read_bytes()
        if path.suffix.casefold() == ".cmd" and not raw.isascii():
            raise ClassroomPackageError(f"CMD must remain ASCII-only: {path}")
        _scan_package_secret(path, raw)
    return PackageFile(path, size, digest, source=source)


def _scan_package_secret(path: PurePosixPath, raw: bytes) -> None:
    try:
        _scan_secret(path, raw)
    except RuntimeError as exc:
        raise ClassroomPackageError(str(exc)) from exc


def _hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _root_command(script: str) -> bytes:
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        'set "PSModulePath="\r\n'
        f'call "%~dp0scripts\\{script}" %*\r\n'
        "exit /b %ERRORLEVEL%\r\n"
    ).encode("ascii")


def _version_bytes(source_root: Path, commit: str) -> bytes:
    path = PurePosixPath("services/version.py")
    if commit == "working-tree":
        return source_root.joinpath(*path.parts).read_bytes()
    result = subprocess.run(
        ["git", "show", f"{commit}:{path.as_posix()}"],
        cwd=source_root,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ClassroomPackageError("services/version.py is missing from source commit")
    return result.stdout


def _created_at(source_root: Path, commit: str) -> str:
    if commit == "working-tree":
        return "1980-01-01T00:00:00Z"
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", commit],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise ClassroomPackageError("cannot resolve source commit timestamp")
    try:
        parsed = datetime.fromisoformat(result.stdout.strip())
    except ValueError as exc:
        raise ClassroomPackageError("source commit timestamp is invalid") from exc
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _requirement_records(lock_path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in lock_path.read_text("utf-8").splitlines():
        match = re.match(
            r"^([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_.,-]+\])?==([^\s\\]+)",
            line,
        )
        if match:
            current = {
                "name": canonicalize_name(match.group(1)),
                "version": match.group(2),
                "hashes": [],
            }
            records.append(current)
        if current is not None:
            for digest in re.findall(r"--hash=sha256:([0-9a-f]{64})", line):
                current["hashes"].append(digest)  # type: ignore[index, union-attr]
    if not records or any(not record["hashes"] for record in records):
        raise ClassroomPackageError("Python requirements lock is incomplete")
    return records


def _metadata_license(name: str, version: str) -> tuple[str, str | None]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN", None
    if distribution.version != version:
        return "UNKNOWN", None
    metadata = distribution.metadata
    expression = metadata.get("License-Expression")
    license_name = expression or metadata.get("License") or "UNKNOWN"
    if license_name == "UNKNOWN":
        for classifier in metadata.get_all("Classifier", []):
            if classifier.startswith("License ::"):
                license_name = classifier.rsplit("::", maxsplit=1)[-1].strip()
                break
    return license_name.strip() or "UNKNOWN", metadata.get("Home-page")


def _license_manifest(
    source_root: Path,
    *,
    version: str,
    created_at: str,
    model_resource: dict[str, object],
) -> dict[str, object]:
    python: list[dict[str, object]] = []
    for requirement in _requirement_records(source_root / "apps/api/requirements.lock"):
        name = str(requirement["name"])
        package_version = str(requirement["version"])
        license_name, homepage = _metadata_license(name, package_version)
        python.append(
            {
                "name": name,
                "version": package_version,
                "license": license_name,
                "homepage": homepage,
            }
        )

    lock = json.loads((source_root / "apps/web/package-lock.json").read_text("utf-8"))
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise ClassroomPackageError("frontend package lock does not contain packages")
    javascript: list[dict[str, object]] = []
    for package_path, metadata in packages.items():
        if not package_path.startswith("node_modules/") or not isinstance(metadata, dict):
            continue
        if metadata.get("dev") is True:
            continue
        name = package_path.removeprefix("node_modules/")
        package_version = metadata.get("version")
        if not isinstance(package_version, str):
            continue
        javascript.append(
            {
                "name": name,
                "version": package_version,
                "license": metadata.get("license", "UNKNOWN"),
            }
        )

    return {
        "schema_version": LICENSE_SCHEMA_VERSION,
        "app_version": version,
        "created_at": created_at,
        "notice": (
            "This inventory records bundled runtime dependencies and the local "
            "embedding model. UNKNOWN means metadata was unavailable; it is not a "
            "license assertion."
        ),
        "python": sorted(python, key=lambda item: str(item["name"])),
        "javascript_bundles": sorted(
            javascript, key=lambda item: (str(item["name"]), str(item["version"]))
        ),
        "models": [
            {
                "model_id": model_resource.get("model_id"),
                "revision": model_resource.get("source_revision"),
                "license": model_resource.get("license"),
                "license_url": model_resource.get("license_url"),
            }
        ],
    }


def _validate_wheelhouse(
    wheelhouse: Path, requirements: list[dict[str, object]]
) -> tuple[Path, ...]:
    wheels = tuple(sorted(wheelhouse.glob("*.whl"), key=lambda path: path.name.casefold()))
    if not wheels:
        raise ClassroomPackageError("Windows Python 3.11 wheelhouse is empty")
    matched: set[tuple[str, str]] = set()
    expected = {
        (str(record["name"]), str(record["version"])): set(record["hashes"])
        for record in requirements
    }
    for wheel in wheels:
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except Exception as exc:
            raise ClassroomPackageError(f"invalid wheel filename: {wheel.name}") from exc
        key = (canonicalize_name(name), str(version))
        if key not in expected:
            raise ClassroomPackageError(f"wheel is not declared by requirements.lock: {wheel.name}")
        digest = _hash_path(wheel)
        if digest not in expected[key]:
            raise ClassroomPackageError(f"wheel hash is not locked: {wheel.name}")
        matched.add(key)
    missing = sorted(set(expected) - matched)
    if missing:
        raise ClassroomPackageError(
            "wheelhouse does not cover locked dependencies: "
            + ", ".join(f"{name}=={version}" for name, version in missing)
        )
    return wheels


def _validate_model(model_root: Path) -> tuple[dict[str, object], tuple[Path, ...]]:
    manifest_path = model_root / "model-resource.json"
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassroomPackageError("RAG model resource manifest is invalid") from exc
    records = manifest.get("files")
    if manifest.get("schema_version") != "rag-model-resource/v1" or not isinstance(records, list):
        raise ClassroomPackageError("RAG model resource manifest is unsupported")
    files = [manifest_path]
    expected_names = {"model-resource.json"}
    for record in records:
        if not isinstance(record, dict):
            raise ClassroomPackageError("RAG model file record is invalid")
        name = record.get("path")
        if not isinstance(name, str) or "/" in name or "\\" in name:
            raise ClassroomPackageError("RAG model file path is invalid")
        path = model_root / name
        if not path.is_file():
            raise ClassroomPackageError(f"RAG model file is missing: {name}")
        if path.stat().st_size != record.get("bytes") or _hash_path(path) != record.get("sha256"):
            raise ClassroomPackageError(f"RAG model file checksum mismatch: {name}")
        files.append(path)
        expected_names.add(name)
    extras = {path.name for path in model_root.iterdir() if path.is_file()} - expected_names
    if extras:
        raise ClassroomPackageError("RAG model directory has unregistered files")
    return manifest, tuple(files)


def _add_file(files: dict[str, PackageFile], item: PackageFile) -> None:
    key = unicodedata.normalize("NFKC", item.path.as_posix()).casefold()
    if key in files:
        raise ClassroomPackageError(f"package path collision: {item.path}")
    files[key] = item


def collect_package_files(
    source_root: Path,
    *,
    version: str,
    commit: str,
    created_at: str,
) -> tuple[tuple[PackageFile, ...], dict[str, object]]:
    entries = _git_entries(source_root, commit)
    files: dict[str, PackageFile] = {}
    found_sources: set[PurePosixPath] = set()
    for source_path, mode in entries:
        if not _is_source_file(source_path):
            continue
        found_sources.add(source_path)
        destination = (
            INSTRUCTION_DESTINATION
            if source_path == INSTRUCTION_SOURCE
            else source_path
        )
        raw = _read_git_file(
            source_root, source_path, commit=commit, mode=mode
        )
        _add_file(files, _bytes_file(destination, raw))
    missing_sources = (EXACT_SOURCE_FILES | {INSTRUCTION_SOURCE}) - found_sources
    if missing_sources:
        raise ClassroomPackageError(
            "classroom package sources are not tracked: "
            + ", ".join(sorted(path.as_posix() for path in missing_sources))
        )

    _add_file(files, _bytes_file(ROOT_START, _root_command("classroom.cmd")))
    _add_file(files, _bytes_file(ROOT_STOP, _root_command("stop-classroom.cmd")))

    web_dist = source_root / "apps/web/dist"
    if not (web_dist / "index.html").is_file() or not (web_dist / "assets").is_dir():
        raise ClassroomPackageError("prebuilt frontend is incomplete")
    for source in sorted(web_dist.rglob("*"), key=lambda path: path.as_posix().casefold()):
        if source.is_file():
            destination = WEB_DIST_DESTINATION / PurePosixPath(
                source.relative_to(web_dist).as_posix()
            )
            _add_file(files, _path_file(destination, source))

    model_root = source_root.joinpath(*MODEL_DESTINATION.parts)
    model_resource, model_files = _validate_model(model_root)
    for source in model_files:
        _add_file(files, _path_file(MODEL_DESTINATION / source.name, source))

    requirements = _requirement_records(source_root / "apps/api/requirements.lock")
    wheelhouse = source_root.joinpath(*WHEELHOUSE_DESTINATION.parts)
    for source in _validate_wheelhouse(wheelhouse, requirements):
        _add_file(files, _path_file(WHEELHOUSE_DESTINATION / source.name, source))

    licenses = _license_manifest(
        source_root,
        version=version,
        created_at=created_at,
        model_resource=model_resource,
    )
    license_raw = (json.dumps(licenses, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _add_file(files, _bytes_file(LICENSE_DESTINATION, license_raw))

    ordered = tuple(sorted(files.values(), key=lambda item: item.path.as_posix().casefold()))
    if len(ordered) > MAX_PACKAGE_FILES:
        raise ClassroomPackageError("classroom package has too many files")
    if sum(item.size_bytes for item in ordered) > MAX_PACKAGE_BYTES:
        raise ClassroomPackageError("classroom package payload is too large")
    missing = REQUIRED_PACKAGE_FILES - {item.path for item in ordered}
    if missing:
        raise ClassroomPackageError(
            "classroom package is missing required files: "
            + ", ".join(sorted(path.as_posix() for path in missing))
        )
    if not any(_is_under(item.path, WHEELHOUSE_DESTINATION) for item in ordered):
        raise ClassroomPackageError("classroom package wheelhouse is missing")
    return ordered, licenses


def _zip_info(path: str) -> ZipInfo:
    info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.flag_bits |= 0x800
    return info


def _manifest(
    *, version: str, commit: str, created_at: str, files: tuple[PackageFile, ...]
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "package_kind": PACKAGE_KIND,
        "app_version": version,
        "source_commit": commit,
        "created_at": created_at,
        "credential_policy": CREDENTIAL_POLICY,
        "network_policy": NETWORK_POLICY,
        "offline_policy": OFFLINE_POLICY,
        "payload_file_count": len(files),
        "payload_size_bytes": sum(item.size_bytes for item in files),
        "files": [
            {
                "path": item.path.as_posix(),
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in files
        ],
    }


def build_classroom_release(
    *, source_root: Path, output_dir: Path, version: str, commit: str
) -> ClassroomPackageBuild:
    source_root = source_root.resolve()
    if not VERSION_PATTERN.fullmatch(version):
        raise ClassroomPackageError("version must use MAJOR.MINOR.PATCH")
    if commit != "working-tree" and not COMMIT_PATTERN.fullmatch(commit):
        raise ClassroomPackageError("source commit must be a full SHA-1 or working-tree")
    try:
        version_source = _version_bytes(source_root, commit).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ClassroomPackageError("services/version.py is not UTF-8") from exc
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"\s*$', version_source, re.MULTILINE)
    if not match or match.group(1) != version:
        raise ClassroomPackageError(f"services/version.py does not declare APP_VERSION {version}")

    created_at = _created_at(source_root, commit)
    files, licenses = collect_package_files(
        source_root, version=version, commit=commit, created_at=created_at
    )
    manifest = _manifest(
        version=version, commit=commit, created_at=created_at, files=files
    )
    manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _scan_package_secret(PurePosixPath(MANIFEST_NAME), manifest_raw)
    if len(manifest_raw) > MAX_MANIFEST_BYTES:
        raise ClassroomPackageError("classroom package manifest is too large")

    package_root = f"Chronovita-Classroom-v{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{package_root}-windows.zip"
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    license_path = output_dir / f"{package_root}-licenses.json"
    for path in (archive_path, checksum_path, license_path):
        path.unlink(missing_ok=True)
    with ZipFile(archive_path, mode="w", compression=ZIP_STORED, allowZip64=True) as bundle:
        for item in files:
            with bundle.open(_zip_info(f"{package_root}/{item.path.as_posix()}"), "w") as destination:
                item.write_to(destination)
        bundle.writestr(
            _zip_info(f"{package_root}/{MANIFEST_NAME}"),
            manifest_raw,
            compress_type=ZIP_STORED,
        )
    archive_sha256 = _hash_path(archive_path)
    checksum_path.write_text(
        f"{archive_sha256}  {archive_path.name}\n", encoding="ascii", newline="\n"
    )
    license_path.write_text(
        json.dumps(licenses, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    verify_classroom_release(archive_path)
    return ClassroomPackageBuild(
        archive_path, checksum_path, license_path, archive_sha256, manifest
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ClassroomPackageError(f"manifest contains duplicate key: {key}")
        result[key] = value
    return result


def _member_hash(bundle: ZipFile, name: str, expected_size: int) -> str:
    digest = hashlib.sha256()
    size = 0
    with bundle.open(name) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_SINGLE_FILE_BYTES:
                raise ClassroomPackageError(f"package file is too large: {name}")
            digest.update(chunk)
    if size != expected_size:
        raise ClassroomPackageError(f"package size mismatch: {name}")
    return digest.hexdigest()


def verify_classroom_release(archive_path: Path) -> dict[str, object]:
    if not archive_path.is_file():
        raise ClassroomPackageError(f"archive does not exist: {archive_path}")
    with ZipFile(archive_path, mode="r") as bundle:
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        if not infos or len(names) != len(set(names)) or any(info.is_dir() for info in infos):
            raise ClassroomPackageError("classroom package archive entries are invalid")
        if len(infos) > MAX_PACKAGE_FILES + 1:
            raise ClassroomPackageError("classroom package has too many archive entries")
        normalized: set[str] = set()
        declared_size = 0
        for info in infos:
            try:
                _validate_path_text(info.filename)
            except RuntimeError as exc:
                raise ClassroomPackageError(f"unsafe archive path: {info.filename}") from exc
            key = unicodedata.normalize("NFKC", info.filename).casefold()
            if key in normalized:
                raise ClassroomPackageError(f"archive path collision: {info.filename}")
            normalized.add(key)
            if info.flag_bits & 0x1 or info.compress_type != ZIP_STORED:
                raise ClassroomPackageError(f"non-canonical archive member: {info.filename}")
            if info.file_size > MAX_SINGLE_FILE_BYTES:
                raise ClassroomPackageError(f"package file is too large: {info.filename}")
            declared_size += info.file_size
        if declared_size > MAX_PACKAGE_BYTES + MAX_MANIFEST_BYTES:
            raise ClassroomPackageError("classroom package declared size is too large")

        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise ClassroomPackageError("classroom package must have one root directory")
        root = next(iter(roots))
        root_match = PACKAGE_ROOT_PATTERN.fullmatch(root)
        if not root_match:
            raise ClassroomPackageError("classroom package root directory is invalid")
        manifest_name = f"{root}/{MANIFEST_NAME}"
        if manifest_name not in names:
            raise ClassroomPackageError("classroom package manifest is missing")
        manifest_info = bundle.getinfo(manifest_name)
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise ClassroomPackageError("classroom package manifest is too large")
        try:
            manifest = json.loads(
                bundle.read(manifest_name).decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClassroomPackageError("classroom package manifest is invalid") from exc
        expected_keys = {
            "schema_version", "package_kind", "app_version", "source_commit",
            "created_at", "credential_policy", "network_policy", "offline_policy",
            "payload_file_count", "payload_size_bytes", "files",
        }
        if not isinstance(manifest, dict) or set(manifest) != expected_keys:
            raise ClassroomPackageError("classroom package manifest fields are invalid")
        if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("package_kind") != PACKAGE_KIND:
            raise ClassroomPackageError("classroom package contract is unsupported")
        if manifest.get("app_version") != root_match.group("version"):
            raise ClassroomPackageError("classroom package version mismatch")
        source_commit = manifest.get("source_commit")
        if source_commit != "working-tree" and (
            not isinstance(source_commit, str) or not COMMIT_PATTERN.fullmatch(source_commit)
        ):
            raise ClassroomPackageError("classroom package source commit is invalid")
        if manifest.get("credential_policy") != CREDENTIAL_POLICY:
            raise ClassroomPackageError("classroom credential policy is invalid")
        if manifest.get("network_policy") != NETWORK_POLICY:
            raise ClassroomPackageError("classroom network policy is invalid")
        if manifest.get("offline_policy") != OFFLINE_POLICY:
            raise ClassroomPackageError("classroom offline policy is invalid")
        try:
            parsed_time = datetime.fromisoformat(str(manifest.get("created_at")).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ClassroomPackageError("classroom package creation time is invalid") from exc
        if parsed_time.utcoffset() != timezone.utc.utcoffset(parsed_time):
            raise ClassroomPackageError("classroom package creation time must be UTC")

        records = manifest.get("files")
        if not isinstance(records, list):
            raise ClassroomPackageError("classroom package file records are invalid")
        expected_names = {manifest_name}
        relative_paths: list[PurePosixPath] = []
        total_size = 0
        for record in records:
            if not isinstance(record, dict) or set(record) != {"path", "size_bytes", "sha256"}:
                raise ClassroomPackageError("classroom package file record is invalid")
            path_value = record.get("path")
            size_value = record.get("size_bytes")
            digest_value = record.get("sha256")
            if (
                not isinstance(path_value, str)
                or not isinstance(size_value, int)
                or isinstance(size_value, bool)
                or size_value < 0
                or not isinstance(digest_value, str)
                or not SHA256_PATTERN.fullmatch(digest_value)
            ):
                raise ClassroomPackageError("classroom package file values are invalid")
            try:
                relative = _validate_path_text(path_value)
                _validate_relative_path(relative)
            except RuntimeError as exc:
                raise ClassroomPackageError(f"unsafe payload path: {path_value}") from exc
            relative_paths.append(relative)
            name = f"{root}/{relative.as_posix()}"
            expected_names.add(name)
            if name not in names:
                raise ClassroomPackageError(f"classroom package file is missing: {relative}")
            if _member_hash(bundle, name, size_value) != digest_value:
                raise ClassroomPackageError(f"classroom package checksum mismatch: {relative}")
            if relative.suffix.casefold() in TEXT_SUFFIXES:
                _scan_package_secret(relative, bundle.read(name))
            total_size += size_value
        if relative_paths != sorted(relative_paths, key=lambda path: path.as_posix().casefold()):
            raise ClassroomPackageError("classroom package file records are not ordered")
        if len(relative_paths) != len(set(relative_paths)):
            raise ClassroomPackageError("classroom package contains duplicate payload paths")
        if set(names) != expected_names:
            raise ClassroomPackageError("classroom package contains unregistered files")
        missing = REQUIRED_PACKAGE_FILES - set(relative_paths)
        if missing:
            raise ClassroomPackageError(
                "classroom package is missing required files: "
                + ", ".join(sorted(path.as_posix() for path in missing))
            )
        top_cmds = {
            path for path in relative_paths if len(path.parts) == 1 and path.suffix.casefold() == ".cmd"
        }
        if top_cmds != ROOT_COMMAND_FILES:
            raise ClassroomPackageError("classroom package root commands are invalid")
        if manifest.get("payload_file_count") != len(records) or manifest.get("payload_size_bytes") != total_size:
            raise ClassroomPackageError("classroom package payload declaration is invalid")
        license_name = f"{root}/{LICENSE_DESTINATION.as_posix()}"
        try:
            licenses = json.loads(bundle.read(license_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClassroomPackageError("classroom license inventory is invalid") from exc
        if licenses.get("schema_version") != LICENSE_SCHEMA_VERSION or licenses.get("app_version") != manifest.get("app_version"):
            raise ClassroomPackageError("classroom license inventory does not match package")
        if not any(_is_under(path, WHEELHOUSE_DESTINATION) for path in relative_paths):
            raise ClassroomPackageError("classroom package wheelhouse is missing")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify the credential-free Chronovita Windows classroom package."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--commit", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_classroom_release(
                source_root=args.source_root,
                output_dir=args.output_dir,
                version=args.version,
                commit=args.commit,
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "archive": str(result.archive_path),
                        "sha256": result.archive_sha256,
                        "checksum": str(result.checksum_path),
                        "licenses": str(result.license_path),
                    },
                    ensure_ascii=True,
                )
            )
        else:
            manifest = verify_classroom_release(args.archive)
            print(json.dumps({"ok": True, "manifest": manifest}, ensure_ascii=True))
    except ClassroomPackageError as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
