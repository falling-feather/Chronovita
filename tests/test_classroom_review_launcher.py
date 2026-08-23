from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "classroom-review.ps1"
STOPPER = ROOT / "scripts" / "stop-classroom-review.ps1"


class ClassroomReviewLauncherTests(unittest.TestCase):
    def test_review_launcher_binds_origin_ports_and_hybrid_mode_explicitly(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('$env:CHRONO_AUTH_MODE = "accounts"', source)
        self.assertIn('$env:CHRONO_CORS_ORIGINS = ConvertTo-Json', source)
        self.assertIn('"http://localhost`:$WebPort"', source)
        self.assertIn('$env:VITE_API_PROXY_TARGET = $ApiUrl', source)
        self.assertIn('$env:CHRONO_RAG_VECTOR_ENABLED', source)
        self.assertIn('--verify-only --target $ModelRoot', source)
        self.assertIn('pass -LexicalOnly explicitly', source)
        self.assertNotIn('CHRONO_RAG_VECTOR_ENABLED = "false"', source)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell 5.1 is required")
    def test_review_scripts_parse_in_windows_powershell(self):
        for path in (LAUNCHER, STOPPER):
            command = (
                "$ErrorActionPreference='Stop';"
                f"[void][scriptblock]::Create([IO.File]::ReadAllText('{path}'))"
            )
            completed = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"PowerShell failed to parse {path.name}:\n{completed.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
