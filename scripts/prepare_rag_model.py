from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = (
    PROJECT_ROOT / "distribution" / "models" / "BAAI-bge-small-zh-v1.5"
)
MANIFEST_NAME = "model-resource.json"
EXPECTED_REPOSITORY = "Qdrant/bge-small-zh-v1.5"
EXPECTED_REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
EXPECTED_LICENSE_URL = "https://huggingface.co/BAAI/bge-small-zh-v1.5"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ModelResourceError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and verify the pinned offline FastEmbed resource used by Chronovita."
        )
    )
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not use the network; only verify the existing target.",
    )
    args = parser.parse_args()
    target = args.target.resolve()
    manifest_path = target / MANIFEST_NAME
    try:
        manifest = _read_manifest(manifest_path)
        if not args.verify_only:
            _fetch_to_target(target, manifest)
        _verify_target(target, manifest)
        _smoke_test(target, manifest)
    except Exception as exc:
        print(f"RAG model preparation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Verified offline RAG model resource: "
        f"{manifest['model_id']} @ {manifest['source_revision']}"
    )
    return 0


def _read_manifest(path: Path) -> dict:
    if path.is_symlink():
        raise ModelResourceError(f"model manifest cannot be a symlink: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelResourceError(f"cannot read model manifest: {path}") from exc
    required = {
        "schema_version",
        "model_id",
        "source_repository",
        "source_revision",
        "dimension",
        "license",
        "license_url",
        "files",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or payload["schema_version"] != "rag-model-resource/v1"
        or payload["model_id"] != "BAAI/bge-small-zh-v1.5"
        or payload["source_repository"] != EXPECTED_REPOSITORY
        or payload["source_revision"] != EXPECTED_REVISION
        or payload["dimension"] != 512
        or payload["license"] != "MIT"
        or payload["license_url"] != EXPECTED_LICENSE_URL
        or not isinstance(payload["files"], list)
        or not payload["files"]
    ):
        raise ModelResourceError("model manifest identity or shape is invalid")
    paths: list[str] = []
    for item in payload["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise ModelResourceError("model file entry shape is invalid")
        relative = item["path"]
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or Path(relative).as_posix() != relative
            or not isinstance(item["sha256"], str)
            or SHA256_PATTERN.fullmatch(item["sha256"]) is None
            or isinstance(item["bytes"], bool)
            or not isinstance(item["bytes"], int)
            or item["bytes"] <= 0
        ):
            raise ModelResourceError("model file entry value is invalid")
        paths.append(relative)
    if paths != sorted(set(paths)):
        raise ModelResourceError("model file paths must be sorted and unique")
    return payload


def _fetch_to_target(target: Path, manifest: dict) -> None:
    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="chronovita-rag-model-") as cache:
        cache_root = Path(cache).resolve()
        snapshot = Path(
            snapshot_download(
                repo_id=manifest["source_repository"],
                revision=manifest["source_revision"],
                allow_patterns=[item["path"] for item in manifest["files"]],
                cache_dir=cache,
                local_files_only=False,
            )
        )
        for item in manifest["files"]:
            source = snapshot / Path(item["path"])
            try:
                resolved_source = source.resolve(strict=True)
            except OSError as exc:
                raise ModelResourceError(
                    f"downloaded snapshot is missing {item['path']}"
                ) from exc
            if (
                not resolved_source.is_relative_to(cache_root)
                or not resolved_source.is_file()
            ):
                raise ModelResourceError(f"downloaded snapshot is missing {item['path']}")
            if (
                resolved_source.stat().st_size != item["bytes"]
                or _sha256(resolved_source) != item["sha256"]
            ):
                raise ModelResourceError(f"downloaded model file failed checksum: {item['path']}")
            destination = _safe_child(target, item["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".partial")
            shutil.copyfile(resolved_source, temporary)
            temporary.replace(destination)


def _verify_target(target: Path, manifest: dict) -> None:
    for item in manifest["files"]:
        path = _safe_child(target, item["path"])
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != item["bytes"]
            or _sha256(path) != item["sha256"]
        ):
            raise ModelResourceError(f"model target failed checksum: {item['path']}")


def _smoke_test(target: Path, manifest: dict) -> None:
    from fastembed import TextEmbedding

    model = TextEmbedding(
        model_name=manifest["model_id"],
        specific_model_path=str(target),
        local_files_only=True,
    )
    vector = tuple(float(value) for value in next(iter(model.embed(["离线检索自检"]))))
    norm = math.sqrt(sum(value * value for value in vector))
    if (
        len(vector) != manifest["dimension"]
        or not all(math.isfinite(value) for value in vector)
        or not 0.99 <= norm <= 1.01
    ):
        raise ModelResourceError("FastEmbed returned an unexpected vector dimension")


def _safe_child(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    child = root / relative_path
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or not child.resolve(strict=False).is_relative_to(root.resolve())
    ):
        raise ModelResourceError(f"model path escapes target: {relative}")
    return child


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
