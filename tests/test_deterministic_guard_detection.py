import unittest

from sympy import Symbol, Rational

from program.assignment import PolyAssignment, DistAssignment
from program.condition import Atom
from program.distribution import Bernoulli
from program.ifstatem import IfStatem
from program.transformer.deterministic_guard import (
    find_affine_self_recurrence,
    is_fully_deterministic,
)


class DeterministicGuardDetectionTest(unittest.TestCase):
    def test_clock_is_affine_deterministic(self):
        t = Symbol("t", real=True)
        dt = Symbol("dt", real=True)
        loop_body = [PolyAssignment.deterministic(t, t + dt)]

        c = find_affine_self_recurrence(loop_body, t)

        self.assertEqual(c, dt)
        self.assertTrue(is_fully_deterministic(loop_body, {t}))

    def test_diffuse_variable_is_rejected(self):
        x = Symbol("x", real=True)
        sigma = Symbol("sigma", real=True)
        sqrt_dt = Symbol("sqrt_dt", real=True)
        # x = x + sigma*sqrt_dt {1/2} x - sigma*sqrt_dt  (a two-point categorical diffuse step)
        loop_body = [
            PolyAssignment(
                x,
                [x + sigma * sqrt_dt, x - sigma * sqrt_dt],
                [Rational(1, 2), Rational(1, 2)],
            )
        ]

        self.assertIsNone(find_affine_self_recurrence(loop_body, x))

    def test_dist_assignment_is_rejected(self):
        p = Symbol("p", real=True)
        flag = Symbol("flag", real=True)
        loop_body = [DistAssignment(flag, Bernoulli([p]))]

        self.assertFalse(is_fully_deterministic(loop_body, {flag}))

    def test_flag_depending_transitively_on_diffusing_variable_is_rejected(self):
        x = Symbol("x", real=True)
        sigma = Symbol("sigma", real=True)
        sqrt_dt = Symbol("sqrt_dt", real=True)
        dirx = Symbol("dirx", real=True)

        diffuse_x = PolyAssignment(
            x,
            [x + sigma * sqrt_dt, x - sigma * sqrt_dt],
            [Rational(1, 2), Rational(1, 2)],
        )
        # if x > 1: dirx = 0 else: dirx = dirx  (a direction flag that flips on a threshold of x)
        flip_dirx = IfStatem(
            [Atom(x, ">", 1)],
            [[PolyAssignment.deterministic(dirx, 0)]],
            else_branch=[PolyAssignment.deterministic(dirx, dirx)],
        )
        loop_body = [diffuse_x, flip_dirx]

        self.assertFalse(is_fully_deterministic(loop_body, {dirx}))

    def test_coefficient_not_one_is_rejected(self):
        x = Symbol("x", real=True)
        mu = Symbol("mu", real=True)
        # x = mu*x  (multiplicative, not a unit-coefficient affine self-recurrence)
        loop_body = [PolyAssignment.deterministic(x, mu * x)]

        self.assertIsNone(find_affine_self_recurrence(loop_body, x))

    def test_no_update_found_returns_none(self):
        t = Symbol("t", real=True)
        loop_body = []

        self.assertIsNone(find_affine_self_recurrence(loop_body, t))


if __name__ == "__main__":
    unittest.main()
