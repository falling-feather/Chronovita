"""Stage and atomically publish the L101/L103 PersonaPackV1 bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import content
from services.content import runtime_artifacts, workflow
from services.content.flagships.dayu_l101_persona_v1 import (
    build_dayu_persona_pack_v1,
)
from services.content.flagships.shangyang_l103_persona_v1 import (
    build_shangyang_persona_pack_v1,
)
from services.contracts.persona_v1 import PersonaPackV1
from services.contracts.release_v2 import CourseReleaseManifestV5

COURSE_ID = "C-prequin-state"
LESSON_IDS = ("L101", "L103")
PUBLISHER = "content-publisher-admin"


def _selection(pack: PersonaPackV1) -> workflow.PersonaBundleReleaseSelection:
    return workflow.PersonaBundleReleaseSelection(
        lesson_id=pack.lesson_id,
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        pack_checksum=pack.checksum,
    )


def publish_flagship_personas_v1(
    content_root: Path,
    *,
    actor: str = PUBLISHER,
) -> dict[str, object]:
    content.configure(content_root)
    current = workflow.get_current_release(COURSE_ID)
    if current is None:
        raise RuntimeError(f"{COURSE_ID} has no active release to upgrade.")
    if tuple(item.lesson_id for item in current.items) != LESSON_IDS:
        raise RuntimeError(
            "The flagship persona publication requires the exact active lesson "
            f"set {LESSON_IDS!r}."
        )

    packs = tuple(
        sorted(
            (
                build_dayu_persona_pack_v1(sealed_by=actor),
                build_shangyang_persona_pack_v1(sealed_by=actor),
            ),
            key=lambda pack: pack.lesson_id,
        )
    )
    expected = {pack.lesson_id: pack.checksum for pack in packs}
    if isinstance(current, CourseReleaseManifestV5):
        active = {item.lesson_id: item.persona_pack.checksum for item in current.items}
        if active == expected:
            return {
                "status": "already-published",
                "course_id": COURSE_ID,
                "release_id": current.release_id,
                "release_no": current.release_no,
                "release_checksum": current.checksum,
                "personas": expected,
            }

    for pack in packs:
        runtime_artifacts.stage_persona_pack(pack)

    release = workflow.publish_persona_bundle_v1(
        COURSE_ID,
        tuple(_selection(pack) for pack in packs),
        actor=actor,
        note=(
            "双旗舰课 PersonaPackV1 已完成角色口吻、可说/不可说边界、"
            "证据用途与场景说话路线审校，原子切换至 course-release/v5。"
        ),
    )
    observed = {
        lesson_id: workflow.get_published_lesson_resources(
            COURSE_ID,
            lesson_id,
        ).persona_pack.checksum
        for lesson_id in LESSON_IDS
    }
    if observed != expected:
        raise RuntimeError("Post-publication persona checksums do not match.")
    return {
        "status": "published",
        "course_id": COURSE_ID,
        "release_id": release.release_id,
        "release_no": release.release_no,
        "release_checksum": release.checksum,
        "personas": expected,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically publish the two flagship PersonaPackV1 files."
    )
    parser.add_argument(
        "--content-root",
        type=Path,
        default=PROJECT_ROOT / "content",
        help="Chronovita content root (default: repository content directory).",
    )
    parser.add_argument(
        "--actor",
        default=PUBLISHER,
        help="Audited publisher account written to the release record.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = publish_flagship_personas_v1(
        args.content_root,
        actor=args.actor,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
