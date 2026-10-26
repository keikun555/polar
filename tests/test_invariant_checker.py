import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same shape as pwhiledt/translate.py's output for bm2d.pwhiledt / bm1d.pwhiledt, inlined so this
# test doesn't depend on running the translator.
BM2D_PROB = """
t, x, y = 0, 0, 0
while t < v_t:
    t = t + dt
    x = x + 1*dt**(1/2) {1/2} x - 1*dt**(1/2)
    y = y + 1*dt**(1/2) {1/2} y - 1*dt**(1/2)
end
"""

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


def run_checker(benchmark_path, lhs, op, rhs, *extra_args):
    result = subprocess.run(
        [sys.executable, "invariant_checker.py", str(benchmark_path), lhs, op, rhs, *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result


class InvariantCheckerTest(unittest.TestCase):
    def test_zero_conservation_invariant_passes(self):
        benchmark = Path(self._make_tmp("bm2d.prob", BM2D_PROB))
        result = run_checker(benchmark, "E((x**2-t)*y)", "==", "0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Holds for every iteration n: PASS", result.stdout)

    def test_false_candidate_fails(self):
        benchmark = Path(self._make_tmp("bm1d.prob", BM1D_PROB))
        result = run_checker(benchmark, "E(x**2)", "==", "dt*n + 1")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Holds for every iteration n: FAIL", result.stdout)

    def test_true_moment_equality_passes(self):
        benchmark = Path(self._make_tmp("bm1d.prob", BM1D_PROB))
        result = run_checker(benchmark, "E(x**2)", "==", "dt*n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Holds for every iteration n: PASS", result.stdout)

    def test_transcendental_bound_is_unknown_not_a_false_pass(self):
        benchmark = Path(self._make_tmp("gbm.prob", GBM_PROB))
        result = run_checker(benchmark, "E(m)", "<=", "E(exp(mu*v_t))")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Holds for every iteration n: UNKNOWN", result.stdout)

    def test_at_n_checks_the_postcondition_at_a_concrete_iteration(self):
        # v_t/dt are left symbolic in this fixture, so the crossing point isn't auto-known --
        # --at_n must be passed explicitly for the postcondition line to appear at all.
        benchmark = Path(self._make_tmp("bm1d.prob", BM1D_PROB))
        result = run_checker(benchmark, "E(x**2)", "==", "dt*n", "--at_n", "5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Holds for every iteration n: PASS", result.stdout)
        self.assertIn("Holds as a postcondition at n=5: PASS", result.stdout)

    def _make_tmp(self, name, content):
        import tempfile
        tmp_dir = tempfile.mkdtemp()
        path = Path(tmp_dir) / name
        path.write_text(content)
        return path


if __name__ == "__main__":
    unittest.main()
