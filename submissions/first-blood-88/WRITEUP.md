# First Blood — `instance_public_88.json` (88-bit)

**Solver:** aburan28
**Date:** 2026-06-08
**Method label:** `OBSERVATION` — generic Pollard-rho (parallel distinguished
points). No non-generic structure used or found; the honest `√n` work, executed
fast on the published curve.

## Instance

A fresh **88-bit** verified-generic prime-field curve, generated with the repo's
own generator `sage tools/gen_instances.sage 88 88` (exact SEA point counting;
prime order, non-anomalous, MOV embedding degree > 200, `j ∉ {0,1728}`; `k`
discarded at generation), and registered in `first_blood/status.json`.

```
p = 242741740111627334084264707
n = 242741740111604890660673023   (prime)
k = 119182292250672575868009920
```

Verify:

```
$ python3 first_blood/verify_first_blood.py first_blood/instance_public_88.json 119182292250672575868009920
k*G == Q : True
RESULT   : SOLVED  (first blood!)
```

## Method

Plain r-adding-walk Pollard rho + distinguished points (van Oorschot–Wiener),
12 threads, 128-bit Montgomery arithmetic, batch-inverted affine EC. The hot loop
uses unchecked indexing and a cached jump-table slice → **~286 M EC-steps/s** on
this machine (≈2.4× the first 80-bit run).

No negation map: a naive 2-cycle escape lets longer fruitless cycles trap walks
(the DP table stops growing while step count climbs); plain rho has no involution
and therefore no fruitless cycles — every step is productive, confirmed live by
the DP-table count tracking `steps / 2²³` at ~100 % unique throughout the run.

Full, auditable source is in `solver/`.

## Cost

| | |
|---|---|
| Hardware | 1 commodity machine (Apple Silicon), **12 worker threads** |
| Throughput | ~**286 M** EC-steps/s (avg over the run) |
| Steps to collision | **15,685,534,042,624** (≈ 1.569 × 10¹³) |
| Wall-clock | **54,749 s ≈ 15.2 h** |
| Expected (rho mean) | `√(πn/2) ≈ 1.2533·√n ≈ 1.95 × 10¹³` steps |

Landed at ~0.80× the rho mean — an unremarkable draw within rho's variance.

## Reproduce

```bash
cd solver
cargo build --release
# args: p a b Gx Gy Qx Qy n [dpbits] [threads]
CKPT=ckpt.bin ./target/release/rho solve \
  242741740111627334084264707 134984510913594150542583735 8920491190001754595878423 \
  141335002058520870978941080 113968915092050568385100851 \
  175341707950410501134136777 15107136843117836188849586 \
  242741740111604890660673023 23 12
```

## Scope / honesty

A *generic* break: it spent the `√n` work, nothing more — no weakness in the
curve. The next open board instance, 96-bit, needs ≈ 2⁴⁸ steps ≈ ~2 weeks at this
throughput on one machine; 112/128-bit are far out of reach for generic methods on
commodity hardware.
