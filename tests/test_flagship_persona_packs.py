from __future__ import annotations

import json
import unittest
from pathlib import Path

from services.content.flagships.dayu_l101 import (
    build_dayu_course_draft,
    build_dayu_scenario_draft,
)
from services.content.flagships.dayu_l101_evidence_v2 import (
    build_dayu_evidence_v2,
)
from services.content.flagships.dayu_l101_persona_v1 import (
    build_dayu_persona_pack_v1,
)
from services.content.flagships.shangyang_l103 import (
    build_shangyang_course_draft,
    build_shangyang_scenario_draft,
)
from services.content.flagships.shangyang_l103_evidence_v2 import (
    build_shangyang_evidence_v2,
)
from services.content.flagships.shangyang_l103_persona_v1 import (
    build_shangyang_persona_pack_v1,
)
from services.contracts.persona_v1 import verify_persona_checksum
from services.contracts.v1 import course_package_from_legacy

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_POINTER = REPO_ROOT / "content" / "releases" / "active" / "C-prequin-state.json"

DAYU_KINDS = {
    "person-7c4825d9": "transmitted_memory",
    "person-b40a4965": "transmitted_memory",
    "person-31118bee": "transmitted_memory",
    "person-cef45322": "composite_group",
    "person-dc224fcf": "composite_group",
}
SHANGYANG_KINDS = {
    "person-c797c18e": "historical_person",
    "person-bd001399": "historical_person",
    "person-75b468fa": "composite_group",
    "person-a748c58d": "composite_group",
    "person-44990ad0": "composite_group",
    "person-829de766": "composite_group",
}


def _active_manifest() -> dict:
    pointer = json.loads(ACTIVE_POINTER.read_text(encoding="utf-8"))
    return json.loads(
        (REPO_ROOT / "content" / pointer["manifest_path"]).read_text(encoding="utf-8")
    )


class FlagshipPersonaPackTests(unittest.TestCase):
    def setUp(self):
        self.dayu_pack = build_dayu_persona_pack_v1()
        self.dayu_course = course_package_from_legacy(build_dayu_course_draft())
        self.dayu_scenario = build_dayu_scenario_draft()
        self.dayu_evidence = build_dayu_evidence_v2()

        self.shangyang_pack = build_shangyang_persona_pack_v1()
        self.shangyang_course = course_package_from_legacy(
            build_shangyang_course_draft()
        )
        self.shangyang_scenario = build_shangyang_scenario_draft()
        self.shangyang_evidence = build_shangyang_evidence_v2()

    def test_packs_are_deterministic_and_checksum_valid(self):
        for first, second in (
            (self.dayu_pack, build_dayu_persona_pack_v1()),
            (self.shangyang_pack, build_shangyang_persona_pack_v1()),
        ):
            with self.subTest(lesson_id=first.lesson_id):
                self.assertEqual(first, second)
                self.assertTrue(verify_persona_checksum(first))

    def test_profiles_cover_course_people_and_scenario_npcs(self):
        cases = (
            (
                self.dayu_pack,
                self.dayu_course,
                self.dayu_scenario,
                DAYU_KINDS,
            ),
            (
                self.shangyang_pack,
                self.shangyang_course,
                self.shangyang_scenario,
                SHANGYANG_KINDS,
            ),
        )
        for pack, course, scenario, expected_kinds in cases:
            with self.subTest(lesson_id=pack.lesson_id):
                profiles = {profile.person_id: profile for profile in pack.profiles}
                course_people = {person.person_id for person in course.people}
                scenario_people = {npc.person_id for npc in scenario.npcs}
                self.assertEqual(set(profiles), course_people)
                self.assertEqual(
                    {
                        person_id: profile.persona_kind
                        for person_id, profile in profiles.items()
                    },
                    expected_kinds,
                )
                self.assertTrue(scenario_people <= set(profiles))
                self.assertTrue(
                    all(
                        "scenario" in profiles[person_id].channels
                        for person_id in scenario_people
                    )
                )

        dayu_profiles = {
            profile.person_id: profile for profile in self.dayu_pack.profiles
        }
        self.assertEqual(dayu_profiles["person-b40a4965"].channels, ("consult",))
        self.assertEqual(
            {
                person_id
                for person_id, profile in dayu_profiles.items()
                if "scenario" in profile.channels
            },
            {npc.person_id for npc in self.dayu_scenario.npcs},
        )
        self.assertTrue(
            all(
                "scenario" in profile.channels
                for profile in self.shangyang_pack.profiles
            )
        )

    def test_profile_references_stay_inside_evidence_v2_persona_scope(self):
        for pack, corpus in (
            (self.dayu_pack, self.dayu_evidence),
            (self.shangyang_pack, self.shangyang_evidence),
        ):
            passages = {passage.passage_id: passage for passage in corpus.passages}
            slots = {slot.slot_id for slot in corpus.answer_slots}
            boundaries = {
                boundary.boundary_id: boundary for boundary in corpus.boundaries
            }
            for profile in pack.profiles:
                with self.subTest(
                    lesson_id=pack.lesson_id,
                    person_id=profile.person_id,
                ):
                    self.assertTrue(set(profile.focus_answer_slot_ids) <= slots)
                    self.assertTrue(set(profile.boundary_ids) <= set(boundaries))
                    self.assertIn(
                        "persona_knowledge",
                        {
                            boundaries[boundary_id].category
                            for boundary_id in profile.boundary_ids
                        },
                    )
                    for evidence_use in profile.evidence_uses:
                        passage = passages[evidence_use.passage_id]
                        self.assertEqual(
                            passage.persona_scope,
                            "expert_and_listed_people",
                        )
                        self.assertIn(profile.person_id, passage.person_ids)
                        self.assertTrue(
                            any(
                                boundaries[boundary_id].category == "persona_knowledge"
                                for boundary_id in passage.boundary_ids
                            )
                        )

    def test_role_voice_excludes_archaeology_research_and_boundary_notes(self):
        safe_role_voice_kinds = {"transmitted_text", "teaching_explanation"}
        for pack, corpus in (
            (self.dayu_pack, self.dayu_evidence),
            (self.shangyang_pack, self.shangyang_evidence),
        ):
            passages = {passage.passage_id: passage for passage in corpus.passages}
            for profile in pack.profiles:
                for evidence_use in profile.evidence_uses:
                    if evidence_use.mode != "role_voice":
                        continue
                    passage = passages[evidence_use.passage_id]
                    with self.subTest(
                        lesson_id=pack.lesson_id,
                        person_id=profile.person_id,
                        passage_id=passage.passage_id,
                    ):
                        self.assertIn(passage.evidence_kind, safe_role_voice_kinds)
                        if passage.evidence_kind == "teaching_explanation":
                            self.assertEqual(profile.persona_kind, "composite_group")

    def test_packs_pin_the_active_release_eight_artifacts(self):
        manifest = _active_manifest()
        self.assertEqual(manifest["schema_version"], "course-release/v5")
        self.assertEqual(manifest["release_no"], 8)
        items = {item["lesson_id"]: item for item in manifest["items"]}
        for pack in (self.dayu_pack, self.shangyang_pack):
            item = items[pack.lesson_id]
            scenario = next(
                descriptor
                for descriptor in item["scenarios"]
                if descriptor["artifact_id"] == pack.scenario_id
            )
            self.assertEqual(
                pack.course_content_version, item["course_package"]["version"]
            )
            self.assertEqual(pack.course_checksum, item["course_package"]["checksum"])
            self.assertEqual(pack.scenario_version, scenario["version"])
            self.assertEqual(pack.scenario_checksum, scenario["checksum"])
            self.assertEqual(pack.evidence_version, item["evidence_corpus"]["version"])
            self.assertEqual(
                pack.evidence_checksum, item["evidence_corpus"]["checksum"]
            )

    def test_shangyang_bindings_cover_every_node_action_route(self):
        expected_routes = {
            (node.node_id, action_id)
            for node in self.shangyang_scenario.nodes
            for action_id in node.action_ids
        }
        actual_routes = {
            (binding.node_id, binding.action_id)
            for binding in self.shangyang_pack.scenario_voice_bindings
        }
        self.assertEqual(actual_routes, expected_routes)
        self.assertEqual(
            {
                binding.person_id
                for binding in self.shangyang_pack.scenario_voice_bindings
            },
            {npc.person_id for npc in self.shangyang_scenario.npcs},
        )

    def test_dayu_bindings_cover_every_global_rule_action(self):
        self.assertEqual(self.dayu_scenario.nodes, [])
        self.assertEqual(
            {
                (binding.node_id, binding.action_id)
                for binding in self.dayu_pack.scenario_voice_bindings
            },
            {
                ("global-rule-set", action.action_id)
                for action in self.dayu_scenario.action_rules
            },
        )
        self.assertEqual(
            {binding.person_id for binding in self.dayu_pack.scenario_voice_bindings},
            {npc.person_id for npc in self.dayu_scenario.npcs},
        )


if __name__ == "__main__":
    unittest.main()
