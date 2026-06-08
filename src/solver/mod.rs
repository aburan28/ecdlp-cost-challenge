//! ============================================================================
//!  THIS IS THE ONLY FILE YOU EDIT.   (editablePaths = ["src/solver"])
//! ============================================================================
//!
//! NEGATION-MAP, FULL-MEMORY parallel rho.
//!
//! Key observation about the scoring rule: the oracle counts only *group
//! operations* (add/scalar_mul). Memory is free and unscored. The classic
//! distinguished-point (DP) trick exists to bound *memory*, but it costs group
//! operations: after two trails collide they must each walk ~1/θ further to the
//! next distinguished point before the collision is registered, an overhead of
//! ~W/θ ops. With memory free, the optimal choice is θ = 1 — store *every* point
//! and detect the collision the instant it happens. That deletes the entire DP
//! tail and lets the walk terminate at the true birthday bound.
//!
//! With negation free (−P = (x,−y)) we walk the n/2 classes {P,−P}, so the
//! expected number of steps to the first collision is
//!
//!       √(π·(n/2)/2) = √(π n / 4) ≈ 0.886·√n      (the negation-map rho optimum)
//!
//! and, because θ = 1, that is essentially the whole score (plus O(setup) and a
//! sub-percent batch-overshoot term). Reference points (lower is better, scored
//! as the MEAN over trials):
//!     this solver (neg-map, full memory):  ≈ √(πn/4)         ≈ 0.71× rho_ref
//!     Pollard-rho optimum (no neg map):    √(πn/2)           = 1.00× rho_ref
//!     generic floor with free negation:    √(n/2) ≈ 0.56× rho_ref  (expected bound)
//!
//! Fruitless cycles. The negation map's hazard is short cycles X→…→X that carry
//! *no* new linear information (they return to the same canonical point with the
//! same coefficients). With a full table they are trivial to spot: a revisit
//! whose stored coefficients give db = 0 is exactly a fruitless return. We escape
//! it with a single deterministic doubling and keep walking. A genuine
//! cross-trail meeting has db ≠ 0 and solves the instance immediately.

use crate::client::{Client, Tok};
use crate::field;
use crate::rng::{fnv1a, SplitMix64};
use std::collections::HashMap;

const R: usize = 128; // r-adding-walk partitions (Teske: ≳20 ⇒ near-ideal mixing)
const MBITS: usize = 20; // bit-length of jump-table coefficients (small ⇒ cheap setup)

/// Integer square root of a u64 (for sizing W to the tier).
fn isqrt(n: u64) -> u64 {
    if n < 2 {
        return n;
    }
    let mut x = (n as f64).sqrt() as u64;
    while x.saturating_mul(x) > n {
        x -= 1;
    }
    while (x + 1).saturating_mul(x + 1) <= n {
        x += 1;
    }
    x
}

/// Canonical representative of the class {t, −t}: the smaller token. The bool
/// says whether we took −t (so the caller negates the tracked coefficients).
#[inline]
fn canon(t: Tok, tneg: Tok) -> (Tok, bool) {
    if tneg < t {
        (tneg, true)
    } else {
        (t, false)
    }
}

pub fn solve(c: &mut Client) -> u128 {
    let n = c.n;
    let p = c.tok_p;
    let q = c.tok_q;
    let mut rng = SplitMix64::new(0x00C0_FFEE_u64 ^ n ^  0x4E45_47); // "NEG"

    // Batch width W. Total ops ≈ √(πn/4) is independent of W; W only sets the
    // round-trip granularity and the (exactly W) batch-overshoot charged on the
    // final add_batch. Scale with √n so overshoot stays ≲0.5% across tiers while
    // keeping round trips bounded (≈ √(πn/4)/W).
    let sn = isqrt(n);
    let w: usize = (sn / 1024).clamp(64, 4096) as usize;

    // --- Jump table J_r = u_r·P + v_r·Q with KNOWN, SMALL coefficients --------
    // Setup is itself counted, so build the table cheaply: form 2^j·P and 2^j·Q
    // ladders once (shared doublings), then assemble each u_r·P / v_r·Q from the
    // set bits of an MBITS-wide coefficient (popcount−1 adds each). This costs
    // ≈ 2·MBITS + R·(MBITS−1) ops instead of R full-width scalar_muls — a ~5×
    // setup reduction at the bits=40 tier. Small coefficients don't hurt walk
    // mixing (Teske: quality is set by R, not by jump magnitude).
    let mbits = MBITS.min(c.bits as usize - 1).max(8);
    let cmax: u64 = 1u64 << mbits;
    let mut pl: Vec<Tok> = Vec::with_capacity(mbits); // pl[j] = 2^j · P
    let mut ql: Vec<Tok> = Vec::with_capacity(mbits); // ql[j] = 2^j · Q
    pl.push(p);
    ql.push(q);
    for j in 1..mbits {
        pl.push(c.add(&pl[j - 1], &pl[j - 1]));
        ql.push(c.add(&ql[j - 1], &ql[j - 1]));
    }
    let combine = |c: &mut Client, ladder: &[Tok], e: u64| -> Tok {
        let mut acc: Option<Tok> = None;
        for (j, t) in ladder.iter().enumerate() {
            if (e >> j) & 1 == 1 {
                acc = Some(match acc {
                    None => *t,
                    Some(a) => c.add(&a, t),
                });
            }
        }
        acc.expect("coefficient is nonzero")
    };
    let mut ju = vec![0u64; R];
    let mut jv = vec![0u64; R];
    let mut jtok: Vec<Tok> = Vec::with_capacity(R);
    for r in 0..R {
        let u = 1 + rng.below(cmax - 1);
        let v = 1 + rng.below(cmax - 1);
        let up = combine(c, &pl, u);
        let vq = combine(c, &ql, v);
        jtok.push(c.add(&up, &vq));
        ju[r] = u;
        jv[r] = v;
    }

    // --- W starting points a_i·P + b_i·Q, built as one cheap add-chain --------
    let mut raw: Vec<Tok> = Vec::with_capacity(w);
    let mut ra: Vec<u64> = Vec::with_capacity(w);
    let mut rb: Vec<u64> = Vec::with_capacity(w);
    {
        let a0 = 1 + rng.below(n - 1);
        let b0 = 1 + rng.below(n - 1);
        let ap = c.scalar_mul(&p, a0 as u128);
        let bq = c.scalar_mul(&q, b0 as u128);
        raw.push(c.add(&ap, &bq));
        ra.push(a0);
        rb.push(b0);
        for i in 1..w {
            let r = i % R;
            let prev = raw[i - 1];
            raw.push(c.add(&prev, &jtok[r]));
            ra.push(field::add(ra[i - 1], ju[r], n));
            rb.push(field::add(rb[i - 1], jv[r], n));
        }
    }
    let negs = c.neg_batch(&raw); // free
    let mut cur: Vec<Tok> = Vec::with_capacity(w);
    let mut av: Vec<u64> = Vec::with_capacity(w);
    let mut bv: Vec<u64> = Vec::with_capacity(w);
    for i in 0..w {
        let (rep, flip) = canon(raw[i], negs[i]);
        cur.push(rep);
        if flip {
            av.push(field::neg(ra[i], n));
            bv.push(field::neg(rb[i], n));
        } else {
            av.push(ra[i]);
            bv.push(rb[i]);
        }
    }

    // --- Full-memory parallel walk; θ = 1 ------------------------------------
    let mut seen: HashMap<Tok, (u64, u64)> = HashMap::with_capacity(1 << 20);
    for i in 0..w {
        seen.entry(cur[i]).or_insert((av[i], bv[i]));
    }

    let mut pairs: Vec<(Tok, Tok)> = Vec::with_capacity(w);
    let mut rs: Vec<usize> = Vec::with_capacity(w);
    loop {
        pairs.clear();
        rs.clear();
        for i in 0..w {
            let r = (fnv1a(&cur[i]) % R as u64) as usize;
            pairs.push((cur[i], jtok[r]));
            rs.push(r);
        }
        let raw_new = c.add_batch(&pairs); // +W counted ops
        let neg_new = c.neg_batch(&raw_new); // free

        for i in 0..w {
            let r = rs[i];
            let (rep, flip) = canon(raw_new[i], neg_new[i]);
            let mut na = field::add(av[i], ju[r], n);
            let mut nb = field::add(bv[i], jv[r], n);
            if flip {
                na = field::neg(na, n);
                nb = field::neg(nb, n);
            }

            if let Some(&(a2, b2)) = seen.get(&rep) {
                let db = field::sub(b2, nb, n);
                if db != 0 {
                    // Genuine collision: (na−a2)·P = (b2−nb)·Q = (b2−nb)·k·P.
                    let da = field::sub(na, a2, n);
                    return field::mul(da, field::inv(db, n), n) as u128;
                }
                // db == 0: fruitless return to a known point. Escape with one
                // deterministic doubling of the current representative.
                let esc = c.add(&cur[i], &cur[i]); // +1 op (rare)
                let escn = c.neg(&esc); // free
                let (erep, eflip) = canon(esc, escn);
                let mut ea = field::add(av[i], av[i], n);
                let mut eb = field::add(bv[i], bv[i], n);
                if eflip {
                    ea = field::neg(ea, n);
                    eb = field::neg(eb, n);
                }
                if let Some(&(a3, b3)) = seen.get(&erep) {
                    let db2 = field::sub(b3, eb, n);
                    if db2 != 0 {
                        let da2 = field::sub(ea, a3, n);
                        return field::mul(da2, field::inv(db2, n), n) as u128;
                    }
                    // Still stuck (vanishingly rare); leave coords, retry next round.
                } else {
                    seen.insert(erep, (ea, eb));
                }
                cur[i] = erep;
                av[i] = ea;
                bv[i] = eb;
                continue;
            }

            seen.insert(rep, (na, nb));
            cur[i] = rep;
            av[i] = na;
            bv[i] = nb;
        }
    }
}
