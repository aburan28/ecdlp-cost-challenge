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

/// Integrity verdict on a finished, correct run (every trial returned a valid k).
///
/// `ops` are the per-trial op counts THIS trusted process charged — the sandboxed
/// solver cannot influence them — so the spread we measure is authoritative.
/// Shoup's generic lower bound makes √(n/2) (`shoup_floor`) a floor on the
/// *expected* op count of any representation-blind algorithm; a re-derived mean
/// below it cannot mean someone broke the bound, only that the meter under-counted
/// (a harness bug or an off-meter exploit). rho's collision time scatters
/// (CV ≈ 0.52), so we hard-reject (`publishable = false`) only when the whole
/// one-sided confidence band on the mean sits below the floor — which needs ≥ 2
/// trials to estimate the spread. The gap between the floor and the negation
/// birthday bound √(πn/4) (`neg_bound`, the best any known generic *walk* averages)
/// is open territory: we keep it publishable but return a loud note asking for
/// fresh-seed reproduction before it goes on the board.
fn floor_verdict(ops: &[u64], shoup_floor: u64, neg_bound: f64, rho_ref: u64) -> (bool, String) {
    const Z_HARD: f64 = 3.0; // one-sided ≈ 99.9%: don't false-accuse a lucky run
    if ops.is_empty() {
        return (true, String::new());
    }
    let k = ops.len() as f64;
    let mean = ops.iter().map(|&o| o as f64).sum::<f64>() / k;
    let mean_ops = (ops.iter().map(|&o| o as u128).sum::<u128>() / ops.len() as u128) as u64;
    let ratio = mean / rho_ref as f64;
    let sem = if ops.len() >= 2 {
        let var = ops
            .iter()
            .map(|&o| (o as f64 - mean) * (o as f64 - mean))
            .sum::<f64>()
            / (k - 1.0);
        (var / k).sqrt()
    } else {
        f64::INFINITY // a single trial gives no spread estimate ⇒ never hard-reject
    };
    if mean + Z_HARD * sem < shoup_floor as f64 {
        return (
            false,
            format!(
                "re-derived mean {mean_ops} ({ratio:.4}×rho) is below the Shoup floor √(n/2)={shoup_floor} by >{z}σ over {nt} trials (sem={sem:.0}); a generic solver cannot average below √(n/2) — the meter under-counted (harness bug or off-meter exploit)",
                z = Z_HARD as u64,
                nt = ops.len(),
            ),
        );
    }
    if mean < shoup_floor as f64 {
        return (
            true,
            format!(
                "mean {mean_ops} is below the √(n/2)={shoup_floor} floor but within sampling noise over {nt} trial(s) — rerun with more trials before treating it as a record",
                nt = ops.len(),
            ),
        );
    }
    if mean < neg_bound {
        return (
            true,
            format!(
                "mean {mean_ops} ({ratio:.4}×rho) beats the negation birthday bound √(πn/4)={neg:.0} ({nr:.4}×rho), the best any known generic walk averages — reproduce with a fresh secret seed before publishing",
                neg = neg_bound,
                nr = neg_bound / rho_ref as f64,
            ),
        );
    }
    (true, String::new())
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
    let mut ops_per_trial: Vec<u64> = Vec::with_capacity(trials as usize);
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
        ops_per_trial.push(ops);
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

    // ---- integrity gate (trusted): refuse to bless a sub-floor "record" -------
    // No representation-blind solver can average below √(n/2) (Shoup). The ops are
    // counted by THIS process, so the spread is authoritative, and a src/solver-only
    // PR cannot reach this code (the editable-paths guard blocks it). See
    // floor_verdict() for the statistics; `publishable=false` voids the score.
    let neg_bound = (std::f64::consts::PI * n as f64).sqrt() / 2.0; // √(πn/4) ≈ 0.71×rho
    let (publishable, integrity_note) = if correct {
        floor_verdict(&ops_per_trial, shoup_floor, neg_bound, rho_ref)
    } else {
        (false, String::new())
    };

    let score_json = if publishable {
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
    } else if !correct {
        format!(
            "{{\n  \"score\": null,\n  \"metrics\": {{ \"correct\": false, \"group_ops\": {count} }}\n}}\n"
        )
    } else {
        // Valid k, but the re-derived mean is below the Shoup floor — void it so a
        // meter bug or off-meter exploit can never masquerade as a broken bound.
        format!(
            concat!(
                "{{\n",
                "  \"score\": null,\n",
                "  \"metrics\": {{\n",
                "    \"correct\": true,\n",
                "    \"rejected\": \"below_shoup_floor\",\n",
                "    \"group_ops\": {ops},\n",
                "    \"bits\": {bits},\n",
                "    \"n\": {n},\n",
                "    \"rho_reference\": {rho},\n",
                "    \"shoup_floor\": {floor},\n",
                "    \"ratio_to_rho\": {ratio:.4},\n",
                "    \"trials\": {trials},\n",
                "    \"instance_seed\": {iseed},\n",
                "    \"token_seed_base\": {tseed},\n",
                "    \"reason\": \"{reason}\"\n",
                "  }}\n",
                "}}\n"
            ),
            ops = count,
            bits = bits,
            n = n,
            rho = rho_ref,
            floor = shoup_floor,
            ratio = ratio,
            trials = trials,
            iseed = seed,
            tseed = base_token_seed,
            reason = integrity_note,
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
        ok = if publishable { "OK" } else { "FAIL" },
        note = if integrity_note.is_empty() {
            note.replace('\t', " ").replace('\n', " ")
        } else {
            format!("{note} [{integrity_note}]")
                .replace('\t', " ")
                .replace('\n', " ")
        },
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
    if publishable {
        eprintln!(
            "[oracle] SOLVED  n=2^{bits}  mean_group_ops={count} (over {trials} trial(s))  rho_ref={rho_ref}  ratio={ratio:.3}×rho  (E[floor] √(n/2)={shoup_floor})"
        );
        if !integrity_note.is_empty() {
            eprintln!("[oracle] ⚠ FLAG: {integrity_note}");
        }
    } else if !correct {
        eprintln!("[oracle] FAILED  (solver did not return a valid k)  group_ops={count}");
        std::process::exit(1);
    } else {
        eprintln!(
            "[oracle] REJECTED (integrity)  {integrity_note}.\n          A generic solver cannot average below √(n/2); this is a meter bug or an off-meter exploit, not a record."
        );
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::floor_verdict;

    // bits=40 sample tier (see main()): rho_ref = round(1.2533·√n),
    // shoup_floor = ⌊√(n/2)⌋ ≈ 0.56×rho, neg_bound = √(πn/4) ≈ 0.71×rho.
    const RHO_REF: u64 = 984_377;
    const FLOOR: u64 = 555_375;
    const NEG_BOUND: f64 = 696_059.0;

    #[test]
    fn ordinary_score_is_publishable_and_silent() {
        // shipped negation-map rho ≈ 0.80×, comfortably above both bounds
        let (ok, note) = floor_verdict(&[788_034; 8], FLOOR, NEG_BOUND, RHO_REF);
        assert!(ok);
        assert!(note.is_empty(), "unexpected note: {note}");
    }

    #[test]
    fn below_neg_bound_is_flagged_but_publishable() {
        // 0.62×: above the floor, below the birthday bound ⇒ soft flag, still valid
        let (ok, note) = floor_verdict(&[612_655; 8], FLOOR, NEG_BOUND, RHO_REF);
        assert!(ok);
        assert!(note.contains("birthday"), "expected soft flag, got: {note:?}");
    }

    #[test]
    fn consistent_sub_floor_mean_is_rejected() {
        // a steady sub-floor mean is impossible for a generic solver ⇒ void it
        let (ok, note) = floor_verdict(&[200_000; 8], FLOOR, NEG_BOUND, RHO_REF);
        assert!(!ok);
        assert!(note.contains("Shoup floor"), "got: {note:?}");
    }

    #[test]
    fn single_sub_floor_run_is_not_rejected() {
        // one lucky run can dip below the floor (rho variance) — never a reject
        let (ok, note) = floor_verdict(&[400_000], FLOOR, NEG_BOUND, RHO_REF);
        assert!(ok);
        assert!(note.contains("sampling noise"), "got: {note:?}");
    }

    #[test]
    fn high_variance_sub_floor_mean_is_not_false_accused() {
        // mean dips below the floor but the spread straddles it ⇒ band overlaps the
        // floor ⇒ not hard-rejected (we only void when the WHOLE band is below it)
        let (ok, _note) = floor_verdict(
            &[120_000, 980_000, 130_000, 950_000, 110_000, 990_000],
            FLOOR,
            NEG_BOUND,
            RHO_REF,
        );
        assert!(ok);
    }
}
