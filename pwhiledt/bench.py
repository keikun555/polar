#!/usr/bin/env python3

"""Timing table for the pwhiledt examples.

Runs pwhiledt/translate.py plus the known-good invariant_checker.py /
ranking_checker.py invocations from pwhiledt/README.md's "Validated examples" table, and reports
wall-clock time for each step.

This is deliberately *not* WhileDT-style (brench.py): that harness earns its TOML configs and
multi-trial CPU-time averaging by comparing several interchangeable SMT backends (Z3/cvc5/dReal)
across dozens of programs that can time out or flake. We have one backend (sympy, via Polar) and
seven examples with no timeouts to worry about -- a full solver-comparison harness would be pure
overhead. This script is the minimum that still produces a timing table for the paper.

Usage:
    .venv/bin/python pwhiledt/bench.py [--trials N] [-o results.csv]
"""

import argparse
import csv
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = REPO_ROOT / "pwhiledt" / "benchmarks"
PYTHON = sys.executable

# Each entry: benchmark stem -> list of (label, script, extra_args). `--solve_deterministic_guards`
# is appended automatically; the benchmark's translated .prob path is inserted as the first
# positional argument. These are exactly the commands pwhiledt/README.md's examples table cites.
CHECKS = {
    "bm1d": [
        ("invariant: E(x**2)==dt*n", "invariant_checker.py", ["E(x**2)", "==", "dt*n"]),
        ("ranking: v_t - t", "ranking_checker.py", ["v_t - t", "--positive", "dt"]),
    ],
    "bm2d": [
        ("invariant: E(x**2+y**2)==2*dt*n", "invariant_checker.py", ["E(x**2+y**2)", "==", "2*dt*n"]),
        ("invariant: E((x**2-t)*y)==0", "invariant_checker.py", ["E((x**2-t)*y)", "==", "0"]),
        ("ranking: v_t - t", "ranking_checker.py", ["v_t - t", "--positive", "dt"]),
    ],
    "bm3d": [
        ("invariant: E(x**2+y**2+z**2)==3*dt*n", "invariant_checker.py", ["E(x**2+y**2+z**2)", "==", "3*dt*n"]),
        ("invariant: E((x**2-t)*y*z)==0", "invariant_checker.py", ["E((x**2-t)*y*z)", "==", "0"]),
        ("ranking: v_t - t", "ranking_checker.py", ["v_t - t", "--positive", "dt"]),
    ],
    "gbm": [
        ("invariant: E(s)==(1+mu*dt)**n", "invariant_checker.py", ["E(s)", "==", "(1+mu*dt)**n"]),
        ("ranking: v_t - t", "ranking_checker.py", ["v_t - t", "--positive", "dt"]),
    ],
    "ou_process": [
        ("ranking: v_t - t", "ranking_checker.py", ["v_t - t", "--positive", "dt"]),
    ],
    "integrated_langevin": [
        ("invariant: E(x**2+v**2)==E(x**2+v**2)", "invariant_checker.py", ["E(x**2+v**2)", "==", "E(x**2+v**2)"]),
        ("ranking: v_t - t", "ranking_checker.py", ["v_t - t", "--positive", "dt"]),
    ],
}


def time_command(cmd, trials):
    """Returns (times, last_result). Does not raise on nonzero exit -- a checker can legitimately
    exit 1 (e.g. an UNKNOWN verdict); the caller inspects stdout for the verdict regardless."""
    times = []
    result = None
    for _ in range(trials):
        start = time.perf_counter()
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        times.append(time.perf_counter() - start)
    return times, result


def extract_verdict(stdout):
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Verdict:") or line.startswith("Holds for every iteration n:"):
            return line
    return "(no verdict line found)"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=3, help="Repetitions per step, timing is the mean")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Also write results as CSV to this path")
    args = parser.parse_args()

    rows = []  # (benchmark, step, mean_seconds, stdev_seconds, trials, verdict)

    for stem, checks in CHECKS.items():
        pwhiledt_path = BENCHMARKS_DIR / f"{stem}.pwhiledt"
        prob_path = Path(f"/tmp/{stem}.prob")

        translate_cmd = [PYTHON, "pwhiledt/translate.py", str(pwhiledt_path), "-o", str(prob_path)]
        times, result = time_command(translate_cmd, args.trials)
        if result.returncode != 0:
            print(f"warning: translating {stem} failed: {result.stderr}", file=sys.stderr)
        rows.append((stem, "translate", times, None))

        for label, script, extra_args in checks:
            cmd = [PYTHON, script, str(prob_path), *extra_args, "--solve_deterministic_guards"]
            times, result = time_command(cmd, args.trials)
            verdict = extract_verdict(result.stdout)
            rows.append((stem, label, times, verdict))

    print_table(rows, args.trials)
    if args.output:
        write_csv(rows, args.output)
        print(f"\nWrote {args.output}")


def print_table(rows, trials):
    header = f"{'Benchmark':<22} {'Step':<38} {'Mean (s)':>9} {'Stdev':>7}  Verdict"
    print(header)
    print("-" * len(header))
    total = 0.0
    for stem, label, times, verdict in rows:
        mean = statistics.mean(times)
        stdev = statistics.stdev(times) if len(times) > 1 else 0.0
        total += mean
        verdict_str = "" if verdict is None else verdict
        print(f"{stem:<22} {label:<38} {mean:>9.3f} {stdev:>7.3f}  {verdict_str}")
    print("-" * len(header))
    print(f"Total (mean, {trials} trial(s) each): {total:.3f}s")


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["benchmark", "step", "mean_seconds", "stdev_seconds", "trials", "verdict"])
        for stem, label, times, verdict in rows:
            mean = statistics.mean(times)
            stdev = statistics.stdev(times) if len(times) > 1 else 0.0
            writer.writerow([stem, label, f"{mean:.4f}", f"{stdev:.4f}", len(times), verdict or ""])


if __name__ == "__main__":
    main()
