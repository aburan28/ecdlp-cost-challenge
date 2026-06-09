"""Preprocessing DLP — a sub-√n ONLINE attack on a GENERIC curve (deterministic).

"Generic ECDLP costs √n" carries an unstated qualifier: *per single target, with no
precomputation*. For a FIXED public curve and generator `G` — exactly what everyone
shares for P-256, secp256k1, … — a one-time precomputed table makes every subsequent
DLP cost **sub-√n online**.

This uses the cleanest such attack: an **extended baby-step table**. Precompute the
baby steps `{j·G : 0 ≤ j < W}` ONCE (amortized over every target sharing `G`); then for
each target `Q`, take giant steps `Q − i·(W·G)` until one lands in the table, giving
`k = i·W + j`. Online cost is `⌈k/W⌉ ≤ n/W` giant steps — **deterministic** (no rho
variance), so the meter measures a clean exponent:

    online  T = n/W = n^α        precompute  P = W = n^(1−α)        ⇒   P·T = n

Total work P+T is still ≥ √n (no break of the problem); but the AMORTIZED online cost,
the right metric when one curve is attacked many times, is genuinely sub-√n. The scored
arena defeats this by re-randomizing tokens per run; the representation track does not.
"""
from counted_curve import IDENTITY


def _key(P):
    return None if P.is_identity else (P.x.v, P.y.v)


def precompute(E, G, n, W):
    """Build the baby-step table {j·G → j : 0 ≤ j < W} and the giant stride W·G. The
    harness counts these field ops as the one-time, amortized PRECOMPUTE cost (= W)."""
    baby = {}
    P = IDENTITY
    for j in range(W):
        baby.setdefault(_key(P), j)
        P = E.add(P, G)            # after the loop, P = W·G
    return {"baby": baby, "WG": P, "negWG": E.neg(P), "W": W}


def solve_online(E, G, Q, n, pc):
    """Giant steps Q − i·(W·G) until a baby match → k = i·W + j. ONLINE field ops,
    counted by the harness, scale as ⌈k/W⌉ ≤ n/W = n^α (deterministic, no variance)."""
    baby, negWG, W = pc["baby"], pc["negWG"], pc["W"]
    R = Q
    imax = n // W + 2
    for i in range(imax):
        j = baby.get(_key(R))
        if j is not None:
            return (i * W + j) % n
        R = E.add(R, negWG)
    return None


# Convenience solve(E,G,Q,n) with a per-curve cached table — for ad-hoc checks only;
# the validator drives precompute/online explicitly to separate the two costs.
_CACHE = {}


def solve(E, G, Q, n, W=None):
    key = (n, G.x.v, G.y.v)
    if key not in _CACHE:
        w = W if W is not None else max(8, round(n ** 0.6))
        _CACHE[key] = precompute(E, G, n, w)
    return solve_online(E, G, Q, n, _CACHE[key])
