# ECDLP.fail — landing site

A self-contained `index.html` (no framework, no dependencies) for the ECDLP cost
challenge. Dark, monospace-accented, in the spirit of `ecdsa.fail`. The only
"build" is one tiny stdlib-Python step ([`build.py`](build.py)) that renders the
live First-Blood board — no toolchain required.

Sections: hero → How it works (Shoup oracle) → Will you beat rho? (reference
leaderboard) → Score history (trajectory chart) → Participate → First-Blood
board → Scope & honesty.

## Updating the First-Blood board (auto)

The First-Blood board is **data-driven** so the site can never go stale when a
challenge is solved. The single source of truth is
[`../first_blood/status.json`](../first_blood/status.json); `build.py` renders it
into both the board in `index.html` and the table in `first_blood/README.md`.

To record a solve: flip the instance to `"solved"` in `status.json`
(fill `solver` / `method` / `writeup`), then

```bash
python3 site/build.py            # regenerate the board + README table
python3 site/build.py --check    # CI/pre-commit: exit 1 if anything is stale
```

The Pages deploy ([`pages.yml`](../.github/workflows/pages.yml)) also runs
`build.py` and triggers on `first_blood/**`, so a push that solves an instance
redeploys the site with the board already updated. The content lives between
`<!-- BUILD:firstblood -->` markers — don't hand-edit inside them.

The scored "Beat rho" leaderboard numbers (`rho_ref = 984,377`; record
**708,536 (0.72×)**, optimum 696,061 (0.71×), Shoup floor 555,375 (0.56×)) are
still curated by hand in `index.html`. **Note:** the 708,536 record is not yet
backed by a row in `results.tsv` (which currently bottoms out at 788,034 /
0.80×) — see the repo summary for how to make the arena board data-driven too.

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
