"""Representation-track instances come from the TRUSTED generator.

Genericity matters *more* here than in the arena: a "sub-√n" result on an
accidentally weak curve (smooth order, anomalous, low embedding degree) would be a
false alarm, not an algorithm. So we do NOT roll our own curves — we shell out to
the repo's verified-generic Rust generator (`gen_instance`), which enforces prime
order, non-anomalous `n≠p`, large MOV embedding degree, and `j∉{0,1728}`, and is
re-checkable by `tools/verify_instance.sage`. We only consume its published
`(p,a,b,G,Q,n)` — `k` is secret, exactly as the solver must find it.
"""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "target" / "release" / "gen_instance"

_FIELDS = ("p", "a", "b", "n", "Gx", "Gy", "Qx", "Qy")


def get_instance(seed, bits):
    """Return the verified-generic public instance at this tier as a dict of ints.
    `seed` is combined with `bits` by the generator, so one sealed seed yields a
    distinct curve per rung (common random numbers across the ladder)."""
    if not GEN.exists():
        raise SystemExit(f"!! {GEN} not built — run ./setup.sh first")
    seed_arg = seed if isinstance(seed, str) else str(seed)
    out = subprocess.run([str(GEN), seed_arg, str(bits)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"!! gen_instance {seed_arg} {bits} failed:\n{out.stderr}")
    d = json.loads(out.stdout)
    inst = {k: int(d[k]) for k in _FIELDS}
    inst["bits"] = int(d["bits"])
    return inst
