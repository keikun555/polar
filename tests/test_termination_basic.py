import unittest

from inputparser.parser import Parser
from program import normalize_program
from program.condition.true_cond import TrueCond
from termination.termination_analyzer import TerminationAnalyzer
from termination.polynomial.polynomial_termination_condition import (
    PolynomialTerminationCondition,
)

COUNTDOWN_SOURCE = """
x = 10
while x > 0:
    x = x - 1
end
"""

TWO_VAR_SOURCE = """
x = 5
y = 0
while x > 0:
    x = x - 1
    y = y + 1
end
"""


def _get_witness(source):
    program = Parser().parse_string(source)
    guard = program.loop_guard
    program.loop_guard = TrueCond()
    program = normalize_program(program)

    poly, terminates_zero, terminates_negative = TerminationAnalyzer._normalize_atom(guard)
    closed_forms = TerminationAnalyzer._compute_closed_form_of_polynomial(
        poly.free_symbols, program
    )
    closed_form_poly = poly.expand().subs(closed_forms)
    return PolynomialTerminationCondition(
        closed_form_poly, terminates_zero, terminates_negative
    ).get_witness()


class TerminationBasicTest(unittest.TestCase):
    def test_countdown_terminates(self):
        witness = _get_witness(COUNTDOWN_SOURCE)
        self.assertIsNotNone(witness)
        self.assertTrue(witness.is_termination_witness())

    def test_two_variable_countdown_terminates(self):
        witness = _get_witness(TWO_VAR_SOURCE)
        self.assertIsNotNone(witness)
        self.assertTrue(witness.is_termination_witness())


if __name__ == "__main__":
    unittest.main()
