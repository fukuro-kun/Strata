#!/usr/bin/env python3
"""Validate that a restored production unit is healthy after a test window.

Reads the API key strictly in-memory from the running process environ/cmdline
(never printed or persisted), probes /health, /slots and a deterministic
chat completion, and writes evidence JSON into the run directory.

Usage: restore_validate.py <run_dir> <pid> [port]
"""

import json
import os
import sys
import urllib.request


def find_token(pid):
    try:
        env = open(f"/proc/{pid}/environ", "rb").read()
        for item in env.split(b"\0"):
            if item.startswith(b"STRATA_API_KEY="):
                tok = item.split(b"=", 1)[1].decode().split(",")[0].strip()
                if tok:
                    return tok
    except OSError:
        pass
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode(
            errors="replace").split("\0")
        for i, a in enumerate(cmd):
            if a == "--api-key" and i + 1 < len(cmd):
                tok = cmd[i + 1].split(",")[0].strip()
                if tok:
                    return tok
            elif a.startswith("--api-key="):
                tok = a.split("=", 1)[1].split(",")[0].strip()
                if tok:
                    return tok
    except OSError:
        pass
    return None


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: restore_validate.py <run_dir> <pid> [port]")
    run, pid = sys.argv[1], sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 18086

    tok = find_token(pid)
    if not tok:
        print("AUTH_SOURCE_ABSENT")
        sys.exit(3)

    def req(path, payload=None, timeout=60):
        hdrs = {"Authorization": "Bearer " + tok}
        if payload is not None:
            hdrs["Content-Type"] = "application/json"
        r = urllib.request.Request(
            f"http://127.0.0.1:{port}" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=hdrs)
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode()

    res = {}
    try:
        st, body = req("/health")
        with open(os.path.join(run, "health.json"), "w") as f:
            f.write(body)
        res["health_http"] = st
        res["loaded"] = json.loads(body).get("loaded")
    except Exception as e:
        res["health_error"] = type(e).__name__
    try:
        st, body = req("/slots")
        with open(os.path.join(run, "slots.json"), "w") as f:
            f.write(body)
        res["slots_http"] = st
        res["slots_nonempty"] = bool(json.loads(body))
    except Exception as e:
        res["slots_error"] = type(e).__name__

    payload = {"model": "strata",
               "messages": [{"role": "user",
                             "content": "Reply with exactly: RESTORE_OK"}],
               "max_tokens": 64, "temperature": 0, "top_p": 1, "min_p": 0,
               "seed": 7, "reasoning_effort": "none",
               "chat_template_kwargs": {"enable_thinking": False}}
    try:
        st, body = req("/v1/chat/completions", payload, timeout=600)
        with open(os.path.join(run, "chat-restore.json"), "w") as f:
            f.write(body)
        content = json.loads(body)["choices"][0]["message"].get("content") or ""
        res["chat_http"] = st
        res["content_nonempty"] = bool(content.strip())
        res["restore_marker"] = "RESTORE_OK" in content
    except Exception as e:
        res["chat_error"] = type(e).__name__

    with open(os.path.join(run, "api-result.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("VALIDATION:", json.dumps(res))


if __name__ == "__main__":
    main()
