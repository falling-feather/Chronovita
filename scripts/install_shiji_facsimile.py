from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "content" / "shiji" / "ocr-pages"
INDEX_PATH = ROOT / "content" / "shiji" / "ocr-pages-index.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安装 Chronovita《史记》百衲本真实书影包")
    parser.add_argument("--archive", type=Path, required=True, help="GitHub Release 下载的书影 ZIP")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="书影安装目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    archive = args.archive.expanduser().resolve()
    target = args.target.expanduser().resolve()
    if not archive.is_file():
        print(f"找不到书影包：{archive}", file=sys.stderr)
        return 2
    if not INDEX_PATH.is_file():
        print(f"缺少索引：{INDEX_PATH}", file=sys.stderr)
        return 2

    expected = json.loads(INDEX_PATH.read_text(encoding="utf-8")).get("page_count", 0)
    with ZipFile(archive) as bundle:
        names = [name for name in bundle.namelist() if name.endswith("/page.webp")]
        if len(names) < expected:
            print(f"书影页数不足：包内 {len(names)}，索引需要至少 {expected}", file=sys.stderr)
            return 2
        staging = Path(tempfile.mkdtemp(prefix="chronovita-shiji-", dir=str(target.parent)))
        try:
            for info in bundle.infolist():
                name = info.filename.replace("\\", "/")
                if not name or name.endswith("/") or name.startswith("/") or ".." in Path(name).parts:
                    print(f"书影包包含不安全路径：{name}", file=sys.stderr)
                    return 2
                destination = (staging / name).resolve()
                if not str(destination).startswith(str(staging)):
                    print(f"书影包越界路径：{name}", file=sys.stderr)
                    return 2
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            installed_root = staging / "baina-ia-mirror"
            if not installed_root.is_dir():
                print("书影包缺少 baina-ia-mirror 根目录", file=sys.stderr)
                return 2
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(installed_root), str(target))
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    print(f"已安装 {expected} 页《史记》书影：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
