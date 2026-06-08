"""The real curve `E: y² = x³ + a·x + b` over a metered `F_p` (`counted_field.py`).

Point arithmetic is built on the counted field, so a solver doing ordinary
elliptic-curve operations is metered automatically — every `add`/`double`/
`scalar_mul` spends the field `mul`/`sqr`/`inv` it actually performs. The solver
*also* gets the raw field (via `E.F`) to attempt non-generic, representation-level
attacks; those are metered at the field level too.

This is the affine short-Weierstrass group law (one inversion per add/double).
A solver that wants to amortize inversions (Montgomery's trick, projective coords)
can — and the meter will reward it, exactly as on real hardware.
"""
from counted_field import CountedField, Fp


class Point:
    """Affine point, or the identity `O` (x=y=None)."""

    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y

    @property
    def is_identity(self):
        return self.x is None

    def __eq__(self, o):
        return isinstance(o, Point) and self.x == o.x and self.y == o.y

    def __hash__(self):
        # FREE: x-coordinate key (canonical up to ±y); enough for BSGS/DP tables.
        return hash(None if self.x is None else self.x.v)

    def __repr__(self):
        return "O" if self.is_identity else f"({self.x.v}, {self.y.v})"


IDENTITY = Point(None, None)


class Curve:
    """`y² = x³ + a x + b` over the metered field `F`."""

    def __init__(self, F, a, b):
        self.F = F
        self.a = F(a)
        self.b = F(b)

    # ---- group law (counted via the field) --------------------------------
    def neg(self, P):
        return IDENTITY if P.is_identity else Point(P.x, -P.y)

    def add(self, P, Q):
        if P.is_identity:
            return Q
        if Q.is_identity:
            return P
        if P.x == Q.x:
            if (P.y + Q.y).is_zero():
                return IDENTITY          # P = -Q
            return self.double(P)        # P = Q
        s = (Q.y - P.y) * (Q.x - P.x).inv()   # 1 inv + 1 mul
        x3 = s.sqr() - P.x - Q.x              # 1 sqr
        y3 = s * (P.x - x3) - P.y             # 1 mul
        return Point(x3, y3)

    def double(self, P):
        if P.is_identity or P.y.is_zero():
            return IDENTITY
        x2 = P.x.sqr()                        # 1 sqr
        s = (x2 + x2 + x2 + self.a) * (P.y + P.y).inv()  # 1 inv + 1 mul (×3, ×2 are free adds)
        x3 = s.sqr() - P.x - P.x              # 1 sqr
        y3 = s * (P.x - x3) - P.y             # 1 mul
        return Point(x3, y3)

    def scalar_mul(self, k, P):
        """Double-and-add. Cost ≈ (log k doublings + ~½ log k adds) of field ops."""
        k = int(k)
        if k < 0:
            return self.scalar_mul(-k, self.neg(P))
        R = IDENTITY
        Acc = P
        while k:
            if k & 1:
                R = self.add(R, Acc)
            Acc = self.double(Acc)
            k >>= 1
        return R

    # ---- helpers ----------------------------------------------------------
    def is_on_curve(self, P):
        if P.is_identity:
            return True
        lhs = P.y.sqr()
        rhs = P.x.sqr() * P.x + self.a * P.x + self.b
        return lhs == rhs

    def point(self, x, y):
        return Point(self.F(x), self.F(y))


def curve_from_public(pub):
    """Build (Curve, G, Q, n) from a public instance dict {p,a,b,Gx,Gy,Qx,Qy,n}.
    Returns a FRESH CountedField each call so the counter starts clean per instance."""
    F = CountedField(pub["p"])
    E = Curve(F, pub["a"], pub["b"])
    G = E.point(pub["Gx"], pub["Gy"])
    Q = E.point(pub["Qx"], pub["Qy"])
    return E, G, Q, int(pub["n"])
