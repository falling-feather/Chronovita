import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Thread, current_thread, local
from unittest.mock import patch

from services import content
from services.content import runtime_artifacts
from services.content import workflow
from services.contracts.release_v2 import CourseReleaseManifestV2
from services.contracts.v1 import (
    RuntimeBundleV1,
    ScenarioTemplateV1,
    calculate_contract_checksum,
)
from services.game_runtime import MAX_CONTRACT_FILE_BYTES
from services.game_runtime.catalog import ScenarioCatalogRepository


class JointReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-joint-release-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        content.configure(self.tmp_root)
        catalog_path = self.tmp_root / "scenarios" / "catalog.v1.json"
        catalog_path.parent.mkdir(parents=True)
        catalog_path.write_text(
            json.dumps({"schema_version": "scenario-catalog/v1", "entries": []}),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass
        content.configure()

    def test_staged_scenario_is_private_until_joint_release(self):
        sealed = self._seal_lesson("joint-lesson", "C-joint", "Joint body")
        staged = runtime_artifacts.stage_scenario(
            self._scenario("joint-scenario", sealed.course_id, sealed.lesson_id)
        )
        catalog = ScenarioCatalogRepository(
            content_root=self.tmp_root,
            catalog_path="scenarios/catalog.v1.json",
        )

        self.assertIsNone(workflow.get_current_release(sealed.course_id))
        self.assertEqual(workflow.load_published_packages(), [])
        self.assertEqual(catalog.list_active_records(), ())
        release, _ = workflow.publish_version(
            sealed.lesson_id,
            sealed.version,
            actor="publisher",
            scenario_selections=[self._selection(staged)],
        )

        self.assertIsInstance(release, CourseReleaseManifestV2)
        item = release.items[0]
        self.assertEqual(item.primary_scenario_id, "joint-scenario")
        self.assertEqual(item.audience, "published")
        (content.package_dir() / "joint-lesson-v001.json").unlink()
        snapshot = workflow.load_published_snapshots()[0]
        scenario = runtime_artifacts.load_runtime_scenario(item.scenarios[0])
        RuntimeBundleV1(course=snapshot.package, scenario=scenario)
        self.assertEqual(snapshot.package.scenario_refs[0].scenario_id, scenario.scenario_id)
        published = catalog.list_active_records()
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].entry.audience, "published")
        self.assertEqual(published[0].engine.course.checksum, snapshot.package.checksum)

    def test_none_empty_and_explicit_scenario_selection_semantics(self):
        sealed_v1 = self._seal_lesson("binding-lesson", "C-binding", "Version one")
        first = runtime_artifacts.stage_scenario(
            self._scenario("binding-first", sealed_v1.course_id, sealed_v1.lesson_id)
        )
        second = runtime_artifacts.stage_scenario(
            self._scenario("binding-second", sealed_v1.course_id, sealed_v1.lesson_id)
        )
        release_v1, _ = workflow.publish_version(
            sealed_v1.lesson_id,
            1,
            actor="publisher",
            scenario_selections=[self._selection(first)],
        )

        sealed_v2 = self._seal_next_version(sealed_v1.lesson_id, "Version two")
        preserved, _ = workflow.publish_version(
            sealed_v2.lesson_id,
            2,
            actor="publisher",
        )
        self.assertEqual(
            preserved.items[0].scenarios,
            release_v1.items[0].scenarios,
        )

        removed, _ = workflow.publish_version(
            sealed_v2.lesson_id,
            2,
            actor="publisher",
            scenario_selections=[],
        )
        self.assertEqual(removed.items[0].scenarios, ())
        self.assertEqual(workflow.load_published_packages()[0].scenario_refs, [])

        replaced, _ = workflow.publish_version(
            sealed_v2.lesson_id,
            2,
            actor="publisher",
            scenario_selections=[self._selection(second)],
        )
        self.assertEqual(
            [item.artifact_id for item in replaced.items[0].scenarios],
            ["binding-second"],
        )

    def test_unrelated_damaged_staging_file_does_not_block_exact_selection(self):
        sealed = self._seal_lesson("isolated-lesson", "C-isolated", "Body")
        selected = runtime_artifacts.stage_scenario(
            self._scenario("selected-scenario", sealed.course_id, sealed.lesson_id)
        )
        unrelated = runtime_artifacts.stage_scenario(
            self._scenario("unrelated-scenario", "C-unrelated", "unrelated-lesson")
        )
        unrelated_path = content.content_root() / unrelated.descriptor.path
        raw = json.loads(unrelated_path.read_text(encoding="utf-8"))
        raw["title"] = "tampered"
        unrelated_path.write_text(json.dumps(raw), encoding="utf-8")

        release, _ = workflow.publish_version(
            sealed.lesson_id,
            1,
            actor="publisher",
            scenario_selections=[self._selection(selected)],
        )

        self.assertEqual(release.items[0].primary_scenario_id, "selected-scenario")

    def test_runtime_artifact_staging_is_immutable_and_size_bounded(self):
        scenario = self._scenario("bounded-scenario", "C-bounded", "bounded-lesson")
        staged = runtime_artifacts.stage_scenario(scenario)
        self.assertEqual(runtime_artifacts.stage_scenario(scenario), staged)

        target = content.content_root() / staged.descriptor.path
        target.write_bytes(b"x" * (MAX_CONTRACT_FILE_BYTES + 1))
        with self.assertRaisesRegex(
            runtime_artifacts.RuntimeArtifactError,
            "exceeds",
        ):
            runtime_artifacts.stage_scenario(scenario)

        shutil.rmtree(content.runtime_scenario_dir())
        content.runtime_scenario_dir().write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(
            runtime_artifacts.RuntimeArtifactError,
            "real directory",
        ):
            runtime_artifacts.list_staged_scenarios()

    def test_damaged_historical_scenario_blocks_rollback_without_pointer_move(self):
        sealed = self._seal_lesson("rollback-lesson", "C-joint-rollback", "Body")
        staged = runtime_artifacts.stage_scenario(
            self._scenario("rollback-scenario", sealed.course_id, sealed.lesson_id)
        )
        historical, _ = workflow.publish_version(
            sealed.lesson_id,
            1,
            actor="publisher",
            scenario_selections=[self._selection(staged)],
        )
        current, _ = workflow.publish_version(
            sealed.lesson_id,
            1,
            actor="publisher",
            scenario_selections=[],
        )
        scenario_path = content.content_root() / historical.items[0].scenarios[0].path
        raw = json.loads(scenario_path.read_text(encoding="utf-8"))
        raw["title"] = "tampered"
        scenario_path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaises(content.ContentIntegrityError):
            workflow.rollback_release(
                sealed.course_id,
                actor="publisher",
                target_release_id=historical.release_id,
            )

        self.assertEqual(
            workflow.get_current_release(sealed.course_id).release_id,
            current.release_id,
        )

    def test_cross_course_duplicate_scenario_id_is_rejected(self):
        sealed_a = self._seal_lesson("lesson-a", "C-scenario-a", "Course A")
        sealed_b = self._seal_lesson("lesson-b", "C-scenario-b", "Course B")
        staged_a = runtime_artifacts.stage_scenario(
            self._scenario("global-scenario", sealed_a.course_id, sealed_a.lesson_id)
        )
        staged_b = runtime_artifacts.stage_scenario(
            self._scenario("global-scenario", sealed_b.course_id, sealed_b.lesson_id)
        )
        release_a, _ = workflow.publish_version(
            sealed_a.lesson_id,
            1,
            actor="publisher",
            scenario_selections=[self._selection(staged_a)],
        )

        with self.assertRaises(workflow.ContentConflict):
            workflow.publish_version(
                sealed_b.lesson_id,
                1,
                actor="publisher",
                scenario_selections=[self._selection(staged_b)],
            )

        self.assertEqual(
            workflow.get_current_release(sealed_a.course_id).release_id,
            release_a.release_id,
        )
        self.assertIsNone(workflow.get_current_release(sealed_b.course_id))

    def test_concurrent_publication_has_one_pointer_winner(self):
        sealed = self._seal_lesson("race-lesson", "C-race", "Race body")
        first = runtime_artifacts.stage_scenario(
            self._scenario("race-first", sealed.course_id, sealed.lesson_id)
        )
        second = runtime_artifacts.stage_scenario(
            self._scenario("race-second", sealed.course_id, sealed.lesson_id)
        )
        barrier = Barrier(2)
        state = local()
        main_thread = current_thread()
        original_load_pointer = workflow._load_pointer
        results = []
        errors = []

        def synchronized_load_pointer(course_id, required=True):
            result = original_load_pointer(course_id, required=required)
            if current_thread() is not main_thread and not getattr(state, "arrived", False):
                state.arrived = True
                barrier.wait(2)
            return result

        def publish(record):
            try:
                results.append(
                    workflow.publish_version(
                        sealed.lesson_id,
                        1,
                        actor="publisher",
                        scenario_selections=[self._selection(record)],
                    )[0]
                )
            except BaseException as exc:
                errors.append(exc)

        with patch.object(
            workflow,
            "_load_pointer",
            side_effect=synchronized_load_pointer,
        ):
            threads = [Thread(target=publish, args=(record,)) for record in (first, second)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], workflow.ContentConflict)
        current = workflow.get_current_release(sealed.course_id)
        self.assertEqual(current.release_id, results[0].release_id)
        self.assertEqual(len(workflow.list_releases(sealed.course_id)), 2)

    def test_v1_active_release_remains_readable_and_upgrades_on_publish(self):
        sealed_v1 = self._seal_lesson("legacy-v1", "C-legacy-v1", "Legacy body")
        item = workflow._materialize_release_item(sealed_v1)
        release_id = workflow._release_id(sealed_v1.course_id, 1)
        legacy = workflow.CourseReleaseManifest(
            release_id=release_id,
            release_no=1,
            course_id=sealed_v1.course_id,
            operation="bootstrap",
            created_at=datetime.now(timezone.utc),
            created_by="legacy-publisher",
            items=(item,),
            checksum="0" * 64,
        )
        legacy = workflow._sign(legacy, workflow.CourseReleaseManifest)
        manifest_path = workflow._release_path(sealed_v1.course_id, release_id)
        content._atomic_write_json(
            manifest_path,
            legacy.model_dump(mode="json"),
            overwrite=False,
        )
        pointer = workflow._build_pointer(
            legacy,
            actor="legacy-publisher",
            previous_pointer=None,
        )
        content._atomic_write_json(
            workflow._active_pointer_path(sealed_v1.course_id),
            pointer.model_dump(mode="json"),
        )

        self.assertEqual(workflow.get_current_release(sealed_v1.course_id).schema_version, "course-release/v1")
        self.assertEqual(workflow.load_published_packages()[0].body[0], "Legacy body")

        sealed_v2 = self._seal_next_version(sealed_v1.lesson_id, "Upgraded body")
        upgraded, _ = workflow.publish_version(
            sealed_v2.lesson_id,
            2,
            actor="publisher",
        )
        self.assertEqual(upgraded.schema_version, "course-release/v2")
        self.assertEqual(workflow.load_published_packages()[0].body[0], "Upgraded body")

    def _seal_lesson(self, lesson_id: str, course_id: str, body: str):
        package = content.content_template()
        package.lesson_id = lesson_id
        package.course_id = course_id
        package.course_title = f"Course {course_id}"
        package.title = f"Lesson {lesson_id}"
        package.unit = f"Unit {course_id}"
        package.era = "Test era"
        package.body = [body, "Second paragraph.", "Third paragraph."]
        content.save_draft(package, saved_by="author")
        workflow.validate_draft(lesson_id, actor="author")
        workflow.submit_for_review(lesson_id, actor="author")
        workflow.approve_draft(lesson_id, actor="reviewer")
        return workflow.seal_approved_draft(lesson_id, actor="reviewer")[0]

    def _seal_next_version(self, lesson_id: str, body: str):
        package = content.get_draft(lesson_id)
        package.body[0] = body
        content.save_draft(package, saved_by="author")
        workflow.validate_draft(lesson_id, actor="author")
        workflow.submit_for_review(lesson_id, actor="author")
        workflow.approve_draft(lesson_id, actor="reviewer")
        return workflow.seal_approved_draft(lesson_id, actor="reviewer")[0]

    @staticmethod
    def _selection(record):
        descriptor = record.descriptor
        return workflow.ScenarioReleaseSelection(
            scenario_id=descriptor.artifact_id,
            scenario_version=descriptor.version,
            scenario_checksum=descriptor.checksum,
            primary=True,
        )

    @staticmethod
    def _scenario(scenario_id: str, course_id: str, lesson_id: str):
        now = datetime.now(timezone.utc)
        payload = {
            "scenario_id": scenario_id,
            "scenario_version": 1,
            "status": "sealed",
            "course_id": course_id,
            "lesson_id": lesson_id,
            "title": f"Scenario {scenario_id}",
            "scenario_type": "crisis_governance",
            "student_role": "Decision maker",
            "objective": "Reach a valid ending",
            "opening": "The situation requires a decision.",
            "variables": [
                {
                    "variable_id": "progress",
                    "label": "Progress",
                    "initial": 0,
                    "minimum": 0,
                    "maximum": 10,
                }
            ],
            "action_rules": [
                {
                    "action_id": "advance",
                    "label": "Advance",
                    "effects": [
                        {
                            "kind": "state",
                            "variable_id": "progress",
                            "operation": "add",
                            "value": 1,
                        }
                    ],
                }
            ],
            "ending_rules": [
                {
                    "ending_id": "complete",
                    "title": "Complete",
                    "conditions": [
                        {
                            "kind": "state",
                            "variable_id": "progress",
                            "operator": "gte",
                            "value": 1,
                        }
                    ],
                    "summary": "The decision reached the ending.",
                }
            ],
            "sealed_at": now,
            "sealed_by": "scenario-reviewer",
            "checksum": "0" * 64,
        }
        provisional = ScenarioTemplateV1.model_validate(payload)
        payload["checksum"] = calculate_contract_checksum(provisional)
        return ScenarioTemplateV1.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
