"""Import final teacher PR snapshots as reading text without republishing modules."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import content  # noqa: E402
from services.courses.textbooks import TextbookCourse, TextbookLesson, text_checksum  # noqa: E402


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT).decode("utf-8")


def read_pr(repository: str, checkout: Path, number: int) -> dict:
    pr = json.loads(run("gh", "pr", "view", str(number), "--repo", repository,
                        "--json", "number,headRefOid,files,statusCheckRollup"))
    checks = pr["statusCheckRollup"]
    if not checks or any(c.get("conclusion") != "SUCCESS" for c in checks):
        raise ValueError(f"PR #{number} checks have not passed")
    paths = [item["path"] for item in pr["files"]]
    manifests = [p for p in paths if p.endswith("/课程发布清单.json")]
    if len(manifests) != 1:
        raise ValueError(f"PR #{number}: expected one course archive")
    def read(path: str):
        return json.loads(run("git", "-C", str(checkout), "show",
                              pr["headRefOid"] + ":" + path))
    release = read(manifests[0])
    prefix = manifests[0].rsplit("/", 1)[0] + "/lessons/"
    sources = []
    for path in paths:
        if (path.startswith(prefix) and path.endswith(".json")
                and not path.endswith(("-格式层.json", "-运行包.json"))):
            source = content.LessonContentPackage.model_validate(read(path))
            if not content.verify_package_checksum(source):
                raise ValueError(f"Source checksum mismatch: PR #{number}/{source.lesson_id}")
            if source.course_id != release["course_id"]:
                raise ValueError("Course identity mismatch")
            sources.append(source)
    if {s.lesson_id for s in sources} != {i["lesson_id"] for i in release["items"]}:
        raise ValueError("Snapshot is incomplete")
    return {"pr": number, "commit": pr["headRefOid"], "release": release,
            "sources": sources}


def normalized(snapshot: dict) -> dict:
    sources = sorted(snapshot["sources"], key=lambda s: (
        tuple(int(n) for n in re.findall(r"\d+", s.lesson_no)), s.lesson_id))
    first = sources[0]
    lessons = [TextbookLesson(
        lesson_id=s.lesson_id, lesson_no=s.lesson_no, title=s.title.strip(),
        abstract=s.abstract.strip(), body=[p.replace("\r\n", "\n").strip() for p in s.body if p.strip()],
        duration=s.duration, keywords=s.keywords, people=s.people,
        map_points=s.map_points, source_refs=s.source_refs,
    ).model_dump(mode="json") for s in sources]
    payload = dict(course_id=first.course_id, title=first.course_title,
                   era=first.era, era_id=first.era_id, section=first.section,
                   source_pr=snapshot["pr"], source_commit=snapshot["commit"],
                   source_checksums={s.lesson_id: s.checksum for s in sources},
                   lessons=lessons)
    payload["text_checksum"] = text_checksum(payload)
    return TextbookCourse.model_validate(payload).model_dump(mode="json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--prs", type=int, nargs="+", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    content.configure(ROOT / "content")
    snapshots = [read_pr(args.repository, args.checkout, n) for n in sorted(args.prs)]
    groups = {}
    for snapshot in snapshots:
        groups.setdefault(snapshot["release"]["course_id"], []).append(snapshot)
    results = []
    for course_id, group in groups.items():
        group.sort(key=lambda s: s["release"]["release_no"])
        latest = group[-1]
        final_ids = {s.lesson_id for s in latest["sources"]}
        for older in group[:-1]:
            if not {s.lesson_id for s in older["sources"]} <= final_ids:
                raise ValueError(f"PR #{older['pr']} contains lessons omitted from final snapshot")
        payload = normalized(latest)
        target = content.content_root() / "textbooks" / f"{course_id}.json"
        changed = not target.exists() or json.loads(target.read_text(encoding="utf-8")) != payload
        if args.apply:
            if changed:
                content._atomic_write_json(target, payload)
            for lesson in payload["lessons"]:
                draft = content.get_draft(lesson["lesson_id"])
                if draft is None:
                    draft = content.LessonContentPackage(
                        lesson_id=lesson["lesson_id"], title=lesson["title"],
                        unit=payload["title"], era=payload["era"], course_id=course_id)
                values = draft.model_dump(mode="json")
                values.update(lesson, course_id=course_id, course_title=payload["title"],
                              unit=payload["title"], era=payload["era"], era_id=payload["era_id"],
                              section=payload["section"], status="draft", version=0,
                              sealed_at=None, sealed_by=None, checksum=None)
                updated = content.LessonContentPackage.model_validate(values)
                if content.draft_fingerprint(updated) != content.draft_fingerprint(draft):
                    content.save_draft(updated, saved_by="teacher-text-sync")
        results.append(dict(course_id=course_id, latest_pr=latest["pr"],
                            prs=[s["pr"] for s in group], changed=changed,
                            text_checksum=payload["text_checksum"],
                            lessons=[dict(id=lesson["lesson_id"],title=lesson["title"],paragraphs=len(lesson["body"]))
                                     for lesson in payload["lessons"]]))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
