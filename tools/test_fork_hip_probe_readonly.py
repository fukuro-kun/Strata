# test_fork_hip_probe_readonly.py - the HIP device probe must not write engine files;
# the explicit repair stays with the install path (hip_card).
#
# AST selection of the reviewed definitions + literal constants from setup.py only -
# the module body (and any setup execution) is never imported.
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
QUELLE = (ROOT / "terminal" / "setup.py").read_text(encoding="utf-8")

FNS = ["hip_devices", "hip_probe_path", "engine_env", "hip_lib_dirs",
       "hip_runtime_beside_exe", "hip_match", "hip_card",
       "amd_gpus", "amd_gpus_win", "amd_problem"]
KONSTANTEN = ["AMD_NAMES", "AMD_ARCHS", "AMD_CARDS", "WIN_AMD_DRIVER",
              "STRIX_HALO_ARCH", "STRIX_HALO_BY_SIMDS", "HIP_RUNTIME_DLLS"]

DEVICE_TEXT = "device 1: AMD Radeon Graphics\n  arch gfx1101, 16.0 GiB\n"


class ProbeError(Exception):
    """Sentinel for the real fail()."""


def _lade():
    baum = ast.parse(QUELLE)
    fns = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name in FNS}
    konst = {}
    for n in baum.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id in KONSTANTEN:
            konst[n.targets[0].id] = n
    fehlt = [f for f in FNS if f not in fns] + [k for k in KONSTANTEN if k not in konst]
    assert not fehlt, f"Selektion unvollstaendig: {fehlt}"
    ns = {
        "os": os, "sys": sys, "re": re, "json": json, "shutil": shutil,
        "subprocess": subprocess, "Path": Path,
        "WIN": False, "ROOT": None,
        # Stubs: no real repair closure, no registry, no setup helpers.
        "hip_runtime_closure": lambda d: ["amdhip64_7.dll"],
        "is_uma_apu": lambda g: False,
        "amd_apply_uma": lambda g, gtt=0: g,
        "amd_gpus_windows": mock.Mock(side_effect=AssertionError("registry must not run")),
        "gfx_arch_is": lambda a, b: a == b,
        "GFX1103_OPT_IN": False, "GFX1150_OPT_IN": False,   # opt-in flags: default state (off)
        "warn": lambda *a, **k: None, "ok": lambda *a, **k: None,
        "say": lambda *a, **k: None, "log": lambda *a, **k: None,
        "fail": lambda *a: (_ for _ in ()).throw(ProbeError(" | ".join(map(str, a)))),
    }
    koerper = list(fns.values()) + list(konst.values())
    exec(compile(ast.Module(body=koerper, type_ignores=[]), "setup-extract", "exec"), ns)
    return ns


class TestHipProbeReadonly(unittest.TestCase):

    def setUp(self):
        self.ns = _lade()
        self.tmp = Path(tempfile.mkdtemp(prefix="hip-probe-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.eng = self.tmp / "engine"
        (self.eng / "rocm" / "bin").mkdir(parents=True)
        (self.eng / "BUILD.json").write_text(
            json.dumps({"backend": "hip", "lib_dirs": ["rocm/bin"]}), encoding="utf-8")
        (self.eng / "rocm" / "bin" / "amdhip64_7.dll").write_bytes(b"fixture-dll")
        self.probe = self.eng / "strata-device.exe"
        self.probe.write_bytes(b"fixture-exe")

    def _env(self, extra):
        return mock.patch.dict(os.environ, extra, clear=True)

    # ---------- (1) successful probe: parses, prepends lib_dirs, copies NOTHING ----------
    def test_probe_copies_nothing(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=DEVICE_TEXT))
        for env in ({}, {"STRATA_NO_ACQUIRE": "1"}):
            with self.subTest(env=env):
                (self.eng / "amdhip64_7.dll").unlink(missing_ok=True)
                with self._env(env), mock.patch.object(subprocess, "run", run):
                    found = self.ns["hip_devices"](self.probe)
                self.assertEqual(found[0]["index"], 1)
                self.assertEqual(found[0]["arch"], "gfx1101")
                self.assertFalse((self.eng / "amdhip64_7.dll").exists(),
                                 "the probe wrote an engine file")
        lib = run.call_args.kwargs["env"]["LD_LIBRARY_PATH"]
        self.assertEqual(lib.split(os.pathsep)[0], str(self.eng / "rocm" / "bin"))

    # ---------- (2) amd_gpus/amd_gpus_win chain (WIN=True): ordinal preserved ----------
    def test_amd_chain_keeps_hip_ordinal(self):
        self.ns["WIN"] = True
        self.ns["ROOT"] = self.tmp          # hip_probe_path findet tmp/engine/strata-device.exe
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=DEVICE_TEXT))
        with self._env({}), mock.patch.object(subprocess, "run", run):
            gefunden = self.ns["amd_gpus"]()
        self.assertEqual(gefunden[0]["index"], 1)
        self.assertEqual(gefunden[0]["arch"], "gfx1101")
        self.ns["amd_gpus_windows"].assert_not_called()
        self.assertFalse((self.eng / "amdhip64_7.dll").exists())

    # ---------- (3) error cases: None, no repair ----------
    def test_probe_errors_give_none_without_repair(self):
        for fehler in (OSError("no process"), subprocess.TimeoutExpired("x", 1)):
            with self.subTest(fehler=type(fehler).__name__):
                (self.eng / "amdhip64_7.dll").unlink(missing_ok=True)
                with self._env({}), mock.patch.object(subprocess, "run", mock.Mock(side_effect=fehler)):
                    self.assertIsNone(self.ns["hip_devices"](self.probe))
                self.assertFalse((self.eng / "amdhip64_7.dll").exists())

    # ---------- (4) text= parser: no process, no repair ----------
    def test_text_parser_runs_no_process(self):
        run = mock.Mock()
        repair = mock.Mock(side_effect=AssertionError("repair must not run"))
        with mock.patch.object(subprocess, "run", run), \
                mock.patch.dict(self.ns, {"hip_runtime_beside_exe": repair}):
            found = self.ns["hip_devices"](text="device 0: x\n  arch gfx1101, 8.0 GiB\n")
        self.assertEqual(found[0]["index"], 0)
        run.assert_not_called()
        repair.assert_not_called()

    # ---------- (5) hip_card: explicit repair BEFORE the probe ----------
    def test_hip_card_repairs_before_probe(self):
        def fake_run(cmd, **kw):
            self.assertTrue((self.eng / "amdhip64_7.dll").exists(),
                            "hip_card must repair before --list-devices")
            return SimpleNamespace(returncode=0, stdout=DEVICE_TEXT)
        gpu = {"index": 0, "name": "AMD Radeon", "vram_gb": 16.0, "arch": "gfx1101",
               "driver": "amdgpu", "vendor": "amd"}
        listed = [gpu, {"index": 1, "name": "iGPU", "vram_gb": 0.0, "arch": "gfx1150",
                        "driver": "amdgpu", "vendor": "amd"}]
        with self._env({}), mock.patch.object(subprocess, "run", fake_run):
            karte = self.ns["hip_card"](self.eng, gpu, listed)
        self.assertEqual(karte["driver"], "hip")
        self.assertEqual(karte["index"], 1)          # HIP ordinal 1, display ordinal 0
        self.assertEqual(karte["count"], 1)
        self.assertTrue((self.eng / "amdhip64_7.dll").exists())

    # ---------- (6) hip_card without devices: fail(), no real process ----------
    def test_hip_card_without_devices_fails(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout=""))
        with self._env({}), mock.patch.object(subprocess, "run", run):
            with self.assertRaises(ProbeError):
                self.ns["hip_card"](self.eng,
                                    {"index": 0, "arch": "gfx1101", "vram_gb": 16.0,
                                     "name": "x", "driver": "amdgpu"}, [])
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
