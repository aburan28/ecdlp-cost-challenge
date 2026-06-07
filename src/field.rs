//! TRUSTED. Prime field F_p for p < 2^62 (so products fit in u128).
//!
//! Plain schoolbook modular arithmetic — no Montgomery form. At the op counts
//! this challenge reaches (a few × 10^7 group ops at most), affine EC arithmetic
//! with a Fermat inverse per addition is entirely adequate and keeps the trusted
//! code small and obviously correct.

#[inline]
pub fn add(a: u64, b: u64, p: u64) -> u64 {
    let s = a as u128 + b as u128;
    let pp = p as u128;
    (if s >= pp { s - pp } else { s }) as u64
}

#[inline]
pub fn sub(a: u64, b: u64, p: u64) -> u64 {
    if a >= b {
        a - b
    } else {
        p - (b - a)
    }
}

#[inline]
pub fn mul(a: u64, b: u64, p: u64) -> u64 {
    ((a as u128 * b as u128) % p as u128) as u64
}

#[inline]
pub fn neg(a: u64, p: u64) -> u64 {
    if a == 0 {
        0
    } else {
        p - a
    }
}

/// a^e mod p by square-and-multiply.
pub fn pow(a: u64, e: u64, p: u64) -> u64 {
    let mut base = a % p;
    let mut exp = e;
    let mut acc: u64 = 1;
    while exp > 0 {
        if exp & 1 == 1 {
            acc = mul(acc, base, p);
        }
        base = mul(base, base, p);
        exp >>= 1;
    }
    acc
}

/// Modular inverse via Fermat: a^(p-2) mod p. `a` must be nonzero mod p.
pub fn inv(a: u64, p: u64) -> u64 {
    pow(a, p - 2, p)
}

/// Legendre symbol test: is `a` a nonzero quadratic residue mod p?
pub fn is_qr(a: u64, p: u64) -> bool {
    if a % p == 0 {
        return false;
    }
    pow(a, (p - 1) / 2, p) == 1
}

/// Square root mod p for p ≡ 3 (mod 4): sqrt = a^((p+1)/4). Caller guarantees
/// `a` is a QR and p ≡ 3 (mod 4) (the instance generator enforces the latter).
pub fn sqrt_3mod4(a: u64, p: u64) -> u64 {
    pow(a, (p + 1) / 4, p)
}
