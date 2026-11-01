# test_fork_dsv41_gate.py — die DSV41-Beschaffungsprimitiven (lokale Paketinstallation,
# Remote-Download, Upgrade, Remote-Erreichbarkeitsprobe) muessen am Acquisition-Gate haengen;
# die lokale Read-Only-Probe bleibt erlaubt.
#
# Echtes geprueftes Modul dsv41_engine + echtes acquisition; Path/shutil/urlopen sind
# Mocks — keine Datei, kein Socket, kein Download.
import os
import shutil
import sys
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import strata_control                                  # noqa: E402
from strata_control import acquisition, dsv41_engine   # noqa: E402

URL = "https://updates.invalid/feed.json"
FAKE_TRANSFER = SimpleNamespace(
    kind_of=lambda source: "path" if source == "fixture-local" else "https",
    _local_path=lambda source: SimpleNamespace(exists=lambda: True),
)

CALLS = (
    ("install_package", lambda d: d.install_package("unused-dest", "unused-package")),
    ("install",         lambda d: d.install("unused-dest", URL)),
    ("upgrade",         lambda d: d.upgrade("unused-dest", URL)),
    ("source_reachable", lambda d: d.source_reachable(URL)),
)


class TestDsv41Gate(unittest.TestCase):

    def setUp(self):
        # Path und rmtree duerfen auf dem verweigerten Pfad nie laufen; urlopen ist
        # stets gemockt, damit auch der Negativbeleg kein echtes Netz beruehrt.
        self._patches = [
            mock.patch.object(dsv41_engine, "Path",
                              mock.Mock(side_effect=AssertionError("unerwarteter Pfadzugriff"))),
            mock.patch.object(shutil, "rmtree", mock.Mock()),
            mock.patch.object(strata_control, "transfer", FAKE_TRANSFER, create=True),
            mock.patch.object(urllib.request, "urlopen",
                              mock.Mock(return_value=SimpleNamespace(close=mock.Mock()))),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _rufe_alle_auf(self, env, erwarte):
        for name, aufruf in CALLS:
            with self.subTest(funktion=name):
                with mock.patch.dict(os.environ, env, clear=True):
                    try:
                        aufruf(dsv41_engine)
                    except Exception as exc:
                        if not erwarte(exc):
                            raise
                    else:
                        if erwarte is not None:
                            raise AssertionError(f"{name} lief ohne Gate weiter")
        shutil.rmtree.assert_not_called()
        dsv41_engine.Path.assert_not_called()

    def test_default_refused(self):
        self._rufe_alle_auf({},
            lambda e: isinstance(e, acquisition.ForkAcquisitionRefused) and e.exit_code == 5)

    def test_wrong_allow_refused(self):
        self._rufe_alle_auf({"STRATA_FORK_ALLOW_ACQUIRE": "true"},
            lambda e: isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_no_acquire_wins(self):
        self._rufe_alle_auf({"STRATA_FORK_ALLOW_ACQUIRE": "1", "STRATA_NO_ACQUIRE": "1"},
            lambda e: isinstance(e, acquisition.AcquisitionRefused)
                      and not isinstance(e, acquisition.ForkAcquisitionRefused))

    def test_forbidden_context_wins(self):
        with acquisition.forbidden():
            self._rufe_alle_auf({"STRATA_FORK_ALLOW_ACQUIRE": "1"},
                lambda e: isinstance(e, acquisition.AcquisitionRefused)
                          and not isinstance(e, acquisition.ForkAcquisitionRefused))

    # ---------- Positiv-Faelle ----------
    def test_allowed_remote_probe(self):
        with mock.patch.dict(os.environ, {"STRATA_FORK_ALLOW_ACQUIRE": "1"}, clear=True):
            ok = dsv41_engine.source_reachable(URL)
        self.assertTrue(ok)
        urllib.request.urlopen.assert_called_once()
        req = urllib.request.urlopen.call_args.args[0]
        self.assertEqual(req.get_method(), "HEAD")
        self.assertEqual(req.full_url, "https://updates.invalid/")
        req_gescheitert = urllib.request.urlopen.call_args.kwargs
        self.assertEqual(req_gescheitert.get("timeout", 10), 10)
        urllib.request.urlopen.return_value.close.assert_called_once()

    def test_local_probe_allowed_without_acquisition(self):
        with mock.patch.dict(os.environ, {"STRATA_NO_ACQUIRE": "1"}, clear=True):
            ok = dsv41_engine.source_reachable("fixture-local")
        self.assertTrue(ok)
        urllib.request.urlopen.assert_not_called()
        dsv41_engine.Path.assert_not_called()

    def test_default_remote_probe_refused(self):
        """Negativbeleg-Fokus: die Remote-HEAD-Probe war vor dem Fix ungated."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(acquisition.ForkAcquisitionRefused):
                dsv41_engine.source_reachable(URL)
        urllib.request.urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
