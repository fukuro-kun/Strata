# test_fork_driver_floor_gate.py — die CUDA-12-Treiberfloor-Feedabfrage muss vor dem
# Threadstart am Fork-Beschaffungs-Gate haengen; lokale Floors bleiben erlaubt.
#
# Reales geprueftes driver_floor + acquisition; Thread/Feed/Signing sind Mocks —
# kein Socket, kein Download, kein Thread.
import os
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import strata_control                                  # noqa: E402
from strata_control import acquisition, driver_floor   # noqa: E402

URL = "https://updates.invalid"


class InlineThread:
    """Fuehrt target synchron in start() aus — beweist den Fetch ohne echten Thread."""
    def __init__(self, target=None, daemon=None):
        self.target = target
    def start(self):
        self.target()
    def join(self, timeout=None):
        pass


class TestDriverFloorGate(unittest.TestCase):

    def setUp(self):
        self.thread_mock = mock.Mock()
        self.fetch = mock.Mock(return_value=SimpleNamespace(engine=()))
        self.keys = mock.Mock(return_value="stubkeys")
        self._patches = [
            mock.patch.object(threading, "Thread", self.thread_mock),
            mock.patch.object(strata_control, "feed",
                              SimpleNamespace(fetch=self.fetch), create=True),
            mock.patch.object(strata_control, "signing",
                              SimpleNamespace(load_trusted_keys=self.keys), create=True),
            mock.patch.dict(sys.modules, {
                "strata_control.feed": SimpleNamespace(fetch=self.fetch),
                "strata_control.signing": SimpleNamespace(load_trusted_keys=self.keys),
            }),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _pruefe(self, env, erwarte):
        with mock.patch.dict(os.environ, env, clear=True):
            try:
                driver_floor.from_feed(URL, "linux-x86_64")
            except Exception as exc:
                if not erwarte(exc):
                    raise
            else:
                raise AssertionError("from_feed lief ohne Gate weiter")
        self.thread_mock.assert_not_called()
        self.fetch.assert_not_called()
        self.keys.assert_not_called()

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

    # ---------- Positiv-/Lokal-Faelle ----------
    def test_allowed_fetch_once(self):
        self.thread_mock.side_effect = InlineThread
        with mock.patch.dict(os.environ, {"STRATA_FORK_ALLOW_ACQUIRE": "1"}, clear=True):
            got = driver_floor.from_feed(URL, "linux-x86_64")
        self.assertIsNone(got)
        self.keys.assert_called_once_with()
        self.fetch.assert_called_once_with(URL, "stubkeys")

    def test_local_floor_without_acquisition(self):
        with mock.patch.object(driver_floor, "installed",
                               mock.Mock(return_value="576.02")) as inst, \
             mock.patch.object(driver_floor, "from_feed",
                               mock.Mock(side_effect=AssertionError("ungerlaubt"))) as remote:
            with mock.patch.dict(os.environ, {"STRATA_NO_ACQUIRE": "1"}, clear=True):
                floor, woher = driver_floor.cuda12_floor(
                    "linux-x86_64", roots=["/synthetic"], feed_source=URL)
        self.assertEqual(floor, "576.02")
        inst.assert_called_once()
        remote.assert_not_called()
        self.thread_mock.assert_not_called()

    def test_fallback_without_feed_source(self):
        with mock.patch.object(driver_floor, "installed", mock.Mock(return_value=None)):
            with mock.patch.dict(os.environ, {}, clear=True):
                floor, woher = driver_floor.cuda12_floor("linux-x86_64",
                                                         roots=[], feed_source=None)
        self.assertEqual(floor, driver_floor.FALLBACK)
        self.thread_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
