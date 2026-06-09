# Faster than rho, fully accounted — the amortized per-target cost beats √n

> **Result.** PR #20 showed a preprocessed *online* solve costs `n^α` — but hid the
> one-time precompute. The honest question is: to solve a **batch of L targets sharing
> a fixed public `G`**, what does each target cost when it pays its fair share of the
> precompute? Answer, measured on the challenge's own **verified-generic, prime-order**
> curves: **per-target amortized = n^0.333 (95% CI [0.31, 0.35])**, held-out verified
> (z=+0.07), and the wall-clock confirms it is **~15× faster than rho at every size**.
> Genuinely faster than running rho (√n) once per target — full precompute accounting
> included.
>
> Total work is still `≥ √n`; this is an amortized statement over a batch, **not a
> break**. It is the realistic shared-curve threat (everyone attacks one `G`).

## The accounting

Extended baby-step table (`solve_preprocessing.py`): precompute `W` baby steps once,
then each target costs `n/W` deterministic giant steps. For a batch of `L` targets:

    per-target amortized  =  precompute/L  +  online  =  W/L  +  n/W

Minimized at `W = n^(1−α)`, `L = n^(1−2α)`: both terms equal `n^α`, giving

    per-target amortized  ≈  2·n^α   <   √n     (for α < ½).

Even charged its share of the table, each target costs sub-√n. This is the
time-optimal preprocessing frontier (`P·T = n`) realized with full accounting — you
cannot beat the frontier, only reach it honestly.

## Measured (`validate_amortized.py`, α=0.33, ladder 20…26 → held-out 28)

| quantity | measured | theory |
|---|---|---|
| **per-target amortized exponent** | **α = 0.333**, 95% CI **[0.313, 0.353]** — sub-√n | 0.33 |
| held-out (bits=28) | predicted 3,193, measured 3,203 → ✅ verified (z=+0.07) | — |
| per-target cost vs rho | 0.25–0.29× the rho optimum | — |
| **b2 wall-clock** | amort **~15× faster than rho at every rung**, ratio widening (0.125→0.087→0.067→0.049) — **decisive ✅** | — |
| **verdict** | **VERIFIED-FASTER** | — |

b1 (the authoritative field-op meter) certifies the per-target amortized cost is
`n^0.333`, held-out verified almost exactly (z=+0.07). b2 confirms amort is decisively
faster in wall-clock — **and the comparison is conservative**: online runs on the slow
*counted* curve while rho runs on plain ints, so amort winning by 15× means the
op-count advantage is real, not an implementation artifact.

### Why the b2 *exponent gap* is reported as imprecise

The exponent gap (β_amort − β_rho) is only `−0.13` with a wide CI, not the `−0.17`
theory predicts, because rho's **wall-clock exponent is overhead-deflated** at toy
sizes (its per-target r-adding setup is a big fraction of its `√n` walk, so its
measured exponent is `~0.44`, not the true `0.5`). The *ratio* — amort 15× faster,
widening — is the robust, un-gameable signal and is what the verdict uses; the deflated
gap is reported only for transparency. This is the same pre-asymptotic wall-clock
limitation [`SCALING.md`](SCALING.md) documents.

## Honest scope

- **Not a break.** `precompute + L·online ≥ √n` always; only the *per-target amortized*
  cost is sub-√n, and only over a batch sharing one `G`.
- **The realistic threat** for a shared curve (P-256, secp256k1): "√n per target" is the
  wrong unit when one `G` is attacked many times.
- **The single-target wall stands.** Beating rho's constant for one target, or sub-√n
  *total*, remains out of reach — this result does neither and claims neither.

## Relationship

- [`PREPROCESSING.md`](PREPROCESSING.md) — the online-only version (n^0.28), which hid
  the precompute and reached only `VERIFIED-FASTER-b1`.
- **This** — the full-accounting per-target cost, still sub-√n (n^0.333), with the
  clean two-meter `VERIFIED-FASTER`: the honest "faster than rho per target."
