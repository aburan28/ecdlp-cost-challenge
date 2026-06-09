#!/usr/bin/env python3
"""Meter validation — the positive control that proves VERIFIED-FASTER fires.

The representation meter (`repr_meter.py`) has only ever printed NO-ASYMPTOTIC-WIN,
because verified-generic curves have no sub-√n attack. This driver exercises the
*other* verdict on curves with a KNOWN one: it runs Pohlig–Hellman
(`solve_pohlig_hellman.py`) across a ladder of WEAK instances
(`weak_instances.py`) whose order has largest prime factor pmax ≈ n^gamma, so the
attack costs ~√pmax = n^(gamma/2). It then checks the meter measures **α ≈ gamma/2**
(held-out verified) and fires **VERIFIED-FASTER**.

This is a CALIBRATION, not a break: by dialing `gamma` we move the *true* attack
exponent across [0, 0.5] and confirm the meter tracks it —
  gamma=1.0 (near-prime, the scored regime) → α≈0.5 → NO-ASYMPTOTIC-WIN  (boundary)
  gamma=0.7                                 → α≈0.35 → VERIFIED-FASTER
  gamma=0.5                                 → α≈0.25 → VERIFIED-FASTER
Two-sided: the same meter that abstains on generic curves fires, correctly and
quantitatively, on weak ones. b1 (field ops) is authoritative; b2 here is a generic
BSGS control (order-agnostic √n) the structure-exploiting PH must out-scale.

    python3 repr_track/validate_meter.py --gamma 0.5 --ladder 20,22,24,26 --holdout 28
"""
import argparse
import math
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools"))

import weak_instances                                   # noqa: E402
import counted_curve                                    # noqa: E402
import solve_pohlig_hellman as PH                        # noqa: E402
import rho_control                                       # noqa: E402
from scaling_battery import fit_from_means, bootstrap, holdout_check, pct  # noqa: E402
from repr_meter import b2_race, verify                   # noqa: E402


def _bsgs_plain(pub):
    """Generic order-agnostic BSGS (√n) in plain ints — the b2 control. Ignores the
    order structure PH exploits, so it's the honest 'no special knowledge' baseline."""
    p, a, n = pub["p"], pub["a"], pub["n"]
    G = (pub["Gx"], pub["Gy"])
    Q = (pub["Qx"], pub["Qy"])
    m = math.isqrt(n) + 1
    table = {}
    cur = None
    for j in range(m):
        if cur not in table:
            table[cur] = j
        cur = rho_control._add(cur, G, a, p)
    mG = rho_control._mul(m, G, a, p)
    step = None if mG is None else (mG[0], (-mG[1]) % p)
    cur = Q
    for i in range(m):
        if cur in table:
            return (i * m + table[cur]) % n
        cur = rho_control._add(cur, step, a, p)
    return None


def _timed(fn, min_dur=0.02):
    """Robust per-call seconds via adaptive batching (timeit-style). A ~1 ms PH solve
    timed alone is pure OS jitter; running it enough times to clear `min_dur` and
    dividing gives a stable per-call time, so the b2 exponent CI isn't swamped by
    the fast solver's relative noise. Slow ops (BSGS at high bits) run once."""
    t0 = time.perf_counter()
    fn()
    single = time.perf_counter() - t0
    reps = max(1, int(min_dur / max(single, 1e-7)) + 1)
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) / reps


def run_rung(seed, bits, gamma, window, timing_reps):
    inst = weak_instances.get_weak_instance(seed, bits, gamma, window)
    E, G, Q, n = counted_curve.curve_from_public(inst)

    E.F.reset()
    k = PH.solve(E, G, Q, n)
    field_ops = E.F.c.total()
    if not verify(k, inst):
        raise SystemExit(f"!! PH returned invalid k at bits={bits}")

    kc = _bsgs_plain(inst)
    if not verify(kc, inst):
        raise SystemExit(f"!! BSGS control failed at bits={bits}")
    # b2 timings — adaptive per-call (robust to the fast solver's jitter).
    solver_t = [_timed(lambda: PH.solve(E, G, Q, n)) for _ in range(timing_reps)]
    ctrl_t = [_timed(lambda: _bsgs_plain(inst)) for _ in range(timing_reps)]

    return {"bits": bits, "n": n, "field_ops": field_ops,
            "mean_ops": field_ops, "trial_ops": [field_ops],
            "solver_t": solver_t, "ctrl_t": ctrl_t,
            "rho_ref": round(math.sqrt(math.pi * n / 2)),
            "gamma_actual": inst["gamma_actual"], "pmax": inst["pmax"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate the representation meter with a Pohlig–Hellman positive control.")
    ap.add_argument("--gamma", type=float, default=0.5, help="target log_n(pmax): attack exponent ≈ gamma/2")
    ap.add_argument("--ladder", default="20,22,24,26")
    ap.add_argument("--holdout", type=int, default=28)
    ap.add_argument("--seed", default="0xD00D")
    ap.add_argument("--window", type=float, default=0.08, help="± window on gamma when searching curves")
    ap.add_argument("--boot", type=int, default=3000)
    ap.add_argument("--timing-reps", type=int, default=5)
    ap.add_argument("--out", default=str(REPO / "repr_validation.json"))
    args = ap.parse_args(argv)

    ladder = [int(x) for x in args.ladder.split(",")]
    seed_int = int(str(args.seed), 0)
    print(f"== meter validation ==  gamma={args.gamma} (predict α≈{args.gamma/2:.3f})  "
          f"ladder={ladder} holdout={args.holdout} seed={args.seed}", file=sys.stderr)

    rungs = []
    for b in ladder:
        r = run_rung(args.seed, b, args.gamma, args.window, args.timing_reps)
        rungs.append(r)
        print(f"  · bits={b}: pmax={r['pmax']:,} (γ_act={r['gamma_actual']})  "
              f"b1 {r['field_ops']:,} field-ops ({r['field_ops']/r['rho_ref']:.3f}×√(πn/2))  "
              f"b2 PH {statistics.median(r['solver_t'])*1e3:.1f}ms vs BSGS {statistics.median(r['ctrl_t'])*1e3:.1f}ms",
              file=sys.stderr)
    hold = run_rung(args.seed, args.holdout, args.gamma, args.window, args.timing_reps)
    print(f"  · holdout bits={args.holdout}: pmax={hold['pmax']:,}  b1 {hold['field_ops']:,} field-ops", file=sys.stderr)

    # b1 fit + held-out
    alpha, lnc, r2 = fit_from_means(rungs)
    alphas, _, _ = bootstrap(rungs, args.boot, seed_int)
    a_ci = [round(pct(sorted(alphas), 2.5), 4), round(pct(sorted(alphas), 97.5), 4)]
    b1_hold = holdout_check(rungs, hold, args.boot, seed_int)
    # b2 race vs generic BSGS
    b2 = b2_race(rungs + [hold], args.boot, seed_int)

    b1_sub = a_ci[1] < 0.5 and b1_hold["pass"]      # clean sub-√n field-op law
    b2_corroborates = b2["gap_ci95"][1] < 0.0       # gap CI entirely negative: solver out-scales control
    b2_contradicts = b2["gap_ci95"][0] > 0.0        # gap CI entirely positive: NO win (off-API suspicion)
    if b1_sub and b2_corroborates:
        verdict = "VERIFIED-FASTER"                  # both meters agree: a real sub-√n attack
    elif b1_sub and b2_contradicts:
        verdict = "SUSPECT-b1-UNCORROBORATED"        # field ops say sub-√n but wall-clock says no win → off-API?
    elif b1_sub:
        verdict = "VERIFIED-FASTER-b1"               # authoritative meter verified; b2 noise-limited (abstains), not contradicting
    else:
        verdict = "NO-ASYMPTOTIC-WIN"

    predicted = args.gamma / 2
    print("\n" + "=" * 70)
    print(f"  PREDICTION:  attack exponent α ≈ gamma/2 = {predicted:.3f}")
    print(f"  b1 MEASURED: α = {round(alpha,4)}  95% CI {a_ci}   (r²={round(r2,4)})")
    hit = a_ci[0] <= predicted <= a_ci[1]
    print(f"               predicted {predicted:.3f} is {'INSIDE' if hit else 'OUTSIDE'} the 95% CI"
          f"  → meter {'tracks the attack exponent ✅' if hit else 'off (small-n overhead?) ⚠️'}")
    h = b1_hold
    print(f"  b1 held-out bits={h['bits']}: predicted {h['predicted_ops']:,}, measured {h['measured_ops']:,}"
          f"  → {'✅ verified' if h['pass'] else '❌ mispredicted'} (z={h['z']:+.2f})")
    b2_state = ("corroborates ✅" if b2_corroborates
                else "CONTRADICTS ⚠️" if b2_contradicts else "abstains (noise-limited)")
    print(f"  b2 race vs generic BSGS:  gap {b2['exponent_gap']:+.3f}  95% CI {b2['gap_ci95']}  → {b2_state}")
    print(f"\n  VERDICT: {verdict}")
    print("=" * 70)

    import json
    Path(args.out).write_text(json.dumps({
        "track": "representation-meter-validation",
        "control": "pohlig-hellman on weak (controlled-order) curves — POSITIVE CONTROL, not a break",
        "gamma": args.gamma, "predicted_alpha": predicted, "seed": args.seed,
        "ladder_bits": ladder, "holdout_bits": args.holdout,
        "rungs": [{k: r[k] for k in ("bits", "n", "field_ops", "gamma_actual", "pmax")} for r in rungs + [hold]],
        "b1_field_ops": {"alpha": round(alpha, 4), "alpha_ci95": a_ci, "r2": round(r2, 4),
                         "holdout": b1_hold},
        "b2_rho_race": b2, "verdict": verdict,
    }, indent=2) + "\n")
    print(f"  wrote {args.out}")
    return 0 if verdict in ("VERIFIED-FASTER", "VERIFIED-FASTER-b1", "NO-ASYMPTOTIC-WIN") else 3


if __name__ == "__main__":
    sys.exit(main())
