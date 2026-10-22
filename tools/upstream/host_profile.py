"""Print only approved, non-secret runtime fields of a Strata fork config.

Secrets are never printed: --api-key/-like args are replaced by <REDACTED>
(both --flag=value and --flag value forms). The config's SHA-256 is included
so the dumped profile can be tied to a pinned input.

Example:
  python3 tools/upstream/host_profile.py --config /path/to/host.fork.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

SAFE_KEYS = ("exe", "pack", "tokenizer", "model", "parallel", "host", "port",
             "context", "ctx", "max_context", "engine", "mmap_experts")
SECRET_HINTS = ("api-key", "password", "secret", "access-token")


def redact_args(args):
    safe = []
    hide_next = False
    for arg in args:
        text = str(arg)
        if hide_next:
            safe.append("<REDACTED>")
            hide_next = False
        elif text.startswith("-") and any(
            hint in text.lower() for hint in SECRET_HINTS
        ):
            if "=" in text:
                safe.append(text.split("=", 1)[0] + "=<REDACTED>")
            else:
                safe.append(text)
                hide_next = True
        else:
            safe.append(text)
    return safe


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ns = ap.parse_args()
    if not ns.config.is_file():
        sys.exit(f"error: config not found: {ns.config}")
    raw = ns.config.read_bytes()
    config = json.loads(raw)
    result = {"config_sha256": hashlib.sha256(raw).hexdigest()}
    for key in SAFE_KEYS:
        if key in config:
            result[key] = config[key]
    result["args"] = redact_args(config.get("args", []))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
