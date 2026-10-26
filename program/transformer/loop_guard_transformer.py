from typing import List, Optional, Tuple

import settings
from .transformer import Transformer
from .deterministic_guard import (
    find_affine_self_recurrence,
    find_initial_value,
    is_fully_deterministic,
)
from program import Program
from program.condition import Atom, Condition, TrueCond, And
from program.ifstatem import IfStatem
from utils.solvers import solve_affine_guard_crossing


class LoopGuardTransformer(Transformer):
    """
    Transforms a program from "while guard: ..." to "while true: if guard: ..."
    Also it collapses simple top-level if-statements into a single if. For example:
    if cond1: if cond2: stuff end end
    turns into
    if cond1 and cond2: stuff end
    """

    trivial_guard: bool = False
    solve_deterministic_guards: bool = False

    def __init__(self, trivial_guard: bool = None, solve_deterministic_guards: bool = None):
        self.trivial_guard = (
            settings.trivial_guard if trivial_guard is None else trivial_guard
        )
        self.solve_deterministic_guards = (
            settings.solve_deterministic_guards
            if solve_deterministic_guards is None
            else solve_deterministic_guards
        )

    def execute(self, program: Program) -> Program:
        if self.trivial_guard:
            program.loop_guard = TrueCond()
            return program

        statements, condition = self._collapse_first_level_ifs(program.loop_body)

        if self.solve_deterministic_guards and isinstance(condition, TrueCond):
            known_iteration_count = self._try_solve_deterministic_guard(program)
            if known_iteration_count is not None:
                program.loop_guard = TrueCond()
                program.known_iteration_count = known_iteration_count
                return program

        condition = And(program.loop_guard, condition).simplify()
        program.loop_guard = TrueCond()
        condition.is_loop_guard = True
        if not isinstance(condition, TrueCond):
            program.loop_body = [IfStatem([condition], [statements])]
        return program

    def _try_solve_deterministic_guard(self, program: Program) -> Optional[object]:
        """If program.loop_guard is a bare `var COP threshold` atom, `var` is a pure affine
        self-recurrence (a clock) with a deterministic, non-random ancestry, and its initial value
        is known, solve for the exact iteration count at which the guard fails. Returns None (and
        changes nothing) for anything outside that shape -- the caller falls back to the existing
        guard-to-if-statement conversion unchanged."""
        guard = program.loop_guard
        if not isinstance(guard, Atom) or guard.cop not in ("<", "<="):
            return None
        var, threshold = guard.poly1, guard.poly2
        if not var.is_Symbol:
            return None

        coeff = find_affine_self_recurrence(program.loop_body, var)
        if coeff is None:
            return None
        if not is_fully_deterministic(program.loop_body, {var} | threshold.free_symbols):
            return None

        initial_value = find_initial_value(program.initial, var)
        if initial_value is None:
            return None

        try:
            return solve_affine_guard_crossing(initial_value, coeff, guard.cop, threshold)
        except ValueError:
            return None

    def _collapse_first_level_ifs(self, statements: List) -> Tuple[List, Condition]:
        if len(statements) != 1 or not isinstance(statements[0], IfStatem):
            return statements, TrueCond()

        if_statem: IfStatem = statements[0]
        if len(if_statem.branches) != 1 or if_statem.else_branch:
            return statements, TrueCond()

        branch_statms, branch_cond = self._collapse_first_level_ifs(
            if_statem.branches[0]
        )
        condition = And(branch_cond, if_statem.conditions[0]).simplify()

        return branch_statms, condition
