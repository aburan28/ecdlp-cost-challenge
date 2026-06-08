#!/usr/bin/env python3
"""Render the First-Blood board from its single source of truth.

`first_blood/status.json` is canonical. This script regenerates, in place,
the marked regions of two derived files so they can never drift:

  * site/index.html          — the `<!-- BUILD:firstblood -->` board rows
  * first_blood/README.md     — the `<!-- BUILD:firstblood-table -->` table

It is pure-stdlib (no dependencies) and idempotent: running it twice is a no-op.

PROOF GATE: in every mode it first re-verifies each "solved" entry — the entry
must carry a decimal `k` that recovers the log (k·G == Q) on its instance, using
the same math as first_blood/verify_first_blood.py. A claimed solve with a
missing or wrong k is REJECTED (exit 2), so it can neither render locally nor
deploy in CI. The SOLVED badge is therefore always a real, re-checkable break.

Usage:
    python3 site/build.py            # verify proofs, then rewrite the derived files
    python3 site/build.py --check    # verify proofs; exit 1 if files are out of date (CI/pre-commit)
    python3 site/build.py --verify   # verify proofs only (no render); exit 2 on a bad/missing k

This is why the website updates when a challenge is solved: edit status.json,
run this (the Pages workflow also runs it on deploy), and the board reflects it.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "first_blood" / "status.json"
INDEX = ROOT / "site" / "index.html"
FB_README = ROOT / "first_blood" / "README.md"


def load_status():
    data = json.loads(STATUS.read_text())
    return data, data["instances"], data.get("repo", ""), data.get("branch", "main")


def blob_url(repo, branch, path):
    return f"https://github.com/{repo}/blob/{branch}/{path}"


# ---- proof gate: a "solved" entry must carry a verifiable k ----------------

def _load_ec_verifier():
    """Reuse the standalone, auditable EC math in first_blood/verify_first_blood.py."""
    import importlib.util

    p = ROOT / "first_blood" / "verify_first_blood.py"
    spec = importlib.util.spec_from_file_location("verify_first_blood", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # only defines functions; main() is __main__-guarded
    return mod


def verify_solved(instances):
    """Return a list of problems. A "solved" entry is valid ONLY if it ships a
    decimal `k` that recovers the log (k·G == Q) on its published instance — the
    same one-scalar-mult check `verify_first_blood.py` exposes. This is what makes
    the board's SOLVED badge a real, re-checkable proof rather than an assertion."""
    fb = ROOT / "first_blood"
    problems = []
    vfb = None
    for it in instances:
        if it.get("status") != "solved":
            continue
        tag = it.get("file", "?")
        k = it.get("k")
        if k in (None, ""):
            problems.append(f'{tag}: marked "solved" but has no "k"')
            continue
        try:
            k = int(str(k), 0)
        except ValueError:
            problems.append(f"{tag}: k is not an integer ({k!r})")
            continue
        try:
            d = json.loads((fb / it["file"]).read_text())
        except FileNotFoundError:
            problems.append(f"{tag}: instance file not found")
            continue
        if vfb is None:
            vfb = _load_ec_verifier()
        p, a, b, n = d["p"], d["a"], d["b"], d["n"]
        G, Q = (d["Gx"], d["Gy"]), (d["Qx"], d["Qy"])
        if vfb.scalar_mul(k % n, G, a, p) != Q:
            problems.append(f"{tag}: k·G != Q — claimed solve does NOT verify")
    return problems


# ---- site/index.html : the .fb-row board ----------------------------------

def render_site_rows(instances, repo, branch):
    lines = []
    for it in instances:
        f = html.escape(it["file"])
        bits = it["bits"]
        if it.get("status") == "solved":
            who = f"<b>{html.escape(it.get('solver', '—'))}</b>"
            if it.get("method"):
                who += f" — {html.escape(it['method'])}"
            if it.get("writeup"):
                url = blob_url(repo, branch, it["writeup"])
                who += f' · <a href="{html.escape(url)}" target="_blank" rel="noopener">writeup ↗</a>'
            lines.append(
                f'      <div class="fb-row"><div class="file">{f}</div>'
                f'<div class="mono">{bits}-bit</div>'
                f'<div class="solved">SOLVED</div>'
                f'<div class="who">{who}</div></div>'
            )
        else:
            lines.append(
                f'      <div class="fb-row"><div class="file">{f}</div>'
                f'<div class="mono">{bits}-bit</div>'
                f'<div class="open">OPEN</div>'
                f'<div class="who muted">—</div></div>'
            )
    return "\n".join(lines)


# ---- first_blood/README.md : the markdown table ---------------------------

def render_readme_table(instances, repo, branch):
    # pad columns so the raw markdown stays nicely aligned (cosmetic only)
    files = [f"`{it['file']}`" for it in instances]
    bitstrs = [f"{it['bits']}-bit" for it in instances]
    fw = max(len(s) for s in files)
    bw = max(len(s) for s in bitstrs)
    rows = ["| File | Field size | Status | First solver |", "|---|---:|---|---|"]
    for it, fcell, bcell in zip(instances, files, bitstrs):
        if it.get("status") == "solved":
            status = "🔴 SOLVED"
            who = f"**{it.get('solver', '—')}**"
            if it.get("method"):
                who += f" — {it['method']}"
            if it.get("writeup"):
                rel = "../" + it["writeup"]  # README lives in first_blood/
                who += f" ([writeup]({rel}))"
        else:
            status = "🟢 OPEN"
            who = "—"
        rows.append(f"| {fcell.ljust(fw)} | {bcell.ljust(bw)} | {status} | {who} |")
    return "\n".join(rows)


# ---- marker injection ------------------------------------------------------

def inject(path, marker, new_inner):
    """Replace text between `<!-- BUILD:marker ... -->` and `<!-- /BUILD:marker -->`."""
    text = path.read_text()
    pat = re.compile(
        r"(<!--\s*BUILD:" + re.escape(marker) + r"\b[^>]*-->)(.*?)(<!--\s*/BUILD:"
        + re.escape(marker) + r"\s*-->)",
        re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        raise SystemExit(
            f"!! marker BUILD:{marker} not found in {path.relative_to(ROOT)} — "
            "the file must contain the <!-- BUILD:{marker} --> / <!-- /BUILD:{marker} --> pair"
        )
    updated = text[: m.start(2)] + "\n" + new_inner + "\n" + text[m.end(2):]
    return text, updated


def main():
    args = sys.argv[1:]
    check = "--check" in args
    verify_only = "--verify" in args
    _, instances, repo, branch = load_status()

    # Proof gate (runs in EVERY mode): a solve cannot render locally or deploy in
    # CI unless its k actually recovers the discrete log. This is the security
    # boundary — "SOLVED" on the board is therefore always a re-verifiable break.
    problems = verify_solved(instances)
    if problems:
        print("REJECTED — first-blood proof check failed:")
        for p in problems:
            print(f"  ✗ {p}")
        print('A "solved" entry needs a "k" with k·G == Q '
              "(audit with first_blood/verify_first_blood.py).")
        return 2

    solved = sum(1 for it in instances if it.get("status") == "solved")
    total = len(instances)
    if verify_only:
        print(f"verified · {solved}/{total} solved, every proof checks out (k·G == Q)")
        return 0

    jobs = [
        (INDEX, "firstblood", render_site_rows(instances, repo, branch)),
        # blank lines around the table so GFM parses it as a table (an HTML
        # comment is an HTML block that a table must be separated from).
        (FB_README, "firstblood-table", "\n" + render_readme_table(instances, repo, branch) + "\n"),
    ]

    stale = []
    for path, marker, inner in jobs:
        before, after = inject(path, marker, inner)
        if before != after:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(after)

    if check:
        if stale:
            print("OUT OF DATE (run `python3 site/build.py`):")
            for p in stale:
                print(f"  - {p}")
            return 1
        print(f"up to date · first-blood {solved}/{total} solved")
        return 0

    if stale:
        print(f"updated {len(stale)} file(s) · first-blood {solved}/{total} solved:")
        for p in stale:
            print(f"  - {p}")
    else:
        print(f"already up to date · first-blood {solved}/{total} solved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
