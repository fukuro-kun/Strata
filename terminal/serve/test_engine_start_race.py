"""Startfehler duerfen nicht vom concurrenten Schliessen verdeckt werden."""

import unittest
from unittest import mock

import serve.server as server


class Pipe:
    def close(self):
        pass

    def __iter__(self):
        return iter(())


class Process:
    returncode = 1
    stdin, stdout = Pipe(), Pipe()
    pid = 0

    def __init__(self, on_wait=lambda: None):
        self.on_wait = on_wait

    def wait(self, timeout=None):
        self.on_wait()
        return 1

    def poll(self):
        return 1

    def kill(self):
        pass


class FailedStart(unittest.TestCase):
    def test_prozess_wird_waehrend_fehlgeschlagenem_start_geschlossen(self):
        engine = server.StrataEngine.__new__(server.StrataEngine)
        process = Process(on_wait=lambda: setattr(engine, "proc", None))
        with mock.patch.object(server, "popen", return_value=process), \
             mock.patch.object(server, "end_leftover_engines"), \
             mock.patch.object(server, "transient_start_failure", return_value=False):
            with self.assertRaises(server.EngineDied):
                engine.__init__("strata", [], _start_retries=0)

    def test_prozess_wird_direkt_nach_zuweisung_geschlossen(self):
        class ReleasedImmediately(server.StrataEngine):
            def __setattr__(self, name, value):
                super().__setattr__(name, value)
                if name == "proc" and isinstance(value, Process):
                    super().__setattr__(name, None)

        engine = ReleasedImmediately.__new__(ReleasedImmediately)
        with mock.patch.object(server, "popen", return_value=Process()), \
             mock.patch.object(server, "end_leftover_engines"):
            with self.assertRaises(server.EngineDied):
                engine.__init__("strata", [], _start_retries=0)

    def test_restart_bewahrt_startfehler_wenn_prozess_schon_freigegeben_ist(self):
        class FailedEngine(server.StrataEngine):
            def __init__(self, *args, **kwargs):
                self.proc = None
                raise server.EngineDied("Start fehlgeschlagen")

            def close(self):
                pass

        engine = FailedEngine.__new__(FailedEngine)
        engine.info, engine.spawn = {}, ("strata", [])
        with self.assertRaisesRegex(server.EngineDied, "Start fehlgeschlagen"):
            engine.restart(tries=1, start_retries=0)
        self.assertFalse(engine.starting)


if __name__ == "__main__":
    unittest.main()
