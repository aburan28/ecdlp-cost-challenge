#!/usr/bin/env bash
# Build the harness. Offline, no external crates.
set -euo pipefail

# shellcheck disable=SC1091
. "$HOME/.cargo/env" 2>/dev/null || true

if ! command -v cargo >/dev/null 2>&1; then
  echo "!! cargo not found. Install Rust: https://rustup.rs" >&2
  exit 1
fi

# If a pinned toolchain is requested and rustup is present, make sure it exists.
if command -v rustup >/dev/null 2>&1 && [[ -f rust-toolchain ]]; then
  channel="$(sed -n 's/^[[:space:]]*channel[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' rust-toolchain | head -n1)"
  if [[ -n "${channel}" ]] && ! rustup toolchain list 2>/dev/null | grep -q "^${channel}"; then
    rustup toolchain install "${channel}" || true
  fi
fi

export CARGO_NET_OFFLINE=true
cargo build --release --bin oracle --bin solver --bin gen_instance

echo "ok: built oracle, solver, gen_instance"
