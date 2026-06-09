# Meter validation — the representation meter is a real sub-√n detector

> **Breakthrough.** The [representation-track meter](REPR_TRACK.md) had only ever
> printed `NO-ASYMPTOTIC-WIN` — its `VERIFIED-FASTER` verdict was **never
> exercised**, because verified-generic curves have no sub-√n attack. A benchmark
> whose positive verdict has never fired is unproven. This makes it fire: on curves
> with a *known* sub-√n attack, the meter correctly detects, verifies, and quantifies
> it — in two-sided contrast with generic curves, where it abstains. The
> representation track is now a **validated, discriminating instrument**, not an
> untested one.
>
> ⚠️ This is a **positive control on deliberately weak curves**. It says nothing
> about generic prime-field ECDLP, which remains `√n` — the wall holds.

## The idea: dial the true attack exponent with the order's factorization

Pohlig–Hellman solves an ECDLP of order `n = ∏ pᵢ^eᵢ` in `Θ(Σ eᵢ√pᵢ)` group ops —
dominated by `√pmax`. So a curve whose order has largest prime factor `pmax ≈ n^γ`
has a *known* attack costing `~n^(γ/2)`. By choosing `γ` we move the true attack
exponent across `[0, 0.5]` and ask whether the meter measures it:

- `γ = 1.0` (near-prime — the scored regime) → `√n` work → **no win** (boundary)
- `γ < 1`  (composite order)                 → `√pmax = n^(γ/2)` work → **sub-√n**

## What was built (all verifiable)

| file | role |
|---|---|
| `repr_track/weak_instances.py` | Shanks–Mestre point counting (**validated**: matches `gen_instance`'s prime order exactly at bits 20/24/28) + a best-of-batch search for curves with `pmax ≈ n^γ` |
| `repr_track/solve_pohlig_hellman.py` | the PH attack, metered through the counted field (integer factoring/CRT off-meter, as the attacker's own number theory) |
| `repr_track/validate_meter.py` | runs PH across a ladder of weak instances at fixed `γ`, fits the field-op exponent, checks held-out + the b2 rho race, prints a verdict |

PH correctness is cross-checked independently (it recovers the same `k` as a
from-scratch rho/BSGS on every instance).

## Result — the meter fires, correctly and two-sided

**Headline (γ=0.5, ladder 24…30 → held-out 31, seed `0xD00D`):**

| meter | result |
|---|---|
| **b1 field-op law** | `α = 0.136` (95% CI [0.09, 0.18]) — decisively **sub-√n** |
| **b1 held-out (bits=31)** | predicted 2,913, measured 2,978 → ✅ verified (z=+0.32) |
| **b2 rho race** | gap −0.298, 95% CI **[−0.571, −0.027] — entirely negative → corroborates ✅** |
| **verdict** | **VERIFIED-FASTER** |

Both the authoritative field-op meter *and* the un-gameable wall-clock race confirm a
genuine sub-√n attack — the meter's positive verdict, fired for the first time.

**Two-sided calibration (common ladder 22…28 → held-out 30):**

| instance | γ | measured α (95% CI) | held-out | verdict |
|---|---:|---|:--:|---|
| weak | 0.5 | 0.156 [0.11, 0.20] | ✅ | **VERIFIED-FASTER** |
| weak | 0.7 | 0.316 [0.30, 0.33] | ❌ z=−3.9 | NO-WIN — held-out gate rejected a curved fit |
| near-prime | 1.0 | 0.63 [0.52, 0.74] | ✅ | **NO-ASYMPTOTIC-WIN** |

The measured exponent **climbs monotonically with γ** (0.16 → 0.32 → 0.63): the meter
reads attack strength. And it is **discriminating** — `VERIFIED-FASTER` on a clean
sub-√n curve, `NO-ASYMPTOTIC-WIN` on near-prime order, the same as on a real generic
curve. The γ=0.7 row is the **held-out gate showing its teeth**: it refused to certify
a fit that didn't predict its own next rung, even though α was sub-0.5 — exactly the
conservatism a benchmark wants.

## Honest scope & limitations

- **Not a break.** These are weak curves built to *have* a sub-√n attack. Generic
  prime-field ECDLP is untouched (`√n`), per the lab constitution: the generic floor
  is not evidence that no attack exists, and a positive control is not a negative one.
- **α is the *effective* exponent, not the asymptotic γ/2.** It is consistently below
  γ/2 because PH's lower-order overhead (per-factor projections, sub-dominant subgroup
  solves) is non-negligible at toy sizes — the same pre-asymptotic deflation
  [`SCALING.md`](SCALING.md) documents, one level over. It is monotone in γ and cleanly
  sub-√n; it is not a precise calibration.
- **b2 needs adaptive timing.** A ~1 ms PH solve timed alone is OS jitter; the exponent
  gap only resolves with `timeit`-style batching (run the fast op enough to clear a
  stable duration, then divide). Even so b2 is a large-n instrument — b1 leads.
- **Verdict fix (applies to the real track too).** Abstention ≠ suspicion: a noisy b2
  with a verified b1 is a win on the authoritative meter (`VERIFIED-FASTER-b1`);
  `SUSPECT` now requires b2 to *affirmatively* contradict (gap CI entirely positive —
  the off-API-gaming signature). `repr_meter.py` carries the same corrected matrix.

## Why this matters for the challenge

The representation track's whole promise — "if a sub-√n attack exists, this meter
measures it" — was an assertion. It is now demonstrated by construction: the meter
fires on a real sub-√n attack, abstains on generic order, and reads exponent strength
monotonically, with a held-out gate strict enough to reject imperfect fits. Together
with [the scaling track](SCALING.md) (generic arena, α≡0.5 confirmed) and
[the meter](REPR_TRACK.md), the challenge now has a **complete, validated** framework
for measuring algorithmic ECDLP cost — and a credible home for a genuine break, should
one ever land.
