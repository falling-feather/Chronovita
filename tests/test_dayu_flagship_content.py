from __future__ import annotations

import hashlib
import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from services import content
from services.content import workflow
from services.content.flagships.dayu_l101 import (
    BODY,
    COURSE_ID,
    DAYU_CORPUS_ID,
    DAYU_PRESENTATION_ID,
    DAYU_SCENARIO_ID,
    FACTS,
    LESSON_ID,
    build_dayu_course_draft,
    build_dayu_evidence_draft,
    build_dayu_scenario_draft,
)
from services.content.scenario_authoring import _sealed_contract, validate_scenario_draft
from services.contracts.rules_v1 import evaluate_rule_action, initial_rule_snapshot
from scripts.publish_flagship_lesson import DAYU_ACTORS, publish_dayu


class DayuFlagshipAuthoringTests(unittest.TestCase):
    def test_formal_content_meets_flagship_depth_and_language_boundaries(self):
        course = build_dayu_course_draft()
        evidence = build_dayu_evidence_draft(course)
        scenario = build_dayu_scenario_draft(course)

        self.assertEqual((course.course_id, course.lesson_id), (COURSE_ID, LESSON_ID))
        self.assertGreaterEqual(sum(len(item) for item in BODY), 2500)
        self.assertLessEqual(sum(len(item) for item in BODY), 3500)
        self.assertGreaterEqual(len(course.facts), 12)
        self.assertEqual(len(course.facts), len(FACTS))
        self.assertGreaterEqual(len(course.source_refs), 8)
        self.assertLessEqual(len(course.source_refs), 12)
        self.assertGreaterEqual(len(evidence.passages), 25)
        self.assertLessEqual(len(evidence.passages), 40)
        self.assertGreaterEqual(len(course.people), 4)
        self.assertLessEqual(len(course.people), 6)
        self.assertEqual(scenario.max_turns, 6)
        self.assertEqual(scenario.scenario_type, "crisis_governance")
        self.assertEqual(len(scenario.ending_rules), 4)
        self.assertTrue(validate_scenario_draft(scenario).valid)

        serialized = json.dumps(
            {
                "course": course.model_dump(mode="json"),
                "evidence": evidence.model_dump(mode="json"),
                "scenario": scenario.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        for forbidden in ("技术占位", "教师待审", "placeholder"):
            self.assertNotIn(forbidden, serialized)
        for required in ("传说", "传世文献", "考古", "教学解释", "角色化教学表达，不是史料原话"):
            self.assertIn(required, serialized)
        self.assertEqual(
            [item.passage_id for item in evidence.passages],
            [f"dayu-p{index:03d}" for index in range(1, 31)],
        )
        self.assertTrue(all(item.fact_ids for item in evidence.passages))
        self.assertEqual(
            {item.reliability for item in evidence.sources},
            {"reviewed", "disputed"},
        )

    def test_success_cost_compromise_and_failure_are_each_reachable_in_six_turns(self):
        scenario = _sealed_contract(
            build_dayu_scenario_draft(build_dayu_course_draft()),
            version=1,
            sealed_by="reachability-test",
            sealed_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        witnesses = {
            "ending-balanced-success": (
                "survey-waterways",
                "dredge-diversion",
                "dredge-diversion",
                "dredge-diversion",
                "share-map-plan",
                "share-map-plan",
            ),
            "ending-costly-success": (
                "survey-waterways",
                "survey-waterways",
                "dredge-diversion",
                "dredge-diversion",
                "dredge-diversion",
                "dredge-diversion",
            ),
            "ending-negotiated-compromise": (
                "survey-waterways",
                "survey-waterways",
                "survey-waterways",
                "dredge-diversion",
                "dredge-diversion",
                "dredge-diversion",
            ),
            "ending-governance-failure": ("survey-waterways",) * 6,
        }
        for ending_id, sequence in witnesses.items():
            snapshot = initial_rule_snapshot(scenario)
            result = None
            for turn_no, action_id in enumerate(sequence, start=1):
                result = evaluate_rule_action(
                    scenario,
                    snapshot,
                    action_id,
                    turn_no,
                )
                snapshot = result.snapshot
                if turn_no < 6:
                    self.assertIsNone(result.ending_id)
            self.assertIsNotNone(result)
            self.assertEqual(result.ending_id, ending_id)
            self.assertTrue(result.turn_limit_reached)

    @staticmethod
    def _copy_media(target: Path) -> None:
        source = Path("content/media/lessons/L101/v001")
        destination = target / "media/lessons/L101/v001"
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("dayu-intro.mp4", "dayu-poster.webp", "dayu-transcript.md"):
            shutil.copyfile(source / name, destination / name)


class DayuFlagshipPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-dayu-publication" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        DayuFlagshipAuthoringTests._copy_media(self.tmp_root)

    def tearDown(self):
        content.configure()
        shutil.rmtree(self.tmp_root.parent, ignore_errors=True)

    def test_distinct_actors_publish_exact_v3_resources_and_assets(self):
        result = publish_dayu(root=self.tmp_root)
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["scenario_id"], DAYU_SCENARIO_ID)

        course_record = workflow.get_workflow(LESSON_ID)
        self.assertEqual(course_record.state, "published")
        actors_by_action = {event.action: event.actor for event in course_record.history}
        self.assertEqual(actors_by_action["save"], DAYU_ACTORS.author)
        self.assertEqual(actors_by_action["submit_review"], DAYU_ACTORS.author)
        self.assertEqual(actors_by_action["approve"], DAYU_ACTORS.reviewer)
        self.assertEqual(actors_by_action["seal"], DAYU_ACTORS.publisher)
        self.assertEqual(actors_by_action["publish"], DAYU_ACTORS.publisher)
        self.assertEqual(len({DAYU_ACTORS.author, DAYU_ACTORS.reviewer, DAYU_ACTORS.publisher}), 3)

        from services.content import evidence_workflow

        evidence_record = evidence_workflow.get_evidence_workflow(DAYU_CORPUS_ID)
        evidence_actors = {
            event.action: event.actor for event in evidence_record.history
        }
        self.assertEqual(evidence_actors["save"], DAYU_ACTORS.author)
        self.assertEqual(evidence_actors["approve"], DAYU_ACTORS.reviewer)
        self.assertEqual(evidence_actors["seal"], DAYU_ACTORS.publisher)

        release = workflow.get_current_release(COURSE_ID)
        self.assertEqual(release.schema_version, "course-release/v3")
        item = next(candidate for candidate in release.items if candidate.lesson_id == LESSON_ID)
        self.assertEqual(item.primary_scenario_id, DAYU_SCENARIO_ID)
        self.assertEqual(item.evidence_corpus.artifact_id, DAYU_CORPUS_ID)
        self.assertEqual(item.lesson_presentation.artifact_id, DAYU_PRESENTATION_ID)
        resources = workflow.get_published_lesson_resources(COURSE_ID, LESSON_ID)
        self.assertEqual(len(resources.evidence_corpus.sources), 12)
        self.assertEqual(len(resources.evidence_corpus.passages), 30)
        self.assertEqual(resources.lesson_presentation.video_duration_seconds, 45)
        self.assertEqual(resources.lesson_presentation.phase_minutes, {"observe": 9, "decide": 14, "consult": 7, "dossier": 10})
        for path, checksum in (
            (resources.lesson_presentation.video_path, resources.lesson_presentation.video_sha256),
            (resources.lesson_presentation.poster_path, resources.lesson_presentation.poster_sha256),
            (resources.lesson_presentation.transcript_path, resources.lesson_presentation.transcript_sha256),
        ):
            self.assertEqual(
                hashlib.sha256((self.tmp_root / path).read_bytes()).hexdigest(),
                checksum,
            )

        repeated = publish_dayu(root=self.tmp_root)
        self.assertEqual(repeated["status"], "already-published")
        self.assertEqual(repeated["release_id"], release.release_id)

        changed_source = build_dayu_course_draft().model_copy(
            update={"title": "被意外改写的标题"}
        )
        with patch(
            "scripts.publish_flagship_lesson.build_dayu_course_draft",
            return_value=changed_source,
        ):
            with self.assertRaisesRegex(RuntimeError, "canonical source"):
                publish_dayu(root=self.tmp_root)

        transcript = self.tmp_root / "media/lessons/L101/v001/dayu-transcript.md"
        transcript.write_text(
            transcript.read_text(encoding="utf-8") + "\n意外漂移。\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "presentation"):
            publish_dayu(root=self.tmp_root)


if __name__ == "__main__":
    unittest.main()
