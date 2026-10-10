from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from services.contracts.reader_v1 import ReaderQuoteRequestV1, ReaderQuoteV1
from services.reader_evidence import make_quote


class ReaderEvidenceTests(unittest.TestCase):
    def record(self):
        return {"manifest_sha256": "a" * 64, "volume": {"volume_no": 2, "title": "夏本纪"},
                "chapter_meta": {"title_simplified": "禹治水"}, "payload": {
                    "chapter_sha256": "b" * 64, "chapter": {
                        "sentences": [{"sentence_id": "s1", "traditional": "禹疏九河。", "simplified": "禹疏九河。", "source_span_ids": ["span1"]}],
                        "source_anchors": [{"source_span_id": "span1", "page_id": "page1"}],
                    }}}

    def test_quote_is_deterministic_and_keeps_exact_source(self):
        request = ReaderQuoteRequestV1(passage_id="passage1", sentence_ids=("s1",))
        with patch("services.reader_evidence.shiji_reader.chapter", return_value=self.record()):
            quote = make_quote(request)
            self.assertEqual(quote, make_quote(request))
        self.assertEqual(quote.quote_text, "禹疏九河。")
        self.assertEqual(quote.page_ids, ("page1",))
        self.assertEqual(quote.chapter_checksum, "b" * 64)
        tampered = quote.model_dump(mode="json")
        tampered["quote_text"] = "伪造的文字"
        with self.assertRaises(ValidationError):
            ReaderQuoteV1.model_validate(tampered)

    def test_unknown_or_duplicate_sentence_is_rejected(self):
        with self.assertRaises(ValidationError):
            ReaderQuoteRequestV1(passage_id="passage1", sentence_ids=("s1", "s1"))
        with patch("services.reader_evidence.shiji_reader.chapter", return_value=self.record()), self.assertRaises(KeyError):
            make_quote(ReaderQuoteRequestV1(passage_id="passage1", sentence_ids=("not-in-chapter",)))


if __name__ == "__main__":
    unittest.main()
