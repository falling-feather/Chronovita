from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "teacher-editor.ps1"
CONFIGURATOR = REPO_ROOT / "scripts" / "configure-content-history.ps1"
TEST_TOKEN = "github_pat_" + ("A" * 48)


def _ps_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _run_powershell(
    source: str,
    *,
    environment: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_environment = os.environ.copy()
    if environment:
        merged_environment.update(environment)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            source,
        ],
        cwd=REPO_ROOT,
        env=merged_environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"PowerShell failed with {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed


@unittest.skipUnless(os.name == "nt", "Windows PowerShell 5.1 is required")
class TeacherLauncherTests(unittest.TestCase):
    def test_scripts_parse_in_windows_powershell_51(self):
        for script in (LAUNCHER, CONFIGURATOR):
            with self.subTest(script=script.name):
                source = (
                    "$errors = $null; "
                    f"[void][Management.Automation.Language.Parser]::ParseFile({_ps_literal(script)}, "
                    "[ref]$null, [ref]$errors); "
                    "if ($errors.Count -ne 0) { $errors | Out-String | Write-Error; exit 1 }"
                )
                _run_powershell(source)

    def test_missing_credential_can_be_skipped_without_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            credential_root = Path(temporary)
            credential_path = credential_root / "content-history-token.dpapi"
            source = (
                f". {_ps_literal(LAUNCHER)}; "
                "Initialize-LocalContentHistoryCredential "
                f"-CredentialRoot {_ps_literal(credential_root)} "
                f"-CredentialPath {_ps_literal(credential_path)} "
                "-AllowInteractiveSetup:$false; "
                f"if (Test-Path -LiteralPath {_ps_literal(credential_path)}) {{ exit 11 }}; "
                "if ($env:CHRONO_GITHUB_PUBLICATION_TOKEN) { exit 12 }"
            )
            completed = _run_powershell(source)
            self.assertIn("setup was skipped", completed.stdout)

    def test_skip_browser_explicitly_disables_credential_prompt(self):
        source = (
            f". {_ps_literal(LAUNCHER)} -SkipBrowser; "
            "if (Test-InteractiveCredentialSetupAllowed) { exit 13 }"
        )
        _run_powershell(source)

    def test_configured_credential_is_encrypted_and_loaded_without_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            credential_root = Path(temporary)
            credential_path = credential_root / "content-history-token.dpapi"
            source = (
                "$token = ConvertTo-SecureString $env:CHRONO_TEST_TOKEN -AsPlainText -Force; "
                f"& {_ps_literal(CONFIGURATOR)} -Token $token "
                f"-CredentialRoot {_ps_literal(credential_root)}; "
                f". {_ps_literal(LAUNCHER)}; "
                "Initialize-LocalContentHistoryCredential "
                f"-CredentialRoot {_ps_literal(credential_root)} "
                f"-CredentialPath {_ps_literal(credential_path)} "
                "-AllowInteractiveSetup:$false; "
                "if ($env:CHRONO_GITHUB_PUBLICATION_TOKEN -cne $env:CHRONO_TEST_TOKEN) { exit 21 }; "
                "if ($env:CHRONO_GITHUB_PUBLICATION_ENABLED -cne 'true') { exit 22 }; "
                "Clear-TransientContentHistoryCredential"
            )
            completed = _run_powershell(
                source,
                environment={"CHRONO_TEST_TOKEN": TEST_TOKEN},
            )
            self.assertIn("credential loaded", completed.stdout)
            encrypted = credential_path.read_text(encoding="utf-8")
            self.assertNotIn(TEST_TOKEN, encrypted)
            self.assertNotIn(TEST_TOKEN, completed.stdout)
            self.assertNotIn(TEST_TOKEN, completed.stderr)

    def test_damaged_credential_disables_submission_with_recovery_steps(self):
        with tempfile.TemporaryDirectory() as temporary:
            credential_root = Path(temporary)
            credential_path = credential_root / "content-history-token.dpapi"
            credential_path.write_text("not-a-dpapi-payload\n", encoding="ascii")
            source = (
                f". {_ps_literal(LAUNCHER)}; "
                "Initialize-LocalContentHistoryCredential "
                f"-CredentialRoot {_ps_literal(credential_root)} "
                f"-CredentialPath {_ps_literal(credential_path)} "
                "-AllowInteractiveSetup:$false; "
                "if ($env:CHRONO_GITHUB_PUBLICATION_TOKEN) { exit 31 }; "
                "if ($env:CHRONO_GITHUB_PUBLICATION_ENABLED) { exit 32 }"
            )
            completed = _run_powershell(source)
            output = completed.stdout + completed.stderr
            self.assertIn("configure-content-history.cmd", output)
            self.assertIn("submission is disabled", output)

    def test_configurator_rejects_noninteractive_missing_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = (
                f"& {_ps_literal(CONFIGURATOR)} "
                f"-CredentialRoot {_ps_literal(Path(temporary))} -NonInteractive"
            )
            completed = _run_powershell(source, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                "No token was supplied and secure input is unavailable",
                completed.stdout + completed.stderr,
            )

    def test_dependency_fingerprint_reuses_only_current_complete_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock_path = root / "dependency.lock"
            package_path = root / "package.json"
            stamp_path = root / "installed.sha256"
            required_path = root / "required.bin"
            lock_path.write_text("lock-v1\n", encoding="ascii")
            package_path.write_text("{}\n", encoding="ascii")
            required_path.write_bytes(b"installed")
            source = (
                f". {_ps_literal(LAUNCHER)}; "
                f"$inputs = @({_ps_literal(lock_path)}, {_ps_literal(package_path)}); "
                f"Set-DependencyInstallStamp -InputPaths $inputs -StampPath {_ps_literal(stamp_path)}; "
                "if (-not (Test-DependencyInstallCurrent -InputPaths $inputs "
                f"-StampPath {_ps_literal(stamp_path)} "
                f"-RequiredPaths @({_ps_literal(required_path)}))) {{ exit 41 }}; "
                f"Add-Content -LiteralPath {_ps_literal(lock_path)} -Value 'lock-v2'; "
                "if (Test-DependencyInstallCurrent -InputPaths $inputs "
                f"-StampPath {_ps_literal(stamp_path)} "
                f"-RequiredPaths @({_ps_literal(required_path)})) {{ exit 42 }}; "
                f"Set-DependencyInstallStamp -InputPaths $inputs -StampPath {_ps_literal(stamp_path)}; "
                f"Remove-Item -LiteralPath {_ps_literal(required_path)}; "
                "if (Test-DependencyInstallCurrent -InputPaths $inputs "
                f"-StampPath {_ps_literal(stamp_path)} "
                f"-RequiredPaths @({_ps_literal(required_path)})) {{ exit 43 }}"
            )
            _run_powershell(source)


if __name__ == "__main__":
    unittest.main()
