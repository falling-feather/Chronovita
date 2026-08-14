from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "classroom.ps1"
STOPPER = REPO_ROOT / "scripts" / "stop-classroom.ps1"


def _ps_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _run_powershell(source: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            source,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"PowerShell failed with {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


@unittest.skipUnless(os.name == "nt", "Windows PowerShell 5.1 is required")
class ClassroomLauncherTests(unittest.TestCase):
    def test_scripts_parse_in_windows_powershell_51(self):
        for script in (LAUNCHER, STOPPER):
            with self.subTest(script=script.name):
                source = (
                    "$errors = $null; "
                    f"[void][Management.Automation.Language.Parser]::ParseFile({_ps_literal(script)}, "
                    "[ref]$null, [ref]$errors); "
                    "if ($errors.Count -ne 0) { $errors | Out-String | Write-Error; exit 1 }"
                )
                _run_powershell(source)

    def test_default_is_loopback_and_lan_binding_is_explicit(self):
        _run_powershell(
            f". {_ps_literal(LAUNCHER)}; if ($BindHost -cne '127.0.0.1') {{ exit 11 }}"
        )
        _run_powershell(
            f". {_ps_literal(LAUNCHER)} -Lan; if ($BindHost -cne '0.0.0.0') {{ exit 12 }}"
        )

    def test_bootstrap_password_survives_scrub_only_until_initializer(self):
        result = _run_powershell(
            "$env:CHRONO_CLASSROOM_ADMIN_PASSWORD = 'process-only-test-value'; "
            "$env:CHRONO_UNTRUSTED_TEST = 'must-clear'; "
            f". {_ps_literal(LAUNCHER)}; Set-ClassroomEnvironment -LanAddresses @(); "
            "if ($env:CHRONO_CLASSROOM_ADMIN_PASSWORD -cne 'process-only-test-value') { exit 21 }; "
            "if ($env:CHRONO_UNTRUSTED_TEST) { exit 22 }; "
            "if ($env:CHRONO_AUTH_MODE -cne 'accounts') { exit 23 }; "
            "if ($env:CHRONO_SERVE_WEB_APP -cne 'true') { exit 24 }; "
            "$hosts = $env:CHRONO_TRUSTED_HOSTS | ConvertFrom-Json; "
            "if ($hosts.Count -ne 2 -or $hosts -contains $null) { exit 25 }"
        )
        self.assertNotIn("process-only-test-value", result.stdout + result.stderr)

    def test_cmd_wrappers_are_ascii_and_delegate(self):
        expected = {
            "classroom.cmd": "classroom.ps1",
            "stop-classroom.cmd": "stop-classroom.ps1",
        }
        for filename, delegated in expected.items():
            with self.subTest(filename=filename):
                raw = (REPO_ROOT / "scripts" / filename).read_bytes()
                self.assertTrue(raw.isascii())
                self.assertIn(delegated, raw.decode("ascii"))

    def test_runtime_records_the_real_port_owner_not_only_the_venv_launcher(self):
        source = LAUNCHER.read_text("utf-8")
        self.assertIn("Get-ClassroomServicePid", source)
        self.assertIn("Select-Object -ExpandProperty OwningProcess -Unique", source)
        self.assertIn("pid = $servicePid", source)
        self.assertIn("launcher_pid = $classroomProcess.Id", source)


if __name__ == "__main__":
    unittest.main()
