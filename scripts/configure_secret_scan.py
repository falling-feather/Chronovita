"""Narrow exceptions for public fixture IDs; all other history remains scanned."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

PORTRAIT_PATTERN = r"""portrait_asset_key["']?\s*[:=]\s*["'](?:L101-settlement-representative|L103-(?:duke-xiao|merit-soldier|county-clerk))["']"""
PORTRAIT_PATHS = (
    r"^services/content/flagships/(dayu_l101|shangyang_l103)_persona_v1\.py$",
    r"^content/runtime/v1/personas/C-prequin-state/L(101|103|105)/[^/]+/v[0-9]+-[a-f0-9]{64}\.json$",
)


def build_config(upstream: str) -> str:
    if len(re.findall(r"^\[allowlist\]$", upstream, flags=re.MULTILINE)) != 1:
        raise ValueError("Pinned upstream allowlist shape changed")
    normalized = re.sub(r"^\[allowlist\]$", "[[allowlists]]", upstream, count=1, flags=re.MULTILINE)
    return normalized + "\n" + rf"""
[[allowlists]]
description = "Deterministic publication operation-key fixtures"
condition = "AND"
targetRules = ["generic-api-key"]
regexTarget = "match"
regexes = ['''operation_key": "[0-9a-f]{{64}}"''']
paths = ['''^content/examples/archive/v1/dayu-git-publication-(intent|record)\.json$''']

[[allowlists]]
description = "Exact public portrait asset identifiers, never authentication keys"
condition = "AND"
targetRules = ["generic-api-key"]
regexTarget = "match"
regexes = ['''{PORTRAIT_PATTERN}''']
paths = ['''{PORTRAIT_PATHS[0]}''', '''{PORTRAIT_PATHS[1]}''']
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(build_config(args.upstream.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
