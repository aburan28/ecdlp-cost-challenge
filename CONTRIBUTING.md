# Contributing — submitting a solver

This repo doubles as a self-hosted submission platform: you submit a better solver
as a **pull request**, and CI validates it.

## The rule that matters

> A submission may modify **only `src/solver/`**.

Everything else — the oracle/meter (`src/oracle.rs`), the verifier and scorer
(`src/bin/oracle.rs`), the instance generator, `benchmark.sh`, `score.json` — is
the *trusted harness*. The whole point of the challenge is that the meter counts
your group operations and you cannot under-report them, so the meter must stay
immutable. CI's **editable-paths guard** rejects any PR that touches files outside
`src/solver/`. (Maintainers making genuine harness changes apply the `harness`
label to bypass it.)

## How to submit

1. Fork the repo and create a branch.
2. Edit **only** `src/solver/mod.rs` (see the header in that file for the API you
   may call: `add` / `add_batch` / `neg` / `neg_batch` / `scalar_mul` /
   `is_identity`, plus the public instance data).
3. Build and run locally:

   ```bash
   ./setup.sh
   ./benchmark.sh --note "what I tried"     # 5-trial mean at bits=40
   cat score.json                            # your score (lower is better)
   ```

   For fast iteration: `ECDLP_TRIALS=1 ECDLP_BITS=28 ./benchmark.sh`.
4. Commit **only** your `src/solver/` changes. `./benchmark.sh` overwrites
   `score.json` and appends a row to `results.tsv`, but those are harness
   **outputs** — do **not** commit them (`git checkout -- score.json results.tsv`
   to drop them). The guard rejects any PR that touches them, and CI re-derives
   the score from the trusted harness regardless.
5. Open a PR. Describe the approach in the PR body (what idea, expected speedup,
   any caveats).

## How it's scored

- **Score = mean counted group operations** the oracle charged your solver to
  recover `k` (with `Q = k·P`), averaged over several trials. **Lower is better.**
- CI **re-derives the score from the trusted harness** and ignores any `score.json`
  you committed — you cannot pre-seed it.
- A run is only valid if the harness confirms `k·P == Q` (`"correct": true`).
- Single runs have heavy variance (rho); the trial **mean** is the ranking
  quantity. See `README.md` for the reference numbers (rho optimum, the `√(n/2)`
  floor with free negation, etc.).

## What CI runs (`.github/workflows/validate.yml`)

| Check | Blocks merge | What it proves |
|---|---|---|
| `build` | yes | the harness + your solver compile |
| editable-paths guard | yes | the PR changed **only** `src/solver/` |
| correctness (sandboxed, `bits=28`) | yes | your solver returns a valid `k` |

The correctness job runs your solver **inside the sandbox** (`bubblewrap`), with a
cleared environment and a hard timeout, and only after the guard has confirmed no
trusted file was touched. The official, larger-tier scoring is run separately by
maintainers (a fixed secret seed can't live in a fork-readable workflow).

## For maintainers (integrity)

For `pull_request`, GitHub runs the workflow **as defined in the PR**, so the
checks are only truly enforced by **branch protection on `main`**:

- Require status checks: **`build`**, **`editable-paths guard`**, **`correctness
  (sandboxed harness)`**. A PR that deletes/renames a job then leaves a required
  check missing → merge blocked. (This — not the workflow file — is what stops a
  PR from disabling its own guard.)
- Require review from Code Owners (see `.github/CODEOWNERS`): all paths except
  `src/solver/` need maintainer review.
- A genuine harness/infra PR (touching files outside `src/solver/`) gets the
  **`harness`** label to pass the guard; adding the label re-runs the guard.

## Tips to beat the shipped solver

The shipped solver is a negation-map distinguished-point rho (~0.8× rho). To go
lower: tune `W` and the distinguished-point rate θ toward the 0.71× negation
optimum, improve the r-adding walk (Teske), or try Gaudry–Schost. Going below the
`√(n/2)` floor *in expectation* is impossible in this (generic-group) arena — that
would require the representation, which is the separate
[First-Blood track](first_blood/README.md).
