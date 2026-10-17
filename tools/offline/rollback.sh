#!/usr/bin/env bash
# rollback.sh — swap strata-deploy/current back to the previous deployment.
#
# Usage:
#   tools/offline/rollback.sh [deploy-id] [--service strata-fork] [--no-restart]
#
# Without an argument it targets `previous` (maintained by deploy_local.sh).
# After the swap the manifest of the restored dir is verified
# (make_manifest.py --verify) — a drifted rollback target is refused.
# The service is restarted unless --no-restart.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
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
    -h|--help)    awk 'NR==1{next} /^[^#]/{exit} {print substr($0,3)}' "$0"; exit 0;;
    -*)           die "unknown option: $1";;
    *)            [ -n "$TARGET" ] && die "only one deploy-id argument"; TARGET="$1"; shift;;
  esac
done

[ -d "$DEPLOY_ROOT" ] || die "$DEPLOY_ROOT does not exist — nothing deployed"
[ -L "$DEPLOY_ROOT/current" ] || die "no current deployment"

if [ -z "$TARGET" ]; then
  [ -L "$DEPLOY_ROOT/previous" ] || die "no previous deployment recorded — pass a deploy-id explicitly"
  DEST="$(readlink -f "$DEPLOY_ROOT/previous")"
else
  DEST="$(readlink -f "$DEPLOY_ROOT/$TARGET" 2>/dev/null || echo "$DEPLOY_ROOT/$TARGET")"
fi
[ -d "$DEST" ] || die "rollback target missing: $DEST"
[ -f "$DEST/MANIFEST.json" ] || die "rollback target has no MANIFEST.json: $DEST"

CUR="$(readlink -f "$DEPLOY_ROOT/current")"
[ "$DEST" != "$CUR" ] || die "target is already current"

# Refuse to roll back onto drifted artifacts.
"$REPO_ROOT/.venv-offline/bin/python" "$REPO_ROOT/tools/offline/make_manifest.py" \
  --verify "$DEST/MANIFEST.json" || die "rollback target failed manifest verification — investigate before switching"

ln -sfnT "$DEST" "$DEPLOY_ROOT/current.new" && mv -T "$DEPLOY_ROOT/current.new" "$DEPLOY_ROOT/current"
ln -sfnT "$CUR" "$DEPLOY_ROOT/previous.new" && mv -T "$DEPLOY_ROOT/previous.new" "$DEPLOY_ROOT/previous"
info "current -> $DEST (was $CUR)"

if [ "$RESTART" = 1 ]; then
  if systemctl --user cat "$SERVICE.service" >/dev/null 2>&1; then
    systemctl --user restart "$SERVICE.service"
    sleep 1
    systemctl --user --no-pager status "$SERVICE.service" 2>&1 | head -5 || true
    info "restarted $SERVICE.service"
  else
    info "no user unit $SERVICE.service — swap done, start it by hand if intended"
  fi
else
  info "swap done (--no-restart) — restart deliberately: systemctl --user restart $SERVICE"
fi
