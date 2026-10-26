# If true, transform categorical assignments into multiple individual assignments
transform_categoricals: bool = False

# If set converts all conditions to arithmetic ahead of the main computation
cond2arithm: bool = False

# If true there won't be automatic type inference
disable_type_inference: bool = False

# Number of iterations in the fixedpoint computation of the type inference
type_fp_iterations: int = 100

# If true, the roots in the recurrence computation will be computed numerically
numeric_roots: bool = False

# If true, the complex roots in the recurrence computation will be computed numerically
numeric_croots: bool = False

# Interval epsilon for the potential approximation of roots
numeric_eps: float = 1e-10

# If set any loop guard will be overridden with 'true'
trivial_guard: bool = False

# If set, a loop guard that depends only on deterministic (non-probabilistic) variables updated by
# a pure affine self-recurrence (e.g. a clock `t := t + dt`) is solved for its exact crossing
# iteration count instead of being rejected by ConditionsNormalizer; see
# program/transformer/deterministic_guard.py and LoopGuardTransformer.
solve_deterministic_guards: bool = False

# If true, moments of functions of distributions which would be transcendental won't be approximated by rationals
exact_func_moments: bool = False
