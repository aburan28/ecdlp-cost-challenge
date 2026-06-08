#!/usr/bin/env python3
"""Scaling battery — score a solver's COST CURVE, not a single instance.

`Find k` is a *point*; "a faster algorithm" is a *slope*. A single solved
instance confounds luck, the constant factor, and the exponent — you cannot read
"faster" off one size. This tool reframes the benchmark accordingly: it runs the
trusted oracle across a **ladder** of bit-sizes, fits the cost law

        log(group_ops) = alpha · log(n) + log(c)

with bootstrap CIs over the trial battery, then **predicts** the cost at a
*held-out* tier and **verifies** that prediction against a fresh measured run.

The graded deliverable is the algorithm's `(alpha, c)` — its exponent and
constant — plus a held-out check that this is a *real cost law*, not an overfit
curve or a lucky point. Recovering `k` is demoted to the per-rung measurement.

Honest scope: inside the opaque generic-group arena, Shoup pins `alpha = 0.5`, so
here the battery *confirms* alpha≈0.5 and ranks by the constant `c` (the existing
0.71× game). A genuinely sub-0.5 exponent can only appear in the representation
track (a different meter); this same fitter scores that curve too.

Design: this wraps `./benchmark.sh` once per rung, so the sandbox and the trusted
op-meter are byte-for-byte unchanged. It snapshots `results.tsv` and restores it
afterwards, so a battery never pollutes the curated single-tier arena history —
the battery's artifact is `scaling.json`. Pure stdlib (no numpy).

    python3 tools/scaling_battery.py                         # default ladder + holdout
    python3 tools/scaling_battery.py --ladder 24,28,32,36 --holdout 40 --trials 16
    python3 tools/scaling_battery.py --seed 0xC0FFEE --boot 4000 --out scaling.json

Common random numbers: ONE `--seed` is applied to every rung and the holdout, so
the whole ladder is a single paired comparison (instance-luck cancels). For
official grading, pass a sealed secret seed and a large `--trials`, exactly as the
single-tier arena does, then reveal it after grading.
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "benchmark.sh"
SCORE = REPO / "score.json"
RESULTS = REPO / "results.tsv"

# Matches the oracle's per-trial stderr line (src/bin/oracle.rs):
#   [oracle] trial 3/32: 788034 group_ops  OK
TRIAL_RE = re.compile(r"\[oracle\]\s+trial\s+\d+/\d+:\s+(\d+)\s+group_ops\s+(OK|FAIL)")


def _seed_str(seed):
    """Accept 0x-hex or decimal; pass through verbatim to the oracle's env parser."""
    return seed


# ---- one rung --------------------------------------------------------------

def run_rung(bits, seed, trials, label):
    """Run the trusted oracle at one tier via benchmark.sh. Returns a rung dict
    with the authoritative mean from score.json plus the per-trial op counts
    parsed from the oracle's stderr (used for the bootstrap)."""
    env = {
        "ECDLP_BITS": str(bits),
        "ECDLP_SEED": str(seed),
        "ECDLP_TRIALS": str(trials),
    }
    import os
    full_env = dict(os.environ, **env)
    proc = subprocess.run(
        ["bash", str(BENCH), "--note", f"scaling rung {label} bits={bits}"],
        cwd=str(REPO), env=full_env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if not SCORE.exists():
        raise SystemExit(
            f"!! rung bits={bits}: no score.json produced.\n"
            f"--- benchmark.sh stderr (tail) ---\n{proc.stderr[-2000:]}"
        )
    sc = json.loads(SCORE.read_text())
    m = sc.get("metrics", {})
    if not m.get("correct"):
        raise SystemExit(
            f"!! rung bits={bits}: solver returned no valid k (correct=false) — "
            f"the battery cannot be fit with a failed rung.\n{proc.stderr[-1500:]}"
        )
    trial_ops = [int(x) for x, ok in TRIAL_RE.findall(proc.stderr) if ok == "OK"]
    return {
        "bits": int(m["bits"]),
        "n": int(m["n"]),
        "mean_ops": int(m["group_ops"]),
        "trial_ops": trial_ops,
        "rho_ref": int(m["rho_reference"]),
        "shoup_floor": int(m.get("shoup_floor", 0)),
        "ratio_to_rho": float(m.get("ratio_to_rho", 0.0)),
        "trials": int(m.get("trials", len(trial_ops))),
    }


# ---- least squares on the log-log cost law ---------------------------------

def ols(xs, ys):
    """Ordinary least squares y = a*x + b. Returns (a=alpha, b=ln c, r2)."""
    nobs = len(xs)
    mx = sum(xs) / nobs
    my = sum(ys) / nobs
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    a = sxy / sxx
    b = my - a * mx
    ss_res = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return a, b, r2


def fit_from_means(rungs):
    xs = [math.log(r["n"]) for r in rungs]
    ys = [math.log(r["mean_ops"]) for r in rungs]
    return ols(xs, ys)


# ---- bootstrap over the trial battery (rho variance -> honest CIs) ---------

class _LCG:
    """Tiny deterministic PRNG (SplitMix64). Math.random is banned in this lab's
    reproducible tooling; seed it from the battery seed so CIs are re-derivable."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def below(self, m):
        return self.next_u64() % m


def bootstrap(rungs, boot, seed):
    """Resample trials *within each rung* (with replacement), refit each replicate.
    This propagates rho's heavy per-trial variance into the (alpha, c) CIs.

    Falls back to a residual bootstrap if any rung lacks per-trial data."""
    have_trials = all(len(r["trial_ops"]) >= 2 for r in rungs)
    rng = _LCG(seed ^ 0xA5A5A5A5A5A5A5A5)
    xs = [math.log(r["n"]) for r in rungs]
    alphas, lncs = [], []

    if have_trials:
        for _ in range(boot):
            ys = []
            for r in rungs:
                ops = r["trial_ops"]
                k = len(ops)
                resampled = [ops[rng.below(k)] for _ in range(k)]
                ys.append(math.log(sum(resampled) / k))
            a, b, _ = ols(xs, ys)
            alphas.append(a)
            lncs.append(b)
    else:
        # Residual bootstrap on the fitted line (weaker; no per-trial spread).
        a0, b0, _ = fit_from_means(rungs)
        ys0 = [math.log(r["mean_ops"]) for r in rungs]
        resid = [y - (a0 * x + b0) for x, y in zip(xs, ys0)]
        for _ in range(boot):
            ys = [a0 * x + b0 + resid[rng.below(len(resid))] for x in xs]
            a, b, _ = ols(xs, ys)
            alphas.append(a)
            lncs.append(b)

    return alphas, lncs, have_trials


def pct(sorted_xs, q):
    """Linear-interpolated percentile (q in [0,100])."""
    if not sorted_xs:
        return float("nan")
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = (len(sorted_xs) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_xs[lo]
    frac = pos - lo
    return sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac


# ---- predict-then-verify on a held-out tier --------------------------------

def holdout_check(rungs, holdout, boot, seed):
    """Fit on `rungs`, predict ops at the held-out tier, then test the measured
    held-out mean against a 95% prediction band. The band combines:
      * PARAMETER uncertainty — the bootstrap spread of (alpha, c) at ln(n_holdout)
      * the held-out mean's OWN sampling SE — relative SE of a rho mean over T trials
    added in quadrature on the log scale. Passing means the curve *predicted its
    own next rung* — the signature of a real cost law, not an overfit/lucky fit."""
    alphas, lncs, _ = bootstrap(rungs, boot, seed)
    xh = math.log(holdout["n"])
    preds = sorted(a * xh + b for a, b in zip(alphas, lncs))  # ln(predicted ops)
    ln_pred_med = pct(preds, 50)
    sd_param = (pct(preds, 84.135) - pct(preds, 15.865)) / 2.0  # ~1σ from bootstrap

    # Held-out mean's own sampling SE on the log scale (relative SE of the mean).
    ops = holdout["trial_ops"]
    if len(ops) >= 2:
        mu = sum(ops) / len(ops)
        var = sum((o - mu) ** 2 for o in ops) / (len(ops) - 1)
        sd_meas = (math.sqrt(var) / mu) / math.sqrt(len(ops))  # log-scale ≈ relative SE
    else:
        sd_meas = 0.0

    sd = math.sqrt(sd_param ** 2 + sd_meas ** 2)
    ln_meas = math.log(holdout["mean_ops"])
    z = (ln_meas - ln_pred_med) / sd if sd > 0 else 0.0
    lo, hi = math.exp(ln_pred_med - 1.96 * sd), math.exp(ln_pred_med + 1.96 * sd)
    return {
        "bits": holdout["bits"],
        "n": holdout["n"],
        "measured_ops": holdout["mean_ops"],
        "predicted_ops": round(math.exp(ln_pred_med)),
        "pi95": [round(lo), round(hi)],
        "sd_param_log": round(sd_param, 5),
        "sd_meas_log": round(sd_meas, 5),
        "z": round(z, 3),
        "pass": bool(lo <= holdout["mean_ops"] <= hi),
    }


# ---- driver ----------------------------------------------------------------

def parse_ladder(s):
    return [int(x) for x in s.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score a solver's cost curve (alpha, c) with a held-out check.")
    ap.add_argument("--ladder", default="24,28,32,36",
                    help="comma-separated fit tiers (bit-lengths of p≈n). Default 24,28,32,36")
    ap.add_argument("--holdout", type=int, default=40,
                    help="held-out tier predicted from the fit, then verified. Default 40")
    ap.add_argument("--seed", default="0x12345678",
                    help="ONE instance seed applied to every rung + holdout (common random numbers)")
    ap.add_argument("--trials", type=int, default=16, help="trial battery per rung (mean is the rung value)")
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap replicates for the CIs")
    ap.add_argument("--out", default=str(REPO / "scaling.json"), help="where to write the battery artifact")
    ap.add_argument("--keep-results", action="store_true",
                    help="do NOT snapshot/restore results.tsv (lets the battery rows persist)")
    args = ap.parse_args(argv)

    ladder = parse_ladder(args.ladder)
    if len(ladder) < 3:
        raise SystemExit("!! need >=3 ladder tiers to fit a slope with a usable CI")
    if args.holdout in ladder:
        raise SystemExit(f"!! holdout tier {args.holdout} must NOT be in the fit ladder (it's the test point)")
    # SplitMix64-style int seed for the bootstrap RNG, derived from the instance seed.
    try:
        seed_int = int(str(args.seed), 0)
    except ValueError:
        raise SystemExit(f"!! --seed {args.seed!r} is not an int (use decimal or 0x-hex)")

    # Snapshot results.tsv so the battery never pollutes the single-tier arena.
    snap = None
    if not args.keep_results and RESULTS.exists():
        snap = tempfile.NamedTemporaryFile(delete=False, suffix=".tsv").name
        shutil.copy2(RESULTS, snap)

    try:
        print(f"== scaling battery ==  ladder={ladder}  holdout={args.holdout}  "
              f"seed={args.seed}  trials={args.trials}", file=sys.stderr)
        rungs = []
        for b in ladder:
            print(f"  · rung bits={b} …", file=sys.stderr)
            r = run_rung(b, args.seed, args.trials, label="fit")
            print(f"    n=2^{b}  mean={r['mean_ops']:,} ops  ({r['ratio_to_rho']:.3f}× rho)  "
                  f"[{len(r['trial_ops'])}/{args.trials} trials parsed]", file=sys.stderr)
            rungs.append(r)

        print(f"  · holdout bits={args.holdout} …", file=sys.stderr)
        hold = run_rung(args.holdout, args.seed, args.trials, label="holdout")
        print(f"    n=2^{args.holdout}  mean={hold['mean_ops']:,} ops  "
              f"({hold['ratio_to_rho']:.3f}× rho)", file=sys.stderr)
    finally:
        if snap is not None:
            shutil.copy2(snap, RESULTS)
            Path(snap).unlink(missing_ok=True)

    # Fit the cost law on the ladder, bootstrap the CIs, verify the holdout.
    alpha, lnc, r2 = fit_from_means(rungs)
    alphas, lncs, used_trials = bootstrap(rungs, args.boot, seed_int)
    alphas_s, cs_s = sorted(alphas), sorted(math.exp(b) for b in lncs)
    hold_res = holdout_check(rungs, hold, args.boot, seed_int)

    out = {
        "track": "scaling",
        "seed": args.seed,
        "trials": args.trials,
        "boot": args.boot,
        "bootstrap": "per-trial" if used_trials else "residual",
        "ladder_bits": ladder,
        "rungs": rungs,
        "fit": {
            "alpha": round(alpha, 5),
            "alpha_ci95": [round(pct(alphas_s, 2.5), 5), round(pct(alphas_s, 97.5), 5)],
            "c": round(math.exp(lnc), 5),
            "c_ci95": [round(pct(cs_s, 2.5), 5), round(pct(cs_s, 97.5), 5)],
            "r2": round(r2, 6),
        },
        "holdout": hold_res,
        "reference": {"alpha_shoup": 0.5, "note": "generic arena pins alpha=0.5; rank by c there"},
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    # ---- human summary -------------------------------------------------------
    f = out["fit"]
    print("\n" + "=" * 64)
    print(f"  cost law:   group_ops ≈ {f['c']:.3g} · n^{f['alpha']:.4f}")
    print(f"  exponent α: {f['alpha']:.4f}   95% CI [{f['alpha_ci95'][0]:.4f}, {f['alpha_ci95'][1]:.4f}]"
          f"   (Shoup pins 0.5 in the generic arena)")
    print(f"  constant c: {f['c']:.4f}   95% CI [{f['c_ci95'][0]:.4f}, {f['c_ci95'][1]:.4f}]   (r²={f['r2']:.5f})")
    print(f"  bootstrap:  {out['bootstrap']} ({args.boot} replicates)")
    h = hold_res
    verdict = "✅ VERIFIED" if h["pass"] else "❌ MISPREDICTED"
    print(f"\n  held-out tier bits={h['bits']}:  {verdict}")
    print(f"    predicted {h['predicted_ops']:,} ops   95% band [{h['pi95'][0]:,}, {h['pi95'][1]:,}]")
    print(f"    measured  {h['measured_ops']:,} ops   (z = {h['z']:+.2f})")
    print("=" * 64)
    print(f"  wrote {args.out}")
    if not h["pass"]:
        print("  ⚠️  the fit did NOT predict its own held-out rung — this is not a")
        print("      verified cost law and beats_curve.py will reject it as a record.")
    return 0 if h["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
