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
- **Can anything beat `√n` here?** Not in *expectation*: the arena is the generic
  group model made executable, and Shoup's bound forbids any generic algorithm
  from succeeding with good probability in `o(√n)` queries. (A *single* run can
  land below `√n` by luck — rho's collision time has heavy variance — which is
  exactly why the official score is the **mean over several trials**.) Beating the
  expected `√n` would require leaving the generic model, which needs the
  *representation* — see [Scope & honesty](#scope--honesty-read-this) and the
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
c.neg(a)           -> token of (-a)         [ +1 group op ]
c.scalar_mul(a, m) -> token of (m·a)        [ +#doublings+#additions for m ]
c.is_identity(a)   -> bool                  [ free ]
a == b             point equality (token compare)   [ free ]
c.n, c.bits, c.tok_p, c.tok_q, c.tok_o      public instance data
```

`add_batch` is the wire protocol's batched op: it steps many independent walks in
a single round trip, so even high tiers run fast while every op is still counted.

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

### Reference numbers (sample instance, `bits = 40`, mean of 5 trials)

| | Group ops | ÷ rho optimum | Notes |
|---|---:|---:|---|
| Shoup generic-group floor | `√n` ≈ 785,418 | 0.80× | bound on the *expected* count / success prob |
| **Pollard-rho optimum** | `√(πn/2)` ≈ 984,377 | **1.00×** | the target |
| Shipped baseline (parallel-DP rho, this file) | ≈ 1.22 M | ≈ 1.2–1.5× | measured 5-trial mean (see `results.tsv`) |
| BSGS | ≈ `2√n` ≈ 1.57 M | 1.60× | but needs `√n` memory |

Scores are **means over trials**: a single rho run scatters widely (this
baseline's individual trials ranged 0.76×–1.7×). The shipped baseline is already a
near-optimal parallel distinguished-point rho, so pushing the mean lower takes
real work — the negation map (≈√2), θ/W tuning, a better walk (Teske),
Gaudry–Schost. The `√n` row is a floor on the *expected* score, **not** a hard
per-run minimum: an individual trial can dip below it by luck without contradicting
Shoup, whose bound is on success probability.

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
lower wins. The shipped baseline is a parallel distinguished-point rho; ideas to
push it down, roughly in increasing effort: the negation map (≈√2 speedup);
tuning `W` / the distinguished-point rate θ; a better r-adding walk (Teske);
Gaudry–Schost. All are constant-factor improvements converging toward the
`1.2533·√n` rho optimum.

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
  below ~`√n` (Shoup); the only game is the constant factor. Individual runs vary
  (which is why we average), and a low score is never evidence about real curves.
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
| `src/solver/mod.rs` | **editable** | your algorithm (ships with parallel-DP rho) |
| `src/field.rs`, `src/curve.rs` | trusted | `F_p` and the real curve group |
| `src/instance.rs` | trusted | deterministic verified-generic instance generation |
| `src/oracle.rs`, `src/bin/oracle.rs` | trusted | the meter (Feistel-encoded GGM), verifier, scoring, trials |
| `src/client.rs`, `src/bin/solver.rs` | trusted | binary protocol glue around your solver |
| `benchmark.sh` / `setup.sh` | trusted | sandbox + run + score |
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
