from typing import List, Optional, Set

from sympy import Expr, Symbol, diff

from program.assignment import Assignment, PolyAssignment, DistAssignment, FunctionalAssignment
from program.ifstatem import IfStatem


def iter_assignments(statements: List, enclosing_conditions=()):
    """Recursively yields (assignment, enclosing_conditions) pairs for every Assignment in a
    (possibly still-nested, pre-IfTransformer) statement list -- a loop body, or the pre-loop
    `initial` block, both of which can contain Assignment subclass instances and IfStatem
    instances at any nesting depth -- matching IfStatem's own
    children = ["branches", "else_branch"] recursion. `enclosing_conditions` accumulates the
    Conditions of every IfStatem an assignment is nested inside, since an assignment's resulting
    value can depend on those conditions' free symbols even when its own RHS does not (e.g. a flag
    flipped only inside `if x > 1: ...`, whose randomness comes entirely from `x` appearing in the
    guard, not in the flag's own `:= 0`/`:= 1` assignment)."""
    for s in statements:
        if isinstance(s, IfStatem):
            for i, branch in enumerate(s.branches):
                yield from iter_assignments(
                    branch, enclosing_conditions + (s.conditions[i],)
                )
            if s.else_branch:
                yield from iter_assignments(
                    s.else_branch, enclosing_conditions + tuple(s.conditions)
                )
        else:
            yield s, enclosing_conditions


def find_affine_self_recurrence(loop_body: List, var: Symbol) -> Optional[Expr]:
    """If `var` is updated, everywhere in `loop_body`, by exactly `var := var + c` for some fixed
    `c` not containing `var` (coefficient of `var` is exactly 1 -- a pure affine self-recurrence,
    the clock-variable pattern `t += dt` compiles to), return `c`. Returns None for anything else:
    no update found, a genuinely probabilistic update (DistAssignment, or a PolyAssignment with
    more than one polynomial), a FunctionalAssignment, a non-affine or non-unit-coefficient
    polynomial update, or inconsistent updates to `var` across different branches."""
    found: Optional[Expr] = None
    for assign, enclosing_conditions in iter_assignments(loop_body):
        if assign.variable != var:
            continue
        if enclosing_conditions:
            return None
        if not isinstance(assign, PolyAssignment):
            return None
        if len(assign.polynomials) != 1:
            return None
        poly = assign.polynomials[0]
        if diff(poly, var) != 1:
            return None
        c = (poly - var).expand()
        if var in c.free_symbols:
            return None
        if found is not None and found != c:
            return None
        found = c
    return found


def is_fully_deterministic(loop_body: List, start_vars: Set[Symbol]) -> bool:
    """True iff every variable in `start_vars`, and transitively every variable referenced by
    their updates, is updated only via deterministic PolyAssignments (never a DistAssignment, and
    never a FunctionalAssignment of a non-constant argument) -- i.e. the whole ancestry is free of
    any randomness. A variable with no assignment anywhere in `loop_body` is treated as an
    external, leaf parameter (trivially deterministic)."""
    seen: Set[Symbol] = set()
    frontier: Set[Symbol] = set(start_vars)
    while frontier:
        v = frontier.pop()
        if v in seen:
            continue
        seen.add(v)
        for assign, enclosing_conditions in iter_assignments(loop_body):
            if assign.variable != v:
                continue
            for cond in enclosing_conditions:
                frontier |= cond.get_free_symbols() - seen
            if isinstance(assign, DistAssignment):
                return False
            if isinstance(assign, FunctionalAssignment):
                if not assign.argument.is_Number:
                    return False
                continue
            if isinstance(assign, PolyAssignment):
                if len(assign.polynomials) > 1:
                    return False
                frontier |= assign.polynomials[0].free_symbols - seen
    return True


def find_initial_value(initial: List, var: Symbol) -> Optional[Expr]:
    """Returns `var`'s initial value if `initial` (program.initial, the pre-loop assignments)
    assigns it exactly once via an unconditional, single-polynomial (deterministic) PolyAssignment
    -- the only shape a loop-guard clock's own initialization uses in practice. Returns None for
    anything else (no initializer found, more than one, probabilistic, or conditioned)."""
    found: Optional[Expr] = None
    for assign, enclosing_conditions in iter_assignments(initial):
        if assign.variable != var:
            continue
        if enclosing_conditions:
            return None
        if not isinstance(assign, PolyAssignment) or len(assign.polynomials) != 1:
            return None
        if found is not None:
            return None
        found = assign.polynomials[0]
    return found
