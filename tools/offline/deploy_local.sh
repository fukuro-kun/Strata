#!/usr/bin/env bash
# deploy_local.sh — stage a versioned deployment under ~/strata-deploy/ and
# switch the `current` symlink atomically (P3).
#
# A deploy dir contains: the engine binaries, the run config, MANIFEST.json
# and run.sh — the config's exe/cwd point INTO the deploy dir so a release is
# self-contained for rollback (the Python code stays in this checkout and is
# pinned by fork_sha in the manifest).
#
# Usage:
#   tools/offline/deploy_local.sh strata-<model>.json [--deploy-root DIR] [--no-unit] [--stage-only]
#
# `strata-deploy/previous` keeps the last `current` — rollback.sh swaps back.
# A systemd --user unit strata-fork.service (ExecStart=current/run.sh) is
# installed unless --no-unit; the service is NOT restarted automatically —
# that is the caller's deliberate step (or rollback's).

set -euo pipefail
# Attestierte Dateien (run.sh, Config, Staging) duerfen keine Rechte des
# Aufruf-umask erben — zwischen Erzeugung und Seal-Hash muss die Datei
# fremden Benutzern gegenueber geschlossen bleiben.
umask 022

REPO_ROOT="$(cd "$(/usr/bin/dirname "$0")/../.." && pwd)"
DEPLOY_ROOT="${STRATA_DEPLOY_ROOT:-$HOME/strata-deploy}"

die()  { echo "deploy_local: ERROR: $*" >&2; exit 1; }
info() { echo "deploy_local: $*"; }

export GIT_NO_LAZY_FETCH=1   # provenance git commands must never fetch

CONFIG=""
WITH_UNIT=1
STAGE_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --deploy-root) DEPLOY_ROOT="${2:?}"; shift 2;;
    --no-unit)     WITH_UNIT=0; shift;;
    --stage-only)  STAGE_ONLY=1; shift;;
    -h|--help)     /usr/bin/awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    -*)            die "unknown option: $1";;
    *)             [ -n "$CONFIG" ] && die "only one config argument"; CONFIG="$1"; shift;;
  esac
done
[ -n "$CONFIG" ] || die "usage: deploy_local.sh strata-<model>.json"
CFG_ABS="$(cd "$(/usr/bin/dirname "$CONFIG")" 2>/dev/null && pwd)/$(/usr/bin/basename "$CONFIG")"
[ -f "$CFG_ABS" ] || die "config not found: $CONFIG"

# All inputs must already be built/verified — this script never builds.
[ -x "$REPO_ROOT/terminal/engine/strata" ] || die "terminal/engine/strata missing — run tools/offline/build_engine.sh"
[ -f "$REPO_ROOT/terminal/engine/BUILD.json" ] || die "terminal/engine/BUILD.json missing"
[ -x "$REPO_ROOT/.venv-offline/bin/python" ] || die "offline venv missing — run tools/offline/make_venv.sh"

# The wheelhouse the venv was installed from must still verify — a deploy
# records deps hashes and must not describe tampered inputs.
[ -f "$REPO_ROOT/wheelhouse/MANIFEST.sha256" ] || die "wheelhouse/MANIFEST.sha256 missing"
( cd "$REPO_ROOT/wheelhouse" && /usr/bin/sha256sum --check --quiet MANIFEST.sha256 ) \
  || die "wheelhouse failed MANIFEST.sha256 verification"

/usr/bin/mkdir -p "$DEPLOY_ROOT" || die "cannot create deploy root"
DEPLOY_ROOT="$(cd "$DEPLOY_ROOT" && pwd -P)"
LOCK_DIR="$DEPLOY_ROOT/.strata-deploy.lock"
if ! /usr/bin/mkdir "$LOCK_DIR" 2>/dev/null; then
  [ -d "$LOCK_DIR" ] && die "deploy or rollback already running, or stale lock requires inspection"
  die "cannot create deploy lock in $DEPLOY_ROOT"
fi
release_lock() {
  /usr/bin/rmdir "$LOCK_DIR" 2>/dev/null || echo "deploy_local: lock could not be released: $LOCK_DIR" >&2
}
trap release_lock EXIT

# The commit the deploy will be sealed under — the manifest refuses a dirty
# tree or a moved HEAD at seal time, so the id still matches the real state.
FORK_SHA="$(/usr/bin/python3 -I -S "$REPO_ROOT/tools/offline/make_manifest.py" --print-head-sha)" \
  || die "could not determine HEAD sha"
ID="${FORK_SHA:0:8}-$(/usr/bin/date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEPLOY_ROOT/$ID"
{ [ -e "$DEST" ] || [ -L "$DEST" ]; } && die "$DEST already exists — deploy-id collision (same second); retry"

info "staging $DEST"
# Die Anlage muss atomar sein: ein zweiter Lauf darf nie dasselbe Ziel teilen.
# Fehlgeschlagenes Staging bleibt zur Pruefung liegen und wird nicht geloescht.
/usr/bin/mkdir "$DEST" || die "staging directory already exists or cannot be created: $DEST"
/usr/bin/cp -a "$REPO_ROOT/terminal/engine/strata" "$REPO_ROOT/terminal/engine/BUILD.json" "$DEST/"
[ -f "$REPO_ROOT/terminal/engine/strata-vision" ] && /usr/bin/cp -a "$REPO_ROOT/terminal/engine/strata-vision" "$DEST/"

# Config copy with exe/cwd re-pointed into the deploy dir (paths like
# --pack/--mtp/model stay absolute — data is versioned by the manifest, not
# copied here). After the rewrite every referenced binary must exist in
# the deploy dir — a config naming something we did not stage is an error.
/usr/bin/python3 -I -S - "$CFG_ABS" "$DEST" <<'PY'
import json, os, sys
from pathlib import Path
src, dest = Path(sys.argv[1]), Path(sys.argv[2])
cfg = json.loads(src.read_text(encoding="utf-8-sig"))
exe = Path(cfg.get("exe") or "strata").name
cfg["exe"] = str(dest / exe)
cfg["cwd"] = str(dest)
staged = {f.name for f in dest.iterdir() if f.is_file()}
if exe not in staged:
    sys.exit(f"config exe basename {exe!r} was not staged into {dest}")
v = cfg.get("vision")
if isinstance(v, dict) and v.get("exe"):
    vname = Path(v["exe"]).name
    if vname not in staged:
        sys.exit(f"config vision.exe {vname!r} was not staged into {dest} "
                 "(terminal/engine/strata-vision missing? rebuild or strip the vision section)")
    v["exe"] = str(dest / vname)
out = dest / src.name
tmp = dest / (src.name + ".tmp")
tmp.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
os.replace(tmp, out)
print(f"config -> {out}")
PY

# Pinned args: a *-required-args.json in the deploy root whose "config_name"
# matches the staged config restores args a rewrite dropped or changed
# (reserves, budgets, context set by hand). Opt-in: no file, no change.
/usr/bin/python3 -I -S "$REPO_ROOT/tools/offline/reapply_required_args.py" \
  --config "$DEST/$(/usr/bin/basename "$CFG_ABS")" --required-dir "$DEPLOY_ROOT" \
  || die "required-args check failed — deploy aborted"

/usr/bin/cat > "$DEST/run.sh" <<EOF
#!/bin/sh
# generated by deploy_local.sh ($ID) — engine + config live in this dir
exec "$REPO_ROOT/tools/offline/run_server.sh" "$DEST/$(/usr/bin/basename "$CFG_ABS")" "\$@"
EOF
/usr/bin/chmod +x "$DEST/run.sh"

# Seal last: the manifest attests the staged binaries, the rewritten config
# and run.sh — then verify that exact dir before the pointer moves.
/usr/bin/python3 -I -S "$REPO_ROOT/tools/offline/make_manifest.py" \
  --deploy-dir "$DEST" --config "$(/usr/bin/basename "$CFG_ABS")" \
  --out "$DEST/MANIFEST.json" || die "manifest sealing failed"
/usr/bin/python3 -I -S "$REPO_ROOT/tools/offline/make_manifest.py" \
  --verify "$DEST/MANIFEST.json" || die "deploy self-verification failed"

if [ "$STAGE_ONLY" = 1 ]; then
  info "sealed $DEST (--stage-only; current, previous and units unchanged)"
  exit 0
fi

# Atomic switch: build the new symlink aside, then rename over `current`.
# -T everywhere: a stray real directory must never swallow the link.
PREV=""
[ -L "$DEPLOY_ROOT/current" ] && PREV="$(/usr/bin/readlink -f "$DEPLOY_ROOT/current")"
/usr/bin/ln -sfnT "$DEST" "$DEPLOY_ROOT/current.new" && /usr/bin/mv -T "$DEPLOY_ROOT/current.new" "$DEPLOY_ROOT/current"
if [ -n "$PREV" ] && [ "$PREV" != "$DEST" ]; then
  /usr/bin/ln -sfnT "$PREV" "$DEPLOY_ROOT/previous.new" && /usr/bin/mv -T "$DEPLOY_ROOT/previous.new" "$DEPLOY_ROOT/previous"
fi
info "current -> $DEST (previous: ${PREV:-none})"

if [ "$WITH_UNIT" = 1 ]; then
  UDIR="$HOME/.config/systemd/user"
  /usr/bin/mkdir -p "$UDIR"
  /usr/bin/cat > "$UDIR/strata-fork.service" <<EOF
# generated by deploy_local.sh ($ID) — delete with the deployment
[Unit]
Description=Strata fork server (offline build, $REPO_ROOT)

[Service]
Type=simple
ExecStart=$DEPLOY_ROOT/current/run.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
  info "user unit written: $UDIR/strata-fork.service (systemctl --user {start,restart} strata-fork)"
fi

info "deployed $ID — restart the service deliberately: systemctl --user restart strata-fork"
