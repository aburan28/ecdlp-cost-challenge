//! TRUSTED parent. Derives the instance from `$ECDLP_SEED`/`$ECDLP_BITS`, spawns
//! the (sandboxed, untrusted) solver, serves the counted group-oracle protocol,
//! then verifies the answer and writes the canonical `score.json` + a `results.tsv`
//! row. The solver runs as a child whose address space never contains the curve
//! secrets, so the op counter maintained here is authoritative.

use ecdlp_challenge::instance;
use ecdlp_challenge::oracle::Oracle;
use std::env;
use std::fs;
use std::io::{BufReader, BufWriter, Write};
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

fn env_u64(key: &str) -> Option<u64> {
    env::var(key).ok().and_then(|s| {
        if let Some(h) = s.strip_prefix("0x") {
            u64::from_str_radix(h, 16).ok()
        } else {
            s.parse().ok()
        }
    })
}

fn git_commit() -> String {
    if let Ok(c) = env::var("ECDLP_COMMIT") {
        return c;
    }
    Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|| "-".to_string())
}

/// Run one trial: spawn the (optionally sandboxed) untrusted solver with a cleared
/// environment, serve the protocol, return (correct, group_ops).
fn run_trial(mut oracle: Oracle, solver_bin: &str, wrap: &str) -> (bool, u64) {
    let mut cmd = if wrap.trim().is_empty() {
        Command::new(solver_bin)
    } else {
        let mut parts = wrap.split_whitespace();
        let mut c = Command::new(parts.next().unwrap());
        for p in parts {
            c.arg(p);
        }
        c.arg(solver_bin);
        c
    };
    // The solver must learn NOTHING about the instance except via the oracle:
    // clear its environment so it cannot read $ECDLP_SEED and regenerate k itself.
    cmd.env_clear()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    let mut child = cmd.spawn().expect("failed to spawn solver");
    let to_solver = BufWriter::new(child.stdin.take().unwrap());
    let from_solver = BufReader::new(child.stdout.take().unwrap());
    let _ = oracle.serve(from_solver, to_solver);
    let _ = child.wait();
    (oracle.finished && oracle.solved, oracle.count)
}

fn main() {
    // ---- note from CLI (e.g. `--note "tried Brent"`) -------------------------
    let mut note = String::new();
    let mut args = env::args().skip(1).peekable();
    while let Some(a) = args.next() {
        if a == "--note" {
            note = args.next().unwrap_or_default();
        }
    }

    // ---- instance ------------------------------------------------------------
    let seed = env_u64("ECDLP_SEED").unwrap_or(0x1234_5678);
    let bits = env_u64("ECDLP_BITS").map(|b| b as u32).unwrap_or(40);
    let inst = instance::generate(seed, bits);

    // The public representation is written only AFTER the run (below). Handing it
    // to the sandboxed solver mid-run would let it solve off-meter, since at these
    // sizes (p,a,b,G,Q) is trivially breakable. Keep it until scoring is done.
    let public_descriptor = instance::public_json(&inst);

    // FAIR & REPRODUCIBLE TRIAL BATTERY (see DESIGN.md §"Fair, reproducible
    // scoring"). The per-trial token encodings are a DETERMINISTIC function of the
    // instance seed — NOT wall-clock — so the same solver scores identically on
    // every run. Nothing to re-roll, no "faster on some runs": rho's collision
    // time is a random variable, so we pin its randomness instead of resampling it.
    // The official grader overrides ECDLP_TOKEN_SEED with ONE per-round secret
    // value applied to EVERY submission (common random numbers ⇒ a paired,
    // luck-cancelling comparison), then reveals it after grading for audit.
    let base_token_seed = env_u64("ECDLP_TOKEN_SEED").unwrap_or_else(|| {
        let mut z = seed.wrapping_add(0x9E37_79B9_7F4A_7C15); // SplitMix64(instance seed)
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    });

    let n = inst.n;
    let rho_ref = (1.2533141373155003_f64 * (n as f64).sqrt()).round() as u64;
    // Negation is free ⇒ you search the n/2 classes {±P}; the floor on the
    // *expected* score is √(n/2) ≈ 0.707·√n (not √n).
    let shoup_floor = ((n as f64) / 2.0).sqrt().floor() as u64;

    let solver_bin =
        env::var("ECDLP_SOLVER_BIN").unwrap_or_else(|_| "target/release/solver".to_string());
    let wrap = env::var("ECDLP_SOLVER_WRAP").unwrap_or_default();

    // Average over several trials (fresh token encoding each) to tame rho's heavy
    // single-run variance, which can otherwise swing a score by 2× either way. The
    // mean is the leaderboard quantity. Default 1 for fast local iteration; the
    // official scored run sets ECDLP_TRIALS higher (see benchmark.sh).
    let trials = env_u64("ECDLP_TRIALS").unwrap_or(1).max(1);

    let mut sum_ops: u128 = 0;
    let mut all_ok = true;
    for t in 0..trials {
        let token_seed = base_token_seed.wrapping_add(t.wrapping_mul(0x9E37_79B9_7F4A_7C15));
        let oracle = Oracle::new(inst.clone(), token_seed);
        let (ok, ops) = run_trial(oracle, &solver_bin, &wrap);
        eprintln!(
            "[oracle] trial {}/{}: {} group_ops  {}",
            t + 1,
            trials,
            ops,
            if ok { "OK" } else { "FAIL" }
        );
        all_ok &= ok;
        sum_ops += ops as u128;
        if !ok {
            break;
        }
    }

    // Publish the representation (no k) only after every trial has finished.
    let _ = fs::write("instance.public.json", &public_descriptor);

    // ---- score (mean over trials) -------------------------------------------
    let correct = all_ok;
    let count = if correct {
        (sum_ops / trials as u128) as u64
    } else {
        0
    };
    let ratio = if rho_ref > 0 {
        count as f64 / rho_ref as f64
    } else {
        0.0
    };

    let score_json = if correct {
        format!(
            concat!(
                "{{\n",
                "  \"score\": {score},\n",
                "  \"metrics\": {{\n",
                "    \"group_ops\": {ops},\n",
                "    \"bits\": {bits},\n",
                "    \"n\": {n},\n",
                "    \"rho_reference\": {rho},\n",
                "    \"shoup_floor\": {floor},\n",
                "    \"ratio_to_rho\": {ratio:.4},\n",
                "    \"trials\": {trials},\n",
                "    \"instance_seed\": {iseed},\n",
                "    \"token_seed_base\": {tseed},\n",
                "    \"reproducible\": true,\n",
                "    \"correct\": true\n",
                "  }}\n",
                "}}\n"
            ),
            score = count,
            ops = count,
            bits = bits,
            n = n,
            rho = rho_ref,
            floor = shoup_floor,
            ratio = ratio,
            trials = trials,
            iseed = seed,
            tseed = base_token_seed,
        )
    } else {
        format!(
            "{{\n  \"score\": null,\n  \"metrics\": {{ \"correct\": false, \"group_ops\": {count} }}\n}}\n"
        )
    };
    let _ = fs::write("score.json", &score_json);

    // results.tsv (append-only). Columns 9–11 (instance_seed/token_seed/trials)
    // make every row reproducible: re-running with the same seeds + solver yields
    // the same score, bit-for-bit. (Legacy 8-column rows still parse — readers
    // take the first 8 fields.)
    let header = "timestamp\tcommit\tgroup_ops\tbits\trho_ref\tratio\tcorrect\tnote\tinstance_seed\ttoken_seed\ttrials\n";
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let row = format!(
        "{ts}\t{commit}\t{ops}\t{bits}\t{rho}\t{ratio:.4}\t{ok}\t{note}\t{iseed}\t{tseed}\t{trials}\n",
        ts = ts,
        commit = git_commit(),
        ops = count,
        bits = bits,
        rho = rho_ref,
        ratio = ratio,
        ok = if correct { "OK" } else { "FAIL" },
        note = note.replace('\t', " ").replace('\n', " "),
        iseed = seed,
        tseed = base_token_seed,
        trials = trials,
    );
    if !std::path::Path::new("results.tsv").exists() {
        let _ = fs::write("results.tsv", header);
    }
    if let Ok(mut f) = fs::OpenOptions::new().append(true).open("results.tsv") {
        let _ = f.write_all(row.as_bytes());
    }

    // Console summary.
    if correct {
        eprintln!(
            "[oracle] SOLVED  n=2^{bits}  mean_group_ops={count} (over {trials} trial(s))  rho_ref={rho_ref}  ratio={ratio:.3}×rho  (E[floor] √(n/2)={shoup_floor})"
        );
    } else {
        eprintln!("[oracle] FAILED  (solver did not return a valid k)  group_ops={count}");
        std::process::exit(1);
    }
}
