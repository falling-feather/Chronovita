import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from services.contracts.evidence_v1 import (
    EVIDENCE_SCHEMA_DOCUMENTS,
    EvidenceCorpusV1,
    EvidencePassageV1,
    EvidenceSourceV1,
    LessonPresentationV1,
    RagAnswerV1,
    RagAskRequestV1,
    RagCitationV1,
    evidence_schema_document,
    sign_evidence_contract,
    verify_evidence_checksum,
)
from services.contracts.release_examples import (
    build_dayu_release_manifest_v3,
    release_v3_example_documents,
)
from services.contracts.release_v2 import (
    CourseReleaseManifestV2,
    CourseReleaseManifestV3,
    RELEASE_V3_SCHEMA_DOCUMENTS,
    parse_signed_course_release_manifest,
    supplement_artifact_path,
    verify_release_metadata_checksum,
)


NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "evidence" / "v1"
RELEASE_V3_SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "releases" / "v3"
RELEASE_V3_EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "releases" / "v3"


def build_corpus() -> EvidenceCorpusV1:
    return sign_evidence_contract(
        EvidenceCorpusV1(
            corpus_id="evidence-L101-v1",
            course_id="C-prequin-state",
            lesson_id="L101",
            corpus_version=1,
            title="大禹治水证据库",
            scope_note="区分传说、传世文献、考古判断与教学解释。",
            sources=(
                EvidenceSourceV1(
                    source_id="source-moe-2022",
                    title="义务教育历史课程标准（2022年版）",
                    kind="curriculum",
                    author_or_institution="中华人民共和国教育部",
                    publisher="北京师范大学出版社",
                    published_year=2022,
                    url_or_path="https://www.moe.gov.cn/",
                    citation_note="用于适龄目标，不作为夏史事件直接证据。",
                    rights_note="只保存必要摘录和自写摘要。",
                ),
            ),
            passages=(
                EvidencePassageV1(
                    passage_id="L101-p001",
                    source_id="source-moe-2022",
                    title="七年级史料实证目标",
                    text="学生应学习区分传说、文献记载与考古材料。",
                    summary="课程回答应明确证据类型和不确定性。",
                    fact_ids=("fact-evidence-boundary",),
                    keywords=("史料实证",),
                    evidence_kind="curriculum_goal",
                    certainty="consensus",
                    chronology_note="现代课程目标，不是古代史料。",
                ),
            ),
            created_at=NOW,
            sealed_at=NOW,
            sealed_by="content-author",
            checksum="0" * 64,
        )
    )


class EvidenceContractTests(unittest.TestCase):
    def test_corpus_checksum_and_source_binding(self):
        corpus = build_corpus()
        self.assertTrue(verify_evidence_checksum(corpus))
        tampered = corpus.model_copy(update={"title": "被篡改"})
        self.assertFalse(verify_evidence_checksum(tampered))

        raw = corpus.model_dump(mode="json")
        raw["passages"][0]["source_id"] = "missing-source"
        with self.assertRaisesRegex(ValidationError, "unknown source_id"):
            EvidenceCorpusV1.model_validate(raw)

    def test_passages_require_stable_sorted_references(self):
        raw = build_corpus().model_dump(mode="json")
        raw["passages"][0]["fact_ids"] = ["fact-z", "fact-a"]
        with self.assertRaisesRegex(ValidationError, "unique and sorted"):
            EvidenceCorpusV1.model_validate(raw)

    def test_presentation_is_local_accessible_and_classroom_timed(self):
        presentation = sign_evidence_contract(
            LessonPresentationV1(
                presentation_id="presentation-L101-v1",
                course_id="C-prequin-state",
                lesson_id="L101",
                presentation_version=1,
                title="洪水、治理与早期国家",
                estimated_minutes=40,
                phase_minutes={
                    "observe": 9,
                    "decide": 14,
                    "consult": 7,
                    "dossier": 10,
                },
                video_path="media/lessons/L101/dayu.mp4",
                poster_path="media/lessons/L101/dayu.webp",
                transcript_path="media/lessons/L101/dayu.md",
                video_duration_seconds=54,
                video_sha256="1" * 64,
                poster_sha256="2" * 64,
                transcript_sha256="3" * 64,
                accessibility_note="视频可跳过，全文字幕和文字稿提供同等信息。",
                sealed_at=NOW,
                sealed_by="media-reviewer",
                checksum="0" * 64,
            )
        )
        self.assertTrue(verify_evidence_checksum(presentation))
        raw = presentation.model_dump(mode="json")
        raw["video_path"] = "https://video.example/dayu.mp4"
        with self.assertRaisesRegex(ValidationError, "canonical path"):
            LessonPresentationV1.model_validate(raw)

        raw = presentation.model_dump(mode="json")
        raw["poster_path"] = "media/lessons/L103/dayu.webp"
        with self.assertRaisesRegex(ValidationError, "media/lessons/L101"):
            LessonPresentationV1.model_validate(raw)

        raw = presentation.model_dump(mode="json")
        raw["phase_minutes"] = {
            "observe": 7,
            "decide": 15,
            "consult": 8,
            "dossier": 10,
        }
        with self.assertRaisesRegex(ValidationError, "observe phase"):
            LessonPresentationV1.model_validate(raw)

    def test_rag_request_and_answer_enforce_persona_and_retrieval_boundary(self):
        request = RagAskRequestV1(
            course_id="C-prequin-state",
            lesson_id="L101",
            persona_mode="person",
            person_id="person-yu",
            question="为什么要从堵水转向疏导？",
        )
        self.assertEqual(request.person_id, "person-yu")
        answer = RagAnswerV1(
            answer_source="extractive",
            body="现有课程证据只能支持：教学叙事把疏导作为治理方式的对照。",
            persona_mode="person",
            person_id="person-yu",
            role_disclaimer="角色化教学表达，不是史料原话。",
            citations=(
                RagCitationV1(
                    citation_id="citation-001",
                    passage_id="L101-p001",
                    source_id="source-moe-2022",
                    source_title="义务教育历史课程标准（2022年版）",
                    excerpt="区分传说、文献记载与考古材料。",
                    relevance=0.91,
                    certainty="consensus",
                ),
            ),
            retrieved_passage_ids=("L101-p001",),
            course_id="C-prequin-state",
            lesson_id="L101",
            release_id="rel-11a2b3c4d5-0002",
            release_no=2,
            release_checksum="a" * 64,
            evidence_corpus_id="evidence-L101-v1",
            evidence_version=1,
            evidence_checksum="b" * 64,
            uncertainty="medium",
        )
        raw = answer.model_dump(mode="json")
        raw["citations"][0]["passage_id"] = "not-retrieved"
        with self.assertRaisesRegex(ValidationError, "belong to retrieved"):
            RagAnswerV1.model_validate(raw)

        ranked = answer.model_dump(mode="json")
        ranked["retrieved_passage_ids"] = ["L101-p002", "L101-p001"]
        RagAnswerV1.model_validate(ranked)
        ranked["retrieved_passage_ids"] = ["L101-p001", "L101-p001"]
        with self.assertRaisesRegex(ValidationError, "must be unique"):
            RagAnswerV1.model_validate(ranked)

        insufficient = deepcopy(answer.model_dump(mode="json"))
        insufficient.update(
            answer_source="insufficient_evidence",
            body="当前课程证据不足，无法作答。",
            citations=[],
            uncertainty="high",
        )
        RagAnswerV1.model_validate(insufficient)

    def test_v3_requires_exact_evidence_and_presentation_bindings(self):
        manifest = build_dayu_release_manifest_v3()
        self.assertTrue(verify_release_metadata_checksum(manifest))
        parsed = parse_signed_course_release_manifest(manifest.model_dump(mode="json"))
        self.assertIsInstance(parsed, CourseReleaseManifestV3)

        raw = manifest.model_dump(mode="json")
        raw["items"][0]["evidence_corpus"]["lesson_id"] = "L103"
        with self.assertRaisesRegex(ValidationError, "content-addressed"):
            CourseReleaseManifestV3.model_validate(raw)

        raw["items"][0]["evidence_corpus"]["path"] = supplement_artifact_path(
            kind="evidence-corpus",
            artifact_id=raw["items"][0]["evidence_corpus"]["artifact_id"],
            course_id=raw["items"][0]["evidence_corpus"]["course_id"],
            lesson_id="L103",
            version=raw["items"][0]["evidence_corpus"]["version"],
            checksum=raw["items"][0]["evidence_corpus"]["checksum"],
        )
        with self.assertRaisesRegex(ValidationError, "identity must match"):
            CourseReleaseManifestV3.model_validate(raw)

    def test_v2_v3_reader_remains_discriminated(self):
        from services.contracts.release_examples import build_dayu_release_manifest

        v2 = build_dayu_release_manifest()
        v3 = build_dayu_release_manifest_v3()
        parsed_v2 = parse_signed_course_release_manifest(v2.model_dump(mode="json"))
        parsed_v3 = parse_signed_course_release_manifest(v3.model_dump(mode="json"))
        self.assertIsInstance(parsed_v2, CourseReleaseManifestV2)
        self.assertIsInstance(parsed_v3, CourseReleaseManifestV3)

    def test_committed_v3_and_evidence_schemas_match_models(self):
        for filename, (model, schema_id) in EVIDENCE_SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                expected = evidence_schema_document(model, schema_id)
                self.assertEqual(_read_json(EVIDENCE_SCHEMA_DIR / filename), expected)
        self.assertEqual(
            {path.name for path in EVIDENCE_SCHEMA_DIR.glob("*.json")},
            set(EVIDENCE_SCHEMA_DOCUMENTS),
        )

        for filename, builder in RELEASE_V3_SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                self.assertEqual(_read_json(RELEASE_V3_SCHEMA_DIR / filename), builder())
        for filename, example in release_v3_example_documents().items():
            with self.subTest(filename=filename):
                raw = _read_json(RELEASE_V3_EXAMPLE_DIR / filename)
                parsed = parse_signed_course_release_manifest(raw)
                self.assertIsInstance(parsed, CourseReleaseManifestV3)
                self.assertEqual(parsed.model_dump(mode="json"), raw)
                self.assertEqual(example.model_dump(mode="json"), raw)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
