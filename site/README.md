# ECDLP.fail — landing site

A single, self-contained `index.html` (no build step, no dependencies) for the
ECDLP cost challenge. Dark, monospace-accented, in the spirit of `ecdsa.fail`.

Sections: hero → How it works (Shoup oracle) → Will you beat rho? (reference
leaderboard) → Score history (trajectory chart) → Participate → First-Blood
board → Scope & honesty.

All numbers are the verified bits=40 figures (`rho_ref = 984,377`): current
record **708,536 (0.72×)**, negation-map optimum 696,061 (0.71×), Shoup floor
555,375 (0.56×). Update them in `index.html` as the leaderboard moves.

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
