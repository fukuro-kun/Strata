#!/usr/bin/env python3
"""reapply_required_args.py — restore required args in a strata run config.

A run config (strata-<model>.json / *.fork.json) is edited by hand in this
fork (reserves, budgets, context) and tools that rewrite the file can lose
those edits: a config regenerated from a stale template, or a manual edit
based on an old copy. A <name>-required-args.json file pins the args that
must be present; this tool puts back whatever a rewrite dropped or changed:

    required {"--flag": null}    -> the flag must be in args (added if absent)
    required {"--key": "value"}  -> key+value must be in args (value fixed or
                                    appended if absent — at the position a
                                    forbidden flag was removed, else at the end)
    forbidden ["--flag"]         -> the flag is removed (with a following
                                    non-flag token, treated as its value)

Duplicate keys: the engine takes the LAST occurrence — a config that gained a
second "--key <other>" silently overrides the pin. Every occurrence is checked
and duplicates are collapsed to the pinned value.

Usage:
    reapply_required_args.py --config PATH [--required PATH | --required-dir DIR]
                             [--dry-run]

With --required-dir every *-required-args.json whose "config_name" matches the
config's basename is applied; without any required file the config is left
alone and the tool exits 0. Deploys call it from deploy_local.sh so a pinned
arg set survives every staging. A required file that cannot be read or fails
validation stops the run (fail closed): a deploy that believes pins are active
must not run unprotected.

Exit codes: 0 config conform or successfully corrected | 1 error |
            2 --dry-run found deviations (nothing written).
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path


def fail(msg):
    sys.exit(f"reapply_required_args: {msg}")


def load_required(path: Path) -> dict:
    """Read and validate a required-args file (hard fail on any problem)."""
    try:
        spec = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as e:
        fail(f"{path}: unreadable ({e})")
    if not isinstance(spec, dict) or not isinstance(spec.get("config_name"), str):
        fail(f"{path}: missing \"config_name\"")
    req, forb = spec.get("required", {}), spec.get("forbidden", [])
    if not isinstance(req, dict) or not isinstance(forb, list):
        fail(f"{path}: \"required\" must be an object, \"forbidden\" a list")
    for k, v in req.items():
        if not (isinstance(k, str) and k.startswith("--")):
            fail(f"{path}: required key {k!r} is not a --flag")
        if v is not None and not isinstance(v, (str, int, float)):
            fail(f"{path}: required value for {k} must be a scalar or null")
    for f in forb:
        if not (isinstance(f, str) and f.startswith("--")):
            fail(f"{path}: forbidden entry {f!r} is not a --flag")
    both = set(req) & set(forb)
    if both:
        fail(f"{path}: {sorted(both)} in required and forbidden")
    return spec


def apply_required(args: list, required: dict, forbidden: list) -> tuple:
    """Return (new_args, changes). New tokens go where a forbidden flag was
    removed (keeps diffs against the previous config clean), else at the end."""
    args = [str(x) for x in args]
    changes = []
    insert_at = None

    for flag in forbidden:
        while flag in args:
            i = args.index(flag)
            insert_at = i
            nxt = args[i + 1] if i + 1 < len(args) else None
            if nxt is not None and not nxt.startswith("--"):
                del args[i:i + 2]
                changes.append(f"removed {flag} {nxt}")
            else:
                del args[i]
                changes.append(f"removed {flag}")

    def add(key, want):
        nonlocal insert_at
        toks = [key] + ([want] if want is not None else [])
        if insert_at is None:
            args.extend(toks)
        else:
            args[insert_at:insert_at] = toks
            insert_at += len(toks)

    for key, want in required.items():
        want = None if want is None else str(want)
        hits = [i for i, t in enumerate(args) if t == key]
        if want is None:
            if not hits:
                add(key, None)
                changes.append(f"added {key}")
            elif len(hits) > 1:
                for i in reversed(hits[1:]):
                    del args[i]
                changes.append(f"{key}: {len(hits)} duplicates collapsed")
            continue
        if hits:
            i = hits[0]
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                args.insert(i + 1, want)
                changes.append(f"{key}: added value {want}")
            elif args[i + 1] != want:
                old = args[i + 1]
                args[i + 1] = want
                changes.append(f"{key}: {old} -> {want}")
            for j in reversed(hits[1:]):              # last-wins: duplicates would
                del args[j:j + 2]                      # silently override the pin
            if len(hits) > 1:
                changes.append(f"{key}: {len(hits) - 1} duplicate(s) removed")
        else:
            add(key, want)
            changes.append(f"added {key} {want}")

    return args, changes


def required_files(directory: Path, cfg_name: str) -> list:
    out = []
    for p in sorted(directory.glob("*-required-args.json")):
        try:
            spec = json.loads(p.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            fail(f"{p}: unreadable ({e})")
        if isinstance(spec, dict) and spec.get("config_name") == cfg_name:
            out.append(p)
        elif not isinstance(spec, dict) or "config_name" not in spec:
            fail(f"{p}: missing \"config_name\"")
    return out


def write_config_atomic(path: Path, cfg: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak-{stamp}")
    n = 1
    while bak.exists():
        n += 1
        bak = path.with_suffix(path.suffix + f".bak-{stamp}-{n}")
    return bak


def apply_one(cfg_path: Path, req_path: Path, dry: bool) -> int:
    spec = load_required(req_path)
    if spec["config_name"] != cfg_path.name:
        fail(f"{req_path.name}: config_name {spec['config_name']!r} does not match {cfg_path.name}")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as e:
        fail(f"{cfg_path}: unreadable ({e})")
    args = cfg.get("args")
    if args is None:
        args = []
        print(f"WARN: {cfg_path.name} has no \"args\" — pins will be added", file=sys.stderr)
    elif not isinstance(args, list):
        fail(f"{cfg_path}: \"args\" is not a list")
    new_args, changes = apply_required(
        args, spec.get("required", {}), spec.get("forbidden", []))
    if not changes:
        print(f"OK conform: {cfg_path.name} vs {req_path.name}")
        return 0
    print(f"{len(changes)} deviation(s) in {cfg_path.name} (vs {req_path.name}):")
    for c in changes:
        print(f"  - {c}")
    if dry:
        print("dry-run: nothing written")
        return 2
    bak = backup_path(cfg_path)
    shutil.copy2(cfg_path, bak)
    cfg["args"] = new_args
    write_config_atomic(cfg_path, cfg)
    print(f"written: {cfg_path} (backup: {bak.name})")
    return 0


def main() -> int:
    argv = sys.argv[1:]

    def opt(name):
        if name not in argv:
            return None
        i = argv.index(name)
        if i + 1 >= len(argv):
            fail(f"{name} needs a value")
        return argv[i + 1]

    if "--config" not in argv or "-h" in argv or "--help" in argv:
        sys.exit(__doc__)
    dry = "--dry-run" in argv
    cfg_path = Path(opt("--config"))
    if not cfg_path.exists():
        fail(f"config not found: {cfg_path}")

    if opt("--required") and opt("--required-dir"):
        fail("use --required or --required-dir, not both")
    reqs = [Path(opt("--required"))] if opt("--required") else (
        required_files(Path(opt("--required-dir")), cfg_path.name)
        if opt("--required-dir") else [])
    if not reqs:
        print(f"no required-args file for {cfg_path.name} — left alone")
        return 0

    rc = 0
    for r in reqs:
        rc = max(rc, apply_one(cfg_path, r, dry))
    return rc


if __name__ == "__main__":
    sys.exit(main())
