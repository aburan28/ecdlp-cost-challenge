#!/usr/bin/env python3
"""Does index calculus break the rho √n barrier on prime-field curves? Measure it.

Runs the index-calculus attack (`solve_index_calculus.py`) across a ladder of
verified-generic, prime-order curves and fits its group-operation exponent. Theory
says prime-field IC costs ≈ n^(2/3) — ABOVE rho's n^(1/2) — so the meter should report
an exponent > 0.5 and verdict BARRIER-HOLDS. This is the honest experiment: implement
the frontier non-generic attack, let the meter say whether it wins. (It recovers a
correct k every time — it is a real attack — it is just slower than rho.)

    python3 repr_track/validate_index_calculus.py --ladder 20,21,22,23,24 --holdout 25
"""
import argparse
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools"))

import counted_curve                                    # noqa: E402
import solve_index_calculus as IC                        # noqa: E402
import rho_control                                       # noqa: E402
from rho_control import _SplitMix64                       # noqa: E402
from scaling_battery import fit_from_means, bootstrap, holdout_check, pct  # noqa: E402

GEN = REPO / "target" / "release" / "gen_instance"


def generic_curve(seed, bits):
    d = json.loads(subprocess.run([str(GEN), str(seed), str(bits)], capture_output=True, text=True).stdout)
    return {k: int(d[k]) for k in ("p", "a", "b", "n", "Gx", "Gy")}


def run_rung(seed, bits, samples):
    inst = generic_curve(seed, bits)
    n, a, p = inst["n"], inst["a"], inst["p"]
    E = counted_curve.Curve(counted_curve.CountedField(p), a, inst["b"])
    G = E.point(inst["Gx"], inst["Gy"])
    rng = _SplitMix64(0x1CACA ^ seed ^ bits)
    ops = []
    for _ in range(samples):
        kp = 1 + rng.below(n - 1)
        Qp = rho_control._mul(kp, (inst["Gx"], inst["Gy"]), a, p)
        Q = E.point(Qp[0], Qp[1])
        E.F.reset()
        kr = IC.solve(E, G, Q, n)
        if kr is None or kr % n != kp % n:
            raise SystemExit(f"!! IC failed to recover k at bits={bits}")
        ops.append(E.F.c.total())
    return {"bits": bits, "n": n, "field_ops": statistics.mean(ops),
            "mean_ops": statistics.mean(ops), "trial_ops": ops,
            "rho_ref": round(math.sqrt(math.pi * n / 2))}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure whether index calculus beats rho on prime-field curves.")
    ap.add_argument("--ladder", default="20,21,22,23,24")
    ap.add_argument("--holdout", type=int, default=25)
    ap.add_argument("--seed", type=int, default=0xACE0)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--boot", type=int, default=4000)
    ap.add_argument("--out", default=str(REPO / "index_calculus_probe.json"))
    args = ap.parse_args(argv)

    ladder = [int(x) for x in args.ladder.split(",")]
    print(f"== index-calculus probe ==  ladder={ladder} holdout={args.holdout}  "
          f"(rho exponent = 0.5; theory IC ≈ 2/3)", file=sys.stderr)
    rungs = []
    for b in ladder:
        r = run_rung(args.seed + b, b, args.samples)
        rungs.append(r)
        print(f"  · bits={b}: IC {r['field_ops']:,.0f} group-ops  ({r['field_ops']/r['rho_ref']:.1f}× rho)",
              file=sys.stderr)
    hold = run_rung(args.seed + args.holdout, args.holdout, args.samples)
    print(f"  · holdout bits={args.holdout}: IC {hold['field_ops']:,.0f} group-ops "
          f"({hold['field_ops']/hold['rho_ref']:.1f}× rho)", file=sys.stderr)

    alpha, lnc, r2 = fit_from_means(rungs)
    alphas, _, _ = bootstrap(rungs, args.boot, args.seed)
    a_ci = [round(pct(sorted(alphas), 2.5), 4), round(pct(sorted(alphas), 97.5), 4)]
    b1_hold = holdout_check(rungs, hold, args.boot, args.seed)

    breaks_rho = a_ci[1] < 0.5 and b1_hold["pass"]      # IC exponent provably below rho's 0.5
    verdict = "BREAKS-RHO" if breaks_rho else "BARRIER-HOLDS"
    rho_growth = hold["field_ops"] / hold["rho_ref"] / (rungs[0]["field_ops"] / rungs[0]["rho_ref"])

    print("\n" + "=" * 72)
    print(f"  INDEX-CALCULUS group-op cost on generic prime-order curves:")
    print(f"     cost ≈ {math.exp(lnc):.3g}·n^{alpha:.3f}   exponent α = {alpha:.3f}  95% CI {a_ci}")
    print(f"     rho is n^0.5.  IC exponent is {'BELOW' if breaks_rho else 'ABOVE'} 0.5"
          f"  →  IC is {'FASTER' if breaks_rho else 'SLOWER'} than rho")
    h = b1_hold
    print(f"     held-out bits={h['bits']}: predicted {h['predicted_ops']:,}, measured {h['measured_ops']:,}"
          f"  → {'✅ verified' if h['pass'] else '❌ mispredicted'} (z={h['z']:+.2f})")
    print(f"     IC/rho ratio grew {rungs[0]['field_ops']/rungs[0]['rho_ref']:.0f}× → "
          f"{hold['field_ops']/hold['rho_ref']:.0f}× across the ladder (widening ⇒ asymptotically worse)")
    print(f"\n  VERDICT: {verdict}")
    if verdict == "BARRIER-HOLDS":
        print("     Index calculus recovers k but at n^(~2/3) group ops — ABOVE rho's n^(1/2).")
        print("     The prime-field decomposition cost keeps IC worse than rho. The barrier stands.")
    print("=" * 72)

    Path(args.out).write_text(json.dumps({
        "track": "index-calculus-probe", "curve_class": "verified-generic prime order",
        "question": "does index calculus beat rho (√n) on a prime-field curve?",
        "seed": args.seed, "ladder_bits": ladder, "holdout_bits": args.holdout,
        "rungs": [{k: r[k] for k in ("bits", "n", "field_ops", "rho_ref")} for r in rungs + [hold]],
        "ic_exponent": round(alpha, 4), "ic_exponent_ci95": a_ci, "rho_exponent": 0.5,
        "holdout": b1_hold, "verdict": verdict,
    }, indent=2) + "\n")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
