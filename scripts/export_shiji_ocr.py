"""Export only the supplied Shiji OCR records/images, never the editor database."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "shiji"
VERSIONS = {"baina-ia-mirror", "siku-quanshu-ia-zju"}


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def natural_key(text: str) -> tuple:
    return tuple((0, int(part)) if part.isdigit() else (1, part)
                 for part in re.split(r"(\d+)", text.casefold()))


def export(source: Path, *, image_archive: Path | None = None) -> dict:
    source = source.resolve(strict=True)
    page_root = (source / "data/processed/ocr/pages/shiji").resolve(strict=True)
    database = source / "data/processed/editor/ocr_workspace.sqlite3"
    if not database.is_file() or not CONTENT.is_dir():
        raise ValueError("缺少源 OCR 数据库或当前项目资料目录")
    # The source workspace is read-only; no initialization or migrations run here.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM ocr_pages WHERE book_id = ?", ("shiji",))]
        mappings = {row["page_id"]: dict(row) for row in connection.execute(
            "SELECT m.* FROM ocr_page_mappings m JOIN ocr_pages p ON m.page_id=p.id WHERE p.book_id=?",
            ("shiji",))}
        enrichments = {row["page_id"]: dict(row) for row in connection.execute(
            "SELECT e.* FROM ocr_page_enrichments e JOIN ocr_pages p ON e.page_id=p.id WHERE p.book_id=?",
            ("shiji",))}
    finally:
        connection.close()
    if not rows or {row["version_id"] for row in rows} != VERSIONS:
        raise ValueError("来源必须包含百衲本和四库本《史记》，且不能混入其他史书")
    rows.sort(key=lambda row: (row["version_id"], natural_key(row["source_file_label"]), row["pdf_page"], row["id"]))
    records_path = CONTENT / "shiji-ocr-records.zip"
    records_temp = records_path.with_suffix(".zip.partial")
    image_bundle = None
    if image_archive is not None:
        image_archive = image_archive.resolve()
        image_archive.parent.mkdir(parents=True, exist_ok=True)
        if image_archive.exists():
            raise FileExistsError(f"不覆盖已有书影发行包：{image_archive}")
        image_bundle = ZipFile(image_archive.with_suffix(".zip.partial"), "w", compression=ZIP_STORED)
    pages = []
    counts: dict[str, int] = {}
    try:
        with ZipFile(records_temp, "w", compression=ZIP_DEFLATED, compresslevel=6) as records:
            for row in rows:
                record_path = (source / row["record_path"]).resolve(strict=True)
                image_path = (source / row["image_path"]).resolve(strict=True)
                if not record_path.is_relative_to(page_root) or not image_path.is_relative_to(page_root):
                    raise ValueError(f"源页路径越界：{row['id']}")
                relative_record = record_path.relative_to(page_root).as_posix()
                relative_image = image_path.relative_to(page_root).as_posix()
                if relative_record.split("/", 1)[0] != row["version_id"]:
                    raise ValueError(f"源页版本与路径不一致：{row['id']}")
                payload = json.loads(record_path.read_text(encoding="utf-8"))
                if payload.get("id") != row["id"] or payload.get("book", {}).get("id") != "shiji":
                    raise ValueError(f"源页身份错误：{row['id']}")
                transcription = payload.setdefault("transcription", {})
                transcription.update(raw_text=row["ocr_text"], corrected_text=row["corrected_text"], status=row["review_status"])
                mapping = mappings.get(row["id"]) or {
                    "page_id": row["id"], "status": "unmapped", "canonical_unit_id": "",
                    "volume_no": None, "volume_title": "", "chapter_title": "", "source_leaf_label": "",
                }
                payload["mapping"] = {**mapping, "revisions": []}
                enrichment = enrichments.get(row["id"])
                payload["manual_content"] = {
                    "page_id": row["id"], "summary": enrichment["summary"] if enrichment else "",
                    "keywords": json.loads(enrichment["keywords_json"]) if enrichment else [],
                    "editor": enrichment["editor"] if enrichment else "",
                    "updated_at": enrichment["updated_at"] if enrichment else "", "revisions": [],
                }
                # Keep source attribution, not an absolute dependency on the old project.
                payload.pop("image_path", None)
                data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                records.writestr(relative_record, data)
                image_sha = checksum(image_path)
                if image_bundle is not None:
                    image_bundle.write(image_path, relative_image)
                item = {key: row[key] for key in (
                    "id", "version_id", "version_label", "source_file_label", "source_pdf", "pdf_page",
                    "ocr_status", "review_status", "character_count", "average_confidence",
                )}
                item.update(relative_image=relative_image, relative_record=relative_record,
                            image_sha256=image_sha, record_sha256=hashlib.sha256(data).hexdigest(),
                            mapping_status=mapping["status"], canonical_unit_id=mapping["canonical_unit_id"])
                counts[row["version_id"]] = counts.get(row["version_id"], 0) + 1
                pages.append(item)
        records_temp.replace(records_path)
        index = {"schema_version": "shiji-ocr-index/v2", "book_id": "shiji", "page_count": len(pages),
                 "versions": [{"id": key, "page_count": value} for key, value in counts.items()],
                 "records_archive": records_path.name, "records_sha256": checksum(records_path), "pages": pages}
        if image_bundle is not None:
            image_bundle.writestr("facsimile-manifest.json", json.dumps({
                "schema_version": "shiji-facsimile/v2", "book_id": "shiji", "page_count": len(pages),
                "versions": index["versions"], "files": [{"path": page["relative_image"], "sha256": page["image_sha256"]} for page in pages],
            }, ensure_ascii=False))
            image_bundle.close()
            image_bundle = None
            image_archive.with_suffix(".zip.partial").replace(image_archive)
            index["facsimile_archive"] = image_archive.name
            index["facsimile_sha256"] = checksum(image_archive)
        (CONTENT / "ocr-pages-index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        return {"page_count": len(pages), "versions": counts, "records_sha256": index["records_sha256"],
                "facsimile_sha256": index.get("facsimile_sha256")}
    finally:
        if image_bundle is not None:
            image_bundle.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="只读迁移史海已提供的史记 OCR 内容")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--image-archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.source, image_archive=args.image_archive), ensure_ascii=False))


if __name__ == "__main__":
    main()
