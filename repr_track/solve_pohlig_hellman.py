"""Pohlig–Hellman solver for the representation track — the sub-√n attack a weak
(non-prime-order) instance admits, metered through the counted field.

Given `(E, G, Q, n)`, the attacker factors the public order `n = ∏ pᵢ^eᵢ` (integer
arithmetic — not a field op, so it isn't metered, exactly as the attacker's own
number theory shouldn't be), then solves the ECDLP in each prime-power subgroup and
recombines by CRT. The subgroup solves cost `Θ(√pmax)` group operations — every one
a counted-field point op — so on a curve with smooth/near-smooth order this is
**decisively sub-√n**, and the meter should measure α ≈ (log_n pmax)/2.

On a PRIME-order curve (the scored track) PH degenerates to a single `√n` BSGS — no
win, α = 0.5 — which is the correct boundary.
"""
import math

from counted_curve import IDENTITY


def _factorize(n):
    f, d = {}, 2
    while d * d <= n:
        while n % d == 0:
            f[d] = f.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        f[n] = f.get(n, 0) + 1
    return f


def _crt(rs, ms):
    """Combine x ≡ rs[i] (mod ms[i]) for coprime ms. Integer arithmetic (off-meter)."""
    x, mod = 0, 1
    for r, m in zip(rs, ms):
        g = mod  # ms are coprime ⇒ inverse of mod modulo m exists
        inv = pow(mod % m, -1, m)
        x += mod * (((r - x) % m) * inv % m)
        mod *= m
    return x % mod


def _bsgs_subgroup(E, P, R, order):
    """x in [0, order) with x·P == R, where P has order `order`. O(√order) point ops."""
    m = math.isqrt(order) + 1
    table = {}
    cur = IDENTITY
    for j in range(m):
        if cur not in table:
            table[cur] = j
        cur = E.add(cur, P)
    step = E.neg(E.scalar_mul(m, P))   # -m·P
    cur = R
    for i in range(m):
        j = table.get(cur)
        if j is not None:
            return (i * m + j) % order
        cur = E.add(cur, step)
    return None


def solve(E, G, Q, n):
    fac = _factorize(n)
    rs, ms = [], []
    for p, e in fac.items():
        pe = p ** e
        cof = n // pe
        Gi = E.scalar_mul(cof, G)        # order pe
        Qi = E.scalar_mul(cof, Q)
        gamma = E.scalar_mul(pe // p, Gi)  # element of order p
        # Pohlig–Hellman prime-power lifting: recover k mod pe digit by digit (base p).
        x = 0
        for j in range(e):
            t = E.add(Qi, E.neg(E.scalar_mul(x, Gi)))
            h = E.scalar_mul(p ** (e - 1 - j), t)   # lands in the order-p subgroup
            d = _bsgs_subgroup(E, gamma, h, p)
            if d is None:
                return None
            x += d * (p ** j)
        rs.append(x % pe)
        ms.append(pe)
    return _crt(rs, ms) % n
