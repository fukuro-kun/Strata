#!/usr/bin/env bash
# run_server.sh — start the Strata server without setup.py, from the offline
# venv only.
#
# FORK POLICY: replaces upstream's generated run-<model>.sh. Same call shape
# (.venv python -> serve/server.py --engine strata --config X --port Y) but
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

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
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
[ -f "$REPO_ROOT/serve/server.py" ] || die "serve/server.py not found — wrong checkout?"

ARGS=(--engine)
if [ "$MOCK" = 1 ]; then
  ARGS+=(mock)
else
  [ -n "$CONFIG" ] || die "no config given — usage: run_server.sh strata-<model>.json [--port N]"
  CFG_ABS="$(cd "$(dirname "$CONFIG")" 2>/dev/null && pwd)/$(basename "$CONFIG")"
  [ -f "$CFG_ABS" ] || die "config not found: $CONFIG"
  # Validate the config and its referenced files before any startup work.
  # exe/args paths resolve against cfg["cwd"] (the engine's working dir),
  # tokenizer against the server's cwd (this repo).
  CFG_CHECK="$("$VPY" - "$CFG_ABS" "$REPO_ROOT" <<'PY'
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
    # flags whose VALUE is a path (or file:scale). --mtp is a path for file
    # models but a count for own-path (qwen36) configs — skip numerics.
    FILE_FLAGS = {"--pack", "--native", "--ple-gguf", "--native-dense-gguf",
                  "--embd-gguf", "--expert-profile", "--draft"}
    for i, a in enumerate(args[:-1]):
        v = str(args[i + 1])
        if a in FILE_FLAGS:
            if not find(v).exists():
                missing.append(f"args {a} -> {v!r}")
        elif a == "--mtp" and not v.lstrip("-").isdigit() and not find(v).exists():
            missing.append(f"args --mtp -> {v!r}")
        elif a == "--control-vector-scaled" and not find(v.rsplit(":", 1)[0]).exists():
            missing.append(f"args --control-vector-scaled -> {v!r}")
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

info "starting: $VPY serve/server.py ${ARGS[*]}"
cd "$REPO_ROOT"
exec "$VPY" "$REPO_ROOT/serve/server.py" "${ARGS[@]}"
