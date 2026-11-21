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

PATH=/usr/bin:/bin:/usr/local/cuda/bin
export PATH
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WH="$REPO_ROOT/wheelhouse"
VENV="$REPO_ROOT/.venv-offline"
LOCK_PY="$REPO_ROOT/tools/offline/lock_python_deps.py"

die()  { echo "make_venv: ERROR: $*" >&2; exit 1; }
info() { echo "make_venv: $*"; }
clean_python() {
  /usr/bin/env -i PATH="$PATH" HOME=/nonexistent LC_ALL=C PIP_CONFIG_FILE=/dev/null "$@"
}

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
clean_python "$PY" -I -c 'import ensurepip' 2>/dev/null \
  || die "ensurepip missing for $PY (on Debian/Ubuntu: python3-venv — deliberate install)"
[ -d "$WH" ] || die "wheelhouse/ missing — run tools/offline/fetch_wheels.sh first (deliberate procurement)"
ls "$WH"/*.whl >/dev/null 2>&1 || die "wheelhouse/ has no wheels — run tools/offline/fetch_wheels.sh first"
[ -f "$WH/MANIFEST.sha256" ] || die "wheelhouse/MANIFEST.sha256 missing — procurement incomplete?"
[ -f "$LOCK_PY" ] || die "offline requirements lock tool missing"
# Eine private Kopie haelt Pruefung und Installation auf demselben Manifest.
LOCK_DIR="$(mktemp -d /tmp/strata-venv-lock.XXXXXXXX)"
LOCK_MANIFEST="$LOCK_DIR/MANIFEST.sha256"
cp "$WH/MANIFEST.sha256" "$LOCK_MANIFEST"
clean_python "$PY" -I "$LOCK_PY" --manifest "$LOCK_MANIFEST" --check-manifest \
  || die "invalid wheelhouse manifest"

# Verify the wheelhouse against its committed manifest before installing
# anything: a tampered or truncated wheel fails here, not at runtime. Files
# NOT listed in the manifest are flagged too — a planted wheel would install
# happily otherwise.
info "verifying wheelhouse against MANIFEST.sha256"
( cd "$WH" && sha256sum --check --quiet "$LOCK_MANIFEST" ) \
  || die "wheelhouse failed MANIFEST.sha256 verification — do not install"
UNEXPECTED="$(cd "$WH" && comm -23 \
  <(shopt -s nullglob; printf '%s\n' *.whl *.tar.gz *.zip | sort) \
  <(awk '{print $2}' "$LOCK_MANIFEST" | sort))"
[ -z "$UNEXPECTED" ] || die "wheelhouse has files not in MANIFEST.sha256 — refusing: $UNEXPECTED"

{ [ -e "$VENV" ] || [ -L "$VENV" ]; } && die "$VENV already exists — remove it by hand to rebuild deliberately"
info "creating $VENV with $(clean_python "$PY" -I --version 2>&1)"
mkdir "$VENV" || die "$VENV already exists or cannot be created"
clean_python "$PY" -I -m venv "$VENV"
VPY="$VENV/bin/python"
[ -x "$VPY" ] || die "venv created but $VPY missing"

info "installing requirements.txt + requirements-build.txt (--no-index, wheelhouse only)"
clean_python "$PY" -I "$LOCK_PY" --manifest "$LOCK_MANIFEST" \
  "$REPO_ROOT/terminal/requirements.txt" "$REPO_ROOT/terminal/requirements-build.txt" > "$LOCK_DIR/requirements-offline.lock" \
  || die "requirements contain unsupported pins or options"
clean_python "$VPY" -I -m pip --isolated install --no-index --no-deps --no-cache-dir --only-binary=:all: \
  --require-hashes --find-links "$WH" --disable-pip-version-check -r "$LOCK_DIR/requirements-offline.lock"

# CUDA runtime wheels (parsed from setup.py — same pins setup installs). An
# empty parse must fail closed: silently skipping means a venv WITHOUT the
# CUDA libs that later dies at runtime on libcublas.
mapfile -t CUDA_WHEELS < <(grep -oP 'CUDA_WHEELS = \[\K[^\]]+' "$REPO_ROOT/terminal/setup.py" | grep -oP '"[^"]+"' | tr -d '"')
mapfile -t CUDA12_WHEELS < <(grep -oP 'CUDA12_WHEELS = \[\K[^\]]+' "$REPO_ROOT/terminal/setup.py" | grep -oP '"[^"]+"' | tr -d '"')
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
  printf '%s\n' "${WHEELS[@]}" | clean_python "$PY" -I "$LOCK_PY" --manifest "$LOCK_MANIFEST" \
    > "$LOCK_DIR/requirements-cuda-offline.lock" || die "CUDA requirements contain unsupported pins"
  clean_python "$VPY" -I -m pip --isolated install --no-index --no-deps --no-cache-dir --only-binary=:all: \
    --require-hashes --find-links "$WH" --disable-pip-version-check -r "$LOCK_DIR/requirements-cuda-offline.lock"
fi

info "checking installed dependency metadata without resolving or fetching"
clean_python "$VPY" -I -m pip --isolated check || die "installed dependencies are incomplete or incompatible"
info "done. Smoke check:"
clean_python "$VPY" -I -c "import numpy, jinja2, requests, yaml, tqdm, PIL, psutil, regex; print('  imports ok:', numpy.__version__, jinja2.__version__, requests.__version__)"
cp "$LOCK_MANIFEST" "$VENV/wheelhouse-manifest.sha256"
cp "$LOCK_DIR/requirements-offline.lock" "$VENV/requirements-offline.lock"
if [ -f "$LOCK_DIR/requirements-cuda-offline.lock" ]; then
  cp "$LOCK_DIR/requirements-cuda-offline.lock" "$VENV/requirements-cuda-offline.lock"
fi
info "private installation evidence kept at $LOCK_DIR"
info "venv at $VENV"
