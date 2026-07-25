from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZIP_STORED, ZipFile, ZipInfo


SCHEMA_VERSION = "chronovita-teacher-package/v1"
PACKAGE_KIND = "windows-teacher-editor"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_PACKAGE_FILES = 512
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 8 * 1024 * 1024
PACKAGE_ROOT_PATTERN = re.compile(
    r"^Chronovita-Teacher-Editor-v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$"
)

EXACT_SOURCE_FILES = {
    PurePosixPath("scripts/teacher-editor.cmd"),
    PurePosixPath("scripts/teacher-editor.ps1"),
    PurePosixPath("scripts/configure-content-history.cmd"),
    PurePosixPath("scripts/configure-content-history.ps1"),
    PurePosixPath("scripts/stop-teacher-editor.cmd"),
    PurePosixPath("scripts/stop-teacher-editor.ps1"),
    PurePosixPath("content/scenarios/catalog.v1.json"),
    PurePosixPath("infra/content-history-target.json"),
}
SOURCE_PREFIXES = (
    PurePosixPath("apps/api"),
    PurePosixPath("apps/web"),
    PurePosixPath("services"),
    PurePosixPath("content/schemas"),
)
INSTRUCTION_SOURCE = PurePosixPath("distribution/teacher/教师使用说明.txt")
INSTRUCTION_DESTINATION = PurePosixPath("教师使用说明.txt")
ROOT_COMMAND_FILES = frozenset(
    {
        PurePosixPath("点我一键启动（部署）.cmd"),
        PurePosixPath("点我一键关闭.cmd"),
    }
)
REQUIRED_PACKAGE_FILES = {
    *ROOT_COMMAND_FILES,
    PurePosixPath("scripts/teacher-editor.cmd"),
    PurePosixPath("scripts/teacher-editor.ps1"),
    PurePosixPath("scripts/configure-content-history.cmd"),
    PurePosixPath("scripts/configure-content-history.ps1"),
    PurePosixPath("scripts/stop-teacher-editor.cmd"),
    PurePosixPath("scripts/stop-teacher-editor.ps1"),
    PurePosixPath("apps/api/main.py"),
    PurePosixPath("apps/api/requirements.txt"),
    PurePosixPath("apps/api/requirements.lock"),
    PurePosixPath("apps/web/package.json"),
    PurePosixPath("apps/web/package-lock.json"),
    PurePosixPath("apps/web/src/pages/admin/ArchivePublicationPanel.tsx"),
    PurePosixPath("content/scenarios/catalog.v1.json"),
    PurePosixPath("infra/content-history-target.json"),
    INSTRUCTION_DESTINATION,
}
MANIFEST_KEYS = {
    "schema_version",
    "package_kind",
    "app_version",
    "source_commit",
    "created_at",
    "credential_policy",
    "payload_file_count",
    "payload_size_bytes",
    "files",
}
FILE_RECORD_KEYS = {"path", "size_bytes", "sha256"}
CREDENTIAL_POLICY = {
    "bundled_credentials": False,
    "local_storage": "windows-dpapi",
    "browser_receives_github_token": False,
}
WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_DEVICE_PATTERN = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)",
    flags=re.IGNORECASE,
)
FORBIDDEN_ANYWHERE_PARTS = {
    ".chronovita-local",
    ".git",
    ".teacher-editor-logs",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "htmlcov",
    "node_modules",
    "storage",
    "tests",
    "uploads",
}
FORBIDDEN_CONTENT_ROOTS = {
    "assets",
    "drafts",
    "examples",
    "packages",
    "releases",
    "runtime",
    "scenario-drafts",
    "sealed",
    "workflows",
}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".env",
    ".key",
    ".log",
    ".pem",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
}
SECRET_PATTERNS = (
    ("github classic token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("github fine-grained token", re.compile(rb"github_pat_[A-Za-z0-9_]{20,}")),
    ("aws access key", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("OpenAI-style API key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live secret", re.compile(rb"\bsk_live_[0-9A-Za-z]{16,}\b")),
    (
        "database credential URL",
        re.compile(
            rb"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)"
            rb"://[^/\s:@]+:[^/\s@]+@",
            re.IGNORECASE,
        ),
    ),
    (
        "assigned secret",
        re.compile(
            rb"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
            rb"\s*[:=]\s*[\"'][A-Za-z0-9_./+=-]{20,}",
            re.IGNORECASE,
        ),
    ),
    (
        "private key",
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)


class TeacherPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageFile:
    path: PurePosixPath
    raw: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.raw)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


@dataclass(frozen=True)
class TeacherPackageBuild:
    archive_path: Path
    checksum_path: Path
    archive_sha256: str
    manifest: dict[str, object]


def _git_output(source_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise TeacherPackageError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _tracked_entries(
    source_root: Path,
    commit: str,
) -> tuple[tuple[PurePosixPath, str | None], ...]:
    arguments = (
        ["git", "ls-files", "-z"]
        if commit == "working-tree"
        else ["git", "ls-tree", "-r", "-z", commit]
    )
    raw = subprocess.run(
        arguments,
        cwd=source_root,
        check=False,
        capture_output=True,
    )
    if raw.returncode != 0:
        raise TeacherPackageError(
            "git tracked-file discovery failed: "
            + raw.stderr.decode("utf-8", errors="replace")
        )
    entries: list[tuple[PurePosixPath, str | None]] = []
    for item in raw.stdout.split(b"\0"):
        if not item:
            continue
        if commit == "working-tree":
            path_raw = item
            mode = None
        else:
            try:
                metadata, path_raw = item.split(b"\t", maxsplit=1)
                mode = metadata.split(b" ", maxsplit=1)[0].decode("ascii")
            except (UnicodeDecodeError, ValueError) as exc:
                raise TeacherPackageError("git tree entry is invalid") from exc
        entries.append((PurePosixPath(path_raw.decode("utf-8")), mode))
    if not entries:
        raise TeacherPackageError("repository has no tracked files")
    return tuple(entries)


def _is_under(path: PurePosixPath, prefix: PurePosixPath) -> bool:
    return path == prefix or prefix in path.parents


def _is_release_source(path: PurePosixPath) -> bool:
    if path in EXACT_SOURCE_FILES or path == INSTRUCTION_SOURCE:
        return True
    if path == PurePosixPath("apps/api/.env.example"):
        return False
    return any(_is_under(path, prefix) for prefix in SOURCE_PREFIXES)


def _destination_path(source_path: PurePosixPath) -> PurePosixPath:
    if source_path == INSTRUCTION_SOURCE:
        return INSTRUCTION_DESTINATION
    return source_path


def _validate_path_text(value: str) -> PurePosixPath:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or "\0" in value
    ):
        raise TeacherPackageError(f"unsafe package path: {value}")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise TeacherPackageError(f"unsafe package path: {value}")
    for raw_part in raw_parts:
        part = unicodedata.normalize("NFKC", raw_part)
        if (
            part.endswith((" ", "."))
            or any(ord(character) < 32 for character in part)
            or any(character in WINDOWS_FORBIDDEN_CHARACTERS for character in part)
            or WINDOWS_DEVICE_PATTERN.match(part)
        ):
            raise TeacherPackageError(f"unsafe Windows package path: {value}")
        if len(part.encode("utf-8")) > 255:
            raise TeacherPackageError(f"package path component is too long: {value}")
    if len(value.encode("utf-8")) > 1024:
        raise TeacherPackageError(f"package path is too long: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts:
        raise TeacherPackageError(f"invalid package path: {value}")
    return path


def _validate_relative_path(path: PurePosixPath) -> None:
    _validate_path_text(path.as_posix())
    if path.is_absolute() or not path.parts:
        raise TeacherPackageError(f"invalid package path: {path}")
    if any(part.casefold() in FORBIDDEN_ANYWHERE_PARTS for part in path.parts):
        raise TeacherPackageError(f"forbidden package path: {path}")
    if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
        raise TeacherPackageError(f"forbidden package file type: {path}")
    if path.name.casefold().startswith(".env"):
        raise TeacherPackageError(f"environment file cannot enter package: {path}")
    if (
        len(path.parts) >= 2
        and path.parts[0].casefold() == "content"
        and path.parts[1].casefold() in FORBIDDEN_CONTENT_ROOTS
    ):
        raise TeacherPackageError(f"mutable content cannot enter package: {path}")


def _scan_secret(path: PurePosixPath, raw: bytes) -> None:
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(raw):
            raise TeacherPackageError(f"{label} detected in package file: {path}")


def _read_source_file(
    source_root: Path,
    source_path: PurePosixPath,
    *,
    commit: str,
    mode: str | None,
) -> bytes:
    if commit == "working-tree":
        absolute = source_root.joinpath(*source_path.parts)
        if absolute.is_symlink():
            raise TeacherPackageError(f"symbolic links are not allowed: {source_path}")
        if not absolute.is_file():
            raise TeacherPackageError(
                f"tracked package source is missing: {source_path}"
            )
        raw = absolute.read_bytes()
    else:
        if mode not in {"100644", "100755"}:
            raise TeacherPackageError(
                f"non-regular Git source is not allowed: {source_path}"
            )
        completed = subprocess.run(
            ["git", "show", f"{commit}:{source_path.as_posix()}"],
            cwd=source_root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise TeacherPackageError(
                f"cannot read package source from commit: {source_path}"
            )
        raw = completed.stdout
    if len(raw) > MAX_SINGLE_FILE_BYTES:
        raise TeacherPackageError(f"package source is too large: {source_path}")
    return raw


def collect_package_files(
    source_root: Path,
    *,
    commit: str = "working-tree",
) -> tuple[PackageFile, ...]:
    tracked_entries = _tracked_entries(source_root, commit)
    tracked = tuple(path for path, _mode in tracked_entries)
    modes = {path: mode for path, mode in tracked_entries}
    root_commands = frozenset(
        path
        for path in tracked
        if len(path.parts) == 1 and path.suffix.casefold() == ".cmd"
    )
    if root_commands != ROOT_COMMAND_FILES:
        missing = ROOT_COMMAND_FILES - root_commands
        unexpected = root_commands - ROOT_COMMAND_FILES
        details = []
        if missing:
            details.append(
                "missing " + ", ".join(sorted(path.name for path in missing))
            )
        if unexpected:
            details.append(
                "unexpected "
                + ", ".join(sorted(path.name for path in unexpected))
            )
        raise TeacherPackageError(
            "tracked teacher-facing root CMD set is invalid: "
            + "; ".join(details)
        )
    source_paths = tuple(
        path
        for path in tracked
        if path in ROOT_COMMAND_FILES or _is_release_source(path)
    )
    if INSTRUCTION_SOURCE not in source_paths:
        raise TeacherPackageError("teacher package instructions are not tracked")

    files: list[PackageFile] = []
    normalized_destinations: dict[str, PurePosixPath] = {}
    for source_path in source_paths:
        destination = _destination_path(source_path)
        _validate_relative_path(destination)
        collision_key = unicodedata.normalize(
            "NFKC", destination.as_posix()
        ).casefold()
        if collision_key in normalized_destinations:
            raise TeacherPackageError(
                "package path collision: "
                f"{normalized_destinations[collision_key]} and {destination}"
            )
        normalized_destinations[collision_key] = destination
        raw = _read_source_file(
            source_root,
            source_path,
            commit=commit,
            mode=modes[source_path],
        )
        if destination.suffix.casefold() == ".cmd" and any(byte > 127 for byte in raw):
            raise TeacherPackageError(f"CMD must remain ASCII-only: {destination}")
        _scan_secret(destination, raw)
        files.append(PackageFile(destination, raw))

    files.sort(key=lambda item: item.path.as_posix().casefold())
    if len(files) > MAX_PACKAGE_FILES:
        raise TeacherPackageError("teacher package has too many files")
    total_size = sum(item.size_bytes for item in files)
    if total_size > MAX_PACKAGE_BYTES:
        raise TeacherPackageError("teacher package payload is too large")

    destinations = {item.path for item in files}
    missing = REQUIRED_PACKAGE_FILES - destinations
    if missing:
        raise TeacherPackageError(
            "teacher package is missing required files: "
            + ", ".join(sorted(path.as_posix() for path in missing))
        )
    return tuple(files)


def _commit_timestamp(source_root: Path, commit: str) -> str:
    if COMMIT_PATTERN.fullmatch(commit):
        raw = _git_output(source_root, "show", "-s", "--format=%cI", commit)
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise TeacherPackageError("git commit timestamp is invalid") from exc
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if commit == "working-tree":
        return datetime(1980, 1, 1, tzinfo=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    raise TeacherPackageError("source commit must be a full SHA-1 or working-tree")


def _manifest(
    *,
    version: str,
    commit: str,
    created_at: str,
    files: tuple[PackageFile, ...],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "package_kind": PACKAGE_KIND,
        "app_version": version,
        "source_commit": commit,
        "created_at": created_at,
        "credential_policy": CREDENTIAL_POLICY,
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


def _zip_info(path: str) -> ZipInfo:
    info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.flag_bits |= 0x800
    return info


def build_teacher_release(
    *,
    source_root: Path,
    output_dir: Path,
    version: str,
    commit: str,
) -> TeacherPackageBuild:
    source_root = source_root.resolve()
    if not VERSION_PATTERN.fullmatch(version):
        raise TeacherPackageError("version must use MAJOR.MINOR.PATCH")
    if commit != "working-tree" and not COMMIT_PATTERN.fullmatch(commit):
        raise TeacherPackageError("source commit must be a full SHA-1 or working-tree")
    if commit == "working-tree":
        version_raw = (source_root / "services" / "version.py").read_bytes()
    else:
        completed = subprocess.run(
            ["git", "show", f"{commit}:services/version.py"],
            cwd=source_root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise TeacherPackageError(
                "services/version.py is missing from the source commit"
            )
        version_raw = completed.stdout
    try:
        version_source = version_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TeacherPackageError("services/version.py is not UTF-8") from exc
    match = re.search(
        r'^APP_VERSION\s*=\s*"([^"]+)"\s*$',
        version_source,
        flags=re.MULTILINE,
    )
    if not match or match.group(1) != version:
        raise TeacherPackageError(
            f"services/version.py does not declare APP_VERSION {version}"
        )

    files = collect_package_files(source_root, commit=commit)
    package_root = f"Chronovita-Teacher-Editor-v{version}"
    manifest = _manifest(
        version=version,
        commit=commit,
        created_at=_commit_timestamp(source_root, commit),
        files=files,
    )
    manifest_raw = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    _scan_secret(PurePosixPath("teacher-package-manifest.json"), manifest_raw)

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{package_root}-windows.zip"
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    archive_path.unlink(missing_ok=True)
    checksum_path.unlink(missing_ok=True)
    with ZipFile(
        archive_path,
        mode="w",
        compression=ZIP_STORED,
    ) as bundle:
        for item in files:
            path = f"{package_root}/{item.path.as_posix()}"
            bundle.writestr(
                _zip_info(path),
                item.raw,
                compress_type=ZIP_STORED,
            )
        manifest_path = f"{package_root}/teacher-package-manifest.json"
        bundle.writestr(
            _zip_info(manifest_path),
            manifest_raw,
            compress_type=ZIP_STORED,
        )

    archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_text(
        f"{archive_sha256}  {archive_path.name}\n",
        encoding="ascii",
        newline="\n",
    )
    verify_teacher_release(archive_path)
    return TeacherPackageBuild(
        archive_path=archive_path,
        checksum_path=checksum_path,
        archive_sha256=archive_sha256,
        manifest=manifest,
    )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise TeacherPackageError(
                f"teacher package manifest contains duplicate key: {key}"
            )
        value[key] = item
    return value


def _validate_manifest_timestamp(value: object) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TeacherPackageError("teacher package creation time is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TeacherPackageError(
            "teacher package creation time is invalid"
        ) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TeacherPackageError("teacher package creation time must be UTC")


def verify_teacher_release(archive_path: Path) -> dict[str, object]:
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise TeacherPackageError(f"archive does not exist: {archive_path}")
    with ZipFile(archive_path, mode="r") as bundle:
        infos = bundle.infolist()
        if not infos:
            raise TeacherPackageError("teacher package is empty")
        archive_names = [info.filename for info in infos]
        if any(info.is_dir() for info in infos):
            raise TeacherPackageError("teacher package must not contain directory entries")
        if len(archive_names) != len(set(archive_names)):
            raise TeacherPackageError("teacher package contains duplicate paths")
        if len(infos) > MAX_PACKAGE_FILES + 1:
            raise TeacherPackageError("teacher package has too many archive entries")
        normalized_archive_names: set[str] = set()
        declared_size = 0
        for info in infos:
            try:
                member_path = _validate_path_text(info.filename)
            except TeacherPackageError as exc:
                raise TeacherPackageError(
                    f"teacher package contains an unsafe archive path: {info.filename}"
                ) from exc
            normalized_name = unicodedata.normalize(
                "NFKC", info.filename
            ).casefold()
            if normalized_name in normalized_archive_names:
                raise TeacherPackageError(
                    f"teacher package archive path collision: {info.filename}"
                )
            normalized_archive_names.add(normalized_name)
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode not in {0, 0o100000}:
                raise TeacherPackageError(
                    f"teacher package contains a non-regular file: {info.filename}"
                )
            if info.flag_bits & 0x1:
                raise TeacherPackageError(
                    f"teacher package contains an encrypted file: {info.filename}"
                )
            if info.compress_type != ZIP_STORED:
                raise TeacherPackageError(
                    f"teacher package uses a non-canonical compression method: {info.filename}"
                )
            if info.file_size > MAX_SINGLE_FILE_BYTES:
                raise TeacherPackageError(
                    f"teacher package file is too large: {info.filename}"
                )
            declared_size += info.file_size
            if declared_size > MAX_PACKAGE_BYTES + MAX_SINGLE_FILE_BYTES:
                raise TeacherPackageError("teacher package declared size is too large")
        roots = {PurePosixPath(name).parts[0] for name in archive_names}
        if len(roots) != 1:
            raise TeacherPackageError("teacher package must have one root directory")
        package_root = next(iter(roots))
        root_match = PACKAGE_ROOT_PATTERN.fullmatch(package_root)
        if not root_match:
            raise TeacherPackageError("teacher package root directory is invalid")
        manifest_name = f"{package_root}/teacher-package-manifest.json"
        if manifest_name not in archive_names:
            raise TeacherPackageError("teacher package manifest is missing")
        try:
            manifest_raw = bundle.read(manifest_name)
            _scan_secret(PurePosixPath("teacher-package-manifest.json"), manifest_raw)
            manifest = json.loads(
                manifest_raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TeacherPackageError("teacher package manifest is invalid") from exc
        if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
            raise TeacherPackageError("teacher package manifest fields are invalid")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise TeacherPackageError("teacher package manifest schema is unsupported")
        if manifest.get("package_kind") != PACKAGE_KIND:
            raise TeacherPackageError("teacher package kind is invalid")
        if manifest.get("app_version") != root_match.group("version"):
            raise TeacherPackageError(
                "teacher package root version does not match its manifest"
            )
        source_commit = manifest.get("source_commit")
        if (
            source_commit != "working-tree"
            and (
                not isinstance(source_commit, str)
                or not COMMIT_PATTERN.fullmatch(source_commit)
            )
        ):
            raise TeacherPackageError("teacher package source commit is invalid")
        _validate_manifest_timestamp(manifest.get("created_at"))
        if manifest.get("credential_policy") != CREDENTIAL_POLICY:
            raise TeacherPackageError(
                "teacher package credential policy is invalid"
            )
        records = manifest.get("files")
        if not isinstance(records, list):
            raise TeacherPackageError("teacher package file records are invalid")
        declared_count = manifest.get("payload_file_count")
        declared_payload_size = manifest.get("payload_size_bytes")
        if (
            not isinstance(declared_count, int)
            or isinstance(declared_count, bool)
            or declared_count < 0
            or not isinstance(declared_payload_size, int)
            or isinstance(declared_payload_size, bool)
            or declared_payload_size < 0
        ):
            raise TeacherPackageError(
                "teacher package payload declaration is invalid"
            )

        expected_names: set[str] = {manifest_name}
        normalized_names: dict[str, str] = {}
        record_paths: list[PurePosixPath] = []
        top_level_cmds: set[PurePosixPath] = set()
        total_size = 0
        for record in records:
            if not isinstance(record, dict) or set(record) != FILE_RECORD_KEYS:
                raise TeacherPackageError("teacher package file record is invalid")
            path_value = record.get("path")
            size_value = record.get("size_bytes")
            checksum_value = record.get("sha256")
            if (
                not isinstance(path_value, str)
                or not isinstance(size_value, int)
                or isinstance(size_value, bool)
                or size_value < 0
                or not isinstance(checksum_value, str)
                or not SHA256_PATTERN.fullmatch(checksum_value)
            ):
                raise TeacherPackageError(
                    "teacher package file record values are invalid"
                )
            relative = _validate_path_text(path_value)
            _validate_relative_path(relative)
            record_paths.append(relative)
            if len(relative.parts) == 1 and relative.suffix.casefold() == ".cmd":
                top_level_cmds.add(relative)
            normalized = unicodedata.normalize(
                "NFKC", relative.as_posix()
            ).casefold()
            if normalized in normalized_names:
                raise TeacherPackageError(
                    f"teacher package path collision: {relative}"
                )
            normalized_names[normalized] = relative.as_posix()
            name = f"{package_root}/{relative.as_posix()}"
            expected_names.add(name)
            if name not in archive_names:
                raise TeacherPackageError(f"teacher package file is missing: {relative}")
            raw = bundle.read(name)
            _scan_secret(relative, raw)
            if len(raw) != size_value:
                raise TeacherPackageError(f"teacher package size mismatch: {relative}")
            if hashlib.sha256(raw).hexdigest() != checksum_value:
                raise TeacherPackageError(f"teacher package checksum mismatch: {relative}")
            total_size += len(raw)

        if record_paths != sorted(
            record_paths,
            key=lambda path: path.as_posix().casefold(),
        ):
            raise TeacherPackageError(
                "teacher package file records are not canonically ordered"
            )
        missing = REQUIRED_PACKAGE_FILES - set(record_paths)
        if missing:
            raise TeacherPackageError(
                "teacher package is missing required files: "
                + ", ".join(sorted(path.as_posix() for path in missing))
            )
        if top_level_cmds != ROOT_COMMAND_FILES:
            raise TeacherPackageError(
                "teacher package must contain the named start and stop root CMD files"
            )
        if set(archive_names) != expected_names:
            extras = sorted(set(archive_names) - expected_names)
            raise TeacherPackageError(
                "teacher package contains unregistered files: " + ", ".join(extras)
            )
        if declared_count != len(records):
            raise TeacherPackageError("teacher package file count mismatch")
        if declared_payload_size != total_size:
            raise TeacherPackageError("teacher package payload size mismatch")
        if len(records) > MAX_PACKAGE_FILES or total_size > MAX_PACKAGE_BYTES:
            raise TeacherPackageError("teacher package exceeds resource limits")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify a credential-free Chronovita teacher package."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--source-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--commit", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "build":
            result = build_teacher_release(
                source_root=arguments.source_root,
                output_dir=arguments.output_dir,
                version=arguments.version,
                commit=arguments.commit,
            )
            payload = {
                "ok": True,
                "archive": str(result.archive_path),
                "checksum_file": str(result.checksum_path),
                "sha256": result.archive_sha256,
                "files": result.manifest["payload_file_count"],
                "bytes": result.manifest["payload_size_bytes"],
            }
        else:
            manifest = verify_teacher_release(arguments.archive)
            payload = {
                "ok": True,
                "archive": str(arguments.archive.resolve()),
                "version": manifest["app_version"],
                "commit": manifest["source_commit"],
                "files": manifest["payload_file_count"],
                "bytes": manifest["payload_size_bytes"],
            }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (OSError, TeacherPackageError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
