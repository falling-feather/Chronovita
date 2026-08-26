from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.content import workflow
from services.rag.query import QUERY_PLANNER_VERSION, plan_rag_query
from services.rag.retrieval import FastEmbedVectorizer, HybridEvidenceRetriever


DEFAULT_FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "rag_natural_benchmark_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate published-lesson RAG retrieval against a JSON benchmark.",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--index-path", type=Path)
    parser.add_argument("--vector-model-root", type=Path)
    parser.add_argument("--min-hit-rate", type=float, default=0.90)
    parser.add_argument("--min-support-rate", type=float, default=0.90)
    return parser.parse_args()


def evaluate(args: argparse.Namespace, *, index_path: Path) -> dict:
    benchmark = json.loads(args.fixture.read_text(encoding="utf-8"))
    vectorizer = (
        FastEmbedVectorizer(args.vector_model_root)
        if args.vector_model_root is not None
        else None
    )
    retriever = HybridEvidenceRetriever(index_path, vectorizer=vectorizer)
    resources_by_lesson = {}
    hits = 0
    supported = 0
    vector_cases = 0
    misses = []
    unsupported = []

    for case in benchmark["cases"]:
        lesson_id = case["lesson_id"]
        resources = resources_by_lesson.get(lesson_id)
        if resources is None:
            resources = workflow.get_published_lesson_resources(
                "C-prequin-state",
                lesson_id,
            )
            resources_by_lesson[lesson_id] = resources
        person = next(
            (
                candidate
                for candidate in resources.course_package.people
                if candidate.name == case.get("persona_name")
            ),
            None,
        )
        plan = plan_rag_query(resources, case["question"], person=person)
        result = retriever.retrieve_many(
            resources,
            plan.retrieval_queries,
            person_id=person.person_id if person is not None else None,
            limit=5,
        )
        actual = [item.passage.passage_id for item in result.passages]
        hit = bool(set(actual).intersection(case["expected_passage_ids"]))
        is_supported = result.supported or (
            plan.intent == "identity" and bool(result.passages)
        )
        hits += int(hit)
        supported += int(is_supported)
        vector_cases += int(result.vector_used)
        if not hit:
            misses.append(
                {
                    "lesson_id": lesson_id,
                    "question": case["question"],
                    "expected": case["expected_passage_ids"],
                    "actual": actual,
                    "queries": plan.retrieval_queries,
                }
            )
        if not is_supported:
            unsupported.append(
                {
                    "lesson_id": lesson_id,
                    "question": case["question"],
                    "queries": plan.retrieval_queries,
                }
            )

    total = len(benchmark["cases"])
    return {
        "ok": hits / total >= args.min_hit_rate
        and supported / total >= args.min_support_rate,
        "fixture": str(args.fixture),
        "schema_version": benchmark["schema_version"],
        "query_planner_version": QUERY_PLANNER_VERSION,
        "cases": total,
        "top5_hits": hits,
        "top5_hit_rate": hits / total,
        "supported": supported,
        "support_rate": supported / total,
        "vector_cases": vector_cases,
        "misses": misses,
        "unsupported_questions": unsupported,
    }


def main() -> int:
    args = parse_args()
    if args.index_path is not None:
        report = evaluate(args, index_path=args.index_path)
    else:
        with tempfile.TemporaryDirectory(prefix="chronovita-rag-eval-") as temp_dir:
            report = evaluate(args, index_path=Path(temp_dir) / "rag.sqlite3")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
