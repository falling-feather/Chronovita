from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services import content
from services.content import evidence_workflow, scenario_authoring, workflow
from services.content.flagships.westzhou_l103_draft import (
    CORPUS_ID,
    COURSE_ID,
    LESSON_ID,
    SCENARIO_ID,
    build_l103_authoring_bundle,
)
from services.contracts.rules_v1 import evaluate_rule_action, initial_rule_snapshot


class WestZhouL103AuthoringDraftTests(unittest.TestCase):
    def test_current_teacher_identity_and_distinct_relationship_activity(self):
        course, scenario, evidence = build_l103_authoring_bundle()
        textbook = json.loads(
            Path("content/textbooks/C-prequin-state.json").read_text(encoding="utf-8")
        )
        teacher_lesson = next(
            item for item in textbook["lessons"] if item["lesson_id"] == LESSON_ID
        )

        self.assertEqual((course.course_id, course.lesson_id), (COURSE_ID, LESSON_ID))
        self.assertEqual(course.status, "draft")
        self.assertEqual(course.title, "西周分封与宗法")
        self.assertEqual(course.title, teacher_lesson["title"])
        self.assertEqual(course.body, teacher_lesson["body"])
        self.assertNotIn("商鞅", "".join(course.body))
        self.assertEqual(
            [item.name for item in course.people],
            [item["name"] for item in teacher_lesson["people"]],
        )
        self.assertEqual(scenario.scenario_id, SCENARIO_ID)
        self.assertNotIn("shangyang", scenario.scenario_id)
        self.assertEqual(scenario.max_turns, 5)
        self.assertEqual(scenario.scenario_type, "council")
        self.assertEqual(len(scenario.npcs), 0)
        self.assertTrue(scenario_authoring.validate_scenario_draft(scenario).valid)
        self.assertEqual(evidence.corpus_id, CORPUS_ID)
        self.assertGreaterEqual(len(evidence.sources), 8)
        self.assertGreaterEqual(len(evidence.passages), 25)
        self.assertTrue(all(item.fact_ids for item in evidence.passages))
        self.assertGreaterEqual(
            sum(bool(item.person_ids) for item in evidence.passages),
            3,
        )
        source_ids = {item.source_id for item in evidence.sources}
        self.assertTrue(all(item.source_id in source_ids for item in evidence.passages))
        self.assertIn(
            "匽侯作馈盂",
            " ".join(item.text for item in evidence.passages),
        )

    def test_relationship_map_outcomes_and_early_source_hold_are_reachable(self):
        from services.content.scenario_authoring import _sealed_contract

        _, scenario_draft, _ = build_l103_authoring_bundle()
        scenario = _sealed_contract(
            scenario_draft,
            version=1,
            sealed_by="l103-rules-fixture",
            sealed_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
        )
        routes = {
            "ending-network-supported": (
                "l103-capital-map-caution",
                "l103-yan-combine-site",
                "l103-fief-distinguish-levels",
                "l103-lineage-separate-rules",
                "l103-ritual-show-transition",
            ),
            "ending-oversimplified-network": (
                "l103-capital-king-alone",
                "l103-yan-equate-one-inscription",
                "l103-fief-same-everywhere",
                "l103-lineage-all-offices-hereditary",
                "l103-ritual-ritual-only-cause",
            ),
            "ending-review-sources": (
                "l103-capital-show-questions",
                "l103-yan-cite-bowl",
                "l103-fief-mark-teacher-claims",
                "l103-lineage-mark-ritual-layer",
                "l103-ritual-keep-dates-open",
            ),
        }
        for expected_ending, route in routes.items():
            snapshot = initial_rule_snapshot(scenario)
            result = None
            for turn, action_id in enumerate(route, start=1):
                result = evaluate_rule_action(scenario, snapshot, action_id, turn)
                snapshot = result.snapshot
                if turn < 5:
                    self.assertIsNone(result.ending_id)
            self.assertIsNotNone(result)
            self.assertEqual(result.ending_id, expected_ending)
            self.assertTrue(result.turn_limit_reached)

        held = evaluate_rule_action(
            scenario,
            initial_rule_snapshot(scenario),
            "l103-capital-pause-source",
            1,
        )
        self.assertEqual(held.ending_id, "ending-review-sources")
        self.assertFalse(held.turn_limit_reached)

    def test_existing_draft_workflows_validate_without_review_or_publication(self):
        original_root = content.content_root()
        with tempfile.TemporaryDirectory(prefix="chronovita-l103-draft-") as directory:
            try:
                content.configure(Path(directory) / "content")
                course, scenario, evidence = build_l103_authoring_bundle()
                content.save_draft(course, saved_by="content-author-l103")
                course_record = workflow.validate_draft(
                    LESSON_ID,
                    actor="content-author-l103",
                )
                self.assertEqual(course_record.state, "validated")
                self.assertTrue(course_record.validation.valid)

                scenario_authoring.save_scenario_draft(
                    scenario,
                    saved_by="content-author-l103",
                )
                scenario_report = scenario_authoring.validate_saved_scenario_draft(
                    SCENARIO_ID
                )
                self.assertTrue(scenario_report.valid)

                evidence_workflow.save_evidence_draft(
                    evidence,
                    saved_by="content-author-l103",
                )
                evidence_record, report = evidence_workflow.validate_evidence_draft(
                    CORPUS_ID,
                    actor="content-author-l103",
                )
                self.assertTrue(report.valid)
                self.assertEqual(evidence_record.state, "validated")
                self.assertIsNone(evidence_record.sealed_version)
                self.assertEqual(
                    evidence_record.history[-1].action, "validation_passed"
                )
                self.assertGreaterEqual(report.source_count, 8)
                self.assertGreaterEqual(report.passage_count, 25)
                self.assertEqual(report.issues, ())
                self.assertIsNone(workflow.get_current_release(COURSE_ID))
            finally:
                content.configure(original_root)


if __name__ == "__main__":
    unittest.main()
