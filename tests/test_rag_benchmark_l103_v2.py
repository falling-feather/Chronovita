from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services.content import workflow
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.rag.query import plan_rag_query
from services.rag.retrieval import HybridEvidenceRetriever


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "rag_benchmark_l103_v2.json"
)
COURSE_ID = "C-prequin-state"
LESSON_ID = "L103"
EXPECTED_RELEASE_NO = 7
EXPECTED_CASE_COUNT = 60
MINIMUM_TOP_FIVE_HIT_RATE = 0.90


class RagBenchmarkL103V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        cls.release = workflow.get_current_release(COURSE_ID)
        cls.resources = workflow.get_published_lesson_resources(
            COURSE_ID,
            LESSON_ID,
        )

    def test_fixture_targets_release_seven_and_exact_v2_corpus(self) -> None:
        self.assertEqual(
            self.benchmark["schema_version"],
            "rag-benchmark-l103-v2/v1",
        )
        self.assertEqual(self.benchmark["course_id"], COURSE_ID)
        self.assertEqual(self.benchmark["lesson_id"], LESSON_ID)
        self.assertEqual(self.benchmark["release_no"], EXPECTED_RELEASE_NO)
        self.assertEqual(
            self.benchmark["evidence_schema_version"],
            "evidence-corpus/v2",
        )
        self.assertEqual(len(self.benchmark["cases"]), EXPECTED_CASE_COUNT)

        self.assertIsNotNone(self.release)
        assert self.release is not None
        self.assertEqual(self.release.schema_version, "course-release/v5")
        self.assertEqual(self.release.release_no, EXPECTED_RELEASE_NO)
        self.assertEqual(self.resources.release_no, EXPECTED_RELEASE_NO)
        self.assertEqual(self.resources.release_id, self.release.release_id)
        self.assertEqual(self.resources.release_checksum, self.release.checksum)
        self.assertIsInstance(self.resources.evidence_corpus, EvidenceCorpusV2)

        corpus = self.resources.evidence_corpus
        passage_ids = {passage.passage_id for passage in corpus.passages}
        supported_slots = {
            slot.slot_id
            for slot in corpus.answer_slots
            if slot.status == "supported"
        }
        case_slots = [case["slot_id"] for case in self.benchmark["cases"]]
        self.assertEqual(set(case_slots), supported_slots)
        self.assertTrue(
            all(case_slots.count(slot_id) == 4 for slot_id in supported_slots)
        )

        for case in self.benchmark["cases"]:
            with self.subTest(question=case["question"]):
                self.assertEqual(
                    set(case),
                    {"slot_id", "question", "expected_passage_ids"},
                )
                self.assertTrue(case["question"].strip())
                self.assertTrue(case["expected_passage_ids"])
                self.assertEqual(
                    len(case["expected_passage_ids"]),
                    len(set(case["expected_passage_ids"])),
                )
                self.assertTrue(
                    set(case["expected_passage_ids"]).issubset(passage_ids)
                )

    def test_release_seven_v2_fts_top_five_hit_rate_is_at_least_90_percent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            # No vectorizer is supplied: this benchmark exercises the offline
            # SQLite FTS path and the same deterministic query rewrites used by
            # the classroom ask service.
            retriever = HybridEvidenceRetriever(
                Path(temp_dir) / "rag-l103-v2-fts.sqlite3"
            )
            hits = 0
            misses: list[dict[str, object]] = []
            for case in self.benchmark["cases"]:
                plan = plan_rag_query(self.resources, case["question"])
                result = retriever.retrieve_many(
                    self.resources,
                    plan.retrieval_queries,
                    limit=5,
                )
                actual_ids = {
                    row.passage.passage_id for row in result.passages
                }
                self.assertFalse(result.vector_used)
                self.assertTrue(
                    actual_ids.issubset(
                        {
                            passage.passage_id
                            for passage in self.resources.evidence_corpus.passages
                        }
                    )
                )
                if actual_ids.intersection(case["expected_passage_ids"]):
                    hits += 1
                else:
                    misses.append(
                        {
                            "slot_id": case["slot_id"],
                            "question": case["question"],
                            "expected": case["expected_passage_ids"],
                            "actual_top_five": sorted(actual_ids),
                            "query_variants": plan.retrieval_queries,
                        }
                    )

        hit_rate = hits / len(self.benchmark["cases"])
        self.assertGreaterEqual(
            hit_rate,
            MINIMUM_TOP_FIVE_HIT_RATE,
            msg=json.dumps(
                {
                    "hits": hits,
                    "total": len(self.benchmark["cases"]),
                    "hit_rate": hit_rate,
                    "misses": misses,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )


if __name__ == "__main__":
    unittest.main()
