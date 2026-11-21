#!/usr/bin/env bash
# rollback.sh — swap strata-deploy/current back to the previous deployment.
#
# Usage:
#   tools/offline/rollback.sh [deploy-id] [--deploy-root DIR]
#                             [--service strata-fork] [--no-restart]
#
# Without an argument it targets `previous` (maintained by deploy_local.sh).
# The target's manifest is verified BEFORE the swap
# (make_manifest.py --verify) — a drifted rollback target is refused.
# The service is restarted unless --no-restart.

set -euo pipefail
umask 022

REPO_ROOT="$(cd "$(/usr/bin/dirname "$0")/../.." && pwd)"
DEPLOY_ROOT="${STRATA_DEPLOY_ROOT:-$HOME/strata-deploy}"

die()  { echo "rollback: ERROR: $*" >&2; exit 1; }
info() { echo "rollback: $*"; }

export GIT_NO_LAZY_FETCH=1

TARGET=""
SERVICE="strata-fork"
RESTART=1
while [ $# -gt 0 ]; do
  case "$1" in
    --deploy-root) DEPLOY_ROOT="${2:?}"; shift 2;;
    --service)    SERVICE="${2:?}"; SERVICE="${SERVICE%.service}"; shift 2;;
    --no-restart) RESTART=0; shift;;
    -h|--help)    /usr/bin/awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    -*)           die "unknown option: $1";;
    *)            [ -n "$TARGET" ] && die "only one deploy-id argument"; TARGET="$1"; shift;;
  esac
done

[ -d "$DEPLOY_ROOT" ] || die "$DEPLOY_ROOT does not exist — nothing deployed"
DEPLOY_ROOT="$(cd "$DEPLOY_ROOT" && pwd -P)"
LOCK_DIR="$DEPLOY_ROOT/.strata-deploy.lock"
if ! /usr/bin/mkdir "$LOCK_DIR" 2>/dev/null; then
  [ -d "$LOCK_DIR" ] && die "deploy or rollback already running, or stale lock requires inspection"
  die "cannot create deploy lock in $DEPLOY_ROOT"
fi
release_lock() {
  /usr/bin/rmdir "$LOCK_DIR" 2>/dev/null || echo "rollback: lock could not be released: $LOCK_DIR" >&2
}
trap release_lock EXIT
[ -L "$DEPLOY_ROOT/current" ] || die "no current deployment"

if [ -z "$TARGET" ]; then
  [ -L "$DEPLOY_ROOT/previous" ] || die "no previous deployment recorded — pass a deploy-id explicitly"
  DEST="$(/usr/bin/readlink -f "$DEPLOY_ROOT/previous")"
else
  [[ "$TARGET" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "invalid deploy-id"
  DEST="$(/usr/bin/readlink -f "$DEPLOY_ROOT/$TARGET" 2>/dev/null || echo "$DEPLOY_ROOT/$TARGET")"
fi
[ "${DEST%/*}" = "$DEPLOY_ROOT" ] || die "rollback target must be a direct child of the deploy root"
[ -d "$DEST" ] || die "rollback target missing: $DEST"
[ -f "$DEST/MANIFEST.json" ] || die "rollback target has no MANIFEST.json: $DEST"

CUR="$(/usr/bin/readlink -f "$DEPLOY_ROOT/current")"
[ "${CUR%/*}" = "$DEPLOY_ROOT" ] || die "current must be a direct child of the deploy root"
[ "$DEST" != "$CUR" ] || die "target is already current"

# Refuse to roll back onto drifted artifacts.
/usr/bin/python3 -I -S "$REPO_ROOT/tools/offline/make_manifest.py" \
  --verify "$DEST/MANIFEST.json" \
  || die "rollback target failed verification; restore and verify the matching checkout and venv before switching"

/usr/bin/ln -sfnT "$DEST" "$DEPLOY_ROOT/current.new" && /usr/bin/mv -T "$DEPLOY_ROOT/current.new" "$DEPLOY_ROOT/current"
/usr/bin/ln -sfnT "$CUR" "$DEPLOY_ROOT/previous.new" && /usr/bin/mv -T "$DEPLOY_ROOT/previous.new" "$DEPLOY_ROOT/previous"
info "current -> $DEST (was $CUR)"

if [ "$RESTART" = 1 ]; then
  if /usr/bin/systemctl --user cat "$SERVICE.service" >/dev/null 2>&1; then
    /usr/bin/systemctl --user restart "$SERVICE.service"
    /usr/bin/sleep 1
    /usr/bin/systemctl --user --no-pager status "$SERVICE.service" 2>&1 | /usr/bin/head -5 || true
    info "restarted $SERVICE.service"
  else
    info "no user unit $SERVICE.service — swap done, start it by hand if intended"
  fi
else
  info "swap done (--no-restart) — restart deliberately: systemctl --user restart $SERVICE"
fi
