import unittest

from sympy import Rational, Symbol, ceiling

from utils.solvers import solve_affine_guard_crossing


class SolveAffineGuardCrossingTest(unittest.TestCase):
    def test_symbolic_increasing_clock_strict(self):
        t0 = Symbol("t0", real=True)
        dt = Symbol("dt", real=True)
        bigt = Symbol("bigt", real=True)

        result = solve_affine_guard_crossing(t0, dt, "<", bigt)

        self.assertEqual(result, ceiling((bigt - t0) / dt))

    def test_symbolic_increasing_clock_from_zero(self):
        dt = Symbol("dt", real=True)
        bigt = Symbol("bigt", real=True)

        result = solve_affine_guard_crossing(0, dt, "<", bigt)

        self.assertEqual(result, ceiling(bigt / dt))

    def test_concrete_increasing_exact_boundary(self):
        # t0=0, dt=1/2, threshold=3 -> t(k)=k/2, guard t<3 holds for k=0..5 (t=2.5), fails at k=6
        result = solve_affine_guard_crossing(0, Rational(1, 2), "<", 3)
        self.assertEqual(result, 6)

    def test_concrete_increasing_non_strict(self):
        # t0=0, dt=1/2, threshold=3 -> guard t<=3 holds through k=6 (t=3.0 exactly), fails at k=7
        result = solve_affine_guard_crossing(0, Rational(1, 2), "<=", 3)
        self.assertEqual(result, 7)

    def test_concrete_decreasing_holds_at_zero_raises(self):
        # t0=0, coeff=-1, threshold=5: guard 0<5 holds at k=0 and f only decreases further below
        # threshold afterward -- the guard never fails, so there is no finite crossing point.
        with self.assertRaises(ValueError):
            solve_affine_guard_crossing(0, -1, "<", 5)

    def test_concrete_decreasing_fails_at_zero_returns_zero(self):
        # t0=10, coeff=-1, threshold=5: guard 10<5 is already false at k=0, loop runs 0 times.
        result = solve_affine_guard_crossing(10, -1, "<", 5)
        self.assertEqual(result, 0)

    def test_unsupported_comparator_raises(self):
        with self.assertRaises(ValueError):
            solve_affine_guard_crossing(0, 1, ">", 5)


if __name__ == "__main__":
    unittest.main()
