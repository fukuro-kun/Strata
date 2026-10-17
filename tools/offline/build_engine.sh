#!/usr/bin/env bash
# build_engine.sh — offline engine build for the fukuro-kun/Strata fork.
#
# FORK POLICY: this script never downloads anything. Every input must already
# exist locally and pinned; a missing input is a hard error with a clear
# message (fail closed), never a fallback to network procurement.
#
# It follows the upstream local-build path (setup.py -> cmake_build) and writes
# an engine/BUILD.json stamp in upstream format plus fork fields. It does NOT
# cover the experimental sm_<75 build (STRATA_EXPERIMENTAL_SM60) or the
# STRATA_ISA_FLOOR path — pass extra flags via --cmake-def if ever needed.
#
# Usage:
#   tools/offline/build_engine.sh [--cuda auto|on|off] [--arch <sm-list|native>]
#                                 [--vision cpu|gpu|off] [--tests]
#                                 [--build-dir DIR] [--jobs N]
#                                 [--cmake-def DEF]...  (extra -D args)
#
# Requirements (checked before anything runs):
#   - local llama.cpp tree at third_party/llama.cpp (or $STRATA_GGML_DIR):
#     .strata-pin == LLAMA_CPP_COMMIT (setup.py), and/or a git checkout whose
#     HEAD is the pin with a CLEAN tree
#   - cmake >= 3.24, ninja, C and C++ compilers, python3
#   - for --cuda on / auto+found: nvcc and an architecture >= sm_75

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

die()  { echo "build_engine: ERROR: $*" >&2; exit 1; }
info() { echo "build_engine: $*"; }

# ---------------------------------------------------------------- options

CUDA=auto
ARCHS=""
VISION=cpu
TESTS=OFF
BUILD_DIR="$REPO_ROOT/build"
JOBS="$(nproc 2>/dev/null || echo 4)"
JOBS=$(( JOBS / 2 )); [ "$JOBS" -ge 2 ] || JOBS=2   # upstream halves cpu_count
EXTRA_DEFS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --cuda)      CUDA="${2:?}"; shift 2;;
    --arch)      ARCHS="${2:?}"; shift 2;;
    --vision)    VISION="${2:?}"; shift 2;;
    --tests)     TESTS=ON; shift;;
    --build-dir) BUILD_DIR="${2:?}"; shift 2;;
    --jobs)      JOBS="${2:?}"; shift 2;;
    --cmake-def) EXTRA_DEFS+=("-D$2"); shift 2;;
    -h|--help)   awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    *)           die "unknown argument: $1";;
  esac
done

case "$CUDA"   in auto|on|off) ;; *) die "--cuda must be auto|on|off (got '$CUDA')";; esac
case "$VISION" in cpu|gpu|off) ;; *) die "--vision must be cpu|gpu|off (got '$VISION')";; esac
if [ -n "$ARCHS" ]; then
  for a in ${ARCHS//;/ }; do
    [[ "$a" =~ ^([0-9]+(-real|-virtual)?|native|all|all-major)$ ]] \
      || die "--arch item '$a' invalid (use e.g. 86 / '86;89' / native)"
  done
fi

# ---------------------------------------------------------------- inputs

LLAMA_CPP_COMMIT="$(grep -oP 'LLAMA_CPP_COMMIT\s*=\s*"\K[0-9a-f]{40}' setup.py)" \
  || die "cannot read LLAMA_CPP_COMMIT from setup.py"
GGML_INPUT="${STRATA_GGML_DIR:-$REPO_ROOT/third_party/llama.cpp}"
GGML_DIR="$(cd "$GGML_INPUT" 2>/dev/null && pwd)" \
  || die "STRATA_GGML_DIR '$GGML_INPUT' does not exist — run tools/offline/fetch_llamacpp.sh first"

[ -f "$GGML_DIR/ggml/CMakeLists.txt" ] || die "$GGML_DIR has no ggml/CMakeLists.txt — not a llama.cpp tree"
[ -d "$GGML_DIR/gguf-py" ]           || die "$GGML_DIR lacks gguf-py/ — incomplete llama.cpp tree"

# Pin proof: require .strata-pin match and/or clean git checkout at the pin.
# A dirty checkout at the pin builds unverified content — refused.
export GIT_NO_LAZY_FETCH=1
PROOF=0
if [ -f "$GGML_DIR/.strata-pin" ]; then
  PIN="$(tr -d '[:space:]' < "$GGML_DIR/.strata-pin")"
  [ "$PIN" = "$LLAMA_CPP_COMMIT" ] \
    || die "ggml tree pin mismatch: .strata-pin=$PIN, expected $LLAMA_CPP_COMMIT"
  PROOF=1; info "ggml pin proven by .strata-pin"
fi
# Only a checkout whose .git sits INSIDE the tree counts — a bare path under
# another repo would resolve HEAD from the parent checkout (false positive).
if [ -e "$GGML_DIR/.git" ]; then
  HEAD="$(git -C "$GGML_DIR" rev-parse HEAD)"
  [ "$HEAD" = "$LLAMA_CPP_COMMIT" ] \
    || die "ggml checkout is at $HEAD, expected pinned $LLAMA_CPP_COMMIT"
  [ -z "$(git -C "$GGML_DIR" status --porcelain)" ] \
    || die "ggml checkout at the pin but has uncommitted changes — refusing to build unverified content"
  PROOF=1; info "ggml pin proven by clean git checkout at pin"
fi
[ "$PROOF" = 1 ] \
  || die "ggml tree carries no pin proof (.strata-pin or git HEAD) — re-obtain via tools/offline/fetch_llamacpp.sh"
info "ggml source: $GGML_DIR (pinned $LLAMA_CPP_COMMIT)"

# ---------------------------------------------------------------- tools

find_tool() {
  for c in "$1" ".venv/bin/$1"; do
    [ -x "$c" ] && { command -v "$c"; return; }
    command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return; }
  done
  return 1
}

CMAKE="$(find_tool cmake)" || die "cmake not found (PATH or .venv/bin)"
NINJA="$(find_tool ninja)" || die "ninja not found (PATH or .venv/bin)"
CMAKE_VER="$("$CMAKE" --version | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
python3 -c "import sys; v='${CMAKE_VER}'.split('.'); sys.exit(0 if [int(v[0]),int(v[1])] >= [3,24] else 1)" \
  || die "cmake $CMAKE_VER < 3.24 (required)"
command -v cc  >/dev/null || command -v gcc   >/dev/null || command -v clang   >/dev/null \
  || die "no C compiler found"
command -v c++ >/dev/null || command -v g++   >/dev/null || command -v clang++ >/dev/null \
  || die "no C++ compiler found"
command -v python3 >/dev/null || die "python3 not found (needed for version check + BUILD.json stamp)"

# ---------------------------------------------------------------- CUDA

NVCC=""
if [ "$CUDA" != off ]; then
  NVCC="$(command -v nvcc || true)"
  if [ -z "$NVCC" ]; then
    [ "$CUDA" = on ] && die "--cuda on but nvcc not found"
    info "no nvcc — falling back to CPU build (--cuda auto)"
    CUDA=off
  fi
fi

if [ "$CUDA" != off ] && [ -z "$ARCHS" ]; then
  if command -v nvidia-smi >/dev/null; then
    ARCHS="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader \
             | sort -Vu | tr -d '.' | paste -sd';')"
  fi
  [ -n "$ARCHS" ] || die "cannot detect GPU arch (no nvidia-smi) — pass --arch 86 / --arch '86;89'"
fi
if [ "$VISION" = gpu ]; then
  [ "$CUDA" != off ] || die "--vision gpu needs a CUDA build (--cuda on|auto with nvcc)"
  [ -n "$NVCC" ] || die "--vision gpu needs nvcc"
fi

# ---------------------------------------------------------------- build

DEFS=(-DCMAKE_BUILD_TYPE=Release -DSTRATA_GGML_DIR="$GGML_DIR" -DSTRATA_BUILD_TESTS="$TESTS")
if [ "$CUDA" != off ]; then
  NVCC_REAL="$(readlink -f "$NVCC")"
  DEFS+=(-DSTRATA_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$ARCHS"
         -DCMAKE_CUDA_COMPILER="$NVCC_REAL")
  NVROOT="$(dirname "$(dirname "$NVCC_REAL")")"
  [ "$NVROOT" != /usr ] && DEFS+=(-DCUDAToolkit_ROOT="$NVROOT")
  # host compiler passthroughs like setup.py:host_compiler_defs
  [ -n "${CC:-}"  ] && DEFS+=(-DCMAKE_C_COMPILER="$CC")
  [ -n "${CXX:-}" ] && DEFS+=(-DCMAKE_CXX_COMPILER="$CXX")
  [ -n "${CUDAHOSTCXX:-}${CXX:-}" ] && DEFS+=(-DCMAKE_CUDA_HOST_COMPILER="${CUDAHOSTCXX:-$CXX}")
fi
DEFS+=("${EXTRA_DEFS[@]}")

# Stale-cache guard: a cache whose key vars differ from the requested build
# makes CMake wipe the cache mid-configure and re-run — and the re-run loses
# the -D options (observed: STRATA_GGML_DIR came back empty → fail-closed
# error). Detect the conflict and remove the cache ourselves, up front.
if [ -f "$BUILD_DIR/CMakeCache.txt" ]; then
  cache_get() { grep -m1 "^$1:" "$BUILD_DIR/CMakeCache.txt" | cut -d= -f2-; }
  want_cuda="OFF"; [ "$CUDA" != off ] && want_cuda="ON"
  stale=0
  [ "$(cache_get STRATA_GGML_DIR)"    = "$GGML_DIR"  ] || stale=1
  [ "$(cache_get STRATA_ENABLE_CUDA)" = "$want_cuda" ] || stale=1
  if [ "$CUDA" != off ]; then
    [ "$(cache_get CMAKE_CUDA_COMPILER)" = "$NVCC_REAL" ] || stale=1
  fi
  if [ "$stale" = 1 ]; then
    info "build cache conflicts with requested options — removing CMakeCache.txt/CMakeFiles for a clean configure"
    rm -f "$BUILD_DIR/CMakeCache.txt"; rm -rf "$BUILD_DIR/CMakeFiles"
  fi
fi

info "configure: cmake -G Ninja -S . -B $BUILD_DIR ${DEFS[*]}"
"$CMAKE" -G Ninja -DCMAKE_MAKE_PROGRAM="$NINJA" -S "$REPO_ROOT" -B "$BUILD_DIR" "${DEFS[@]}"

# One retry on failure — CUDA 13.0 ptxas intermittently fails to parse its own
# PTX (upstream issue #45); a second build compiles only what is still missing.
if ! "$CMAKE" --build "$BUILD_DIR" --target strata -j "$JOBS"; then
  info "first build pass failed — retrying once (upstream issue #45)"
  "$CMAKE" --build "$BUILD_DIR" --target strata -j "$JOBS"
fi
[ -x "$BUILD_DIR/strata" ] || die "build finished but $BUILD_DIR/strata is missing"

# ---------------------------------------------------------------- vision

VEXE=""
if [ "$VISION" != off ]; then
  VDIR="$REPO_ROOT/build-vision"
  VDEFS=(-DCMAKE_BUILD_TYPE=Release -DLLAMA_DIR="$GGML_DIR" -DSTRATA_PORTABLE=OFF)
  if [ "$VISION" = gpu ]; then
    VDEFS+=(-DSTRATA_VISION_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$ARCHS"
            -DCMAKE_CUDA_COMPILER="$(readlink -f "$NVCC")")
    [ "$NVROOT" != /usr ] && VDEFS+=(-DCUDAToolkit_ROOT="$NVROOT")
  else
    VDEFS+=(-DSTRATA_VISION_CUDA=OFF)
  fi
  [ -n "${CXX:-}" ] && VDEFS+=(-DCMAKE_CXX_COMPILER="$CXX")
  info "vision build ($VISION): tools/vision -> $VDIR"
  "$CMAKE" -G Ninja -DCMAKE_MAKE_PROGRAM="$NINJA" -S "$REPO_ROOT/tools/vision" -B "$VDIR" "${VDEFS[@]}"
  "$CMAKE" --build "$VDIR" --target strata-vision -j "$JOBS"
  VEXE="$VDIR/bin/strata-vision"
  [ -x "$VEXE" ] || die "vision build finished but $VEXE is missing"
fi

# ---------------------------------------------------------------- staging

mkdir -p engine
cp -a "$BUILD_DIR/strata" engine/strata
if [ -f "$BUILD_DIR/libstrata_kq.so" ]; then
  cp -a "$BUILD_DIR/libstrata_kq.so" engine/libstrata_kq.so
else
  rm -f engine/libstrata_kq.so   # a stale one of another build would only confuse
fi
if [ -n "$VEXE" ]; then
  cp -a "$VEXE" engine/strata-vision
fi

# Provenance stamp — same fields as upstream BUILD.json, plus fork additions.
# The embedded engine version is read from the binary, the source version from
# project() in CMakeLists.txt (upstream's binary_engine_version/source_version).
python3 - "$REPO_ROOT" "$GGML_DIR" "$LLAMA_CPP_COMMIT" "$ARCHS" "$VISION" "${NVCC:-none}" <<'PYEOF'
import hashlib, json, pathlib, re, sys
root, ggml, pin, archs, vision, nvcc = sys.argv[1:]
root = pathlib.Path(root)

def source_hash(parts):
    h = hashlib.sha256(pin.encode())
    for part in parts:
        base = root / part
        for f in [base] if base.is_file() else sorted(x for x in base.rglob('*') if x.is_file()):
            h.update(f.relative_to(root).as_posix().encode() + b'\0'
                     + f.read_bytes().replace(b'\r\n', b'\n'))
    return h.hexdigest()[:16]

m = re.search(r"project\(strata VERSION ([\d.]+)", (root / 'CMakeLists.txt').read_text())
ver = m.group(1) if m else '0'
vision_stamp = {'cpu': 'cpu', 'gpu': 'gpu'}.get(vision, 'none')   # upstream vocabulary
arch_list = [int(a) if a.isdigit() else a for a in archs.split(';') if a]
arch_list.sort(key=lambda x: (not isinstance(x, int), x))
bindir = pathlib.Path(nvcc).resolve().parent if nvcc != 'none' else None
dirs = [] if bindir is None else [str(d) for d in (bindir, bindir / 'x64', bindir.parent / 'lib64') if d.is_dir()]
stamp = {"source": "local-fork", "version": ver, "archs": arch_list,
         "vision": vision_stamp, "cuda_dirs": dirs,
         "src": source_hash(('CMakeLists.txt', 'cmake', 'src', 'include', 'third_party/ggml')),
         "vision_src": source_hash(('tools/vision',)) if vision != 'off' else None,
         "ggml_commit": pin, "ggml_dir": ggml}
(root / 'engine' / 'BUILD.json').write_text(json.dumps(stamp, indent=1))
print('engine/BUILD.json:', json.dumps(stamp))
PYEOF

echo
info "BUILD COMPLETE — engine/ staged:"
for f in engine/strata engine/libstrata_kq.so engine/strata-vision; do
  [ -f "$f" ] && sha256sum "$f" | sed 's/^/  /'
done
