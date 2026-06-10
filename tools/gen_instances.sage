# Generate a large VERIFIED-GENERIC prime-field ECDLP instance for the (unscored)
# representation-attack research track. The scored oracle arena uses the Rust
# generator for solvable sizes; this one is for big curves where you want full CM /
# pairing structure checks and don't intend to run rho.
#
# Usage:  sage tools/gen_instances.sage <bits> [seed]
# Writes: instance_public_<bits>.json   (public params only; k is drawn from system
#         entropy — NOT the published seed — and discarded, so nobody, including the
#         generator, knows the discrete log: a genuine challenge, self-verified by
#         Q = k*G. The seed determines only the curve, so anyone can re-derive it and
#         audit that the curve is good_curve's honest output, not hand-picked.)
import json, os, sys

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
# SECURITY — the secret scalar must NOT come from the seeded PRNG.
# set_random_seed(seed) makes the ENTIRE Sage random stream a deterministic
# function of `seed`, which is published below. Curve params may safely be
# seed-derived (reproducibility lets anyone audit the curve is good_curve's honest
# output, not a hand-picked weak one) — but a seed-derived k is equivalent to
# PUBLISHING k: re-running this script with the same seed recomputes it. So draw k
# from system entropy (os.urandom), independent of `seed`, and discard it.
def secret_scalar(n):
    nbits = int(n - 1).bit_length()
    nbytes = (nbits + 7) // 8
    while True:
        x = int.from_bytes(os.urandom(nbytes), "big") & ((1 << nbits) - 1)
        if 1 <= x <= n - 1:
            return x  # uniform in [1, n-1], unpredictable, never stored

k = secret_scalar(n)
Q = k * G
del k  # genuinely discarded — independent of the public seed, nobody can recompute it

out = {
    "name": "generic-prime-field-ecdlp",
    "encoding": "affine-weierstrass",
    "bits": int(p.nbits()),
    "seed": seed,
    "p": int(p), "a": int(a), "b": int(b), "n": int(n),
    "Gx": int(G[0]), "Gy": int(G[1]),
    "Qx": int(Q[0]), "Qy": int(Q[1]),
    "j_invariant": int(E.j_invariant()),
    "note": "Research-track instance. k was drawn from system entropy (os.urandom), "
            "independent of the published seed (which determines only the auditable "
            "curve), and immediately discarded — nobody, including the generator, "
            "knows it. Recover k from these params by ANY method; verify via k*G == Q. "
            "Not scored on the oracle counter (not a generic-group computation).",
}
fn = f"instance_public_{p.nbits()}.json"
json.dump(out, open(fn, "w"), indent=2)
print(f"wrote {fn}: {p.nbits()}-bit prime-order curve, embedding degree > 200, j={E.j_invariant()}")
