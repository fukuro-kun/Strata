# test_fork_local_engine_gate.py — auch eine lokale Paketinstallation muss kontrollierte
# Beschaffung bleiben: install_engine_file muss VOR dem ersten Pfadzugriff durch
# require_acquisition laufen.
#
# AST-Extrakt nur von `require_acquisition` + `install_engine_file` aus updater.py;
# das echte gepruefte acquisition-Modul liefert die Gate-Logik. Path ist ein Mock,
# der beim Erreichen ReachedPathException wirft — so beweist der Test "vor Path".
import ast
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strata_control import acquisition  # noqa: E402  (geprueftes Modul, echte Gate-Logik)

SRC = (ROOT / "strata_control" / "updater.py").read_text(encoding="utf-8")


class ReachedPathException(Exception):
    """Marker: der ungepruefte Pfad wurde erreicht — Path() wurde aufgerufen."""


def _load():
    baum = ast.parse(SRC)
    gesucht = {"require_acquisition", "install_engine_file"}
    fns = [n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name in gesucht]
    assert {n.name for n in fns} == gesucht
    path_mock = mock.Mock(side_effect=ReachedPathException)
    ns = {"Context": object, "Path": path_mock, "acquisition": acquisition}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "updater-extract", "exec"), ns)
    return ns, path_mock


class TestLocalEngineGate(unittest.TestCase):
    """Fuenf Faelle: Default/Allow/No-Acquire/forbidden()/Allow gegen den Gate."""

    def setUp(self):
        self.ns, self.path_mock = _load()
        self.fn = self.ns["install_engine_file"]

    def _call(self, env):
        with mock.patch.dict(os.environ, env, clear=True):
            try:
                self.fn(object(), "unused-local.tar.gz")
            except Exception as exc:
                return exc
        return None

    def test_default_refuses_before_path(self):
        exc = self._call({})
        self.assertIsInstance(exc, acquisition.ForkAcquisitionRefused)
        self.assertEqual(exc.exit_code, 5)
        self.path_mock.assert_not_called()

    def test_wrong_allow_value_refused(self):
        exc = self._call({"STRATA_FORK_ALLOW_ACQUIRE": "true"})
        self.assertIsInstance(exc, acquisition.ForkAcquisitionRefused)
        self.path_mock.assert_not_called()

    def test_no_acquire_wins_over_allow(self):
        exc = self._call({"STRATA_FORK_ALLOW_ACQUIRE": "1", "STRATA_NO_ACQUIRE": "1"})
        self.assertIsInstance(exc, acquisition.AcquisitionRefused)
        self.assertNotIsInstance(exc, acquisition.ForkAcquisitionRefused)
        self.path_mock.assert_not_called()

    def test_forbidden_context_wins_over_allow(self):
        with acquisition.forbidden():
            exc = self._call({"STRATA_FORK_ALLOW_ACQUIRE": "1"})
        self.assertIsInstance(exc, acquisition.AcquisitionRefused)
        self.assertNotIsInstance(exc, acquisition.ForkAcquisitionRefused)
        self.path_mock.assert_not_called()

    def test_allow_reaches_path(self):
        exc = self._call({"STRATA_FORK_ALLOW_ACQUIRE": "1"})
        self.assertIsInstance(exc, ReachedPathException)
        self.path_mock.assert_called_once_with("unused-local.tar.gz")


if __name__ == "__main__":
    unittest.main(verbosity=2)
