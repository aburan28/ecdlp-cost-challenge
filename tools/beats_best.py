#!/usr/bin/env python3
"""Monotonic "beats-best" gate for the scored arena (prototype).

Borrowed from ecdsa.fail's review rule — *a submission is accepted and promoted
only if it beats the current best* — adapted to this repo's git-as-ledger model.
It turns `results.tsv` from an open append-log into a strictly-improving frontier:
a run is ACCEPTED only when its mean group-op count is **strictly lower** than the
current record for the same tier (same `bits`); otherwise it is REJECTED.

Pure-stdlib, no dependencies.

    python3 tools/beats_best.py                       # gate ./score.json vs results.tsv
    python3 tools/beats_best.py --score score.json --against results.tsv
    python3 tools/beats_best.py --against <(git show origin/main:results.tsv)

`--against` is the leaderboard the candidate must beat. For a true "beats the
promoted frontier" check (like ecdsa.fail's server-side best), point it at the
committed/main `results.tsv`, not your local working copy.

Exit codes:  0 = ACCEPT (new record, or inaugural)   1 = REJECT   2 = bad input

Tiers vs authority: this gates whatever tier the candidate `score.json` is for. In
public CI that is the small correctness tier; the official `bits=40` ranking is run
by a maintainer with the sealed seed (a fork-readable workflow can't hold it), who
runs this same gate to decide promotion. Same logic, two trust contexts.
"""
import argparse
import json
import sys
from pathlib import Path


def load_candidate(path):
    d = json.loads(Path(path).read_text())
    m = d.get("metrics", {})
    correct = m.get("correct") is True
    ops = m.get("group_ops")
    bits = m.get("bits")
    rho = m.get("rho_reference")
    if ops is None:
        ops = d.get("score")
    return {"ops": ops, "bits": bits, "rho": rho, "correct": correct}


def load_leaderboard(path):
    """Best (min group_ops) per tier among correct rows. Tolerant of extra columns."""
    best = {}  # bits -> (ops, note)
    p = Path(path)
    if not p.exists():
        return best
    for line in p.read_text().splitlines():
        if not line.strip() or line.startswith("timestamp"):
            continue
        f = line.split("\t")
        if len(f) < 8:
            continue
        _ts, _commit, ops, bits, _rho, _ratio, correct, note = f[:8]
        if correct.strip() != "OK" or not ops.strip().isdigit() or not bits.strip().isdigit():
            continue
        ops, bits = int(ops), int(bits)
        if bits not in best or ops < best[bits][0]:
            best[bits] = (ops, note.strip())
    return best


def ratio(ops, rho):
    return f"{ops / rho:.4f}× rho" if rho else "(rho_ref unknown)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Monotonic beats-best gate for the arena.")
    ap.add_argument("--score", default="score.json", help="candidate score.json (default: ./score.json)")
    ap.add_argument("--against", default="results.tsv", help="leaderboard to beat (default: ./results.tsv)")
    args = ap.parse_args(argv)

    try:
        cand = load_candidate(args.score)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"!! cannot read candidate score {args.score}: {e}", file=sys.stderr)
        return 2

    if not cand["correct"] or cand["ops"] is None:
        print(f"REJECT — invalid run (correct={cand['correct']}); it recovered no valid k, so it cannot be a record.")
        return 1
    if cand["bits"] is None:
        print("!! candidate score.json has no metrics.bits — cannot place it on a tier", file=sys.stderr)
        return 2

    best = load_leaderboard(args.against)
    bits, ops, rho = cand["bits"], cand["ops"], cand["rho"]
    prev = best.get(bits)

    if prev is None:
        print(f"ACCEPT — inaugural record for bits={bits}")
        print(f"  candidate : {ops:,} ops  ({ratio(ops, rho)})")
        print(f"  (no prior correct run at this tier in {args.against})")
        return 0

    prev_ops, prev_note = prev
    if ops < prev_ops:
        gain = (prev_ops - ops) / prev_ops * 100
        print(f"ACCEPT — new record for bits={bits} 🏆")
        print(f"  candidate : {ops:,} ops  ({ratio(ops, rho)})")
        print(f"  prev best : {prev_ops:,} ops  ({ratio(prev_ops, rho)})  [{prev_note}]")
        print(f"  improvement: {gain:.2f}% fewer ops")
        return 0

    print(f"REJECT — does not beat the current best for bits={bits}")
    print(f"  candidate : {ops:,} ops  ({ratio(ops, rho)})")
    print(f"  best      : {prev_ops:,} ops  ({ratio(prev_ops, rho)})  [{prev_note}]")
    if ops == prev_ops:
        print("  a tie does not beat the record — you need strictly fewer ops.")
    else:
        print(f"  you need  : < {prev_ops:,} ops to be promoted ({ops - prev_ops:,} too many).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
