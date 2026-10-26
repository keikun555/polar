import unittest

import settings
from inputparser.parser import Parser
from program import normalize_program
from program.transformer.exceptions import NormalizingException

GBM_SOURCE = """
t = 0
s, m = 1, 1
while t < bigt:
    t = t + dt
    m = m + ((mu*m)*dt)
    s = s + ((mu*s)*dt)
    s = s + ((sigma*s)*1)*dt**(1/2) {1/2} s - ((sigma*s)*1)*dt**(1/2)
end
"""


class LoopGuardDeterminismTest(unittest.TestCase):
    def setUp(self):
        self._original_setting = settings.solve_deterministic_guards

    def tearDown(self):
        settings.solve_deterministic_guards = self._original_setting

    def test_default_off_still_raises_same_exception_as_before(self):
        settings.solve_deterministic_guards = False
        program = Parser().parse_string(GBM_SOURCE)

        with self.assertRaises(NormalizingException):
            normalize_program(program)

    def test_enabled_solves_the_guard_instead_of_rejecting_it(self):
        from sympy import Symbol, ceiling

        settings.solve_deterministic_guards = True
        program = Parser().parse_string(GBM_SOURCE)

        normalized = normalize_program(program)

        bigt = Symbol("bigt", real=True)
        dt = Symbol("dt", real=True)
        self.assertEqual(
            normalized.known_iteration_count, ceiling(bigt / dt)
        )


if __name__ == "__main__":
    unittest.main()
