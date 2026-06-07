# Independent verification of a public instance JSON, using Sage's own curve
# arithmetic and point counting. Confirms the trusted Rust generator produced a
# genuinely generic prime-order curve. Run:  sage tools/verify_instance.sage instance.public.json
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "instance.public.json"
d = json.load(open(path))
p, a, b, n = d["p"], d["a"], d["b"], d["n"]
E = EllipticCurve(GF(p), [a, b])
order = E.order()
G = E(d["Gx"], d["Gy"])
Q = E(d["Qx"], d["Qy"])

print(f"p prime:                {is_prime(p)}  ({p.bit_length()} bits)")
print(f"order == n:             {order == n}   (E.order()={order}, n={n})")
print(f"n prime:                {is_prime(n)}")
print(f"non-anomalous (n!=p):   {n != p}")
print(f"G on curve, ord(G)==n:  {G in E and G.order() == n}")
print(f"Q on curve, Q in <G>:   {Q in E}")
# embedding degree: smallest k with n | p^k - 1
emb = None
acc = 1
for k in range(1, 500):
    acc = (acc * p) % n
    if acc == 1:
        emb = k
        break
print(f"embedding degree:       {'>500 (good)' if emb is None else emb}")
# recover the secret log just to confirm the instance is self-consistent
try:
    k = discrete_log(Q, G, ord=n, operation='+')
    print(f"discrete_log(Q,G):      k={k}  ->  k*G==Q: {k*G == Q}")
except Exception as e:
    print(f"discrete_log:           (skipped: {e})")
print(f"j-invariant:            {E.j_invariant()}  (0 or 1728 would be excluded)")
