#!/usr/bin/env python3

"""Standalone candidate-ranking-function checker for pWhile-dt examples translated by
pwhiledt/translate.py.

Polar's --termination/--termination_smt/--termination_amber (termination/termination_analyzer.py)
synthesize a termination witness for the loop guard itself. This script instead takes a candidate
decreasing (or increasing) expectation the user already wrote down -- e.g. paper.tex's e_d -- and
checks whether it really changes by a fixed, favorable amount every iteration, using Polar's own
one-step recurrence construction (the same primitive unsolvable_analysis/unsolv_inv_synthesizer.py
uses to build candidate recurrences).

Scope: this only confirms an *unconditional* per-iteration decrease/increase (the delta does not
itself depend on a loop variable) -- exactly the case for every translated example's natural ranking
function, the clock remainder "v_t - t" (decreases by exactly "dt" each step, independent of the
loop guard). A candidate whose delta is guard-dependent is reported UNKNOWN rather than attempting
an unsound guess; boundedness-below is not separately checked (the candidates checked here are the
clock remainder itself, whose boundedness is already established by solving the deterministic
guard's exact crossing point -- this script always does so, see below).

Usage:
    .venv/bin/python ranking_checker.py <benchmark.prob> "<candidate>"
        [--direction decreasing|increasing] [--positive PARAM ...]

`--positive` asserts a parameter (e.g. "dt") is strictly positive -- Polar's own parameter symbols
carry no domain assumptions, so without this a step size is, correctly, treated as an unconstrained
real and the checker reports UNKNOWN rather than guessing its sign.

Every pwhiledt example has a deterministic clock guard, so this script always solves it
(settings.solve_deterministic_guards = True unconditionally) -- there is no benchmark in this
project without one, so this isn't exposed as a flag.

Example:
    .venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/bm1d.pwhiledt -o /tmp/bm1d.prob
    .venv/bin/python ranking_checker.py /tmp/bm1d.prob "v_t - t" --positive dt
"""

import argparse
import sys

from sympy import Symbol

import settings
from inputparser import GoalParser, parse_program
from program import normalize_program
from recurrences import RecBuilder
from termination.util.poly_utils import get_sign

N = Symbol("n", integer=True)


def _sympify_term(raw):
    """Same real=True-but-keep-n-as-integer idiom as invariant_checker.py's _sympify_term."""
    expr = GoalParser._sympify_reals(raw)
    return expr.xreplace({s: N for s in expr.free_symbols if s.name == "n"})


def check_ranking(candidate, direction, program, rec_builder, positive_params=()):
    """Returns (verdict, detail) where verdict is one of 'PASS', 'FAIL', 'UNKNOWN'.

    `positive_params` names parameters the *caller* asserts are strictly positive (e.g. "dt", a
    discretization step). Polar's own parameter symbols carry no domain assumptions (Program.__init__
    only ever creates Symbol(name, real=True)), so without this a step size like "dt" is, correctly,
    an unconstrained real as far as sign analysis is concerned -- this lets the caller supply exactly
    the background assumption a human proof would also need, rather than the tool silently guessing
    it. Swapping the symbol's assumptions happens only after `delta` is already computed, by name,
    the same way tests/common.py's assert_specified_proportional reconciles mismatched-assumption
    symbols elsewhere in this codebase."""
    candidate_vars = sorted(candidate.free_symbols & program.variables, key=str)
    one_step = rec_builder.get_recurrence_poly(candidate, candidate_vars)

    if direction == "decreasing":
        delta = (candidate - one_step).expand()
    else:
        delta = (one_step - candidate).expand()

    if positive_params:
        positive_syms = {name: Symbol(name, real=True, positive=True) for name in positive_params}
        delta = delta.xreplace(
            {s: positive_syms[s.name] for s in delta.free_symbols if s.name in positive_syms}
        )

    loop_vars_in_delta = delta.free_symbols & program.variables
    if loop_vars_in_delta:
        return "UNKNOWN", (
            f"delta per iteration ({delta}) still depends on loop variable(s) "
            f"{sorted(loop_vars_in_delta, key=str)}; this checker only decides an unconditional "
            f"(guard-independent) decrease/increase"
        )

    if delta.is_extended_positive:
        sign = True
    elif delta.is_extended_negative:
        sign = False
    else:
        # poly_utils.get_sign's zero-finding assumes the full real line is in play (it samples the
        # poly at 0 once no zero is found): that reasoning breaks for a positive=True-constrained
        # symbol, since excluding 0 is exactly *why* no zero was found there. The direct Expr-level
        # check above handles that case correctly; this Poly-based fallback is for everything else
        # (e.g. a genuine multi-term polynomial with no asserted-positive symbols at all).
        try:
            poly = delta.as_poly()
        except Exception:
            poly = None
        sign = get_sign(poly) if poly is not None else None

    if sign is True:
        return "PASS", f"delta per iteration is always positive: {delta}"
    if sign is False:
        return "FAIL", f"delta per iteration is always non-positive: {delta}"
    return "UNKNOWN", f"delta per iteration ({delta}) does not have a constant sign"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("benchmark", help="Path to a .prob file (e.g. output of pwhiledt/translate.py)")
    parser.add_argument("candidate", help="Candidate ranking function, e.g. 'v_t - t'")
    parser.add_argument("--direction", choices=["decreasing", "increasing"], default="decreasing")
    parser.add_argument(
        "--positive",
        nargs="*",
        default=[],
        metavar="PARAM",
        help="Parameters asserted to be strictly positive (e.g. 'dt'), since Polar's own parameter "
        "symbols carry no domain assumptions by default",
    )
    args = parser.parse_args()

    settings.solve_deterministic_guards = True

    program = parse_program(args.benchmark)
    program = normalize_program(program)
    rec_builder = RecBuilder(program)

    candidate = _sympify_term(args.candidate)
    verdict, detail = check_ranking(candidate, args.direction, program, rec_builder, args.positive)

    print(f"Candidate ranking function: {args.candidate} ({args.direction})")
    print(f"  {detail}")
    print(f"  Verdict: {verdict}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
