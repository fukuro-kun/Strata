#!/usr/bin/env bash
# make_venv.sh — create the fork's offline venv from the local wheelhouse.
#
# FORK POLICY: installs ONLY from wheelhouse/ via --no-index --find-links.
# Missing wheel → pip fails (fail closed), never a PyPI fallback. No pip
# upgrade, no network. The venv lands at .venv-offline/ (next to upstream's
# .venv — no conflict; upstream .venv is never touched).
#
# Usage:
#   tools/offline/make_venv.sh [--python /path/to/python3] [--cuda 13|12|none]
#
# --cuda picks which NVIDIA runtime wheels (setup.py's CUDA_WHEELS pins) get
# installed into the venv so the engine finds libcublas at runtime. Default:
# auto — 13 when nvcc is CUDA 13, 12 for CUDA 12, none without nvcc.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WH="$REPO_ROOT/wheelhouse"
VENV="$REPO_ROOT/.venv-offline"

die()  { echo "make_venv: ERROR: $*" >&2; exit 1; }
info() { echo "make_venv: $*"; }

PY="$(command -v python3 || true)"
CUDA=auto
while [ $# -gt 0 ]; do
  case "$1" in
    --python) PY="${2:?--python needs a path}"; shift 2;;
    --cuda)   CUDA="${2:?--cuda needs 13|12|none}"; shift 2;;
    -h|--help) awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    *)        die "unknown argument: $1";;
  esac
done

[ -x "$PY" ] || die "python not found: $PY"
"$PY" -c 'import ensurepip' 2>/dev/null \
  || die "ensurepip missing for $PY (on Debian/Ubuntu: python3-venv — deliberate install)"
[ -d "$WH" ] || die "wheelhouse/ missing — run tools/offline/fetch_wheels.sh first (deliberate procurement)"
ls "$WH"/*.whl >/dev/null 2>&1 || die "wheelhouse/ has no wheels — run tools/offline/fetch_wheels.sh first"
[ -f "$WH/MANIFEST.sha256" ] || die "wheelhouse/MANIFEST.sha256 missing — procurement incomplete?"

# Verify the wheelhouse against its committed manifest before installing
# anything: a tampered or truncated wheel fails here, not at runtime. Files
# NOT listed in the manifest are flagged too — a planted wheel would install
# happily otherwise.
info "verifying wheelhouse against MANIFEST.sha256"
( cd "$WH" && sha256sum --check --quiet MANIFEST.sha256 ) \
  || die "wheelhouse failed MANIFEST.sha256 verification — do not install"
UNEXPECTED="$(cd "$WH" && comm -23 \
  <(shopt -s nullglob; printf '%s\n' *.whl *.tar.gz *.zip | sort) \
  <(awk '{print $2}' MANIFEST.sha256 | sort))"
[ -z "$UNEXPECTED" ] || die "wheelhouse has files not in MANIFEST.sha256 — refusing: $UNEXPECTED"

[ -e "$VENV" ] && die "$VENV already exists — remove it by hand to rebuild deliberately"
info "creating $VENV with $("$PY" --version 2>&1)"
"$PY" -m venv "$VENV"
VPY="$VENV/bin/python"
[ -x "$VPY" ] || die "venv created but $VPY missing"

info "installing requirements.txt (--no-index, wheelhouse only)"
"$VPY" -m pip install --no-index --find-links "$WH" --disable-pip-version-check \
  -r "$REPO_ROOT/requirements.txt"

# CUDA runtime wheels (parsed from setup.py — same pins setup installs). An
# empty parse must fail closed: silently skipping means a venv WITHOUT the
# CUDA libs that later dies at runtime on libcublas.
mapfile -t CUDA_WHEELS < <(grep -oP 'CUDA_WHEELS = \[\K[^\]]+' "$REPO_ROOT/setup.py" | grep -oP '"[^"]+"' | tr -d '"')
mapfile -t CUDA12_WHEELS < <(grep -oP 'CUDA12_WHEELS = \[\K[^\]]+' "$REPO_ROOT/setup.py" | grep -oP '"[^"]+"' | tr -d '"')
if [ "$CUDA" = auto ]; then
  if command -v nvcc >/dev/null; then
    MAJ="$(nvcc --version | grep -oP 'release \K[0-9]+' || true)"
    case "${MAJ:-}" in
      12) CUDA=12;;
      13) CUDA=13;;
      *)  CUDA=none; info "nvcc release '$MAJ' not 12/13 — no matching wheel set";;
    esac
  else
    CUDA=none
  fi
  info "--cuda auto -> $CUDA"
fi
case "$CUDA" in
  13)   [ "${#CUDA_WHEELS[@]}" -gt 0 ] || die "cannot parse CUDA_WHEELS from setup.py"; WHEELS=("${CUDA_WHEELS[@]}");;
  12)   [ "${#CUDA12_WHEELS[@]}" -gt 0 ] || die "cannot parse CUDA12_WHEELS from setup.py"; WHEELS=("${CUDA12_WHEELS[@]}");;
  none) WHEELS=();;
  *)    die "--cuda must be 13|12|none";;
esac
if [ "${#WHEELS[@]}" -gt 0 ]; then
  info "installing CUDA runtime wheels (--cuda $CUDA): ${WHEELS[*]}"
  "$VPY" -m pip install --no-index --find-links "$WH" --disable-pip-version-check "${WHEELS[@]}"
fi

info "done. Smoke check:"
"$VPY" -c "import numpy, jinja2, requests, yaml, tqdm, PIL, psutil, regex; print('  imports ok:', numpy.__version__, jinja2.__version__, requests.__version__)"
info "venv at $VENV"
