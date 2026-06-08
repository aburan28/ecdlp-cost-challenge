"""Reference solver for the representation track — baby-step/giant-step.

A submission is a module exposing `solve(E, G, Q, n) -> k` that recovers the log
`k` (Q = k·G) using the *metered* curve `E` (`counted_curve.Curve` over a
`CountedField`). Every field op it performs is counted; the harness scores the
total (`repr_meter.py`).

BSGS is a clean reference: it's a real representation-level computation (it
manipulates coordinates, not opaque tokens) and it's **deterministic**, so its
field-op count is a fixed function of the instance — no trial averaging needed.
Its cost is `Θ(√n)` field ops, so the meter should fit exponent `α ≈ 0.5`: the
expected result on a generic curve, and the baseline a *genuinely faster*
(sub-√n, structure-exploiting) submission must beat.
"""
import math

from counted_curve import IDENTITY


def solve(E, G, Q, n):
    m = math.isqrt(n) + 1

    # Baby steps: table[j·G] = j for j in [0, m].  (Point hashing is free.)
    table = {}
    R = IDENTITY
    for j in range(m + 1):
        if R not in table:
            table[R] = j
        R = E.add(R, G)

    # Giant steps: Q − i·(m·G); a hit gives k = i·m + j.
    stride = E.neg(E.scalar_mul(m, G))
    R = Q
    for i in range(m + 1):
        j = table.get(R)
        if j is not None:
            return (i * m + j) % n
        R = E.add(R, stride)
    return None  # unreachable for a valid instance (BSGS is complete over [0,n))
