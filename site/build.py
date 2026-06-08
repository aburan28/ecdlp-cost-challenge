#!/usr/bin/env python3
"""Render the First-Blood board from the challenge manifest + contestant solves.

The board is DERIVED, so it can't drift and contestants can solve via a PR that
touches only `submissions/` (which the editable-paths guard already allows):

  * first_blood/status.json       — the board MANIFEST: which instances exist
                                     (file + bits), in display order, + repo/branch.
  * submissions/**/solution.json  — a contestant's solve: the instance it targets,
                                     the recovered `k`, solver handle, method, date.
                                     The sibling WRITEUP.md is linked automatically.

`build.py` joins them and regenerates, in place, the marked regions of:

  * site/index.html           — the `<!-- BUILD:firstblood -->` board rows
  * first_blood/README.md      — the `<!-- BUILD:firstblood-table -->` table

It is pure-stdlib (no dependencies) and idempotent: running it twice is a no-op.

PROOF GATE: in every mode it re-verifies every submission — the `k` must recover
the log (k·G == Q) on its instance, using the same math as verify_first_blood.py.
A submission with a missing/wrong k, or one pointing at an unknown instance, is
REJECTED (exit 2), so it can neither render locally nor deploy in CI. An instance
shows SOLVED only when a real, re-checkable break exists for it.

Usage:
    python3 site/build.py            # verify solves, then rewrite the derived files
    python3 site/build.py --check    # verify solves; exit 1 if files are out of date (CI/pre-commit)
    python3 site/build.py --verify   # verify solves only (no render); exit 2 on a bad/unknown submission

This is why the board updates when a challenge is solved: a contestant adds a
submissions/<dir>/solution.json (CI validates it), it lands on main, and the Pages
deploy runs build.py — the board promotes that instance to SOLVED automatically.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FB = ROOT / "first_blood"
STATUS = FB / "status.json"
SUBMISSIONS = ROOT / "submissions"
INDEX = ROOT / "site" / "index.html"
FB_README = FB / "README.md"


def load_manifest():
    data = json.loads(STATUS.read_text())
    return data["instances"], data.get("repo", ""), data.get("branch", "main")


def load_submissions():
    """Every submissions/**/solution.json is a claimed first-blood solve."""
    subs = []
    if SUBMISSIONS.is_dir():
        for p in sorted(SUBMISSIONS.glob("**/solution.json")):
            rec = {"_path": p, "_dir": p.parent}
            try:
                rec.update(json.loads(p.read_text()))
            except json.JSONDecodeError as e:
                rec["_error"] = f"invalid JSON ({e})"
            subs.append(rec)
    return subs


def blob_url(repo, branch, path):
    return f"https://github.com/{repo}/blob/{branch}/{path}"


def _load_ec_verifier():
    """Reuse the standalone, auditable EC math in first_blood/verify_first_blood.py."""
    import importlib.util

    p = FB / "verify_first_blood.py"
    spec = importlib.util.spec_from_file_location("verify_first_blood", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # only defines functions; main() is __main__-guarded
    return mod


def verify_submissions(submissions, known_instances):
    """Return (verified, problems). A submission is verified ONLY if its decimal `k`
    recovers the log (k·G == Q) on a known instance — the same one-scalar-mult check
    verify_first_blood.py exposes. This makes SOLVED a re-checkable proof, not a claim."""
    problems, verified = [], []
    vfb = None
    for s in submissions:
        tag = str(s["_path"].relative_to(ROOT))
        if "_error" in s:
            problems.append(f"{tag}: {s['_error']}")
            continue
        inst = s.get("instance")
        if inst not in known_instances:
            problems.append(f"{tag}: unknown instance {inst!r} (not in the status.json manifest)")
            continue
        k = s.get("k")
        if k in (None, ""):
            problems.append(f'{tag}: no "k"')
            continue
        try:
            kk = int(str(k), 0)
        except ValueError:
            problems.append(f"{tag}: k is not an integer ({k!r})")
            continue
        try:
            d = json.loads((FB / inst).read_text())
        except FileNotFoundError:
            problems.append(f"{tag}: instance file {inst} not found")
            continue
        if vfb is None:
            vfb = _load_ec_verifier()
        p, a, n = d["p"], d["a"], d["n"]
        G, Q = (d["Gx"], d["Gy"]), (d["Qx"], d["Qy"])
        if vfb.scalar_mul(kk % n, G, a, p) != Q:
            problems.append(f"{tag}: k·G != Q — claimed solve does NOT verify")
            continue
        verified.append(s)
    return verified, problems


def first_solver_by_instance(verified):
    """instance filename -> the first-blood solve (earliest date, then path as tiebreak)."""
    by = {}
    for s in sorted(verified, key=lambda s: (str(s.get("date") or "9999-12-31"), str(s["_path"]))):
        by.setdefault(s["instance"], s)
    return by


def writeup_path(sub):
    """Repo-relative path to the submission's writeup (WRITEUP.md if present, else its dir)."""
    wu = sub["_dir"] / "WRITEUP.md"
    target = wu if wu.exists() else sub["_dir"]
    return str(target.relative_to(ROOT))


# ---- renderers -------------------------------------------------------------

def render_site_rows(instances, solved_by, repo, branch):
    lines = []
    for it in instances:
        f = html.escape(it["file"])
        bits = it["bits"]
        sub = solved_by.get(it["file"])
        if sub:
            who = f"<b>{html.escape(sub.get('solver', '—'))}</b>"
            if sub.get("method"):
                who += f" — {html.escape(sub['method'])}"
            url = blob_url(repo, branch, writeup_path(sub))
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


def render_readme_table(instances, solved_by):
    # pad columns so the raw markdown stays nicely aligned (cosmetic only)
    files = [f"`{it['file']}`" for it in instances]
    bitstrs = [f"{it['bits']}-bit" for it in instances]
    fw = max(len(s) for s in files)
    bw = max(len(s) for s in bitstrs)
    rows = ["| File | Field size | Status | First solver |", "|---|---:|---|---|"]
    for it, fcell, bcell in zip(instances, files, bitstrs):
        sub = solved_by.get(it["file"])
        if sub:
            status = "🔴 SOLVED"
            who = f"**{sub.get('solver', '—')}**"
            if sub.get("method"):
                who += f" — {sub['method']}"
            rel = "../" + writeup_path(sub)  # README lives in first_blood/
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

    instances, repo, branch = load_manifest()
    known = {it["file"] for it in instances}
    submissions = load_submissions()

    # Proof gate (runs in EVERY mode): a solve cannot render locally or deploy in CI
    # unless its k actually recovers the discrete log. This is the security boundary —
    # SOLVED on the board is therefore always a re-verifiable break.
    verified, problems = verify_submissions(submissions, known)
    if problems:
        print("REJECTED — first-blood submission check failed:")
        for p in problems:
            print(f"  ✗ {p}")
        print('Each submissions/<dir>/solution.json needs a "k" with k·G == Q on a '
              "known instance (audit with first_blood/verify_first_blood.py).")
        return 2

    solved_by = first_solver_by_instance(verified)
    solved, total = len(solved_by), len(instances)
    if verify_only:
        print(f"verified · {len(verified)} submission(s) ok, {solved}/{total} instances solved (k·G == Q)")
        return 0

    jobs = [
        (INDEX, "firstblood", render_site_rows(instances, solved_by, repo, branch)),
        # blank lines around the table so GFM parses it as a table (an HTML
        # comment is an HTML block that a table must be separated from).
        (FB_README, "firstblood-table", "\n" + render_readme_table(instances, solved_by) + "\n"),
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
