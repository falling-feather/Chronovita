import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.contracts.examples import build_dayu_bundle, build_shangyang_bundle
from services.contracts.v1 import (
    CoursePackageV1,
    ScenarioTemplateV1,
    calculate_contract_checksum,
)
from services.game_runtime import (
    ActionUnavailable,
    DuplicateActionConflict,
    RevisionConflict,
    RuntimeCommandV1,
    ScenarioFileError,
    ScenarioIntegrityError,
    SessionIntegrityError,
    SessionTerminalError,
    SituationEngineV1,
    load_scenario_template,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "v1"
BASE_TIME = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)


class SituationEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = SituationEngineV1.from_files(
            EXAMPLE_DIR / "dayu-course-package.json",
            EXAMPLE_DIR / "dayu-scenario-template.json",
        )

    def test_dayu_replay_is_deterministic_and_matches_golden_rules(self):
        commands = _dayu_commands()
        first = self.engine.replay(
            session_id="session-runtime-dayu-001",
            user_id="student-runtime",
            started_at=BASE_TIME,
            commands=commands,
            random_seed="fixed-seed",
        )
        second = self.engine.replay(
            session_id="session-runtime-dayu-001",
            user_id="student-runtime",
            started_at=BASE_TIME,
            commands=commands,
            random_seed="fixed-seed",
        )
        self.assertEqual(
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
        )

        golden = build_dayu_bundle().session
        self.assertIsNotNone(golden)
        self.assertEqual(first.status, "completed")
        self.assertEqual(first.ending_id, "ending-water-controlled")
        self.assertEqual(first.current_state, golden.current_state)
        self.assertEqual(first.triggered_event_ids, golden.triggered_event_ids)
        self.assertEqual(len(first.turns), len(golden.turns))
        for actual, expected in zip(first.turns, golden.turns):
            self.assertEqual(actual.classified_action_id, expected.classified_action_id)
            self.assertEqual(actual.state_before, expected.state_before)
            self.assertEqual(actual.state_after, expected.state_after)
            self.assertEqual(actual.state_changes, expected.state_changes)
            self.assertEqual(actual.npc_changes, expected.npc_changes)
            self.assertEqual(actual.triggered_event_ids, expected.triggered_event_ids)

    def test_two_file_driven_scenarios_share_one_engine_without_registration(self):
        shangyang = SituationEngineV1.from_files(
            EXAMPLE_DIR / "shangyang-course-package.json",
            EXAMPLE_DIR / "shangyang-scenario-template.json",
        )
        self.assertEqual(self.engine.scenario.scenario_type, "crisis_governance")
        self.assertEqual(shangyang.scenario.scenario_type, "institutional_reform")

        commands = _shangyang_commands()
        replayed = shangyang.replay(
            session_id="session-runtime-shangyang-001",
            user_id="student-runtime",
            started_at=BASE_TIME,
            commands=commands,
            random_seed="fixed-seed",
        )
        repeated = shangyang.replay(
            session_id="session-runtime-shangyang-001",
            user_id="student-runtime",
            started_at=BASE_TIME,
            commands=commands,
            random_seed="fixed-seed",
        )
        online = shangyang.start_session(
            session_id="session-runtime-shangyang-001",
            user_id="student-runtime",
            started_at=BASE_TIME,
            random_seed="fixed-seed",
        )
        self.assertEqual(
            online.available_action_ids,
            ["consult-court", "announce-principles"],
        )
        for command in commands:
            online = shangyang.apply_action(online, command).session

        self.assertEqual(replayed.model_dump(mode="json"), repeated.model_dump(mode="json"))
        self.assertEqual(replayed.model_dump(mode="json"), online.model_dump(mode="json"))
        self.assertEqual(replayed.status, "completed")
        self.assertEqual(replayed.current_node_id, "node-reform-recorded")
        self.assertEqual(replayed.ending_id, "ending-reform-recorded")
        self.assertEqual(replayed.current_state["law_clarity"], 85)
        self.assertEqual(replayed.current_state["administrative_capacity"], 55)
        self.assertEqual(
            replayed.turns[2].triggered_event_ids,
            ["event-implementation-friction"],
        )
        local_official = next(
            item
            for item in replayed.npc_states
            if item.person_id == "person-local-official"
        )
        self.assertEqual(local_official.trust, 15)

        fixture = build_shangyang_bundle()
        self.assertEqual(shangyang.course, fixture.course)
        self.assertEqual(shangyang.scenario, fixture.scenario)

    def test_shangyang_alternate_node_path_reaches_review_ending(self):
        engine = SituationEngineV1.from_files(
            EXAMPLE_DIR / "shangyang-course-package.json",
            EXAMPLE_DIR / "shangyang-scenario-template.json",
        )
        specs = [
            ("announce-principles", "公布制度原则"),
            ("prepare-local-offices", "准备地方执行节点"),
            ("phase-rollout", "分阶段执行"),
            ("pause-and-review", "暂缓并复核"),
        ]
        commands = [
            RuntimeCommandV1(
                client_action_id=f"client-review-{index:03d}",
                raw_input=raw_input,
                action_id=action_id,
                expected_revision=index,
                occurred_at=BASE_TIME + timedelta(minutes=index),
            )
            for index, (action_id, raw_input) in enumerate(specs, start=1)
        ]
        session = engine.replay(
            session_id="session-runtime-shangyang-review",
            user_id="student-runtime",
            started_at=BASE_TIME,
            commands=commands,
        )
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.current_node_id, "node-review-pending")
        self.assertEqual(session.ending_id, "ending-review-pending")
        self.assertEqual(session.current_state["law_clarity"], 45)

    def test_apply_is_immutable_idempotent_and_revision_guarded(self):
        course_before = self.engine.course.model_dump(mode="json")
        scenario_before = self.engine.scenario.model_dump(mode="json")
        session = self.engine.start_session(
            session_id="session-idempotent",
            user_id="student-runtime",
            started_at=BASE_TIME,
        )
        session_before = session.model_dump(mode="json")
        command = _dayu_commands()[0]

        first = self.engine.apply_action(session, command)
        retry = self.engine.apply_action(first.session, command)
        self.assertEqual(first.session, retry.session)
        self.assertEqual(first.turn, retry.turn)
        self.assertEqual(session.model_dump(mode="json"), session_before)
        self.assertEqual(self.engine.course.model_dump(mode="json"), course_before)
        self.assertEqual(self.engine.scenario.model_dump(mode="json"), scenario_before)

        conflict = command.model_copy(
            update={
                "raw_input": "抢修堤坝",
                "action_id": "reinforce-dam",
            }
        )
        with self.assertRaises(DuplicateActionConflict):
            self.engine.apply_action(first.session, conflict)

        stale = RuntimeCommandV1(
            client_action_id="client-stale-001",
            raw_input="抢修堤坝",
            action_id="reinforce-dam",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=2),
        )
        with self.assertRaises(RevisionConflict):
            self.engine.apply_action(first.session, stale)

    def test_alias_resolution_unavailable_action_and_tampered_session_fail_closed(self):
        session = self.engine.start_session(
            session_id="session-fail-closed",
            user_id="student-runtime",
            started_at=BASE_TIME,
        )
        alias_command = RuntimeCommandV1(
            client_action_id="client-alias-001",
            raw_input="  查看地形  ",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        result = self.engine.apply_action(session, alias_command)
        self.assertEqual(result.turn.classified_action_id, "survey-terrain")

        unavailable = RuntimeCommandV1(
            client_action_id="client-unavailable-001",
            raw_input="开挖疏导线",
            action_id="open-channels",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )
        with self.assertRaises(ActionUnavailable):
            self.engine.apply_action(session, unavailable)
        self.assertEqual(session.current_turn, 0)

        tampered = session.model_copy(deep=True)
        tampered.current_state["flood_risk"] = 1
        with self.assertRaises(SessionIntegrityError):
            self.engine.apply_action(tampered, alias_command)

    def test_new_action_is_rejected_after_terminal_ending(self):
        completed = self.engine.replay(
            session_id="session-terminal",
            user_id="student-runtime",
            started_at=BASE_TIME,
            commands=_dayu_commands(),
        )
        command = RuntimeCommandV1(
            client_action_id="client-after-ending",
            raw_input="抢修堤坝",
            action_id="reinforce-dam",
            expected_revision=completed.revision,
            occurred_at=BASE_TIME + timedelta(minutes=6),
        )
        with self.assertRaises(SessionTerminalError):
            self.engine.apply_action(completed, command)

    def test_turn_limit_without_ending_and_dead_start_fail_deterministically(self):
        max_course, max_scenario = _modified_dayu(
            max_turns=1,
            disable_endings=True,
        )
        max_engine = SituationEngineV1(max_course, max_scenario)
        session = max_engine.start_session(
            session_id="session-max-turn",
            user_id="student-runtime",
            started_at=BASE_TIME,
        )
        result = max_engine.apply_action(session, _dayu_commands()[0])
        self.assertEqual(result.session.status, "failed")
        self.assertEqual(
            result.session.flags["rules_terminal_reason"],
            "max_turns_without_ending",
        )

        dead_course, dead_scenario = _modified_dayu(disable_actions=True)
        dead_engine = SituationEngineV1(dead_course, dead_scenario)
        dead = dead_engine.start_session(
            session_id="session-dead-start",
            user_id="student-runtime",
            started_at=BASE_TIME,
        )
        self.assertEqual(dead.status, "failed")
        self.assertEqual(
            dead.flags["rules_terminal_reason"],
            "no_available_actions_at_start",
        )

    def test_state_and_npc_effects_are_clamped_to_declared_ranges(self):
        course, scenario = _modified_dayu(clamp_effects=True)
        engine = SituationEngineV1(course, scenario)
        session = engine.start_session(
            session_id="session-clamping",
            user_id="student-runtime",
            started_at=BASE_TIME,
        )
        first = engine.apply_action(session, _dayu_commands()[0]).session
        second_command = _dayu_commands()[1].model_copy(update={"expected_revision": 2})
        second = engine.apply_action(first, second_command).session

        self.assertEqual(first.current_state["flood_risk"], 0)
        self.assertEqual(first.current_state["engineering_knowledge"], 100)
        tribe = next(
            item
            for item in second.npc_states
            if item.person_id == "person-tribe-leader"
        )
        self.assertEqual(tribe.attitude, 100)
        self.assertEqual(tribe.trust, 100)

    def test_scenario_files_reject_tampering_and_duplicate_keys(self):
        raw = json.loads(
            (EXAMPLE_DIR / "dayu-scenario-template.json").read_text(encoding="utf-8")
        )
        raw["title"] = "tampered"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tampered = root / "tampered.json"
            tampered.write_text(
                json.dumps(raw, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(ScenarioIntegrityError):
                load_scenario_template(tampered)

            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"scenario_id":"first","scenario_id":"second"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ScenarioFileError, "duplicate JSON key"):
                load_scenario_template(duplicate)


def _dayu_commands() -> list[RuntimeCommandV1]:
    specs = [
        ("survey-terrain", "先勘察地势和河道"),
        ("explain-plan", "向各部族解释疏导计划"),
        ("open-channels", "按勘察结果开挖疏导线"),
        ("allocate-food", "分配粮食，保障参与工程的民众"),
        ("open-channels", "扩大已经见效的疏导工程"),
    ]
    return [
        RuntimeCommandV1(
            client_action_id=f"client-runtime-dayu-{index:03d}",
            raw_input=raw_input,
            action_id=action_id,
            expected_revision=index,
            occurred_at=BASE_TIME + timedelta(minutes=index),
        )
        for index, (action_id, raw_input) in enumerate(specs, start=1)
    ]


def _shangyang_commands() -> list[RuntimeCommandV1]:
    specs = [
        ("consult-court", "征询改革意见"),
        ("standardize-rules", "统一规则文本"),
        ("apply-merit-system", "应用激励规则"),
        ("consolidate-rules", "确认制度方案"),
    ]
    return [
        RuntimeCommandV1(
            client_action_id=f"client-runtime-shangyang-{index:03d}",
            raw_input=raw_input,
            action_id=action_id,
            expected_revision=index,
            occurred_at=BASE_TIME + timedelta(minutes=index),
        )
        for index, (action_id, raw_input) in enumerate(specs, start=1)
    ]


def _modified_dayu(
    *,
    max_turns: int | None = None,
    disable_endings: bool = False,
    disable_actions: bool = False,
    clamp_effects: bool = False,
) -> tuple[CoursePackageV1, ScenarioTemplateV1]:
    bundle = build_dayu_bundle()
    scenario_raw = bundle.scenario.model_dump(mode="python")
    if max_turns is not None:
        scenario_raw["max_turns"] = max_turns
    if disable_endings:
        for ending in scenario_raw["ending_rules"]:
            ending["match"] = "all"
            ending["conditions"] = [
                {
                    "kind": "state",
                    "variable_id": "flood_risk",
                    "operator": "lt",
                    "value": 0,
                }
            ]
    if disable_actions:
        for action in scenario_raw["action_rules"]:
            action["available_when"] = [
                {
                    "kind": "state",
                    "variable_id": "engineering_knowledge",
                    "operator": "gt",
                    "value": 100,
                }
            ]
    if clamp_effects:
        survey = next(
            item
            for item in scenario_raw["action_rules"]
            if item["action_id"] == "survey-terrain"
        )
        for effect in survey["effects"]:
            if effect["variable_id"] == "flood_risk":
                effect["value"] = -1000
            if effect["variable_id"] == "engineering_knowledge":
                effect["value"] = 1000
        explain = next(
            item
            for item in scenario_raw["action_rules"]
            if item["action_id"] == "explain-plan"
        )
        npc_effect = next(
            effect
            for effect in explain["effects"]
            if effect["kind"] == "npc"
        )
        npc_effect["attitude_delta"] = 1000
        npc_effect["trust_delta"] = 1000
    scenario_raw["checksum"] = "0" * 64
    provisional_scenario = ScenarioTemplateV1.model_validate(scenario_raw)
    scenario_raw["checksum"] = calculate_contract_checksum(provisional_scenario)
    scenario = ScenarioTemplateV1.model_validate(scenario_raw)

    course_raw = bundle.course.model_dump(mode="python")
    course_raw["scenario_refs"][0]["checksum"] = scenario.checksum
    course_raw["checksum"] = "0" * 64
    provisional_course = CoursePackageV1.model_validate(course_raw)
    course_raw["checksum"] = calculate_contract_checksum(provisional_course)
    course = CoursePackageV1.model_validate(course_raw)
    return course, scenario


if __name__ == "__main__":
    unittest.main()
