#!/usr/bin/env bash
# Benchmark a submission.
#
#   1. Wipe stale score.json / instance.public.json so a contestant can neither
#      pre-seed the score nor leave the representation on disk for the solver to
#      read (at these sizes (p,a,b,G,Q) is trivially breakable off-meter).
#   2. Build the trusted binaries (oracle, solver, gen_instance) offline.
#   3. Run the TRUSTED `oracle`. It derives the instance from $ECDLP_SEED (kept
#      only in its own memory) and spawns the UNTRUSTED `solver` as a sandboxed
#      child with a CLEARED environment, talking the counted group-oracle protocol
#      over a pipe. The solver never receives the curve, the coordinates, or the
#      seed — only opaque per-run-random tokens — so the op counter the oracle
#      keeps is authoritative and cannot be under-reported.
#   4. The oracle verifies the recovered k (k·P == Q) and writes the canonical
#      score.json + a results.tsv row.
#
# The sandbox confines the solver: no network (no exfiltration), no filesystem
# writes (cannot forge score.json or tamper with the oracle binary), and no read
# of the instance files. On Linux it uses bubblewrap; on macOS, sandbox-exec; if
# neither is present it falls back to an unconfined local-dev run.
#
# All CLI args are forwarded to the oracle (e.g. --note "tried Brent").
set -euo pipefail

# shellcheck disable=SC1091
. "$HOME/.cargo/env" 2>/dev/null || true
export CARGO_NET_OFFLINE=true

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$REPO"

# 1. Clean slate.
rm -f score.json instance.public.json

# 2. Build trusted binaries.
if ! command -v cargo >/dev/null 2>&1; then
  echo "!! cargo not found; run ./setup.sh first" >&2
  exit 1
fi
cargo build --release --bin oracle --bin solver --bin gen_instance >/dev/null

SOLVER_BIN="$REPO/target/release/solver"
ORACLE_BIN="$REPO/target/release/oracle"

# 3. Build the sandbox wrapper for the (untrusted) solver.
solver_wrap=""
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch" "${profile:-}" 2>/dev/null || true' EXIT

if command -v bwrap >/dev/null 2>&1; then
  # Linux: read-only view of everything, no network, writable only in scratch.
  solver_wrap="bwrap --ro-bind / / --dev /dev --proc /proc \
    --bind $scratch $scratch --chdir $REPO --setenv TMPDIR $scratch \
    --unshare-net --unshare-ipc --unshare-uts --new-session --die-with-parent"
elif [[ "$(uname -s)" == "Darwin" ]] && command -v sandbox-exec >/dev/null 2>&1; then
  # macOS: deny network + all writes (except scratch/dev), deny reading the
  # instance files and .git. Reading src/ is harmless (it holds no seed).
  profile="$(mktemp -t ecdlp_solver_XXXXXX).sb"
  cat > "$profile" <<EOF
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "$scratch"))
(allow file-write* (subpath "/dev"))
(deny file-read* (subpath "$REPO/.git"))
(deny file-read* (literal "$REPO/instance.public.json"))
(deny file-read* (literal "$REPO/instance.secret.json"))
EOF
  solver_wrap="/usr/bin/sandbox-exec -f $profile"
else
  echo "!! no sandbox available (bubblewrap/sandbox-exec); running solver UNCONFINED (dev only)" >&2
fi

# 4. Run the trusted oracle, which spawns the (wrapped) solver.
#    - $ECDLP_SEED: official runs set a fresh secret seed; local dev uses the
#      committed default baked into the oracle.
#    - Token encoding is randomized per run by the oracle (do NOT pin it here).
#    - $ECDLP_TRIALS: the official score is the MEAN over several trials, to tame
#      rho's heavy single-run variance. Override to 1 for quick local iteration.
export ECDLP_SOLVER_BIN="$SOLVER_BIN"
export ECDLP_SOLVER_WRAP="$solver_wrap"
export ECDLP_TRIALS="${ECDLP_TRIALS:-5}"

"$ORACLE_BIN" "$@"
