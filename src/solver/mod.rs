//! ============================================================================
//!  THIS IS THE ONLY FILE YOU EDIT.   (editablePaths = ["src/solver"])
//! ============================================================================
//!
//! Goal: recover the discrete log k (with Q = k·P) using as few **counted group
//! operations** as possible. You touch the group exclusively through `Client`:
//!
//!     c.add(a, b)            -> token of (a + b)          [+1 group op]
//!     c.add_batch(&pairs)    -> tokens of each (a + b)    [+1 op per pair]
//!     c.neg(a)               -> token of (-a)             [+1 group op]
//!     c.scalar_mul(a, m)     -> token of (m·a)            [+#dbl+#add for m]
//!     c.is_identity(a)       -> bool                      [free]
//!     a == b                 point equality (token cmp)   [free]
//!     c.n, c.bits, c.tok_p, c.tok_q, c.tok_o              public instance data
//!
//! Return the recovered k (mod n). The trusted harness submits it and scores you
//! on the oracle's own op counter — you cannot under-report it.
//!
//! Reference points (lower is better):
//!     Shipped baseline (this file): parallel distinguished-point rho ≈ 1.2–1.5·√n.
//!     Pollard-rho optimum:          √(πn/2) ≈ 1.2533·√n ops.        <- the target
//!     Shoup generic-group floor:    √n ops (proven; you cannot beat this here).
//!
//! `add_batch` is the key to wall-clock scaling: it steps all W parallel walks in
//! one pipe round trip, so higher tiers run fast even though each group op is
//! still individually counted. Ways to push the *score* down toward 1.00×: the
//! negation map (≈√2), tuning W / the distinguished-point rate θ, a better
//! r-adding walk (Teske), or Gaudry–Schost. Going below √n would require breaking
//! out of the generic group model — which this arena forbids (see README).

use crate::client::{Client, Tok};
use crate::field;
use crate::rng::{fnv1a, SplitMix64};
use std::collections::HashMap;

/// Number of partitions in the r-adding walk.
const R: usize = 32;

#[derive(Clone)]
struct Walk {
    tok: Tok,
    a: u64,
    b: u64,
}

#[inline]
fn is_dp(tok: &Tok, dp_bits: u32) -> bool {
    if dp_bits == 0 {
        return true;
    }
    (fnv1a(tok) & ((1u64 << dp_bits) - 1)) == 0
}

pub fn solve(c: &mut Client) -> u128 {
    let n = c.n;
    let bits = c.bits;
    let p = c.tok_p;
    let q = c.tok_q;
    let mut rng = SplitMix64::new(0x00C0_FFEE_u64 ^ n);

    // W parallel walks; distinguished-point rate θ = 2^dp_bits, chosen so the
    // detection slack (≈ W·θ) and the stored-DP count (≈ √n/θ) both stay modest.
    let logw: u32 = (bits / 2).saturating_sub(4).clamp(2, 9);
    let w: usize = 1usize << logw;
    let dp_bits: u32 = ((bits / 2) as i64 - logw as i64 - 2).clamp(1, 28) as u32;

    // Jump table J_r = u_r·P + v_r·Q with known coefficients.
    let mut ju = [0u64; R];
    let mut jv = [0u64; R];
    let mut jtok: Vec<Tok> = Vec::with_capacity(R);
    for r in 0..R {
        let u = 1 + rng.below(n - 1);
        let v = 1 + rng.below(n - 1);
        let up = c.scalar_mul(&p, u as u128);
        let vq = c.scalar_mul(&q, v as u128);
        jtok.push(c.add(&up, &vq));
        ju[r] = u;
        jv[r] = v;
    }

    // Cheap independent starts: seed one random point, then derive the rest along
    // a spawn trail (one add each) instead of W full scalar multiplications.
    let mut walks: Vec<Walk> = Vec::with_capacity(w);
    {
        let a0 = rng.below(n);
        let b0 = rng.below(n);
        let ap = c.scalar_mul(&p, a0 as u128);
        let bq = c.scalar_mul(&q, b0 as u128);
        walks.push(Walk {
            tok: c.add(&ap, &bq),
            a: a0,
            b: b0,
        });
    }
    for i in 1..w {
        let r = i % R;
        let prev = walks[i - 1].clone();
        walks.push(Walk {
            tok: c.add(&prev.tok, &jtok[r]),
            a: field::add(prev.a, ju[r], n),
            b: field::add(prev.b, jv[r], n),
        });
    }
    // Spawn pointer continues the trail, for the (rare) cheap reset on a self-loop.
    let mut spawn = walks[w - 1].clone();

    // Distinguished points seen: token -> (a, b). A second arrival with different
    // coefficients gives a₁P+b₁Q = a₂P+b₂Q, which solves for k. Walks are NOT reset
    // on a fresh DP — they keep running, and the standard rho self-collision (a
    // trail re-entering its own path) shows up here as a different-coefficient hit.
    let mut seen: HashMap<Tok, (u64, u64)> = HashMap::new();

    let mut pairs: Vec<(Tok, Tok)> = Vec::with_capacity(w);
    let mut rs: Vec<usize> = Vec::with_capacity(w);
    loop {
        pairs.clear();
        rs.clear();
        for wk in &walks {
            let r = (fnv1a(&wk.tok) % R as u64) as usize;
            pairs.push((wk.tok, jtok[r]));
            rs.push(r);
        }
        let res = c.add_batch(&pairs);

        for i in 0..w {
            let r = rs[i];
            walks[i].tok = res[i];
            walks[i].a = field::add(walks[i].a, ju[r], n);
            walks[i].b = field::add(walks[i].b, jv[r], n);

            if is_dp(&walks[i].tok, dp_bits) {
                let key = walks[i].tok;
                let (a1, b1) = (walks[i].a, walks[i].b);
                if let Some(&(a2, b2)) = seen.get(&key) {
                    let db = field::sub(b2, b1, n);
                    if db != 0 {
                        let da = field::sub(a1, a2, n);
                        return field::mul(da, field::inv(db, n), n) as u128;
                    }
                    // Same coefficients: a degenerate self-loop. Reset this walk
                    // cheaply by advancing the spawn trail one step.
                    let jr = ((a1 ^ b1) as usize) % R;
                    spawn = Walk {
                        tok: c.add(&spawn.tok, &jtok[jr]),
                        a: field::add(spawn.a, ju[jr], n),
                        b: field::add(spawn.b, jv[jr], n),
                    };
                    walks[i] = spawn.clone();
                } else {
                    seen.insert(key, (a1, b1));
                }
            }
        }
    }
}
