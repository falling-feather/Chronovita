from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone

from services.content.flagships.dayu_l101 import build_dayu_evidence_draft
from services.content.flagships.dayu_l101_evidence_v2 import (
    DAYU_V1_CHECKSUM,
    build_dayu_evidence_v2,
)
from services.contracts.evidence_v1 import verify_evidence_checksum


class DayuEvidenceV2ContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = build_dayu_evidence_v2(
            sealed_by="content-test",
            sealed_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        )

    def test_preserves_v1_ids_and_delivers_formal_depth(self):
        corpus = self.corpus
        self.assertEqual(corpus.schema_version, "evidence-corpus/v2")
        self.assertEqual(corpus.supersedes_checksum, DAYU_V1_CHECKSUM)
        self.assertEqual(
            [item.passage_id for item in corpus.passages],
            [f"dayu-p{index:03d}" for index in range(1, 49)],
        )
        self.assertEqual(
            [item.passage_id for item in corpus.passages[:30]],
            [item.passage_id for item in build_dayu_evidence_draft().passages],
        )
        all_passage_text = "".join(item.text for item in corpus.passages)
        self.assertGreaterEqual(len(all_passage_text), 6000)
        self.assertGreaterEqual(len(re.findall(r"[\u3400-\u9fff]", all_passage_text)), 6000)
        self.assertTrue(all(len(item.source_locator) >= 12 for item in corpus.passages))
        self.assertTrue(all(item.fact_ids for item in corpus.passages))
        self.assertTrue(verify_evidence_checksum(corpus))

    def test_corpus_covers_all_evidence_layers_and_registered_sources(self):
        corpus = self.corpus
        self.assertEqual(len(corpus.sources), 12)
        self.assertEqual(
            {item.evidence_kind for item in corpus.passages},
            {
                "archaeological_evidence",
                "boundary_note",
                "curriculum_goal",
                "scholarly_interpretation",
                "teaching_explanation",
                "transmitted_text",
            },
        )
        self.assertEqual(
            {item.reliability for item in corpus.sources},
            {"disputed", "reviewed"},
        )
        serialized = corpus.model_dump_json()
        for required in (
            "传世文献",
            "自然科学",
            "考古",
            "教学解释",
            "局地洪水不能独证大禹治水",
            "人物仅在已发布知识边界内发言",
        ):
            self.assertIn(required, serialized)
        for forbidden in ("技术占位", "placeholder", "教师待审"):
            self.assertNotIn(forbidden, serialized)

    def test_answer_slots_are_closed_reciprocal_and_api_ready(self):
        corpus = self.corpus
        passages = {item.passage_id: item for item in corpus.passages}
        supported = [item for item in corpus.answer_slots if item.status == "supported"]
        unsupported = [item for item in corpus.answer_slots if item.status == "unsupported"]
        self.assertGreaterEqual(len(supported), 8)
        self.assertGreaterEqual(len(unsupported), 1)

        expected_pairs = {
            (slot.slot_id, passage_id)
            for slot in supported
            for passage_id in slot.passage_ids
        }
        actual_pairs = {
            (slot_id, passage.passage_id)
            for passage in corpus.passages
            for slot_id in passage.answer_slot_ids
        }
        self.assertEqual(actual_pairs, expected_pairs)

        for slot in supported:
            self.assertTrue(slot.passage_ids)
            bound = [passages[item] for item in slot.passage_ids]
            available_boundaries = {
                boundary_id for passage in bound for boundary_id in passage.boundary_ids
            }
            self.assertTrue(set(slot.boundary_ids).issubset(available_boundaries))
            if slot.api_synthesis_allowed:
                self.assertGreaterEqual(len(bound), 3)
                self.assertGreaterEqual(len({item.source_id for item in bound}), 2)
                self.assertGreaterEqual(len({item.evidence_kind for item in bound}), 2)

        for slot in unsupported:
            self.assertFalse(slot.passage_ids)
            self.assertFalse(slot.api_synthesis_allowed)
            self.assertTrue(slot.boundary_ids)

    def test_persona_scope_never_grants_unlisted_people_access(self):
        for passage in self.corpus.passages:
            if passage.persona_scope == "expert_only":
                self.assertFalse(passage.person_ids)
            else:
                self.assertEqual(passage.persona_scope, "expert_and_listed_people")
                self.assertTrue(passage.person_ids)
                self.assertIn(
                    "dayu-b-persona",
                    passage.boundary_ids,
                    passage.passage_id,
                )

        persona_boundaries = {
            item.boundary_id
            for item in self.corpus.boundaries
            if item.category == "persona_knowledge"
        }
        self.assertEqual(persona_boundaries, {"dayu-b-persona"})


if __name__ == "__main__":
    unittest.main()
