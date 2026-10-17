#!/usr/bin/env bash
# fetch_llamacpp.sh — controlled procurement of the pinned llama.cpp source.
#
# FORK POLICY (fukuro-kun/Strata): this is the ONLY sanctioned way to obtain
# the llama.cpp source. It is a deliberate, documented, one-time procurement
# step — never invoked automatically by build/start/calibration paths.
# The result lands at third_party/llama.cpp (gitignored, reserved path) with a
# .strata-pin marker; tools/offline/build_engine.sh refuses to run without it.
#
# Sources (in order of preference):
#   --from-dir <path>   copy an existing verified tree (e.g. rsync'd from a LAN
#                       host that already ran upstream setup at the same pin)
#   --from-git <path>   `git archive` the pinned commit out of a local clone
#                       (clone must contain LLAMA_CPP_COMMIT; lazy fetching is
#                       disabled — a partial clone missing the blobs fails
#                       closed instead of silently hitting the network)
#   --clone             `git clone` from github.com/ggml-org/llama.cpp
#                       (network! deliberate procurement only)
#
# Proof accepted for --from-dir (checked BEFORE copying):
#   - source has .strata-pin matching the pin, or
#   - source is a git checkout at exactly the pinned commit with a clean tree, or
#   - --allow-unverified is given explicitly (e.g. an extracted zip whose
#     integrity was proven another way — record the hashes you used).
#
# Verification afterwards (all modes): tree must contain ggml/CMakeLists.txt,
# gguf-py/, ggml/src/; the pin in third_party/ggml/VERSION.txt must equal
# LLAMA_CPP_COMMIT in setup.py. .strata-pin is then written into the tree.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$REPO_ROOT/third_party/llama.cpp"
PIN_FILE="$REPO_ROOT/third_party/ggml/VERSION.txt"

die() { echo "fetch_llamacpp: ERROR: $*" >&2; exit 1; }
info() { echo "fetch_llamacpp: $*"; }

# Never let a partial clone turn git commands into silent network fetches.
export GIT_NO_LAZY_FETCH=1

# The pin is read from setup.py (single source of truth).
LLAMA_CPP_COMMIT="$(grep -oP 'LLAMA_CPP_COMMIT\s*=\s*"\K[0-9a-f]{40}' "$REPO_ROOT/setup.py")" \
  || die "could not read LLAMA_CPP_COMMIT from setup.py"
[ -n "$LLAMA_CPP_COMMIT" ] || die "LLAMA_CPP_COMMIT empty in setup.py"

# Cross-check against the vendored VERSION.txt (written when ggml was vendored).
if [ -f "$PIN_FILE" ]; then
  PINNED_TXT="$(grep -oE '[0-9a-f]{40}' "$PIN_FILE" | head -1 || true)"
  if [ -n "$PINNED_TXT" ] && [ "$PINNED_TXT" != "$LLAMA_CPP_COMMIT" ]; then
    die "pin mismatch: setup.py has $LLAMA_CPP_COMMIT but $PIN_FILE records $PINNED_TXT"
  fi
fi
info "pinned commit: $LLAMA_CPP_COMMIT"

MODE=""
SRC=""
ALLOW_UNVERIFIED=0
while [ $# -gt 0 ]; do
  case "$1" in
    --from-dir)          MODE=dir; SRC="${2:?--from-dir needs a path}"; shift 2;;
    --from-git)          MODE=git; SRC="${2:?--from-git needs a clone path}"; shift 2;;
    --clone)             MODE=clone; shift;;
    --allow-unverified)  ALLOW_UNVERIFIED=1; shift;;
    -h|--help)           awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    *)                   die "unknown argument: $1";;
  esac
done
[ -n "$MODE" ] || die "no source given — use --from-dir, --from-git or --clone (see header comment)"

if [ -e "$DEST" ]; then
  # Re-running is allowed only to repair: refuse to silently replace a tree.
  die "$DEST already exists — remove it by hand if you really want to replace it (keeps procurement deliberate)"
fi
mkdir -p "$(dirname "$DEST")"

verify_tree() {
  [ -f "$DEST/ggml/CMakeLists.txt" ] || die "verification failed: $DEST/ggml/CMakeLists.txt missing"
  [ -d "$DEST/gguf-py" ]           || die "verification failed: $DEST/gguf-py missing"
  [ -d "$DEST/ggml/src" ]          || die "verification failed: $DEST/ggml/src missing"
  printf '%s\n' "$LLAMA_CPP_COMMIT" > "$DEST/.strata-pin"
  info "verified tree at $DEST; .strata-pin = $LLAMA_CPP_COMMIT"
}

case "$MODE" in
  dir)
    [ -f "$SRC/ggml/CMakeLists.txt" ] || die "$SRC does not look like a llama.cpp tree (ggml/CMakeLists.txt missing)"
    # Prove the pin BEFORE copying anything.
    if [ -f "$SRC/.strata-pin" ]; then
      SRC_PIN="$(tr -d '[:space:]' < "$SRC/.strata-pin")"
      [ "$SRC_PIN" = "$LLAMA_CPP_COMMIT" ] || die "source .strata-pin is $SRC_PIN, expected $LLAMA_CPP_COMMIT"
      info "source .strata-pin matches"
    elif [ -e "$SRC/.git" ]; then
      # .git directly in the source — a path under another repo would resolve
      # to the parent checkout (false positive).
      SRC_HEAD="$(git -C "$SRC" rev-parse HEAD)"
      [ "$SRC_HEAD" = "$LLAMA_CPP_COMMIT" ] || die "source checkout is at $SRC_HEAD, expected $LLAMA_CPP_COMMIT"
      [ -z "$(git -C "$SRC" status --porcelain)" ] \
        || die "source checkout is at the pin but has uncommitted changes — unverifiable content"
      info "source git checkout matches pin and is clean"
    else
      [ "$ALLOW_UNVERIFIED" = 1 ] || die "source has no .strata-pin and is not a git checkout — cannot prove the pin. Pass --allow-unverified to accept it anyway (and record your own hash evidence)"
      info "WARNING: source tree accepted without pin proof (--allow-unverified)"
    fi
    info "copying $SRC -> $DEST (excluding __pycache__)"
    mkdir -p "$DEST"
    if command -v rsync >/dev/null; then
      rsync -a --exclude='__pycache__' "$SRC/" "$DEST/"
    else
      (cd "$SRC" && tar --exclude='__pycache__' -cf - .) | tar -xf - -C "$DEST"
    fi
    verify_tree
    ;;

  git)
    git -C "$SRC" rev-parse --git-dir >/dev/null 2>&1 || die "$SRC is not a git repository"
    git -C "$SRC" cat-file -e "$LLAMA_CPP_COMMIT^{commit}" \
      || die "repo $SRC does not contain $LLAMA_CPP_COMMIT (lazy fetch disabled — fetch in that repo first, deliberately)"
    info "git archive $LLAMA_CPP_COMMIT -> $DEST"
    mkdir -p "$DEST"
    git -C "$SRC" archive "$LLAMA_CPP_COMMIT" | tar -x -C "$DEST"
    verify_tree
    ;;

  clone)
    TMP="$(dirname "$DEST")/.llama.cpp.git-tmp"
    trap 'rm -rf "$TMP"' EXIT
    info "DELIBERATE NETWORK PROCUREMENT: cloning github.com/ggml-org/llama.cpp"
    git clone --no-checkout https://github.com/ggml-org/llama.cpp.git "$TMP"
    git -C "$TMP" cat-file -e "$LLAMA_CPP_COMMIT^{commit}" \
      || die "pinned commit $LLAMA_CPP_COMMIT not present after clone"
    mkdir -p "$DEST"
    git -C "$TMP" archive "$LLAMA_CPP_COMMIT" | tar -x -C "$DEST"
    rm -rf "$TMP"; trap - EXIT
    verify_tree
    ;;
esac

info "done. Build with: tools/offline/build_engine.sh"
