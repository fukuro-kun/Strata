# test_fork_backend_build_gates.py - backend build primitives must pass the fork
# acquisition gate before tooling/env work; valid cached artifacts stay allowed.
#
# AST selection of the reviewed definitions only - neither backend setup module
# body nor root setup is ever imported.
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
QUELLE_MAC = (ROOT / "metal" / "setup_mac.py").read_text(encoding="utf-8")
QUELLE_SYCL = (ROOT / "sycl" / "setup_intel.py").read_text(encoding="utf-8")

sys.path.insert(0, str(ROOT))
from strata_control import acquisition  # noqa: E402


class PrepSentinel(AssertionError):
    """Reached: a compiler/tool/env helper ran despite the denied acquisition."""


def _lade():
    mac = ast.parse(QUELLE_MAC)
    sycl = ast.parse(QUELLE_SYCL)
    fns = {}
    for n in mac.body:
        if isinstance(n, ast.FunctionDef) and n.name in ("build_engine", "build_vision"):
            fns[n.name] = n
    for n in sycl.body:
        if isinstance(n, ast.FunctionDef) and n.name in ("build_vision_sycl_reader", "build_vision_sycl"):
            fns[n.name] = n
    fehlt = {"build_engine", "build_vision", "build_vision_sycl_reader", "build_vision_sycl"} - set(fns)
    assert not fehlt, f"Selektion unvollstaendig: {fehlt}"
    return fns


class TestBackendBuildGates(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bbg-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        fns = _lade()
        self.S = SimpleNamespace(
            acquisition=acquisition,
            ensure_build_tools=mock.Mock(side_effect=PrepSentinel("ensure_build_tools")),
            cmake_build=mock.Mock(side_effect=PrepSentinel("cmake_build")),
            source_version=lambda: "v-fixture",
            ok=lambda *a, **k: None, say=lambda *a, **k: None,
            warn=lambda *a, **k: None,
            fail=lambda *a, **k: (_ for _ in ()).throw(SystemExit(1)),
        )
        self.build_dir = self.tmp / "build-metal"
        self.exe = self.build_dir / "strata"
        self.vision_exe = self.tmp / "build-vision" / "bin" / "strata-vision"
        ns = {
            "S": self.S, "os": os, "sys": sys, "json": json, "shutil": shutil,
            "subprocess": subprocess, "Path": Path,
            "ROOT": self.tmp, "BUILD_DIR": self.build_dir,
            "EXE": self.exe, "VISION_EXE": self.vision_exe,
            "tool": lambda name: f"/tools/{name}",
            "metal_cpp": mock.Mock(side_effect=PrepSentinel("metal_cpp")),
            "source_digest": lambda: "frozen-digest-1234",
            "engine_current": mock.Mock(return_value=False),
            "oneapi_compiler": mock.Mock(side_effect=PrepSentinel("oneapi_compiler")),
            "oneapi_environment": mock.Mock(side_effect=PrepSentinel("oneapi_environment")),
        }
        exec(compile(ast.Module(body=list(fns.values()), type_ignores=[]), "backend-extract", "exec"), ns)
        self.ns = ns
        # __main__-Guard-Blöcke separat extrahieren (nie Modul-Body ausfuehren).
        self.guards = {}
        for schlues, quelle in (("mac", QUELLE_MAC), ("sycl", QUELLE_SYCL)):
            baum = ast.parse(quelle)
            guard = next((n for n in baum.body
                          if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                          and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__"), None)
            self.guards[schlues] = guard
            assert guard is not None

    def _env(self, extra):
        return mock.patch.dict(os.environ, extra, clear=True)

    # ---------- Verweigerung: alle drei Primitive vor erstem Prep ----------
    def _verweigert(self, env, erwarte):
        for name in ("build_engine", "build_vision", "build_vision_sycl_reader"):
            with self.subTest(primitive=name):
                args = (self.tmp / "llama", 4) if name == "build_engine" else \
                       (self.tmp / "llama",) if name == "build_vision" else \
                       (self.tmp / "stub", self.tmp / "llama")
                call = mock.Mock(side_effect=PrepSentinel("subprocess.call"))
                with self._env(env), mock.patch.object(subprocess, "call", call):
                    try:
                        self.ns[name](*args)
                    except Exception as exc:
                        if not erwarte(exc):
                            raise
                    else:
                        raise AssertionError(f"{name} lief ohne Gate weiter")
                self.S.ensure_build_tools.assert_not_called()
                self.S.cmake_build.assert_not_called()
                self.ns["metal_cpp"].assert_not_called()
                self.ns["oneapi_compiler"].assert_not_called()
                self.ns["oneapi_environment"].assert_not_called()
                call.assert_not_called()

    def test_default_refused(self):
        self._verweigert({}, lambda e: isinstance(e, acquisition.ForkAcquisitionRefused)
                                     and e.exit_code == 5)

    def test_wrong_allow_refused(self):
        self._verweigert({"STRATA_FORK_ALLOW_ACQUIRE": "true"},
                         lambda e: isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_no_acquire_wins(self):
        self._verweigert({"STRATA_FORK_ALLOW_ACQUIRE": "1", "STRATA_NO_ACQUIRE": "1"},
                         lambda e: isinstance(e, acquisition.AcquisitionRefused)
                              and not isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_forbidden_context_wins(self):
        with acquisition.forbidden():
            self._verweigert({"STRATA_FORK_ALLOW_ACQUIRE": "1"},
                             lambda e: isinstance(e, acquisition.AcquisitionRefused)
                                  and not isinstance(e, acquisition.ForkAcquisitionRefused))

    # ---------- Positiv: explizites Allow ----------
    def test_allowed_metal_engine_builds(self):
        self.ns["metal_cpp"].side_effect = lambda: self.tmp / "metal-cpp"
        self.S.ensure_build_tools.side_effect = lambda: None
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}), \
                mock.patch.object(subprocess, "call", mock.Mock(return_value=0)) as call:
            out = self.ns["build_engine"](self.tmp / "llama", jobs=9)
        self.assertEqual(out, self.exe)
        self.assertEqual(call.call_count, 2)
        ninja_cmd = call.call_args_list[1].args[0]
        self.assertIn("-j", ninja_cmd)
        self.assertIn("9", ninja_cmd)
        stamp = json.loads((self.build_dir / "BUILD.json").read_text())
        self.assertEqual(stamp["source"], "frozen-digest-1234")
        self.assertEqual(stamp["backend"], "metal")

    def test_allowed_metal_vision_builds(self):
        self.S.ensure_build_tools.side_effect = lambda: None
        (self.tmp / "build-vision").mkdir()          # cmake -B legt das Verzeichnis im echten Lauf an
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}), \
                mock.patch.object(subprocess, "call", mock.Mock(return_value=0)) as call:
            out = self.ns["build_vision"](self.tmp / "llama")
        self.assertEqual(out, self.vision_exe)
        self.assertEqual(call.call_count, 2)
        stamp = self.tmp / "build-vision" / "BUILD.json"
        self.assertEqual(json.loads(stamp.read_text())["source"], "frozen-digest-1234")

    def test_allowed_sycl_reader_builds_and_restores_env(self):
        self.ns["oneapi_compiler"].side_effect = lambda: ("icx", "icpx")
        self.ns["oneapi_environment"].side_effect = lambda: {"ONEAPI": "1"}
        self.S.cmake_build.side_effect = lambda *a, **k: None
        bin_src = self.tmp / "build-vision-sycl" / "bin"
        bin_src.mkdir(parents=True)
        (bin_src / "strata-vision-sycl").write_bytes(b"fixture-exe")
        stub = self.tmp / "stub"
        stub.mkdir()
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}):
            env_vor = dict(os.environ)
            ok = self.ns["build_vision_sycl_reader"](stub, self.tmp / "llama")
            env_danach = dict(os.environ)
        self.assertTrue(ok)
        self.assertEqual((stub / "strata-vision-sycl").read_bytes(), b"fixture-exe")
        self.S.cmake_build.assert_called_once()
        self.assertEqual(env_danach, env_vor)   # env vollstaendig restauriert, kein ONEAPI-Leck

    def test_allowed_sycl_no_compiler_returns_false(self):
        self.ns["oneapi_compiler"].side_effect = lambda: None
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}):
            self.assertFalse(self.ns["build_vision_sycl_reader"](self.tmp / "stub", self.tmp / "llama"))
        self.ns["oneapi_environment"].assert_not_called()
        self.S.cmake_build.assert_not_called()

    def test_allowed_sycl_build_error_returns_false_restores_env(self):
        self.ns["oneapi_compiler"].side_effect = lambda: ("icx", "icpx")
        self.ns["oneapi_environment"].side_effect = lambda: {"ONEAPI": "1"}
        self.S.cmake_build.side_effect = RuntimeError("compile failed")
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}):
            env_vor = dict(os.environ)
            self.assertFalse(self.ns["build_vision_sycl_reader"](self.tmp / "stub", self.tmp / "llama"))
            env_danach = dict(os.environ)
        self.assertEqual(env_danach, env_vor)   # auch im Fehlerfall restauriert

    # ---------- Cached: kein Allow noetig ----------
    def test_cached_engine_and_vision_allowed_under_deny(self):
        self.ns["engine_current"].side_effect = lambda: True
        self.vision_exe.parent.mkdir(parents=True)
        self.vision_exe.write_bytes(b"fixture")
        (self.tmp / "build-vision").mkdir(exist_ok=True)
        (self.tmp / "build-vision" / "BUILD.json").write_text(json.dumps({"source": "frozen-digest-1234"}))
        for name, env in (("default", {}), ("no_acquire", {"STRATA_NO_ACQUIRE": "1"})):
            with self.subTest(env=name):
                with self._env(env):
                    self.assertEqual(self.ns["build_engine"](self.tmp / "llama"), self.exe)
                    self.assertEqual(self.ns["build_vision"](self.tmp / "llama"), self.vision_exe)
        self.S.ensure_build_tools.assert_not_called()
        self.ns["metal_cpp"].assert_not_called()

    def test_cached_sycl_parent_returns_before_denied_helper(self):
        stub = self.tmp / "stub"
        stub.mkdir()
        (stub / "strata-vision-sycl").write_bytes(b"fixture")
        stamp = self.tmp / "stamp.json"
        stamp.write_text(json.dumps({"vision_gpu_src": "v-fixture"}))
        reader = mock.Mock(side_effect=PrepSentinel("reader"))
        for env in ({}, {"STRATA_NO_ACQUIRE": "1"}):
            with self.subTest(env=env):
                with mock.patch.dict(self.ns, {"build_vision_sycl_reader": reader}):
                    with self._env(env):
                        self.ns["build_vision_sycl"](stub, stamp, self.tmp / "llama", "v-fixture")
        reader.assert_not_called()


class TestBackendMainGuards(unittest.TestCase):
    """__main__-Guards: typisierte Beschaffungsverweigerung -> [X]-Zeile + Exit 5."""

    def _guard(self, schlues, quelle, aufruf_exc=None, aufruf_rv=None):
        baum = ast.parse(quelle)
        guard = next(n for n in baum.body
                     if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                     and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__")
        say = mock.Mock()
        S = SimpleNamespace(acquisition=acquisition, say=say)
        def aufruf(*a, **k):
            if aufruf_exc:
                raise aufruf_exc
            return aufruf_rv
        ns = {"__name__": "__main__", "S": S,
              "sys": SimpleNamespace(argv=["prog"],
                                     exit=lambda c: (_ for _ in ()).throw(SystemExit(c))),
              "main": aufruf, "install": aufruf}
        try:
            exec(compile(ast.Module(body=[guard], type_ignores=[]), "guard-exec", "exec"), ns)
        except SystemExit as e:
            return e.code, say
        return None, say

    def _faelle(self, quelle, erwarte_erfolg):
        # Verweigerung: Fork-Unterklasse und Basisklasse -> Exit 5 + [X]-Zeile.
        for exc in (acquisition.ForkAcquisitionRefused("the build", "procurement"),
                    acquisition.AcquisitionRefused("the build", "procurement")):
            with self.subTest(exc=type(exc).__name__):
                code, say = self._guard("x", quelle, aufruf_exc=exc)
                self.assertEqual(code, 5)
                say.assert_called_once()
                self.assertIn("missing or out of date", say.call_args.args[0])
        # Erfolg + KeyboardInterrupt bleiben unveraendert.
        with self.subTest(exc="success"):
            code, _ = self._guard("x", quelle, aufruf_rv=3)
            self.assertEqual(code, erwarte_erfolg)
        with self.subTest(exc="KeyboardInterrupt"):
            code, say = self._guard("x", quelle, aufruf_exc=KeyboardInterrupt())
            self.assertEqual(code, 1)
            say.assert_called_once()

    def test_mac_main_guard_typed_refusal(self):
        self._faelle(QUELLE_MAC, 3)        # mac: sys.exit(main()) uebernimmt den Rueckgabewert

    def test_sycl_main_guard_typed_refusal(self):
        self._faelle(QUELLE_SYCL, None)    # sycl: install() ohne sys.exit -> normaler Exit 0


if __name__ == "__main__":
    unittest.main(verbosity=2)
