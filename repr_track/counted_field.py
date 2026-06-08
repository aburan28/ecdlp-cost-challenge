"""b1 — a metered prime field `F_p`.

The representation track *gives* the solver the real curve `(p, a, b, G, Q)` so it
can attempt a **non-generic** attack (a decomposition, a factor base, an
index-calculus path) that the opaque generic-group oracle structurally cannot host.
The price: we can no longer meter group operations the way the arena does — the
solver has `p`, so it could do arithmetic with its own bignums off-meter.

So this meter works one level down and **cooperatively**: the harness owns a field
`F_p` whose every multiplicative operation bumps a counter, hands it to the solver,
and *re-executes the solver itself*. The score is the field-op count of that
re-execution — a **hardware-independent, reproducible** cost (matches the arena's
ethos: a count, not a wall-clock). Field multiplications are the universal currency
of elliptic-curve cost, so `mul + sqr + inv` is the natural unit.

`HONEST LIMITATION (why b2 exists).` Unlike the arena, this count is **not
adversarially unforgeable**: a solver that reimplements `F_p` with raw ints and
never calls this field reports ≈0 ops. So b1 measures the field-op complexity of a
*good-faith reference implementation*, re-executed by the harness — and is paired
with the b2 same-hardware rho-control horse race (`rho_control.py`), which times the
solver end-to-end against a tuned rho on identical instances and so cannot be gamed
by moving arithmetic off-API. b1 is the publishable curve; b2 is the truth check.

Adds and subtractions are **free** (cheap, and the arena likewise makes `neg`
free); only the multiplicative ops `mul`, `sqr`, `inv` are counted.
"""


class FieldCounter:
    """Harness-owned tally of multiplicative field ops. The solver holds a field
    that mutates this; it cannot read or reset it mid-solve (the harness does)."""

    __slots__ = ("mul", "sqr", "inv")

    def __init__(self):
        self.mul = 0
        self.sqr = 0
        self.inv = 0

    def total(self):
        """Headline score: total multiplicative field ops (lower is better)."""
        return self.mul + self.sqr + self.inv

    def breakdown(self):
        return {"mul": self.mul, "sqr": self.sqr, "inv": self.inv, "total": self.total()}


class Fp:
    """An element of `F_p`. Arithmetic routes through the field's counter. Equality
    and hashing are FREE (comparisons aren't field ops) so the solver can use
    elements as dict keys (BSGS tables, distinguished points) without paying."""

    __slots__ = ("v", "F")

    def __init__(self, v, F):
        self.v = v % F.p
        self.F = F

    # --- free: additive group + comparisons -------------------------------
    def __add__(self, o):
        return Fp(self.v + o.v, self.F)

    def __sub__(self, o):
        return Fp(self.v - o.v, self.F)

    def __neg__(self):
        return Fp(-self.v, self.F)

    def __eq__(self, o):
        return isinstance(o, Fp) and self.v == o.v

    def __hash__(self):
        return hash(self.v)

    def is_zero(self):
        return self.v == 0

    # --- counted: multiplicative ops --------------------------------------
    def __mul__(self, o):
        self.F.c.mul += 1
        return Fp(self.v * o.v, self.F)

    def sqr(self):
        self.F.c.sqr += 1
        return Fp(self.v * self.v, self.F)

    def inv(self):
        self.F.c.inv += 1
        return Fp(pow(self.v, self.F.p - 2, self.F.p), self.F)

    def __repr__(self):
        return f"Fp({self.v})"


class CountedField:
    """`F_p` with a harness-owned op counter. `F(v)` lifts an int into the field.

    The solver receives this object and must do *all* field arithmetic through it
    for the count to be meaningful (see the module docstring's honest limitation).
    """

    def __init__(self, p):
        self.p = int(p)
        self.c = FieldCounter()

    def __call__(self, v):
        return Fp(int(v), self)

    def zero(self):
        return Fp(0, self)

    def one(self):
        return Fp(1, self)

    def reset(self):
        """Harness-only: zero the counter before timing a solve."""
        self.c = FieldCounter()
