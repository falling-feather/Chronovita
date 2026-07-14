import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from services import content
from services.contracts.examples import build_dayu_bundle, example_documents
from services.contracts.rules_v1 import (
    evaluate_rule_action,
    initial_rule_snapshot,
    render_rule_narrative,
)
from services.contracts.v1 import (
    CoursePackageV1,
    DossierV1,
    GameSessionV1,
    RuntimeBundleV1,
    SCHEMA_DOCUMENTS,
    ScenarioTemplateV1,
    calculate_contract_checksum,
    course_package_from_legacy,
    schema_document,
    verify_contract_checksum,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "v1"
EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "v1"


class RuntimeContractTests(unittest.TestCase):
    def test_committed_schema_documents_match_pydantic_models(self):
        for filename, (model, schema_id) in SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                committed = _read_json(SCHEMA_DIR / filename)
                self.assertEqual(committed, schema_document(model, schema_id))

    def test_generated_contract_directories_have_no_stale_json(self):
        self.assertEqual(
            {path.name for path in SCHEMA_DIR.glob("*.json")},
            set(SCHEMA_DOCUMENTS),
        )
        self.assertEqual(
            {path.name for path in EXAMPLE_DIR.glob("*.json")},
            set(example_documents()),
        )

    def test_schema_documents_explain_lifecycle_and_semantic_validation(self):
        lifecycle_models = {
            CoursePackageV1,
            ScenarioTemplateV1,
            GameSessionV1,
            DossierV1,
        }
        for filename, (model, schema_id) in SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                document = schema_document(model, schema_id)
                self.assertIn("RuntimeBundleV1", document["$comment"])
                if model in lifecycle_models:
                    self.assertTrue(document.get("allOf"))
                    self.assertIn("status", document.get("required", []))

        course_schema = schema_document(CoursePackageV1, "urn:test:course")
        scenario_schema = schema_document(ScenarioTemplateV1, "urn:test:scenario")
        self.assertIn(
            "content_version",
            _schema_then_for_status(course_schema, "sealed")["required"],
        )
        self.assertIn(
            "scenario_version",
            _schema_then_for_status(scenario_schema, "sealed")["required"],
        )

    def test_dayu_example_documents_are_valid_and_current(self):
        expected = example_documents()
        validators = {
            "dayu-course-package.json": CoursePackageV1,
            "dayu-scenario-template.json": ScenarioTemplateV1,
            "dayu-game-session.json": GameSessionV1,
            "dayu-dossier.json": DossierV1,
            "dayu-runtime-bundle.json": RuntimeBundleV1,
        }
        for filename, model in validators.items():
            with self.subTest(filename=filename):
                raw = _read_json(EXAMPLE_DIR / filename)
                parsed = model.model_validate(raw)
                self.assertEqual(parsed.model_dump(mode="json"), raw)
                self.assertEqual(raw, expected[filename].model_dump(mode="json"))
                if filename in {
                    "dayu-course-package.json",
                    "dayu-scenario-template.json",
                    "dayu-dossier.json",
                }:
                    self.assertTrue(verify_contract_checksum(parsed))

    def test_bundle_enforces_cross_object_references(self):
        raw = build_dayu_bundle().model_dump(mode="json")
        raw["scenario"]["action_rules"][0]["fact_refs"] = ["fact-does-not-exist"]
        _refresh_bundle_artifact_checksums(raw)
        with self.assertRaisesRegex(ValidationError, "unknown references"):
            RuntimeBundleV1.model_validate(raw)

    def test_bundle_rejects_tampered_sealed_artifacts(self):
        raw = build_dayu_bundle().model_dump(mode="json")
        raw["course"]["title"] = "Tampered after sealing"
        with self.assertRaisesRegex(ValidationError, "invalid checksum"):
            RuntimeBundleV1.model_validate(raw)

    def test_bundle_replays_state_rules_and_turn_status(self):
        over_turn_limit = build_dayu_bundle().model_dump(mode="json")
        over_turn_limit["scenario"]["max_turns"] = 4
        _refresh_bundle_artifact_checksums(over_turn_limit)
        with self.assertRaisesRegex(ValidationError, "max_turns"):
            RuntimeBundleV1.model_validate(over_turn_limit)

        active_at_turn_limit = build_dayu_bundle().model_dump(mode="json")
        active_at_turn_limit["scenario"]["max_turns"] = 5
        active_at_turn_limit["scenario"]["ending_rules"][0]["conditions"][0]["value"] = 6
        active_at_turn_limit["dossier"] = None
        active_at_turn_limit["session"].update(
            status="active",
            ending_id=None,
            dossier_id=None,
            ended_at=None,
            available_action_ids=[],
        )
        _refresh_bundle_artifact_checksums(active_at_turn_limit)
        with self.assertRaisesRegex(ValidationError, "remain open.*max_turns"):
            RuntimeBundleV1.model_validate(active_at_turn_limit)

        continues_after_ending = build_dayu_bundle().model_dump(mode="json")
        continues_after_ending["scenario"]["ending_rules"][1]["conditions"][0]["value"] = 75
        _refresh_bundle_artifact_checksums(continues_after_ending)
        with self.assertRaisesRegex(ValidationError, "continues after ending"):
            RuntimeBundleV1.model_validate(continues_after_ending)

        unavailable_action = build_dayu_bundle().model_dump(mode="json")
        unavailable_action["session"]["turns"][0]["classified_action_id"] = "open-channels"
        with self.assertRaisesRegex(ValidationError, "action conditions are not satisfied"):
            RuntimeBundleV1.model_validate(unavailable_action)

        wrong_action = build_dayu_bundle().model_dump(mode="json")
        wrong_action["session"]["turns"][0]["classified_action_id"] = "reinforce-dam"
        with self.assertRaisesRegex(ValidationError, "state_after does not match rule effects"):
            RuntimeBundleV1.model_validate(wrong_action)

        missing_event = build_dayu_bundle().model_dump(mode="json")
        missing_event["session"]["turns"][2]["triggered_event_ids"] = []
        with self.assertRaisesRegex(ValidationError, "triggered events do not match"):
            RuntimeBundleV1.model_validate(missing_event)

        rejected_with_effects = build_dayu_bundle().model_dump(mode="json")
        rejected_with_effects["session"]["turns"][0]["status"] = "rejected"
        with self.assertRaisesRegex(ValidationError, "cannot contain rule effects"):
            RuntimeBundleV1.model_validate(rejected_with_effects)

        invalid_ended_at = build_dayu_bundle().model_dump(mode="json")
        invalid_ended_at["session"]["ended_at"] = "2020-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValidationError, "ended_at must stay"):
            RuntimeBundleV1.model_validate(invalid_ended_at)

        abandoned_with_success = build_dayu_bundle().model_dump(mode="json")
        abandoned_with_success["dossier"] = None
        abandoned_with_success["session"]["status"] = "abandoned"
        with self.assertRaisesRegex(ValidationError, "abandoned/failed"):
            RuntimeBundleV1.model_validate(abandoned_with_success)

        active = _zero_turn_bundle_raw()
        self.assertEqual(RuntimeBundleV1.model_validate(active).session.status, "active")
        active["session"]["available_action_ids"].pop()
        with self.assertRaisesRegex(ValidationError, "available_action_ids"):
            RuntimeBundleV1.model_validate(active)

    def test_terminal_failure_cannot_hide_a_reached_ending(self):
        for status in ("failed", "abandoned"):
            with self.subTest(status=status):
                raw = build_dayu_bundle().model_dump(mode="json")
                raw["dossier"] = None
                raw["session"].update(
                    status=status,
                    ending_id=None,
                    dossier_id=None,
                    available_action_ids=[],
                )
                with self.assertRaisesRegex(
                    ValidationError,
                    "cannot discard reached ending",
                ):
                    RuntimeBundleV1.model_validate(raw)

    def test_contracts_reject_non_finite_rule_numbers(self):
        raw = build_dayu_bundle().scenario.model_dump(mode="python")
        raw["variables"][0]["initial"] = float("nan")
        with self.assertRaisesRegex(ValidationError, "finite number"):
            ScenarioTemplateV1.model_validate(raw)

    def test_bundle_replays_npc_effects(self):
        raw = build_dayu_bundle().model_dump(mode="json")
        raw["session"]["turns"][1]["npc_changes"][0]["trust_after"] = 14
        with self.assertRaisesRegex(ValidationError, "npc change does not match rule effects"):
            RuntimeBundleV1.model_validate(raw)

    def test_bundle_replays_all_rule_products_and_revision(self):
        wrong_state_changes = build_dayu_bundle().model_dump(mode="json")
        wrong_state_changes["session"]["turns"][0]["state_changes"].reverse()
        with self.assertRaisesRegex(ValidationError, "state_changes do not match"):
            RuntimeBundleV1.model_validate(wrong_state_changes)

        wrong_facts = build_dayu_bundle().model_dump(mode="json")
        wrong_facts["session"]["turns"][0]["fact_refs"] = ["fact-cooperation"]
        with self.assertRaisesRegex(ValidationError, "fact_refs do not match"):
            RuntimeBundleV1.model_validate(wrong_facts)

        wrong_hash = build_dayu_bundle().model_dump(mode="json")
        wrong_hash["session"]["turns"][0]["ruleset_hash"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "ruleset_hash does not match"):
            RuntimeBundleV1.model_validate(wrong_hash)

        wrong_narrative = build_dayu_bundle().model_dump(mode="json")
        wrong_narrative["session"]["turns"][0]["narrative"] = "tampered"
        with self.assertRaisesRegex(ValidationError, "rules narrative does not match"):
            RuntimeBundleV1.model_validate(wrong_narrative)

        wrong_revision = build_dayu_bundle().model_dump(mode="json")
        wrong_revision["session"]["revision"] = 999
        with self.assertRaisesRegex(ValidationError, "revision must equal"):
            RuntimeBundleV1.model_validate(wrong_revision)

    def test_dossier_must_match_session_ending_and_full_trajectory(self):
        forged_quote = build_dayu_bundle().model_dump(mode="json")
        forged_quote["dossier"]["key_choices"][0]["choice"] = "FORGED PLAYER QUOTE"
        forged_quote["dossier"]["checksum"] = calculate_contract_checksum(
            DossierV1.model_validate(forged_quote["dossier"])
        )
        with self.assertRaisesRegex(ValidationError, "quote applied player input"):
            RuntimeBundleV1.model_validate(forged_quote)

        early_dossier = build_dayu_bundle().model_dump(mode="json")
        early_dossier["dossier"]["generated_at"] = "2026-07-14T02:20:00Z"
        early_dossier["dossier"]["checksum"] = calculate_contract_checksum(
            DossierV1.model_validate(early_dossier["dossier"])
        )
        with self.assertRaisesRegex(ValidationError, "generated_at"):
            RuntimeBundleV1.model_validate(early_dossier)

        wrong_session_ending = build_dayu_bundle().model_dump(mode="json")
        wrong_session_ending["session"]["ending_id"] = "ending-timeout"
        wrong_session_ending["dossier"]["ending_id"] = "ending-timeout"
        wrong_session_ending["dossier"]["checksum"] = calculate_contract_checksum(
            DossierV1.model_validate(wrong_session_ending["dossier"])
        )
        with self.assertRaisesRegex(ValidationError, "ending_id does not match ending rules"):
            RuntimeBundleV1.model_validate(wrong_session_ending)

        wrong_ending = build_dayu_bundle().model_dump(mode="json")
        wrong_ending["dossier"]["ending_id"] = "ending-timeout"
        wrong_ending["dossier"]["checksum"] = calculate_contract_checksum(
            DossierV1.model_validate(wrong_ending["dossier"])
        )
        with self.assertRaisesRegex(ValidationError, "ending_id must match"):
            RuntimeBundleV1.model_validate(wrong_ending)

        wrong_trajectory = build_dayu_bundle().model_dump(mode="json")
        wrong_trajectory["dossier"]["state_trajectory"][1]["state"]["flood_risk"] = 74
        wrong_trajectory["dossier"]["checksum"] = calculate_contract_checksum(
            DossierV1.model_validate(wrong_trajectory["dossier"])
        )
        with self.assertRaisesRegex(ValidationError, "trajectory must match"):
            RuntimeBundleV1.model_validate(wrong_trajectory)

    def test_zero_turn_session_cannot_start_from_an_arbitrary_state(self):
        raw = _zero_turn_bundle_raw()
        raw["session"]["current_state"]["flood_risk"] -= 1
        with self.assertRaisesRegex(ValidationError, "zero-turn session"):
            RuntimeBundleV1.model_validate(raw)

    def test_scenario_rejects_unknown_state_variable(self):
        raw = build_dayu_bundle().scenario.model_dump(mode="json")
        raw["action_rules"][0]["effects"][0]["variable_id"] = "missing-variable"
        with self.assertRaisesRegex(ValidationError, "unknown references"):
            ScenarioTemplateV1.model_validate(raw)

    def test_contracts_reject_unknown_fields(self):
        raw = build_dayu_bundle().course.model_dump(mode="json")
        raw["titel"] = "typo"
        with self.assertRaises(ValidationError):
            CoursePackageV1.model_validate(raw)

    def test_incomplete_drafts_are_allowed_but_cannot_be_sealed(self):
        course = CoursePackageV1(
            package_id="pkg-incomplete",
            course_id="C-incomplete",
            lesson_id="lesson-incomplete",
            title="Incomplete draft",
            unit="Draft unit",
            era="Draft era",
            body=[],
        )
        scenario = ScenarioTemplateV1(
            scenario_id="scenario-incomplete",
            course_id=course.course_id,
            lesson_id=course.lesson_id,
            title="Incomplete scenario",
            scenario_type="crisis_governance",
            student_role="Draft role",
            objective="Draft objective",
            opening="Draft opening",
        )

        self.assertEqual(course.status, "draft")
        self.assertEqual(scenario.status, "draft")
        sealed = course.model_dump(mode="json")
        sealed.update(
            status="sealed",
            content_version=1,
            sealed_at="2026-07-14T00:00:00Z",
            sealed_by="tester",
            checksum="a" * 64,
        )
        with self.assertRaisesRegex(ValidationError, "require body"):
            CoursePackageV1.model_validate(sealed)

    def test_checksum_detects_artifact_tampering(self):
        course = build_dayu_bundle().course
        tampered = course.model_copy(update={"title": "tampered"})
        self.assertTrue(verify_contract_checksum(course))
        self.assertFalse(verify_contract_checksum(tampered))

    def test_contract_models_are_frozen_value_objects(self):
        course = build_dayu_bundle().course
        with self.assertRaises(ValidationError):
            course.status = "draft"
        self.assertEqual(course.status, "sealed")
        self.assertEqual(course.content_version, 1)

    def test_legacy_lesson_content_can_be_normalized_without_mutation(self):
        legacy = content.content_template()
        before = deepcopy(legacy.model_dump(mode="json"))
        legacy.lesson_id = "legacy-contract-test"
        legacy.course_id = "C-legacy-contract"
        legacy.course_title = "Legacy Course"
        legacy.era_id = "legacy-era"
        legacy.section = "Legacy Section"
        legacy.lesson_no = "L-01"
        legacy.duration = "10:00"
        legacy.facts = ["Legacy fact boundary"]
        legacy.level_goals = ["Legacy level goal"]
        legacy.keywords.append(content.KeywordCard(word="Second keyword"))

        normalized = course_package_from_legacy(legacy)
        reordered = legacy.model_copy(deep=True)
        reordered.keywords.reverse()
        normalized_reordered = course_package_from_legacy(reordered)

        self.assertEqual(normalized.schema_version, "course-package/v1")
        self.assertEqual(normalized.lesson_id, legacy.lesson_id)
        self.assertEqual(normalized.course_id, legacy.course_id)
        self.assertEqual(normalized.content_version, 0)
        self.assertEqual(normalized.status, "draft")
        self.assertEqual(normalized.body, legacy.body)
        self.assertEqual(normalized.course_title, "Legacy Course")
        self.assertEqual(normalized.era_id, "legacy-era")
        self.assertEqual(normalized.section, "Legacy Section")
        self.assertEqual(normalized.lesson_no, "L-01")
        self.assertEqual(normalized.duration, "10:00")
        self.assertEqual(normalized.facts[0].statement, "Legacy fact boundary")
        self.assertEqual(normalized.facts[0].source_ref_ids, [])
        self.assertEqual(normalized.compatibility.kind, "lesson-content-package")
        self.assertEqual(
            {item.word: item.keyword_id for item in normalized.keywords},
            {item.word: item.keyword_id for item in normalized_reordered.keywords},
        )
        self.assertEqual(before, content.content_template().model_dump(mode="json"))

    def test_legacy_adapter_preserves_materials_duplicates_and_canvas_ids(self):
        legacy = content.content_template()
        legacy.lesson_id = "legacy-fidelity-test"
        legacy.source_refs = [
            content.SourceRef(title="", source="", url_or_path="refs/source-a.pdf")
        ]
        legacy.keywords = [
            content.KeywordCard(word="shared", gloss="first meaning"),
            content.KeywordCard(word="shared", gloss="second meaning"),
            content.KeywordCard(word="shared", gloss="first meaning"),
        ]
        legacy.seed_canvas = [
            content.SeedCanvasNode(id="keep-node", label="Kept node", note="stable"),
            content.SeedCanvasNode(id="x", label="Mapped node", note="legacy id too short"),
        ]
        legacy.saga_material.title = "Saga title"
        legacy.saga_material.objective = "Saga objective"
        legacy.saga_material.notes = "Saga notes"
        legacy.saga_material.assets = ["scenarios/dayu.json", "shared.asset"]
        legacy.sandbox_material.title = "Sandbox title"
        legacy.sandbox_material.objective = "Sandbox objective"
        legacy.sandbox_material.notes = "Sandbox notes"
        legacy.sandbox_material.assets = ["shared.asset", "maps/dayu.geojson"]

        normalized = course_package_from_legacy(legacy)

        self.assertEqual(len(normalized.keywords), 2)
        self.assertEqual({item.gloss for item in normalized.keywords}, {"first meaning", "second meaning"})
        self.assertTrue(normalized.source_refs[0].title)
        self.assertEqual(normalized.seed_canvas[0].node_id, "keep-node")
        self.assertEqual(
            normalized.compatibility.legacy_id_map["seed_canvas:x"],
            normalized.seed_canvas[1].node_id,
        )
        self.assertEqual(
            normalized.compatibility.unresolved_refs,
            ["scenarios/dayu.json", "shared.asset", "maps/dayu.geojson"],
        )
        self.assertEqual(
            normalized.compatibility.legacy_materials[0].model_dump(mode="json"),
            {
                "kind": "saga",
                "title": "Saga title",
                "objective": "Saga objective",
                "notes": "Saga notes",
                "assets": ["scenarios/dayu.json", "shared.asset"],
            },
        )

    def test_legacy_sealed_content_requires_a_valid_source_checksum(self):
        legacy = content.content_template()
        legacy.lesson_id = "legacy-invalid-seal"
        legacy.status = "sealed"
        legacy.version = 1
        legacy.sealed_at = datetime(2026, 7, 14, tzinfo=timezone.utc)
        legacy.sealed_by = "legacy-admin"
        legacy.checksum = calculate_contract_checksum(legacy)
        legacy.title = "Tampered after source seal"

        with self.assertRaisesRegex(ValueError, "legacy sealed content"):
            course_package_from_legacy(legacy)

    def test_dossier_rejects_edges_with_missing_nodes(self):
        raw = build_dayu_bundle().dossier.model_dump(mode="json")
        raw["knowledge_edges"][0]["target_node_id"] = "missing-node"
        with self.assertRaisesRegex(ValidationError, "unknown references"):
            DossierV1.model_validate(raw)

    def test_legacy_sealed_metadata_and_unresolved_scenario_refs_are_preserved(self):
        legacy = content.content_template()
        legacy.lesson_id = "legacy-sealed-test"
        legacy.status = "sealed"
        legacy.version = 3
        legacy.sealed_at = datetime(2026, 7, 14, tzinfo=timezone.utc)
        legacy.sealed_by = "legacy-admin"
        legacy.saga_material.assets = ["legacy-saga-template"]
        legacy.checksum = calculate_contract_checksum(legacy)

        normalized = course_package_from_legacy(legacy)

        self.assertEqual(normalized.status, "sealed")
        self.assertEqual(normalized.content_version, 3)
        self.assertEqual(normalized.sealed_at, legacy.sealed_at)
        self.assertEqual(normalized.sealed_by, "legacy-admin")
        self.assertNotEqual(normalized.checksum, legacy.checksum)
        self.assertTrue(verify_contract_checksum(normalized))
        self.assertEqual(normalized.compatibility.source_checksum, legacy.checksum)
        self.assertEqual(normalized.scenario_refs, [])
        self.assertEqual(normalized.compatibility.unresolved_refs, ["legacy-saga-template"])

    def test_draft_dossier_cannot_be_smuggled_into_runtime_bundle(self):
        dossier = build_dayu_bundle().dossier.model_dump(mode="json")
        dossier["status"] = "draft"
        with self.assertRaisesRegex(ValidationError, "draft dossiers"):
            DossierV1.model_validate(dossier)

        raw = build_dayu_bundle().model_dump(mode="json")
        raw["dossier"]["status"] = "draft"
        raw["dossier"]["checksum"] = None
        with self.assertRaisesRegex(ValidationError, "final dossier"):
            RuntimeBundleV1.model_validate(raw)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_then_for_status(document: dict, status: str) -> dict:
    return next(
        condition["then"]
        for condition in document["allOf"]
        if condition["if"].get("properties", {}).get("status", {}).get("const") == status
    )


def _refresh_bundle_artifact_checksums(raw: dict) -> None:
    scenario = raw["scenario"]
    scenario["checksum"] = calculate_contract_checksum(
        ScenarioTemplateV1.model_validate(scenario)
    )
    scenario_model = ScenarioTemplateV1.model_validate(scenario)

    course = raw["course"]
    for scenario_ref in course["scenario_refs"]:
        if scenario_ref["scenario_id"] == scenario["scenario_id"]:
            scenario_ref["checksum"] = scenario["checksum"]
    course["checksum"] = calculate_contract_checksum(
        CoursePackageV1.model_validate(course)
    )

    session = raw.get("session")
    if session is not None:
        session["course_checksum"] = course["checksum"]
        session["scenario_checksum"] = scenario["checksum"]
        snapshot = initial_rule_snapshot(scenario_model)
        for turn in session["turns"]:
            result = evaluate_rule_action(
                scenario_model,
                snapshot,
                turn["classified_action_id"],
                turn["turn_no"],
            )
            turn["fact_refs"] = list(result.fact_refs)
            turn["ruleset_hash"] = scenario["checksum"]
            if turn["narrative_source"] == "rules":
                turn["narrative"] = render_rule_narrative(scenario_model, result)
            snapshot = result.snapshot

    dossier = raw.get("dossier")
    if dossier is not None:
        dossier["course_checksum"] = course["checksum"]
        dossier["scenario_checksum"] = scenario["checksum"]
        dossier["checksum"] = calculate_contract_checksum(
            DossierV1.model_validate(dossier)
        )


def _zero_turn_bundle_raw() -> dict:
    raw = build_dayu_bundle().model_dump(mode="json")
    raw["dossier"] = None
    session = raw["session"]
    scenario = raw["scenario"]
    session.update(
        status="active",
        revision=1,
        current_turn=0,
        current_state={item["variable_id"]: item["initial"] for item in scenario["variables"]},
        current_node_id=scenario["start_node_id"],
        npc_states=[
            {
                "person_id": item["person_id"],
                "attitude": item["initial_attitude"],
                "trust": item["initial_trust"],
                "known_fact_refs": [],
                "last_basis_refs": [],
                "flags": {},
                "updated_turn": 0,
            }
            for item in scenario["npcs"]
        ],
        turns=[],
        triggered_event_ids=[],
        available_action_ids=[
            "survey-terrain",
            "reinforce-dam",
            "explain-plan",
            "allocate-food",
        ],
        observed_entities=[],
        history=[],
        ending_id=None,
        dossier_id=None,
        ended_at=None,
    )
    return raw


if __name__ == "__main__":
    unittest.main()
