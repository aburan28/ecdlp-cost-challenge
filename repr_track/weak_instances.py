"""Weak instances for METER VALIDATION — a positive control, NOT the scored track.

The scored representation track uses the trusted verified-generic generator
(prime order, non-anomalous, large MOV degree). Those curves have no known sub-√n
attack, so the meter only ever prints NO-ASYMPTOTIC-WIN — and its VERIFIED-FASTER
verdict has never been exercised. This module builds the opposite: curves with a
*known* sub-√n attack, so we can prove the meter detects and quantifies one.

The lever is the group order's factorization. Pohlig–Hellman solves an ECDLP of
order `n = ∏ pᵢ^eᵢ` in `Θ(Σ eᵢ·√pᵢ)` group ops — dominated by `√pmax`. So:

  * `gamma → 0` (smooth order, pmax = O(1))     → polylog work,  α ≈ 0
  * `gamma` in (0,1) (one prime pmax ≈ n^gamma)  → `√pmax` = n^(gamma/2) work, α ≈ gamma/2
  * `gamma = 1` (prime order — the scored track) → `√n` work,    α = 0.5  (no win)

`gen_instance` only makes the `gamma=1` end, so this module searches for curves at a
chosen `gamma` by counting #E (Shanks BSGS), factoring it, and keeping curves whose
largest prime factor lands in the target window. Plain `int` arithmetic — this is
generation, not the metered solve.

⚠️ These are DELIBERATELY WEAK. They validate the instrument; they say nothing about
generic ECDLP, which remains √n.
"""
import math

from rho_control import _add, _mul, _SplitMix64


def _tonelli(a, p):
    """A square root of a mod p (p odd prime), or None if a is a non-residue."""
    a %= p
    if a == 0:
        return 0
    if pow(a, (p - 1) // 2, p) != 1:
        return None
    if p % 4 == 3:
        return pow(a, (p + 1) // 4, p)
    # Tonelli–Shanks
    q, s = p - 1, 0
    while q % 2 == 0:
        q //= 2
        s += 1
    z = 2
    while pow(z, (p - 1) // 2, p) != p - 1:
        z += 1
    m, c, t, r = s, pow(z, q, p), pow(a, q, p), pow(a, (q + 1) // 2, p)
    while t != 1:
        i, t2 = 0, t
        while t2 != 1:
            t2 = t2 * t2 % p
            i += 1
        b = pow(c, 1 << (m - i - 1), p)
        m, c, t, r = i, b * b % p, t * b * b % p, r * b % p
    return r


def _random_point(a, b, p, rng):
    """A random affine point on y² = x³ + ax + b (never the identity)."""
    for _ in range(200):
        x = rng.below(p)
        rhs = (x * x % p * x + a * x + b) % p
        y = _tonelli(rhs, p)
        if y is not None and not (x == 0 and y == 0):
            return (x, y)
    raise RuntimeError("could not sample a point (degenerate curve?)")


def _bsgs_trace_multiple(P, p, a, lo, hi):
    """Find t in [lo,hi] with t·P = O (a multiple of ord(P)), via BSGS on
    t·P = (p+1)·P shifted across the Hasse window. Returns t or None."""
    S = _mul(p + 1, P, a, p)                       # (p+1)·P ; want t with t·P = S, t≈p+1
    w = math.isqrt(hi - lo) + 1
    baby = {}                                       # r·P -> r, r in [0,w)
    R = None
    for r in range(w):
        baby[R if R is None else R[0]] = r          # key on x-coord (free, canonical ±)
        R = _add(R, P, a, p)
    wP = _mul(w, P, a, p)
    neg_wP = None if wP is None else (wP[0], (-wP[1]) % p)
    # giant: S - i·(w·P) == r·P  ⇒  t = (p+1) - (i·w) ... search both directions of i.
    base = (p + 1)
    cur = S
    steps = (hi - lo) // w + 2
    for i in range(steps + 1):
        key = None if cur is None else cur[0]
        if key in baby:
            for sgn, t in ((+1, base - (i * w - baby[key])), (+1, base - (i * w + baby[key]))):
                if lo <= t <= hi and _mul(t, P, a, p) is None:
                    return t
        cur = _add(cur, neg_wP, a, p)
    cur = _add(S, wP, a, p)
    for i in range(1, steps + 1):
        key = None if cur is None else cur[0]
        if key in baby:
            t = base + (i * w + baby[key])
            if lo <= t <= hi and _mul(t, P, a, p) is None:
                return t
        cur = _add(cur, wP, a, p)
    return None


def count_points(a, b, p, rng, tries=12):
    """#E for y²=x³+ax+b over F_p. Finds a Hasse-window multiple of ord(P) for a
    random P, then VERIFIES the candidate kills several other points (Lagrange) —
    rejecting small-order points that yield a wrong multiple. Returns #E or None."""
    r = math.isqrt(p)
    lo, hi = p + 1 - 2 * r - 2, p + 1 + 2 * r + 2
    for _ in range(tries):
        P = _random_point(a, b, p, rng)
        t = _bsgs_trace_multiple(P, p, a, lo, hi)
        if t is None:
            continue
        # t is a multiple of ord(P) in the window; the true #E is the value in the
        # window that annihilates EVERY point. Verify on fresh points.
        if all(_mul(t, _random_point(a, b, p, rng), a, p) is None for _ in range(4)):
            return t
    return None


def factorize(n):
    """Trial-division factorization (n is small, ≤ ~2^32). Returns {prime: exp}."""
    f, d = {}, 2
    while d * d <= n:
        while n % d == 0:
            f[d] = f.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        f[n] = f.get(n, 0) + 1
    return f


def _order_of(P, n, factn, a, p):
    """Exact order of P given #E=n and its factorization (reduce n by primes)."""
    order = n
    for q in factn:
        while order % q == 0 and _mul(order // q, P, a, p) is None:
            order //= q
    return order


def get_weak_instance(seed, bits, gamma, window=0.12, batch=40):
    """Search for a curve whose group order's largest prime factor pmax satisfies
    log_n(pmax) ≈ gamma (so a Pohlig–Hellman solve costs ~√pmax = n^(gamma/2)).

    Smooth orders are commoner than near-prime ones, so the FIRST in-window hit is
    biased to the low-γ edge; that makes pmax lumpy across a ladder and wrecks the
    power-law fit. So we take the **best of a batch**: collect up to `batch`
    in-window candidates and return the one whose γ_actual is closest to `gamma`,
    which centres the ladder and keeps the cost curve clean.

    Returns {p,a,b,n,Gx,Gy,Qx,Qy,bits,gamma_actual,pmax}; G generates the full group
    (order n), Q = k·G for hidden random k. `gamma=1.0` ⇒ near-prime (scored regime)."""
    rng = _SplitMix64(int(str(seed), 0) if isinstance(seed, str) else seed)
    p = (1 << bits) | 1
    while not _is_prime(p):
        p += 2
    target_lo, target_hi = gamma - window, gamma + window

    best = None  # (abs_err_to_gamma, inst)
    kept = 0
    for _ in range(200000):
        a = rng.below(p)
        b = rng.below(p)
        if (4 * a % p * a % p * a + 27 * b % p * b) % p == 0:   # singular
            continue
        n = count_points(a, b, p, rng)
        if n is None or n < 16:
            continue
        fac = factorize(n)
        g_actual = math.log(max(fac)) / math.log(n)
        if not (target_lo <= g_actual <= target_hi):
            continue
        G = None
        for _ in range(40):
            cand = _random_point(a, b, p, rng)
            if _order_of(cand, n, fac, a, p) == n:
                G = cand
                break
        if G is None:
            continue
        k = 1 + rng.below(n - 1)
        Q = _mul(k, G, a, p)
        inst = {"p": p, "a": a, "b": b, "n": n, "Gx": G[0], "Gy": G[1],
                "Qx": Q[0], "Qy": Q[1], "bits": bits,
                "gamma_actual": round(g_actual, 4), "pmax": max(fac)}
        err = abs(g_actual - gamma)
        if best is None or err < best[0]:
            best = (err, inst)
        kept += 1
        if err < 0.01 or kept >= batch:
            break
    if best is None:
        raise SystemExit(f"!! no curve with gamma≈{gamma} (±{window}) at bits={bits}; "
                         f"widen --window or change seed")
    return best[1]


def _is_prime(n):
    if n < 2:
        return False
    for q in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % q == 0:
            return n == q
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True
