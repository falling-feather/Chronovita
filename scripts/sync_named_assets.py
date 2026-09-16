"""Import a bounded course asset batch by name rather than stale exported IDs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services import content  # noqa: E402


def identity(name: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).casefold()


def asset_id(kind: str, name: str) -> str:
    return kind + "-" + hashlib.sha256(identity(name).encode("utf-8")).hexdigest()[:24]


def name_forms(name: str) -> set[str]:
    normalized = identity(name)
    return {normalized, *filter(None, re.split(r'[()]', normalized))}


def person_lessons(name: str, names: dict[str, list[str]]) -> list[str]:
    key = identity(name)
    if key in names:
        return names[key]
    matches = [lessons for other, lessons in names.items()
               if name_forms(name) & name_forms(other)]
    return matches[0] if len(matches) == 1 else []


def split_people(values: list[str], names: list[str]) -> list[str]:
    known = {identity(name): name for name in names}
    pattern = '|'.join(re.escape(key) for key in sorted(known, key=len, reverse=True))
    result = []
    for value in values:
        normalized = identity(value)
        matches = list(re.finditer(pattern, normalized)) if pattern else []
        remainder = re.sub(pattern, '', normalized) if pattern else normalized
        if matches and not remainder.strip('；;、,，/|'):
            result.extend(known[match.group()] for match in matches)
        else:
            result.append(value.strip())
    return list(dict.fromkeys(result))


def git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "-C", str(checkout), *args]
    ).decode("utf-8")


def documents(checkout: Path, commit: str, suffixes: tuple[str, ...]):
    paths = git(checkout, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
    return [json.loads(git(checkout, "show", commit + ":" + path))
            for path in paths if path.endswith(suffixes)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--course-pr", type=int, nargs='+', required=True)
    parser.add_argument("--prs", type=int, nargs="+", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
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
