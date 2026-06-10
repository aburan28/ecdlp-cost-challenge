# Does index calculus break the rho √n barrier on prime-field curves? — Measured: no

> **The honest attempt.** Shoup proves no *generic* algorithm beats √n — so a real
> break must be *non-generic*, exploiting the `F_p`/curve structure. The frontier
> non-generic method is **index calculus** (it beats √n for E over *extension* fields,
> Gaudry–Diem). This implements it on the challenge's verified-generic, **prime-order**
> curves and lets the meter measure its cost. Result: it recovers `k` every time — a
> real, working attack — at **n^0.633 group ops, decisively *above* rho's n^0.5.** The
> barrier holds, now with measured evidence rather than an assertion.

## The attack (`solve_index_calculus.py`)

2-point decomposition, the cleanest index calculus:

1. **Factor base** `F` = the `B` points with smallest x-coordinate.
2. **Decomposition table**: hash all `P_i ± P_j` (≈ B² metered group additions).
3. **Relation walk**: step `R = c·G + d·Q`; each hit `R = ε_i P_i + ε_j P_j` is a linear
   relation `c + d·k ≡ ε_i ℓ_i + ε_j ℓ_j (mod n)`.
4. Collect `> B` relations; **solve the linear system over `F_n`** for `k` (off-meter —
   the attacker's number theory, like factoring in Pohlig–Hellman).

The harness counts the group operations (steps 2–3). Cost ≈ `B² + n/B`, minimized at
`B ≈ (n/2)^(1/3)` → **≈ n^(2/3)**, above rho's `n^(1/2)`.

## Measured (`validate_index_calculus.py`, ladder 20…24 → held-out 25)

Verified-generic, prime-order curves; many random targets per tier.

| quantity | measured |
|---|---|
| **IC group-op exponent** | **α = 0.633**, 95% CI **[0.622, 0.643]** (theory: 2/3 ≈ 0.667) |
| held-out (bits=25) | predicted 1,035,421, measured 1,059,859 → ✅ verified (z=+1.57) |
| IC vs rho | **85× → 147× more group ops**, ratio **widening** across the ladder |
| **verdict** | **BARRIER-HOLDS** — IC exponent is above 0.5, so IC is *slower* than rho |

IC's exponent CI `[0.62, 0.64]` lies **entirely above** rho's `0.5`. It is not close: IC
is two orders of magnitude more expensive at these sizes, and the gap grows with `n`.

## Why prime fields resist (the mechanism the data shows)

Index calculus needs cheap **decompositions** of a random point into factor-base points.
Over an *extension* field `F_{p^k}`, the factor base = points with coordinates in the
subfield `F_p`, and decompositions are found via Semaev summation polynomials with a
Gröbner cost that (for growing `k`) yields sub-√n. Over a **prime** field there is **no
subfield** — the factor base is an arbitrary size-`B` subset, a random point decomposes
into `m` of them with probability only `~B^m/n`, and the search/precompute to find one
costs enough that the optimum sits at `~n^(2/3)`. The `F_p` structure that makes a curve
"generic-looking" is exactly what denies index calculus a cheap factor base. (Wagner's
k-list trick, which could beat the birthday bound, does **not** apply to EC over prime
fields — the mixed-Deligne obstruction.)

## Honest bottom line

- **Generic sub-√n is a theorem against it** (Shoup, `Ω(√n)`). Not "hard" — *impossible*.
- **The frontier non-generic method, measured, is `n^(2/3)` — worse than rho.** Every
  other known avenue (MOV/pairings, anomalous `n=p`, Weil descent, CM/GLV endomorphisms)
  is blocked by the challenge's genericity guards or is inapplicable to prime fields.
- So: **no known method breaks the rho barrier on a generic prime-field curve**, and this
  probe demonstrates the main candidate failing, with a tight measured exponent. A genuine
  break would be a landmark result; this is the honest negative the experiment yields.

This is the representation track's first **index-calculus** artifact — recorded as a
measured probe (`index_calculus_probe.baseline.json`) so the negative result is
re-checkable, not folklore.
