#!/usr/bin/env bash
# fetch_wheels.sh — controlled procurement of the pinned Python wheels.
#
# FORK POLICY (fukuro-kun/Strata): deliberate, documented, one-time
# procurement. Downloads exactly the pins from requirements.txt plus the
# NVIDIA CUDA-library wheels that setup.py puts into the venv (CUDA_WHEELS /
# CUDA12_WHEELS — parsed from setup.py so the pins stay single-sourced).
# Everything lands in wheelhouse/ (gitignored); the committed provenance is
# wheelhouse/MANIFEST.sha256, regenerated at the end of every run.
#
# Usage:
#   tools/offline/fetch_wheels.sh                      # wheels for THIS python
#   tools/offline/fetch_wheels.sh --for-python 3.12    # wheels for another
#                                                      # interpreter (same
#                                                      # platform; --only-binary)
#
# Run it once per interpreter you deploy to; all variants coexist in the
# wheelhouse. After the last run the manifest is complete and committable.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WH="$REPO_ROOT/wheelhouse"
MANIFEST="$WH/MANIFEST.sha256"

die()  { echo "fetch_wheels: ERROR: $*" >&2; exit 1; }
info() { echo "fetch_wheels: $*"; }

PYVER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --for-python) PYVER="${2:?--for-python needs X.Y}"; shift 2;;
    -h|--help)    awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    *)            die "unknown argument: $1";;
  esac
done

PIP=(python3 -m pip)
"${PIP[@]}" --version >/dev/null 2>&1 || die "no pip for python3 — install python3-pip (deliberate one-time install)"

# CUDA library wheels are pinned in setup.py (single source of truth).
mapfile -t CUDA_WHEELS < <(grep -oP 'CUDA_WHEELS = \[\K[^\]]+' "$REPO_ROOT/setup.py" | grep -oP '"[^"]+"' | tr -d '"')
mapfile -t CUDA12_WHEELS < <(grep -oP 'CUDA12_WHEELS = \[\K[^\]]+' "$REPO_ROOT/setup.py" | grep -oP '"[^"]+"' | tr -d '"')
[ "${#CUDA_WHEELS[@]}" -gt 0 ]   || die "could not parse CUDA_WHEELS from setup.py"
[ "${#CUDA12_WHEELS[@]}" -gt 0 ] || die "could not parse CUDA12_WHEELS from setup.py"
info "CUDA wheels (setup.py): ${CUDA_WHEELS[*]} | ${CUDA12_WHEELS[*]}"

mkdir -p "$WH"

DL=(download --dest "$WH" --disable-pip-version-check)
if [ -n "$PYVER" ]; then
  DL+=(--python-version "$PYVER" --only-binary :all:)
  info "target interpreter: python $PYVER (cross-fetch, binary wheels only)"
else
  info "target interpreter: $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
fi

info "downloading requirements.txt wheels -> $WH"
"${PIP[@]}" "${DL[@]}" -r "$REPO_ROOT/requirements.txt"

info "downloading CUDA library wheels (13.x + 12.x sets)"
"${PIP[@]}" "${DL[@]}" "${CUDA_WHEELS[@]}" "${CUDA12_WHEELS[@]}"

info "writing $MANIFEST"
# Hash every installable artifact, not only *.whl: pip download may fetch an
# sdist (.tar.gz/.zip) for a pin without a compatible wheel, and --find-links
# would still install it — it belongs in the provenance too.
( cd "$WH" && shopt -s nullglob && \
  files=(*.whl *.tar.gz *.zip) && [ "${#files[@]}" -gt 0 ] && \
  sha256sum "${files[@]}" | sort -k2 > MANIFEST.sha256.tmp && mv MANIFEST.sha256.tmp MANIFEST.sha256 )
info "done: $(cd "$WH" && shopt -s nullglob && files=(*.whl *.tar.gz *.zip) && echo "${#files[@]}") artifacts, manifest committed separately"
info "NOTE: .whl files are gitignored; only $MANIFEST is tracked."
