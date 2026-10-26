from sympy import S, ceiling, floor, symbols, summation, sympify
from utils import without_piecewise, get_unique_var


def solve_rec_by_summing(rec_coeff, init_value, inhom_part):
    n = None
    for item in inhom_part.free_symbols:
        if str(item) == "n":
            n = item
    if n is None:
        n = symbols("n", integer=True)
    hom_solution = (rec_coeff**n) * init_value
    k = symbols(get_unique_var("k"), integer=True)
    summand = ((rec_coeff**k) * inhom_part.xreplace({n: n - k})).simplify()
    particular_solution = summation(summand, (k, 0, (n - 1)))
    particular_solution = without_piecewise(particular_solution)
    return (hom_solution + particular_solution).simplify()


def solve_affine_guard_crossing(initial_value, coeff, cop, threshold):
    """Given the exact closed form `f(k) = initial_value + k*coeff` of a deterministic, purely
    affine self-recurrence (see program/transformer/deterministic_guard.py -- `coeff` is exactly
    what find_affine_self_recurrence returns, and `solve_rec_by_summing(1, initial_value, coeff)`
    already gives this same closed form), solve the loop guard `f(k) <cop> threshold` for the exact
    number of iterations k* the loop runs before the guard first fails -- i.e. the smallest k >= 0
    at which `f(k)` violates the guard.

    `coeff`'s sign decides the direction. When it can't be determined (the common case: `coeff` is
    a bare symbol like `dt` with no positivity assumption -- every pwhiledt clock is represented
    this way, see Semantics.lean's drift/diffuse atoms, which always treat dt as the positive time
    step, never asserted as a sympy assumption), this function treats it as positive, matching
    every actual pwhiledt guard (`t < T` with `t += dt`). When `coeff` is concretely non-positive,
    `f` is non-increasing, so a `<`/`<=` guard that holds at k=0 never fails (f can only move
    further below threshold) -- there is no finite crossing point, and this is a genuinely
    different (never-terminating, for this guard alone) shape, not a mirrored ceiling/floor
    formula; this function raises in that case rather than returning a wrong answer.
    """
    if cop not in ("<", "<="):
        raise ValueError(f"Unsupported comparison operator: {cop!r}")

    initial_value = sympify(initial_value)
    coeff = sympify(coeff)
    threshold = sympify(threshold)

    if bool(coeff.is_negative):
        holds_at_zero = (initial_value < threshold) if cop == "<" else (initial_value <= threshold)
        if not bool(holds_at_zero):
            return S.Zero
        raise ValueError(
            "guard holds at k=0 with a non-increasing affine variable: it never fails, so there "
            "is no finite crossing point"
        )

    bound = (threshold - initial_value) / coeff
    return ceiling(bound) if cop == "<" else floor(bound) + 1
