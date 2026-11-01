# test_fork_updater_env.py — STRATA_API_KEY darf beim Updater-Test-Start nicht verloren gehen.
#
# Unit-Test NUR gegen die AST-extrahierten Funktionen `_patched_environ` und `default_test_start`
# aus strata_control/updater.py — kein Import des echten Moduls, keine echten Profile/Runtimes.
# Vier Faelle: Eltern-Key vorhanden/abwesend x Erfolg/Fehler.
import ast
import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "strata_control" / "updater.py"
QUELLE = SRC.read_text(encoding="utf-8")


def _lade_funktionen():
    """Nur die zwei echten FunctionDefs aus dem Quelltext kompilieren — nichts sonst ausfuehren."""
    baum = ast.parse(QUELLE)
    gesucht = {"_patched_environ", "default_test_start"}
    fns = [n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name in gesucht]
    assert {n.name for n in fns} == gesucht

    class TestStartFailed(RuntimeError):
        def __init__(self, version, reason=""):
            super().__init__(f"{version}: {reason}")
            self.version, self.reason = version, reason

    ns = {
        "os": os, "contextlib": contextlib, "Path": Path, "tempfile": tempfile,
        "shutil": shutil, "json": json, "Context": object,
        "ec": SimpleNamespace(EngineComponent=object, REFERENCE_PREFIX="component:",
                              COMPONENT_ID="strata-engine"),
        "TestStartFailed": TestStartFailed,
        "light_test_args": lambda args: args,
        "longpath": SimpleNamespace(long_path=lambda p: p),
        "_free_port": lambda: 12345,
        "_test_progress": lambda ctx, component: None,
        "_keep_log": lambda *a, **k: None,
        "_keep_records": lambda *a, **k: None,
        "_test_start_failure": lambda component, started, ctx, tail:
            TestStartFailed(component.version, str(started.get("error", "start failed"))),
        "_log_tail": lambda *a: "",
        "binary_smoke": lambda c: {"mode": "smoke"},
        "discover_run_config": lambda environ=None: None,
    }
    exec(compile(ast.Module(body=fns, type_ignores=[]), str(SRC), "exec"), ns)
    return ns, TestStartFailed


NS, TestStartFailed = _lade_funktionen()
default_test_start = NS["default_test_start"]


class TestUpdaterEnv(unittest.TestCase):
    """Vier Faelle: STRATA_API_KEY vorhanden/abwesend x Erfolg/Fehler."""

    def _fixture(self):
        # eigene Mini-Fixtures unterhalb des (im Sandbox tmpfs belegten) Temp-Roots
        root = Path(tempfile.mkdtemp(prefix="uenv-"))
        stage = root / "stage"; stage.mkdir()
        cfg = root / "run.json"
        cfg.write_text(json.dumps({"model_name": "dummy", "args": []}), encoding="utf-8")
        ctx = SimpleNamespace(run_config=str(cfg), test_timeout=1,
                              allow_no_model_smoke=True, environ={})
        component = SimpleNamespace(backend="cuda", version="0.0.0-test")
        return root, stage, component, ctx

    def _lauf(self, *, key_vorhanden, fehler):
        aufrufe = {"create": 0, "start": 0, "stop": 0, "verify": 0}

        def assert_kein_key():
            self.assertNotIn("STRATA_API_KEY", os.environ)

        def create(name, cfg):
            aufrufe["create"] += 1; assert_kein_key()

        def start(name, **kw):
            aufrufe["start"] += 1; assert_kein_key()
            if fehler:
                raise RuntimeError("simulierter Startfehler")
            return {"ok": True, "state": "ready", "generation_ready": True}

        def stop(name, **kw):
            aufrufe["stop"] += 1; assert_kein_key()
            return {"ok": True}

        def verify(name, **kw):
            aufrufe["verify"] += 1
            raise AssertionError("verify darf nicht aufgerufen werden")

        paket = ModuleType("strata_control")
        paket.profiles = SimpleNamespace(create=create)
        paket.runtime = SimpleNamespace(start=start, stop=stop, verify=verify)
        root, stage, component, ctx = self._fixture()
        result, geworfen = None, None
        try:
            base = {"STRATA_API_KEY": "dummy-eltern-key"} if key_vorhanden else {}
            with mock.patch.dict(os.environ, base, clear=True):
                with mock.patch.dict(sys.modules, {"strata_control": paket}):
                    try:
                        result = default_test_start(stage, component, ctx)
                    except Exception as exc:            # jede Ausnahme wird aufgezeichnet, nichts stillschweigend
                        geworfen = exc
                # Erwartung zuerst: Erfolg ohne Ausnahme; Fehler nur als TestStartFailed mit genau diesem Grund.
                if not fehler:
                    self.assertIsNone(geworfen)
                else:
                    self.assertIsInstance(geworfen, TestStartFailed)
                    self.assertIn("RuntimeError: simulierter Startfehler", str(geworfen.reason))
                self.assertEqual(aufrufe["create"], 1)
                self.assertEqual(aufrufe["start"], 1)
                self.assertEqual(aufrufe["stop"], 1)
                self.assertEqual(aufrufe["verify"], 0)
                # Nach dem Kontext-Manager: der Eltern-Zustand muss exakt wiederhergestellt sein.
                if key_vorhanden:
                    self.assertEqual(os.environ.get("STRATA_API_KEY"), "dummy-eltern-key")
                else:
                    self.assertNotIn("STRATA_API_KEY", os.environ)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        return result

    def test_key_vorhanden_erfolg(self):
        r = self._lauf(key_vorhanden=True, fehler=False)
        self.assertIsNotNone(r); self.assertEqual(r["mode"], "full")

    def test_key_vorhanden_fehler(self):
        r = self._lauf(key_vorhanden=True, fehler=True)
        self.assertIsNone(r)          # TestStartFailed propagiert; Key dennoch restauriert (oben geprueft)

    def test_key_abwesend_erfolg(self):
        r = self._lauf(key_vorhanden=False, fehler=False)
        self.assertIsNotNone(r); self.assertEqual(r["mode"], "full")

    def test_key_abwesend_fehler(self):
        r = self._lauf(key_vorhanden=False, fehler=True)
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
