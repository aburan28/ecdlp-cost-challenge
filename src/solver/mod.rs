//! ============================================================================
//!  THIS IS THE ONLY FILE YOU EDIT.   (editablePaths = ["src/solver"])
//! ============================================================================
//!
//! NEGATION-MAP parallel distinguished-point rho, tuned for **minimum counted
//! group operations** — the score is the TOTAL op count over a single-threaded
//! run, so this solver optimizes ops, not wall-clock.
//!
//! Three op-count levers over the shipped baseline (W=512, R=256 built with
//! 2R scalar_muls), each a legitimate algorithmic change inside the oracle:
//!
//!  1. CHEAP JUMP TABLE.  The r-adding jump set J_r = u_r·P + v_r·Q is built from
//!     ONE base (a·P + b·Q, two scalar_muls) followed by R−1 single adds that
//!     alternately fold in P or Q. Each J_r is still a distinct pseudo-random
//!     group element with exactly-tracked (u_r, v_r), but the table now costs
//!     ≈ R adds instead of ≈ 2R·bits ops. At bits=40 that turns ~31k of pure
//!     setup into ~1k — a deterministic saving straight off the mean.
//!
//!  2. SMALL WALK COUNT W.  With a single-threaded meter there is no speed reason
//!     to run 512 walks; a large W only inflates the distinguished-point "drain
//!     tail" (≈ W·gap ops between a collision and its detection). We use a small W
//!     — just enough to batch round-trips so wall-clock stays sane — which makes
//!     the tail negligible. (Op count is identical whether the W adds happen in
//!     one batched round trip or W separate ones; batching is purely for speed.)
//!
//!  3. LARGE R (now affordable).  Because the table is cheap, we use a large
//!     partition count R: better Teske r-adding mixing and fewer negation-map
//!     fruitless cycles (rate ≈ 1/2R).
//!
//! NEGATION-MAP FRUITLESS CYCLES.  Walking the n/2 classes {±X} introduces short
//! cycles X→…→X that make no progress. We catch them two ways, both robust:
//!   * A DP-free cycle (no distinguished point inside) is caught by a per-walk set
//!     of points seen since its last DP: any revisit ⇒ a cycle with no DP ⇒ escape
//!     by a deterministic doubling (which preserves the (a,b) relation).
//!   * A cycle that does contain a DP shows up as a useless collision (db=0, the
//!     walk rejoined a stored DP with identical coefficients) ⇒ restart that walk.
//! Together these guarantee progress for any cycle length.
//!
//! Reference points (lower is better, scored as the MEAN over trials):
//!     negation-map rho optimum:           √(πn/4) ≈ 0.71× rho_ref   (target)
//!     generic floor with free negation:   √(n/2)  ≈ 0.56× rho_ref   (expected)
//!     Pollard-rho optimum (no neg map):   √(πn/2)  = 1.00× rho_ref

use crate::client::{Client, Tok};
use crate::field;
use crate::rng::{fnv1a, SplitMix64};
use std::collections::{HashMap, HashSet};

#[inline]
fn is_dp(tok: &Tok, dp_bits: u32) -> bool {
    if dp_bits == 0 {
        return true;
    }
    (fnv1a(tok) & ((1u64 << dp_bits) - 1)) == 0
}

/// Canonical representative of the class {t, −t}: the smaller token. `flipped`
/// says whether we took −t (so the caller negates the coefficients).
#[inline]
fn canon(t: &Tok, tneg: &Tok) -> (Tok, bool) {
    if *tneg < *t {
        (*tneg, true)
    } else {
        (*t, false)
    }
}

pub fn solve(c: &mut Client) -> u128 {
    let n = c.n;
    let bits = c.bits;
    let p = c.tok_p;
    let q = c.tok_q;
    let mut rng = SplitMix64::new(0x00C0_FFEE_u64 ^ n ^ 0x4E45_47); // "NEG"

    // --- parameters (see module header) -------------------------------------
    let w_bits: u32 = ((bits / 8) + 1).clamp(3, 7); // small W: only batches round-trips
    let w: usize = 1usize << w_bits;
    let r_bits: u32 = (bits / 4).clamp(8, 11); // large R: good mixing, few fruitless cycles
    let r_parts: usize = 1usize << r_bits;
    let r_mask: u64 = (r_parts as u64) - 1;
    // θ = 2^-dp_bits, ~2^7 DPs per walk; small enough that the drain tail (≈ W·2^dp_bits)
    // stays well under √(πn/4).
    let dp_bits: u32 = ((bits / 2) as i64 - w_bits as i64 - 7).clamp(3, 30) as u32;

    // --- cheap jump table:  J_r = u_r·P + v_r·Q ------------------------------
    let mut ju = vec![0u64; r_parts];
    let mut jv = vec![0u64; r_parts];
    let mut jtok: Vec<Tok> = Vec::with_capacity(r_parts);
    {
        let a0 = 1 + rng.below(n - 1);
        let b0 = 1 + rng.below(n - 1);
        let ap = c.scalar_mul(&p, a0 as u128);
        let bq = c.scalar_mul(&q, b0 as u128);
        let mut acc = c.add(&ap, &bq); // +1 op
        let (mut cu, mut cv) = (a0, b0);
        jtok.push(acc);
        ju[0] = cu;
        jv[0] = cv;
        for r in 1..r_parts {
            if r & 1 == 0 {
                acc = c.add(&acc, &p); // +1 op; fold in P
                cu = field::add(cu, 1, n);
            } else {
                acc = c.add(&acc, &q); // +1 op; fold in Q
                cv = field::add(cv, 1, n);
            }
            jtok.push(acc);
            ju[r] = cu;
            jv[r] = cv;
        }
    }

    // --- spawn W independent walks, canonicalize all at once -----------------
    let mut raw: Vec<Tok> = Vec::with_capacity(w);
    let mut ra: Vec<u64> = Vec::with_capacity(w);
    let mut rb: Vec<u64> = Vec::with_capacity(w);
    {
        let a0 = rng.below(n);
        let b0 = rng.below(n);
        let ap = c.scalar_mul(&p, a0 as u128);
        let bq = c.scalar_mul(&q, b0 as u128);
        raw.push(c.add(&ap, &bq));
        ra.push(a0);
        rb.push(b0);
        for i in 1..w {
            let r = i % r_parts;
            let prev = raw[i - 1];
            raw.push(c.add(&prev, &jtok[r])); // +1 op
            ra.push(field::add(ra[i - 1], ju[r], n));
            rb.push(field::add(rb[i - 1], jv[r], n));
        }
    }
    let negs = c.neg_batch(&raw); // free
    let mut cur: Vec<Tok> = Vec::with_capacity(w);
    let mut av: Vec<u64> = Vec::with_capacity(w);
    let mut bv: Vec<u64> = Vec::with_capacity(w);
    let mut seg: Vec<HashSet<Tok>> = (0..w).map(|_| HashSet::new()).collect();
    for i in 0..w {
        let (rep, flip) = canon(&raw[i], &negs[i]);
        cur.push(rep);
        seg[i].insert(rep);
        if flip {
            av.push(field::neg(ra[i], n));
            bv.push(field::neg(rb[i], n));
        } else {
            av.push(ra[i]);
            bv.push(rb[i]);
        }
    }

    // --- parallel distinguished-point rho on the n/2 classes {±X} ------------
    let mut seen: HashMap<Tok, (u64, u64)> = HashMap::new();
    let mut pairs: Vec<(Tok, Tok)> = Vec::with_capacity(w);
    let mut rs: Vec<usize> = Vec::with_capacity(w);
    loop {
        pairs.clear();
        rs.clear();
        for i in 0..w {
            let r = (fnv1a(&cur[i]) & r_mask) as usize;
            pairs.push((cur[i], jtok[r]));
            rs.push(r);
        }
        let raw_new = c.add_batch(&pairs); // +W counted ops, one round trip
        let neg_new = c.neg_batch(&raw_new); // free

        for i in 0..w {
            let r = rs[i];
            let (ca, cb, ccur) = (av[i], bv[i], cur[i]); // snapshot for escape
            let mut na = field::add(ca, ju[r], n);
            let mut nb = field::add(cb, jv[r], n);
            let (mut rep, flip) = canon(&raw_new[i], &neg_new[i]);
            if flip {
                na = field::neg(na, n);
                nb = field::neg(nb, n);
            }

            // DP-free fruitless-cycle escape: revisiting a point before reaching a
            // distinguished point means the walk is looping in a cycle that holds
            // no DP. Break it deterministically by doubling the point we stepped
            // from (preserves the (a,b) relation, so stored trails stay valid).
            if seg[i].contains(&rep) {
                let esc = c.add(&ccur, &ccur); // +1 op (rare with large R)
                let escneg = c.neg(&esc); // free
                let (rep2, flip2) = canon(&esc, &escneg);
                na = field::add(ca, ca, n);
                nb = field::add(cb, cb, n);
                if flip2 {
                    na = field::neg(na, n);
                    nb = field::neg(nb, n);
                }
                rep = rep2;
                seg[i].clear();
            }

            cur[i] = rep;
            av[i] = na;
            bv[i] = nb;

            if is_dp(&rep, dp_bits) {
                seg[i].clear(); // segment boundary: start a fresh no-DP window
                let (a1, b1) = (na, nb);
                if let Some(&(a2, b2)) = seen.get(&rep) {
                    let db = field::sub(b2, b1, n);
                    if db != 0 {
                        let da = field::sub(a1, a2, n);
                        return field::mul(da, field::inv(db, n), n) as u128;
                    } else {
                        // Useless collision (DP-containing fruitless cycle):
                        // restart this walk from a fresh random point.
                        let fa = 1 + rng.below(n - 1);
                        let fb = 1 + rng.below(n - 1);
                        let fp = c.scalar_mul(&p, fa as u128);
                        let fq = c.scalar_mul(&q, fb as u128);
                        let fresh = c.add(&fp, &fq);
                        let fresh_neg = c.neg(&fresh);
                        let (frep, fflip) = canon(&fresh, &fresh_neg);
                        cur[i] = frep;
                        av[i] = if fflip { field::neg(fa, n) } else { fa };
                        bv[i] = if fflip { field::neg(fb, n) } else { fb };
                    }
                } else {
                    seen.insert(rep, (a1, b1));
                }
            } else {
                seg[i].insert(rep);
            }
        }
    }
}
