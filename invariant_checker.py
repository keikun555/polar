#!/usr/bin/env python3

"""Standalone candidate-invariant checker for pWhile-dt examples translated by pwhiledt/translate.py.

Polar's own `--invariants`/`--goals` (cli/actions/goals_action.py, invariants/invariant_ideal.py)
*derive* invariants from scratch via Gröbner-basis elimination over the goals' closed forms. This
script instead takes a candidate relation the user already wrote down (e.g. from paper.tex) and
checks whether Polar's exact closed-form moments actually confirm it, without deriving anything new.

It reuses Polar's existing machinery directly:
  - recurrences.RecBuilder / recurrences.solver.RecurrenceSolver for exact closed forms
  - cli.common.get_moment_poly for turning a polynomial in program variables into its closed form
  - inputparser.GoalParser._sympify_reals for the real=True symbol-assumption idiom

Usage:
    .venv/bin/python invariant_checker.py <benchmark.prob> "<LHS>" "<OP>" "<RHS>"
        [--solve_deterministic_guards] [--at_n N]

    OP is one of: == <= >= < >
    LHS/RHS are each either `E(<expr>)` (a moment of program variables) or a bare expression in
    the program's untouched parameters (e.g. "dt*n", "0", "E(exp(mu*T))" -- see below).

Examples:
    .venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/bm2d.pwhiledt -o /tmp/bm2d.prob
    .venv/bin/python invariant_checker.py /tmp/bm2d.prob "E((x**2-t)*y)" "==" "0"
    .venv/bin/python invariant_checker.py /tmp/bm1d.prob "E(x**2)" "==" "dt*n" --solve_deterministic_guards
"""

import argparse
import re
import sys
from types import SimpleNamespace

from sympy import Symbol

import settings
from inputparser import GoalParser, parse_program
from program import normalize_program
from recurrences import RecBuilder
from termination.util.poly_utils import get_sign
from cli.common import get_moment_poly
from utils import unpack_piecewise

# Every closed form Polar produces uses this exact (real=True-incompatible!) `n` symbol -- see
# recurrences/solver/{acyclic,cyclic}_solver.py and invariants/invariant_ideal.py. Substituting a
# plain Symbol("n") instead silently fails to match (different assumptions hash differently).
N = Symbol("n", integer=True)

_MOMENT_RE = re.compile(r"^E\((.*)\)$")

# get_moment_poly only needs cli_args.solvability_check; standalone scripts have no full
# argparse.Namespace from Polar's own CLI, so a tiny shim stands in for it.
_CLI_ARGS_SHIM = SimpleNamespace(solvability_check=False)


def _sympify_term(raw):
    """Like GoalParser._sympify_reals, but keeps a literal `n` as the integer=True iteration-count
    symbol every closed form in this codebase uses (recurrences/solver/*.py,
    invariants/invariant_ideal.py) -- real=True and integer=True symbols named "n" compare equal
    but hash differently, so a blanket real=True pass would make "n" never match the closed form."""
    expr = GoalParser._sympify_reals(raw)
    return expr.xreplace({s: N for s in expr.free_symbols if s.name == "n"})


def resolve_term(raw, program, rec_builder, solvers):
    """Returns the exact closed form (in n and the program's parameters) of one candidate term."""
    raw = raw.strip()
    match = _MOMENT_RE.match(raw)
    inner_raw = match.group(1) if match else raw
    expr = _sympify_term(inner_raw)

    if not (expr.free_symbols & program.variables):
        # Pure-parameter expression (e.g. "dt*n", "0", "exp(mu*T)") -- it has no program variable
        # to take an expectation over, so it already *is* its own closed form. Calling into
        # RecBuilder here crashes (KeyError in var_to_index), since parameters aren't loop variables.
        return expr

    moment, is_exact = get_moment_poly(expr, solvers, rec_builder, _CLI_ARGS_SHIM, program)
    if not is_exact:
        print(f"warning: closed form for {raw} is not exact", file=sys.stderr)
    # The n=0 iteration is often a Piecewise special case (e.g. "0 before the loop ever runs");
    # an invariant should hold for every *looping* n, so drop that boundary case the same way
    # invariants/invariant_ideal.py and termination_analyzer.py already do before comparing.
    return unpack_piecewise(moment)


def check_relation(lhs_cf, op, rhs_cf):
    """Returns one of 'PASS', 'FAIL', 'UNKNOWN' for lhs_cf <op> rhs_cf, holding for every n."""
    diff = (lhs_cf - rhs_cf).expand()

    if op == "==":
        verdict = diff.is_zero
        if verdict is True:
            return "PASS"
        if verdict is False:
            return "FAIL"
        return "UNKNOWN"

    # <=, >=, <, > : normalize to "is `diff` (or -diff) always non-negative/positive".
    negate = op in (">=", ">")
    strict = op in ("<", ">")
    signed_diff = -diff if negate else diff

    if signed_diff.is_zero:
        return "FAIL" if strict else "PASS"

    try:
        poly = signed_diff.as_poly()
    except Exception:
        poly = None

    if poly is None:
        # Not a plain polynomial (e.g. it still contains exp(...)/log(...)/etc.) -- honestly
        # report that this checker cannot decide it, rather than guessing.
        return "UNKNOWN"

    sign = get_sign(poly)
    if sign is True:
        return "PASS"
    if sign is False:
        return "FAIL"
    return "UNKNOWN"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("benchmark", help="Path to a .prob file (e.g. output of pwhiledt/translate.py)")
    parser.add_argument("lhs", help="Left-hand side of the candidate, e.g. 'E(x**2)'")
    parser.add_argument("op", choices=["==", "<=", ">=", "<", ">"], help="Relation between LHS and RHS")
    parser.add_argument("rhs", help="Right-hand side of the candidate, e.g. 'dt*n'")
    parser.add_argument(
        "--solve_deterministic_guards",
        action="store_true",
        default=False,
        help="Solve a deterministic clock guard (e.g. 't < T') for its exact crossing iteration count",
    )
    parser.add_argument(
        "--at_n",
        type=int,
        default=-1,
        help="Also evaluate and check the candidate at this concrete iteration number",
    )
    args = parser.parse_args()

    settings.solve_deterministic_guards = args.solve_deterministic_guards

    program = parse_program(args.benchmark)
    program = normalize_program(program)
    rec_builder = RecBuilder(program)
    solvers = {}

    lhs_cf = resolve_term(args.lhs, program, rec_builder, solvers)
    rhs_cf = resolve_term(args.rhs, program, rec_builder, solvers)

    verdict = check_relation(lhs_cf, args.op, rhs_cf)
    print(f"{args.lhs} {args.op} {args.rhs}")
    print(f"  LHS closed form: {lhs_cf}")
    print(f"  RHS closed form: {rhs_cf}")
    print(f"  Holds for every iteration n: {verdict}")

    known_iteration_count = getattr(program, "known_iteration_count", None)
    at_n = args.at_n if args.at_n >= 0 else None
    if at_n is None and known_iteration_count is not None and not known_iteration_count.free_symbols:
        at_n = int(known_iteration_count)

    if at_n is not None:
        at_n_verdict = check_relation(lhs_cf.subs({N: at_n}), args.op, rhs_cf.subs({N: at_n}))
        print(f"  Holds as a postcondition at n={at_n}: {at_n_verdict}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
