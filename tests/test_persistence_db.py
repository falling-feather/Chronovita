import shutil
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.persistence import db


class PersistenceDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-persistence-db-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)

    def tearDown(self):
        db.close_engine()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_sqlite_path_inside_non_ascii_workspace(self):
        sqlite_path = self.tmp_root / "data" / "chronovita.db"

        db.init_engine(str(sqlite_path))
        db.kv_set("qa", "lesson", {"title": "封存样课"})

        self.assertEqual(db.kv_get("qa", "lesson"), {"title": "封存样课"})
        self.assertTrue(sqlite_path.exists())

    def test_compare_and_set_allows_only_one_writer_for_the_same_snapshot(self):
        sqlite_path = self.tmp_root / "data" / "chronovita.db"
        db.init_engine(str(sqlite_path))
        original = {"revision": 1, "nodes": []}
        db.kv_set("canvas", "lesson", original)

        def replace(revision: int) -> bool:
            return db.kv_compare_and_set(
                "canvas",
                "lesson",
                original,
                {"revision": revision, "nodes": []},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(replace, (2, 3)))

        self.assertEqual(sorted(results), [False, True])
        self.assertIn(db.kv_get("canvas", "lesson")["revision"], {2, 3})


if __name__ == "__main__":
    unittest.main()
