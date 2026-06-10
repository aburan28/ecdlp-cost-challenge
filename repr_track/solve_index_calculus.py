"""Index calculus for prime-field ECDLP — the frontier non-generic attack.

The honest attempt at breaking the rho √n barrier. Shoup proves no GENERIC algorithm
can; a break must exploit the F_p representation. Index calculus is the method that
does so for many other groups (and for E over EXTENSION fields, Gaudry–Diem beat √n).
The open question this tests: does it beat √n for a PRIME-field curve?

Implementation (2-point decomposition, the cleanest IC):
  1. Factor base F = the B points with smallest x-coordinate.
  2. Precompute a hash of all P_i ± P_j (≈ B² sums) — the "decomposition table".
  3. Walk R = c·G + d·Q (one group op per step); each step, look up R in the table.
     A hit means R = ε_i P_i + ε_j P_j ⇒ a linear relation  c + d·k ≡ ε_i ℓ_i + ε_j ℓ_j.
  4. Collect > B relations; solve the linear system over F_n for k (off-meter — the
     attacker's number theory, like factoring in Pohlig–Hellman).

The harness counts the GROUP operations (steps 2–3). Theory says the cost-optimal
factor base B ≈ (n/2)^(1/3) gives total ≈ n^(2/3) group ops — *above* rho's √n, i.e.
the barrier holds. This module lets the meter MEASURE that exponent rather than assume
it. It recovers a correct k (it is a real, working attack); it is just not faster.
"""
import math

from counted_curve import IDENTITY
from weak_instances import _tonelli


def _solve_linear_mod_n(rels, B, n):
    """Gaussian elimination over F_n (n prime) for k. Unknowns ℓ_0..ℓ_{B-1}, k (col B).
    Each relation: ε_i ℓ_i + ε_j ℓ_j − d·k ≡ c (mod n). Returns k or None (under-determined)."""
    cols = B + 1
    rows = []
    for (c, d, i, si, j, sj) in rels:
        row = [0] * (cols + 1)
        if i == j:
            row[i] = (si + sj) % n
        else:
            row[i] = si % n
            row[j] = sj % n
        row[B] = (-d) % n
        row[cols] = c % n
        rows.append(row)

    m, r = len(rows), 0
    pivots = []
    for col in range(cols):
        piv = next((rr for rr in range(r, m) if rows[rr][col] % n), None)
        if piv is None:
            continue
        rows[r], rows[piv] = rows[piv], rows[r]
        inv = pow(rows[r][col], -1, n)
        rows[r] = [(v * inv) % n for v in rows[r]]
        for rr in range(m):
            if rr != r and rows[rr][col] % n:
                f = rows[rr][col]
                rows[rr] = [(rows[rr][t] - f * rows[r][t]) % n for t in range(cols + 1)]
        pivots.append((r, col))
        r += 1
        if r == m:
            break
    for rr, col in pivots:
        if col == B:                          # k is a pivot
            if not any(rows[rr][t] % n for t in range(cols) if t != B):  # no free vars in k's row
                return rows[rr][cols] % n
    return None


def build_factor_base(E, n, B):
    """The B points with smallest x for which x³+ax+b is a square."""
    a, b, p = E.a.v, E.b.v, E.F.p
    F, x = [], 1
    while len(F) < B and x < p:
        y = _tonelli((x * x % p * x + a * x + b) % p, p)
        if y is not None and not (x == 0 and y == 0):
            F.append(E.point(x, y))
        x += 1
    return F


def precompute_table(E, F):
    """Hash of P_i ± P_j → (i, j, sign_i, sign_j). Metered group ops."""
    p = E.F.p
    H = {}
    B = len(F)
    for i in range(B):
        for j in range(i, B):
            for sj, Pj in ((1, F[j]), (-1, E.neg(F[j]))):     # neg is the free involution
                S = E.add(F[i], Pj)
                if S.is_identity:
                    continue
                H.setdefault((S.x.v, S.y.v), (i, j, 1, sj))
                H.setdefault((S.x.v, (-S.y.v) % p), (i, j, -1, -sj))
    return H


def solve(E, G, Q, n, B=None):
    if B is None:
        B = max(8, round((n / 2) ** (1.0 / 3.0)))
    F = build_factor_base(E, n, B)
    B = len(F)
    H = precompute_table(E, F)

    # Relation walk: R = c·G + d·Q, one group op per step. Collect ~3B relations so the
    # B-unknown factor-base system has full rank and k is determined; if the first solve
    # is under-determined, collect 2B more and retry once.
    rels = []
    need = 3 * B + 32
    c, d = 1, 0
    R = E.scalar_mul(1, G)                     # = G
    cap = 300 * (n // max(B * B, 1) + 1) * need + 300000
    steps = 0
    extended = False
    while steps < cap:
        steps += 1
        key = None if R.is_identity else (R.x.v, R.y.v)
        hit = H.get(key)
        if hit is not None:
            i, j, si, sj = hit
            rels.append((c % n, d % n, i, si, j, sj))
            if len(rels) >= need:
                k = _solve_linear_mod_n(rels, B, n)
                if k is not None:
                    return k
                if extended:
                    return None
                need, extended = len(rels) + 2 * B, True
        if steps % 5 == 0:
            R = E.add(R, Q)
            d += 1
        else:
            R = E.add(R, G)
            c += 1
    return _solve_linear_mod_n(rels, B, n) if rels else None
