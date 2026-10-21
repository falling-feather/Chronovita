from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services import content
from services.content import evidence_workflow, scenario_authoring, workflow
from services.content.flagships.shang_l102_draft import (
    CORPUS_ID,
    COURSE_ID,
    LESSON_ID,
    SCENARIO_ID,
    build_l102_authoring_bundle,
)
from services.contracts.rules_v1 import evaluate_rule_action, initial_rule_snapshot


class L102AuthoringDraftTests(unittest.TestCase):
    def test_authoring_bundle_uses_current_teacher_text_and_has_bounded_references(
        self,
    ):
        course, scenario, evidence = build_l102_authoring_bundle()
        textbook_path = Path("content/textbooks/C-prequin-state.json")
        textbook = json.loads(textbook_path.read_text(encoding="utf-8"))
        teacher_lesson = next(
            item for item in textbook["lessons"] if item["lesson_id"] == LESSON_ID
        )

        self.assertEqual((course.course_id, course.lesson_id), (COURSE_ID, LESSON_ID))
        self.assertEqual(course.status, "draft")
        self.assertEqual(course.version, 0)
        self.assertEqual(course.title, teacher_lesson["title"])
        self.assertEqual(course.body, teacher_lesson["body"])
        self.assertEqual(
            [item.word for item in course.keywords],
            [item["word"] for item in teacher_lesson["keywords"]],
        )
        self.assertEqual(
            [item.name for item in course.people],
            [item["name"] for item in teacher_lesson["people"]],
        )
        self.assertEqual(scenario.scenario_id, SCENARIO_ID)
        self.assertEqual(scenario.max_turns, 5)
        self.assertEqual(scenario.scenario_type, "council")
        self.assertEqual(len(scenario.nodes), 6)
        self.assertEqual(len(scenario.npcs), 0)
        self.assertEqual(evidence.corpus_id, CORPUS_ID)
        self.assertGreaterEqual(len(evidence.passages), 25)
        self.assertTrue(all(item.fact_ids for item in evidence.passages))
        self.assertEqual(
            {item.passage_id for item in evidence.passages},
            {f"l102-p{index:03d}" for index in range(1, len(evidence.passages) + 1)},
        )
        source_ids = {item.source_id for item in evidence.sources}
        self.assertTrue(all(item.source_id in source_ids for item in evidence.passages))
        self.assertTrue(scenario_authoring.validate_scenario_draft(scenario).valid)

    def test_five_round_routes_reach_ready_overclaim_and_more_evidence_feedback(self):
        from services.content.scenario_authoring import _sealed_contract

        _, scenario_draft, _ = build_l102_authoring_bundle()
        scenario = _sealed_contract(
            scenario_draft,
            version=1,
            sealed_by="l102-reachability-check",
            sealed_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
        )
        routes = {
            "ending-evidence-card-ready": (
                "l102-migration-flag-location",
                "l102-city-combine-remains",
                "l102-bronze-label-inference",
                "l102-oracle-cite-item",
                "l102-fall-compare-layers",
            ),
            "ending-overclaim-review": (
                "l102-migration-equate-site",
                "l102-city-single-tomb",
                "l102-bronze-invent-workforce",
                "l102-oracle-generalize-bone",
                "l102-fall-single-moral-cause",
            ),
            "ending-more-sources-needed": (
                "l102-migration-equate-site",
                "l102-city-map-with-limit",
                "l102-bronze-label-inference",
                "l102-oracle-generalize-bone",
                "l102-fall-mark-date-frame",
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
            "l102-migration-pause-for-source",
            1,
        )
        self.assertEqual(held.ending_id, "ending-more-sources-needed")
        self.assertFalse(held.turn_limit_reached)

    def test_existing_workflows_validate_drafts_without_approval_or_publication(self):
        original_root = content.content_root()
        with tempfile.TemporaryDirectory(prefix="chronovita-l102-draft-") as directory:
            try:
                content.configure(Path(directory) / "content")
                course, scenario, evidence = build_l102_authoring_bundle()
                content.save_draft(course, saved_by="content-author-l102")
                course_record = workflow.validate_draft(
                    LESSON_ID, actor="content-author-l102"
                )
                self.assertEqual(course_record.state, "validated")
                self.assertTrue(course_record.validation.valid)

                scenario_authoring.save_scenario_draft(
                    scenario, saved_by="content-author-l102"
                )
                scenario_report = scenario_authoring.validate_saved_scenario_draft(
                    SCENARIO_ID
                )
                self.assertTrue(scenario_report.valid)

                evidence_workflow.save_evidence_draft(
                    evidence, saved_by="content-author-l102"
                )
                evidence_record, evidence_report = (
                    evidence_workflow.validate_evidence_draft(
                        CORPUS_ID,
                        actor="content-author-l102",
                    )
                )
                self.assertTrue(evidence_report.valid)
                self.assertEqual(evidence_record.state, "validated")
                self.assertIsNone(evidence_record.sealed_version)
                self.assertEqual(
                    evidence_record.history[-1].action, "validation_passed"
                )
                self.assertEqual(evidence_report.source_count, 8)
                self.assertEqual(evidence_report.passage_count, 29)
                self.assertEqual(evidence_report.issues, ())
                self.assertEqual(workflow.get_current_release(COURSE_ID), None)
            finally:
                content.configure(original_root)


if __name__ == "__main__":
    unittest.main()
