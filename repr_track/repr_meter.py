#!/usr/bin/env python3
"""Representation-track meter — score a non-generic ECDLP algorithm's cost CURVE.

This is the scaling track's twin for the representation track: where the arena
hides the curve (forcing generic play, α≡0.5 by Shoup), this **publishes** it and
asks whether any method bends the exponent **below** 0.5. It scores the *cost law*,
not a single solved instance, with two complementary meters:

  b1 (SCORED, authoritative) — COUNTED FIELD OPS. The solver runs against a metered
        `F_p` (`counted_field.py`); the harness re-executes it and fits
        field_ops ≈ c·n^α across a ladder, held-out-verified. Deterministic,
        hardware-independent, reproducible. Cooperative: gameable by arithmetic done
        off-API (a solver that under-counts looks sub-√n without being faster).

  b2 (CORROBORATOR) — SAME-HARDWARE RHO RACE. The solver and a tuned rho control
        (`rho_control.py`) solve identical instances on one box; we fit the exponent
        GAP between their wall-clock curves, with a CI over repeated timings. b2
        can't be gamed off-meter — but it is a LARGE-n instrument: at toy sizes
        wall-clock exponents are overhead/noise-limited (the same pre-asymptotic
        deflation the scaling track documents). So b2 never overrides b1; it only
        **corroborates or blocks a sub-√n claim** when its CI is decisive.

VERDICT logic (b1 leads, b2 guards):
  * b1 says sub-√n (α CI entirely below 0.5, held-out verified):
      - b2 corroborates (gap CI decisively negative)  → VERIFIED-FASTER
      - b2 does not corroborate                        → SUSPECT (b1 likely gamed
                                                          off-API, or a fit artifact)
  * b1 says α≈0.5 (no sub-√n claim)                    → NO-ASYMPTOTIC-WIN
    (b2's point estimate is shown but, at toy sizes, treated as noise — the clean
     deterministic field-op meter is authoritative.)

On a generic curve the reference BSGS gives α≈0.5 and NO-ASYMPTOTIC-WIN — the honest
result, and the baseline a genuinely non-generic attack must beat.

    python3 repr_track/repr_meter.py                                   # reference BSGS
    python3 repr_track/repr_meter.py --solver my_attack --ladder 20,22,24,26 --holdout 28
    python3 repr_track/repr_meter.py --seed 0x<SECRET> --timing-reps 9  # sealed grading

Pure stdlib; reuses the scaling track's fitter (tools/scaling_battery.py).
"""
import argparse
import importlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))            # counted_field/curve, instances, solvers
sys.path.insert(0, str(REPO / "tools"))  # reuse the scaling-track fitter

import instances                                   # noqa: E402
import counted_curve                               # noqa: E402
import rho_control                                 # noqa: E402
from scaling_battery import (fit_from_means, bootstrap, holdout_check,  # noqa: E402
                             ols, pct, _LCG)


def verify(k, pub):
    """Off-meter check k·G == Q via plain ints (does not touch the field counter)."""
    if k is None:
        return False
    n, a, p = pub["n"], pub["a"], pub["p"]
    return rho_control._mul(k % n, (pub["Gx"], pub["Gy"]), a, p) == (pub["Qx"], pub["Qy"])


def run_rung(solver, seed, bits, timing_reps):
    pub = instances.get_instance(seed, bits)
    E, G, Q, n = counted_curve.curve_from_public(pub)

    # b1: field-op count is DETERMINISTIC, so one metered run is exact.
    E.F.reset()
    k = solver.solve(E, G, Q, n)
    bd = E.F.c.breakdown()
    if not verify(k, pub):
        raise SystemExit(f"!! solver returned invalid k at bits={bits} (k·G≠Q)")

    # b2: time the solver and the rho control K times each (median is robust; the
    # full sample feeds the gap CI). Same instance, same box, back to back.
    solver_t = []
    for _ in range(timing_reps):
        t0 = time.perf_counter()
        solver.solve(E, G, Q, n)
        solver_t.append(time.perf_counter() - t0)
    ctrl_t, ck = [], None
    for _ in range(timing_reps):
        ck, dt = rho_control.time_control(pub)
        ctrl_t.append(dt)
    if not verify(ck, pub):
        raise SystemExit(f"!! rho control failed at bits={bits}")

    return {
        "bits": bits, "n": n,
        "field_ops": bd["total"], "field_breakdown": bd,
        "mean_ops": bd["total"], "trial_ops": [bd["total"]],   # for the reused b1 fitter
        "solver_secs": statistics.median(solver_t), "ctrl_secs": statistics.median(ctrl_t),
        "solver_t": solver_t, "ctrl_t": ctrl_t,
        "rho_ref": round(math.sqrt(math.pi * n / 2)),
    }


def b2_race(rungs, boot, seed):
    """Wall-clock exponents from median timings, plus a bootstrap CI on the exponent
    GAP (β_solver − β_control) over resampled timing samples. A gap CI decisively
    below 0 is the only thing that corroborates a sub-√n claim."""
    xs = [math.log(r["n"]) for r in rungs]
    med_s = [statistics.median(r["solver_t"]) for r in rungs]
    med_c = [statistics.median(r["ctrl_t"]) for r in rungs]
    bs, _, _ = ols(xs, [math.log(t) for t in med_s])
    bc, _, _ = ols(xs, [math.log(t) for t in med_c])
    gap, _, r2 = ols(xs, [math.log(s / c) for s, c in zip(med_s, med_c)])

    rng = _LCG(seed ^ 0x2B2B2B2B2B2B2B2B)
    gaps = []
    for _ in range(boot):
        ys = []
        for r in rungs:
            s = r["solver_t"][rng.below(len(r["solver_t"]))]
            c = r["ctrl_t"][rng.below(len(r["ctrl_t"]))]
            ys.append(math.log(s / c))
        g, _, _ = ols(xs, ys)
        gaps.append(g)
    gaps.sort()
    return {"beta_solver": round(bs, 4), "beta_control": round(bc, 4),
            "exponent_gap": round(gap, 4),
            "gap_ci95": [round(pct(gaps, 2.5), 4), round(pct(gaps, 97.5), 4)],
            "gap_r2": round(r2, 4)}


def parse_ladder(s):
    return [int(x) for x in s.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Representation-track cost-curve meter (b1 field-ops + b2 rho race).")
    ap.add_argument("--solver", default="solve_reference",
                    help="module exposing solve(E,G,Q,n)->k (default: solve_reference = BSGS)")
    ap.add_argument("--ladder", default="20,22,24,26", help="fit tiers (small — must be solvable)")
    ap.add_argument("--holdout", type=int, default=28, help="held-out tier for the b1 prediction check")
    ap.add_argument("--seed", default="0xC0FFEE", help="one sealed seed across every rung + holdout")
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap replicates for the CIs")
    ap.add_argument("--timing-reps", type=int, default=5, help="wall-clock repeats per rung (b2)")
    ap.add_argument("--out", default=str(REPO / "repr_scaling.json"))
    args = ap.parse_args(argv)

    ladder = parse_ladder(args.ladder)
    if len(ladder) < 3:
        raise SystemExit("!! need >=3 ladder tiers to fit a slope")
    if args.holdout in ladder:
        raise SystemExit(f"!! holdout {args.holdout} must not be in the fit ladder")
    try:
        seed_int = int(str(args.seed), 0)
    except ValueError:
        raise SystemExit(f"!! --seed {args.seed!r} not an int")

    solver = importlib.import_module(args.solver)
    if not hasattr(solver, "solve"):
        raise SystemExit(f"!! solver module {args.solver!r} has no solve(E,G,Q,n)")

    print(f"== representation-track meter ==  solver={args.solver}  ladder={ladder}  "
          f"holdout={args.holdout}  seed={args.seed}  timing_reps={args.timing_reps}", file=sys.stderr)
    rungs = []
    for b in ladder:
        r = run_rung(solver, args.seed, b, args.timing_reps)
        rungs.append(r)
        print(f"  · bits={b}: b1 {r['field_ops']:,} field-ops "
              f"({r['field_ops']/r['rho_ref']:.2f}× √(πn/2))  |  "
              f"b2 solver {r['solver_secs']*1e3:.1f}ms vs rho {r['ctrl_secs']*1e3:.1f}ms (medians)",
              file=sys.stderr)
    hold = run_rung(solver, args.seed, args.holdout, args.timing_reps)
    print(f"  · holdout bits={args.holdout}: b1 {hold['field_ops']:,} field-ops", file=sys.stderr)

    # ---- b1: fit the field-op cost law + held-out verify (authoritative) ----
    alpha, lnc, r2 = fit_from_means(rungs)
    alphas, lncs, _ = bootstrap(rungs, args.boot, seed_int)
    a_ci = [round(pct(sorted(alphas), 2.5), 4), round(pct(sorted(alphas), 97.5), 4)]
    b1_hold = holdout_check(rungs, hold, args.boot, seed_int)

    # ---- b2: wall-clock exponent gap vs rho (corroborator) ------------------
    b2 = b2_race(rungs + [hold], args.boot, seed_int)

    # ---- verdict: b1 leads, b2 guards a sub-√n claim ------------------------
    b1_sub = a_ci[1] < 0.5 and b1_hold["pass"]          # clean evidence of sub-√n
    b2_corroborates = b2["gap_ci95"][1] < -0.10         # gap CI decisively negative
    if b1_sub:
        verdict = "VERIFIED-FASTER" if b2_corroborates else "SUSPECT-b1-UNCORROBORATED"
    else:
        verdict = "NO-ASYMPTOTIC-WIN"

    out = {
        "track": "representation",
        "solver": args.solver, "seed": args.seed, "boot": args.boot,
        "timing_reps": args.timing_reps, "ladder_bits": ladder, "rungs": rungs + [hold],
        "b1_field_ops": {
            "alpha": round(alpha, 4), "alpha_ci95": a_ci, "c": round(math.exp(lnc), 6),
            "r2": round(r2, 5), "holdout": b1_hold, "shoup_alpha": 0.5, "authoritative": True,
        },
        "b2_rho_race": dict(b2, role="corroborator", note="large-n instrument; toy-size exponents are overhead-limited"),
        "verdict": verdict,
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    # ---- summary ------------------------------------------------------------
    bf = out["b1_field_ops"]
    h = b1_hold
    print("\n" + "=" * 68)
    print(f"  b1 (scored)  field_ops ≈ {bf['c']:.3g}·n^{bf['alpha']:.3f}")
    print(f"     exponent α = {bf['alpha']:.3f}  95% CI {a_ci}   (generic/Shoup = 0.5)")
    print(f"     held-out bits={h['bits']}: predicted {h['predicted_ops']:,}, measured {h['measured_ops']:,}"
          f"  → {'✅ verified' if h['pass'] else '❌ mispredicted'} (z={h['z']:+.2f})")
    print(f"  b2 (check)   β_solver={b2['beta_solver']}  β_rho={b2['beta_control']}  "
          f"gap={b2['exponent_gap']:+.3f}  95% CI {b2['gap_ci95']}")
    print(f"               {'decisively negative → corroborates' if b2_corroborates else 'CI straddles 0 / noise-limited → abstains'}")
    print(f"\n  VERDICT: {verdict}")
    if verdict == "NO-ASYMPTOTIC-WIN":
        print("    Clean field-op meter says α≈0.5 — no sub-√n claim. The b2 point estimate")
        print("    is overhead/noise-limited at these toy sizes and is not allowed to override b1.")
        print("    A genuine non-generic attack would push b1's α CI below 0.5 (held-out verified)")
        print("    AND open a decisively-negative b2 gap at the largest tiers.")
    elif verdict == "SUSPECT-b1-UNCORROBORATED":
        print("    b1 claims sub-√n but the wall-clock race does NOT corroborate — suspect the")
        print("    field-op count was gamed off-API, or the fit is a pre-asymptotic artifact.")
    print("=" * 68)
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
