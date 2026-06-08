#!/usr/bin/env python3
"""Curve-comparison promotion gate for the scaling track.

This is the cost-CURVE analogue of `beats_best.py` (which compares single-tier
op-counts — *points*). Here a submission is the artifact `scaling.json` produced
by `scaling_battery.py`: a fitted cost law `group_ops ≈ c · n^alpha` with a
held-out prediction check. The gate ranks *algorithms*, not instances:

  GATE 0 (proof).   The candidate's held-out prediction must have VERIFIED.
                    An unproven fit (overfit / lucky / mispredicting) can never
                    be a record — exactly as an invalid k can't be in beats_best.

  GATE 1 (exponent). Lower alpha wins when the 95% CIs are DISJOINT. A candidate
                    whose alpha CI lies entirely below the baseline's is
                    asymptotically faster — the only thing that means "a faster
                    algorithm." (In the generic arena Shoup pins alpha=0.5, so
                    this gate is normally a tie and the constant decides.)

  GATE 2 (constant). When the exponent CIs OVERLAP (statistically tied alpha),
                    the lower constant `c` wins — the existing 0.71×-style
                    constant-factor game, now correctly demoted to the tiebreak.

    python3 tools/beats_curve.py                                  # ./scaling.json vs ./scaling.baseline.json
    python3 tools/beats_curve.py --score scaling.json --against scaling.baseline.json
    python3 tools/beats_curve.py --against <(git show origin/main:scaling.json)

Exit codes:  0 = ACCEPT (new record / inaugural)   1 = REJECT   2 = bad input
Pure stdlib.
"""
import argparse
import json
import sys
from pathlib import Path


def load(path):
    d = json.loads(Path(path).read_text())
    fit = d.get("fit", {})
    hold = d.get("holdout", {})
    a_ci = fit.get("alpha_ci95") or [None, None]
    return {
        "alpha": fit.get("alpha"),
        "alpha_lo": a_ci[0],
        "alpha_hi": a_ci[1],
        "c": fit.get("c"),
        "holdout_pass": bool(hold.get("pass")),
        "holdout_bits": hold.get("bits"),
        "z": hold.get("z"),
        "seed": d.get("seed"),
    }


def _fmt(s):
    return (f"α={s['alpha']:.4f} [{s['alpha_lo']:.4f},{s['alpha_hi']:.4f}]  "
            f"c={s['c']:.4f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Curve-comparison beats-best gate for the scaling track.")
    ap.add_argument("--score", default="scaling.json", help="candidate scaling.json (default: ./scaling.json)")
    ap.add_argument("--against", default="scaling.baseline.json",
                    help="the curve to beat (default: ./scaling.baseline.json)")
    args = ap.parse_args(argv)

    try:
        cand = load(args.score)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"!! cannot read candidate {args.score}: {e}", file=sys.stderr)
        return 2
    if cand["alpha"] is None or cand["c"] is None:
        print(f"!! candidate {args.score} has no fit.alpha / fit.c — run scaling_battery.py first", file=sys.stderr)
        return 2

    # GATE 0 — the cost law must have predicted its own held-out rung.
    if not cand["holdout_pass"]:
        print("REJECT — held-out prediction did NOT verify "
              f"(bits={cand['holdout_bits']}, z={cand['z']}).")
        print("  An unproven fit is not a cost law; it cannot be a record.")
        print(f"  candidate : {_fmt(cand)}")
        return 1

    base_path = Path(args.against)
    try:
        base_text = base_path.read_text() if base_path.exists() else ""
    except OSError:
        base_text = ""
    # An absent OR empty baseline (e.g. `git show` of a not-yet-committed scaling.json,
    # or /dev/null) means there is no record to beat — this is the inaugural one.
    if not base_text.strip():
        print(f"ACCEPT — inaugural verified cost law (no baseline at {args.against})")
        print(f"  candidate : {_fmt(cand)}   holdout ✅")
        return 0
    try:
        base = load(args.against)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"!! cannot read baseline {args.against}: {e}", file=sys.stderr)
        return 2

    if cand.get("seed") != base.get("seed"):
        print(f"!! WARNING: candidate seed ({cand.get('seed')}) != baseline seed "
              f"({base.get('seed')}); compare curves graded on the SAME sealed seed "
              f"for a paired comparison.", file=sys.stderr)

    print(f"  candidate : {_fmt(cand)}   holdout ✅")
    print(f"  baseline  : {_fmt(base)}")

    # GATE 1 — exponent: disjoint CIs decide.
    if cand["alpha_hi"] < base["alpha_lo"]:
        print(f"\nACCEPT — strictly faster EXPONENT 🏆")
        print(f"  candidate α CI [{cand['alpha_lo']:.4f},{cand['alpha_hi']:.4f}] lies entirely below")
        print(f"  baseline  α CI [{base['alpha_lo']:.4f},{base['alpha_hi']:.4f}] — an asymptotic win.")
        return 0
    if base["alpha_hi"] < cand["alpha_lo"]:
        print(f"\nREJECT — slower exponent (candidate α CI lies entirely ABOVE the baseline's).")
        return 1

    # GATE 2 — exponents statistically tied: the constant decides.
    print(f"\n  exponents statistically tied (α CIs overlap) — comparing the constant c.")
    if cand["c"] < base["c"]:
        gain = (base["c"] - cand["c"]) / base["c"] * 100
        print(f"ACCEPT — same exponent, lower CONSTANT 🏆  ({gain:.2f}% smaller c)")
        return 0
    if cand["c"] > base["c"]:
        print(f"REJECT — same exponent, higher constant ({cand['c']:.4f} ≥ {base['c']:.4f}).")
        return 1
    print("REJECT — identical curve; a tie does not beat the record.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
