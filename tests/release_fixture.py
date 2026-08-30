from __future__ import annotations

import shutil
from pathlib import Path

from services import content
from services.content import workflow

COURSE_ID = "C-prequin-state"
V3_RELEASE_ID = "rel-28b5624648-0005"
V4_RELEASE_ID = "rel-28b5624648-0006"


def activate_v3_release_5(root: Path) -> None:
    """Make a copied content root start at the historical V3 release."""

    content.configure(root)
    manifest_dir = root / "releases" / "manifests" / COURSE_ID
    for candidate in manifest_dir.glob("rel-*.json"):
        if int(candidate.stem.rsplit("-", 1)[1]) > 5:
            candidate.unlink()
    manifest = workflow._read_release_manifest(
        root / "releases" / "manifests" / COURSE_ID / f"{V3_RELEASE_ID}.json"
    )
    pointer = workflow.ActiveReleasePointer(
        course_id=COURSE_ID,
        release_id=manifest.release_id,
        release_no=manifest.release_no,
        manifest_path=f"releases/manifests/{COURSE_ID}/{V3_RELEASE_ID}.json",
        manifest_checksum=manifest.checksum,
        generation=4,
        previous_release_id="rel-28b5624648-0004",
        activated_at=workflow._now(),
        activated_by="v3-to-v4-test-fixture",
        checksum="0" * 64,
    )
    pointer = workflow._sign(pointer, workflow.ActiveReleasePointer)
    content._atomic_write_json(
        root / "releases" / "active" / f"{COURSE_ID}.json",
        pointer.model_dump(mode="json"),
        overwrite=True,
    )
    shutil.rmtree(root / "runtime" / "v2", ignore_errors=True)


def activate_v4_release_6(root: Path) -> None:
    """Make a copied content root start immediately before persona publication."""

    content.configure(root)
    manifest_dir = root / "releases" / "manifests" / COURSE_ID
    for candidate in manifest_dir.glob("rel-*.json"):
        if int(candidate.stem.rsplit("-", 1)[1]) > 6:
            candidate.unlink()
    manifest = workflow._read_release_manifest(manifest_dir / f"{V4_RELEASE_ID}.json")
    pointer = workflow.ActiveReleasePointer(
        course_id=COURSE_ID,
        release_id=manifest.release_id,
        release_no=manifest.release_no,
        manifest_path=f"releases/manifests/{COURSE_ID}/{V4_RELEASE_ID}.json",
        manifest_checksum=manifest.checksum,
        generation=5,
        previous_release_id=V3_RELEASE_ID,
        activated_at=workflow._now(),
        activated_by="v4-to-v5-test-fixture",
        checksum="0" * 64,
    )
    pointer = workflow._sign(pointer, workflow.ActiveReleasePointer)
    content._atomic_write_json(
        root / "releases" / "active" / f"{COURSE_ID}.json",
        pointer.model_dump(mode="json"),
        overwrite=True,
    )
    shutil.rmtree(root / "runtime" / "v1" / "personas", ignore_errors=True)
