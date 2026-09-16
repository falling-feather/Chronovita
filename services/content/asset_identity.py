"""Shared stable naming rules for imported assets and reading projections."""
import hashlib
import re
import unicodedata

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
