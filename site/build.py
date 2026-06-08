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
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FB = ROOT / "first_blood"
STATUS = FB / "status.json"
SUBMISSIONS = ROOT / "submissions"
INDEX = ROOT / "site" / "index.html"
FB_README = FB / "README.md"
ARENA = ROOT / "site" / "arena.json"
RESULTS = ROOT / "results.tsv"


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


# ---- scored "Beat rho" arena (site/arena.json + results.tsv) ---------------

def arena_constants(n):
    """The reference rows are exact functions of the group order n."""
    return {
        "rho": round(math.sqrt(math.pi * n / 2)),       # √(πn/2)  Pollard-rho optimum
        "floor": round(math.sqrt(n / 2)),               # √(n/2)   Shoup expected floor
        "optimum": round(math.sqrt(math.pi * n / 4)),   # √(πn/4)  negation-map optimum
        "bsgs": round(2 * math.sqrt(n)),                # 2√n      baby-step giant-step
    }


def load_results(bits):
    """Measured runs from results.tsv for this tier (correct only), oldest first."""
    rows = []
    if RESULTS.exists():
        for line in RESULTS.read_text().splitlines():
            if not line or line.startswith("timestamp"):
                continue
            f = line.split("\t")
            if len(f) < 8:
                continue
            ts, commit, ops, b, _rho, ratio, correct, note = f[:8]
            if not b.isdigit() or int(b) != bits or correct.strip() != "OK":
                continue
            rows.append({"ts": int(ts), "ops": int(ops), "note": note.strip()})
    return rows


def _short(note):
    """A compact label for a measured run, derived from its results.tsv note."""
    s = re.sub(r"\s*\([^)]*\)", "", note)          # drop "(8-trial mean)" etc.
    s = re.split(r"\s+[—-]\s+", s)[0]               # keep text before " — " / " - "
    if ": " in s:
        s = s.split(": ", 1)[1]                     # drop a "baseline: " prefix
    s = s.strip()
    return (s[:26] + "…") if len(s) > 27 else s


def _fmt(x):
    return f"{x:,}"


def _ratiostr(r):
    return f"{r:.2f}×"


_ROLE = {  # role -> (ratio css class, bar colour)
    "floor": ("r-floor", "var(--cyan)"),
    "optimum": ("r-good", "var(--accent-dim)"),
    "rho": ("r-ref", "var(--muted)"),
    "bsgs": ("r-bad", "var(--fail)"),
    "measured": ("r-bad", "var(--fail)"),
    "record": ("", "var(--gold)"),
}


def _arena_rows(arena, measured, consts):
    """Unified, ops-sorted list of leaderboard rows (references + measured)."""
    rho = consts["rho"]
    rows = []
    for ref in arena["references"]:
        ops = consts[ref["formula"]]
        rows.append({"name": ref["name"], "sub": ref["sub"], "ops": ops,
                     "ratio": ops / rho, "role": ref["role"],
                     "rank": ref.get("rank", "—"), "record": False})
    best = min((m["ops"] for m in measured), default=None)
    for m in measured:
        rec = m["ops"] == best
        rows.append({"name": _short(m["note"]), "sub": m["note"], "ops": m["ops"],
                     "ratio": m["ops"] / rho, "role": "record" if rec else "measured",
                     "rank": "1" if rec else "—", "record": rec})
    rows.sort(key=lambda r: r["ops"])
    return rows


def render_arena_stats(measured, consts, bits):
    rho = consts["rho"]
    best = min((m["ops"] for m in measured), default=None)
    rec = f"{best / rho:.2f}×" if best else "—"
    opt = f"{consts['optimum'] / rho:.2f}×"
    flr = f"{consts['floor'] / rho:.2f}×"
    return (
        f'      <div class="stat"><div class="v gold">{rec}</div><div class="k">current record · ÷ rho</div></div>\n'
        f'      <div class="stat"><div class="v">{opt}</div><div class="k">negation-map optimum</div></div>\n'
        f'      <div class="stat"><div class="v">{flr}</div><div class="k">generic floor √(n/2)</div></div>\n'
        f'      <div class="stat"><div class="v">bits = {bits}</div><div class="k">official tier</div></div>'
    )


def render_beat_table(arena, measured, consts):
    rows = _arena_rows(arena, measured, consts)
    maxr = max((r["ratio"] for r in rows), default=1.0)
    out = []
    for r in rows:
        cls, barcol = _ROLE[r["role"]]
        rowcls = "lb-row best" if r["record"] else "lb-row"
        tag = ' <span class="tag-best">RECORD</span>' if r["record"] else ""
        ratio_cls = f" {cls}" if cls else ""
        barw = round(r["ratio"] / maxr * 100)
        out.append(
            f'      <div class="{rowcls}">\n'
            f'        <div class="rank mono">{html.escape(str(r["rank"]))}</div>\n'
            f'        <div class="name">{html.escape(r["name"])}{tag}<small>{html.escape(r["sub"])}</small></div>\n'
            f'        <div class="ops">{_fmt(r["ops"])}</div><div class="ratio{ratio_cls}">{_ratiostr(r["ratio"])}</div>\n'
            f'        <div class="bar"><i style="width:{barw}%;background:{barcol}"></i></div>\n'
            f"      </div>"
        )
    return "\n".join(out)


def render_history_table(measured, consts):
    rho = consts["rho"]
    rows = sorted(measured, key=lambda m: m["ops"])
    best = rows[0]["ops"] if rows else None
    out = []
    for i, m in enumerate(rows, 1):
        rec = m["ops"] == best
        rowcls = "lb-row best" if rec else "lb-row"
        ratio = m["ops"] / rho
        cls = "" if rec else " r-bad" if ratio > 1 else " r-ref"
        tag = ' <span class="tag-best">BEST</span>' if rec else ""
        out.append(
            f'      <div class="{rowcls}">\n'
            f'        <div class="rank mono">{i}</div>\n'
            f'        <div class="name">{html.escape(_short(m["note"]))}{tag}<small>{html.escape(m["note"])}</small></div>\n'
            f'        <div class="ops">{_fmt(m["ops"])}</div><div class="ratio{cls}">{_ratiostr(ratio)}</div>\n'
            f"      </div>"
        )
    return "\n".join(out)


def render_demo_score(measured, consts):
    """The illustrative score in the 'How it works' terminal — kept in step with the record."""
    best = min((m["ops"] for m in measured), default=None)
    ops = best if best else consts["optimum"]
    return (f'<span class="c-cost">{_fmt(ops)}</span> group ops   '
            f'<span class="c-com">({_ratiostr(ops / consts["rho"])} rho)</span>')


def _y(ratio):
    """ratio -> svg y, the same [0.50,1.45]->[240,40] mapping the chart uses."""
    r = max(0.50, min(1.45, ratio))
    return round(240 - (r - 0.50) / 0.95 * 200, 1)


def render_trajectory(measured, consts):
    rho = consts["rho"]
    pts = [{"ratio": m["ops"] / rho, "label": _short(m["note"])}
           for m in sorted(measured, key=lambda m: -m["ops"])]  # worst -> best
    n = len(pts)
    xs = [320.0] if n == 1 else [round(120 + i * (400 / (n - 1)), 1) for i in range(n)]
    for p, x in zip(pts, xs):
        p["x"], p["y"] = x, _y(p["ratio"])
    colours = ["#f87171", "#e7eaf0", "#f5b941"]

    def col(i):
        return colours[-1] if i == n - 1 else (colours[0] if i == 0 else colours[1])

    L = []
    # reference lines (computed)
    for ratio, txt, stroke in [(1.0, "1.00× rho", "#97a1b2"),
                               (consts["optimum"] / rho, "0.71× optimum", "#4ade80"),
                               (consts["floor"] / rho, "0.56× floor", "#38bdf8")]:
        y = _y(ratio)
        fill = f' fill="{stroke}"' if stroke != "#97a1b2" else ""
        L.append(f'        <line class="ref" x1="60" y1="{y}" x2="600" y2="{y}" stroke="{stroke}"/>')
        L.append(f'        <text x="600" y="{y - 4:.1f}" text-anchor="end" font-size="11"{fill}>{txt}</text>')
    # axes
    L.append('        <line class="axis" x1="60" y1="40" x2="60" y2="248"/>')
    L.append('        <line class="axis" x1="60" y1="248" x2="600" y2="248"/>')
    # descent polyline + points
    if pts:
        L.append('        <polyline points="{}" fill="none" stroke="#f5b941" stroke-width="2.5"/>'
                 .format(" ".join(f'{p["x"]},{p["y"]}' for p in pts)))
        for i, p in enumerate(pts):
            r = 6.5 if i == n - 1 else 5.5
            L.append(f'        <circle cx="{p["x"]}" cy="{p["y"]}" r="{r}" fill="{col(i)}"/>')
        for i, p in enumerate(pts):
            ly = max(12.0, p["y"] - 12)
            fill = f' fill="{col(i)}"' if i in (0, n - 1) else ' fill="#e7eaf0"'
            L.append(f'        <text x="{p["x"]}" y="{ly:.1f}" text-anchor="middle" font-size="12"{fill}>{_ratiostr(p["ratio"])}</text>')
            lblfill = ' fill="#f5b941"' if i == n - 1 else ""
            L.append(f'        <text x="{p["x"]}" y="266" text-anchor="middle" font-size="10.5"{lblfill}>{html.escape(p["label"])}</text>')
    return "\n".join(L)


# ---- marker injection ------------------------------------------------------

def inject(path, marker, new_inner, inline=False):
    """Replace text between `<!-- BUILD:marker ... -->` and `<!-- /BUILD:marker -->`.

    inline=True keeps it on one line (no surrounding newlines) — needed inside a
    <pre> block, where stray newlines would render as blank lines."""
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
    body = new_inner if inline else "\n" + new_inner + "\n"
    updated = text[: m.start(2)] + body + text[m.end(2):]
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

    # Scored "Beat rho" arena: reference rows are computed from n; the record,
    # score history, and trajectory come from the measured runs in results.tsv.
    arena = json.loads(ARENA.read_text())
    consts = arena_constants(arena["n"])
    measured = load_results(arena["tier_bits"])

    jobs = [  # (path, marker, inner, inline)
        (INDEX, "firstblood", render_site_rows(instances, solved_by, repo, branch), False),
        # blank lines around the table so GFM parses it as a table (an HTML
        # comment is an HTML block that a table must be separated from).
        (FB_README, "firstblood-table", "\n" + render_readme_table(instances, solved_by) + "\n", False),
        (INDEX, "arena-stats", render_arena_stats(measured, consts, arena["tier_bits"]), False),
        (INDEX, "arena-demo", render_demo_score(measured, consts), True),
        (INDEX, "arena-beat", render_beat_table(arena, measured, consts), False),
        (INDEX, "arena-trajectory", render_trajectory(measured, consts), False),
        (INDEX, "arena-history", render_history_table(measured, consts), False),
    ]

    stale = set()
    for path, marker, inner, inline in jobs:
        before, after = inject(path, marker, inner, inline)
        if before != after:
            stale.add(path.relative_to(ROOT))
            if not check:
                path.write_text(after)
    stale = sorted(stale)

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
