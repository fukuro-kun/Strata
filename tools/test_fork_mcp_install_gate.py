# test_fork_mcp_install_gate.py — MCP-Modellinstaller und Hintergrundjob muessen VOR
# State-/Spec-/Venv-Zugriff das Fork-Beschaffungs-Gate passieren; STRATA_NO_ACQUIRE darf
# im Control-Kind nicht entfernt werden.
#
# AST-Selektion: nur install_job, main und Tools.launch_install aus dem echten Quelltext;
# das gepruefte acquisition-Modul liefert das Gate. Path/s/Popen sind Sentinels —
# keine echten Pfade, Jobs oder Prozesse.
import argparse
import ast
import contextlib
import io
import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "terminal"))
from strata_control import acquisition  # noqa: E402

SRC = (ROOT / "terminal" / "tools" / "strata_mcp.py").read_text(encoding="utf-8")


class ReachedPath(Exception):
    """Sentinel: ein lokaler Pfad-/Spec-Zugriff wurde erreicht."""


class ReachedState(Exception):
    """Sentinel: der Setup-State (self.s) wurde erreicht."""


def _lade():
    baum = ast.parse(SRC)
    gewaehlt = {}
    for n in baum.body:
        if isinstance(n, ast.FunctionDef) and n.name in ("install_job", "main"):
            gewaehlt[n.name] = n
        elif isinstance(n, ast.ClassDef) and n.name == "Tools":
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and m.name == "launch_install":
                    gewaehlt["launch_install"] = m
    assert set(gewaehlt) == {"install_job", "main", "launch_install"}
    path_mock = mock.Mock(side_effect=ReachedPath)
    popen_mock = mock.Mock()
    run_mock = mock.Mock(return_value=SimpleNamespace(returncode=0))
    ns = {
        "acquisition": acquisition, "argparse": argparse, "json": json, "os": os,
        "sys": sys, "time": time, "shutil": shutil, "CONTROL": True,
        "subprocess": SimpleNamespace(run=run_mock, Popen=popen_mock, DEVNULL=None),
        "Path": path_mock, "print": print,
    }
    exec(compile(ast.Module(body=list(gewaehlt.values()), type_ignores=[]), "mcp-extract", "exec"), ns)
    return ns, path_mock, popen_mock, run_mock


def _selbst():
    class _S:
        @property
        def s(self):
            raise ReachedState
    return _S()


class TestMcpInstallGate(unittest.TestCase):

    def setUp(self):
        self.ns, self.path_mock, self.popen, self.run = _lade()

    def _rufe(self, name):
        if name == "launch_install":
            return lambda: self.ns["launch_install"](_selbst(), {}, [])
        return lambda: self.ns["install_job"]("fixture-spec.json")

    def _pruefe(self, env, erwarte):
        for name in ("launch_install", "install_job"):
            with self.subTest(primitive=name):
                with mock.patch.dict(os.environ, env, clear=True):
                    try:
                        self._rufe(name)()
                    except Exception as exc:
                        if not erwarte(exc):
                            raise
                    else:
                        raise AssertionError(f"{name} lief ohne Gate weiter")
        self.path_mock.assert_not_called()
        self.popen.assert_not_called()
        self.run.assert_not_called()

    def test_default_refused(self):
        self._pruefe({}, lambda e: isinstance(e, acquisition.ForkAcquisitionRefused)
                                 and e.exit_code == 5)

    def test_wrong_allow_refused(self):
        self._pruefe({"STRATA_FORK_ALLOW_ACQUIRE": "true"},
                     lambda e: isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_no_acquire_wins(self):
        self._pruefe({"STRATA_FORK_ALLOW_ACQUIRE": "1", "STRATA_NO_ACQUIRE": "1"},
                     lambda e: isinstance(e, acquisition.AcquisitionRefused)
                          and not isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_forbidden_context_wins(self):
        with acquisition.forbidden():
            self._pruefe({"STRATA_FORK_ALLOW_ACQUIRE": "1"},
                         lambda e: isinstance(e, acquisition.AcquisitionRefused)
                              and not isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_allowed_reaches_sentinels(self):
        """Positiv: mit explizitem Allow erreicht der Lauf den ersten lokalen Zugriff."""
        with mock.patch.dict(os.environ, {"STRATA_FORK_ALLOW_ACQUIRE": "1"}, clear=True):
            with self.assertRaises(ReachedState):
                self.ns["launch_install"](_selbst(), {}, [])
            with self.assertRaises(ReachedPath):
                self.ns["install_job"]("fixture-spec.json")
        self.path_mock.assert_called_once_with("fixture-spec.json")

    def test_main_install_job_exit5(self):
        """main --install-job: typisierte Verweigerung wird Exit 5 statt Traceback."""
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stderr(buf):
                rc = self.ns["main"](["--install-job", "fixture-spec.json"])
        self.assertEqual(rc, 5)
        self.assertIn("controlled procurement", buf.getvalue())
        self.assertNotIn("Traceback", buf.getvalue())
        self.path_mock.assert_not_called()
        self.popen.assert_not_called()
        self.run.assert_not_called()

    def test_module_init_bootstrap(self):
        """Nur die drei Kopf-Nodes (DEFAULT_ROOT, sys.path-Guard, acquisition-Import)
        in echter Reihenfolge ausfuehren — kein Gesamt-MCP-Import."""
        baum = ast.parse(SRC)
        idx = next(i for i, n in enumerate(baum.body)
                   if isinstance(n, ast.Assign) and n.targets
                   and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "DEFAULT_ROOT")
        guard = baum.body[idx + 1]
        imp = baum.body[idx + 2]
        self.assertIsInstance(guard, ast.If)
        self.assertIsInstance(imp, ast.ImportFrom)
        self.assertEqual(imp.module, "strata_control")
        self.assertIn("acquisition", [a.name for a in imp.names])
        ns = {"Path": Path, "sys": sys, "__file__": "/src/tools/strata_mcp.py"}
        with mock.patch.object(sys, "path", ["/usr/lib/python3.14"]):
            exec(compile(ast.Module(body=[baum.body[idx], guard, imp], type_ignores=[]),
                         "mcp-head", "exec"), ns)
            self.assertEqual(sys.path[0], "/src")
        self.assertIs(ns["acquisition"], acquisition)
        self.assertNotIn("setup", sys.modules)
        # Gesamt-Datei laesst sich syntax-sauber kompilieren (ohne exec).
        compile(SRC, "strata_mcp.py", "exec")

    def test_no_acquire_pop_removed(self):
        """Statischer AST-Check: install_job entfernt STRATA_NO_ACQUIRE nicht mehr."""
        baum = ast.parse(SRC)
        job = next(n for n in baum.body
                   if isinstance(n, ast.FunctionDef) and n.name == "install_job")
        for n in ast.walk(job):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == "pop" and n.args \
                    and isinstance(n.args[0], ast.Constant) \
                    and n.args[0].value == "STRATA_NO_ACQUIRE":
                self.fail("install_job entfernt STRATA_NO_ACQUIRE noch immer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
