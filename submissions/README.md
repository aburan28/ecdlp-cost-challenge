# Submissions

Three kinds of contribution land here, each validated by CI or a local checker.

## First-Blood solves (recover `k` for a published curve)

Solve any **open** instance on the [First-Blood board](../first_blood/README.md)
and submit it as a commit — no maintainer hand-off, CI checks your proof:

1. Recover `k` for an open `first_blood/instance_public_<bits>.json` by any method.
2. Add a directory `submissions/first-blood-<bits>/` (use a unique suffix if it
   already exists, e.g. `first-blood-96-yourhandle/`) containing:

   **`solution.json`**
   ```json
   {
     "instance": "instance_public_96.json",
     "solver": "your-github-handle",
     "method": "short method, e.g. 'generic VW parallel rho, 64 cores, 9 days'",
     "k": "the recovered k as a decimal string",
     "date": "2026-06-09"
   }
   ```

   **`WRITEUP.md`** — how you did it. Per the lab constitution, **say which**:
   the honest `√n` generic work, or a non-generic shortcut (the real prize). Label
   the claim (`OBSERVATION` / `HEURISTIC` / `THEOREM`).
3. Open a PR. The **`first-blood submissions`** CI job re-derives `k·G == Q` on
   the published curve and **fails if it doesn't check out** — so a bogus or
   missing `k`, or an unknown instance, is rejected automatically. Verify locally
   first:
   ```bash
   python3 first_blood/verify_first_blood.py first_blood/instance_public_96.json <k>
   ```
4. On merge, the Pages deploy runs `site/build.py`, which promotes your instance
   to **SOLVED** on the board and the README — crediting you as first solver
   (earliest `date` wins if two valid solves race the same instance).

A first-blood PR touches **only `submissions/`**, which the editable-paths guard
allows, so it needs no maintainer label — just a passing check and a merge.

## Scored-solver submissions (beat rho)

A better generic solver is a different track: edit **only `src/solver/mod.rs`** and
open a PR; CI re-derives the score in a sandbox. See
[`CONTRIBUTING.md`](../CONTRIBUTING.md). Notes/writeups for those may also live here.

## Research-track submissions (develop a mechanism)

Use this when the goal is not merely another rho constant-factor tweak, but a
mechanism-backed algorithmic claim.

Copy the template:

```bash
cp -R submissions/research-template submissions/research-<name>
```

Fill in:

```text
submissions/research-<name>/
  submission.toml   # declared track, capabilities, mechanism, validation plan
  CLAIM.md          # falsifiable mechanism claim and result class
  results.json      # measured costs, baseline, and correctness fields
  scaling.json      # optional but required for sub-sqrt claims
  WRITEUP.md        # detailed method and reproduction notes
```

Then run the structural checker:

```bash
python3 tools/classify_research_submission.py submissions/research-<name>
```

The checker separates these result classes:

| Class | Meaning |
|---|---|
| `rho_constant` | Rho-family constant-factor improvement. |
| `generic_collision` | Representation-blind collision search that is not necessarily the shipped rho implementation. |
| `representation_constant` | Uses curve representation, but scaling is still compatible with `alpha = 0.5`. |
| `representation_subsqrt_candidate` | Uses curve representation and has held-out-verified `alpha` upper 95% below `0.5`. |
| `failed_or_overfit` | Wrong result, failed held-out prediction, missing mechanism, or unsupported claim. |

The rule of thumb is: a solved instance is a point; a new algorithm is a predictive
cost law plus a mechanism.
