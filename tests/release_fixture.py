from __future__ import annotations

import shutil
from pathlib import Path

from services import content
from services.content import workflow

COURSE_ID = "C-prequin-state"
V3_RELEASE_ID = "rel-28b5624648-0005"
V4_RELEASE_ID = "rel-28b5624648-0006"
V5_RELEASE_ID = "rel-28b5624648-0008"


def copy_legacy_content(root: Path) -> Path:
    """Isolate published-artifact regression tests from the current teacher catalogue."""
    source = Path(__file__).resolve().parents[1] / "content"
    shutil.copytree(source, root, ignore=shutil.ignore_patterns("textbooks", "shiji"))
    original = content.content_root()
    try:
        activate_historical_release(root, "rel-28b5624648-0010")
    finally:
        content.configure(original)
    return root


def activate_historical_release(root: Path, release_id: str) -> None:
    """Pin legacy contract tests explicitly; never expose that fixture to real students."""
    if root.resolve() == (Path(__file__).resolve().parents[1] / "content").resolve():
        raise ValueError("Historical fixtures must not mutate repository content")
    content.configure(root)
    manifest_dir = root / "releases" / "manifests" / COURSE_ID
    manifest = workflow._read_release_manifest(manifest_dir / f"{release_id}.json")
    def artifact_paths(release) -> set[str]:
        paths = set()
        for item in release.items:
            paths.add(item.source_path)
            legacy = getattr(item, 'package_path', None)
            if legacy:
                paths.add(legacy)
            for name in ('course_package', 'evidence_corpus', 'lesson_presentation', 'persona_pack'):
                descriptor = getattr(item, name, None)
                if descriptor:
                    paths.add(descriptor.path)
            for scenario in getattr(item, 'scenarios', ()):
                paths.add(scenario.path)
        return paths
    retained = set()
    future = set()
    for candidate in manifest_dir.glob("rel-*.json"):
        release = workflow._read_release_manifest(candidate)
        (retained if release.release_no <= manifest.release_no else future).update(artifact_paths(release))
    for relative in future - retained:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Fixture artifact path escaped its isolated root")
        # Sealed sources remain valid authoring history, even when this test
        # deliberately moves the publication pointer backwards. Only remove
        # later derived runtime artifacts that would collide with a new stage.
        if path.is_relative_to((root / 'runtime').resolve()):
            path.unlink(missing_ok=True)
    for candidate in manifest_dir.glob("rel-*.json"):
        if int(candidate.stem.rsplit("-", 1)[1]) > manifest.release_no:
            candidate.unlink()
    pointer = workflow.ActiveReleasePointer(course_id=COURSE_ID, release_id=manifest.release_id,
        release_no=manifest.release_no, manifest_path=f"releases/manifests/{COURSE_ID}/{release_id}.json",
        manifest_checksum=manifest.checksum, generation=manifest.release_no - 1,
        previous_release_id=manifest.parent_release_id, activated_at=workflow._now(),
        activated_by="historical-contract-fixture", checksum="0" * 64)
    content._atomic_write_json(root / "releases" / "active" / f"{COURSE_ID}.json",
        workflow._sign(pointer, workflow.ActiveReleasePointer).model_dump(mode="json"), overwrite=True)
    workflow._synchronize_workflows_without_pointer_change(manifest, actor="historical-contract-fixture",
        note="Historical contract regression; current teacher flow is tested separately.", action="publish")


def install_teacher_text(lesson_id: str, version: int = 1) -> None:
    """Explicitly register reviewed test content as a teacher reading snapshot."""
    from scripts.sync_teacher_course_snapshot import normalized
    source = content.get_sealed_package(lesson_id, version)
    payload = normalized({"sources": [source], "pr": 0, "commit": "0" * 40})
    content._atomic_write_json(
        content.content_root() / "textbooks" / f"{source.course_id}.json", payload)


def activate_v3_release_5(root: Path) -> None:
    """Make a copied content root start at the historical V3 release."""
    activate_historical_release(root, V3_RELEASE_ID)
    shutil.rmtree(root / "runtime" / "v2", ignore_errors=True)


def activate_v4_release_6(root: Path) -> None:
    """Make a copied content root start immediately before persona publication."""
    activate_historical_release(root, V4_RELEASE_ID)
    shutil.rmtree(root / "runtime" / "v1" / "personas", ignore_errors=True)


def activate_v5_release_8(root: Path) -> None:
    """Make a copied content root use the fixed flagship authoring baseline."""
    activate_historical_release(root, V5_RELEASE_ID)
