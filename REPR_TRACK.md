# The representation track, metered — score a non-generic algorithm

> **Reframe.** The scored arena *hides* the curve, which forces generic play and
> pins the exponent at `α = 0.5` (Shoup). This track **publishes** the curve
> `(p,a,b,G,Q)` and asks the real frontier question: can *any* method — a
> decomposition, a factor base, an index-calculus path — bend the exponent **below
> 0.5**? Like [the scaling track](SCALING.md), it scores the **cost curve**, not a
> single solved instance — but with a non-generic meter, because here the solver
> holds the representation.

This is the **scored** layer over the [First-Blood board](first_blood/README.md).
First-Blood is pass/fail ("can you recover `k` at all?"); this asks "how does your
method's cost **scale**?" — and gives a genuine sub-√n result a *number*, not just a
checkmark.

## The metering problem (why two meters)

In the arena, hiding the representation is what makes the op-count unforgeable — you
*can't* add points without the counted oracle. Here the solver has `p`, so it can do
field arithmetic with its own bignums off-meter. There is no single unforgeable
count. So we use two complementary meters and cross-check them:

- **b1 — counted field ops (SCORED, authoritative).** The harness owns a metered
  `F_p` ([`repr_track/counted_field.py`](repr_track/counted_field.py)); the solver
  runs against it and the harness re-executes it, fitting `field_ops ≈ c·n^α` across
  a ladder, **held-out-verified** (same fitter as the scaling track). Deterministic,
  hardware-independent, reproducible. *Cooperative*: a solver that reimplements `F_p`
  off-API under-counts — so b1 alone is gameable.
- **b2 — same-hardware rho race (CORROBORATOR).** The solver and a tuned rho control
  ([`repr_track/rho_control.py`](repr_track/rho_control.py)) solve identical
  instances on one box; we fit the **exponent gap** between their wall-clock curves,
  with a CI over repeated timings. b2 *can't* be gamed off-meter — a genuinely
  sub-√n method beats rho by a margin that widens with `n`. But b2 is a **large-n
  instrument**: at toy sizes wall-clock exponents are overhead/noise-limited (the
  same pre-asymptotic deflation the scaling track documents), so b2 never overrides
  b1 — it only **corroborates or blocks a sub-√n claim**.

## Verdict — b1 leads, b2 guards

| b1 (clean field-op exponent) | b2 (wall-clock gap vs rho) | verdict |
|---|---|---|
| α CI entirely **below 0.5**, held-out ✅ | gap CI **decisively negative** | **VERIFIED-FASTER** |
| α CI **below 0.5**, held-out ✅ | gap CI not negative | **SUSPECT** — b1 likely gamed off-API, or a fit artifact |
| α ≈ 0.5 (CI includes 0.5) | anything | **NO-ASYMPTOTIC-WIN** — b2's toy-size point estimate is noise; the clean meter rules |

`VERIFIED-FASTER` is deliberately hard: it needs the reproducible field-op curve to
show sub-√n scaling that *predicts a held-out tier*, **and** an end-to-end wall-clock
win over rho that can't be faked off-meter.

## Reference result — BSGS on a generic curve (measured)

`solve_reference.py` (baby-step/giant-step), ladder `20,22,24,26` → held-out `28`,
seed `0xC0FFEE`:

| meter | result |
|---|---|
| **b1 field-op law** | `field_ops ≈ 6·n^0.500`, **α = 0.500** (95% CI [0.38, 0.62]) |
| **b1 held-out (bits=28)** | predicted 71,739, measured 76,011 → ✅ verified (z=+0.23) |
| **b2 rho race** | gap 95% CI **[−0.23, 0.65] — straddles 0, abstains** (the point estimate's sign flips run-to-run: pure timing noise at toy sizes) |
| **verdict** | **NO-ASYMPTOTIC-WIN** |

This is the **honest** result: even handed the full representation, a verified-generic
curve costs `√n` — BSGS fits `α = 0.5` exactly and rho can't be beaten. The meter is
calibrated to say "no win" here, so that if a genuinely non-generic attack ever lands,
its sub-0.5 α (held-out) and negative b2 gap will stand out against this baseline.

## How to run / submit a solver

```bash
python3 repr_track/repr_meter.py                                  # reference BSGS
python3 repr_track/repr_meter.py --solver my_attack \
        --ladder 20,22,24,26 --holdout 28 --timing-reps 9        # your module
python3 repr_track/repr_meter.py --seed 0x<SECRET> --boot 4000   # sealed grading seed
```

A submission is a Python module exposing `solve(E, G, Q, n) -> k`, where `E` is the
metered [`Curve`](repr_track/counted_curve.py) over a `CountedField`, `G`/`Q` are
points, and `n` is the prime order. Do **all** field arithmetic through `E` (and
`E.F`) for the b1 count to be meaningful; b2 will catch you if you don't. Instances
come from the **trusted verified-generic generator** (`gen_instance`) — genericity
matters more here, since a sub-√n result on an accidentally weak curve would be a
false alarm. The artifact is `repr_scaling.json`; the committed reference baseline is
`repr_scaling.baseline.json`.

## Scope & honesty

- This is **not** a claim that ECDLP is broken. It is where a real attack would land,
  *with a measured cost curve* instead of a checkmark.
- `NO-ASYMPTOTIC-WIN` on these toy sizes is **not** evidence that no sub-√n attack
  exists — per the lab constitution, the generic floor is not an impossibility proof.
- Sizes are tiny by design (`bits ≤ ~28`) so a metered Python solver finishes; the
  *exponent*, not the absolute size, is the deliverable.

See [`SCALING.md`](SCALING.md) for the generic-arena twin (α≡0.5, rank by the
constant) and [`DESIGN.md`](DESIGN.md) for why the arena must hide the representation.
