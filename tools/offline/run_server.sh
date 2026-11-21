#!/usr/bin/env bash
# run_server.sh — start the Strata server without setup.py, from the offline
# venv only.
#
# FORK POLICY: replaces upstream's generated run-<model>.sh. Same call shape
# (.venv python -> terminal/serve/server.py --engine strata --config X --port Y) but
# every input is validated first and missing input is a hard error — never a
# download, never a fallback to setup.py.
#
# Usage:
#   tools/offline/run_server.sh strata-<model>.json [--port N] [--host ADDR]
#   tools/offline/run_server.sh --mock [--port N]          # no engine/model —
#                                                          # API smoke test
#
# The config JSON (strata-<model>.json) is the same file setup.py writes; on
# hosts that already ran setup it exists and is reused verbatim. For a fresh
# checkout write one with tools/offline/make_config.py.

set -euo pipefail

# FORK POLICY: serving never acquires. Refuse every download/install/update
# primitive even when a caller inherited a broad STRATA_FORK_ALLOW_ACQUIRE=1;
# STRATA_NO_HANDOVER keeps the corrected env name (strata_cli/handover.py ENV_OFF).
export STRATA_NO_ACQUIRE=1
export STRATA_NO_HANDOVER=1
export PYTHONDONTWRITEBYTECODE=1
export STRATA_NATIVE_HELPERS=0
unset STRATA_NATIVE_HELPER_DIR

REPO_ROOT="$(cd "$(/usr/bin/dirname "$0")/../.." && pwd)"
VPY="$REPO_ROOT/.venv-offline/bin/python"

die()  { echo "run_server: ERROR: $*" >&2; exit 1; }
info() { echo "run_server: $*"; }

CONFIG=""
PORT=""
HOST=""
MOCK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --mock)  MOCK=1; shift;;
    --port)  PORT="${2:?--port needs a number}"; shift 2;;
    --host)  HOST="${2:?--host needs an address}"; shift 2;;
    -h|--help) awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    -*)      die "unknown option: $1";;
    *)       [ -n "$CONFIG" ] && die "only one config argument allowed"; CONFIG="$1"; shift;;
  esac
done

[ -x "$VPY" ] || die "offline venv missing ($VPY) — run tools/offline/make_venv.sh first"
[ -f "$REPO_ROOT/terminal/serve/server.py" ] || die "terminal/serve/server.py not found — wrong checkout?"

ARGS=(--offline --engine)
if [ "$MOCK" = 1 ]; then
  ARGS+=(mock)
else
  [ -n "$CONFIG" ] || die "no config given — usage: run_server.sh strata-<model>.json [--port N]"
  CFG_ABS="$(cd "$(/usr/bin/dirname "$CONFIG")" 2>/dev/null && pwd)/$(/usr/bin/basename "$CONFIG")"
  [ -f "$CFG_ABS" ] || die "config not found: $CONFIG"
  # Validate the config and its referenced files before any startup work.
  # exe/args paths resolve against cfg["cwd"] (the engine's working dir),
  # tokenizer against the server's cwd (this repo).
  CFG_CHECK="$(/usr/bin/python3 -I -S - "$CFG_ABS" "$REPO_ROOT" <<'PY'
import json, sys
from pathlib import Path
p, root = Path(sys.argv[1]), Path(sys.argv[2])
try:
    cfg = json.load(open(p, encoding="utf-8-sig"))
except Exception as e:
    print(f"config {p} does not parse: {e}"); sys.exit(1)
if not isinstance(cfg, dict):
    print(f"config {p} is not a JSON object"); sys.exit(1)
cwd = Path(cfg.get("cwd") or ".")
def find(v):                    # engine-side relative paths resolve on cfg["cwd"]
    q = Path(str(v))
    return q if q.is_absolute() else cwd / q
missing = []
exe = cfg.get("exe")
if not exe or not find(exe).is_file():
    missing.append(f'"exe": {exe!r}')
args = cfg.get("args")
if not isinstance(args, list):
    missing.append('"args": not a list')
else:
    # flags whose VALUE is a path (or FILE:SCALE list). --mtp is a path for file
    # models but a count for own-path (qwen36) configs — skip numerics.
    # --draft is a mode, --draft-costs is mutable state: neither binds a file.
    FILE_FLAGS = {"--pack", "--native", "--model", "--ple-gguf", "--native-dense-gguf",
                  "--native-head-gguf", "--embd-gguf", "--expert-profile", "--draft-model",
                  "--mtp-draft-vocab", "--control-vector", "--tokens-file",
                  "--spec-oracle", "--spec-follow"}
    for key, seq in (("args", args), ("user_args", cfg.get("user_args", []))):
        if not isinstance(seq, list):
            missing.append(f'"{key}": not a list')
            continue
        for i, a in enumerate(seq[:-1]):
            v = str(seq[i + 1])
            if a in FILE_FLAGS:
                if not find(v).exists():
                    missing.append(f"{key} {a} -> {v!r}")
            elif a == "--mtp" and not v.lstrip("-").isdigit() and not find(v).exists():
                missing.append(f"{key} --mtp -> {v!r}")
            elif a == "--control-vector-scaled":
                for item in v.split(','):
                    file, sep, scale = item.rpartition(':')
                    if not sep or not file or not scale or not find(file).is_file():
                        missing.append(f"{key} {a} -> {item!r}")
tok = cfg.get("tokenizer")
if tok:
    tdir = Path(str(tok)) if Path(str(tok)).is_absolute() else root / str(tok)
    for f in ("vocab.json", "merges.txt", "token_type.json"):
        if not (tdir / f).exists():
            missing.append(f'"tokenizer": {tok!r} missing {f}')
if missing:
    print("missing/unreadable: " + ", ".join(missing)); sys.exit(1)
print("OK:" + str(cfg.get("port", "")))
PY
)" || die "$CFG_CHECK"
  case "$CFG_CHECK" in OK:*)
    CFG_PORT="${CFG_CHECK#OK:}"
    [ -n "$PORT" ] || PORT="$CFG_PORT"
  ;; esac
  ARGS+=(strata --config "$CFG_ABS")
fi

[ -n "$PORT" ] && ARGS+=(--port "$PORT")
[ -n "$HOST" ] && ARGS+=(--host "$HOST")

info "starting: $VPY terminal/serve/server.py ${ARGS[*]}"
cd "$REPO_ROOT"
exec "$VPY" "$REPO_ROOT/terminal/serve/server.py" "${ARGS[@]}"
