import unittest
from unittest.mock import patch

from services.reader_assistant import ReaderAskRequestV1, answer_reader
from tests import test_reader_evidence


class ReaderAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_answer_is_source_bound_and_irrelevant_questions_refuse(self):
        record = test_reader_evidence.ReaderEvidenceTests().record()
        with patch("services.shiji_reader.chapter", return_value=record):
            answer = await answer_reader(ReaderAskRequestV1(passage_id="passage1", question="解释这句话"))
            self.assertEqual(answer.answer_source, "extractive")
            self.assertEqual(answer.citations[0].quote_text, "禹疏九河。")
            unrelated = await answer_reader(ReaderAskRequestV1(passage_id="passage1", question="我想买比特币"))
            self.assertEqual(unrelated.answer_source, "insufficient_evidence")
            self.assertEqual(unrelated.citations, ())

    async def test_identity_and_unrelated_introduction_are_not_fake_chapter_answers(self):
        record = test_reader_evidence.ReaderEvidenceTests().record()
        with patch("services.shiji_reader.chapter", return_value=record):
            identity = await answer_reader(ReaderAskRequestV1(passage_id="passage1", question="你是谁？"))
            self.assertIn("教学形象", identity.body)
            self.assertEqual(identity.citations, ())
            unrelated = await answer_reader(ReaderAskRequestV1(passage_id="passage1", question="介绍今天的气温"))
            self.assertEqual(unrelated.answer_source, "insufficient_evidence")

    async def test_model_cannot_cite_unretrieved_sentence(self):
        record = test_reader_evidence.ReaderEvidenceTests().record()
        async def bad_generator(messages, schema):
            return schema(answer="错误引用", sentence_ids=["not-retrieved"])
        with patch("services.shiji_reader.chapter", return_value=record):
            answer = await answer_reader(ReaderAskRequestV1(passage_id="passage1", question="解释这句话"), generator=bad_generator)
            self.assertEqual(answer.answer_source, "extractive")
            self.assertIn("未通过校验", answer.model_notice)

    async def test_current_sentence_is_not_replaced_by_the_start_of_chapter(self):
        record = test_reader_evidence.ReaderEvidenceTests().record()
        second = {**record['payload']['chapter']['sentences'][0], 'sentence_id': 'second',
                  'simplified': '禹与众人议事。', 'translation': '禹同大家商议。'}
        record['payload']['chapter']['sentences'].append(second)
        with patch('services.shiji_reader.chapter', return_value=record):
            answer = await answer_reader(ReaderAskRequestV1(passage_id='passage1', sentence_id='second', question='解释这句话'))
            self.assertEqual(answer.citations[0].sentence_ids, ('second',))
            with self.assertRaises(ValueError):
                await answer_reader(ReaderAskRequestV1(passage_id='passage1', sentence_id='unknown', question='解释这句话'))
