# The Generic Prime-Field ECDLP Cost Challenge

> **Goal.** Recover the discrete logarithm `k` (with `Q = k·P`) on a **generic
> prime-field elliptic curve**, using as few **group operations** as possible.
> You play inside an *executable generic-group oracle*: every elliptic-curve
> addition is one counted query. Score = group operations to recover `k`.
> **Lower is better.**

---

## Why this matters

Pollard's rho is the best known general-purpose attack on the discrete-log
problem in a prime-order elliptic-curve group. It costs about

$$\sqrt{\tfrac{\pi n}{2}}\;\approx\;1.2533\,\sqrt{n}$$

group operations, where `n` is the group order. Shoup's generic-group lower
bound says **no** algorithm that treats the group as a black box can do
asymptotically better than `√n`. Every deployed prime-field curve (P-256,
secp256k1, …) is chosen so that *no faster, non-generic attack is known* — the
whole security argument is "the only thing that works is generic, and generic
costs `√n`."

This challenge turns that argument into a measurable game. It asks, precisely:

- **How close to the rho optimum can a real implementation get?** (constant-factor
  arena: the negation map, distinguished points, Gaudry–Schost, BSGS trade-offs).
- **How low can the expected score go?** The arena is the generic group model made
  executable. With negation free you search the `n/2` classes `{±P}`, so the floor
  on the *expected* score is `√(n/2)` (Shoup); the negation-map walk gets within a
  small constant of it. A *single* run can land below the floor by luck — rho's
  collision time has heavy variance — which is why the official score is the
  **mean over several trials**. Going below `√(n/2)` *in expectation* would require
  leaving the generic model, which needs the *representation* — see
  [Scope & honesty](#scope--honesty-read-this) and the
  [First-Blood board](first_blood/README.md).

It follows the **resource-cost benchmark** pattern: a fixed, precisely specified
cryptographic task, scored by a resource the harness counts for you, with no
loopholes.

---

## The benchmark, precisely

You are given a Rust harness with two halves separated by a process boundary:

- **The oracle** (trusted, `src/oracle.rs`, `src/bin/oracle.rs`) holds a real
  curve `E: y² = x³ + a·x + b` over `F_p` with **prime** order `n`, a generator
  `P`, a secret scalar `k`, and the target `Q = k·P`. It exposes the group as
  Shoup's oracle: opaque, per-run-random 128-bit **tokens** for `P`, `Q`, `O`,
  and a counted `add` / `neg` / `scalar_mul` interface.
- **The solver** (untrusted, `src/solver/mod.rs` — *the only file you edit*) runs
  as a sandboxed child with a cleared environment. It talks to the oracle over a
  pipe. It only ever holds tokens, never coordinates.

```
c.add(a, b)        -> token of (a + b)      [ +1 group op ]
c.add_batch(&ps)   -> token per (a + b)     [ +1 op per pair; ONE round trip ]
c.neg(a)           -> token of (-a)         [ FREE  (-P = (x,-y)) ]
c.neg_batch(&ts)   -> token per (-t)        [ FREE; ONE round trip ]
c.scalar_mul(a, m) -> token of (m·a)        [ +#doublings+#additions for m ]
c.is_identity(a)   -> bool                  [ free ]
a == b             point equality (token compare)   [ free ]
c.n, c.bits, c.tok_p, c.tok_q, c.tok_o      public instance data
```

`add_batch` is the wire protocol's batched op: it steps many independent walks in
a single round trip, so even high tiers run fast while every op is still counted.
**Negation is free** — on a curve −P = (x,−y), the one involution the
representation hands you — which is what makes the standard √2 negation-map
speedup legitimate (the shipped solver uses it).

Your `solve` returns the recovered `k`. The oracle checks `k·P == Q` and writes
the **score** — the value of its own operation counter — to `score.json`.

### What "valid" means — no loopholes

A run is rejected (`correct: false`, nonzero exit) unless the submitted `k`
satisfies `k·P = Q` on the real curve. And you cannot get a low score by cheating
the meter, because:

- **You cannot do a group operation off-meter.** The solver never receives
  `(p, a, b)` or any coordinates — only opaque tokens. Tokens are unguessable
  128-bit randoms, so you can only name group elements you reached through counted
  `add`/`neg`/`scalar_mul` queries. There is no way to "add two points yourself."
- **You cannot under-report the count.** The counter lives in the oracle process,
  which the sandboxed solver cannot read or write. The solver only delivers the
  final `k`; the oracle owns the number.
- **You cannot pre-seed or replay.** The token encoding is freshly randomized
  every run, so a table built in a previous run is meaningless this run. (This is
  the Fiat–Shamir trick: the per-run randomness is derived freshly, so a solver
  cannot precompute against it.)
- **You cannot read the answer off disk.** `benchmark.sh` wipes
  `instance.public.json` before the run, the solver's environment is cleared (no
  `$ECDLP_SEED`), and the sandbox denies network and all filesystem writes. The
  representation is published only *after* scoring.
- **Official runs use a fresh secret seed.** The instance committed in this repo
  is a *sample* for offline study. The scored instance's seed is chosen
  server-side and never revealed, so hardcoding `k` (or the curve) into your
  solver fails on the official run — exactly as a solver tuned to a public test
  set fails on the hidden one.

A "win" that comes from skipping group operations you actually performed, or from
reading the secret, doesn't make the run faster — it makes it invalid.

### Reference numbers (sample instance, `bits = 40`, free negation)

| | Group ops | ÷ rho optimum | Notes |
|---|---:|---:|---|
| Generic floor (free negation) | `√(n/2)` ≈ 555,375 | 0.56× | bound on the *expected* count / success prob |
| negation-map rho optimum | `√(πn/4)` ≈ 696,073 | 0.71× | best the √2 walk can do |
| **Shipped solver (negation-map DP rho)** | ≈ **788 k** | ≈ **0.80×** | measured 8-trial mean (`results.tsv`) |
| **Pollard-rho optimum (no neg map)** | `√(πn/2)` ≈ 984,377 | **1.00×** | the reference |
| plain parallel-DP rho (`solutions/`) | ≈ 1.24 M | ≈ 1.2–1.4× | the negation map's √2 baseline |
| BSGS | ≈ `2√n` ≈ 1.57 M | 1.60× | but needs `√n` memory |

Scores are **means over trials**: a single rho run scatters widely (±~50%). The
shipped solver is a negation-map parallel distinguished-point rho — it beats the
plain-DP baseline by the textbook **√2** (head-to-head 8-trial means: 1.26× vs
0.90×). Pushing lower still takes real work: θ/W tuning toward the 0.71× negation
optimum, a better r-adding walk (Teske), or Gaudry–Schost. The floor row binds the
*expected* score, **not** any individual trial — a single run can dip below it by
luck without contradicting Shoup (whose bound is on success probability).

---

## How to play

Locally, with the harness directly:

```bash
./setup.sh                       # build oracle, solver, gen_instance
./benchmark.sh --note "tried X"  # build, sandbox, run (5-trial mean), score
cat score.json                   # your score; one row also appended to results.tsv
```

Pick a tier (bit-length of `p ≈ n`):

```bash
ECDLP_BITS=28 ./benchmark.sh --note "warmup"     # ~instant
ECDLP_BITS=40 ./benchmark.sh --note "official"   # default; a few seconds
ECDLP_BITS=48 ./benchmark.sh --note "stretch"    # ~1–2 min (binary+batched protocol)
ECDLP_TRIALS=1 ECDLP_BITS=40 ./benchmark.sh      # single trial, for fast iteration
```

Edit **only** `src/solver/mod.rs`. Then re-run. The score is the mean `group_ops`;
lower wins. The shipped solver is already a **negation-map** parallel
distinguished-point rho (≈0.80×; it uses the free `neg`/`neg_batch` to walk the
n/2 classes {±P}). The previous plain-DP rho is preserved at
`solutions/baseline_parallel_dp.rs` to show the √2 gap. To push lower still: tune
`W` and the distinguished-point rate θ toward the 0.71× negation optimum, improve
the r-adding walk (Teske), or try Gaudry–Schost — all constant-factor moves above
the `√(n/2)` floor.

Inspect the (sample) instance you're attacking, or attempt the open
[First-Blood board](first_blood/README.md):

```bash
./target/release/gen_instance 0x12345678 40          # print public params (no k)
sage tools/verify_instance.sage instance.public.json # independent Sage check
python3 first_blood/verify_first_blood.py first_blood/instance_public_96.json <k>
```

---

## Scope & honesty (read this)

This is a research instrument, not a claim that ECDLP is broken.

- **This is the generic group model, executed.** Hiding the representation is
  what makes the op-count unforgeable — but it also means the scored arena
  *cannot host non-generic attacks*. Inside it, the *expected* score cannot go
  below ~`√(n/2)` (Shoup, with negation free); the only game is the constant
  factor. Individual runs vary (which is why we average), and a low score is never
  evidence about real curves.
- **Generic bounds do not rule out non-generic algorithms.** A real
  representation-level structure (a cheap decomposition, a useful factor base, an
  index-calculus path) would live *outside* this oracle. To invite exactly that,
  the full curve `(p, a, b, G, Q)` is published in `instance.public.json` after
  each run, and the [First-Blood board](first_blood/README.md) posts larger
  verified-generic instances whose `k` nobody knows. Finding `k` from the
  representation alone — by any method — is the **representation track**; it is
  verified the same trivial way (`k·G = Q`) but is **not** scored on the oracle
  counter (it isn't a generic-group computation).
- **"Generic" is enforced, not assumed.** Every instance has prime order, `n ≠ p`
  (non-anomalous), large MOV embedding degree, and `j ∉ {0, 1728}`. The Rust
  generator computes the order exactly (BSGS in the Hasse interval) and Sage
  re-checks it (`tools/verify_instance.sage`). So a "win" can never come from an
  accidentally weak curve.
- **Sizes are toy by design.** The scored tiers are small enough to actually
  solve (`bits ≤ ~48`). This is a benchmark of *algorithmic group-operation
  efficiency*, not a break of any deployed parameter set. Nothing here recovers a
  real key.

See [`DESIGN.md`](DESIGN.md) for the threat model and the argument for *why* an
unforgeable group-operation score forces this oracle design.

---

## Files

| Path | Trust | Role |
|---|---|---|
| `src/solver/mod.rs` | **editable** | your algorithm (ships with negation-map DP rho) |
| `src/field.rs`, `src/curve.rs` | trusted | `F_p` and the real curve group |
| `src/instance.rs` | trusted | deterministic verified-generic instance generation |
| `src/oracle.rs`, `src/bin/oracle.rs` | trusted | the meter (Feistel-encoded GGM, free neg), verifier, scoring, trials |
| `src/client.rs`, `src/bin/solver.rs` | trusted | binary protocol glue (add/add_batch/neg/neg_batch/scalar_mul) |
| `benchmark.sh` / `setup.sh` | trusted | sandbox + run + score |
| `solutions/` | reference | prior solvers (plain parallel-DP rho) — the √2 baseline |
| `tools/verify_instance.sage` | tool | independent Sage check of an instance |
| `tools/gen_instances.sage` | tool | larger verified-generic instances |
| `first_blood/` | track | open representation-attack board + pure-Python verifier |

### Knobs

| Env var | Default | Meaning |
|---|---|---|
| `ECDLP_BITS` | 40 | bit-length of `p ≈ n` (the tier) |
| `ECDLP_TRIALS` | 5 in `benchmark.sh`, else 1 | trials averaged into the score |
| `ECDLP_SEED` | sample seed | instance seed; official runs set a fresh secret one |
| `ECDLP_TOKEN_SEED` | random | pin only for reproducible tests |
