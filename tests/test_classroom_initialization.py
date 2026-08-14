from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.initialize_classroom import (
    PASSWORD_ENV,
    _read_new_password,
    initialize_classroom,
)
from services.auth import AuthService, AuthServiceConfig
from services.persistence.database import create_database_engine, resolve_database_target


class ClassroomInitializationTests(unittest.TestCase):
    def test_first_admin_is_created_once_and_password_is_not_stored_plaintext(self):
        password = "Classroom admin password 2026"
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "classroom.db"
            reads = 0

            def first_password() -> str:
                nonlocal reads
                reads += 1
                return password

            first = initialize_classroom(database, password_reader=first_password)

            def must_not_read_again() -> str:
                raise AssertionError("idempotent initialization prompted again")

            second = initialize_classroom(database, password_reader=must_not_read_again)
            self.assertEqual(first["status"], "initialized")
            self.assertEqual(second["status"], "already-initialized")
            self.assertEqual(reads, 1)
            self.assertNotIn(password.encode("utf-8"), database.read_bytes())

            engine = create_database_engine(
                resolve_database_target(database_url=None, sqlite_path=str(database))
            )
            try:
                service = AuthService(
                    engine,
                    AuthServiceConfig(mode="accounts", session_ttl_seconds=300),
                )
                session = service.login(
                    "admin", password, request_id="classroom-initialization-test"
                )
                self.assertEqual(session.principal.roles, ("admin",))
            finally:
                engine.dispose()

    def test_noninteractive_password_environment_is_process_only(self):
        password = "Environment-only classroom password 2026"
        previous = os.environ.get(PASSWORD_ENV)
        try:
            os.environ[PASSWORD_ENV] = password
            self.assertEqual(_read_new_password(), password)
            self.assertNotIn(PASSWORD_ENV, os.environ)
        finally:
            if previous is None:
                os.environ.pop(PASSWORD_ENV, None)
            else:
                os.environ[PASSWORD_ENV] = previous


if __name__ == "__main__":
    unittest.main()
