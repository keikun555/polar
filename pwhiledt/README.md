# pWhile-dt → Polar translator

Translates ProbContLogic's `\pwhiledt` program-listing syntax (paper.tex / notes/new-examples.tex)
into Polar's `.prob` input language, so Polar's exact closed-form moment engine can be run against
these examples directly.

See `translate.py`'s module docstring for the semantic mapping (drift/diffuse/sample/clamp) and the
Polar-side gotchas it works around (identifier mangling for sympy/Polar reserved names; the loop's
clock guard, e.g. `t < T`, is emitted literally and solved by Polar itself via
`--solve_deterministic_guards`, added to this fork specifically for this -- see below).

Usage:

```
.venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/<name>.pwhiledt -o /tmp/<name>.prob
.venv/bin/python polar.py /tmp/<name>.prob --solve_deterministic_guards --goals "E(...)" -N 1
```

With `T`/`dt` left symbolic (the usual case, to get a general-in-`T`/`dt` result), Polar solves the
guard (no crash, no rejection) but can't auto-evaluate at a concrete `n` since the crossing point
itself stays symbolic -- pass `--at_n <n>` explicitly for that, substituting `n = T/dt` by hand, same
as before this feature existed. With `T`/`dt` both concrete numbers, `--at_n` isn't needed at all:
the exact crossing count is solved and applied automatically.

## Known limitations

**Resolved:** a loop guard on a purely deterministic clock (`t < T`, `t` updated only by
`t := t + dt`, never touched by any distribution) used to be rejected outright -- `main` with a clean
`NormalizingException`, `ost-extension` with an unhandled `KeyError` (a bug in how it reported the
same rejection, fixed separately). Neither rejection was actually necessary for this specific,
common case: `--solve_deterministic_guards` (this fork only, see `program/transformer/
deterministic_guard.py`, `LoopGuardTransformer`) now detects a guard whose variable's entire update
ancestry is free of randomness and solves it for its exact crossing iteration count instead.

**Still open:** an absorbing/reflecting/region-switching mechanism -- an explicit `if` branching on
a variable that itself diffuses randomly, or a clamp baked into a drift/diffusion coefficient (e.g.
`driftL`'s `min(2,max(-2,w))`) -- is **not translatable today**, and the guard fix above does not
touch this. Polar's `ConditionsNormalizer` can only abstract a branch condition into a Bernoulli
when that condition's truth probability is iteration-independent (a sound requirement: the
probability of e.g. `x>=0` for a diffusing `x` genuinely changes with the iteration count, so
collapsing it to a single constant-p Bernoulli would be unsound -- unlike the deterministic-clock
case above, there is no single crossing point to solve for here). This blocks every
boundary-mechanism example in both documents: `RBM`/`RBM2D`, `AbsorbedBM`,
`OscillatingBM`/`OBMDrift`, `Poll`, `StickyBM`/`StickyGBM`, `VanDerPol`,
`PeriodicallyForcedBistable`, `SlowFastFitzHughNagumo`, `FHNFastNoise`, and the five `Cmpct`-clamped
examples (`EpidemicSIS`, `DrawdownGBM`, `ReflectedGBM`, `DividendBarrierRBM`, `RestrictedBessel`).
The `termination` branch's `BranchBuilder`/`compute_bounds_of_expr` (bounds per possible
update-branch, no exact probability needed) looks like the right building block to relax this
properly; not yet investigated to completion.

## Validated examples (7/23 across paper.tex §5 and notes/new-examples.tex)

All of the following have no boundary mechanism and are confirmed working end to end, with Polar's
exact output checked against the paper's/addendum's own claimed result. The "Checked via" column
gives the exact `invariant_checker.py` verdict for a candidate matching that claim -- see
`invariant_checker.py`/`ranking_checker.py` below for what these standalone scripts do and why a
verdict of `PASS` is a real check (not an eyeballed comparison) while `UNKNOWN` is an honestly
reported gap, never a false `PASS`:

| Benchmark | Goal | Polar's exact closed form | Matches | Checked via `invariant_checker.py` |
|---|---|---|---|---|
| `bm1d.pwhiledt` (`prog:1bm`) | `E(x**2)` | `dt*n` | paper: `E[x^2]=T` | `PASS` |
| `bm2d.pwhiledt` (`prog:2bm`) | `E(x**2+y**2)` | `2*dt*n` | paper: `E[\|\|(x,y)\|\|^2]=2T` | `PASS` |
| `bm3d.pwhiledt` (`prog:3bm`) | `E(x**2+y**2+z**2)` | `3*dt*n` | paper: `3T` | `PASS` |
| `bm2d.pwhiledt` | `E((x**2-t)*y)` | `0` (exact, every n) | new-examples \S1: exact conservation | `PASS` |
| `bm3d.pwhiledt` | `E((x**2-t)*y*z)` | `0` (exact, every n) | new-examples \S1: exact conservation | `PASS` |
| `gbm.pwhiledt` (`prog:gbm`) | `E(s)` | `(1+mu*dt)**n` | exact GBM discrete mean | `PASS` |
| `ou_process.pwhiledt` (`prog:ou-process`) | `E(m)` | closed form converging to `mu` | OU mean-reversion: `mu*(1-(1-theta*dt)**n)` | `UNKNOWN` (see below) |
| `integrated_langevin.pwhiledt` (new-examples \S3) | `E(x**2+v**2)` | exact closed form in `n` | stronger than the paper's Gronwall bound (linear system, solved exactly) | `PASS` (self-equality sanity check) |

Example commands (`PASS` rows):
```
.venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/bm1d.pwhiledt -o /tmp/bm1d.prob
.venv/bin/python invariant_checker.py /tmp/bm1d.prob "E(x**2)" "==" "dt*n" --solve_deterministic_guards

.venv/bin/python pwhiledt/translate.py pwhiledt/benchmarks/bm2d.pwhiledt -o /tmp/bm2d.prob
.venv/bin/python invariant_checker.py /tmp/bm2d.prob "E((x**2-t)*y)" "==" "0" --solve_deterministic_guards
```

The clock remainder `v_t - t` -- the natural ranking function for every example's deterministic
clock guard -- is confirmed decreasing by exactly `dt` each iteration via `ranking_checker.py`:
```
.venv/bin/python ranking_checker.py /tmp/bm1d.prob "v_t - t" --positive dt --solve_deterministic_guards
```

**Two real, honestly-reported gaps in what `invariant_checker.py` can automatically decide** (both
return `UNKNOWN`, never a false `PASS`):
- **Comparisons against a literal `exp(...)` of a continuous parameter.** E.g. the GBM/OU mean and
  variance bounds in paper.tex rely on the inequality `1+x <= exp(x)`, comparing a discrete closed
  form like `(1+mu*dt)**n` against `exp(mu*T)`. The checker has no notion of this inequality and
  correctly refuses to guess: `invariant_checker.py /tmp/gbm.prob "E(m)" "<=" "E(exp(mu*v_t))"
  --solve_deterministic_guards` reports `UNKNOWN`.
- **Exponentials with mixed symbolic-integer exponents.** The OU process's own exact closed form for
  `E(m)` is algebraically equal to `mu*(1-(1-theta*dt)**n)` (confirmed numerically at several `n`),
  but neither `sympy`'s `.expand()`/`.simplify()` nor `.equals()` can prove this symbolically --
  terms like `(-dt*theta+1)**(2*n-1)` vs. `(-dt*theta+1)**n` don't combine automatically when the
  exponent itself contains the free symbol `n`. This is a real limit of the underlying CAS, not a
  shortcut taken by this checker.

`rotational3dbm.pwhiledt` has no boundary mechanism either, but hits a *different*, unrelated wall:
sympy can't find closed-form roots of the coupled 3-variable characteristic polynomial symbolically
in both `dt` and `tau` at once (`NotImplementedError: sorted roots not supported over ZZ[dt,tau]`).
Untried: holding one of `dt`/`tau` numeric, or `--numeric_roots`. Since `invariant_checker.py` needs
a closed form to substitute into, this benchmark is untestable by it regardless.

## Candidate checking: `invariant_checker.py` / `ranking_checker.py`

Two standalone scripts at the repo root (same pattern as `translate.py`: their own small `argparse`,
no changes to `polar.py`/`cli/`) that *check* a candidate invariant or ranking function someone
already wrote down, rather than deriving one from scratch the way `--invariants`/`--termination` do.
See each script's module docstring for full usage, and the table above for worked examples.
