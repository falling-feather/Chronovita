import unittest
from services.reading_links import lesson_destinations, related_reading


class ReadingLinksTests(unittest.TestCase):
    def test_links_are_real_catalog_entries_and_teacher_destinations(self):
        destinations = lesson_destinations()
        self.assertEqual(len(destinations), 46)
        self.assertEqual(len({item['value'] for item in destinations}), 46)
        self.assertTrue(any(item['volume_no'] == 2 for item in related_reading('L101')))
        self.assertTrue(any(item['volume_no'] == 68 for item in related_reading('L105')))
        with self.assertRaises(KeyError):
            related_reading('unknown')
