from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from services.content import workflow
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.rag.query import plan_rag_query
from services.rag.retrieval import HybridEvidenceRetriever


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = REPO_ROOT / "tests" / "fixtures" / "rag_benchmark_l101_v2.json"


class RagBenchmarkL101V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        cls.release = workflow.get_current_release("C-prequin-state")
        cls.resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            "L101",
        )

    def test_fixture_is_scoped_to_current_release_seven_and_exact_v2_ids(self) -> None:
        benchmark = self.benchmark
        release = self.release
        resources = self.resources
        self.assertIsNotNone(release)
        self.assertEqual(release.schema_version, "course-release/v5")
        self.assertEqual(release.release_no, 7)
        self.assertEqual(release.release_id, "rel-28b5624648-0007")
        self.assertEqual(resources.release_id, release.release_id)
        self.assertEqual(resources.release_checksum, release.checksum)
        self.assertIsInstance(resources.evidence_corpus, EvidenceCorpusV2)

        self.assertEqual(benchmark["schema_version"], "rag-benchmark-l101/v2")
        self.assertEqual(benchmark["course_id"], resources.course_id)
        self.assertEqual(benchmark["lesson_id"], resources.lesson_id)
        self.assertEqual(benchmark["release_no"], resources.release_no)
        self.assertEqual(len(benchmark["cases"]), 60)
        self.assertEqual(
            len({item["case_id"] for item in benchmark["cases"]}),
            60,
        )
        self.assertEqual(
            len({item["question"] for item in benchmark["cases"]}),
            60,
        )

        passage_ids = {
            item.passage_id for item in resources.evidence_corpus.passages
        }
        slots = {
            item.slot_id: item for item in resources.evidence_corpus.answer_slots
        }
        supported_slots = {
            item.slot_id
            for item in resources.evidence_corpus.answer_slots
            if item.status == "supported"
        }
        self.assertEqual(
            {item["slot_id"] for item in benchmark["cases"]},
            supported_slots,
        )
        for slot_id in supported_slots:
            self.assertEqual(
                sum(item["slot_id"] == slot_id for item in benchmark["cases"]),
                6,
                slot_id,
            )
        for item in benchmark["cases"]:
            expected = set(item["expected_passage_ids"])
            self.assertTrue(expected, item["case_id"])
            self.assertTrue(expected.issubset(passage_ids), item["case_id"])
            self.assertTrue(
                expected.intersection(slots[item["slot_id"]].passage_ids),
                item["case_id"],
            )

        normalized_titles = {
            item.title.strip("？?。！!")
            for item in resources.evidence_corpus.passages
        }
        self.assertTrue(
            all(
                item["question"].strip("？?。！!") not in normalized_titles
                for item in benchmark["cases"]
            )
        )

    def test_release_seven_fts_places_exact_v2_evidence_in_top_five(self) -> None:
        with tempfile.TemporaryDirectory(prefix="chronovita-l101-v2-benchmark-") as temp_dir:
            retriever = HybridEvidenceRetriever(Path(temp_dir) / "rag.sqlite3")
            hits = 0
            misses: list[dict[str, object]] = []
            for item in self.benchmark["cases"]:
                plan = plan_rag_query(self.resources, item["question"])
                result = retriever.retrieve_many(
                    self.resources,
                    plan.retrieval_queries,
                    limit=5,
                )
                self.assertFalse(result.vector_used, item["case_id"])
                actual = [
                    candidate.passage.passage_id
                    for candidate in result.passages
                ]
                if set(actual).intersection(item["expected_passage_ids"]):
                    hits += 1
                else:
                    misses.append(
                        {
                            "case_id": item["case_id"],
                            "question": item["question"],
                            "expected": item["expected_passage_ids"],
                            "actual": actual,
                            "queries": plan.retrieval_queries,
                        }
                    )
            hit_rate = hits / len(self.benchmark["cases"])
            self.assertGreaterEqual(hit_rate, 0.90, misses)


if __name__ == "__main__":
    unittest.main()
