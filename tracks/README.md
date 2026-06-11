# Harness tracks

The repository now has three deliberately separate ways to score ECDLP work. They should not share one leaderboard, because they reward different things.

## Track A: generic constant-factor arena

**Question.** How close can a generic-group implementation get to the rho constant?

**Meter.** Oracle-counted group operations.

**Allowed information.** Opaque tokens only; no curve representation.

**Expected winner class.** Pollard-rho family algorithms: negation map, r-adding walks, distinguished-point tuning, full-memory collision detection, Gaudry-Schost style constant-factor variants.

**Promotion rule.** Lower mean `group_ops / sqrt(n)` wins, but this is only a constant-factor board. It should not be described as evidence for a new ECDLP algorithmic exponent.

## Track B: scaling-law arena

**Question.** What cost law does the algorithm obey?

**Meter.** A fitted law

```text
group_ops ~= c * n^alpha
```

from a ladder of bit sizes plus a held-out prediction check.

**Primary rank.** Lower `alpha`, but only when confidence intervals are disjoint and the held-out tier verifies.

**Secondary rank.** Lower `c` when exponent confidence intervals overlap.

**Novelty rule.** In the opaque generic oracle, `alpha < 0.5` should be treated as a regime/measurement bug unless the held-out tier verifies and the submission uses a representation-dependent meter. A generic-oracle solver with verified `alpha ~= 0.5` is a rho-class or generic-collision-class result even if its constant is excellent.

## Track C: representation research arena

**Question.** Does the algorithm exploit the published curve representation in a way that beats a same-hardware rho control?

**Meter.** Verified solution plus representation-aware costs, for example:

```text
field_adds
field_muls
field_invs
group_adds
scalar_muls
memory_bytes
wall_time_ms
precompute_bytes
success_rate
```

**Allowed information.** Full public curve data: `p, a, b, n, G, Q`.

**Expected winner class.** Non-generic approaches: summation-polynomial/index-calculus experiments, decomposition oracles, isogeny/Jacobian-transfer attempts, special-coordinate attacks, endomorphism-structure exploitation, or other representation-level methods.

**Promotion rule.** A result is promoted as a research result only if it provides:

1. a recovered `k` or a clearly scoped partial-measurement artifact,
2. a mechanism claim,
3. a fitted cost law or falsifiable prediction,
4. a held-out validation run, and
5. a comparison against the same-hardware rho baseline.

## Submission classes

Use these labels in `CLAIM.md` and generated score reports:

| Class | Meaning |
|---|---|
| `rho_constant` | Rho-family constant-factor improvement. Valuable, but not novel asymptotics. |
| `generic_collision` | Generic collision search that is not literally the shipped rho implementation, but still representation-blind. |
| `representation_constant` | Uses curve representation, but measured scaling is still compatible with `alpha = 0.5`. |
| `representation_subsqrt_candidate` | Uses curve representation and has a held-out-verified upper confidence bound below `0.5`. |
| `failed_or_overfit` | Wrong `k`, missing mechanism claim, failed held-out prediction, or unsupported scaling claim. |

## Required files for research submissions

A research submission should live under:

```text
submissions/research-<name>/
  submission.toml
  CLAIM.md
  results.json
  scaling.json
  WRITEUP.md
```

The template in `submissions/research-template/` gives the expected shape.

## Practical policy

The default README leaderboard can stay focused on generic group operations, but the front-page research claim should be based on Track B or Track C. The slogan is:

> A solved instance is a point. A new algorithm is a predictive cost law plus a mechanism.
