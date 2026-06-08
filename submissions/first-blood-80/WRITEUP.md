# First Blood — `instance_public_80.json` (80-bit)

**Solver:** aburan28
**Date:** 2026-06-07
**Method label:** `OBSERVATION` — generic Pollard-rho (van Oorschot–Wiener parallel
distinguished points). **No** non-generic structure was used or found; this is the
honest `√n` work, just executed fast on the real curve.

## Result

```
k = 405306096300473350288613
```

Verification (the unforgeable one-scalar-mult check shipped in this repo):

```
$ python3 first_blood/verify_first_blood.py first_blood/instance_public_80.json 405306096300473350288613
instance : first_blood/instance_public_80.json  (80-bit)
k        : 405306096300473350288613
k*G == Q : True
RESULT   : SOLVED  (first blood!)
```

## Method

Plain **r-adding-walk Pollard rho** with **distinguished points**, parallelised
van-Oorschot–Wiener style across threads, attacking the published curve directly
(we have `(p,a,b,G,Q)`, so this is the representation track, not the generic
oracle). Each walk tracks `(a,b)` with the point `= a·G + b·Q`; a collision of two
trails at the same point gives `k = (a₁−a₂)·(b₂−b₁)⁻¹ mod n`.

Implementation notes (full source in `solver/`):

- **Field:** 128-bit Montgomery arithmetic (the 80-bit prime needs 160-bit
  products; done with a 128×128→256 schoolbook multiply + Montgomery REDC).
- **Group:** affine short Weierstrass with **batch inversion** (Montgomery's trick):
  one field inversion per *batch* of `W=512` parallel walks, ~6 mults per EC-add
  amortised. This is the throughput lever.
- **Distinguished points:** a point is distinguished when the low 20 bits of its
  Montgomery x-coordinate are zero (`θ = 2⁻²⁰`); only those go in a shared, sharded
  hash table, so memory stays at a few hundred thousand entries.
- **No negation map.** The √2 negation-map speedup needs robust fruitless-cycle
  handling; a naive 2-cycle-only escape lets longer cycles trap walks (we observed
  the DP table stop growing while step count climbed — ~88 % of steps wasted).
  Plain rho has no involution and therefore no fruitless cycles: every step is
  productive. The √2 we give up is far cheaper than a stalled run.
- **Resilience:** periodic checkpointing of the DP table (`CKPT` env) so a multi-
  hour run survives interruption.

## Cost

| | |
|---|---|
| Hardware | 1 machine, **12 worker threads** (Apple Silicon, commodity) |
| Throughput | ~**120 M** EC-steps / s (all threads) |
| Steps to collision | **261,228,343,296** (≈ 2.61 × 10¹¹) |
| Wall-clock | **2,177 s ≈ 36 min** |
| Expected (rho mean) | `√(πn/2) ≈ 1.2533·√n ≈ 1.36 × 10¹²` steps |

The solve landed at ~0.19× the rho mean — a lucky early collision, well within
rho's heavy variance (a single run routinely scatters by a large factor). The
*expected* cost at this throughput is ~3 hours; budget accordingly to reproduce.

## Reproduce

```bash
cd solver
cargo build --release
# args: p a b Gx Gy Qx Qy n [dpbits] [threads]
CKPT=ckpt.bin ./target/release/rho solve \
  1175497345426422717181999 620247556179443582645353 102263172566403403989251 \
  431501422402526006168944 165713249792560672976557 \
  581398211330274887184268 207849787939911311087460 \
  1175497345426922808444299 20 12
```

The solver self-verifies `k·G == Q` before printing `k`; cross-check with
`first_blood/verify_first_blood.py`.

## Scope / honesty

This is a *generic* break: it spent the `√n` work, nothing more. It is **not**
evidence of any weakness in the curve, and it says nothing about 96/112/128-bit
instances, which are out of reach for this method on commodity hardware
(96-bit ≈ 2⁴⁸ steps ≈ months on one machine; 112/128-bit infeasible).
