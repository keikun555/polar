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
exact output checked against the paper's/addendum's own claimed result:

| Benchmark | Goal | Polar's exact closed form | Matches |
|---|---|---|---|
| `bm1d.pwhiledt` (`prog:1bm`) | `E(x**2)` | `dt*n` | paper: `E[x^2]=T` |
| `bm2d.pwhiledt` (`prog:2bm`) | `E(x**2+y**2)` | `2*dt*n` | paper: `E[\|\|(x,y)\|\|^2]=2T` |
| `bm3d.pwhiledt` (`prog:3bm`) | `E(x**2+y**2+z**2)` | `3*dt*n` | paper: `3T` |
| `bm2d.pwhiledt` | `E((x**2-t)*y)` | `0` (exact, every n) | new-examples \S1: exact conservation |
| `bm3d.pwhiledt` | `E((x**2-t)*y*z)` | `0` (exact, every n) | new-examples \S1: exact conservation |
| `gbm.pwhiledt` (`prog:gbm`) | `E(s)` | `(1+mu*dt)**n` | exact GBM discrete mean |
| `ou_process.pwhiledt` (`prog:ou-process`) | `E(x)` | closed form converging to `mu` | OU mean-reversion |
| `integrated_langevin.pwhiledt` (new-examples \S3) | `E(x**2+v**2)` | exact closed form in `n` | stronger than the paper's Gronwall bound (linear system, solved exactly) |

`rotational3dbm.pwhiledt` has no boundary mechanism either, but hits a *different*, unrelated wall:
sympy can't find closed-form roots of the coupled 3-variable characteristic polynomial symbolically
in both `dt` and `tau` at once (`NotImplementedError: sorted roots not supported over ZZ[dt,tau]`).
Untried: holding one of `dt`/`tau` numeric, or `--numeric_roots`.
