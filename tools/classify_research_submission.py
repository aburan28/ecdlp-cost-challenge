#!/usr/bin/env python3
"""Classify research-track submissions.

This is intentionally a lightweight guard, not a theorem prover. It makes the
leaderboard harder to game by forcing every research submission to declare:

  * whether it uses rho-family machinery,
  * whether it uses the curve representation,
  * what mechanism it claims, and
  * whether held-out scaling evidence supports the claim.

Usage:

    python3 tools/classify_research_submission.py submissions/research-foo

Exit codes:

    0: submission is structurally valid
    2: missing required files or malformed manifest/results
    3: claimed class is inconsistent with declared capabilities/evidence
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib


REQUIRED = ["submission.toml", "CLAIM.md", "results.json"]
VALID_CLASSES = {
    "rho_constant",
    "generic_collision",
    "representation_constant",
    "representation_subsqrt_candidate",
    "failed_or_overfit",
}


def fail(code: int, msg: str) -> None:
    print(f"REJECT: {msg}", file=sys.stderr)
    raise SystemExit(code)


def warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        fail(2, f"cannot parse {path}: {e}")


def finite_number(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def main() -> int:
    if len(sys.argv) != 2:
        fail(2, "usage: classify_research_submission.py submissions/research-<name>")

    root = Path(sys.argv[1])
    if not root.is_dir():
        fail(2, f"not a directory: {root}")

    for rel in REQUIRED:
        if not (root / rel).exists():
            fail(2, f"missing required file: {rel}")

    try:
        manifest = tomllib.loads((root / "submission.toml").read_text())
    except Exception as e:  # noqa: BLE001
        fail(2, f"cannot parse submission.toml: {e}")

    claim_md = (root / "CLAIM.md").read_text()
    results = load_json(root / "results.json")
    scaling_path = root / "scaling.json"
    scaling = load_json(scaling_path) if scaling_path.exists() else {}

    caps = manifest.get("capabilities", {})
    claim = manifest.get("claim", {})
    sub = manifest.get("submission", {})

    uses_rho = bool(caps.get("uses_rho")) or bool(caps.get("uses_distinguished_points")) or bool(caps.get("uses_negation_map"))
    uses_rep = bool(caps.get("uses_representation"))
    track = sub.get("track")
    mechanism = str(claim.get("mechanism", "")).strip()

    if track not in {"generic", "scaling", "representation"}:
        fail(2, "submission.track must be one of: generic, scaling, representation")
    if not mechanism or mechanism.lower().startswith("describe "):
        fail(2, "claim.mechanism must describe a concrete mechanism")

    declared = None
    for cls in VALID_CLASSES:
        if cls in claim_md:
            declared = cls
            break
    if declared is None:
        fail(2, "CLAIM.md must declare one result class")

    # Pull scaling evidence from either common shapes.
    alpha = None
    alpha_upper = None
    heldout_passed = None
    if scaling:
        fit = scaling.get("fit", scaling)
        alpha = fit.get("alpha")
        ci = fit.get("alpha_ci95") or fit.get("alpha_ci") or fit.get("alpha_95ci")
        if isinstance(ci, list) and len(ci) == 2 and finite_number(ci[1]):
            alpha_upper = float(ci[1])
        heldout = scaling.get("heldout", {})
        if isinstance(heldout, dict):
            heldout_passed = heldout.get("passed")

    # Classification consistency checks.
    if declared == "rho_constant":
        if not uses_rho:
            warn("declared rho_constant but manifest does not mark rho-family features")
        if uses_rep:
            warn("rho_constant submission also declares representation use; consider representation_constant")

    elif declared == "generic_collision":
        if uses_rep:
            fail(3, "generic_collision cannot set uses_representation=true")

    elif declared == "representation_constant":
        if not uses_rep:
            fail(3, "representation_constant requires uses_representation=true")

    elif declared == "representation_subsqrt_candidate":
        if not uses_rep:
            fail(3, "subsqrt candidate requires uses_representation=true")
        if heldout_passed is not True:
            fail(3, "subsqrt candidate requires scaling.heldout.passed=true")
        if alpha_upper is None:
            fail(3, "subsqrt candidate requires alpha_ci95 upper bound in scaling.json")
        if alpha_upper >= 0.5:
            fail(3, f"subsqrt candidate requires alpha upper 95% < 0.5, got {alpha_upper}")

    elif declared == "failed_or_overfit":
        pass

    if alpha is not None and finite_number(alpha):
        print(f"alpha={float(alpha):.6f}")
    if alpha_upper is not None:
        print(f"alpha_upper_95={alpha_upper:.6f}")
    if heldout_passed is not None:
        print(f"heldout_passed={heldout_passed}")
    print(f"class={declared}")
    print("ACCEPT: research submission is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
