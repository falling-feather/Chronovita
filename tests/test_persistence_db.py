import shutil
import unittest
import uuid
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


if __name__ == "__main__":
    unittest.main()
