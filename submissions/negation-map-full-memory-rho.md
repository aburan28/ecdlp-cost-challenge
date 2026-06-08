# Submission: negation-map **full-memory (θ=1)** rho

**File changed:** `src/solver/mod.rs` only.

## Result (local, bits=40)

| Measurement | Ratio ×rho | Ops |
|---|---:|---:|
| Official `benchmark.sh` (5-trial mean, default seed) | **0.677×** | 666,158 |
| 30 seeds × 5 trials (150 runs, 0 failures) | **0.657×** | — |
| Shipped solver, same 20 seeds (head-to-head) | 0.885× | — |
| This solver, same 20 seeds | 0.74–0.78× | — |

Also verified: bits=28 ≈ 0.54–0.62× (CI gate), bits=48 solves correctly in ~23 s
(0.58×, single trial). Zero incorrect answers across all runs.

That is a **~17–25 % reduction** in mean group operations versus the shipped
negation-map distinguished-point rho, landing at the negation-map rho optimum
`√(πn/4) ≈ 0.707×` (sampling can dip below it, as the README notes).

## The idea

The oracle scores **group operations only — memory is free and unscored.**

1. **θ = 1 (store every point).** The distinguished-point trick exists to bound
   *memory*; it does not help the *op* count. Worse, it adds a tail: after two
   trails collide they must each walk ~`1/θ` further to the next distinguished
   point, an overhead of ~`W/θ` ops (with the shipped `W=512`, `θ=1/512` that is
   ~260k ops — a large fraction of the score). With memory free, the optimal
   choice is θ = 1: store every visited point and detect the collision the instant
   it happens. This deletes the DP tail and lets the walk terminate at the true
   birthday bound `√(πn/4)`.

2. **Correct, deterministic fruitless-cycle handling.** The negation map's hazard
   is short cycles `X→…→X` that carry no new linear information (same canonical
   point, same coefficients). With a full table they are trivial to detect: a
   revisit whose stored coefficients give `db = 0` is exactly a fruitless return,
   escaped with a single deterministic doubling. A genuine cross-trail meeting has
   `db ≠ 0` and solves immediately. (The shipped solver escaped via a per-walk
   history and doubled the *current* point rather than the cycle's canonical
   point, so colliding trails could fail to merge — the source of its bimodal
   ~1.2M-op runs.)

3. **Cheap setup.** Setup ops are counted too. The jump table is built from shared
   `2^j·P` / `2^j·Q` doubling-ladders plus small (`MBITS`-wide) coefficients
   assembled from set bits, costing ≈ `2·MBITS + R·(MBITS−1)` ops instead of `R`
   full-width `scalar_mul`s — a ~5× setup reduction (visible at bits=28:
   1.68× → 0.54×). Small jump magnitudes don't hurt mixing (Teske: walk quality
   is set by the partition count `R`, not jump size).

4. **`W` sized to the tier** so the (exactly `W`) final-batch overshoot and the
   `W`-op start-up chain stay ≲0.5% of the score, while keeping round trips bounded.

This is at the constant-factor floor for a generic negation-map rho; going lower
*in expectation* would require leaving the generic-group model (the representation
track), which the scored arena forbids.
