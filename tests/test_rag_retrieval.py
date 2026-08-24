import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.content import workflow
from services.contracts.evidence_v1 import EvidenceCorpusV1
from services.rag.retrieval import (
    EvidenceIntegrityError,
    HybridEvidenceRetriever,
)
from services.rag.query import plan_rag_query


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = REPO_ROOT / "tests" / "fixtures" / "rag_benchmark_v1.json"
NATURAL_BENCHMARK_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "rag_natural_benchmark_v1.json"
)


class _DeterministicVectorizer:
    model_id = "test/hash-vector-v1"
    dimension = 8

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.passage_calls = 0

    def embed_passages(self, texts):
        self.passage_calls += 1
        return [self._embed(value) for value in texts]

    def embed_query(self, text):
        return self._embed(text)

    def _embed(self, value):
        totals = [0.0] * self.dimension
        for index, char in enumerate(value):
            totals[(ord(char) + index) % self.dimension] += 1.0
        norm = sum(item * item for item in totals) ** 0.5 or 1.0
        return tuple(item / norm for item in totals)


class RagRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.index_path = Path(self.temp_dir.name) / "rag.sqlite3"
        self.resources = {
            lesson_id: workflow.get_published_lesson_resources(
                "C-prequin-state",
                lesson_id,
            )
            for lesson_id in ("L101", "L103")
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_40_question_fts_benchmark_has_top_five_hit_rate_above_90_percent(self):
        benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(benchmark["schema_version"], "rag-benchmark/v1")
        self.assertEqual(len(benchmark["cases"]), 40)
        self.assertEqual(
            {item["lesson_id"] for item in benchmark["cases"]},
            {"L101", "L103"},
        )
        self.assertEqual(
            [item["lesson_id"] for item in benchmark["cases"]].count("L101"),
            20,
        )
        retriever = HybridEvidenceRetriever(self.index_path)
        hits = 0
        missed = []
        for item in benchmark["cases"]:
            result = retriever.retrieve(
                self.resources[item["lesson_id"]],
                item["question"],
                limit=5,
            )
            actual = {entry.passage.passage_id for entry in result.passages}
            if actual.intersection(item["expected_passage_ids"]):
                hits += 1
            else:
                missed.append((item["question"], sorted(actual)))
        self.assertGreaterEqual(
            hits / len(benchmark["cases"]),
            0.90,
            missed,
        )

    def test_40_natural_questions_have_top_five_hit_and_support_above_90_percent(self):
        benchmark = json.loads(NATURAL_BENCHMARK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            benchmark["schema_version"],
            "rag-natural-benchmark/v1",
        )
        self.assertEqual(len(benchmark["cases"]), 40)
        self.assertEqual(
            [item["lesson_id"] for item in benchmark["cases"]].count("L101"),
            20,
        )
        retriever = HybridEvidenceRetriever(self.index_path)
        hits = 0
        supported = 0
        missed = []
        unsupported = []
        for item in benchmark["cases"]:
            resources = self.resources[item["lesson_id"]]
            person = next(
                (
                    candidate
                    for candidate in resources.course_package.people
                    if candidate.name == item.get("persona_name")
                ),
                None,
            )
            plan = plan_rag_query(
                resources,
                item["question"],
                person=person,
            )
            result = retriever.retrieve_many(
                resources,
                plan.retrieval_queries,
                person_id=person.person_id if person is not None else None,
                limit=5,
            )
            actual = {entry.passage.passage_id for entry in result.passages}
            if actual.intersection(item["expected_passage_ids"]):
                hits += 1
            else:
                missed.append((item["question"], sorted(actual), plan.retrieval_queries))
            if result.supported or (plan.intent == "identity" and result.passages):
                supported += 1
            else:
                unsupported.append((item["question"], plan.retrieval_queries))
        self.assertGreaterEqual(hits / len(benchmark["cases"]), 0.90, missed)
        self.assertGreaterEqual(
            supported / len(benchmark["cases"]),
            0.90,
            unsupported,
        )

    def test_index_is_scoped_by_release_and_rebuilds_corrupted_derived_rows(self):
        retriever = HybridEvidenceRetriever(self.index_path)
        first = retriever.retrieve(
            self.resources["L101"],
            "二里头遗址与夏史有什么关系？",
            limit=5,
        )
        second = retriever.retrieve(
            self.resources["L103"],
            "商鞅方升能直接证明什么？",
            limit=5,
        )
        self.assertNotEqual(first.scope_key, second.scope_key)
        self.assertTrue(all(item.passage.passage_id.startswith("dayu-") for item in first.passages))
        self.assertTrue(all(item.passage.passage_id.startswith("shangyang-") for item in second.passages))

        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute(
                "DELETE FROM rag_passages WHERE scope_key = ? AND passage_id = ?",
                (first.scope_key, first.passages[0].passage.passage_id),
            )
            connection.commit()
        finally:
            connection.close()
        rebuilt = retriever.retrieve(
            self.resources["L101"],
            "二里头遗址与夏史有什么关系？",
            limit=5,
        )
        self.assertEqual(rebuilt.passages[0].passage.passage_id, first.passages[0].passage.passage_id)

        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute(
                """
                UPDATE rag_passages_fts SET body = ?
                WHERE scope_key = ? AND passage_id = ?
                """,
                ("b_伪造 b_缓存", first.scope_key, first.passages[0].passage.passage_id),
            )
            connection.commit()
        finally:
            connection.close()
        repaired_content = retriever.retrieve(
            self.resources["L101"],
            "二里头遗址与夏史有什么关系？",
            limit=5,
        )
        self.assertEqual(
            repaired_content.passages[0].passage.passage_id,
            first.passages[0].passage.passage_id,
        )
        connection = sqlite3.connect(self.index_path)
        try:
            stored_body = connection.execute(
                """
                SELECT body FROM rag_passages_fts
                WHERE scope_key = ? AND passage_id = ?
                """,
                (first.scope_key, first.passages[0].passage.passage_id),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertNotEqual(stored_body, "b_伪造 b_缓存")

    def test_truncated_sqlite_cache_is_replaced_from_sealed_evidence(self):
        retriever = HybridEvidenceRetriever(self.index_path)
        first = retriever.retrieve(
            self.resources["L101"],
            "二里头遗址与夏史有什么关系？",
            limit=5,
        )
        self.assertTrue(first.passages)
        self.index_path.write_bytes(b"not-a-sqlite-database")

        repaired = retriever.retrieve(
            self.resources["L101"],
            "二里头遗址与夏史有什么关系？",
            limit=5,
        )
        self.assertTrue(repaired.passages)
        connection = sqlite3.connect(self.index_path)
        try:
            self.assertEqual(
                connection.execute("PRAGMA quick_check").fetchone()[0],
                "ok",
            )
        finally:
            connection.close()

    def test_vector_cache_and_rrf_fusion_are_reused(self):
        vectorizer = _DeterministicVectorizer()
        retriever = HybridEvidenceRetriever(self.index_path, vectorizer=vectorizer)
        first = retriever.retrieve(
            self.resources["L101"],
            "积石峡洪水如何连接夏史推论？",
            limit=8,
        )
        second = retriever.retrieve(
            self.resources["L101"],
            "禹迹图是什么年代的地图？",
            limit=8,
        )
        self.assertTrue(first.vector_used)
        self.assertTrue(any(item.lexical_rank and item.vector_rank for item in first.passages))
        self.assertEqual(vectorizer.passage_calls, 1)
        self.assertTrue(second.vector_used)

        connection = sqlite3.connect(self.index_path)
        try:
            connection.execute(
                """
                UPDATE rag_passages SET vector = ?
                WHERE scope_key = ? AND passage_id = ?
                """,
                (b"broken-vector", first.scope_key, first.passages[0].passage.passage_id),
            )
            connection.commit()
        finally:
            connection.close()
        repaired = retriever.retrieve(
            self.resources["L101"],
            "积石峡洪水如何连接夏史推论？",
            limit=8,
        )
        self.assertTrue(repaired.vector_used)
        self.assertEqual(vectorizer.passage_calls, 2)

    def test_multi_query_fuses_original_and_published_alias_rewrite(self):
        plan = plan_rag_query(
            self.resources["L101"],
            "考古真的挖到大禹名字了吗？",
        )
        result = HybridEvidenceRetriever(self.index_path).retrieve_many(
            self.resources["L101"],
            plan.retrieval_queries,
            limit=5,
        )
        self.assertTrue(result.supported)
        self.assertIn(
            "dayu-p026",
            {item.passage.passage_id for item in result.passages},
        )
        self.assertTrue(any(item.lexical_rank for item in result.passages))

    def test_missing_vector_model_falls_back_to_fts(self):
        vectorizer = _DeterministicVectorizer(available=False)
        result = HybridEvidenceRetriever(
            self.index_path,
            vectorizer=vectorizer,
        ).retrieve(
            self.resources["L103"],
            "睡虎地秦简为何不能全部署名商鞅？",
            limit=5,
        )
        self.assertFalse(result.vector_used)
        self.assertIn("shangyang-p016", {item.passage.passage_id for item in result.passages})

    def test_vector_similarity_alone_must_cross_the_support_threshold(self):
        class _ModerateSimilarityVectorizer:
            model_id = "test/moderate-vector-v1"
            dimension = 2
            available = True

            def embed_passages(self, texts):
                return [(0.8, 0.6) for _ in texts]

            def embed_query(self, _text):
                return (1.0, 0.0)

        result = HybridEvidenceRetriever(
            self.index_path,
            vectorizer=_ModerateSimilarityVectorizer(),
        ).retrieve(
            self.resources["L103"],
            "商鞅当时用手机给秦孝公发消息吗？",
            limit=5,
        )
        self.assertTrue(result.vector_used)
        self.assertFalse(result.supported)
        self.assertTrue(
            all(
                (item.vector_similarity or 0) < 0.82
                for item in result.passages
            )
        )

    def test_person_scope_only_returns_published_person_bindings(self):
        result = HybridEvidenceRetriever(self.index_path).retrieve(
            self.resources["L103"],
            "秦简为什么不能视为商鞅亲笔法令？",
            person_id="person-c797c18e",
            limit=8,
        )
        self.assertTrue(result.passages)
        self.assertTrue(
            all(
                "person-c797c18e" in item.passage.person_ids
                for item in result.passages
            )
        )

    def test_tampered_corpus_fails_before_index_access(self):
        tampered = self.resources["L101"].model_copy(
            update={
                "evidence_corpus": EvidenceCorpusV1.model_validate(
                    {
                        **self.resources["L101"].evidence_corpus.model_dump(mode="json"),
                        "title": "被篡改的证据库",
                    }
                )
            }
        )
        with self.assertRaises(EvidenceIntegrityError):
            HybridEvidenceRetriever(self.index_path).retrieve(
                tampered,
                "二里头遗址",
            )


if __name__ == "__main__":
    unittest.main()
