from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "data" / "shiji" / "ocr-pages"
INDEX_PATH = ROOT / "content" / "shiji" / "ocr-pages-index.json"


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_member(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or ".." in path.parts
            or PureWindowsPath(name).drive):
        raise ValueError(f"书影包包含不安全路径：{name}")
    return path.as_posix()


def install(archive: Path, target: Path, *, index_path: Path = INDEX_PATH, expected_sha256: str | None = None) -> dict:
    archive = archive.expanduser().resolve(strict=True)
    requested_target = target.expanduser().absolute()
    if requested_target.is_symlink():
        raise ValueError("安装目标不能是目录链接")
    target = requested_target.resolve()
    if target in {Path(target.anchor), ROOT, Path.home(), *ROOT.parents}:
        raise ValueError("安装目标必须是专用书影目录，不能是工作区或用户目录")
    if target.exists() and not target.is_dir():
        raise ValueError("安装目标不是目录")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("book_id") != "shiji" or not isinstance(index.get("pages"), list):
        raise ValueError("书影索引格式错误")
    actual_sha = checksum(archive)
    expected = expected_sha256
    if expected is None and archive.name == index.get("facsimile_archive"):
        expected = index.get("facsimile_sha256")
    if expected is not None and actual_sha.lower() != expected.lower():
        raise ValueError("书影发行包 SHA-256 校验失败")
    images = {safe_member(page["relative_image"]): page for page in index["pages"]}
    if len(images) != len(index["pages"]):
        raise ValueError("索引存在重复书影路径")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="chronovita-shiji-install-", dir=target.parent)).resolve()
    committed: list[Path] = []
    try:
        with ZipFile(archive) as bundle:
            members = {safe_member(info.filename): info for info in bundle.infolist() if not info.is_dir()}
            if len(members) != sum(not info.is_dir() for info in bundle.infolist()):
                raise ValueError("书影包存在重复文件名")
            included = {name for name in members if name.endswith("/page.webp")}
            if not included or included - images.keys():
                raise ValueError("书影包存在未登记页或不是史记书影包")
            versions = {name.split("/", 1)[0] for name in included}
            required = {name for name in images if name.split("/", 1)[0] in versions}
            if included != required:
                raise ValueError("书影包缺页；按页身份校验失败")
            reused: set[str] = set()
            for version in versions:
                installed = target / version
                if installed.exists():
                    if installed.is_symlink() or not installed.is_dir():
                        raise ValueError(f"已有版本目录不可用：{version}")
                    for name in required:
                        if not name.startswith(version + "/"):
                            continue
                        path = (target / name).resolve()
                        if not path.is_relative_to(target) or not path.is_file() or checksum(path) != images[name]["image_sha256"]:
                            raise ValueError(f"已有书影不完整或与索引不同，未覆盖；请换专用目录安装：{version}")
                    reused.add(version)
            for name in sorted(required):
                if name.split("/", 1)[0] in reused:
                    continue
                destination = (staging / name).resolve()
                if not destination.is_relative_to(staging):
                    raise ValueError("书影包路径越界")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(members[name]) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if checksum(destination) != images[name]["image_sha256"]:
                    raise ValueError(f"书影单页校验失败：{name}")
            target.mkdir(parents=True, exist_ok=True)
            for version in sorted(versions - reused):
                destination = target / version
                if destination.exists():
                    raise ValueError("安装期间目标变化，拒绝覆盖")
                (staging / version).rename(destination)
                committed.append(destination)
            receipt = {
                "schema_version": "shiji-facsimile-install/v2", "archive_sha256": actual_sha,
                "versions": sorted(versions), "page_count": len(required),
                "index_sha256": checksum(index_path),
            }
            receipt_path = target / f"installation-{actual_sha[:16]}.json"
            if not receipt_path.exists():
                receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return {**receipt, "reused_versions": sorted(reused), "target": str(target)}
    except Exception:
        # Roll back only newly installed version directories; existing data is untouched.
        for destination in reversed(committed):
            destination.rename(staging / destination.name)
        raise
    finally:
        if not staging.is_relative_to(target.parent) or not staging.name.startswith("chronovita-shiji-install-"):
            raise RuntimeError("暂存目录归属错误")
        shutil.rmtree(staging)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验并安装 Chronovita《史记》真实书影包")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--sha256", help="可选的发行包 SHA-256")
    args = parser.parse_args(argv)
    try:
        result = install(args.archive, args.target, expected_sha256=args.sha256)
    except (OSError, ValueError, BadZipFile, KeyError, json.JSONDecodeError) as exc:
        print(f"安装未完成：{exc}")
        return 2
    print(f"已校验安装 {result['page_count']} 页《史记》书影：{result['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
