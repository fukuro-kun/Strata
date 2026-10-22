"""Deterministic SHA-256 (truncated to 16 hex) over selected source trees.

Each file contributes relpath + NUL + normalized content (CRLF -> LF), seeded
with the pinned commit SHA so two trees at different commits can never
collide. Used to prove that A/B sandbox source copies are identical.

Example:
  python3 tools/upstream/source_hash.py --root /tmp/armA/src \
    --pin <commit-sha> --parts tools/vision
  python3 tools/upstream/source_hash.py --root /tmp/armA/src \
    --pin <commit-sha> --parts CMakeLists.txt cmake src include third_party/ggml
"""

import argparse
import hashlib
import sys
from pathlib import Path


def source_hash(root, parts, pin):
    h = hashlib.sha256(pin.encode())
    root = Path(root)
    for part in parts:
        base = root / part
        if not base.exists():
            sys.exit(f"error: missing path {base}")
        files = [base] if base.is_file() else sorted(
            f for f in base.rglob("*") if f.is_file())
        for f in files:
            h.update(f.relative_to(root).as_posix().encode() + b"\0"
                     + f.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", required=True)
    ap.add_argument("--pin", required=True, help="gepinnter Commit-SHA")
    ap.add_argument("--parts", nargs="+", required=True,
                    help="relative Pfade unter --root")
    ns = ap.parse_args()
    print(source_hash(ns.root, ns.parts, ns.pin))


if __name__ == "__main__":
    main()
