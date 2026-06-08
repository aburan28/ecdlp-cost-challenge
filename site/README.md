# ECDLP.fail — landing site

A self-contained `index.html` (no framework, no dependencies) for the ECDLP cost
challenge. Dark, monospace-accented, in the spirit of `ecdsa.fail`. The only
"build" is one tiny stdlib-Python step ([`build.py`](build.py)) that renders the
live First-Blood board — no toolchain required.

Sections: hero → How it works (Shoup oracle) → Will you beat rho? (reference
leaderboard) → Score history (trajectory chart) → Participate → First-Blood
board → Scope & honesty.

## The First-Blood board (data-driven, contestant-solvable)

The board is **derived**, so it can't go stale and contestants solve via a PR.
`build.py` joins two inputs and renders both the board in `index.html` and the
table in `first_blood/README.md`:

- [`../first_blood/status.json`](../first_blood/status.json) — the **manifest**:
  which instances exist (`file` + `bits`), in order, plus `repo`/`branch`.
- `../submissions/**/solution.json` — a contestant's **verified solve** (the
  instance, the recovered `k`, handle, method). See
  [`../submissions/README.md`](../submissions/README.md).

`build.py` re-verifies every submission's `k` (`k·G == Q`) and **refuses to render
or deploy** a missing/wrong `k`, so SOLVED is always a real break:

```bash
python3 site/build.py            # verify solves, regenerate the board + README table
python3 site/build.py --check    # CI/pre-commit: exit 1 if files are stale
python3 site/build.py --verify   # verify solves only (the `first-blood submissions` CI job)
```

The Pages deploy ([`pages.yml`](../.github/workflows/pages.yml)) runs `build.py`
and triggers on `first_blood/**` and `submissions/**`, so when a contestant's solve
merges, the site redeploys with that instance already promoted to SOLVED. The
content lives between `<!-- BUILD:firstblood -->` markers — don't hand-edit inside.

## The scored "Beat rho" arena (also data-driven)

`build.py` renders the hero stats, the "Beat rho" leaderboard, the trajectory
chart, and the score-history table — all between `<!-- BUILD:arena-* -->` markers —
from two inputs:

- [`arena.json`](arena.json) — the tier group order `n`. The **reference rows**
  (Shoup floor √(n/2), the negation-map optimum √(πn/4), the rho optimum √(πn/2),
  and BSGS 2√n) are **computed exactly from `n`**, never hand-typed.
- [`../results.tsv`](../results.tsv) — the measured benchmark runs. The **record**,
  score history, and chart come straight from these rows; a new `./benchmark.sh`
  row updates them automatically (the deploy triggers on `results.tsv`).

So the headline reflects the best *committed* run. As of now that is **0.80×**
(788,034); the faster ~0.72× solver lives in an open PR and isn't in `results.tsv`
yet — merge it (its benchmark row promotes the record) or commit a `./benchmark.sh`
run, and the board, chart, and hero stat all move on their own.

## Preview locally

```bash
cd site && python3 -m http.server 8099   # then open http://localhost:8099
```

## Deploy

The site is plain static files — host anywhere. `CNAME` pins the custom domain
`ecdlp.fail`.

- **GitHub Pages (recommended).** A deploy workflow is included at
  [`.github/workflows/pages.yml`](../.github/workflows/pages.yml): it publishes
  `site/` on every push to `main` (and via *Run workflow*). One-time setup:
  **Settings → Pages → Source = "GitHub Actions"**. After it runs, set
  **Settings → Pages → Custom domain = `ecdlp.fail`** (the `CNAME` file already
  pins it) and enable *Enforce HTTPS*.
- **Netlify / Vercel / Cloudflare Pages.** Point the project at `site/` as the
  publish directory; no build command.

DNS: point `ecdlp.fail` at the host. For GitHub Pages, an apex domain uses the
four `A` records (`185.199.108–111.153`) — or a `CNAME`/`ALIAS` to
`<user>.github.io` for a subdomain. (You'll move this off the current Squarespace
parking page at the registrar.)
