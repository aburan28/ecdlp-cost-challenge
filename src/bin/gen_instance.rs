//! TRUSTED. Print the *public* descriptor (no secret k) for a (seed, bits)
//! instance. Used to materialise `instance.public.json` for a fresh official run
//! and for the representation-attack research track.
//!
//! Usage: gen_instance [seed] [bits]

use ecdlp_challenge::instance;

fn main() {
    let mut args = std::env::args().skip(1);
    let seed: u64 = args
        .next()
        .and_then(|s| parse_u64(&s))
        .unwrap_or(0x1234_5678);
    let bits: u32 = args.next().and_then(|s| s.parse().ok()).unwrap_or(40);
    let inst = instance::generate(seed, bits);
    print!("{}", instance::public_json(&inst));
}

fn parse_u64(s: &str) -> Option<u64> {
    if let Some(hex) = s.strip_prefix("0x") {
        u64::from_str_radix(hex, 16).ok()
    } else {
        s.parse().ok()
    }
}
