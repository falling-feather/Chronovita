from __future__ import annotations

import json
import unittest

from services.content.flagships.shangyang_l103 import build_shangyang_evidence_draft
from services.content.flagships.shangyang_l103_evidence_v2 import (
    SHANGYANG_V1_CHECKSUM,
    build_shangyang_evidence_v2,
)
from services.contracts.evidence_v1 import verify_evidence_checksum


class ShangyangEvidenceV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v1 = build_shangyang_evidence_draft()
        cls.corpus = build_shangyang_evidence_v2()

    def test_v2_preserves_stable_ids_and_reaches_formal_content_depth(self) -> None:
        corpus = self.corpus
        self.assertEqual(corpus.schema_version, "evidence-corpus/v2")
        self.assertEqual(corpus.corpus_version, 2)
        self.assertEqual(corpus.supersedes_checksum, SHANGYANG_V1_CHECKSUM)
        self.assertTrue(verify_evidence_checksum(corpus))
        self.assertEqual(len(corpus.sources), 10)
        self.assertEqual(len(corpus.passages), 48)
        self.assertEqual(
            [item.passage_id for item in corpus.passages],
            [f"shangyang-p{index:03d}" for index in range(1, 49)],
        )

        v2_by_id = {item.passage_id: item for item in corpus.passages}
        for v1_passage in self.v1.passages:
            self.assertIn(v1_passage.passage_id, v2_by_id)
            self.assertTrue(
                v2_by_id[v1_passage.passage_id].text.startswith(v1_passage.text),
                v1_passage.passage_id,
            )

        formal_characters = sum(
            len(item.text) + len(item.summary) for item in corpus.passages
        )
        self.assertGreaterEqual(formal_characters, 6000)
        self.assertTrue(all(item.source_locator for item in corpus.passages))
        self.assertTrue(all(item.answer_slot_ids for item in corpus.passages))
        self.assertTrue(all(item.boundary_ids for item in corpus.passages))

    def test_answer_slots_are_closed_and_api_slots_have_diverse_grounding(self) -> None:
        corpus = self.corpus
        supported = [item for item in corpus.answer_slots if item.status == "supported"]
        unsupported = [
            item for item in corpus.answer_slots if item.status == "unsupported"
        ]
        self.assertGreaterEqual(len(supported), 12)
        self.assertGreaterEqual(len(unsupported), 1)

        passages = {item.passage_id: item for item in corpus.passages}
        for slot in supported:
            self.assertTrue(slot.passage_ids, slot.slot_id)
            for passage_id in slot.passage_ids:
                self.assertIn(slot.slot_id, passages[passage_id].answer_slot_ids)
            if slot.api_synthesis_allowed:
                grounded = [passages[passage_id] for passage_id in slot.passage_ids]
                self.assertGreaterEqual(len(grounded), 3, slot.slot_id)
                self.assertGreaterEqual(
                    len({item.source_id for item in grounded}),
                    2,
                    slot.slot_id,
                )
                self.assertGreaterEqual(
                    len({item.evidence_kind for item in grounded}),
                    2,
                    slot.slot_id,
                )

        for slot in unsupported:
            self.assertFalse(slot.passage_ids)
            self.assertFalse(slot.api_synthesis_allowed)
            self.assertTrue(slot.boundary_ids)

    def test_boundaries_and_persona_scope_cover_required_historical_layers(self) -> None:
        corpus = self.corpus
        boundary_ids = {item.boundary_id for item in corpus.boundaries}
        self.assertEqual(len(corpus.boundaries), 11)
        self.assertIn("shangyang-boundary-01-transmitted-distance", boundary_ids)
        self.assertIn("shangyang-boundary-03-fangsheng-claim", boundary_ids)
        self.assertIn("shangyang-boundary-04-slips-distance", boundary_ids)
        self.assertIn("shangyang-boundary-05-shangjunshu-authorship", boundary_ids)
        self.assertIn("shangyang-boundary-06-modern-rule-of-law", boundary_ids)
        self.assertIn("shangyang-boundary-09-persona-hindsight", boundary_ids)

        for passage in corpus.passages:
            if passage.person_ids:
                self.assertEqual(
                    passage.persona_scope,
                    "expert_and_listed_people",
                    passage.passage_id,
                )
                self.assertIn(
                    "shangyang-boundary-09-persona-hindsight",
                    passage.boundary_ids,
                    passage.passage_id,
                )
            else:
                self.assertEqual(
                    passage.persona_scope,
                    "expert_only",
                    passage.passage_id,
                )

        serialized = json.dumps(corpus.model_dump(mode="json"), ensure_ascii=False)
        for required in (
            "《史记·商君列传》",
            "西汉",
            "商鞅方升",
            "公元前344年",
            "睡虎地秦简",
            "晚于商鞅最初变法百余年",
            "《韩非子·定法》",
            "后世评价",
            "《商君书》",
            "累积文本",
            "现代法治",
            "角色化教学表达",
            "依据不足",
        ):
            self.assertIn(required, serialized)

    def test_material_families_keep_distinct_sources_and_claim_limits(self) -> None:
        by_id = {item.passage_id: item for item in self.corpus.passages}
        self.assertEqual(
            by_id["shangyang-p012"].source_id,
            "src-shanghaimuseum-fangsheng",
        )
        self.assertEqual(
            by_id["shangyang-p012"].evidence_kind,
            "archaeological_evidence",
        )
        self.assertEqual(
            by_id["shangyang-p016"].source_id,
            "src-hb-archaeology-slips",
        )
        self.assertIn(
            "shangyang-boundary-04-slips-distance",
            by_id["shangyang-p016"].boundary_ids,
        )
        self.assertEqual(
            by_id["shangyang-p020"].source_id,
            "src-cambridge-shangjunshu",
        )
        self.assertIn(
            "shangyang-boundary-05-shangjunshu-authorship",
            by_id["shangyang-p020"].boundary_ids,
        )
        self.assertIn(
            "shangyang-boundary-06-modern-rule-of-law",
            by_id["shangyang-p048"].boundary_ids,
        )

    def test_unsupported_exact_data_slot_rejects_each_unpublished_number_family(self) -> None:
        slot = next(
            item
            for item in self.corpus.answer_slots
            if item.slot_id == "shangyang-slot-16-unsupported-exact-data"
        )
        self.assertEqual(slot.status, "unsupported")
        self.assertEqual(len(slot.term_groups), 1)
        self.assertFalse(slot.passage_ids)
        self.assertFalse(slot.api_synthesis_allowed)

        def matches(question: str) -> bool:
            return all(
                any(term in question for term in group)
                for group in slot.term_groups
            )

        for question in (
            "商鞅变法规定的具体税率是多少？",
            "军功爵造成的伤亡人数有多少？",
            "秦国农户每年需要承担多少徭役天数？",
            "能否给出某户的每户田亩精确数值？",
        ):
            self.assertTrue(matches(question), question)
        self.assertFalse(matches("商鞅方升铭文能够直接证明什么？"))


if __name__ == "__main__":
    unittest.main()
