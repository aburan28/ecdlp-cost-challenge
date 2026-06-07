#!/usr/bin/env python3
"""Verify a First-Blood submission: does k recover the discrete log?

Pure Python (arbitrary-precision ints), no Sage / no dependencies — anyone can
audit a claimed break in seconds. A submission is valid iff  k * G == Q  on the
published curve.

Usage:
    python3 verify_first_blood.py instance_public_96.json <k>
    echo <k> | python3 verify_first_blood.py instance_public_96.json
"""
import json
import sys


def inv_mod(a, p):
    return pow(a, -1, p)


def ec_add(P, Q, a, p):
    if P is None:
        return Q
    if Q is None:
        return P
    x1, y1 = P
    x2, y2 = Q
    if x1 == x2 and (y1 + y2) % p == 0:
        return None  # P + (-P) = O
    if P == Q:
        lam = (3 * x1 * x1 + a) * inv_mod(2 * y1 % p, p) % p
    else:
        lam = (y2 - y1) * inv_mod((x2 - x1) % p, p) % p
    x3 = (lam * lam - x1 - x2) % p
    y3 = (lam * (x1 - x3) - y1) % p
    return (x3, y3)


def scalar_mul(k, P, a, p):
    R = None
    Q = P
    while k > 0:
        if k & 1:
            R = ec_add(R, Q, a, p)
        Q = ec_add(Q, Q, a, p)
        k >>= 1
    return R


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    d = json.load(open(sys.argv[1]))
    p, a, b, n = d["p"], d["a"], d["b"], d["n"]
    G = (d["Gx"], d["Gy"])
    Q = (d["Qx"], d["Qy"])

    if len(sys.argv) >= 3:
        k = int(sys.argv[2], 0)
    else:
        k = int(sys.stdin.read().strip(), 0)

    # Sanity: are G and Q actually on the curve?
    def on_curve(P):
        if P is None:
            return True
        x, y = P
        return (y * y - (x * x * x + a * x + b)) % p == 0

    assert on_curve(G) and on_curve(Q), "published G/Q not on curve (corrupt instance)"

    R = scalar_mul(k % n, G, a, p)
    ok = (R == Q)
    print(f"instance : {sys.argv[1]}  ({p.bit_length()}-bit)")
    print(f"k        : {k % n}")
    print(f"k*G == Q : {ok}")
    print("RESULT   :", "SOLVED  (first blood!)" if ok else "REJECTED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
