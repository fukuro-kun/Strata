#!/usr/bin/env python3
"""make_config.py — write a strata-<model>.json run config without setup.py.

FORK (fukuro-kun/Strata): minimal writer producing exactly the JSON shape
serve/server.py reads (keys exe/args/cwd/tokenizer/model_name/log/lib_dirs/
port/gpu). It does NOT reproduce setup's model-choice logic — the engine
"args" stay the caller's responsibility (copy a known-good config's args or
take them from a P3 manifest). Written atomically like setup's write_config.

Usage:
  python3 tools/offline/make_config.py NAME --pack DIR --native GGUF [engine-args...]
      [--tokenizer DIR] [--port N] [--gpu 0,1] [--exe PATH] [--log FILE]
      [--lib-dirs DIR[,DIR...]] [--out FILE] [--force]

  NAME becomes model_name qwen3.8-flash-next-NAME and file strata-NAME.json.
  Everything after a bare `--` is appended to the engine args verbatim.

Example:
  python3 tools/offline/make_config.py iq3_xxs \\
      --pack /data/packs/iq3_xxs --native /models/Q...-IQ3_XXS-00001-of-00002.gguf \\
      --tokenizer /data/packs/iq3_xxs/tokenizer --port 8080 --gpu 0,1 \\
      -- --ple-gguf /models/Q...-00002-of-00002.gguf --max-context 65536 --kv int8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", help="model short name -> strata-<name>.json, model_name qwen3.8-flash-next-<name>")
    p.add_argument("--exe", default=str(ROOT / "engine" / "strata"), help="engine binary (default: repo engine/strata)")
    p.add_argument("--pack", help="engine --pack directory")
    p.add_argument("--native", help="engine --native GGUF file")
    p.add_argument("--tokenizer", help="tokenizer dir containing vocab.json (default: <pack>/tokenizer)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--gpu", help="GPU list as nvidia-smi numbers them, e.g. '0' or '0,1'")
    p.add_argument("--log", help="log file (default: strata-<name>.log next to the config)")
    p.add_argument("--lib-dirs", help="comma-separated CUDA lib dirs for the engine's LD_LIBRARY_PATH")
    p.add_argument("--cwd", default=str(ROOT), help="engine working directory (default: repo root)")
    p.add_argument("--out", help="output path (default: <repo>/strata-<name>.json)")
    p.add_argument("--force", action="store_true", help="overwrite an existing config")
    a, engine_extra = p.parse_known_args()

    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.name):
        p.error(f"invalid name {a.name!r} — use [A-Za-z0-9_.-] only (it becomes file/setting names)")

    engine = Path(a.exe).expanduser().resolve()
    if not engine.is_file():
        p.error(f"engine binary missing: {engine} — build it (tools/offline/build_engine.sh) or pass --exe")

    args: list[str] = []
    if a.pack:
        pack = Path(a.pack).expanduser().resolve()
        if not pack.is_dir():
            p.error(f"--pack directory missing: {a.pack}")
        args += ["--pack", str(pack)]
    if a.native:
        native = Path(a.native).expanduser().resolve()
        if not native.is_file():
            p.error(f"--native file missing: {a.native}")
        args += ["--native", str(native)]
    args += [x for x in engine_extra if x != "--"]

    tok = a.tokenizer or (str(Path(a.pack) / "tokenizer") if a.pack else None)
    if tok:
        tok = str(Path(tok).expanduser().resolve())
    if not tok or not (Path(tok) / "vocab.json").exists():
        p.error(f"tokenizer missing vocab.json: {tok} — pass --tokenizer DIR")

    cfg = {
        "exe": str(engine),
        "args": args,
        "cwd": a.cwd,
        "tokenizer": tok,
        "model_name": f"qwen3.8-flash-next-{a.name}",
        "log": a.log or str(ROOT / f"strata-{a.name}.log"),
        "port": a.port,
    }
    if a.lib_dirs:
        dirs = [d for d in a.lib_dirs.split(",") if d]
        for d in dirs:
            if not Path(d).is_dir():
                p.error(f"--lib-dirs entry missing: {d}")
        cfg["lib_dirs"] = dirs
    if a.gpu is not None:
        try:
            cfg["gpu"] = int(a.gpu) if a.gpu.strip().isdigit() else [int(x) for x in a.gpu.split(",") if x != ""]
        except ValueError:
            p.error(f"--gpu takes nvidia-smi numbers like '0' or '0,1', not {a.gpu!r}")
        cfg["gpus_asked"] = True
        cfg["layer_split"] = "auto"

    out = Path(a.out or ROOT / f"strata-{a.name}.json")
    if out.exists() and not a.force:
        p.error(f"{out} exists — pass --force to overwrite deliberately")
    tmp = out.with_name(out.name + ".tmp")       # atomic write, like setup's write_config (#459)
    tmp.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    print(f"wrote {out}")
    print(json.dumps(cfg, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
