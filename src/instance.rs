//! TRUSTED. Deterministic generation of a *verified-generic* prime-field ECDLP
//! instance from a 64-bit seed.
//!
//! "Generic" = we actively rule out the structures that would make the instance
//! easier than a random prime-order curve:
//!   * prime group order n           (no Pohlig–Hellman / subgroup descent),
//!   * n != p                        (not anomalous — blocks Smart/SSSA),
//!   * large MOV embedding degree    (blocks MOV/Frey–Rück pairing transfer),
//!   * j-invariant not 0 or 1728     (no extra automorphisms / tiny-disc CM).
//!
//! Exact point counting at these sizes is cheap: the group order is the unique
//! value in the Hasse interval [p+1-2√p, p+1+2√p] that annihilates a random
//! point, found by baby-step/giant-step in O(p^{1/4}) group operations. We only
//! *accept* a curve when that value is prime (see `find_order` for why a prime
//! annihilator in the interval is necessarily the full group order).

use crate::curve::{Curve, Point};
use crate::field;
use crate::rng::SplitMix64;
use std::collections::HashMap;

#[derive(Clone)]
pub struct Instance {
    pub seed: u64,
    pub bits: u32,
    pub curve: Curve,
    pub n: u64,       // prime group order
    pub gen: Point,   // P, a generator (any non-identity point: order is prime)
    pub target: Point, // Q = k*P
    pub k: u64,       // the secret discrete log (oracle-only; never published)
}

/// Integer square root of a u128.
pub fn isqrt(n: u128) -> u128 {
    if n < 2 {
        return n;
    }
    let mut x = (n as f64).sqrt() as u128;
    // Newton tidy-up in case of float rounding.
    while x.saturating_mul(x) > n {
        x -= 1;
    }
    while (x + 1).saturating_mul(x + 1) <= n {
        x += 1;
    }
    x
}

/// Deterministic Miller–Rabin, exact for all n < 2^64.
pub fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    for &small in &[2u64, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37] {
        if n == small {
            return true;
        }
        if n % small == 0 {
            return false;
        }
    }
    let mut d = n - 1;
    let mut r = 0u32;
    while d & 1 == 0 {
        d >>= 1;
        r += 1;
    }
    'witness: for &a in &[2u64, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37] {
        let mut x = field::pow(a % n, d, n);
        if x == 1 || x == n - 1 {
            continue;
        }
        for _ in 0..r - 1 {
            x = field::mul(x, x, n);
            if x == n - 1 {
                continue 'witness;
            }
        }
        return false;
    }
    true
}

/// Smallest prime p with exactly `bits` bits and p ≡ 3 (mod 4), at or above the
/// seed-derived starting candidate. p ≡ 3 (mod 4) lets us take square roots with
/// a single exponentiation (`field::sqrt_3mod4`).
fn prime_3mod4(rng: &mut SplitMix64, bits: u32) -> u64 {
    let low = 1u64 << (bits - 1);
    let span = low; // [2^(bits-1), 2^bits)
    let mut cand = low | (rng.next_u64() % span);
    cand |= 3; // force ≡ 3 (mod 4)
    loop {
        if cand >> (bits - 1) != 1 {
            // wrapped past 2^bits — restart inside the band
            cand = low | 3;
        }
        if is_prime(cand) {
            return cand;
        }
        cand = cand.wrapping_add(4);
    }
}

/// MOV/Frey–Rück guard: reject if the embedding degree is small, i.e. n | p^i - 1
/// for some small i.
fn embedding_degree_ok(p: u64, n: u64) -> bool {
    let mut acc = p % n;
    for _ in 1..=200u32 {
        if acc == 1 {
            return false;
        }
        acc = field::mul(acc, p, n);
    }
    true
}

/// Find the group order of `curve` as the unique Hasse-interval value annihilating
/// `r`, via BSGS. Returns `Some(m)` where `m*r = O`; the caller checks `m` prime.
///
/// Soundness of the "prime ⇒ it's the order" shortcut: if the returned `m` is
/// prime and lies in [p+1-2√p, p+1+2√p] and `m*r = O`, then ord(r) | m so
/// ord(r) ∈ {1, m}; r != O gives ord(r) = m, so m | #E. The only multiple of a
/// prime m > √p inside an interval of width 4√p is m itself, hence #E = m.
fn find_order(curve: &Curve, r: &Point) -> Option<u64> {
    let p = curve.p;
    let w = 2 * isqrt(p as u128) as u64; // ≈ 2√p (Hasse half-width)
    let lo = p + 1 - w;
    let m_steps = 2 * w; // search i ∈ [0, m_steps], order = lo + i

    let (base, _) = curve.scalar_mul(lo, r); // lo * R
    let target = curve.neg(&base); // want i*R = -base

    let s = isqrt(m_steps as u128 + 1) as u64 + 1; // baby block size
    let mut table: HashMap<Point, u64> = HashMap::with_capacity(s as usize + 1);
    let mut jp = Point::infinity();
    for j in 0..s {
        table.entry(jp).or_insert(j);
        jp = curve.add(&jp, r);
    }
    let (sr, _) = curve.scalar_mul(s, r); // s * R
    let neg_sr = curve.neg(&sr);

    let mut cur = target; // cur = target - g*sR
    let mut g: u64 = 0;
    while g * s <= m_steps {
        if let Some(&j) = table.get(&cur) {
            let i = g * s + j;
            if i <= m_steps {
                return Some(lo + i);
            }
        }
        g += 1;
        cur = curve.add(&cur, &neg_sr);
    }
    None
}

/// Try to mint one verified-generic instance from `rng`. Returns `None` if this
/// particular (curve, point) draw is rejected; the caller loops.
fn try_instance(rng: &mut SplitMix64, bits: u32, p: u64) -> Option<Instance> {
    let a = rng.next_u64() % p;
    let b = rng.next_u64() % p;
    if a == 0 || b == 0 {
        return None; // j ∈ {0, 1728}: extra automorphisms — exclude
    }
    let curve = Curve::new(p, a, b);
    if !curve.is_nonsingular() {
        return None;
    }

    // Find a point R on the curve.
    let mut r = None;
    for _ in 0..64 {
        let x = rng.next_u64() % p;
        let x2 = field::mul(x, x, p);
        let x3 = field::mul(x2, x, p);
        let rhs = field::add(field::add(x3, field::mul(a, x, p), p), b, p);
        if rhs == 0 {
            continue;
        }
        if field::is_qr(rhs, p) {
            let y = field::sqrt_3mod4(rhs, p);
            r = Some(Point::affine(x, y));
            break;
        }
    }
    let r = r?;
    debug_assert!(curve.on_curve(&r));

    let n = find_order(&curve, &r)?;
    // Re-verify and apply genericity guards.
    let (chk, _) = curve.scalar_mul(n, &r);
    if !chk.inf {
        return None;
    }
    if !is_prime(n) {
        return None;
    }
    if n == p {
        return None; // anomalous
    }
    if !embedding_degree_ok(p, n) {
        return None;
    }

    // Generator P = R (prime order ⇒ any non-identity point generates).
    let gen = r;
    let k = 1 + rng.next_u64() % (n - 1);
    let (target, _) = curve.scalar_mul(k, &gen);

    Some(Instance {
        seed: 0, // filled by caller
        bits,
        curve,
        n,
        gen,
        target,
        k,
    })
}

/// Generate the instance for `(seed, bits)`. Deterministic: same inputs ⇒ same
/// instance (including the secret k). `bits` is the bit-length of p (≈ n).
pub fn generate(seed: u64, bits: u32) -> Instance {
    assert!((20..=60).contains(&bits), "bits must be in [20, 60]");
    let mut rng = SplitMix64::new(seed ^ 0xA5A5_5A5A_DEAD_BEEF);
    let p = prime_3mod4(&mut rng, bits);
    for _ in 0..100_000 {
        if let Some(mut inst) = try_instance(&mut rng, bits, p) {
            inst.seed = seed;
            return inst;
        }
    }
    panic!("instance generation failed for seed={seed} bits={bits} (should be unreachable)");
}

/// Public descriptor (NO secret k) as JSON, for the representation-attack track.
pub fn public_json(inst: &Instance) -> String {
    let c = &inst.curve;
    format!(
        concat!(
            "{{\n",
            "  \"name\": \"generic-prime-field-ecdlp\",\n",
            "  \"encoding\": \"affine-weierstrass\",\n",
            "  \"bits\": {bits},\n",
            "  \"seed\": {seed},\n",
            "  \"p\": {p},\n",
            "  \"a\": {a},\n",
            "  \"b\": {b},\n",
            "  \"n\": {n},\n",
            "  \"Gx\": {gx},\n",
            "  \"Gy\": {gy},\n",
            "  \"Qx\": {qx},\n",
            "  \"Qy\": {qy},\n",
            "  \"note\": \"y^2 = x^3 + a*x + b over F_p; n is the prime group order; ",
            "Q = k*G with k secret. Coordinates are published only for the unscored ",
            "representation-attack research track; the scored arena hides them.\"\n",
            "}}\n"
        ),
        bits = inst.bits,
        seed = inst.seed,
        p = c.p,
        a = c.a,
        b = c.b,
        n = inst.n,
        gx = inst.gen.x,
        gy = inst.gen.y,
        qx = inst.target.x,
        qy = inst.target.y,
    )
}
