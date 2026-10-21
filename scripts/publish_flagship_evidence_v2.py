"""Stage and atomically publish the L101/L103 EvidenceCorpusV2 bundle.

The active pointer moves once, only after both immutable corpora pass their
contract, lineage and course-binding checks.  Re-running an already completed
publication is idempotent and does not create a new release.
"""

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
from services.content.flagships.dayu_l101_evidence_v2 import (
    build_dayu_evidence_v2,
)
from services.content.flagships.shangyang_l103_evidence_v2 import (
    build_shangyang_evidence_v2,
)
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.contracts.release_v2 import (
    CourseReleaseManifestV4,
    CourseReleaseManifestV5,
)


COURSE_ID = "C-prequin-state"
LESSON_IDS = ("L101", "L103")
PUBLISHER = "content-publisher-admin"


def _selection(
    corpus: EvidenceCorpusV2,
) -> workflow.EvidenceBundleReleaseSelection:
    return workflow.EvidenceBundleReleaseSelection(
        lesson_id=corpus.lesson_id,
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        corpus_checksum=corpus.checksum,
        schema_version="evidence-corpus/v2",
    )


def publish_flagship_evidence_v2(
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
            "The flagship evidence upgrade requires the exact active lesson "
            f"set {LESSON_IDS!r}."
        )

    corpora = tuple(
        sorted(
            (
                build_dayu_evidence_v2(),
                build_shangyang_evidence_v2(),
            ),
            key=lambda corpus: corpus.lesson_id,
        )
    )
    expected = {corpus.lesson_id: corpus.checksum for corpus in corpora}
    active = {
        item.lesson_id: item.evidence_corpus.checksum for item in current.items
    }
    if isinstance(
        current,
        (CourseReleaseManifestV4, CourseReleaseManifestV5),
    ) and active == expected:
        return {
            "status": "already-published",
            "course_id": COURSE_ID,
            "release_id": current.release_id,
            "release_no": current.release_no,
            "release_checksum": current.checksum,
            "evidence": expected,
        }
    if isinstance(current, CourseReleaseManifestV5):
        raise RuntimeError(
            "The active V5 release binds persona packs to exact evidence checksums; "
            "publish replacement evidence and persona packs together."
        )

    for corpus in corpora:
        runtime_artifacts.stage_evidence_corpus(corpus)

    release = workflow.publish_evidence_bundle_v2(
        COURSE_ID,
        tuple(_selection(corpus) for corpus in corpora),
        actor=actor,
        note=(
            "双旗舰课 EvidenceCorpusV2 已完成事实边界、回答槽、人物范围与"
            "原子片段审校，原子切换至 course-release/v4。"
        ),
    )
    resources = {
        lesson_id: workflow.get_published_lesson_resources(
            COURSE_ID,
            lesson_id,
        )
        for lesson_id in LESSON_IDS
    }
    observed = {
        lesson_id: item.evidence_corpus.checksum
        for lesson_id, item in resources.items()
    }
    if observed != expected:
        raise RuntimeError("Post-publication evidence checksums do not match.")
    return {
        "status": "published",
        "course_id": COURSE_ID,
        "release_id": release.release_id,
        "release_no": release.release_no,
        "release_checksum": release.checksum,
        "evidence": expected,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically publish the two flagship EvidenceCorpusV2 files."
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
    result = publish_flagship_evidence_v2(
        args.content_root,
        actor=args.actor,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
