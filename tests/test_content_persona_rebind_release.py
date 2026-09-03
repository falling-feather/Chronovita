from __future__ import annotations

import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from services import content
from services.content import runtime_artifacts, workflow
from services.contracts.persona_v1 import PersonaPackV1, sign_persona_pack
from services.contracts.release_v2 import CourseReleaseManifestV5
from services.contracts.v1 import course_package_from_legacy


REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"
COURSE_ID = "C-prequin-state"
LESSON_ID = "L101"


def _copy_runtime_history(target: Path) -> None:
    for name in ("media", "releases", "runtime", "sealed"):
        shutil.copytree(REPOSITORY_CONTENT / name, target / name)


def _seal_text_only_revision() -> content.LessonContentPackage:
    current = workflow.get_current_release(COURSE_ID)
    if not isinstance(current, CourseReleaseManifestV5):
        raise AssertionError("The fixture requires an active V5 release.")
    current_item = next(item for item in current.items if item.lesson_id == LESSON_ID)
    prior = content.get_sealed_package(LESSON_ID, current_item.content_version)
    payload = prior.model_dump(mode="json")
    payload.update(
        title="Text-only classroom revision",
        body=[
            "This paragraph changed while structural learning modules stayed pinned.",
            *payload["body"][1:],
        ],
        status="draft",
        version=0,
        sealed_at=None,
        sealed_by=None,
        checksum=None,
    )
    draft = content.LessonContentPackage.model_validate(payload)
    content.save_draft(draft, saved_by="content-sync-author")
    record = workflow.validate_draft(LESSON_ID, actor="content-sync-author")
    if record.validation is None or not record.validation.valid:
        raise AssertionError("The text-only revision must pass content validation.")
    workflow.submit_for_review(LESSON_ID, actor="content-sync-author")
    workflow.approve_draft(LESSON_ID, actor="content-sync-reviewer")
    return workflow.seal_approved_draft(
        LESSON_ID,
        actor="content-sync-reviewer",
    )[0]


def _rebind_current_persona(
    sealed: content.LessonContentPackage,
) -> PersonaPackV1:
    current = workflow.get_current_release(COURSE_ID)
    if not isinstance(current, CourseReleaseManifestV5):
        raise AssertionError("The fixture requires an active V5 release.")
    item = next(candidate for candidate in current.items if candidate.lesson_id == LESSON_ID)
    scenarios = tuple(
        (
            runtime_artifacts.load_runtime_scenario(descriptor),
            descriptor.artifact_id == item.primary_scenario_id,
        )
        for descriptor in item.scenarios
    )
    bound_course = runtime_artifacts.bind_course_package(
        course_package_from_legacy(sealed),
        scenarios,
    )
    previous = runtime_artifacts.load_release_persona(item.persona_pack)
    now = datetime.now(timezone.utc)
    payload = previous.model_dump(mode="json")
    payload.update(
        pack_version=previous.pack_version + 1,
        course_content_version=sealed.version,
        course_checksum=bound_course.checksum,
        created_at=now,
        sealed_at=now,
        sealed_by="content-sync-reviewer",
        checksum="0" * 64,
    )
    return sign_persona_pack(PersonaPackV1.model_validate(payload))


class ContentPersonaRebindReleaseTests(unittest.TestCase):
    def test_text_update_and_rebound_persona_publish_in_one_v5_release(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_runtime_history(root)
            content.configure(root)
            try:
                previous = workflow.get_current_release(COURSE_ID)
                self.assertIsInstance(previous, CourseReleaseManifestV5)
                sealed = _seal_text_only_revision()
                rebound = _rebind_current_persona(sealed)
                staged = runtime_artifacts.stage_persona_pack(rebound)

                published, record = workflow.publish_version(
                    LESSON_ID,
                    sealed.version,
                    actor="content-sync-publisher",
                    note="Publish a text-only revision with an exact persona rebind.",
                    persona_selection=workflow.PersonaBundleReleaseSelection(
                        lesson_id=LESSON_ID,
                        pack_id=rebound.pack_id,
                        pack_version=rebound.pack_version,
                        pack_checksum=rebound.checksum,
                    ),
                )

                self.assertIsInstance(published, CourseReleaseManifestV5)
                assert previous is not None
                self.assertEqual(published.release_no, previous.release_no + 1)
                self.assertEqual(record.published_release_id, published.release_id)
                resources = workflow.get_published_lesson_resources(
                    COURSE_ID,
                    LESSON_ID,
                )
                self.assertEqual(resources.course_package.title, "Text-only classroom revision")
                self.assertEqual(resources.persona_pack, rebound)
                item = next(
                    candidate
                    for candidate in published.items
                    if candidate.lesson_id == LESSON_ID
                )
                self.assertEqual(item.persona_pack, staged.descriptor)
            finally:
                content.configure()

    def test_persona_selection_for_another_lesson_never_moves_pointer(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_runtime_history(root)
            content.configure(root)
            try:
                previous = workflow.get_current_release(COURSE_ID)
                sealed = _seal_text_only_revision()
                rebound = _rebind_current_persona(sealed)
                runtime_artifacts.stage_persona_pack(rebound)

                with self.assertRaisesRegex(
                    workflow.ContentValidationFailed,
                    "another lesson",
                ):
                    workflow.publish_version(
                        LESSON_ID,
                        sealed.version,
                        actor="content-sync-publisher",
                        persona_selection=workflow.PersonaBundleReleaseSelection(
                            lesson_id="L103",
                            pack_id=rebound.pack_id,
                            pack_version=rebound.pack_version,
                            pack_checksum=rebound.checksum,
                        ),
                    )
                self.assertEqual(workflow.get_current_release(COURSE_ID), previous)
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
