from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services import content
from services.content import runtime_artifacts, workflow
from services.content.flagships.dayu_l101_persona_v1 import (
    build_dayu_persona_pack_v1,
)
from services.content.flagships.shangyang_l103_persona_v1 import (
    build_shangyang_persona_pack_v1,
)
from services.contracts.persona_v1 import PersonaPackV1, sign_persona_pack
from services.contracts.release_v2 import (
    CourseReleaseManifestV4,
    CourseReleaseManifestV5,
)
from tests.release_fixture import activate_v4_release_6

REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"


def _copy_published_content(target: Path) -> None:
    for name in ("media", "releases", "runtime", "sealed", "workflows"):
        shutil.copytree(REPOSITORY_CONTENT / name, target / name)


def _selection(pack: PersonaPackV1) -> workflow.PersonaBundleReleaseSelection:
    return workflow.PersonaBundleReleaseSelection(
        lesson_id=pack.lesson_id,
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        pack_checksum=pack.checksum,
    )


class PersonaBundleReleaseTests(unittest.TestCase):
    def test_two_lesson_persona_bundle_is_activated_in_one_v5_release(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_published_content(root)
            activate_v4_release_6(root)
            content.configure(root)
            try:
                previous = workflow.get_current_release("C-prequin-state")
                self.assertIsInstance(previous, CourseReleaseManifestV4)
                self.assertEqual(previous.release_no, 6)

                dayu = build_dayu_persona_pack_v1(sealed_by="content-publisher-admin")
                shangyang = build_shangyang_persona_pack_v1(
                    sealed_by="content-publisher-admin"
                )
                runtime_artifacts.stage_persona_pack(dayu)
                runtime_artifacts.stage_persona_pack(shangyang)

                published = workflow.publish_persona_bundle_v1(
                    "C-prequin-state",
                    (_selection(dayu), _selection(shangyang)),
                    actor="content-publisher-admin",
                    note="双课人物表达包通过审校并原子发布。",
                )

                self.assertIsInstance(published, CourseReleaseManifestV5)
                self.assertEqual(published.release_no, 7)
                self.assertEqual(published.parent_release_id, previous.release_id)
                self.assertEqual(
                    [item.lesson_id for item in published.items],
                    ["L101", "L103"],
                )
                self.assertEqual(
                    {item.persona_pack.schema_version for item in published.items},
                    {"persona-pack/v1"},
                )
                self.assertEqual(
                    workflow.get_current_release("C-prequin-state"),
                    published,
                )
                self.assertIsInstance(
                    workflow.get_release(
                        "C-prequin-state",
                        previous.release_id,
                    ),
                    CourseReleaseManifestV4,
                )
                for lesson_id, expected in (("L101", dayu), ("L103", shangyang)):
                    resources = workflow.get_published_lesson_resources(
                        "C-prequin-state",
                        lesson_id,
                    )
                    self.assertEqual(resources.persona_pack, expected)
                    self.assertEqual(resources.evidence_corpus.corpus_version, 2)
            finally:
                content.configure()

    def test_partial_or_stale_persona_bundle_never_moves_pointer(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_published_content(root)
            activate_v4_release_6(root)
            content.configure(root)
            try:
                previous = workflow.get_current_release("C-prequin-state")
                dayu = build_dayu_persona_pack_v1()
                shangyang = build_shangyang_persona_pack_v1()
                runtime_artifacts.stage_persona_pack(dayu)
                runtime_artifacts.stage_persona_pack(shangyang)

                with self.assertRaisesRegex(
                    workflow.ContentValidationFailed,
                    "every lesson",
                ):
                    workflow.publish_persona_bundle_v1(
                        "C-prequin-state",
                        (_selection(dayu),),
                        actor="content-publisher-admin",
                    )
                self.assertEqual(
                    workflow.get_current_release("C-prequin-state"),
                    previous,
                )

                payload = dayu.model_dump(mode="json")
                payload.update(
                    pack_id="dayu-persona-stale",
                    evidence_checksum="f" * 64,
                    checksum="0" * 64,
                )
                stale = sign_persona_pack(PersonaPackV1.model_validate(payload))
                runtime_artifacts.stage_persona_pack(stale)
                with self.assertRaisesRegex(
                    workflow.ContentValidationFailed,
                    "exact published",
                ):
                    workflow.publish_persona_bundle_v1(
                        "C-prequin-state",
                        (_selection(stale), _selection(shangyang)),
                        actor="content-publisher-admin",
                    )
                self.assertEqual(
                    workflow.get_current_release("C-prequin-state"),
                    previous,
                )
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
