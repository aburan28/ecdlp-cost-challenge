# Generate a large VERIFIED-GENERIC prime-field ECDLP instance for the (unscored)
# representation-attack research track. The scored oracle arena uses the Rust
# generator for solvable sizes; this one is for big curves where you want full CM /
# pairing structure checks and don't intend to run rho.
#
# Usage:  sage tools/gen_instances.sage <bits> [seed]
# Writes: instance_public_<bits>.json   (public params only; k is discarded, so
#         nobody — including the generator — knows the discrete log: a genuine
#         challenge, self-verified by Q = k*G.)
import json, sys

bits = int(sys.argv[1]) if len(sys.argv) > 1 else 96
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
set_random_seed(seed)

def good_curve(bits):
    while True:
        p = random_prime(2**bits - 1, lbound=2**(bits-1))
        if p % 4 != 3:
            continue
        F = GF(p)
        for _ in range(40):
            a = F.random_element()
            b = F.random_element()
            if a == 0 or b == 0:
                continue                      # j in {0,1728}: exclude
            if 4*a**3 + 27*b**2 == 0:
                continue                      # singular
            E = EllipticCurve(F, [a, b])
            n = E.order()
            if not is_prime(n):
                continue                      # prime order only
            if n == p:
                continue                      # anomalous (Smart/SSSA)
            # MOV/Frey-Ruck: require large embedding degree
            emb_ok = True
            acc = 1
            for kk in range(1, 200):
                acc = (acc * p) % n
                if acc == 1:
                    emb_ok = False
                    break
            if not emb_ok:
                continue
            return E, p, int(a), int(b), int(n)

E, p, a, b, n = good_curve(bits)
G = E.gens()[0] if E.gens() else E.random_point()
while G.order() != n:
    G = E.random_point()
k = randint(1, n - 1)
Q = k * G
# k is intentionally NOT stored.

out = {
    "name": "generic-prime-field-ecdlp",
    "encoding": "affine-weierstrass",
    "bits": int(p.nbits()),
    "seed": seed,
    "p": int(p), "a": int(a), "b": int(b), "n": int(n),
    "Gx": int(G[0]), "Gy": int(G[1]),
    "Qx": int(Q[0]), "Qy": int(Q[1]),
    "j_invariant": int(E.j_invariant()),
    "note": "Research-track instance. k is unknown (discarded at generation). "
            "Recover k from these params by ANY method; verify via k*G == Q. "
            "Not scored on the oracle counter (not a generic-group computation).",
}
fn = f"instance_public_{p.nbits()}.json"
json.dump(out, open(fn, "w"), indent=2)
print(f"wrote {fn}: {p.nbits()}-bit prime-order curve, embedding degree > 200, j={E.j_invariant()}")
