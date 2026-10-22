#!/usr/bin/env bash
# Parity window runner — executes an approved parity matrix in a rootless,
# networkless podman sandbox, then restores the production unit on ANY exit
# path (trap). Parameterized via env vars; refuses to run with unset paths.
#
# Required env:
#   AB_BUILDS    build tree root containing armA/ and armB/
#   AB_ROOTFS    sandbox rootfs image path
#   AB_UNIT      production systemd unit to stop/restore
#   AB_CONF      production fork config (sha256 recorded, api key read in-mem)
#   AB_DEVICES   space-separated GPU device indexes, e.g. "0 1"
#   AB_SPLITS    space-separated STRATA_HC_SPLIT values, e.g. "1 2"
#   AB_RUN_DIR   output dir (created fresh; refuses to reuse)
# Optional:
#   AB_EXTRA_ENV extra env assignments for the payload, space-separated
set -uo pipefail

: "${AB_BUILDS:?set AB_BUILDS}"
: "${AB_ROOTFS:?set AB_ROOTFS}"
: "${AB_UNIT:?set AB_UNIT}"
: "${AB_CONF:?set AB_CONF}"
: "${AB_DEVICES:?set AB_DEVICES}"
: "${AB_SPLITS:?set AB_SPLITS}"
: "${AB_RUN_DIR:?set AB_RUN_DIR}"

B="$AB_BUILDS"; ROOTFS="$AB_ROOTFS"; UNIT="$AB_UNIT"; CONF="$AB_CONF"
RUN="$AB_RUN_DIR"
if [ -e "$RUN" ]; then echo "ABORT: $RUN already exists"; exit 2; fi
mkdir -p "$RUN/logs"
exec > >(tee -a "$RUN/run.log") 2>&1
echo "RUN=$RUN  start=$(date -u +%FT%TZ)"

snap() {
  nvidia-smi > "$RUN/nvidia-$1.txt" 2>&1
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv >> "$RUN/nvidia-$1.txt" 2>&1
}

restore() {
  echo "[$(date -u +%FT%TZ)] RESTORE: sudo -n systemctl start $UNIT"
  sudo -n systemctl start "$UNIT"
  echo "restore_rc=$?"
}
trap restore EXIT

echo "=== pre-state ==="
systemctl show "$UNIT" -p Id,ActiveState,SubState,MainPID,LimitMEMLOCK | tee "$RUN/prestate.txt"
sha256sum "$CONF" | tee -a "$RUN/prestate.txt"

{
  for arm in armA armB; do
    sha256sum "$B/$arm/src/engine/strata" "$B/$arm/src/engine/libstrata_kq.so" "$B/$arm/build/gr_parity"
  done
} > "$RUN/meta.txt"
cat "$RUN/meta.txt"

snap pre

echo "=== STOP production $UNIT ==="
if ! sudo -n systemctl stop "$UNIT"; then echo "STOP_FAILED"; exit 10; fi
for i in $(seq 1 60); do
  [ "$(systemctl is-active "$UNIT" 2>/dev/null)" = "inactive" ] && break
  sleep 2
done
systemctl show "$UNIT" -p ActiveState,SubState
snap stopped

FREE=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | wc -l)
MEM=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | awk '{s+=$1} END{print s}')
echo "compute_apps=$FREE mem_used_mib_total=$MEM"
if [ "${FREE:-9}" -ne 0 ] || [ "${MEM:-999999}" -gt 2048 ]; then
  echo "ABORT: GPUs not free after stop"; exit 11
fi

for arm in armA armB; do
  for d in $AB_DEVICES; do
    for s in $AB_SPLITS; do
      name="parity-${arm}-gpu${d}-hc${s}"
      echo "=== RUN $name $(date -u +%FT%TZ) ==="
      cmd=(sudo -n systemd-run --quiet --wait --pipe --collect
        --unit="${name}-$$" --service-type=exec --uid="$USER"
        -E "HOME=$HOME" -E "XDG_RUNTIME_DIR=/run/user/$(id -u)"
        -p LimitMEMLOCK=infinity -p RuntimeMaxSec=300
        -- podman run --rm --network none --read-only
        --cap-drop=ALL --security-opt=no-new-privileges --tmpfs /tmp
        --ulimit memlock=-1:-1
        -v /usr:/usr:ro -v "$B/$arm/src:/src:ro" -v "$B/$arm/build:/build:ro"
        --device /dev/nvidia0 --device /dev/nvidia1
        --device /dev/nvidiactl --device /dev/nvidia-uvm --device /dev/nvidia-uvm-tools
        --rootfs "$ROOTFS" /usr/bin/env -i
        "PATH=/usr/local/cuda-13.0/bin:/usr/bin:/bin" HOME=/tmp TMPDIR=/tmp
        "LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64:/src/engine"
        "CUDA_VISIBLE_DEVICES=$d" "STRATA_HC_SPLIT=$s"
        ${AB_EXTRA_ENV:-}
        /build/gr_parity --selftest)
      echo "+ ${cmd[*]}"
      "${cmd[@]}" > "$RUN/logs/$name.log" 2>&1
      rc=$?
      echo "$rc" > "$RUN/logs/$name.rc"
      echo "$name rc=$rc"
      tail -20 "$RUN/logs/$name.log"
      if [ "$rc" -ne 0 ]; then echo "ABORT: nonzero rc at $name"; exit 20; fi
      if grep -qE "MISMATCH|PARITY.*FAIL|\bFAIL(ED|URE)?\b" "$RUN/logs/$name.log"; then
        echo "ABORT: parity mismatch marker in $name"; exit 21
      fi
    done
  done
done
echo "=== matrix complete ==="
snap postmatrix

echo "=== RESTORE production ==="
restore

echo "=== readiness wait (<=1800s) + http validation ==="
python3 - "$CONF" "$RUN" <<'PYEOF'
import json, sys, time, urllib.request, urllib.error
conf_path, run = sys.argv[1:3]
with open(conf_path) as f:
    cfg = json.load(f)
key = cfg.get("api_key")
keys = key if isinstance(key, list) else (key.split(",") if isinstance(key, str) else [])
tok = keys[0].strip() if keys else None
res = {"api_key_present": bool(tok)}

def req(path, payload=None, timeout=30):
    hdrs = {}
    if tok: hdrs["Authorization"] = "Bearer " + tok
    if payload is not None: hdrs["Content-Type"] = "application/json"
    r = urllib.request.Request("http://127.0.0.1:18086" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=hdrs)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read().decode()

if not tok:
    print("API_AUTH_NOT_FROM_CONFIG — skipping http validation per spec")
    sys.exit(3)

deadline = time.time() + 1800
health_ok = False
while time.time() < deadline:
    try:
        st, body = req("/health", timeout=20)
        with open(run + "/health.json", "w") as f:
            f.write(body)
        d = json.loads(body)
        if st == 200 and d.get("loaded", True):
            health_ok = True
            break
    except Exception:
        pass
    time.sleep(10)
res["health_ready"] = health_ok
try:
    st, body = req("/slots", timeout=20)
    with open(run + "/slots.json", "w") as f:
        f.write(body)
    res["slots_http"] = st
except Exception as e:
    res["slots_error"] = type(e).__name__

if health_ok:
    payload = {"model": "strata", "messages": [{"role": "user", "content": "Reply with exactly: RESTORE_OK"}],
               "max_tokens": 64, "temperature": 0, "top_p": 1, "min_p": 0, "seed": 7,
               "reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}
    try:
        st, body = req("/v1/chat/completions", payload, timeout=600)
        with open(run + "/chat-restore.json", "w") as f:
            f.write(body)
        d = json.loads(body)
        content = d["choices"][0]["message"].get("content") or ""
        res["chat_http"] = st
        res["content_nonempty"] = bool(content.strip())
        res["restore_marker"] = "RESTORE_OK" in content
    except Exception as e:
        res["chat_error"] = type(e).__name__
with open(run + "/api-result.json", "w") as f:
    json.dump(res, f, indent=1)
print("VALIDATION:", json.dumps(res))
PYEOF
pyrc=$?
echo "validation_py_rc=$pyrc"

echo "=== post-state ==="
systemctl show "$UNIT" -p Id,ActiveState,SubState,MainPID,LimitMEMLOCK | tee "$RUN/poststate.txt"
sha256sum "$CONF" | tee -a "$RUN/poststate.txt"
snap restored
echo "DONE run=$(date -u +%FT%TZ) RUN=$RUN"
