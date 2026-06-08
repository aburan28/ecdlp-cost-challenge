#!/usr/bin/env python3
"""Monotonic "beats-best" gate for the scored arena.

Borrowed from ecdsa.fail's review rule — *a submission is accepted and promoted
only if it beats the current best* — adapted to this repo. It turns a result from
an open data point into a promotion decision: ACCEPT only when the candidate's
mean group-op count is **strictly lower** than the current best for the same tier
(same `bits`); otherwise REJECT.

Pure-stdlib, no dependencies. Two ways to name "the current best":

    # vs the best correct row in a leaderboard TSV
    python3 tools/beats_best.py --score score.json --against results.tsv
    python3 tools/beats_best.py --against <(git show origin/main:results.tsv)

    # vs ONE baseline score.json — use this for a PAIRED run, where the candidate
    # and the current-best solver were scored on the SAME fresh seed (CI gate):
    python3 tools/beats_best.py --score candidate.json --against-score best.json

Exit codes:  0 = ACCEPT (new record, or inaugural)   1 = REJECT   2 = bad input

Paired vs unpaired. The arena score is *deterministic* for a given seed + trial
battery, so the cleanest gate scores the candidate and the incumbent on the SAME
fresh seed (`--against-score`) — a common-random-numbers comparison that cancels
instance luck. A fresh seed minted at run time also can't be pre-solved offline,
which is why a CI gate needs no secret. `--against` (vs a leaderboard) is the
looser, unpaired check for a quick local "would this be promoted?".
"""
import argparse
import json
import sys
from pathlib import Path


def load_candidate(path):
    d = json.loads(Path(path).read_text())
    m = d.get("metrics", {})
    ops = m.get("group_ops")
    if ops is None:
        ops = d.get("score")
    return {"ops": ops, "bits": m.get("bits"), "rho": m.get("rho_reference"),
            "correct": m.get("correct") is True}


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


def decide(bits, ops, rho, prev_ops, prev_note):
    """Print a verdict and return an exit code. prev_ops=None means inaugural."""
    if prev_ops is None:
        print(f"ACCEPT — inaugural record for bits={bits}")
        print(f"  candidate : {ops:,} ops  ({ratio(ops, rho)})")
        print("  (no prior correct run at this tier)")
        return 0
    tag = f"  [{prev_note}]" if prev_note else ""
    if ops < prev_ops:
        gain = (prev_ops - ops) / prev_ops * 100
        print(f"ACCEPT — new record for bits={bits} 🏆")
        print(f"  candidate : {ops:,} ops  ({ratio(ops, rho)})")
        print(f"  prev best : {prev_ops:,} ops  ({ratio(prev_ops, rho)}){tag}")
        print(f"  improvement: {gain:.2f}% fewer ops")
        return 0
    print(f"REJECT — does not beat the current best for bits={bits}")
    print(f"  candidate : {ops:,} ops  ({ratio(ops, rho)})")
    print(f"  best      : {prev_ops:,} ops  ({ratio(prev_ops, rho)}){tag}")
    if ops == prev_ops:
        print("  a tie does not beat the record — you need strictly fewer ops.")
    else:
        print(f"  you need  : < {prev_ops:,} ops to be promoted ({ops - prev_ops:,} too many).")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Monotonic beats-best gate for the arena.")
    ap.add_argument("--score", default="score.json", help="candidate score.json (default: ./score.json)")
    ap.add_argument("--against", default="results.tsv", help="leaderboard TSV to beat (default: ./results.tsv)")
    ap.add_argument("--against-score", help="a single best score.json to beat (paired / same-seed mode)")
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

    bits, ops, rho = cand["bits"], cand["ops"], cand["rho"]

    if args.against_score:
        try:
            best = load_candidate(args.against_score)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"!! cannot read baseline score {args.against_score}: {e}", file=sys.stderr)
            return 2
        if not best["correct"] or best["ops"] is None:
            print(f"!! baseline {args.against_score} is not a valid run — cannot gate against it", file=sys.stderr)
            return 2
        if best["bits"] is not None and best["bits"] != bits:
            print(f"!! tier mismatch: candidate bits={bits} vs baseline bits={best['bits']}", file=sys.stderr)
            return 2
        return decide(bits, ops, rho, best["ops"], "current best, same seed (paired)")

    prev = load_leaderboard(args.against).get(bits)
    prev_ops, prev_note = prev if prev else (None, None)
    return decide(bits, ops, rho, prev_ops, prev_note)


if __name__ == "__main__":
    sys.exit(main())
