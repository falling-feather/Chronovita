from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from services.contracts.evidence_v1 import EvidencePassageV1, EvidenceSourceV1, evidence_schema_document, sign_evidence_contract, verify_evidence_checksum
from services.contracts.evidence_v2 import EVIDENCE_V2_SCHEMA_DOCUMENTS, EvidenceAnswerSlotV1, EvidenceBoundaryV1, EvidenceCorpusV2, EvidencePassageV2, parse_evidence_corpus
from services import content
from services.content import runtime_artifacts
from services.rag.retrieval import RetrievedPassage
from services.rag.service import _passage_locator


def corpus() -> EvidenceCorpusV2:
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    return sign_evidence_contract(EvidenceCorpusV2(
        corpus_id="evidence-L101-v2", course_id="C-prequin-state", lesson_id="L101",
        corpus_version=2, title="正式证据库", scope_note="仅回答课程边界内问题。",
        supersedes_checksum="1" * 64,
        sources=(EvidenceSourceV1(source_id="src-001", title="来源", kind="research", url_or_path="local", rights_note="自写摘要。"),),
        boundaries=(EvidenceBoundaryV1(boundary_id="bound-001", label="边界", category="claim_limit", statement="不得超出材料断言。"),),
        answer_slots=(EvidenceAnswerSlotV1(slot_id="slot-001", label="主题", status="supported", response_mode="topic", term_groups=(("治水",),), passage_ids=("pass-001",), boundary_ids=("bound-001",)),),
        passages=(EvidencePassageV2(passage_id="pass-001", source_id="src-001", title="材料", text="这是一条可以独立引用并核验的正式课程证据片段。", summary="课程证据摘要。", source_locator="第1节", keywords=("治水",), answer_slot_ids=("slot-001",), boundary_ids=("bound-001",), evidence_kind="scholarly_interpretation", certainty="interpretation", chronology_note="现代研究。"),),
        created_at=now, sealed_at=now, sealed_by="reviewer", checksum="0" * 64,
    ))


class EvidenceV2ContractTests(unittest.TestCase):
    def test_committed_v2_schema_matches_model_without_stale_files(self):
        schema_dir = Path(__file__).resolve().parents[1] / "content" / "schemas" / "evidence" / "v2"
        for filename, (model, schema_id) in EVIDENCE_V2_SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    json.loads((schema_dir / filename).read_text(encoding="utf-8")),
                    evidence_schema_document(model, schema_id),
                )
        self.assertEqual(
            {path.name for path in schema_dir.glob("*.json")},
            set(EVIDENCE_V2_SCHEMA_DOCUMENTS),
        )

    def test_v2_checksum_and_discriminated_read(self):
        item = corpus()
        self.assertTrue(verify_evidence_checksum(item))
        self.assertEqual(
            parse_evidence_corpus(item.model_dump(mode="json")),
            item,
        )
        self.assertFalse(
            verify_evidence_checksum(item.model_copy(update={"title": "tampered"}))
        )

    def test_v2_cross_references_and_unsupported_policy_fail_closed(self):
        raw = corpus().model_dump(mode="json")
        raw["passages"][0]["answer_slot_ids"] = ["missing-slot"]
        with self.assertRaisesRegex(ValidationError, "unknown slot"):
            EvidenceCorpusV2.model_validate(raw)
        with self.assertRaisesRegex(ValidationError, "cannot allow API"):
            EvidenceAnswerSlotV1(
                slot_id="slot-x",
                label="拒答",
                status="unsupported",
                response_mode="boundary",
                term_groups=(("天文",),),
                boundary_ids=("bound-001",),
                api_synthesis_allowed=True,
            )

    def test_persona_scope_is_explicit(self):
        raw = corpus().passages[0].model_dump(mode="json")
        raw.update(persona_scope="expert_and_listed_people", person_ids=[])
        with self.assertRaisesRegex(ValidationError, "require person_ids"):
            EvidencePassageV2.model_validate(raw)

    def test_api_slots_require_diverse_grounding(self):
        raw = corpus().model_dump(mode="json")
        raw["answer_slots"][0]["api_synthesis_allowed"] = True
        with self.assertRaisesRegex(ValidationError, "at least three passages"):
            EvidenceCorpusV2.model_validate(raw)

    def test_api_slots_require_an_explicit_boundary(self):
        raw = corpus().model_dump(mode="json")
        raw["answer_slots"][0]["api_synthesis_allowed"] = True
        raw["answer_slots"][0]["boundary_ids"] = []
        with self.assertRaisesRegex(ValidationError, "at least one boundary"):
            EvidenceCorpusV2.model_validate(raw)

    def test_persona_passages_require_persona_knowledge_boundary(self):
        raw = corpus().model_dump(mode="json")
        raw["passages"][0]["persona_scope"] = "expert_and_listed_people"
        raw["passages"][0]["person_ids"] = ["person-yu"]
        with self.assertRaisesRegex(ValidationError, "persona_knowledge"):
            EvidenceCorpusV2.model_validate(raw)

    def test_v2_atomic_locator_overrides_source_fallback(self):
        item = corpus()
        source = item.sources[0].model_copy(update={"locator": "来源级定位"})
        common = {
            "source": source,
            "score": 1.0,
            "relevance": 1.0,
            "lexical_rank": 1,
            "vector_rank": None,
            "matched_signal_count": 1,
            "query_signal_coverage": 1.0,
            "vector_similarity": None,
        }
        v2 = RetrievedPassage(passage=item.passages[0], **common)
        self.assertEqual(_passage_locator(v2), "第1节")

        v1_passage = EvidencePassageV1(
            passage_id="pass-v1",
            source_id=source.source_id,
            title="旧片段",
            text="旧版片段继续使用来源级定位。",
            summary="旧版摘要。",
            evidence_kind="teaching_explanation",
            certainty="interpretation",
            chronology_note="测试。",
        )
        v1 = RetrievedPassage(passage=v1_passage, **common)
        self.assertEqual(_passage_locator(v1), "来源级定位")

    def test_v2_runtime_is_content_addressed_and_tampering_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            content.configure(Path(temp_dir))
            try:
                item = corpus()
                record = runtime_artifacts.stage_evidence_corpus(item)
                self.assertEqual(
                    record.descriptor.schema_version,
                    "evidence-corpus/v2",
                )
                self.assertTrue(
                    record.descriptor.path.startswith("runtime/v2/evidence/")
                )
                self.assertEqual(
                    runtime_artifacts.load_release_evidence(record.descriptor),
                    item,
                )
                target = content.content_root() / record.descriptor.path
                target.write_text(
                    target.read_text(encoding="utf-8").replace(
                        "正式证据库",
                        "篡改证据库",
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(runtime_artifacts.RuntimeArtifactError):
                    runtime_artifacts.load_release_evidence(record.descriptor)
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
