import shutil
import threading
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

    def test_set_is_an_atomic_upsert_under_concurrent_first_writes(self):
        sqlite_path = self.tmp_root / "data" / "chronovita.db"
        db.init_engine(str(sqlite_path))
        write_count = 16
        barrier = threading.Barrier(write_count)

        def write(value: int) -> None:
            barrier.wait(timeout=10)
            db.kv_set("qa-upsert", "shared", {"value": value})

        with ThreadPoolExecutor(max_workers=write_count) as pool:
            tuple(pool.map(write, range(write_count)))

        self.assertIn(
            db.kv_get("qa-upsert", "shared")["value"],
            range(write_count),
        )

    def test_cas_uses_json_semantics_and_distinguishes_stored_null(self):
        sqlite_path = self.tmp_root / "data" / "chronovita.db"
        db.init_engine(str(sqlite_path))
        original = {"revision": 1, "nodes": []}
        db.kv_set("qa-cas", "legacy-format", original)
        with db._engine().begin() as connection:
            connection.execute(
                db.kv_table.update()
                .where(
                    (db.kv_table.c.namespace == "qa-cas")
                    & (db.kv_table.c.key == "legacy-format")
                )
                .values(data='{ "nodes": [ ], "revision": 1 }')
            )
        self.assertTrue(
            db.kv_compare_and_set(
                "qa-cas",
                "legacy-format",
                original,
                {"revision": 2, "nodes": []},
                expected_present=True,
            )
        )

        db.kv_set("qa-cas", "null-value", None)
        self.assertEqual(
            db.kv_get_with_presence("qa-cas", "null-value"),
            (True, None),
        )
        self.assertFalse(
            db.kv_compare_and_set(
                "qa-cas",
                "null-value",
                None,
                {"revision": 1},
            )
        )
        self.assertTrue(
            db.kv_compare_and_set(
                "qa-cas",
                "null-value",
                None,
                {"revision": 1},
                expected_present=True,
            )
        )

        db.kv_set("qa-cas", "typed-value", True)
        self.assertFalse(
            db.kv_compare_and_set(
                "qa-cas",
                "typed-value",
                1,
                "wrong-type",
                expected_present=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
