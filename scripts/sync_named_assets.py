"""Import a bounded course asset batch by name rather than stale exported IDs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services import content  # noqa: E402
from services.content.asset_identity import (  # noqa: E402
    identity, asset_id, person_lessons, split_people,
)


def git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "-C", str(checkout), *args]
    ).decode("utf-8")


def documents(checkout: Path, commit: str, suffixes: tuple[str, ...]):
    paths = git(checkout, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
    return [json.loads(git(checkout, "show", commit + ":" + path))
            for path in paths if path.endswith(suffixes)]


def archive_profiles(paths: list[Path]) -> list[tuple[str, dict, dict]]:
    """Read data only; never extract or execute archive contents."""
    result = []
    for path in paths:
        archive_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        with ZipFile(path) as bundle:
            entries = [entry for entry in bundle.infolist() if not entry.is_dir()]
            if len(entries) > 2000 or sum(e.file_size for e in entries) > 32 * 1024 * 1024:
                raise ValueError(f"Archive exceeds import limits: {path.name}")
            for entry in entries:
                parts = entry.filename.replace("\\", "/").split("/")
                if ".." in parts or entry.filename.startswith(("/", "\\")):
                    raise ValueError(f"Unsafe archive member: {entry.filename}")
                if not entry.filename.endswith(".json"):
                    continue
                raw = bundle.read(entry)
                data = json.loads(raw.decode("utf-8-sig"))
                kind = "person" if "name" in data else "keyword"
                model = content.PersonProfilePackage if kind == "person" else content.KeywordProfilePackage
                profile = model.model_validate(data)
                if profile.status == "sealed" and not content.verify_package_checksum(profile):
                    raise ValueError(f"Invalid source checksum: {entry.filename}")
                result.append((kind, profile.model_dump(mode="json"), {
                    "archive": path.name, "archive_sha256": archive_hash,
                    "member": entry.filename, "member_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_id": profile.asset_id,
                }))
    return result


def merge_archive_profiles(records: list[tuple[str, dict, dict]]) -> list[tuple[str, dict, list[dict]]]:
    groups = {}
    for kind, data, origin in records:
        key = (kind, identity(data["name" if kind == "person" else "word"]))
        groups.setdefault(key, []).append((data, origin))
    merged = []
    lifecycle = {"asset_id", "created_at", "updated_at", "sealed_at", "sealed_by",
                 "checksum", "version", "status"}
    list_fields = {"related_lessons", "related_people", "keywords", "source_refs"}
    for (kind, _), versions in groups.items():
        combined = dict(versions[0][0])
        for data, _ in versions[1:]:
            for field, value in data.items():
                if field in lifecycle:
                    continue
                if field in {"name", "word"} and identity(combined[field]) == identity(value):
                    continue
                if field in list_fields:
                    combined[field] = list(combined.get(field, []))
                    for item in value:
                        if item not in combined[field]:
                            combined[field].append(item)
                elif combined.get(field) != value:
                    raise ValueError(f"Conflicting archive content: {combined.get('name', combined.get('word'))}/{field}")
        merged.append((kind, combined, [origin for _, origin in versions]))
    return merged


def import_archives(paths: list[Path], checkout: Path, *, apply: bool = False) -> dict:
    from services.courses.textbooks import load_textbooks

    books = load_textbooks()
    lesson_ids = {lesson.lesson_id for book in books.values() for lesson in book.lessons}
    names = {}
    for book in books.values():
        for lesson in documents(checkout, book.source_commit, (".json",)):
            if not {"lesson_id", "body", "unit", "version"} <= lesson.keys():
                continue
            if lesson["lesson_id"] not in lesson_ids:
                continue
            for person in lesson["people"]:
                names.setdefault(identity(person["name"]), []).append(lesson["lesson_id"])
    records = archive_profiles(paths)
    existing = content.list_assets()
    prepared = []
    for kind, data, origins in merge_archive_profiles(records):
        name = data["name" if kind == "person" else "word"]
        matches = [item for item in existing if item.kind == kind and identity(item.title) == identity(name)]
        if len(matches) > 1:
            raise ValueError(f"Multiple existing assets: {name}")
        target = matches[0].asset_id if matches else asset_id(kind, name)
        if any(item.asset_id == target and item.kind == kind and identity(item.title) != identity(name)
               for item in existing):
            raise ValueError(f"Asset ID collision: {name}")
        # Real missing lesson IDs are retained; placeholder IDs are not.
        related = [value for value in data["related_lessons"] if re.fullmatch(r"L\d+", value)]
        if kind == "person":
            related = person_lessons(name, names)
        related = sorted(set(related))
        note = data["teacher_notes"] + "\n\n本地附件同步来源：\n" + "\n".join(
            json.dumps(origin, ensure_ascii=False, sort_keys=True) for origin in origins
        )
        if not related or set(related) - lesson_ids:
            note += "\n课时待关联或对应课文缺稿；本次保留素材，不生成旧课文或互动内容。"
        values = dict(data, asset_id=target, related_lessons=related, teacher_notes=note,
                      status="draft", version=0, checksum=None, sealed_at=None, sealed_by=None)
        if kind == "person":
            values["keywords"] = list(dict.fromkeys(
                part.strip() for value in values["keywords"]
                for part in re.split("[；;、\\n]", value) if part.strip()))
        model = content.PersonProfilePackage if kind == "person" else content.KeywordProfilePackage
        profile = model.model_validate(values)
        prepared.append((kind, profile, {
            "kind": kind, "name": name, "asset_id": target, "origins": origins,
            "lessons": related, "missing_lessons": sorted(set(related) - lesson_ids),
            "existed": bool(matches),
        }))
    person_names = list(dict.fromkeys(
        [item.title for item in existing if item.kind == "person"]
        + [profile.name for kind, profile, _ in prepared if kind == "person"]))
    for kind, profile, row in prepared:
        if kind == "keyword":
            profile.related_people = split_people(profile.related_people, person_names)
        getter = content.get_person_profile if kind == "person" else content.get_keyword_profile
        current = getter(profile.asset_id)
        ignored = {"created_at", "updated_at"}
        row["changed"] = current is None or current.model_dump(exclude=ignored) != profile.model_dump(exclude=ignored)
    if apply:
        for kind, profile, row in prepared:
            if row["changed"]:
                saver = content.save_person_profile if kind == "person" else content.save_keyword_profile
                saver(profile)
    return {"source_records": len(records), "unique_assets": len(prepared),
            "assets": [row for _, _, row in prepared]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--repository")
    parser.add_argument("--course-pr", type=int, nargs='+')
    parser.add_argument("--prs", type=int, nargs="+")
    parser.add_argument("--archives", type=Path, nargs="+")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.archives:
        if args.prs or args.course_pr or args.repository:
            parser.error("--archives cannot be combined with PR import arguments")
        print(json.dumps(import_archives(args.archives, args.checkout, apply=args.apply),
                         ensure_ascii=False, indent=2))
        return
    if not (args.repository and args.course_pr and args.prs):
        parser.error("PR import requires --repository, --course-pr and --prs")
    course_docs = [d for number in args.course_pr
                   for d in documents(args.checkout, f'refs/remotes/origin/pr/{number}', ('.json',))
                   if 'lesson_id' in d and 'body' in d and 'unit' in d and 'version' in d]
    lessons = {d['lesson_id'] for d in course_docs}
    names = {}
    for lesson in course_docs:
        for person in lesson['people']:
            names.setdefault(identity(person['name']), []).append(lesson['lesson_id'])
    groups = {}
    for number in sorted(args.prs):
        metadata = json.loads(subprocess.check_output([
            "gh", "pr", "view", str(number), "--repo", args.repository,
            "--json", "headRefOid,statusCheckRollup"
        ]))
        if not metadata['statusCheckRollup'] or any(
            c.get('conclusion') != 'SUCCESS' for c in metadata['statusCheckRollup']
        ):
            raise ValueError(f"PR #{number} checks did not pass")
        docs = documents(args.checkout, metadata['headRefOid'], ('-人物档案.json', '-关键词档案.json'))
        if len(docs) != 1:
            raise ValueError(f"PR #{number}: expected one profile")
        data = docs[0]
        kind = 'person' if data['schema_version'] == 'person-profile/v1' else 'keyword'
        model = content.PersonProfilePackage if kind == 'person' else content.KeywordProfilePackage
        profile = model.model_validate(data)
        if not content.verify_package_checksum(profile):
            raise ValueError(f"PR #{number}: checksum mismatch")
        name = data['name' if kind == 'person' else 'word']
        groups.setdefault((kind, identity(name)), []).append((number, metadata['headRefOid'], data))
    prepared = []
    existing = content.list_assets()
    for (kind, key), versions in groups.items():
        number, commit, data = max(versions, key=lambda v: (v[2]['sealed_at'], v[0]))
        name = data['name' if kind == 'person' else 'word']
        matches = [a for a in existing if a.kind == kind and identity(a.title) == key]
        if len(matches) > 1:
            raise ValueError(f"Multiple existing IDs for {name}; resolve before importing")
        target = matches[0].asset_id if matches else asset_id(kind, name)
        occupied = [a for a in existing if a.kind == kind and a.asset_id == target and identity(a.title) != key]
        if occupied:
            raise ValueError(f"ID collision for {name}")
        related = sorted(set(data['related_lessons']) & lessons)
        if kind == 'person':
            related = sorted(set(related + person_lessons(name, names)))
        original_id = data['asset_id']
        original_checksum = data['checksum']
        local = dict(data, asset_id=target, related_lessons=related,
                     status='draft', version=0, checksum=None, sealed_at=None, sealed_by=None)
        if kind == 'person':
            local['keywords'] = list(dict.fromkeys(
                part.strip() for value in local['keywords']
                for part in re.split('[；;、\\n]', value) if part.strip()))
        local['teacher_notes'] = data['teacher_notes'] + (
            f"\n\n同步来源：{args.repository} PR #{number}；commit {commit}；"
            f"源 ID {original_id}；源 checksum {original_checksum}。"
        )
        if not related:
            local['teacher_notes'] += '\n课时关联待确认：当前已导入课文中没有唯一可核对的对应项；已移除无效占位课号。'
        model = content.PersonProfilePackage if kind == 'person' else content.KeywordProfilePackage
        profile = model.model_validate(local)
        prepared.append((kind, profile, dict(name=name, kind=kind, asset_id=target,
                        source_id=original_id, prs=[v[0] for v in versions],
                        latest_pr=number, lessons=related,
                        association_status='已关联' if related else '待关联')))
    person_names = [profile.name for kind, profile, _ in prepared if kind == 'person']
    for kind, profile, _ in prepared:
        if kind == 'keyword':
            profile.related_people = split_people(profile.related_people, person_names)
    if args.apply:
        for kind, profile, _ in prepared:
            getter = content.get_person_profile if kind == 'person' else content.get_keyword_profile
            saver = content.save_person_profile if kind == 'person' else content.save_keyword_profile
            current = getter(profile.asset_id)
            ignored = {'created_at','updated_at'}
            if current is None or current.model_dump(exclude=ignored) != profile.model_dump(exclude=ignored):
                saver(profile)
    print(json.dumps([row for _, _, row in prepared], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
