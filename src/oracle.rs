//! TRUSTED. The executable generic-group oracle and its **binary** wire protocol.
//!
//! The oracle owns the real curve and the secret k. The solver is given only
//! opaque, per-run-random 128-bit tokens for P, Q and O, plus a counted
//! add/neg/scalar_mul oracle (with a batched add for parallel walks). Because
//! tokens are unguessable, the solver can only ever name group elements it
//! reached through counted operations — it cannot fabricate a token to dodge the
//! meter. This is Shoup's generic group model, made executable; the group
//! operation count is the score.
//!
//! ENCODING. A group element (a curve point) is encoded by a **keyed
//! permutation** (an 8-round Feistel cipher keyed per run): token = Feistel_key(
//! encode(point)). This is a stateless bijection, so equal points always yield
//! equal tokens (collision detection works) and distinct points distinct tokens,
//! with O(1) oracle memory at any tier. It is exactly the GGM's random-encoding
//! oracle, and being fresh per run it is the "you can't replay a table" property.
//!
//! Binary protocol (little-endian). Handshake (oracle → solver), 60 bytes:
//!     n:u64  bits:u32  tok_P:[16]  tok_Q:[16]  tok_O:[16]
//! Then request/response, one opcode byte + payload:
//!     0x01 ADD       tokA[16] tokB[16]                 -> tok[16]      (+1 op)
//!     0x02 NEG       tok[16]                           -> tok[16]      (FREE)
//!     0x03 SMUL      tok[16] scalar:u128[16]           -> tok[16]      (+#dbl+#add)
//!     0x04 ISID      tok[16]                           -> u8           (free)
//!     0x05 SUBMIT    k:u128[16]                        -> u8 + count:u64 (terminal)
//!     0x06 ADDBATCH  count:u32 then count*(tokA[16] tokB[16]) -> count*tok[16]  (+count ops)
//!     0x07 NEGBATCH  count:u32 then count*tok[16]      -> count*tok[16] (FREE)
//!
//! NEGATION IS FREE. On an elliptic curve −P = (x, −y), so negation is the one
//! involution the representation hands you for nothing. Counting it would cancel
//! the standard √2 negation-map speedup, so we model it as free — exactly as
//! optimized EC rho does. The consequence: the generic floor on the *expected*
//! score drops from √n to √(n/2) (you search n/2 classes {±P}); the rho reference
//! stays √(πn/2) (basic rho, no negation map), and the negation map targets
//! √(πn/4) ≈ 0.886·√n.

use crate::curve::Point;
use crate::instance::Instance;
use crate::rng::SplitMix64;
use std::io::{self, Read, Write};

pub type Tok = [u8; 16];

const ROUNDS: usize = 8;
/// Reserved 128-bit block for the identity. A real point has x < p < 2^60, so its
/// high 64 bits are < 2^60 and never all-ones — no collision with this sentinel.
const INF_BLOCK: u128 = u128::MAX;

#[inline]
fn mix(y0: u64) -> u64 {
    let mut y = y0;
    y = (y ^ (y >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    y = (y ^ (y >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    y ^ (y >> 31)
}

pub struct Oracle {
    inst: Instance,
    rk: [u64; ROUNDS],
    pub count: u64,
    pub finished: bool,
    pub solved: bool,
    pub submitted_k: Option<u128>,
}

impl Oracle {
    pub fn new(inst: Instance, token_seed: u64) -> Self {
        let mut g = SplitMix64::new(token_seed);
        let mut rk = [0u64; ROUNDS];
        for k in rk.iter_mut() {
            *k = g.next_u64();
        }
        Oracle {
            inst,
            rk,
            count: 0,
            finished: false,
            solved: false,
            submitted_k: None,
        }
    }

    pub fn order(&self) -> u64 {
        self.inst.n
    }
    pub fn bits(&self) -> u32 {
        self.inst.bits
    }
    /// Pollard-rho reference: E[#ops] ≈ √(πn/2) ≈ 1.2533·√n.
    pub fn rho_reference(&self) -> u64 {
        (1.2533141373155003_f64 * (self.inst.n as f64).sqrt()).round() as u64
    }

    fn encrypt(&self, block: u128) -> u128 {
        let mut l = (block >> 64) as u64;
        let mut r = block as u64;
        for i in 0..ROUNDS {
            let t = l ^ mix(r ^ self.rk[i]);
            l = r;
            r = t;
        }
        ((l as u128) << 64) | r as u128
    }

    fn decrypt(&self, block: u128) -> u128 {
        let mut l = (block >> 64) as u64;
        let mut r = block as u64;
        for i in (0..ROUNDS).rev() {
            let prev_r = l;
            let prev_l = r ^ mix(l ^ self.rk[i]);
            l = prev_l;
            r = prev_r;
        }
        ((l as u128) << 64) | r as u128
    }

    fn mint(&self, pt: Point) -> Tok {
        let block = if pt.inf {
            INF_BLOCK
        } else {
            ((pt.x as u128) << 64) | pt.y as u128
        };
        self.encrypt(block).to_le_bytes()
    }

    fn resolve(&self, t: &Tok) -> Point {
        let block = self.decrypt(u128::from_le_bytes(*t));
        if block == INF_BLOCK {
            return Point::infinity();
        }
        let x = (block >> 64) as u64;
        let y = block as u64;
        let pt = Point::affine(x, y);
        // A forged/garbage token decrypts to an off-curve point: treat as identity.
        // No advantage to the solver, and it keeps arithmetic well-defined.
        if x < self.inst.curve.p && y < self.inst.curve.p && self.inst.curve.on_curve(&pt) {
            pt
        } else {
            Point::infinity()
        }
    }

    fn header(&self) -> Vec<u8> {
        let mut v = Vec::with_capacity(60);
        v.extend_from_slice(&self.inst.n.to_le_bytes());
        v.extend_from_slice(&self.inst.bits.to_le_bytes());
        v.extend_from_slice(&self.mint(self.inst.gen));
        v.extend_from_slice(&self.mint(self.inst.target));
        v.extend_from_slice(&self.mint(Point::infinity()));
        v
    }

    /// Serve the whole session: handshake, then process requests until SUBMIT/EOF.
    pub fn serve<R: Read, W: Write>(&mut self, mut r: R, mut w: W) -> io::Result<()> {
        w.write_all(&self.header())?;
        w.flush()?;

        let mut op = [0u8; 1];
        let mut a = [0u8; 16];
        let mut b = [0u8; 16];
        loop {
            if r.read_exact(&mut op).is_err() {
                break; // EOF: solver exited without SUBMIT
            }
            match op[0] {
                0x01 => {
                    r.read_exact(&mut a)?;
                    r.read_exact(&mut b)?;
                    let res = self.inst.curve.add(&self.resolve(&a), &self.resolve(&b));
                    self.count += 1;
                    w.write_all(&self.mint(res))?;
                }
                0x02 => {
                    // Negation is FREE (−P = (x, −y)); see the module header.
                    r.read_exact(&mut a)?;
                    let res = self.inst.curve.neg(&self.resolve(&a));
                    w.write_all(&self.mint(res))?;
                }
                0x03 => {
                    r.read_exact(&mut a)?;
                    let mut sc = [0u8; 16];
                    r.read_exact(&mut sc)?;
                    let scalar = (u128::from_le_bytes(sc) % self.inst.n as u128) as u64;
                    let (res, ops) = self.inst.curve.scalar_mul(scalar, &self.resolve(&a));
                    self.count += ops;
                    w.write_all(&self.mint(res))?;
                }
                0x04 => {
                    r.read_exact(&mut a)?;
                    let id = if self.resolve(&a).inf { 1u8 } else { 0u8 };
                    w.write_all(&[id])?;
                }
                0x05 => {
                    let mut kb = [0u8; 16];
                    r.read_exact(&mut kb)?;
                    let kv = u128::from_le_bytes(kb);
                    self.submitted_k = Some(kv);
                    let kk = (kv % self.inst.n as u128) as u64;
                    let (cand, _) = self.inst.curve.scalar_mul(kk, &self.inst.gen);
                    self.solved = cand == self.inst.target;
                    self.finished = true;
                    w.write_all(&[self.solved as u8])?;
                    w.write_all(&self.count.to_le_bytes())?;
                    w.flush()?;
                    break;
                }
                0x06 => {
                    let mut cb = [0u8; 4];
                    r.read_exact(&mut cb)?;
                    let count = u32::from_le_bytes(cb) as usize;
                    let mut out = Vec::with_capacity(count * 16);
                    for _ in 0..count {
                        r.read_exact(&mut a)?;
                        r.read_exact(&mut b)?;
                        let res = self.inst.curve.add(&self.resolve(&a), &self.resolve(&b));
                        self.count += 1;
                        out.extend_from_slice(&self.mint(res));
                    }
                    w.write_all(&out)?;
                }
                0x07 => {
                    // Batched negation, FREE — lets the negation-map solver
                    // canonicalize all its parallel walks in one round trip.
                    let mut cb = [0u8; 4];
                    r.read_exact(&mut cb)?;
                    let count = u32::from_le_bytes(cb) as usize;
                    let mut out = Vec::with_capacity(count * 16);
                    for _ in 0..count {
                        r.read_exact(&mut a)?;
                        let res = self.inst.curve.neg(&self.resolve(&a));
                        out.extend_from_slice(&self.mint(res));
                    }
                    w.write_all(&out)?;
                }
                _ => break,
            }
            w.flush()?;
            if self.finished {
                break;
            }
        }
        Ok(())
    }
}

/// Helper exposed for tests: does `k` solve the instance?
pub fn verifies(inst: &Instance, k: u128) -> bool {
    let kk = (k % inst.n as u128) as u64;
    let (cand, _) = inst.curve.scalar_mul(kk, &inst.gen);
    cand == inst.target
}
