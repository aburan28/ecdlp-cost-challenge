"""b2 — the same-hardware rho control.

b1 (`counted_field.py`) is a *cooperative* meter: it scores the field ops of a
re-executed reference implementation, but a solver that does arithmetic off-API can
under-report. b2 closes that hole without trying to meter anything: it runs a
**tuned generic baseline (Pollard rho) on the same box, on the same instances**, and
times both. Hardware, language, and constant factors cancel in the *ratio*; what
survives is the **exponent**. A genuinely sub-√n solver beats rho by a margin that
**widens with n** (the time ratio decays); a constant-factor or same-exponent solver
shows a *flat* ratio. So b2 can't be gamed by moving work off-meter — only by
actually being asymptotically faster.

Plain `int` arithmetic (no metering — this is the wall-clock control), Teske
r-adding walk (no doubling-branch bias), deterministic from a fixed seed so timings
are reproducible up to machine noise.
"""
import time


# ---- plain-int curve arithmetic (uncounted; this is the control) -----------

def _add(P, Q, a, p):
    if P is None:
        return Q
    if Q is None:
        return P
    x1, y1 = P
    x2, y2 = Q
    if x1 == x2:
        if (y1 + y2) % p == 0:
            return None
        s = (3 * x1 * x1 + a) * pow(2 * y1, -1, p) % p
    else:
        s = (y2 - y1) * pow(x2 - x1, -1, p) % p
    x3 = (s * s - x1 - x2) % p
    y3 = (s * (x1 - x3) - y1) % p
    return (x3, y3)


def _mul(k, P, a, p):
    R = None
    while k:
        if k & 1:
            R = _add(R, P, a, p)
        P = _add(P, P, a, p)
        k >>= 1
    return R


class _SplitMix64:
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFFFFFFFFFF

    def below(self, m):
        self.s = (self.s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        z ^= z >> 31
        return z % m


def pollard_rho_dlp(pub, seed=0x9E3779B9, r=32):
    """Recover k via a Teske r-adding rho with Floyd cycle detection. Returns k or
    None (degenerate collision — caller reseeds)."""
    p, a, n = pub["p"], pub["a"], pub["n"]
    G = (pub["Gx"], pub["Gy"])
    Q = (pub["Qx"], pub["Qy"])

    rng = _SplitMix64(seed)
    steps = []
    for _ in range(r):
        c = rng.below(n)
        d = rng.below(n)
        R = _add(_mul(c, G, a, p), _mul(d, Q, a, p), a, p)
        steps.append((R, c, d))

    def walk(X, A, B):
        i = (X[0] if X else 0) % r
        R, c, d = steps[i]
        return _add(X, R, a, p), (A + c) % n, (B + d) % n

    X, A, B = walk(G, 1, 0)
    Xh, Ah, Bh = walk(X, A, B)
    while X != Xh:
        X, A, B = walk(X, A, B)
        Xh, Ah, Bh = walk(*walk(Xh, Ah, Bh))
    denom = (Bh - B) % n
    if denom == 0:
        return None
    return ((A - Ah) * pow(denom, -1, n)) % n


def time_control(pub, reseeds=6):
    """Wall-clock seconds for rho to solve this instance (reseeding past the rare
    degenerate collision; the successful attempt's time only). Returns (k, seconds);
    k is verified by the caller."""
    dt = 0.0
    for j in range(reseeds):
        t0 = time.perf_counter()
        k = pollard_rho_dlp(pub, seed=0x9E3779B9 + j * 0x1000193)
        dt = time.perf_counter() - t0
        if k is not None:
            return k, dt
    return None, dt
