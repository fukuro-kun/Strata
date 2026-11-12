#!/usr/bin/env python3
"""Erzeuge aus festen Pins und dem Wheel-Manifest eine pip-Hashliste."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.+-]+\.whl)$")
PIN_LINE = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+!]*)'
    r'(?:\s*;\s*((?:python_version|sys_platform)\s*(?:==|!=|>=|<=|>|<)\s*"'
    r'[A-Za-z0-9_.+-]+"))?$'
)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def manifest_hashes(text: str) -> dict[tuple[str, str], list[str]]:
    hashes: dict[tuple[str, str], list[str]] = {}
    filenames = set()
    for line in text.splitlines():
        match = MANIFEST_LINE.fullmatch(line)
        if not match:
            raise ValueError("ungueltiger Eintrag im Wheel-Manifest")
        digest, filename = match.groups()
        if filename in filenames:
            raise ValueError("doppelter Wheel-Eintrag im Manifest")
        filenames.add(filename)
        parts = filename[:-4].split("-")
        if len(parts) not in (5, 6) or any(not part for part in parts):
            raise ValueError("ungueltiger Wheel-Dateiname im Manifest")
        key = (canonical(parts[0]), parts[1].replace("_", "-").lower())
        hashes.setdefault(key, []).append(digest)
    if not filenames:
        raise ValueError("leeres Wheel-Manifest")
    return hashes


def lock_requirements(hashes: dict[tuple[str, str], list[str]], text: str) -> str:
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"ungueltiger Abhaengigkeits-Pin in Zeile {number}")
        name, version, marker = match.groups()
        key = (canonical(name), version.replace("_", "-").lower())
        # PEP-440-Localversionen ("2.4.0+cu121") matchen Wheel-Namen
        # ("2.4.0_cu121" -> "2.4.0-cu121") bewusst nicht: ohne Hash
        # scheitert --require-hashes fail-closed statt falsch zuzuordnen.
        pin = f"{name}=={version}" + (f"; {marker}" if marker else "")
        pin += "".join(f" --hash=sha256:{digest}" for digest in hashes.get(key, []))
        lines.append(pin)
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--check-manifest", action="store_true")
    parser.add_argument("requirements", nargs="*", type=Path)
    args = parser.parse_args()
    if args.check_manifest and args.requirements:
        parser.error("--check-manifest erwartet keine Requirements-Dateien")
    try:
        hashes = manifest_hashes(args.manifest.read_text(encoding="ascii"))
        if args.check_manifest:
            return 0
        if args.requirements:
            text = "\n".join(path.read_text(encoding="utf-8") for path in args.requirements)
        else:
            text = sys.stdin.read()
        sys.stdout.write(lock_requirements(hashes, text))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"offline requirements: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
