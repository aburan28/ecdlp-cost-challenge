# Design & threat model

This note explains *why* the challenge is built as an opaque generic-group
oracle, and what its score does and does not mean. It uses the lab's claim
labels.

## 1. The artifact-cost benchmark pattern, and why ECDLP is different

`OBSERVATION.` An artifact-cost benchmark scores a **resource intrinsic to a
submitted artifact** (e.g., the Toffoli count of a submitted reversible circuit).
The contestant submits a reversible circuit (an op stream); a trusted stage
re-simulates it, counts Toffolis, and checks it computes point-addition on hidden
test points. The contestant controls the *artifact* but not the *scoring
function*, which the trusted stage recomputes. There is no way to "report a low
Toffoli count" because the count is a deterministic function of the submitted
circuit that the harness re-derives.

`OBSERVATION.` ECDLP has **no short cost-bearing artifact**. Once you know `k`,
the proof is just `k` (16 bytes), and verifying it (`k·P = Q`) is one scalar
multiplication. The *effort* of the search is not a property of any short object
you can submit. Concretely:

`NEGATIVE RESULT (certificate length ≠ search effort).` Suppose we tried to score
the length of a submitted **collision certificate** — two addition chains
`a₁P+b₁Q` and `a₂P+b₂Q` reaching the same point, which yields
`k = (a₁−a₂)(b₂−b₁)⁻¹`. A successful attacker can always exhibit such a
certificate with chains of length `O(log n)` (small coefficients, double-and-add),
even though *finding* it cost `√n` work. So certificate length measures "how short
is the proof," not "how hard was the search," and is gameable down to `O(log n)`
for **any** attack. Re-execution of a minimal op stream therefore cannot score the
search. ∎

`CONCLUSION.` To score *group operations of the search*, the trusted code must
**observe the search as it happens** and own the counter, and the solver must be
**unable to perform a group operation off-meter**.

## 2. The only way to make the count unforgeable: hide the representation

`OBSERVATION.` If the solver is handed `(p, a, b)` and the coordinates of
`P, Q`, it can run its entire search using its *own* field arithmetic, never
calling the meter, then submit `k` with a counter reading of (almost) zero. Any
design that exposes the representation cannot honestly count group operations.

`DESIGN DECISION.` Therefore the solver is given **only opaque, per-run-random
tokens** for group elements, plus a counted `add`/`neg`/`scalar_mul` oracle. It
never receives the representation. The encoding is a **stateless keyed permutation**
— an 8-round Feistel cipher over the 128-bit point block, keyed fresh per run —
so it is an injective random labelling computed in O(1) memory at any tier (no
growing point→token table). This is exactly **Shoup's generic group model** (GGM):
group elements are random labels; the only operation is the group law via an
oracle. The score is the number of oracle group operations.

`RESTRICTED THEOREM (Shoup 1997, instantiated).` In this model, any algorithm that
outputs `k` with constant success probability makes `Ω(√n)` group-operation
queries. Pollard rho achieves `√(πn/2)(1+o(1))`. Hence in this arena the *expected*
score is floored at `Θ(√n)` and the open quantity is the *constant*. (Single runs
fluctuate around the mean and can fall below the floor; the bound is on
probability, so the harness scores the **mean over trials**.)

`REFINEMENT (free negation).` The oracle makes `neg` free, because `−P = (x,−y)`
is the one involution an elliptic-curve representation hands you for nothing —
and counting it would cancel the standard √2 negation-map speedup. With a free
involution you search the `n/2` classes `{±P}`, so the expected floor drops to
`√(n/2) ≈ 0.707·√n` and negation-map rho reaches `√(πn/4) ≈ 0.886·√n`. The shipped
solver demonstrates this: it beats the plain-DP baseline by the textbook √2. This
is still `Θ(√n)`; the constant just improves by a fixed factor.

`Assumptions / model boundary.` The bound is about *generic* (representation-blind)
algorithms. It says nothing about algorithms that exploit the actual `F_p`
representation. By hiding the representation we *force* generic play, which is the
price of an unforgeable op-count. Non-generic attacks are out of scope for the
*scored* arena (see §4).

## 3. Threat model for the meter

The adversary is the contestant's `src/solver/mod.rs`, an arbitrary program.
Defenses:

| Attack | Defense |
|---|---|
| Do group ops with own arithmetic, report count≈0 | Solver never gets `(p,a,b)` or coordinates; only opaque tokens. |
| Forge a token for a chosen point to skip ops | Token = keyed Feistel permutation of the point (per-run key); a forged token decrypts to an off-curve point, treated as identity — no advantage. |
| Tamper with the counter / `score.json` | Counter is in a *separate trusted process*; sandbox denies the solver all writes. |
| Read `$ECDLP_SEED` and regenerate `k` | Child spawned with `env_clear()`; seed lives only in the oracle's memory. |
| Read `instance.public.json` off disk | Wiped before the run; sandbox denies reading it; written only post-run. |
| Hardcode `k` / the curve from the committed sample | Official run uses a **fresh secret seed**; the committed instance is a different, sample seed. |
| Exfiltrate / phone home | Sandbox denies network (`bwrap --unshare-net` / Seatbelt `(deny network*)`). |
| Pre-seed / replay a prior run's table | Token encoding randomized per run (Fiat–Shamir analogue). |

`HYPOTHESIS (residual).` The remaining trust assumption is the OS sandbox
(`sandbox-exec` on macOS, `bubblewrap` on Linux) plus process isolation. A kernel
sandbox escape, or a side channel reading the oracle process's memory, would
break the meter. This matches any sandboxed-submission benchmark's reliance on
the sandbox. `Next
action:` for a hardened deployment, run oracle and solver in separate containers
/ VMs rather than parent–child processes on one host.

## 4. What the score means

- `score = group_ops`, **averaged over several trials**, is an honest,
  hardware-independent measure of generic-group query efficiency for this ECDLP
  instance. Averaging matters: rho's collision time has heavy variance, so a single
  run can land anywhere from ~0.5× to ~2× its mean — including *below* `√n`. That
  does **not** contradict Shoup, whose `Ω(√n)` is a bound on success probability /
  expectation, not a per-run minimum. The mean is the leaderboard quantity.
- `1.00×` denotes the basic rho optimum `√(πn/2)`. Plain distinguished-point rho
  lands ≈`1.2–1.4×` (DP slack + setup); the negation map pulls that down by √2 to
  ≈`0.80×`, toward the `0.71×` negation optimum. The `√(n/2)` floor (≈`0.56×`)
  binds the expectation, not any individual trial.
- `OPEN.` The best achievable constant in this executable model (with the negation
  map, optimal walks, distinguished points, Gaudry–Schost) is a clean, finite
  question this benchmark measures directly.
- `OPEN (representation track).` Whether *any* method recovers `k` from the
  published `(p,a,b,G,Q)` faster than `√n` — i.e. a genuine non-generic attack on
  a generic prime-field curve — is the real frontier. Such a result would be
  verified trivially (`k·P=Q`) but is **not** an oracle-arena submission, because
  it is not a generic-group computation. Per the lab constitution: the generic
  floor here is *not* evidence that no such attack exists.

## 4½. Fair, reproducible scoring (common random numbers)

`PROBLEM.` rho's cost is a **random variable** with heavy variance (CV ≈ 33% per
trial; a single run swings ~0.5×–2× the mean). If each run drew *fresh* randomness,
the same solver would score differently every time, and a contestant could simply
**re-roll** — run repeatedly, or shrink the trial count — and submit the luckiest
draw. That measures luck, not the algorithm: not fair, not consistent.

`DESIGN DECISION (common random numbers).` We do not resample rho's randomness; we
**pin** it into a fixed trial battery, so the score is a deterministic function of
the solver:

- **Deterministic encodings.** The per-trial token encodings are a deterministic
  function of the instance seed (`token_seed_t = SplitMix64(ECDLP_SEED) ⊕ t·φ`), not
  wall-clock. So the same solver scores **identically on every run** — verified
  bit-for-bit. (Solvers must likewise be deterministic — seed any internal PRNG from
  the public instance data, as the shipped one does; it reads `c.n`.)
- **Fixed trial count.** `ECDLP_TRIALS` is a *fixed* battery size, not a knob to
  shrink for a lucky small-sample mean. The score is the mean over the whole battery.
- **Recorded for audit.** Every `score.json` and `results.tsv` row records its
  `instance_seed`, `token_seed`, and `trials`, so any number is reproducible by
  re-running — the leaderboard is checkable, not self-reported on faith.

`OFFICIAL GRADING.` One per-round **secret** `(ECDLP_SEED, ECDLP_TOKEN_SEED)` and a
large fixed `ECDLP_TRIALS` are applied to **every** submission, then revealed after
grading. Because all solvers face the *identical* battery, the comparison is a
**paired / common-random-numbers** comparison: the instance-luck cancels, so the
*difference* between two solvers has far lower variance than two independent runs —
a genuinely better algorithm wins reliably even at moderate `N`. Secrecy preserves
the anti-precompute property (§2–3); reveal-after-grading preserves reproducibility.

`CONSEQUENCE.` "Faster on some runs" cannot happen: a solver's score is fixed.
The remaining variance is only *across grading rounds* (different secret seeds),
which moves the absolute number a little but not the ranking — and a large `N`
keeps even the absolute number close to the true expected `√(πn/4)`.

## 5. Why generic curves, and why "generic" is enforced

`HEURISTIC.` For a curve with no special structure (prime order, non-anomalous,
large embedding degree, `j ∉ {0,1728}`), no attack better than generic is known,
so the GGM is believed to faithfully model its real difficulty. Hiding the
representation then loses nothing *known*. The generator enforces these
properties exactly (Hasse-interval BSGS point counting, deterministic
Miller–Rabin, MOV/anomalous/automorphism guards) and Sage re-verifies them, so a
low score can never come from an accidentally weak instance — only from a better
generic algorithm.
