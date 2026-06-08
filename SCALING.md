# The scaling track — score the cost *curve*, not the instance

> **Reframe.** "Find `k`" is a **point**; "a faster algorithm" is a **slope**. A
> single solved instance confounds three things you cannot separate at one size —
> luck, the constant factor, and the exponent. This track stops scoring instances
> and scores the **cost law** `group_ops ≈ c · n^α` instead, fit across a ladder of
> sizes and **verified by held-out prediction**. Recovering `k` is demoted to the
> per-rung measurement.

This sits on top of the single-tier [Beat-Rho arena](README.md): same trusted
oracle, same counted group ops, same common-random-numbers grading — but run at a
*ladder* of bit-sizes and reduced to `(α, c)` rather than one number.

## What it measures

`tools/scaling_battery.py` runs the oracle at each tier in a `--ladder`, fits

$$\log(\text{group\_ops}) = \alpha\cdot\log(n) + \log(c)$$

by least squares, and **bootstraps the CIs over the trial battery** — it resamples
the per-trial op counts (parsed from the oracle's own stderr) so rho's heavy
per-trial variance flows honestly into the error bars on `α` and `c`. A submission's
identity becomes `(α, c)`, written to `scaling.json`.

- **`α` — the exponent.** The only quantity that means "asymptotically faster." In
  the generic arena Shoup pins `α = 0.5`; a *genuinely* faster algorithm (sub-√n)
  has `α < 0.5`, and can only appear in the representation track (a different meter).
- **`c` — the constant.** The existing `0.71×`-style game (negation map, DP rate,
  Gaudry–Schost). When two solvers share an exponent, the smaller `c` wins.

## Predict-then-verify (the anti-gaming core)

A fit is worthless if it only describes the points it was fit on — that rewards
overfitting, precompute tables, and lucky draws. So the battery **fits on the
ladder, predicts a held-out tier it never saw, then measures that tier** and checks
the prediction:

- The 95% band combines **parameter uncertainty** (the bootstrap spread of `(α,c)`
  at `log n_holdout`) with the held-out mean's **own sampling SE** (a rho mean's
  relative SE over `T` trials), added in quadrature on the log scale.
- **Pass** ⟺ the measured held-out cost lands in that band. A real cost law predicts
  its own next rung; an overfit or pre-asymptotic curve mispredicts.

This is a train/test split for cost laws. `beats_curve.py` will not promote a
submission whose held-out prediction did not verify — an unproven fit is to this
track what an invalid `k` is to the arena.

## ⚠️ Site the ladder in the asymptotic regime (a measured caution)

The fitted exponent is only meaningful where the *constant* has stabilized.
DP-rho carries fixed setup overhead that is dominant at tiny `n` and amortizes
away as `n` grows, so a ladder placed too low reads a **falsely small `α`** — pure
artifact, not a faster algorithm. The held-out check catches exactly this.

Measured, shipped negation-map DP-rho solver, seed `0x12345678` (reproduce with the
commands below):

| ladder (fit tiers) | regime | fitted `α` | predicts bits=40 | measured bits=40 | held-out |
|---|---|---:|---:|---:|:--:|
| `24,28,32,36` | pre-asymptotic (ratio swings 1.33× → 0.62×) | **0.41** [0.39, 0.44] | 453k ops | 735k ops | ❌ z=+3.3 |
| `32,35,38` | plateaued (ratio ≈ 0.74–0.79×, flat) | **0.48** [0.43, 0.53] | 678k ops | 688k ops | ✅ z=+0.11 |

The low ladder *looks* sub-√n (`α=0.41`) and is **rejected**: it cannot predict its
own bits=40 rung. The plateaued ladder recovers `α≈0.5` — its 95% CI **straddles
Shoup's 0.5** — and its prediction nails the held-out rung (z=+0.11). Lesson: in
the generic arena, an honest `α` ladder must live where ops/√n has flattened
(here, bits ≳ 32); read `α < 0.5` as "check your regime," not "I broke ECDLP,"
unless you are in the representation track with a non-generic meter.

## How to run

```bash
# default ladder 24,28,32,36 + held-out 40 (fast; demonstrates the regime caveat)
python3 tools/scaling_battery.py

# a plateaued ladder with more trials (tighter means), same held-out target
python3 tools/scaling_battery.py --ladder 32,35,38 --holdout 40 --trials 40

# official-style: one sealed secret seed across every rung + holdout, large trials
python3 tools/scaling_battery.py --seed 0x<SECRET> --ladder 32,36,40,44 --holdout 48 --trials 64
```

One `--seed` is applied to every rung **and** the holdout, so the whole ladder is a
single paired comparison (common random numbers — instance luck cancels). The
battery snapshots and restores `results.tsv`, so it never pollutes the single-tier
arena history; its artifact is `scaling.json`. Exit code is `3` if the held-out
prediction failed.

## Promotion — comparing curves

`tools/beats_curve.py` is the cost-curve analogue of `beats_best.py` (which compares
single-tier *points*). It ranks *algorithms*:

```bash
python3 tools/beats_curve.py --score scaling.json --against scaling.baseline.json
```

- **Gate 0 (proof).** The candidate's held-out prediction must have verified, else
  REJECT — an unproven fit can't be a record.
- **Gate 1 (exponent).** Lower `α` wins when the 95% CIs are **disjoint** — a true
  asymptotic win. (Generic arena: Shoup makes this a tie; the constant decides.)
- **Gate 2 (constant).** When the exponent CIs overlap, the lower constant `c`
  wins — the constant-factor game, correctly demoted to the tiebreak.

**The ledger (two files).** A run writes its candidate to `scaling.json` (transient,
git-ignored); the promoted record is the committed `scaling.baseline.json`. Mirror
`beats_best.py`: locally you gate against the saved baseline, and for the true
promoted frontier you gate against `main`:

```bash
python3 tools/beats_curve.py --against <(git show origin/main:scaling.baseline.json)
cp scaling.json scaling.baseline.json   # promote: ONLY after an ACCEPT, then commit
```

Grade every candidate on the **same sealed seed** (the gate warns on a seed
mismatch) so the comparison is paired — common random numbers cancel instance luck,
exactly as in the single-tier arena.

## Honest scope

Inside the opaque generic-group oracle, `α = 0.5` is a floor (Shoup), so this track
*confirms* the exponent and competes on `c`. Bending the exponent below `0.5`
requires the **representation** — a different, non-generic cost meter — which is the
[First-Blood / representation track](first_blood/README.md). This same fitter scores
that curve once such a meter exists; building it (counted field arithmetic vs. a
same-hardware rho control) is the next design step.
