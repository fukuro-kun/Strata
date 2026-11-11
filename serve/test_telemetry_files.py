"""Tests fuer das Schliessen der Linux-CPU- und Speicherdateien."""

import glob
import io
import sys
import unittest
from unittest import mock

from serve import telemetry


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux-Probedateien")
class TelemetryFiles(unittest.TestCase):
    def test_cpu_name_schliesst_datei_auch_bei_frueher_rueckgabe(self):
        source = io.StringIO("processor: 0\nmodel name : Test CPU\n")
        with mock.patch.object(telemetry.os.path, "exists", return_value=True), \
             mock.patch("builtins.open", return_value=source):
            self.assertEqual(telemetry._cpu_name(), "Test CPU")
        self.assertTrue(source.closed)

    def test_cpu_name_faellt_bei_lesefehler_zurueck(self):
        with mock.patch.object(telemetry.os.path, "exists", return_value=True), \
             mock.patch("builtins.open", side_effect=OSError("nicht lesbar")), \
             mock.patch.object(telemetry.platform, "processor", return_value="Fallback"):
            self.assertEqual(telemetry._cpu_name(), "Fallback")

    def test_cpu_name_faellt_bei_unvollstaendiger_zeile_zurueck(self):
        source = io.StringIO("model name ohne Doppelpunkt\n")
        with mock.patch.object(telemetry.os.path, "exists", return_value=True), \
             mock.patch("builtins.open", return_value=source), \
             mock.patch.object(telemetry.platform, "processor", return_value="Fallback"):
            self.assertEqual(telemetry._cpu_name(), "Fallback")
        self.assertTrue(source.closed)

    def test_cpu_topologie_schliesst_jede_datei(self):
        first, second = io.StringIO("0\n"), io.StringIO("1\n")
        with mock.patch.object(glob, "glob", side_effect=[["cpu0", "cpu1"], ["node0"]]), \
             mock.patch("builtins.open", side_effect=[first, second]):
            self.assertEqual(telemetry._cpu_topology("/test"), (2, 1))
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_cpu_zeiten_schliessen_datei(self):
        source = io.StringIO("cpu 1 2 3 4 5 6\n")
        fallback = telemetry._CpuRamFallback.__new__(telemetry._CpuRamFallback)
        with mock.patch("builtins.open", return_value=source):
            self.assertEqual(fallback._times(), (9, 21))
        self.assertTrue(source.closed)

    def test_ungueltige_cpu_zeiten_werden_als_unbekannt_gemeldet(self):
        source = io.StringIO("cpu 1\n")
        fallback = telemetry._CpuRamFallback.__new__(telemetry._CpuRamFallback)
        with mock.patch("builtins.open", return_value=source):
            self.assertIsNone(fallback._times())
        self.assertTrue(source.closed)

    def test_cpu_lesefehler_schliesst_datei(self):
        class Broken(io.StringIO):
            def readline(self, *args):
                raise OSError("Lesefehler")

        source = Broken()
        fallback = telemetry._CpuRamFallback.__new__(telemetry._CpuRamFallback)
        with mock.patch("builtins.open", return_value=source):
            self.assertIsNone(fallback._times())
        self.assertTrue(source.closed)

    def test_speicherinfo_schliesst_datei(self):
        source = io.StringIO("MemTotal: 1024 kB\nMemAvailable: 384 kB\n")
        with mock.patch("builtins.open", return_value=source):
            self.assertEqual(telemetry._CpuRamFallback.ram(), (640 * 1024, 1024 * 1024))
        self.assertTrue(source.closed)

    def test_speicherinfo_ohne_wert_ist_unbekannt(self):
        source = io.StringIO("MemTotal:\nMemAvailable: 384 kB\n")
        with mock.patch("builtins.open", return_value=source):
            self.assertEqual(telemetry._CpuRamFallback.ram(), (None, None))
        self.assertTrue(source.closed)


if __name__ == "__main__":
    unittest.main()
