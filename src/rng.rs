//! TRUSTED. Tiny deterministic PRNG + a fast non-cryptographic hash.
//!
//! `SplitMix64` makes the whole instance a pure function of a 64-bit seed, so a
//! run is perfectly reproducible from `$ECDLP_SEED`. The hash is used (a) by the
//! oracle to mint per-run-random tokens and (b) by the baseline solver's r-adding
//! walk. Neither needs to be cryptographic — tokens get their unpredictability
//! from a fresh random key per run, not from the hash's strength.

/// SplitMix64 — Steele/Lea/Vigna. One 64-bit state, excellent statistical quality
/// for our purposes, trivial to audit.
#[derive(Clone)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        SplitMix64 { state: seed }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform-ish in `[0, bound)` (bound > 0). Modulo bias is negligible at our sizes.
    pub fn below(&mut self, bound: u64) -> u64 {
        self.next_u64() % bound
    }

    /// 16 random bytes, used to mint a token.
    pub fn token(&mut self) -> [u8; 16] {
        let a = self.next_u64().to_le_bytes();
        let b = self.next_u64().to_le_bytes();
        let mut out = [0u8; 16];
        out[..8].copy_from_slice(&a);
        out[8..].copy_from_slice(&b);
        out
    }
}

/// FNV-1a over a byte slice → 64 bits. Used to assign a walk a partition index.
pub fn fnv1a(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for &byte in bytes {
        h ^= byte as u64;
        h = h.wrapping_mul(0x0000_0100_0000_01B3);
    }
    h
}
