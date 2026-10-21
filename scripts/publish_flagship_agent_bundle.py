"""Stage and atomically publish the L101/L103 evidence + persona bundle.

The authoring modules remain the source of artifact identity, version and
lineage.  This script never edits them or silently invents a version bump: a
changed EvidenceCorpusV2 must explicitly supersede the active checksum and its
PersonaPackV1 must bind that exact newly signed corpus.
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
from services.content.flagships.dayu_l101_persona_v1 import (
    build_dayu_persona_pack_v1,
)
from services.content.flagships.shangyang_l103_evidence_v2 import (
    build_shangyang_evidence_v2,
)
from services.content.flagships.shangyang_l103_persona_v1 import (
    build_shangyang_persona_pack_v1,
)
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.contracts.persona_v1 import PersonaPackV1
from services.contracts.release_v2 import CourseReleaseManifestV5


COURSE_ID = "C-prequin-state"
LESSON_IDS = ("L101", "L103")
PUBLISHER = "content-publisher-admin"


def _selection(
    corpus: EvidenceCorpusV2,
    pack: PersonaPackV1,
) -> workflow.EvidencePersonaBundleReleaseSelection:
    return workflow.EvidencePersonaBundleReleaseSelection(
        lesson_id=corpus.lesson_id,
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        corpus_checksum=corpus.checksum,
        evidence_schema_version="evidence-corpus/v2",
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        pack_checksum=pack.checksum,
    )


def publish_flagship_agent_bundle(
    content_root: Path,
    *,
    actor: str = PUBLISHER,
) -> dict[str, object]:
    content.configure(content_root)
    current = workflow.get_current_release(COURSE_ID)
    if not isinstance(current, CourseReleaseManifestV5):
        raise RuntimeError(
            "The flagship joint publication requires an active course-release/v5."
        )
    if tuple(item.lesson_id for item in current.items) != LESSON_IDS:
        raise RuntimeError(
            "The flagship joint publication requires the exact active lesson "
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
    packs = tuple(
        sorted(
            (
                build_dayu_persona_pack_v1(sealed_by=actor),
                build_shangyang_persona_pack_v1(sealed_by=actor),
            ),
            key=lambda pack: pack.lesson_id,
        )
    )
    if tuple(corpus.lesson_id for corpus in corpora) != LESSON_IDS or tuple(
        pack.lesson_id for pack in packs
    ) != LESSON_IDS:
        raise RuntimeError("Flagship authoring did not produce the exact lesson set.")

    active_by_lesson = {item.lesson_id: item for item in current.items}
    pack_by_lesson = {pack.lesson_id: pack for pack in packs}
    for corpus in corpora:
        active_item = active_by_lesson[corpus.lesson_id]
        if (
            corpus.checksum != active_item.evidence_corpus.checksum
            and corpus.supersedes_checksum != active_item.evidence_corpus.checksum
        ):
            raise RuntimeError(
                f"{corpus.lesson_id} authoring evidence does not supersede the "
                "exact active evidence checksum."
            )
        pack = pack_by_lesson[corpus.lesson_id]
        if (
            pack.evidence_corpus_id,
            pack.evidence_version,
            pack.evidence_checksum,
        ) != (corpus.corpus_id, corpus.corpus_version, corpus.checksum):
            raise RuntimeError(
                f"{corpus.lesson_id} authoring persona does not bind the exact "
                "candidate evidence corpus."
            )

    for corpus in corpora:
        runtime_artifacts.stage_evidence_corpus(corpus)
    for pack in packs:
        runtime_artifacts.stage_persona_pack(pack)

    previous_release_id = current.release_id
    release = workflow.publish_evidence_persona_bundle_v1(
        COURSE_ID,
        tuple(
            _selection(corpus, pack_by_lesson[corpus.lesson_id])
            for corpus in corpora
        ),
        actor=actor,
        note=(
            "双旗舰课 EvidenceCorpusV2 与 PersonaPackV1 已按精确证据血缘、"
            "人物知识边界和场景路线完成联合审校并原子重签发布。"
        ),
    )

    artifacts: list[dict[str, object]] = []
    for corpus in corpora:
        lesson_id = corpus.lesson_id
        pack = pack_by_lesson[lesson_id]
        resources = workflow.get_published_lesson_resources(COURSE_ID, lesson_id)
        if resources.evidence_corpus != corpus or resources.persona_pack != pack:
            raise RuntimeError(
                f"Post-publication artifacts do not match for {lesson_id}."
            )
        artifacts.append(
            {
                "lesson_id": lesson_id,
                "evidence": {
                    "corpus_id": corpus.corpus_id,
                    "version": corpus.corpus_version,
                    "checksum": corpus.checksum,
                    "supersedes_checksum": corpus.supersedes_checksum,
                },
                "persona": {
                    "pack_id": pack.pack_id,
                    "version": pack.pack_version,
                    "checksum": pack.checksum,
                    "evidence_checksum": pack.evidence_checksum,
                },
            }
        )
    return {
        "schema_version": "flagship-agent-bundle-publication/v1",
        "status": (
            "already-published"
            if release.release_id == previous_release_id
            else "published"
        ),
        "course_id": COURSE_ID,
        "release": {
            "schema_version": release.schema_version,
            "release_id": release.release_id,
            "release_no": release.release_no,
            "checksum": release.checksum,
        },
        "artifacts": artifacts,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Atomically publish the two flagship EvidenceCorpusV2 and "
            "PersonaPackV1 authoring bundles."
        )
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
    result = publish_flagship_agent_bundle(args.content_root, actor=args.actor)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
