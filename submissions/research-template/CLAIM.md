# Research claim

## Summary

One paragraph describing the algorithm, the instance family, and the claimed improvement.

## Claim label

Choose one:

- `OBSERVATION`: measured behavior only; no predictive or theoretical claim yet.
- `HEURISTIC`: a mechanism plus a cost model that is expected to extrapolate.
- `THEOREM`: a proof-backed claim with explicit assumptions.

## Algorithm family

Examples:

- rho-family constant-factor search
- generic collision search
- BSGS / table-based search
- summation-polynomial / index calculus
- isogeny walk / isogenous-neighbor search
- transfer to higher-dimensional abelian variety
- endomorphism / automorphism exploitation
- decomposition oracle / factor-base method
- other

## Mechanism

What structure is the algorithm exploiting?

Be specific. For example, do not write "Semaev is faster." Write what measurable object changes: factor-base hit rate, Gröbner degree, relation density, decomposition success probability, memory exponent, transfer degree, endomorphism orbit size, etc.

## Generic or representation-dependent?

State one:

- `generic`: uses only opaque group operations or token equality.
- `representation-dependent`: uses field coordinates, curve equation, polynomial systems, endomorphism data, isogenies, pairings, or any other published representation detail.
- `hybrid`: uses both, and explains which part is representation-dependent.

## Expected cost law

Fill in what you claim. Use `unknown` for fields not yet measured.

```text
group_ops      ~= c_g * n^alpha_g
field_ops      ~= c_f * n^alpha_f
memory_bytes   ~= c_m * n^alpha_m
precompute     ~= c_p * n^alpha_p
success_prob   ~= p_s per trial
```

## Predictions before held-out validation

List concrete predictions before running the held-out tier.

| Bits | Predicted cost | 95% band | Notes |
|---:|---:|---:|---|
| 44 | unknown | unknown | |
| 48 | unknown | unknown | |

## Falsifier

What result would make this claim fail?

Examples:

- held-out cost lands outside the prediction band,
- fitted `alpha` confidence interval overlaps `0.5`,
- relation density tracks the rho baseline,
- Gröbner degree stays flat but wall-time grows exponentially,
- decomposition succeeds only after birthday-scale work.

## Baseline

Describe the baseline you compare against:

```text
baseline = negation-map full-memory rho
hardware = ...
seed policy = common random numbers / independent seeds
trials = ...
```

## Result classification

Choose the most honest class:

- `rho_constant`
- `generic_collision`
- `representation_constant`
- `representation_subsqrt_candidate`
- `failed_or_overfit`

## Repro commands

```bash
# commands to reproduce the measurements
```
