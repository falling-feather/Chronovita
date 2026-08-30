import json
from pathlib import Path
import tempfile
import unittest

from services.content import workflow
from services.contracts.evidence_v1 import RagAskRequestV1
from services.rag.local_reply import fit_local_reply
from services.rag.query import plan_rag_query
from services.rag.retrieval import HybridEvidenceRetriever
from services.rag.routing import RAG_ROUTER_VERSION, route_rag_query


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "rag_route_benchmark_v1.json"
)
EXPECTED_CATEGORIES = {
    "local_template",
    "complex_api",
    "ambiguous_clarify",
    "unsupported_answer_slot",
    "off_topic_refuse",
    "false_premise_correction",
    "prompt_injection_refuse",
}


class RagRoutingBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        cls.resources = {
            lesson_id: workflow.get_published_lesson_resources(
                "C-prequin-state",
                lesson_id,
            )
            for lesson_id in ("L101", "L103")
        }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.retriever = HybridEvidenceRetriever(
            Path(self.temp_dir.name) / "rag-routing.sqlite3"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fixture_is_balanced_across_lessons_and_route_categories(self):
        self.assertEqual(
            self.benchmark["schema_version"],
            "rag-route-benchmark/v1",
        )
        cases = self.benchmark["cases"]
        self.assertEqual(len(cases), 38)
        self.assertEqual(len({item["id"] for item in cases}), len(cases))
        self.assertEqual({item["category"] for item in cases}, EXPECTED_CATEGORIES)
        for lesson_id in ("L101", "L103"):
            lesson_cases = [
                item for item in cases if item["lesson_id"] == lesson_id
            ]
            self.assertEqual(len(lesson_cases), 19)
            for category in EXPECTED_CATEGORIES - {"unsupported_answer_slot"}:
                self.assertEqual(
                    sum(item["category"] == category for item in lesson_cases),
                    3,
                    (lesson_id, category),
                )
            self.assertEqual(
                sum(
                    item["category"] == "unsupported_answer_slot"
                    for item in lesson_cases
                ),
                1,
            )

    def test_two_lesson_route_benchmark_matches_expected_targets(self):
        self.assertEqual(RAG_ROUTER_VERSION, "chronovita-rag-router/v1")
        failures = []
        for item in self.benchmark["cases"]:
            decision = self._decision_for(item)
            expected_targets = item.get(
                "expected_targets",
                [item.get("expected_target")],
            )
            if decision.target not in expected_targets:
                failures.append(
                    {
                        "id": item["id"],
                        "expected": expected_targets,
                        "actual": decision.target,
                        "reason": decision.reason,
                        "confidence": decision.evidence_confidence,
                        "complexity": decision.complexity_score,
                    }
                )
        self.assertEqual(failures, [])

    def test_only_complex_grounded_cases_can_reach_external_api(self):
        failures = []
        for item in self.benchmark["cases"]:
            decision = self._decision_for(item)
            max_api_calls = item.get(
                "max_api_calls",
                1 if item["category"] == "complex_api" else 0,
            )
            if decision.external_api_allowed != (max_api_calls == 1):
                failures.append(
                    (item["id"], decision.target, decision.reason)
                )
        self.assertEqual(failures, [])

    def test_route_decisions_are_deterministic(self):
        for item in self.benchmark["cases"]:
            first = self._decision_for(item)
            second = self._decision_for(item)
            self.assertEqual(first, second, item["id"])

    def _decision_for(self, item):
        resources = self.resources[item["lesson_id"]]
        person = next(
            (
                candidate
                for candidate in resources.course_package.people
                if candidate.name == item.get("persona_name")
            ),
            None,
        )
        request = RagAskRequestV1(
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            persona_mode="person" if person is not None else "expert",
            person_id=person.person_id if person is not None else None,
            question=item["question"],
        )
        plan = plan_rag_query(resources, item["question"], person=person)
        batch = self.retriever.retrieve_many(
            resources,
            plan.retrieval_queries,
            person_id=person.person_id if person is not None else None,
            limit=8,
        )
        local_fit = fit_local_reply(
            resources,
            request,
            person,
            plan,
            batch,
        )
        return route_rag_query(
            plan,
            batch,
            local_fit=local_fit,
            require_local_fit=True,
        )


if __name__ == "__main__":
    unittest.main()
