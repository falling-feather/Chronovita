"""Build the deterministic read-only dataset consumed by GitHub Pages."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = ROOT / "content"
OUTPUT = ROOT / "apps" / "web" / "public" / "preview" / "preview-data-v1.json"
sys.path.insert(0, str(ROOT))

from services import courses  # noqa: E402


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _published_presentations() -> tuple[dict[str, dict], list[str]]:
    result: dict[str, dict] = {}
    release_identities: list[str] = []
    active_dir = CONTENT_ROOT / "releases" / "active"
    for pointer_path in sorted(active_dir.glob("*.json")):
        pointer = _load_json(pointer_path)
        manifest = _load_json(CONTENT_ROOT / pointer["manifest_path"])
        release_identities.append(
            f'{manifest["course_id"]}#{manifest["release_no"]}:{manifest["checksum"][:12]}'
        )
        for item in manifest.get("items", []):
            descriptor = item.get("lesson_presentation")
            if not descriptor:
                continue
            presentation = _load_json(CONTENT_ROOT / descriptor["path"])
            lesson_id = item["lesson_id"]
            key = f'{item["course_id"]}/{lesson_id}'
            result[key] = {
                "release_id": manifest["release_id"],
                "release_no": manifest["release_no"],
                "release_checksum": manifest["checksum"],
                "presentation": presentation,
                "asset_urls": {
                    "video": f'/preview/media/{lesson_id}/{Path(presentation["video_path"]).name}',
                    "poster": f'/preview/media/{lesson_id}/{Path(presentation["poster_path"]).name}',
                    "transcript": f'/preview/media/{lesson_id}/{Path(presentation["transcript_path"]).name}',
                },
            }
    return result, release_identities


def build() -> dict:
    era_items: list[dict] = []
    seen_eras: set[str] = set()
    for era in courses.list_eras():
        if era.id in seen_eras:
            continue
        seen_eras.add(era.id)
        era_items.append(era.model_dump(mode="json"))

    course_items = [item.model_dump(mode="json") for item in courses.list_courses()]
    course_details: dict[str, dict] = {}
    lessons: dict[str, dict] = {}
    for summary in course_items:
        course = courses.get_course(summary["id"])
        if course is None:
            continue
        course_details[summary["id"]] = course.model_dump(mode="json")
        for lesson_summary in course.lessons:
            lesson = courses.get_lesson(lesson_summary.id)
            if lesson is None or lesson.course_id != summary["id"]:
                continue
            lessons[f'{summary["id"]}/{lesson.id}'] = lesson.model_dump(mode="json")

    presentations, release_identities = _published_presentations()
    return {
        "schema_version": "chronovita-pages-preview/v1",
        "release_identity": " | ".join(release_identities) or "builtin-course-catalogue",
        "eras": era_items,
        "courses": course_items,
        "course_details": course_details,
        "lessons": lessons,
        "presentations": presentations,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(rendered.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
