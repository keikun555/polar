import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class PwhiledtBenchSmokeTest(unittest.TestCase):
    def test_runs_and_reports_pass_verdicts(self):
        result = subprocess.run(
            [sys.executable, "pwhiledt/bench.py", "--trials", "1"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bm1d", result.stdout)
        self.assertIn("Total (mean, 1 trial(s) each):", result.stdout)
        # Every row in the table is a known-good check, so every verdict should be a PASS.
        self.assertNotIn("UNKNOWN", result.stdout)
        self.assertNotIn("FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
