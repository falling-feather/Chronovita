from __future__ import annotations

import io
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import provision_postgres_test as provisioning


class PostgresProvisioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provisioned = provisioning.ProvisionedPostgresTest(
            migration_url=(
                "postgresql+psycopg://migrator:migration-secret@db/test"
            ),
            runtime_url="postgresql+psycopg://runtime:runtime-secret@db/test",
            migrator_password="migration-secret",
            runtime_password="runtime-secret",
        )

    def test_run_tests_child_receives_only_role_urls_and_returns_its_status(
        self,
    ) -> None:
        for child_status in (0, 7):
            with self.subTest(child_status=child_status):
                stdout = io.StringIO()
                stderr = io.StringIO()
                completed = subprocess.CompletedProcess(
                    args=["python"],
                    returncode=child_status,
                )
                with patch.dict(
                    os.environ,
                    {
                        "CUSTOM_ADMIN_URL": "admin-secret",
                        "CHRONO_TEST_POSTGRES_OLD_URL": "old-secret",
                        "UNRELATED": "preserved",
                    },
                    clear=True,
                ):
                    with patch.object(
                        provisioning,
                        "provision_postgres_test",
                        return_value=self.provisioned,
                    ) as provision:
                        with patch.object(
                            provisioning.subprocess,
                            "run",
                            return_value=completed,
                        ) as run:
                            with redirect_stdout(stdout), redirect_stderr(
                                stderr
                            ):
                                code = provisioning.main(
                                    [
                                        "--admin-url-env",
                                        "CUSTOM_ADMIN_URL",
                                        "--run-tests",
                                    ]
                                )

                self.assertEqual(code, child_status)
                provision.assert_called_once_with("admin-secret")
                child_env = run.call_args.kwargs["env"]
                self.assertNotIn("CUSTOM_ADMIN_URL", child_env)
                self.assertNotIn("CHRONO_TEST_POSTGRES_ADMIN_URL", child_env)
                self.assertNotIn("CHRONO_TEST_POSTGRES_OLD_URL", child_env)
                self.assertEqual(child_env["UNRELATED"], "preserved")
                self.assertEqual(
                    child_env["CHRONO_TEST_POSTGRES_MIGRATION_URL"],
                    self.provisioned.migration_url,
                )
                self.assertEqual(
                    child_env["CHRONO_TEST_POSTGRES_RUNTIME_URL"],
                    self.provisioned.runtime_url,
                )
                self.assertNotIn("admin-secret", stdout.getvalue())
                self.assertNotIn("runtime-secret", stdout.getvalue())
                if child_status == 0:
                    self.assertIn('"ok":true', stdout.getvalue())
                    self.assertEqual(stderr.getvalue(), "")
                else:
                    self.assertNotIn('"ok":true', stdout.getvalue())
                    self.assertIn(
                        "postgres_service_test_failed",
                        stderr.getvalue(),
                    )

    def test_github_env_is_appended_without_admin_url(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "github-env"
            output.write_text("EXISTING=value\n", encoding="utf-8")
            code, stdout, stderr = self._run(
                ["--github-env"],
                env={
                    "CHRONO_TEST_POSTGRES_ADMIN_URL": "admin-secret",
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_ENV": str(output),
                },
            )

            self.assertEqual(code, 0, stderr)
            contents = output.read_text(encoding="utf-8")
            self.assertTrue(contents.startswith("EXISTING=value\n"))
            self.assertNotIn("CHRONO_TEST_POSTGRES_ADMIN_URL", contents)
            self.assertNotIn("admin-secret", contents + stdout + stderr)

    def test_github_env_is_rejected_outside_actions(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "not-github-env"
            with patch.dict(
                os.environ,
                {
                    "CHRONO_TEST_POSTGRES_ADMIN_URL": "admin-secret",
                    "GITHUB_ENV": str(output),
                },
                clear=True,
            ):
                with patch.object(
                    provisioning,
                    "provision_postgres_test",
                ) as provision:
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = provisioning.main(["--github-env"])

            self.assertEqual(code, 2)
            provision.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "postgres_github_environment_unavailable",
                stderr.getvalue(),
            )

    def test_provisioning_failure_is_redacted(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(
            os.environ,
            {"CHRONO_TEST_POSTGRES_ADMIN_URL": "admin-secret"},
            clear=True,
        ):
            with patch.object(
                provisioning,
                "provision_postgres_test",
                side_effect=RuntimeError("admin-secret"),
            ):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = provisioning.main(["--run-tests"])

        self.assertEqual(code, 1)
        self.assertNotIn("admin-secret", stdout.getvalue() + stderr.getvalue())
        self.assertIn("postgres_test_provisioning_failed", stderr.getvalue())

    def test_missing_admin_url_fails_without_creating_output(self) -> None:
        code, stdout, stderr = self._run(
            ["--run-tests"],
            env={},
            provision=False,
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("postgres_test_admin_url_missing", stderr)

    def test_destructive_provisioning_is_limited_to_the_local_test_database(
        self,
    ) -> None:
        invalid_urls = (
            "postgresql+psycopg://chronovita_test_admin:x@db.example/test",
            "postgresql+psycopg://chronovita_test_admin:x@127.0.0.1/production",
            "postgresql+psycopg://postgres:x@127.0.0.1/chronovita_test",
        )
        for database_url in invalid_urls:
            with self.subTest(database_url=database_url):
                with self.assertRaises(ValueError):
                    provisioning.provision_postgres_test(database_url)

    def _run(
        self,
        arguments: list[str],
        *,
        env: dict[str, str],
        provision: bool = True,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        provision_patch = patch.object(
            provisioning,
            "provision_postgres_test",
            return_value=self.provisioned,
        )
        with patch.dict(os.environ, env, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                if provision:
                    with provision_patch:
                        code = provisioning.main(arguments)
                else:
                    code = provisioning.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
