# First-Blood board — the representation track

The scored [Beat-Rho arena](../README.md) deliberately hides the curve, so it can
only measure *generic* (representation-blind) algorithms, where `√n` is a proven
floor. **This board is the opposite half of the lab constitution:** it publishes
the full curve and dares you to recover `k` by *any* method — generic or not.

> A genuine sub-`√n` attack on a generic prime-field curve would be a major
> result. The generic floor in the arena is **not** evidence that no such attack
> exists. This board exists so that, if one does, it has somewhere to land.

## The instances

Each `instance_public_<bits>.json` is a **verified-generic** prime-field curve
(prime order, non-anomalous, large MOV embedding degree, `j ∉ {0,1728}`) with a
published generator `G` and target `Q = k·G`. **`k` was generated at random and
immediately discarded** — nobody, including us, knows it. The instance is a
genuine challenge, self-verified by `k·G == Q`.

| File | Field size | Status | First solver |
|---|---:|---|---|
| `instance_public_80.json`  | 80-bit  | 🔴 SOLVED | **aburan28** — generic parallel-DP rho, 12 cores, ~36 min ([writeup](../submissions/first-blood-80/WRITEUP.md)) |
| `instance_public_96.json`  | 96-bit  | 🟢 OPEN | — |
| `instance_public_112.json` | 112-bit | 🟢 OPEN | — |
| `instance_public_128.json` | 128-bit | 🟢 OPEN | — |

These are **toy** by cryptographic standards (real curves are 256-bit), but a
classical machine cannot brute-force an 80-bit ECDLP by generic means without
serious compute (`√n ≈ 2^40` group ops), and 112–128-bit is out of reach for
generic methods on commodity hardware. So a solve here means one of:

1. you spent the generic `√n` work (a feat in itself at ≥96-bit), **or**
2. you found a **non-generic** shortcut — the actual prize.

Either way: **say which.** A scoped writeup ("generic VW on N cores for T hours"
vs. "exploited structure X") is the whole point. Per the lab constitution, report
the method honestly and label the claim (`OBSERVATION` / `HEURISTIC` / `THEOREM`).

## Rules

- Recover `k` for any listed instance by any method you can document.
- Verify locally, then submit `k` + a method writeup. Verification is trivial and
  unforgeable — it's one scalar multiplication:

  ```bash
  python3 verify_first_blood.py instance_public_96.json <k>
  ```

- No oracle, no op counter here — this track is about *whether* you can break a
  generic prime-field curve at all, not about constant factors.

## Regenerate / add instances

```bash
sage ../tools/gen_instances.sage <bits> <seed>   # writes instance_public_<bits>.json
```

The generator enforces the genericity guards and discards `k`. To post a new
challenge, generate, commit the JSON, and add a row above.
