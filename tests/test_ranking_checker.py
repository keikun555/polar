import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BM1D_PROB = """
t, x = 0, 0
while t < v_t:
    t = t + dt
    x = x + 1*dt**(1/2) {1/2} x - 1*dt**(1/2)
end
"""

GBM_PROB = """
t = 0
s, m = 1, 1
while t < v_t:
    t = t + dt
    m = m + ((mu*m)*dt)
    s = s + ((mu*s)*dt)
    s = s + ((sigma*s)*1)*dt**(1/2) {1/2} s - ((sigma*s)*1)*dt**(1/2)
end
"""


def run_checker(benchmark_path, candidate, *extra_args):
    result = subprocess.run(
        [sys.executable, "ranking_checker.py", str(benchmark_path), candidate, *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result


def _make_tmp(name, content):
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    path = Path(tmp_dir) / name
    path.write_text(content)
    return path


class RankingCheckerTest(unittest.TestCase):
    def test_clock_remainder_decreases_on_bm1d(self):
        benchmark = _make_tmp("bm1d.prob", BM1D_PROB)
        result = run_checker(benchmark, "v_t - t", "--positive", "dt")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Verdict: PASS", result.stdout)

    def test_clock_remainder_decreases_on_gbm(self):
        benchmark = _make_tmp("gbm.prob", GBM_PROB)
        result = run_checker(benchmark, "v_t - t", "--positive", "dt")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Verdict: PASS", result.stdout)

    def test_wrong_direction_fails(self):
        benchmark = _make_tmp("bm1d.prob", BM1D_PROB)
        result = run_checker(benchmark, "v_t - t", "--positive", "dt", "--direction", "increasing")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Verdict: FAIL", result.stdout)

    def test_without_positivity_assertion_is_unknown_not_a_false_pass(self):
        benchmark = _make_tmp("bm1d.prob", BM1D_PROB)
        result = run_checker(benchmark, "v_t - t")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Verdict: UNKNOWN", result.stdout)

    def test_guard_dependent_delta_is_unknown(self):
        benchmark = _make_tmp("bm1d.prob", BM1D_PROB)
        result = run_checker(benchmark, "t**2", "--positive", "dt")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Verdict: UNKNOWN", result.stdout)
        self.assertIn("still depends on loop variable", result.stdout)


if __name__ == "__main__":
    unittest.main()
