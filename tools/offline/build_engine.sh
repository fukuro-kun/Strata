#!/usr/bin/env bash
# build_engine.sh — offline engine build for the fukuro-kun/Strata fork.
#
# FORK POLICY: this script never downloads anything. Every input must already
# exist locally and pinned; a missing input is a hard error with a clear
# message (fail closed), never a fallback to network procurement.
#
# It follows the upstream local-build path (terminal/setup.py -> cmake_build)
# and writes a terminal/engine/BUILD.json stamp in upstream format plus fork
# fields. It does NOT cover the experimental sm_<75 build
# (STRATA_EXPERIMENTAL_SM60) or the STRATA_ISA_FLOOR path — pass extra flags
# via --cmake-def if ever needed.
#
# Usage:
#   tools/offline/build_engine.sh [--cuda auto|on|off] [--arch <sm-list|native>]
#                                 [--vision cpu|gpu|off] [--tests]
#                                 [--build-dir DIR] [--jobs N]
#                                 [--cmake-def DEF]...  (extra -D args)
#
# Requirements (checked before anything runs):
#   - vendored ggml tree at engine/third_party/strata-ggml (or $STRATA_GGML_DIR
#     override): the vendored tree is proven per-file by tools/check_vendored.py;
#     an override checkout must prove the pin via .strata-pin == LLAMA_CPP_COMMIT
#     (terminal/setup.py) and/or a git checkout whose HEAD is the pin with a
#     CLEAN tree
#   - cmake >= 3.24, ninja, C and C++ compilers, python3
#   - for --cuda on / auto+found: nvcc and an architecture >= sm_75

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENGINE_ROOT="$REPO_ROOT/engine"
TERMINAL_ROOT="$REPO_ROOT/terminal"
ARTIFACTS="$TERMINAL_ROOT/engine"
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

LLAMA_CPP_COMMIT="$(grep -oP 'LLAMA_CPP_COMMIT\s*=\s*"\K[0-9a-f]{40}' "$TERMINAL_ROOT/setup.py")" \
  || die "cannot read LLAMA_CPP_COMMIT from terminal/setup.py"
GGML_INPUT="${STRATA_GGML_DIR:-$ENGINE_ROOT/third_party/strata-ggml}"
GGML_DIR="$(cd "$GGML_INPUT" 2>/dev/null && pwd)" \
  || die "ggml tree '$GGML_INPUT' does not exist"

[ -f "$GGML_DIR/ggml/CMakeLists.txt" ] || die "$GGML_DIR has no ggml/CMakeLists.txt — not a ggml/llama.cpp tree"
[ -d "$ENGINE_ROOT/third_party/strata-gguf-py" ] || die "engine/third_party/strata-gguf-py missing — incomplete vendored layout"

# Pin proof: require .strata-pin match and/or clean git checkout at the pin.
# A dirty checkout at the pin builds unverified content — refused.
export GIT_NO_LAZY_FETCH=1
PROOF=0
if [ "$GGML_DIR" = "$ENGINE_ROOT/third_party/strata-ggml" ]; then
  # vendored tree: the manifest verifier hashes every file against the declared pin
  command -v python3 >/dev/null 2>&1 || die "python3 not found — required for tools/check_vendored.py"
  VOUT="$(python3 tools/check_vendored.py)" || die "tools/check_vendored.py failed: $VOUT"
  echo "$VOUT" | grep -q "strata-ggml: .*pin ${LLAMA_CPP_COMMIT:0:9}" \
    || die "strata-ggml manifest pin does not match $LLAMA_CPP_COMMIT"
  PROOF=1; info "ggml pin proven by tools/check_vendored.py"
fi
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
  for c in "$1" ".venv-offline/bin/$1" ".venv/bin/$1"; do
    if [ -f "$c" ] && [ -x "$c" ]; then   # executable file: absolutize (cmake chdir's)
      ( cd "$(dirname "$c")" && pwd -P ) | sed "s|\$|/$(basename "$c")|"
      return
    fi
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"     # PATH hit — already absolute
      return
    fi
  done
  return 1
}

CMAKE="$(find_tool cmake)" || die "cmake not found (PATH or .venv-offline/bin)"
NINJA="$(find_tool ninja)" || die "ninja not found (PATH or .venv-offline/bin)"
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

DEFS=(-DCMAKE_BUILD_TYPE=Release -DSTRATA_BUILD_TESTS="$TESTS")
# STRATA_GGML_DIR means "override away from the vendored tree" — pass it only
# when the caller actually set one; empty makes CMake resolve the vendored
# third_party/strata-ggml (and pick its ggml-cuda-tq dir instead of the overlay).
[ -n "${STRATA_GGML_DIR:-}" ] && DEFS+=(-DSTRATA_GGML_DIR="$GGML_DIR")
if [ "$CUDA" != off ]; then
  # A user-supplied --cmake-def CMAKE_CUDA_COMPILER=… wins over PATH-nvcc —
  # needed on hosts whose default toolkit is older than the intended one.
  NVCC_CHOSEN="$NVCC"
  for d in "${EXTRA_DEFS[@]:-}"; do
    case "$d" in -DCMAKE_CUDA_COMPILER=*) NVCC_CHOSEN="${d#-DCMAKE_CUDA_COMPILER=}";; esac
  done
  [ -x "$NVCC_CHOSEN" ] || die "CUDA compiler '$NVCC_CHOSEN' is not executable"
  NVCC_REAL="$(readlink -f "$NVCC_CHOSEN")"
  NVCC="$NVCC_REAL"   # effective compiler — also what BUILD.json records
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
DEFS+=(-DGGML_CCACHE=OFF)

# Stale-cache guard: a cache whose key vars differ from the requested build
# makes CMake wipe the cache mid-configure and re-run — and the re-run loses
# the -D options (observed: STRATA_GGML_DIR came back empty → fail-closed
# error). Detect the conflict and refuse — never remove preexisting files.
if [ -f "$BUILD_DIR/CMakeCache.txt" ]; then
  cache_get() { grep -m1 "^$1:" "$BUILD_DIR/CMakeCache.txt" | cut -d= -f2-; }
  want_cuda="OFF"; [ "$CUDA" != off ] && want_cuda="ON"
  stale=0
  # the cache stores the RESOLVED absolute path ($GGML_DIR) when an override is
  # set, empty otherwise — compare against exactly what configure receives
  [ "$(cache_get CMAKE_HOME_DIRECTORY)" = "$ENGINE_ROOT" ] || stale=1
  [ "$(cache_get STRATA_GGML_DIR)"    = "${STRATA_GGML_DIR:+$GGML_DIR}"  ] || stale=1
  [ "$(cache_get STRATA_ENABLE_CUDA)" = "$want_cuda" ] || stale=1
  if [ "$CUDA" != off ]; then
    [ "$(cache_get CMAKE_CUDA_COMPILER)" = "$NVCC_REAL" ] || stale=1
    [ "$(cache_get CUDAToolkit_ROOT)" = "$([ "$NVROOT" = /usr ] || printf '%s' "$NVROOT")" ] || stale=1
  fi
  if [ "$stale" = 1 ]; then
    die "stale CMake cache in $BUILD_DIR; use a fresh --build-dir"
  fi
fi

info "configure: cmake -G Ninja -S $ENGINE_ROOT -B $BUILD_DIR ${DEFS[*]}"
"$CMAKE" -G Ninja -DCMAKE_MAKE_PROGRAM="$NINJA" -S "$ENGINE_ROOT" -B "$BUILD_DIR" "${DEFS[@]}"

# One retry on failure — CUDA 13.0 ptxas intermittently fails to parse its own
# PTX (upstream issue #45); a second build compiles only what is still missing.
if ! "$CMAKE" --build "$BUILD_DIR" --target strata -j "$JOBS"; then
  info "first build pass failed — retrying once (upstream issue #45)"
  "$CMAKE" --build "$BUILD_DIR" --target strata -j "$JOBS"
fi
[ -x "$BUILD_DIR/strata" ] || die "build finished but $BUILD_DIR/strata is missing"

# Embedded-version provenance: the binary's "engine=<version>" stamp must equal
# the source's project() version — refuses a stale/mismatched binary without
# executing it.
python3 - "$ENGINE_ROOT/CMakeLists.txt" "$BUILD_DIR/strata" <<'PYEOF'
import pathlib, re, sys
source = re.search(r"project\(strata VERSION ([\d.]+)", pathlib.Path(sys.argv[1]).read_text())
versions = {v.decode() for v in re.findall(rb"engine=(\d+\.\d+\.\d+(?:\.\d+)?)\n", pathlib.Path(sys.argv[2]).read_bytes())}
if source is None or versions != {source.group(1)}:
    sys.exit(f"build_engine: ERROR: embedded engine version {sorted(versions)} does not match source")
PYEOF

# ---------------------------------------------------------------- vision

VEXE=""
if [ "$VISION" != off ]; then
  VDIR="$REPO_ROOT/build-vision"
  # v0.2.17 vision builds its own tower — no llama.cpp input, oracles stay off.
  VDEFS=(-DCMAKE_BUILD_TYPE=Release -DSTRATA_VISION_ORACLES=OFF -DSTRATA_PORTABLE=OFF)
  if [ "$VISION" = gpu ]; then
    VDEFS+=(-DSTRATA_VISION_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$ARCHS"
            -DCMAKE_CUDA_COMPILER="$(readlink -f "$NVCC")")
    [ "$NVROOT" != /usr ] && VDEFS+=(-DCUDAToolkit_ROOT="$NVROOT")
  else
    VDEFS+=(-DSTRATA_VISION_CUDA=OFF)
  fi
  [ -n "${CXX:-}" ] && VDEFS+=(-DCMAKE_CXX_COMPILER="$CXX")
  info "vision build ($VISION): terminal/tools/vision -> $VDIR"
  "$CMAKE" -G Ninja -DCMAKE_MAKE_PROGRAM="$NINJA" -S "$TERMINAL_ROOT/tools/vision" -B "$VDIR" "${VDEFS[@]}"
  "$CMAKE" --build "$VDIR" --target strata-vision -j "$JOBS"
  VEXE="$VDIR/bin/strata-vision"
  [ -x "$VEXE" ] || die "vision build finished but $VEXE is missing"
fi

# ---------------------------------------------------------------- staging

mkdir -p "$ARTIFACTS"
# The upstream CUDA backend only ships mmq_absent.cpp — no libstrata_kq.so is
# staged anymore. A legacy copy in the artifact dir is an error, not something
# to silently delete.
if [ -e "$ARTIFACTS/libstrata_kq.so" ] || [ -L "$ARTIFACTS/libstrata_kq.so" ]; then
  die "legacy libstrata_kq.so present in $ARTIFACTS — remove it deliberately before staging"
fi
if [ -z "$VEXE" ] && { [ -e "$ARTIFACTS/strata-vision" ] || [ -L "$ARTIFACTS/strata-vision" ]; }; then
  die "stale vision binary in $ARTIFACTS; use a clean artifact directory for --vision off"
fi
cp -a "$BUILD_DIR/strata" "$ARTIFACTS/strata"
if [ -n "$VEXE" ]; then
  cp -a "$VEXE" "$ARTIFACTS/strata-vision"
fi

# Provenance stamp — same fields as upstream BUILD.json, plus fork additions.
# The embedded engine version is read from the binary, the source version from
# project() in engine/CMakeLists.txt (upstream's binary_engine_version/
# source_version). Source fingerprints hash under the two source roots —
# engine/ for engine parts, terminal/ for tools/* — like upstream
# terminal/setup.py.
python3 - "$REPO_ROOT" "$GGML_DIR" "$LLAMA_CPP_COMMIT" "$ARCHS" "$VISION" "${NVCC:-none}" "$BUILD_DIR" <<'PYEOF'
import hashlib, json, pathlib, re, sys
root, ggml, pin, archs, vision, nvcc, build = sys.argv[1:]
root = pathlib.Path(root)
engine_root = root / 'engine'
terminal_root = root / 'terminal'

def source_hash(parts):
    h = hashlib.sha256(pin.encode())
    for part in parts:
        top = terminal_root if part.startswith('tools/') else engine_root
        base = top / part
        for f in [base] if base.is_file() else sorted(x for x in base.rglob('*') if x.is_file()):
            h.update(f.relative_to(top).as_posix().encode() + b'\0'
                     + f.read_bytes().replace(b'\r\n', b'\n'))
    return h.hexdigest()[:16]

m = re.search(r"project\(strata VERSION ([\d.]+)", (engine_root / 'CMakeLists.txt').read_text())
ver = m.group(1) if m else '0'
vision_stamp = {'cpu': 'cpu', 'gpu': 'gpu'}.get(vision, 'none')   # upstream vocabulary
arch_list = [int(a) if a.isdigit() else a for a in archs.split(';') if a]
arch_list.sort(key=lambda x: (not isinstance(x, int), x))
bindir = pathlib.Path(nvcc).resolve().parent if nvcc != 'none' else None
dirs = [] if bindir is None else [str(d) for d in (bindir, bindir / 'x64', bindir.parent / 'lib64') if d.is_dir()]
cuda_compiler = cuda_compiler_version = None
if bindir is not None:
    # The stamp must describe the compiler CMake actually used — read it from
    # generated text (cache entry + compiler probe file), never by executing
    # or evaluating the compiler itself.
    m = re.search(r'(?m)^CMAKE_CUDA_COMPILER:[^=\n]+=(.+)$',
                  (pathlib.Path(build) / 'CMakeCache.txt').read_text())
    if m is None:
        sys.exit('build_engine: ERROR: CMAKE_CUDA_COMPILER missing in CMakeCache.txt')
    cache_compiler = m.group(1).strip()
    compat = set()
    for f in pathlib.Path(build).glob('CMakeFiles/*/CMakeCUDACompiler.cmake'):
        text = f.read_text()
        comp = re.search(r'(?m)^set\(CMAKE_CUDA_COMPILER "([^"]+)"\)$', text)
        if comp is None or pathlib.Path(comp.group(1)).resolve() != pathlib.Path(cache_compiler).resolve():
            continue
        cver = re.search(r'(?m)^set\(CMAKE_CUDA_COMPILER_VERSION "([0-9.]+)"\)$', text)
        if cver is not None:
            compat.add((cache_compiler, cver.group(1)))
    if len(compat) != 1:
        sys.exit('build_engine: ERROR: CUDA compiler stamp missing or ambiguous')
    cuda_compiler, cuda_compiler_version = compat.pop()
stamp = {"source": "local-fork", "version": ver, "archs": arch_list,
         "vision": vision_stamp, "cuda_dirs": dirs,
         "cuda_compiler": cuda_compiler, "cuda_compiler_version": cuda_compiler_version,
         "src": source_hash(('CMakeLists.txt', 'cmake', 'src', 'include',
                             'third_party/ggml', 'third_party/strata-ggml')),
         "vision_src": source_hash(('tools/vision', 'third_party/stb')) if vision != 'off' else None,
         "ggml_commit": pin, "ggml_dir": ggml}
(terminal_root / 'engine' / 'BUILD.json').write_text(json.dumps(stamp, indent=1))
print('terminal/engine/BUILD.json:', json.dumps(stamp))
PYEOF

echo
info "BUILD COMPLETE — $ARTIFACTS staged:"
sha256sum "$ARTIFACTS/strata" | sed 's/^/  /'
if [ -n "$VEXE" ]; then
  sha256sum "$ARTIFACTS/strata-vision" | sed 's/^/  /'
fi
