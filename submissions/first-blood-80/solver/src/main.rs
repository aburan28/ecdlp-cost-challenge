//! Standalone Pollard-rho (negation map + distinguished points, multithreaded)
//! for prime-field ECDLP — the ECDLP-cost-challenge First-Blood (representation)
//! track. We have the real curve coordinates here, so this is NOT the generic
//! oracle; it's a direct fast attack on the published curve.
//!
//! Field: 128-bit Montgomery. Group: affine short Weierstrass, batch-inverted.
//!
//! Modes:
//!   rho solve  <p> <a> <b> <Gx> <Gy> <Qx> <Qy> <n> [dpbits] [threads]
//!   rho bench  <p> <a> <b> <Gx> <Gy> <n> [seconds] [threads]
//! All numbers are decimal (or 0x-hex).

use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

// --------------------------- 128x128 -> 256 multiply -------------------------
#[inline(always)]
fn mul_wide(a: u128, b: u128) -> (u128, u128) {
    let a0 = a as u64;
    let a1 = (a >> 64) as u64;
    let b0 = b as u64;
    let b1 = (b >> 64) as u64;
    let p00 = (a0 as u128) * (b0 as u128);
    let p01 = (a0 as u128) * (b1 as u128);
    let p10 = (a1 as u128) * (b0 as u128);
    let p11 = (a1 as u128) * (b1 as u128);
    let r0 = p00 as u64;
    let mut acc = (p00 >> 64) + (p01 & 0xffff_ffff_ffff_ffff) + (p10 & 0xffff_ffff_ffff_ffff);
    let r1 = acc as u64;
    acc = (acc >> 64) + (p01 >> 64) + (p10 >> 64) + (p11 & 0xffff_ffff_ffff_ffff);
    let r2 = acc as u64;
    acc = (acc >> 64) + (p11 >> 64);
    let r3 = acc as u64;
    ((r0 as u128) | ((r1 as u128) << 64), (r2 as u128) | ((r3 as u128) << 64))
}

// --------------------------- Montgomery field --------------------------------
#[derive(Clone, Copy)]
struct Fp {
    p: u128,
    np: u128, // -p^{-1} mod 2^128
    r1: u128, // R mod p  (Montgomery 1)
    r2: u128, // R^2 mod p
}
impl Fp {
    fn new(p: u128) -> Self {
        let mut inv: u128 = 1;
        for _ in 0..7 {
            inv = inv.wrapping_mul(2u128.wrapping_sub(p.wrapping_mul(inv)));
        }
        let r1 = (((1u128 << 127) % p) << 1) % p; // 2^128 mod p
        let r2 = mulmod_bits(r1, r1, p); // (R mod p)^2 mod p = R^2 mod p
        Fp { p, np: inv.wrapping_neg(), r1, r2 }
    }
    #[inline(always)]
    fn mont(&self, a: u128, b: u128) -> u128 {
        let (t_lo, t_hi) = mul_wide(a, b);
        let m = t_lo.wrapping_mul(self.np);
        let (mp_lo, mp_hi) = mul_wide(m, self.p);
        let (_s, carry1) = t_lo.overflowing_add(mp_lo);
        let s_hi = t_hi.wrapping_add(mp_hi).wrapping_add(carry1 as u128);
        if s_hi >= self.p {
            s_hi - self.p
        } else {
            s_hi
        }
    }
    #[inline(always)]
    fn add(&self, a: u128, b: u128) -> u128 {
        let s = a + b;
        if s >= self.p { s - self.p } else { s }
    }
    #[inline(always)]
    fn sub(&self, a: u128, b: u128) -> u128 {
        if a >= b { a - b } else { a + self.p - b }
    }
    #[inline(always)]
    fn neg(&self, a: u128) -> u128 {
        if a == 0 { 0 } else { self.p - a }
    }
    #[inline(always)]
    fn to_mont(&self, a: u128) -> u128 {
        self.mont(a % self.p, self.r2)
    }
    #[inline(always)]
    fn from_mont(&self, a: u128) -> u128 {
        self.mont(a, 1)
    }
    fn inv(&self, a: u128) -> u128 {
        self.pow(a, self.p - 2)
    }
    fn pow(&self, a: u128, mut e: u128) -> u128 {
        let mut r = self.r1;
        let mut b = a;
        while e > 0 {
            if e & 1 == 1 {
                r = self.mont(r, b);
            }
            b = self.mont(b, b);
            e >>= 1;
        }
        r
    }
}

/// a*b mod m (any odd/even m < 2^128) via 256-bit product, MSB-first reduce.
/// Slow; used only O(1) times (setup, final recovery).
fn mulmod_bits(a: u128, b: u128, m: u128) -> u128 {
    let (lo, hi) = mul_wide(a % m, b % m);
    let mut rem: u128 = 0;
    for i in (0..256).rev() {
        let bit = if i >= 128 { (hi >> (i - 128)) & 1 } else { (lo >> i) & 1 };
        let top = rem >> 127;
        rem = (rem << 1) | bit;
        if top == 1 || rem >= m {
            rem = rem.wrapping_sub(m);
        }
    }
    rem
}
fn mulmod_n(a: u128, b: u128, n: u128) -> u128 {
    mulmod_bits(a, b, n)
}
fn invmod_n(a: u128, n: u128) -> u128 {
    let mut r: u128 = 1 % n;
    let mut b = a % n;
    let mut e = n - 2;
    while e > 0 {
        if e & 1 == 1 {
            r = mulmod_n(r, b, n);
        }
        b = mulmod_n(b, b, n);
        e >>= 1;
    }
    r
}
#[inline(always)]
fn addmod_n(a: u128, b: u128, n: u128) -> u128 {
    let s = a + b;
    if s >= n { s - n } else { s }
}
#[inline(always)]
fn negmod_n(a: u128, n: u128) -> u128 {
    if a == 0 { 0 } else { n - a }
}

// --------------------------- curve (Montgomery coords) -----------------------
type Pt = Option<(u128, u128)>; // None = identity; coords in Montgomery domain
#[derive(Clone, Copy)]
struct Curve {
    fp: Fp,
    a: u128,
    b: u128,
}
impl Curve {
    fn add(&self, p1: &Pt, p2: &Pt) -> Pt {
        match (p1, p2) {
            (None, _) => *p2,
            (_, None) => *p1,
            (Some((x1, y1)), Some((x2, y2))) => {
                let f = &self.fp;
                if x1 == x2 {
                    if f.add(*y1, *y2) == 0 {
                        return None;
                    }
                    return self.double(p1);
                }
                let lam = f.mont(f.sub(*y2, *y1), f.inv(f.sub(*x2, *x1)));
                self.from_lambda(*x1, *y1, *x2, lam)
            }
        }
    }
    fn double(&self, p1: &Pt) -> Pt {
        match p1 {
            None => None,
            Some((x1, y1)) => {
                let f = &self.fp;
                if *y1 == 0 {
                    return None;
                }
                let three = f.to_mont(3);
                let two = f.to_mont(2);
                let num = f.add(f.mont(three, f.mont(*x1, *x1)), self.a);
                let lam = f.mont(num, f.inv(f.mont(two, *y1)));
                self.from_lambda(*x1, *y1, *x1, lam)
            }
        }
    }
    #[inline]
    fn from_lambda(&self, x1: u128, y1: u128, x2: u128, lam: u128) -> Pt {
        let f = &self.fp;
        let lam2 = f.mont(lam, lam);
        let x3 = f.sub(f.sub(lam2, x1), x2);
        let y3 = f.sub(f.mont(lam, f.sub(x1, x3)), y1);
        Some((x3, y3))
    }
    fn scalar_mul(&self, k: u128, p: &Pt) -> Pt {
        let mut r: Pt = None;
        let mut q = *p;
        let mut e = k;
        while e > 0 {
            if e & 1 == 1 {
                r = self.add(&r, &q);
            }
            q = self.double(&q);
            e >>= 1;
        }
        r
    }
    fn on_curve(&self, p: &Pt) -> bool {
        match p {
            None => true,
            Some((x, y)) => {
                let f = &self.fp;
                let lhs = f.mont(*y, *y);
                let x3 = f.mont(f.mont(*x, *x), *x);
                let rhs = f.add(f.add(x3, f.mont(self.a, *x)), self.b);
                lhs == rhs
            }
        }
    }
}

// --------------------------- prng -------------------------------------------
struct Sm(u64);
impl Sm {
    #[inline(always)]
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    fn below(&mut self, n: u128) -> u128 {
        let hi = self.next() as u128;
        let lo = self.next() as u128;
        ((hi << 64) | lo) % n
    }
}

// --------------------------- shared rho state --------------------------------
const R: usize = 1024; // partitions
const NSHARD: usize = 4096;

struct Jump {
    pt: (u128, u128), // Montgomery affine (jumps are never identity, w.h.p.)
    u: u128,
    v: u128,
}

struct Shared {
    curve: Curve,
    n: u128,
    g: (u128, u128),
    q: (u128, u128),
    jumps: Vec<Jump>,
    dp_mask: u128,
    table: Vec<Mutex<HashMap<(u128, u128), (u128, u128)>>>,
    found: AtomicBool,
    answer: Mutex<Option<u128>>,
    steps: AtomicU64,
}

#[inline(always)]
fn canon(fp: &Fp, x: u128, y: u128, a: u128, b: u128, n: u128) -> (u128, u128, u128, u128) {
    // Canonical class representative {(x,y),(x,-y)}: smaller Montgomery y.
    let ny = fp.neg(y);
    if ny < y {
        (x, ny, negmod_n(a, n), negmod_n(b, n))
    } else {
        (x, y, a, b)
    }
}

#[inline(always)]
fn part(x: u128) -> usize {
    (x as usize) & (R - 1)
}

fn worker(sh: Arc<Shared>, seed: u64, w: usize) {
    // PLAIN r-adding-walk rho (NO negation map): every step explores fresh
    // pseudo-random ground — there is no involution, hence no fruitless cycles.
    // Costs √2 more steps than a (correct) negation map but is fully robust.
    let fp = sh.curve.fp;
    let n = sh.n;
    let curve = sh.curve;
    let mut rng = Sm(seed);

    let mut px = vec![0u128; w];
    let mut py = vec![0u128; w];
    let mut pa = vec![0u128; w];
    let mut pb = vec![0u128; w];

    let g_pt: Pt = Some(sh.g);
    let q_pt: Pt = Some(sh.q);
    let respawn = |rng: &mut Sm| -> (u128, u128, u128, u128) {
        loop {
            let a0 = 1 + rng.below(n - 1);
            let b0 = 1 + rng.below(n - 1);
            let ag = curve.scalar_mul(a0, &g_pt);
            let bq = curve.scalar_mul(b0, &q_pt);
            if let Some((x, y)) = curve.add(&ag, &bq) {
                return (x, y, a0, b0);
            }
        }
    };
    for i in 0..w {
        let (x, y, a, b) = respawn(&mut rng);
        px[i] = x; py[i] = y; pa[i] = a; pb[i] = b;
    }

    let mut den = vec![0u128; w];
    let mut pref = vec![0u128; w];
    let mut inv = vec![0u128; w];
    let mut rr = vec![0usize; w];
    let mut local_steps: u64 = 0;

    while !sh.found.load(Ordering::Relaxed) {
        // 1) denominators (x_jr - x_i); respawn the (vanishingly rare) x-collisions
        for i in 0..w {
            let mut r = part(px[i]);
            let mut d = fp.sub(sh.jumps[r].pt.0, px[i]);
            while d == 0 {
                let (x, y, a, b) = respawn(&mut rng);
                px[i] = x; py[i] = y; pa[i] = a; pb[i] = b;
                r = part(px[i]);
                d = fp.sub(sh.jumps[r].pt.0, px[i]);
            }
            rr[i] = r;
            den[i] = d;
        }
        // 2) batch invert (Montgomery's trick): 1 inversion for all W
        let mut acc = fp.r1;
        for i in 0..w {
            pref[i] = acc;
            acc = fp.mont(acc, den[i]);
        }
        let mut accinv = fp.inv(acc);
        for i in (0..w).rev() {
            inv[i] = fp.mont(accinv, pref[i]);
            accinv = fp.mont(accinv, den[i]);
        }
        // 3) finish each add + DP check
        for i in 0..w {
            let r = rr[i];
            let jx = sh.jumps[r].pt.0;
            let jy = sh.jumps[r].pt.1;
            let lam = fp.mont(fp.sub(jy, py[i]), inv[i]);
            let lam2 = fp.mont(lam, lam);
            let nx = fp.sub(fp.sub(lam2, px[i]), jx);
            let ny = fp.sub(fp.mont(lam, fp.sub(px[i], nx)), py[i]);
            let na = addmod_n(pa[i], sh.jumps[r].u, n);
            let nb = addmod_n(pb[i], sh.jumps[r].v, n);
            px[i] = nx; py[i] = ny; pa[i] = na; pb[i] = nb;

            if nx & sh.dp_mask == 0 {
                let shard = (nx as usize) & (NSHARD - 1);
                let mut t = sh.table[shard].lock().unwrap();
                if let Some(&(a2, b2)) = t.get(&(nx, ny)) {
                    let dbb = if b2 >= nb { b2 - nb } else { b2 + n - nb };
                    if dbb != 0 {
                        let daa = if na >= a2 { na - a2 } else { na + n - a2 };
                        let k = mulmod_n(daa, invmod_n(dbb, n), n);
                        if curve.scalar_mul(k, &g_pt) == q_pt {
                            *sh.answer.lock().unwrap() = Some(k);
                            sh.found.store(true, Ordering::Relaxed);
                            return;
                        }
                    }
                } else {
                    t.insert((nx, ny), (na, nb));
                }
            }
        }
        local_steps += w as u64;
        if local_steps >= (1 << 20) {
            sh.steps.fetch_add(local_steps, Ordering::Relaxed);
            local_steps = 0;
        }
    }
    sh.steps.fetch_add(local_steps, Ordering::Relaxed);
}

fn build_shared(curve: Curve, n: u128, g: (u128, u128), q: (u128, u128), dpbits: u32) -> Shared {
    let fp = curve.fp;
    let mut rng = Sm(0xA5A5_1234_5678_9ABC);
    let g_pt: Pt = Some(g);
    let q_pt: Pt = Some(q);
    let mut jumps = Vec::with_capacity(R);
    for _ in 0..R {
        let u = 1 + rng.below(n - 1);
        let v = 1 + rng.below(n - 1);
        let ug = curve.scalar_mul(u, &g_pt);
        let vq = curve.scalar_mul(v, &q_pt);
        let jp = curve.add(&ug, &vq).expect("jump not identity");
        // canonicalize jump point too? No — jumps are added to canonical points;
        // they need not be canonical. Keep raw.
        jumps.push(Jump { pt: jp, u, v });
    }
    let mut table = Vec::with_capacity(NSHARD);
    for _ in 0..NSHARD {
        table.push(Mutex::new(HashMap::new()));
    }
    Shared {
        curve,
        n,
        g,
        q,
        jumps,
        dp_mask: (1u128 << dpbits) - 1,
        table,
        found: AtomicBool::new(false),
        answer: Mutex::new(None),
        steps: AtomicU64::new(0),
    }
}

// --------------------------- checkpoint (DP table) ---------------------------
fn w16(buf: &mut Vec<u8>, v: u128) {
    buf.extend_from_slice(&v.to_le_bytes());
}
fn r16(b: &[u8], o: usize) -> u128 {
    u128::from_le_bytes(b[o..o + 16].try_into().unwrap())
}
/// Atomically write all DP entries to `path` (count:u64 then 4×u128 each).
fn save_ckpt(sh: &Shared, path: &str) {
    let mut buf: Vec<u8> = Vec::new();
    buf.extend_from_slice(&0u64.to_le_bytes()); // count placeholder
    let mut count: u64 = 0;
    for shard in sh.table.iter() {
        let g = shard.lock().unwrap();
        for (&(cx, cy), &(ca, cb)) in g.iter() {
            w16(&mut buf, cx);
            w16(&mut buf, cy);
            w16(&mut buf, ca);
            w16(&mut buf, cb);
            count += 1;
        }
    }
    buf[0..8].copy_from_slice(&count.to_le_bytes());
    let tmp = format!("{}.tmp", path);
    if let Ok(mut f) = std::fs::File::create(&tmp) {
        if f.write_all(&buf).is_ok() {
            let _ = std::fs::rename(&tmp, path);
        }
    }
}
fn load_ckpt(sh: &Shared, path: &str) -> u64 {
    let mut f = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return 0,
    };
    let mut b = Vec::new();
    if f.read_to_end(&mut b).is_err() || b.len() < 8 {
        return 0;
    }
    let count = u64::from_le_bytes(b[0..8].try_into().unwrap());
    let mut o = 8usize;
    for _ in 0..count {
        if o + 64 > b.len() {
            break;
        }
        let cx = r16(&b, o);
        let cy = r16(&b, o + 16);
        let ca = r16(&b, o + 32);
        let cb = r16(&b, o + 48);
        o += 64;
        let shard = (cx as usize) & (NSHARD - 1);
        sh.table[shard].lock().unwrap().insert((cx, cy), (ca, cb));
    }
    count
}

// --------------------------- parsing / setup ---------------------------------
fn parse(s: &str) -> u128 {
    let s = s.trim();
    if let Some(h) = s.strip_prefix("0x") {
        u128::from_str_radix(h, 16).expect("hex")
    } else {
        s.parse().expect("dec")
    }
}

/// Build a Curve + Montgomery G,Q from plain-integer params.
fn setup(p: u128, a: u128, b: u128, gx: u128, gy: u128, qx: u128, qy: u128) -> (Curve, (u128, u128), (u128, u128)) {
    let fp = Fp::new(p);
    let curve = Curve { fp, a: fp.to_mont(a), b: fp.to_mont(b) };
    let g = (fp.to_mont(gx), fp.to_mont(gy));
    let q = (fp.to_mont(qx), fp.to_mont(qy));
    (curve, g, q)
}

fn isqrt(n: u128) -> u128 {
    if n < 2 {
        return n;
    }
    let mut x = (n as f64).sqrt() as u128;
    while x.saturating_mul(x) > n {
        x -= 1;
    }
    while (x + 1).saturating_mul(x + 1) <= n {
        x += 1;
    }
    x
}

fn run(sh: Arc<Shared>, threads: usize, w: usize) {
    let mut handles = vec![];
    for t in 0..threads {
        let sh2 = sh.clone();
        let seed = 0x1000_0000u64
            .wrapping_mul(t as u64 + 1)
            .wrapping_add(0xDEAD_BEEF_CAFE_0000 ^ (t as u64));
        handles.push(std::thread::spawn(move || worker(sh2, seed, w)));
    }
    for h in handles {
        h.join().ok();
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: rho solve|bench ...");
        std::process::exit(2);
    }
    let ncpu = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    match args[1].as_str() {
        "solve" => {
            // p a b Gx Gy Qx Qy n [dpbits] [threads]
            let p = parse(&args[2]);
            let a = parse(&args[3]);
            let b = parse(&args[4]);
            let gx = parse(&args[5]);
            let gy = parse(&args[6]);
            let qx = parse(&args[7]);
            let qy = parse(&args[8]);
            let n = parse(&args[9]);
            let dpbits: u32 = args.get(10).map(|s| s.parse().unwrap()).unwrap_or_else(|| {
                // aim ~ a few million DPs: dp ≈ log2(sqrt(n)) - 22
                let sn = isqrt(n) as f64;
                ((sn.log2() - 21.0).max(1.0)) as u32
            });
            let threads = args.get(11).map(|s| s.parse().unwrap()).unwrap_or(ncpu);
            let (curve, g, q) = setup(p, a, b, gx, gy, qx, qy);
            assert!(curve.on_curve(&Some(g)), "G not on curve");
            assert!(curve.on_curve(&Some(q)), "Q not on curve");
            let w = 512usize;
            let sh = Arc::new(build_shared(curve, n, g, q, dpbits));
            let ckpt = std::env::var("CKPT").unwrap_or_default();
            if !ckpt.is_empty() {
                let loaded = load_ckpt(&sh, &ckpt);
                if loaded > 0 {
                    eprintln!("[rho] resumed: loaded {} DPs from {}", loaded, ckpt);
                }
            }
            eprintln!(
                "[rho] solve  threads={} W={} dpbits={}  sqrt(n)~2^{:.1}  expected~{:.2e} steps",
                threads,
                w,
                dpbits,
                (isqrt(n) as f64).log2(),
                1.2533 * isqrt(n) as f64
            );
            let sh_mon = sh.clone();
            let ckpt_mon = ckpt.clone();
            let t0 = Instant::now();
            let mon = std::thread::spawn(move || {
                let mut last_ckpt = Instant::now();
                while !sh_mon.found.load(Ordering::Relaxed) {
                    std::thread::sleep(Duration::from_secs(15));
                    let s = sh_mon.steps.load(Ordering::Relaxed);
                    let el = t0.elapsed().as_secs_f64();
                    let dps: usize = sh_mon.table.iter().map(|m| m.lock().unwrap().len()).sum();
                    let expected = 1.2533 * isqrt(sh_mon.n) as f64;
                    eprintln!(
                        "[rho] {:.0}s  steps={:.3e} ({:.1}%)  {:.1}M/s  DPs={}",
                        el,
                        s as f64,
                        100.0 * s as f64 / expected,
                        s as f64 / el / 1e6,
                        dps
                    );
                    if !ckpt_mon.is_empty() && last_ckpt.elapsed().as_secs() >= 300 {
                        save_ckpt(&sh_mon, &ckpt_mon);
                        last_ckpt = Instant::now();
                        eprintln!("[rho] checkpoint saved ({} DPs)", dps);
                    }
                }
            });
            run(sh.clone(), threads, w);
            let _ = mon.join();
            let k = sh.answer.lock().unwrap().expect("no answer");
            let el = t0.elapsed().as_secs_f64();
            eprintln!("[rho] SOLVED in {:.1}s, steps={}", el, sh.steps.load(Ordering::Relaxed));
            println!("k = {}", k);
        }
        "bench" => {
            // p a b Gx Gy n [seconds] [threads]   (Q := G for bench)
            let p = parse(&args[2]);
            let a = parse(&args[3]);
            let b = parse(&args[4]);
            let gx = parse(&args[5]);
            let gy = parse(&args[6]);
            let n = parse(&args[7]);
            let secs: u64 = args.get(8).map(|s| s.parse().unwrap()).unwrap_or(8);
            let threads = args.get(9).map(|s| s.parse().unwrap()).unwrap_or(ncpu);
            let (curve, g, _q) = setup(p, a, b, gx, gy, gx, gy);
            let w = 512usize;
            // dp_mask huge so we never "find"; just walk.
            let sh = Arc::new(build_shared(curve, n, g, g, 100));
            let t0 = Instant::now();
            let mut handles = vec![];
            for t in 0..threads {
                let sh2 = sh.clone();
                handles.push(std::thread::spawn(move || worker(sh2, 0x55 ^ t as u64 + 1, w)));
            }
            std::thread::sleep(Duration::from_secs(secs));
            sh.found.store(true, Ordering::Relaxed);
            for h in handles {
                h.join().ok();
            }
            let s = sh.steps.load(Ordering::Relaxed);
            let el = t0.elapsed().as_secs_f64();
            eprintln!(
                "[bench] threads={} steps={} {:.2}M steps/s over {:.1}s",
                threads,
                s,
                s as f64 / el / 1e6,
                el
            );
        }
        _ => {
            eprintln!("unknown mode");
            std::process::exit(2);
        }
    }
}
