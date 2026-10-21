#!/usr/bin/env python3
"""make_manifest.py — write the immutable build/model manifest for a deploy
state (P3).

Collects every hash that defines this deployment: fork commit + diff vs the
reviewed baseline, the pinned llama.cpp source, toolchain versions, wheel
hashes, engine binary hashes, and model/pack provenance. Output:
MANIFEST.json next to the staged artifacts.

  python3 tools/offline/make_manifest.py --out engine/MANIFEST.json
      [--model name=path_or_hash ...] [--baseline SHA]

  --verify FILE   re-hash everything a manifest lists and report drift
                  (exit 1 on any mismatch — used before a rollback counts as
                  "known good")

Fields: fork_sha, baseline_sha, fork_files[], llama_cpp{commit,pin_ok},
toolchain{gcc,cmake,ninja,nvcc,python}, deps{filename: sha256},
artifacts{file: {sha256,size}}, build{BUILD.json}, models{}, created (UTC),
host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "296b59d2f73c8f04a805df29c2fa97655adace78"   # P0-reviewed pin

os.environ.setdefault("GIT_NO_LAZY_FETCH", "1")   # git commands must never lazy-fetch (partial clones)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"ERROR: {' '.join(cmd)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def tool_ver(cmd: list[str], pat: str = r"[0-9]+\.[0-9]+[0-9.]*") -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(pat, (out.stdout or "") + (out.stderr or ""))
    return (m.group(1) if m.groups() else m.group(0)) if m else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", help="output path (default <repo>/engine/MANIFEST.json)")
    p.add_argument("--model", action="append", default=[],
                   help="name=path → hash the file; name=hash → record a pre-verified sha256")
    p.add_argument("--baseline", default=BASELINE, help="reviewed baseline SHA (default: P0 pin)")
    p.add_argument("--verify", metavar="MANIFEST", help="verify an existing manifest instead of writing one")
    a = p.parse_args()

    if a.verify:
        return verify(Path(a.verify))

    m: dict = {"schema": 1, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "host": platform.node()}

    # --- source state ---
    head = run(["git", "rev-parse", "HEAD"])
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        sys.exit("ERROR: git rev-parse HEAD failed — not a checkout?")
    m["fork_sha"] = head
    m["baseline_sha"] = a.baseline
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        sys.exit("ERROR: working tree is dirty — commit first, manifests describe committed state\n" + dirty)
    # fork divergence vs the reviewed baseline = the "applied patches" list
    diff = run(["git", "diff", "--name-only", a.baseline, "HEAD"]) if a.baseline else ""
    m["fork_files"] = [f for f in diff.splitlines() if f]
    m["fork_commits"] = [c for c in run(["git", "rev-list", "--reverse", f"{a.baseline}..HEAD"]).splitlines() if c] \
        if a.baseline else []

    # --- llama.cpp pin ---
    mo = re.search(r'LLAMA_CPP_COMMIT\s*=\s*"([0-9a-f]{40})"', (ROOT / "setup.py").read_text())
    if not mo:
        sys.exit("ERROR: LLAMA_CPP_COMMIT not found in setup.py")
    pin_file = ROOT / "third_party" / "llama.cpp" / ".strata-pin"
    pin = pin_file.read_text().strip() if pin_file.exists() else None
    m["llama_cpp"] = {"commit": mo.group(1), "pin_file": pin,
                      "pin_ok": pin == mo.group(1)}
    if pin != mo.group(1):
        sys.exit(f"ERROR: llama.cpp pin proof missing/mismatch (.strata-pin={pin}, expected {mo.group(1)})")

    # --- toolchain ---
    # BUILD.json exists by the time a manifest is made (checked below) — its
    # cuda_dirs name the EFFECTIVE compiler, which may differ from PATH-nvcc
    # (--cmake-def CMAKE_CUDA_COMPILER=… override; e.g. uranus PATH=12.0,
    # build=13.0). Record what actually compiled, not what PATH happens to say.
    build_json = {}
    bj_path = ROOT / "engine" / "BUILD.json"
    if bj_path.exists():
        try:
            build_json = json.loads(bj_path.read_text())
        except Exception:
            build_json = {}
    eff_nvcc = None
    for d in (build_json.get("cuda_dirs") or []):
        c = Path(d) / "nvcc"
        if c.is_file():
            eff_nvcc = str(c)
            break

    def venv_tool(name: str) -> str:
        for d in (".venv-offline/bin", ".venv/bin"):
            c = ROOT / d / name
            if c.is_file() and os.access(c, os.X_OK):
                return str(c)
        return name   # PATH lookup inside tool_ver

    m["toolchain"] = {
        "python": platform.python_version(),
        "gcc": tool_ver(["gcc", "--version"], r"gcc \S+ ([0-9.]+)") or tool_ver(["gcc", "-dumpfullversion"]),
        "cmake": tool_ver(["cmake", "--version"], r"version ([0-9.]+)"),
        "ninja": tool_ver([venv_tool("ninja"), "--version"], r"[0-9.]+"),
        "nvcc": tool_ver([eff_nvcc or "nvcc", "--version"], r"release ([0-9.]+)"),
        "nvcc_path": eff_nvcc,
    }

    # --- deps (wheelhouse manifest) ---
    deps = {}
    wman = ROOT / "wheelhouse" / "MANIFEST.sha256"
    if wman.exists():
        for line in wman.read_text().splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                deps[parts[1].lstrip("*").strip()] = parts[0]
    m["deps"] = deps

    # --- venv state (shared, not versioned — record what it is right now) ---
    vpy = ROOT / ".venv-offline" / "bin" / "python"
    venv = {"path": str(ROOT / ".venv-offline")}
    if vpy.exists():
        fr = subprocess.run([str(vpy), "-m", "pip", "freeze", "--all", "--disable-pip-version-check"],
                            capture_output=True, text=True)
        pkgs = sorted(l for l in fr.stdout.splitlines() if l and not l.startswith("#"))
        venv["python"] = run([str(vpy), "--version"]).split()[-1] if vpy.exists() else None
        venv["pip_freeze_sha256"] = hashlib.sha256("\n".join(pkgs).encode()).hexdigest()
        venv["pip_freeze_count"] = len(pkgs)
    else:
        venv["present"] = False
    m["venv"] = venv

    # --- artifacts ---
    artifacts = {}
    for name in ("strata", "libstrata_kq.so", "strata-vision"):
        f = ROOT / "engine" / name
        if f.exists():
            artifacts[name] = {"sha256": sha256_file(f), "size": f.stat().st_size}
    if not artifacts:
        sys.exit("ERROR: no engine/ artifacts — run tools/offline/build_engine.sh first")
    m["artifacts"] = artifacts
    m["build"] = build_json if build_json else None
    if m["build"] is None:
        sys.exit("ERROR: engine/BUILD.json missing — build stamp required (build_engine.sh writes it)")

    # --- models ---
    models = {}
    for spec in a.model:
        if "=" not in spec:
            sys.exit(f"ERROR: --model expects name=path_or_sha256, got {spec!r}")
        name, val = spec.split("=", 1)
        path = ROOT / val
        p2 = Path(val)
        cand = p2 if p2.is_absolute() else path
        if cand.exists() and cand.is_file():
            models[name] = {"sha256": sha256_file(cand), "size": cand.stat().st_size,
                            "path": str(cand), "hashed": "now"}
        elif re.fullmatch(r"[0-9a-f]{64}", val):
            models[name] = {"sha256": val, "hashed": "pre-verified"}
        else:
            sys.exit(f"ERROR: --model {name}: neither an existing file nor a sha256 ({val!r})")
    m["models"] = models

    out = Path(a.out or ROOT / "engine" / "MANIFEST.json")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(m, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    print(f"wrote {out}")
    print(json.dumps({k: m[k] for k in ("fork_sha", "baseline_sha", "llama_cpp", "toolchain")}, indent=1))
    print(f"artifacts: {list(artifacts)}, deps: {len(deps)}, models: {list(models)}, fork_files: {len(m['fork_files'])}")
    return 0


def verify(path: Path) -> int:
    m = json.loads(path.read_text())
    base = path.parent
    bad = []
    # Artifacts must sit NEXT TO the manifest (deploy dir or engine/) — a
    # missing one is drift, not a reason to look elsewhere (that would pass
    # a partial deploy dir because the repo copy has the same hash).
    for name, rec in m.get("artifacts", {}).items():
        f = base / name
        if not f.exists() or sha256_file(f) != rec["sha256"]:
            bad.append(f"artifact {name}")
    head = run(["git", "rev-parse", "HEAD"])
    if head != m.get("fork_sha"):
        bad.append(f"fork_sha (manifest {m.get('fork_sha')}, checkout {head})")
    if run(["git", "status", "--porcelain"]):
        bad.append("working tree dirty (serve/ runs from the checkout)")
    pin = m.get("llama_cpp", {})
    if pin:
        cur_pin = None
        pf = ROOT / "third_party" / "llama.cpp" / ".strata-pin"
        if pf.exists():
            cur_pin = pf.read_text().strip()
        if cur_pin != pin.get("commit"):
            bad.append("llama_cpp .strata-pin mismatch/missing now")
        if not pin.get("pin_ok"):
            bad.append("llama_cpp pin_ok was false in manifest")
    if m.get("deps"):
        wman = ROOT / "wheelhouse" / "MANIFEST.sha256"
        if not wman.exists():
            bad.append("wheelhouse MANIFEST.sha256 missing (manifest lists deps)")
        else:
            have = {p[1].lstrip("*").strip(): p[0] for l in wman.read_text().splitlines()
                    if len(p := l.split(None, 1)) == 2}
            for f, h in m["deps"].items():
                if have.get(f) != h:
                    bad.append(f"dep {f}")
    v = m.get("venv") or {}
    if v.get("pip_freeze_sha256"):
        vpy = ROOT / ".venv-offline" / "bin" / "python"
        if not vpy.exists():
            bad.append("venv missing (manifest recorded one)")
        else:
            fr = subprocess.run([str(vpy), "-m", "pip", "freeze", "--all", "--disable-pip-version-check"],
                                capture_output=True, text=True)
            pkgs = sorted(l for l in fr.stdout.splitlines() if l and not l.startswith("#"))
            if hashlib.sha256("\n".join(pkgs).encode()).hexdigest() != v["pip_freeze_sha256"]:
                bad.append("venv pip_freeze drifted (venv rebuilt since deploy)")
    if bad:
        print("MANIFEST VERIFY FAILED:", ", ".join(bad))
        return 1
    print(f"manifest verified: fork_sha {m['fork_sha'][:8]}, {len(m.get('artifacts', {}))} artifacts, "
          f"{len(m.get('deps', {}))} deps — all match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
