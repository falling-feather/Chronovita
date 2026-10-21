import unittest
from scripts.sync_named_assets import asset_id, split_people, person_lessons, merge_archive_profiles


class NamedAssetTests(unittest.TestCase):
    def test_different_names_do_not_share_exported_placeholder_id(self):
        self.assertNotEqual(asset_id('person', '禹'), asset_id('person', '启'))

    def test_normalized_name_has_stable_id(self):
        self.assertEqual(asset_id('person', '姬重耳（晋文公）'),
                         asset_id('person', ' 姬重耳(晋文公) '))
        self.assertEqual(asset_id('keyword', ' 春秋五霸 '),
                         asset_id('keyword', '春秋五霸'))

    def test_glued_known_people_split_without_duplicates(self):
        names = ['姜小白（齐桓公）', '姬重耳（晋文公）', '吴王阖闾']
        self.assertEqual(split_people([''.join(names), '吴王阖闾'], names), names)

    def test_unrecognized_related_people_are_not_discarded(self):
        self.assertEqual(split_people(['未知称谓'], ['禹']), ['未知称谓'])

    def test_person_title_matches_unique_course_name(self):
        self.assertEqual(person_lessons('李世民（唐太宗）', {'李世民': ['L801']}), ['L801'])
        self.assertEqual(person_lessons('张骞', {'李世民': ['L801']}), [])

    def test_ambiguous_alias_does_not_guess_a_lesson(self):
        self.assertEqual(person_lessons('同名', {'同名(甲)': ['L1'], '同名(乙)': ['L2']}), [])

    def test_duplicate_archives_merge_relations_and_keep_both_sources(self):
        first = {"asset_id": "old", "word": "春秋五霸", "gloss": "释义",
                 "related_people": ["齐桓公"], "related_lessons": ["L104"]}
        second = dict(first, asset_id="new", related_people=["齐桓公", "晋文公"])
        result = merge_archive_profiles([
            ("keyword", first, {"archive": "a.zip"}),
            ("keyword", second, {"archive": "b.zip"}),
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1]["related_people"], ["齐桓公", "晋文公"])
        self.assertEqual(len(result[0][2]), 2)

    def test_conflicting_prose_is_not_silently_replaced(self):
        first = {"word": "词条", "gloss": "甲"}
        second = {"word": "词条", "gloss": "乙"}
        with self.assertRaisesRegex(ValueError, "Conflicting archive content"):
            merge_archive_profiles([("keyword", first, {}), ("keyword", second, {})])

    def test_identity_normalization_preserves_single_asset(self):
        first = {"name": " 姬重耳（晋文公） ", "summary": "正文"}
        second = {"name": "姬重耳(晋文公)", "summary": "正文"}
        self.assertEqual(len(merge_archive_profiles([
            ("person", first, {}), ("person", second, {}),
        ])), 1)
