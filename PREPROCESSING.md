# Sub-√n online ECDLP on GENERIC curves — the preprocessing breakthrough

> **Result.** "Generic prime-field ECDLP costs √n" carries an unstated qualifier:
> *per single target, with no precomputation*. For a **fixed public generator `G`** —
> exactly what everyone shares for P-256, secp256k1, … — a one-time precomputed table
> makes every subsequent **online** DLP cost **sub-√n**. Measured on the challenge's
> own verified-generic, prime-order curves, the online exponent is **α = 0.28 (95% CI
> [0.22, 0.34])**, held-out verified, with the precompute/online tradeoff law
> `P·T ≈ n` confirmed empirically (`P = n^0.70`, `T = n^0.28`, product `n^0.98`).
>
> This is **not a break** — total work `P + T` is still `≥ √n`. It sharpens the
> challenge's central claim: the √n security is *amortized-online-free*, and the
> amortized per-target online cost — the right metric when one curve is attacked many
> times — is genuinely sub-√n. The scored *arena* defeats this on purpose by
> re-randomizing the token encoding every run; the **representation track** (fixed,
> public curve) is exactly where it bites, and it bites on **generic** curves, not
> contrived weak ones.

## The attack (deterministic, clean to measure)

An **extended baby-step table**. Precompute the baby steps `{j·G : 0 ≤ j < W}` once
(`solve_preprocessing.precompute`); then for each target `Q`, take giant steps
`Q − i·(W·G)` until one lands in the table, giving `k = i·W + j`
(`solve_preprocessing.solve_online`). Online cost is `⌈k/W⌉ ≤ n/W` giant steps —
**deterministic** (no rho variance), so the meter reads a clean exponent:

|            | cost          | exponent (W = n^(1−α)) |
|---|---|---|
| precompute | `P = W`       | `n^(1−α)`  (once, amortized) |
| online     | `T = n/W`     | `n^α`,  α < ½ |
| product    | `P·T = n`     | `n^1` |

Choosing the table-size schedule `W(n) = n^(1−α)` dials the online exponent `α`.

## Measured (`validate_preprocessing.py`, α=0.3, ladder 20…26 → held-out 28)

Curves are **verified-generic, prime order** from the trusted `gen_instance`; we use
only `p,a,b,G,n` and mint many targets sharing the one fixed `G`.

| quantity | measured | theory |
|---|---|---|
| **online exponent** | **α = 0.282**, 95% CI **[0.224, 0.342]** — entirely sub-√n | 0.30 |
| online held-out (bits=28) | predicted 555, measured 653 → ✅ verified (z=+1.11) | — |
| **precompute exponent** | **n^0.700** | n^(1−α) = n^0.70 |
| **tradeoff P·T** | **n^0.982** | n^1 |
| b2 online-vs-rho race | β_online = 0.34 < β_rho = 0.50, gap −0.16 (directionally corroborates) | — |
| **verdict** | **VERIFIED-FASTER-b1** | — |

The authoritative field-op meter (b1) certifies a genuine sub-√n online cost on a
generic curve, held-out verified, and the precompute exponent + `P·T ≈ n` confirm the
tradeoff law. The wall-clock cross-check (b2) agrees in direction (β_online tracks the
b1 online α, both well below rho's 0.5) but its CI is **timing-floor-limited**: a
microsecond online solve is below stable wall-clock resolution even batch-timed —
hence `VERIFIED-FASTER-b1` rather than the full two-meter verdict.

## Why this is the real breakthrough (and its honest limits)

- **It's on GENERIC curves** — the actual instances the challenge ships, not weak
  ones. The earlier meter-validation needed deliberately weak (composite-order)
  curves; this needs no weakness at all, only a *shared, fixed `G`*.
- **It's the realistic threat model.** Everyone attacking secp256k1 shares one `G`;
  preprocessing is amortized across all of them. "√n per target" is the wrong unit.
- **It is not a break.** `P + T ≥ √n` always; the problem's total hardness is intact.
  The result is about the *online* cost, and only in the fixed-curve/amortized model.
- **Toy sizes.** `bits ≤ 28` so a metered Python solver runs; the *exponent* and the
  `P·T ≈ n` law are the deliverables, not any real key.

## Relationship to the rest of the challenge

- [`SCALING.md`](SCALING.md) — generic arena, α ≡ 0.5 confirmed (no preprocessing,
  tokens re-randomized).
- [`REPR_TRACK.md`](REPR_TRACK.md) + [`METER_VALIDATION.md`](METER_VALIDATION.md) —
  the representation meter, validated to detect sub-√n (on weak curves).
- **This** — the representation track's first sub-√n result on *generic* curves, via
  preprocessing, measured by the same meter. The challenge's "generic = √n" thesis now
  carries its proper qualifier, demonstrated and quantified.
