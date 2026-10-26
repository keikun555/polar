# pWhile-dt on Polar

Runs ProbContLogic's `\pwhiledt` example programs (`paper.tex` §5 / `notes/new-examples.tex`) through
Polar. Three capabilities, exercised in that order below (see `notes/implementation-section-draft.tex`
in ProbContLogic for the actual derived results and how they compare to the paper's claims -- this
file only covers how to run things):

1. **Recurrence finder** (Moosbrugger, Stankovič, Bartocci & Kovács,
   ["This Is the Moment for Probabilistic Loops"](https://dl.acm.org/doi/10.1145/3563341), OOPSLA 2022)
   -- Polar's own exact closed-form moment computation.
2. **Invariant/ranking verification** (`invariant_checker.py`, `ranking_checker.py`, this fork) --
   checks a candidate invariant or ranking function someone already wrote down, rather than deriving
   one from scratch.
3. **Invariant synthesis** (Müllner, Moosbrugger & Kovács,
   ["Strong Invariants Are Hard"](https://dl.acm.org/doi/10.1145/3632872), POPL 2024) -- Polar's
   `--invariants` flag, deriving the complete moment invariant ideal of a goal set.

## Requirements

* Python 3.12 (the pinned dependencies below do not install on newer Pythons)

## Layout

* `pwhiledt/translate.py`: the `\pwhiledt` → `.prob` translator; see its module docstring for the
  semantic mapping (drift/diffuse/sample/clamp) and the Polar-side gotchas it works around
  (identifier mangling for sympy/Polar reserved names; deterministic clock guards, see below)
* `pwhiledt/benchmarks/*.pwhiledt`: the example programs
* `invariant_checker.py`, `ranking_checker.py` (repo root): standalone scripts, same style as
  `translate.py` -- no changes to `polar.py`/`cli/`. See each script's module docstring for usage.
* `pwhiledt/bench.py`: runs every invariant-verification check below and reports wall-clock timing
* `tests/test_invariant_checker.py`, `tests/test_ranking_checker.py`,
  `tests/test_pwhiledt_bench.py`: their tests

## Setup

From the repo root, with Python 3.12 on `PATH`:
```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Recurrence benchmark

Computes Polar's exact closed-form moments for a translated `\pwhiledt` program:
```
.venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/<name>.pwhiledt -o /tmp/<name>.prob
.venv/bin/python polar.py /tmp/<name>.prob --solve_deterministic_guards --goals "E(...)" -N 1
```
Add `--at_n <n>` to evaluate at a concrete iteration when `T`/`dt` are left symbolic.

## Invariant verification benchmark

Checks a candidate invariant or ranking function against Polar's closed forms:
```
.venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/bm1d.pwhiledt -o /tmp/bm1d.prob
.venv/bin/python invariant_checker.py /tmp/bm1d.prob "E(x**2)" "==" "t"
.venv/bin/python ranking_checker.py /tmp/bm1d.prob "v_t - t" --positive dt
```
Run every known-good check for all seven benchmarks at once, with timing:
```
.venv/bin/python pwhiledt/bench.py [--trials N] [-o results.csv]
```
See `invariant_checker.py`/`ranking_checker.py`'s module docstrings for the full CLI and the PASS/
FAIL/UNKNOWN verdict discipline.

## Invariant synthesis benchmark

Derives the complete moment invariant ideal of a goal set -- a Gröbner basis for every polynomial
relation that holds among them at every iteration:
```
.venv/bin/python polar.py /tmp/bm1d.prob --solve_deterministic_guards --invariants \
    --goals "E(x**2)" "E(x)" "E(t)" "E(x**4)" -N 1
```
