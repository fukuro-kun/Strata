#!/usr/bin/env bash
# calibrate.sh — offline calibration wrapper (P2).
#
# Runs upstream's tools/calibrate.py under the fork's offline venv against an
# existing run config — measures --pcie-frac / --spec-min-p / --pool-workers /
# adaptive-tier values on this machine. setup.py --calibrate additionally
# SAVES the result into the config; this script only measures and prints —
# write the values into the config deliberately (they are user-owned keys
# under "args", setup's carry_over keeps them).
#
# Usage:
#   tools/offline/calibrate.sh strata-<model>.json

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VPY="$REPO_ROOT/.venv-offline/bin/python"

die() { echo "calibrate: ERROR: $*" >&2; exit 1; }

CFG="${1:-}"
[ -n "$CFG" ] || die "usage: calibrate.sh strata-<model>.json"
[ $# -le 1 ] || die "calibrate.py takes exactly the config — no extra args"
CFG_ABS="$(cd "$(dirname "$CFG")" 2>/dev/null && pwd)/$(basename "$CFG")"
[ -f "$CFG_ABS" ] || die "config not found: $CFG"
[ -x "$VPY" ] || die "offline venv missing — run tools/offline/make_venv.sh first"

cd "$REPO_ROOT"
exec "$VPY" tools/calibrate.py "$CFG_ABS"
