"""Engine-Auto-Recovery (opt-in "engine_auto_restart"): der Watchdog startet eine gestorbene StrataEngine
wieder, innerhalb eines strikten Versuchsbudgets - nie solange ein Request läuft, wartet oder noch ausläuft,
nie eine absichtlich entladene oder gerade (re)startende Engine, und nur echte StrataEngines werden überwacht.

Die Unit-Ticks fahren Service.recovery_tick über eine Stub-Engine mit injizierter Monotonic-Uhr (fifo, status
und live_reqs des Service sind die echten).  Die Integrations-Tests lassen die echte StrataEngine über einen
Fake-Prozess hinter HTTP laufen: ein extern getötetes (oder per nativem ERR gestorbenes) Kind wird ohne neue
Generation wieder gestartet, /health und /slots berichten es, und der API-Key gate-t /v1 weiterhin.

    python -m unittest serve.test_engine_recovery -v
"""
import collections
import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from serve.frontend import ChatTemplate
from serve.server import (ByteTokenizer, EngineDied, EngineStarting, EngineStuck, GpuBusy, MockEngine,
                          Service, StrataEngine, config_bool, serve, shutdown_closers)
import serve.server as server


class StubEngine:
    """Die Sicht der Recovery auf eine Engine: alive/unloaded/starting-Flags plus restart(), das die
    übergebenen Werte (tries, start_retries) aufzeichnet.  unload_calls zählt das ordentliche Entladen."""

    def __init__(self):
        self.max_context = 4096
        self.alive_v = True
        self.unloaded = False
        self.starting = False
        self.restarts = []            # je ein (tries, start_retries)-Tupel pro restart()-Aufruf
        self.unload_calls = 0
        self.fail = None              # eine Ausnahme, die restart() einmal wirft
        self.gate = None              # ein Event, auf das restart() wartet (blockierter-Start-Test)
        self.entered = None           # ein Event, das restart() NACH starting=True setzt (Race-freies Warten)

    def alive(self):
        return self.alive_v

    def exit_code(self):
        return 1

    def close(self):
        self.alive_v = False

    def unload(self):
        self.unload_calls += 1
        self.unloaded = True
        self.alive_v = False

    def restart(self, tries=3, *, start_retries=None):
        # wie die echte Engine: "starting" ist waehrend des ganzen Neustarts gesetzt (auch im Gate-Warten),
        # erst danach lebt sie wieder bzw. der Versuch scheitert
        self.restarts.append((tries, start_retries))
        self.starting = True
        if self.entered is not None:
            self.entered.set()        # erst JETZT ist starting=True - Tests warten darauf, nicht auf den Aufruf
        try:
            if self.gate is not None:
                self.gate.wait(timeout=30)
            if self.fail is not None:
                e, self.fail = self.fail, None
                raise e
            self.alive_v = True
            self.unloaded = False
        finally:
            self.starting = False


def make_service(engine=None, auto_restart=True, eligible=True):
    svc = Service(engine or StubEngine(), ByteTokenizer(),
                  ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
    svc.engine_auto_restart = auto_restart
    if eligible:
        svc._recovery_eligible = lambda: True   # die Stub-Engine spielt die überwachte StrataEngine
    return svc


class ConfigSeam(unittest.TestCase):
    """config_bool ist die Stelle, über die main() "engine_auto_restart" liest - der echte Config-Pfad."""

    def test_default_and_booleans(self):
        self.assertIs(config_bool({}, "engine_auto_restart"), False)             # Default: aus
        self.assertIs(config_bool({"engine_auto_restart": True}, "engine_auto_restart"), True)
        self.assertIs(config_bool({"engine_auto_restart": False}, "engine_auto_restart"), False)

    def test_non_bool_values_rejected(self):
        for bad in ("yes", "true", "", None, 1, 0, ["x"], {"x": 1}):
            with self.assertRaises(SystemExit, msg=repr(bad)):
                config_bool({"engine_auto_restart": bad}, "engine_auto_restart")


class TickUnits(unittest.TestCase):
    """Deterministische Ticks: injizierte Uhr, Stub-Engine, echte fifo/status."""

    def svc(self, **kw):
        s = make_service(**kw)
        s.now = [1000.0]                            # eine veränderbare Zelle, die die injizierte Uhr liest
        s._recovery_clock = lambda: s.now[0]
        self.addCleanup(s.stop_engine_recovery)
        return s

    def tick(self, svc, t=None):
        if t is not None:
            svc.now[0] = t
        return svc.recovery_tick()

    def dead(self, svc):
        svc.engine.alive_v = False
        return svc

    def test_optout_never_restarts(self):
        svc = self.svc(auto_restart=False)
        self.dead(svc)
        self.assertEqual(self.tick(svc), "disabled")
        self.assertEqual(svc.engine.restarts, [])
        self.assertFalse(svc.engine_recovery_status()["enabled"])

    def test_non_strata_engine_not_supervised(self):
        tok = ByteTokenizer()
        svc = Service(MockEngine(tok, "hi"), tok,
                      ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        self.addCleanup(svc.stop_engine_recovery)
        svc.engine_auto_restart = True
        self.assertEqual(svc.recovery_tick(), "disabled")      # die echte Prüfung: Typ ist nicht StrataEngine
        self.assertEqual(svc.engine_recovery_status()["state"], "disabled")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            svc.start_engine_recovery()
        self.assertIn("keine Auto-Recovery", buf.getvalue())   # Warnung statt stiller Supervisor
        self.assertIsNone(svc._recovery_thread)                # und es startet kein Worker

    def test_dead_engine_restarts_once_with_single_native_start(self):
        svc = self.svc()
        self.dead(svc)
        self.assertEqual(self.tick(svc), "idle")
        # die Recovery fragt genau einen Versuch an und deaktiviert die internen transienten Wiederholungen:
        # ein gebuchter Versuch ist genau ein nativer Start (hartes Budget)
        self.assertEqual(svc.engine.restarts, [(1, 0)])
        self.assertTrue(svc.engine.alive())
        st = svc.engine_recovery_status()
        self.assertEqual((st["enabled"], st["state"], st["attempts_in_window"]), (True, "idle", 1))

    def test_healthy_engine_is_left_alone(self):
        svc = self.svc()
        self.assertEqual(self.tick(svc), "idle")                # lebt: nichts zu tun
        self.assertEqual(svc.engine.restarts, [])

    def test_explicit_unload_not_restarted(self):
        svc = self.svc()
        svc.engine.unload()
        self.assertEqual(self.tick(svc), "idle")
        self.assertEqual(svc.engine.restarts, [])

    def test_lazy_engine_is_not_started_but_manual_load_works(self):
        svc = self.svc()
        svc.engine.alive_v = False
        svc.engine.unloaded = True                              # lazy: noch nie gestartet
        self.assertEqual(self.tick(svc), "idle")                # die Recovery fasst die Absicht nicht an
        self.assertEqual(svc.engine.restarts, [])
        svc.load()                                              # ein manuelles Laden bleibt möglich ...
        self.assertEqual(svc.engine.restarts, [(3, None)])      # ... über den argumentfreien Default-Pfad
        self.assertTrue(svc.engine.alive())

    def test_unload_of_dead_engine_cleans_up_and_is_not_restarted(self):
        svc = self.svc()
        self.dead(svc)
        # kein bloßes Flag-Setzen: engine.unload() räumt Prozess-Handle und Vision ordentlich auf
        self.assertEqual(svc.unload(), "not loaded")
        self.assertEqual(svc.engine.unload_calls, 1)
        self.assertTrue(svc.engine.unloaded)
        self.assertEqual(self.tick(svc), "idle")
        self.assertEqual(svc.engine.restarts, [])

    def test_unload_dead_engine_releases_live_encoder_once(self):
        svc = self.svc()
        self.dead(svc)
        svc.vision = mock.Mock()
        svc.vision.alive.return_value = True
        svc.vision_held = True
        self.assertEqual(svc.unload(), "not loaded")
        svc.vision.unload.assert_called_once_with()
        self.assertFalse(svc.vision_held)
        self.assertTrue(svc.engine.unloaded)

    def test_unload_dead_engine_with_busy_or_draining_request_stays_busy(self):
        for mark in ("busy", "queued", "live"):
            svc = self.svc()
            self.dead(svc)
            with svc.status_lock:
                if mark == "busy":
                    svc.status["busy"] = True
                elif mark == "queued":
                    svc.status["queued"] = 1
                else:
                    svc.live_reqs[7] = ({"busy": True}, collections.deque())
            self.assertEqual(svc.unload(), "busy", mark)        # laufender/auslaufender Request zuerst
            self.assertEqual(svc.engine.unload_calls, 0, mark)  # keine Aufräumaktion, keine Flag-Markierung
            self.assertFalse(svc.engine.unloaded, mark)

    def test_idle_unload_dead_engine_respects_the_deadline(self):
        svc = self.svc()
        self.dead(svc)
        svc.last_request_at = time.time()                       # die Idle-Frist ist nicht erreicht
        self.assertEqual(svc.unload(idle_for=300), "busy")      # -> "busy", keine Zustandsänderung
        self.assertEqual(svc.engine.unload_calls, 0)
        self.assertFalse(svc.engine.unloaded)
        self.assertEqual(svc.unload(idle_for=0), "not loaded")  # Frist abgelaufen: ordentlich aufräumen
        self.assertEqual(svc.engine.unload_calls, 1)
        self.assertTrue(svc.engine.unloaded)
        self.assertEqual(self.tick(svc), "idle")                # und nicht wiederbelebt
        self.assertEqual(svc.engine.restarts, [])

    def test_starting_engine_not_touched(self):
        svc = self.svc()
        self.dead(svc).engine.starting = True
        self.assertEqual(self.tick(svc), "idle")
        self.assertEqual(svc.engine.restarts, [])

    def test_load_waits_while_starting_when_opted_out(self):
        """Opt-out (Default): läuft gerade ein (Re-)Start, stellt sich ein Request wie bisher an die fifo und
        wartet - nur mit engine_auto_restart gibt es sofort 503 EngineStarting."""
        svc = self.svc(auto_restart=False)
        svc.engine.alive_v = False
        svc.engine.unloaded = True
        svc.engine.starting = True                       # ein fremder (Re-)Start hält die fifo unten
        svc.fifo.acquire()
        done, outcome = threading.Event(), []

        def client():
            try:
                svc.load()
                outcome.append("loaded")
            except EngineStarting:
                outcome.append("refused")
            finally:
                done.set()

        th = threading.Thread(target=client, daemon=True)
        th.start()
        self.assertFalse(done.wait(0.3))                 # wartet an der fifo statt sofort 503
        self.assertEqual(svc.status.get("queued"), 1)    # als wartend gezählt - das bisherige Verhalten
        svc.engine.starting = False                      # der (Re-)Start kommt zu Ende ...
        svc.engine.unloaded = False
        svc.engine.alive_v = True
        svc.fifo.release()
        self.assertTrue(done.wait(10))
        th.join(10)
        self.assertEqual(outcome, ["loaded"])            # ... und der wartende Request läuft normal durch
        self.assertEqual(svc.engine.restarts, [])        # ohne dass er selbst nochmal gestartet hätte

    def test_busy_queued_and_draining_requests_not_touched(self):
        for mark in ("busy", "queued", "live"):
            svc = self.svc()
            self.dead(svc)
            with svc.status_lock:
                if mark == "busy":
                    svc.status["busy"] = True
                elif mark == "queued":
                    svc.status["queued"] = 1
                else:
                    svc.live_reqs[7] = ({"busy": True}, collections.deque())
            self.assertEqual(self.tick(svc), "idle", mark)
            self.assertEqual(svc.engine.restarts, [], mark)

    def test_held_fifo_means_one_restart_only(self):
        svc = self.svc()
        self.dead(svc)
        assert svc.fifo.acquire(blocking=False)          # ein manuelles Laden (oder ein Turn) hält die fifo
        try:
            self.assertEqual(self.tick(svc), "idle")
            self.assertEqual(len(svc._recovery_attempts), 0)   # nichts gebucht, solange die fifo belegt ist
        finally:
            svc.fifo.release()
        self.assertEqual(svc.engine.restarts, [])
        self.assertEqual(self.tick(svc), "idle")               # jetzt geht es: genau ein Neustart
        self.assertEqual(svc.engine.restarts, [(1, 0)])

    def test_concurrent_manual_load_and_tick_start_once(self):
        svc = self.svc()
        self.dead(svc)
        gate = threading.Event()
        svc.engine.gate = gate                                # restart() blockiert, bis das Gate aufgeht
        self.addCleanup(gate.set)                             # ein Fehlschlag laesst den Start trotzdem los
        entered = threading.Event()
        svc.engine.entered = entered                          # wird gesetzt, sobald restart() starting=True hat
        th = threading.Thread(target=svc.load, daemon=True)   # das manuelle Laden hält die fifo im restart
        th.start()
        self.assertTrue(entered.wait(10))                     # es steckt im blockierten Neustart
        self.assertEqual(svc.recovery_tick(), "idle")         # der Tick weicht aus - kein zweiter Start
        self.assertEqual(len(svc._recovery_attempts), 0)
        gate.set()
        th.join(10)
        self.assertFalse(th.is_alive())
        self.assertTrue(svc.engine.alive())
        self.assertEqual(svc.engine.restarts, [(3, None)])    # nur das manuelle Laden hat gestartet

    def test_concurrent_tick_and_manual_load_start_once(self):
        svc = self.svc()
        self.dead(svc)
        gate = threading.Event()
        svc.engine.gate = gate
        self.addCleanup(gate.set)
        entered = threading.Event()
        svc.engine.entered = entered                          # erst NACH starting=True - der 503 ist so sicher
        th = threading.Thread(target=svc.recovery_tick, daemon=True)   # der Tick hält die fifo im restart
        th.start()
        self.assertTrue(entered.wait(10))
        loaded, refused = threading.Event(), threading.Event()

        def manual():
            try:
                svc.load()
                loaded.set()
            except EngineStarting:
                refused.set()     # Opt-in: ein laufender (Re-)Start beantwortet 503 statt Warten

        th2 = threading.Thread(target=manual, daemon=True)
        th2.start()
        th2.join(10)
        self.assertFalse(th2.is_alive())                      # die Antwort kommt sofort, kein Warten
        self.assertTrue(refused.is_set())                     # deterministisch EngineStarting (starting war an)
        self.assertFalse(loaded.is_set())                     # und kein zweiter Start durch das manuelle Laden
        gate.set()
        th.join(10)
        self.assertFalse(th.is_alive())
        self.assertTrue(svc.engine.alive())
        self.assertEqual(svc.engine.restarts, [(1, 0)])       # nur die Recovery hat gestartet

    def test_min_gap_backoff(self):
        svc = self.svc()
        self.dead(svc)
        self.tick(svc, 1000.0)
        self.dead(svc)
        self.assertEqual(self.tick(svc, 1005.0), "backoff")   # 5 s < 15 s seit dem letzten Versuch
        self.assertEqual(svc.engine.restarts, [(1, 0)])
        st = svc.engine_recovery_status()
        self.assertEqual(st["state"], "backoff")
        self.assertAlmostEqual(st["retry_after_s"], 10.0, delta=0.2)
        self.assertEqual(self.tick(svc, 1016.0), "idle")      # 16 s später: der nächste Versuch
        self.assertEqual(svc.engine.restarts, [(1, 0), (1, 0)])

    def test_budget_exhausted_and_window_rolls(self):
        svc = self.svc()
        for t in (1000.0, 1016.0, 1032.0):
            self.dead(svc)
            self.tick(svc, t)
        self.assertEqual(svc.engine.restarts, [(1, 0)] * 3)
        self.dead(svc)
        self.assertEqual(self.tick(svc, 1050.0), "exhausted")  # 3 Starts in 900 s: kein vierter
        self.assertEqual(svc.engine.restarts, [(1, 0)] * 3)
        st = svc.engine_recovery_status()
        self.assertEqual((st["state"], st["attempts_in_window"]), ("exhausted", 3))
        self.assertAlmostEqual(st["retry_after_s"], 850.0, delta=0.2)    # das Fenster endet bei t=1900
        self.assertEqual(self.tick(svc, 1901.0), "idle")                 # Fenster gerollt: wieder erlaubt
        self.assertEqual(svc.engine.restarts, [(1, 0)] * 4)

    def test_failed_restart_counts_and_backs_off(self):
        svc = self.svc()
        svc.engine.fail = RuntimeError("boom")
        self.dead(svc)
        self.assertEqual(self.tick(svc, 1000.0), "backoff")    # der fehlgeschlagene Versuch zählt trotzdem
        self.assertEqual(svc.engine.restarts, [(1, 0)])
        self.assertFalse(svc.engine.alive())
        self.assertEqual(self.tick(svc, 1005.0), "backoff")    # innerhalb der Gap: kein neuer Versuch
        self.assertEqual(svc.engine.restarts, [(1, 0)])
        self.assertEqual(self.tick(svc, 1016.0), "idle")       # nach der Gap gelingt der nächste
        self.assertTrue(svc.engine.alive())

    def test_third_failed_attempt_reports_exhausted(self):
        """Statuskorrektheit: der dritte fehlgeschlagene Versuch im Fenster ist 'exhausted' mit dem
        restlichen Fenster als retry_after - nicht 'backoff' mit den 15 s der Gap."""
        svc = self.svc()
        for t in (1000.0, 1015.0, 1030.0):
            svc.engine.fail = RuntimeError("boom")
            self.dead(svc)
            self.assertEqual(self.tick(svc, t), "backoff" if t < 1030.0 else "exhausted")
        st = svc.engine_recovery_status()
        self.assertEqual(st["state"], "exhausted")
        self.assertAlmostEqual(st["retry_after_s"], 870.0, delta=0.2)    # Fensterende: 1000 + 900
        self.assertEqual(self.tick(svc, 1031.0), "exhausted")            # Budget vor der Gap geprueft

    def test_short_lived_start_counts_too(self):
        svc = self.svc()
        self.dead(svc)
        self.tick(svc, 1000.0)
        self.assertTrue(svc.engine.alive())
        self.dead(svc)                                         # stirbt direkt nach READY wieder
        self.assertEqual(self.tick(svc, 1000.5), "backoff")    # der Versuch zählte schon: Gap abwarten
        self.assertEqual(svc.engine.restarts, [(1, 0)])
        self.assertEqual(self.tick(svc, 1016.0), "idle")
        self.assertEqual(svc.engine.restarts, [(1, 0), (1, 0)])

    def test_vram_and_hook_refusals_budget_the_attempt(self):
        for kind in ("vram", "hook"):
            svc = self.svc()
            self.dead(svc)
            if kind == "vram":
                svc.min_free_vram_mib = 99999
                svc.vram_free_wait_s = 0                       # kein Warten auf freiwerdenden VRAM
                svc.free_vram_mib = lambda: 128                # Methode des Service gestubbt
            else:
                svc.before_load = [sys.executable, "-c", "import sys; sys.exit(7)"]
                svc.before_load_strict = True                  # ein Hook-Fehler verweigert den Start
            self.assertEqual(self.tick(svc, 1000.0), "backoff", kind)
            self.assertEqual(svc.engine.restarts, [], kind)              # kein nativer Start passiert
            self.assertEqual(len(svc._recovery_attempts), 1, kind)       # absichtlich budgetiert (Sicherheit)
            self.assertEqual(svc.engine_recovery_status()["state"], "backoff", kind)

    def test_stop_between_precheck_and_fifo_starts_nothing(self):
        svc = self.svc()
        eng = svc.engine
        self.dead(svc)
        real_alive = eng.alive

        def alive_then_stop():
            svc._recovery_stop.set()            # der Stop landet genau in der Vorsichts-Phase des Ticks
            return real_alive()

        eng.alive = alive_then_stop
        self.assertEqual(svc.recovery_tick(), "stopped")
        self.assertEqual(eng.restarts, [])
        self.assertEqual(len(svc._recovery_attempts), 0)

    def test_stop_between_booking_and_start_unbooks_and_starts_nothing(self):
        svc = self.svc()
        self.dead(svc)

        class StopOnUnlock:                     # Stop exakt beim Verlassen des Buchungs-Abschnitts
            def __enter__(self2):
                svc._status_lock_real.__enter__()

            def __exit__(self2, *a):
                svc._recovery_stop.set()
                return svc._status_lock_real.__exit__(*a)

        svc._status_lock_real = svc.status_lock
        svc.status_lock = StopOnUnlock()
        self.assertEqual(svc.recovery_tick(), "stopped")
        self.assertEqual(svc.engine.restarts, [])
        self.assertEqual(len(svc._recovery_attempts), 0)      # gebucht, aber nie gestartet -> ausgebucht

    def test_stop_during_blocked_restart_waits_and_never_respawns(self):
        svc = self.svc()
        svc.RECOVERY_POLL_S = 0.01
        gate = threading.Event()
        svc.engine.gate = gate
        self.addCleanup(gate.set)                         # ein Assert-Fehlschlag lässt den Start trotzdem los
        self.dead(svc)
        svc.start_engine_recovery()
        worker = svc._recovery_thread                     # Referenz sichern, bevor der Stop sie leert
        self.assertIsNotNone(worker)
        deadline = time.monotonic() + 10
        while not svc.engine.restarts and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(svc.engine.restarts, "der Worker muss im blockierten Neustart stecken")

        stopped = threading.Event()

        def stopper():
            svc.stop_engine_recovery()
            stopped.set()

        th = threading.Thread(target=stopper, daemon=True)   # der Stop läuft in einem anderen Thread
        th.start()
        self.addCleanup(th.join, 10)                      # den Stopper nie als Leiche stehen lassen
        # Cleanup-Reihenfolge beachten (LIFO): das Gate-Release NACH dem Join registrieren, damit es im
        # Fehlerfall ZUERST oeffnet und der Join nicht erst 10 s ins Leere wartet
        self.addCleanup(gate.set)
        time.sleep(0.1)
        self.assertFalse(stopped.is_set())                     # er blockiert, solange der Neustart läuft
        self.assertTrue(worker.is_alive())
        gate.set()                                             # Gate auf: der angefangene Start endet
        th.join(10)
        self.assertFalse(th.is_alive())
        self.assertTrue(stopped.is_set())
        self.assertTrue(svc.engine.alive())
        self.assertFalse(worker.is_alive())
        self.assertEqual(svc._recovery_state, "stopped")
        self.dead(svc)                                         # ein späterer Tod spawnt nichts mehr
        time.sleep(0.05)
        self.assertEqual(len(svc.engine.restarts), 1)

    def test_worker_survives_a_tick_error(self):
        svc = self.svc()
        svc.RECOVERY_POLL_S = 0.01
        ticks = [0]
        real = svc.recovery_tick

        def bad_tick():
            ticks[0] += 1
            if ticks[0] == 1:
                raise RuntimeError("boom")
            return real()

        svc.recovery_tick = bad_tick
        svc.start_engine_recovery()
        deadline = time.monotonic() + 10
        while ticks[0] < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertGreaterEqual(ticks[0], 3, "der Worker tickt nach einem Fehler weiter")
        self.assertTrue(svc._recovery_thread.is_alive())
        svc.stop_engine_recovery()


FAKE = r'''
import sys
print('READY 4096 stop', flush=True)
for line in sys.stdin:
    if line.startswith('QUIT'):
        break
    if line.startswith(('GEN ', 'BGEN ')):
        print('T 90\nDONE 1 1 0 1 stop', flush=True)
'''

# die erste Generation erzeugt ein natives Fatal-Verify-ERR (der _pump markiert die Engine ended und
# terminiert den Prozess); jede spätere Engine-Generation antwortet normal
FATAL_FAKE = r'''
import sys
from pathlib import Path
state = Path(sys.argv[sys.argv.index('--state') + 1])
print('READY 4096 stop', flush=True)
for line in sys.stdin:
    if line.startswith('QUIT'):
        break
    if line.startswith(('GEN ', 'BGEN ')):
        if not state.exists():
            state.write_text('first request ran')
            print('ERR verify: timed out at layer 18; its GPU waits were released and the GPU finished (#267)',
                  flush=True)
            print('DONE 0 1 0 1 error', flush=True)
            continue
        print('T 90\nDONE 1 1 0 1 stop', flush=True)
'''

# wartet vor READY auf eine Gate-Datei: blockierte Readiness deterministisch testbar
GATED_FAKE = r'''
import sys, time
from pathlib import Path
gate = Path(sys.argv[sys.argv.index('--gate') + 1])
while not gate.exists():
    time.sleep(0.05)
print('READY 4096 stop', flush=True)
for line in sys.stdin:
    if line.startswith('QUIT'):
        break
    if line.startswith(('GEN ', 'BGEN ')):
        print('T 90\nDONE 1 1 0 1 stop', flush=True)
'''

# nur der erste Start meldet READY; jeder spätere Start beendet sich sofort, ohne eine Zeile zu schreiben
# (ein transienter Startfehler, den __init__ intern wiederholen würde - STRATA_START_RETRIES)
TRANSIENT_FAKE = r'''
import sys
from pathlib import Path
state = Path(sys.argv[sys.argv.index('--state') + 1])
if state.exists():
    sys.exit(2)
state.write_text('x')
print('READY 4096 stop', flush=True)
for line in sys.stdin:
    if line.startswith('QUIT'):
        break
    if line.startswith(('GEN ', 'BGEN ')):
        print('T 90\nDONE 1 1 0 1 stop', flush=True)
'''

REAL_POPEN = server.subprocess.Popen


def redirect_engine_spawns(script, counter=None):
    """Popen-Fake für die Tests: nur Engine-Spawns (cmd[0] == "strata") werden auf das Fake-Skript
    umgeschrieben (und bei gegebenem counter gezählt); jeder andere Prozessstart im selben Prozess
    läuft unverändert durch - subprocess.Popen ist global gepatcht, nicht nur der Server-Pfad."""
    real = REAL_POPEN

    def fake(cmd, **kw):
        if cmd and cmd[0] == "strata":
            if counter is not None:
                counter.append(cmd)
            return real([sys.executable, str(script), *cmd[1:]], **kw)
        return real(cmd, **kw)

    return fake


class RecoveryOverHttp(unittest.TestCase):
    """Eine echte StrataEngine über einem Fake-Prozess: das Kind gekillt, der Watchdog startet es von selbst."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        script = Path(self.tmp.name) / "fake_engine.py"
        script.write_text(FAKE)
        self._patch = mock.patch.object(
            server.subprocess, "Popen", redirect_engine_spawns(script))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.engine = StrataEngine("strata", ["--max-context", "4096"])
        self.addCleanup(self.engine.close)
        self.svc = Service(self.engine, ByteTokenizer(),
                           ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        self.svc.engine_auto_restart = True
        self.svc.RECOVERY_POLL_S = 0.05
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path, key=None):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        with urllib.request.urlopen(urllib.request.Request(self.base + path, headers=headers), timeout=10) as r:
            return json.loads(r.read().decode())

    def post_chat(self, key=None):
        body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8,
                "chat_template_kwargs": {"enable_thinking": False}}
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def kill_engine(self):
        self.engine.proc.kill()
        self.engine.proc.wait(timeout=10)
        deadline = time.monotonic() + 10
        while self.engine.alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.engine.alive())

    def wait_loaded(self):
        deadline = time.monotonic() + 30
        health = {}
        while time.monotonic() < deadline:
            health = self.get("/health")
            if health.get("loaded"):
                break
            time.sleep(0.1)
        return health

    def test_dead_engine_recovers_without_a_request(self):
        self.assertTrue(self.engine.alive())
        self.kill_engine()
        health = self.wait_loaded()
        self.assertTrue(health.get("loaded"), "der Watchdog hat die Engine nicht zurückgebracht")
        rec = health["engine_recovery"]
        self.assertTrue(rec["enabled"])
        self.assertGreaterEqual(rec["attempts_in_window"], 1)
        self.assertIn(rec["state"], ("idle", "restarting", "backoff"))
        slots = self.get("/slots")
        self.assertTrue(slots and slots[0]["n_ctx"] == 4096, "/slots meldet die wiederhergestellte Engine")
        out = self.post_chat()                  # die Engine antwortet wirklich wieder, nicht nur ein Flag
        self.assertEqual(out["usage"]["completion_tokens"], 1)

    def test_api_key_still_gates_after_recovery(self):
        self.svc.api_key = "testkey"
        self.kill_engine()
        self.assertTrue(self.wait_loaded().get("loaded"))
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post_chat()                                     # ohne Key bleibt es 401
        self.assertEqual(e.exception.code, 401)
        out = self.post_chat(key="testkey")                      # mit Key läuft die wiederhergestellte Engine
        self.assertEqual(out["usage"]["completion_tokens"], 1)

    def test_status_endpoint_reports_recovery(self):
        st = self.get("/v1/status")
        self.assertEqual(st["engine_recovery"]["enabled"], True)
        self.assertEqual(st["engine_recovery"]["state"], "idle")

    def test_load_endpoint_503s_on_engine_failures(self):
        """POST /load: eine Exception aus svc.load() (tot, haengend, GPU belegt) wird 503-JSON statt
        SocketDrop - Retry-After bleibt den Refusals vorbehalten, die einen liefern (GpuBusy)."""
        for exc, retry in ((EngineDied("engine died"), None), (EngineStuck("engine stuck"), None),
                           (GpuBusy("gpu busy", retry_after=7), "7")):
            real = self.svc.load
            self.svc.load = mock.Mock(side_effect=exc)
            try:
                req = urllib.request.Request(self.base + "/load", data=b"{}",
                                             headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(req, timeout=10)
            finally:
                self.svc.load = real
            self.assertEqual(e.exception.code, 503, exc)
            body = json.loads(e.exception.read().decode())
            self.assertEqual(body["error"]["type"], "server_error", exc)
            self.assertEqual(e.exception.headers.get("Retry-After"), retry, exc)

    def test_server_close_stops_the_worker(self):
        svc = make_service()                      # Stub-Engine, eigener Server
        svc.RECOVERY_POLL_S = 0.01
        httpd = serve(svc, port=0)
        worker = svc._recovery_thread
        self.assertIsNotNone(worker)                      # der Worker läuft wirklich, nicht nur "kein Attribut"
        self.assertTrue(worker.is_alive())
        httpd.shutdown()
        httpd.server_close()                      # server_close stoppt genau diesen Watchdog mit dem Server
        self.assertEqual(svc._recovery_state, "stopped")
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        svc.stop_engine_recovery()                # idempotent

    def test_shutdown_order_is_http_then_recovery_then_engine(self):
        svc = make_service()
        calls = []

        class FakeHttpd:
            def shutdown(self):
                calls.append("httpd")

        svc.stop_engine_recovery = lambda: calls.append("recovery")
        svc.engine.close = lambda: calls.append("engine")
        # dieselbe Liste, die main() fährt: der Recovery-Worker wird vor dem close der Engine gejoint,
        # damit ein laufender Neustart zu Ende kommt
        for close in shutdown_closers(FakeHttpd(), svc, svc.engine, None, None):
            close()
        self.assertEqual(calls, ["httpd", "recovery", "engine"])


class FatalRecoveryOverHttp(unittest.TestCase):
    """Ein natives Fatal-Verify-ERR über HTTP: die Anfrage bekommt genau einen Fehler, kein Replay - und der
    Watchdog bringt die Engine selbst zurück, sobald der Turn frei ist."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        script = Path(self.tmp.name) / "fake_engine.py"
        script.write_text(FATAL_FAKE)
        self._patch = mock.patch.object(
            server.subprocess, "Popen", redirect_engine_spawns(script))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.engine = StrataEngine("strata", ["--max-context", "4096",
                                              "--state", str(self.state)])
        self.addCleanup(self.engine.close)
        self.svc = Service(self.engine, ByteTokenizer(),
                           ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        self.svc.engine_auto_restart = True
        self.svc.RECOVERY_POLL_S = 5.0            # sehr langsam: der Worker tickt in der Haltephase nicht dazwischen
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path, key=None):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        with urllib.request.urlopen(urllib.request.Request(self.base + path, headers=headers), timeout=10) as r:
            return json.loads(r.read().decode())

    def test_fatal_error_fails_once_then_watchdog_recovers(self):
        body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8, "stream": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read().decode()
        self.assertIn('"error"', text)                                 # genau eine Fehlerantwort ...
        self.assertTrue(text.rstrip().endswith("data: [DONE]"))
        self.assertEqual(len(self.svc.history), 1)                     # ... nichts gezählt/replayed
        self.assertEqual(self.svc.history[-1]["finish"], "error")
        self.assertEqual(self.svc.totals["requests"], 1)
        deadline = time.monotonic() + 10
        while self.engine.alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.engine.alive())
        self.assertFalse(self.get("/health")["loaded"])

        # solange die fifo belegt ist (ein Request der toten Engine läuft noch aus), darf ein Tick weder
        # starten noch buchen - direkt aufgerufen statt auf den langsamen Worker zu hoffen
        self.assertTrue(self.svc.fifo.acquire(blocking=False))
        try:
            self.assertEqual(self.svc.recovery_tick(), "idle")
            self.assertFalse(self.engine.alive())
            self.assertEqual(len(self.svc._recovery_attempts), 0)      # auch nichts budgetiert
        finally:
            self.svc.fifo.release()

        self.svc.RECOVERY_POLL_S = 0.05                                # jetzt darf der Watchdog schnell ticken
        health = {}
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            health = self.get("/health")
            if health.get("loaded"):
                break
            time.sleep(0.1)
        self.assertTrue(health.get("loaded"), "kein neuer Request: die Recovery hat selbst gestartet")
        slots = self.get("/slots")
        self.assertTrue(slots and slots[0]["n_ctx"] == 4096)
        self.assertEqual(len(self.svc.history), 1)                     # die Wiederherstellung zählt keinen Request

        self.svc.api_key = "k"                                         # Auth bleibt nach der Recovery intakt
        with self.assertRaises(urllib.error.HTTPError) as e:
            req = urllib.request.Request(self.base + "/v1/chat/completions",
                                         data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(e.exception.code, 401)
        body["stream"] = False
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer k"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(json.loads(r.read().decode())["usage"]["completion_tokens"], 1)


class BlockedReadinessOverHttp(unittest.TestCase):
    """Die Recovery steckt im blockierten Start (die Gate-Datei fehlt): /health zeigt restarting + loaded false,
    /slots ist leer und eine Anfrage bekommt 503 EngineStarting - sobald die Gate da ist, wird es gesund."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gate = Path(self.tmp.name) / "gate"
        self.gate.write_text("go")                                     # der erste Start läuft sofort
        script = Path(self.tmp.name) / "fake_engine.py"
        script.write_text(GATED_FAKE)
        self._patch = mock.patch.object(
            server.subprocess, "Popen", redirect_engine_spawns(script))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.engine = StrataEngine("strata", ["--max-context", "4096",
                                              "--gate", str(self.gate)])
        self.addCleanup(self.engine.close)
        self.svc = Service(self.engine, ByteTokenizer(),
                           ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        self.svc.engine_auto_restart = True
        self.svc.RECOVERY_POLL_S = 0.05
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.gate.write_text("go")                                     # blockierte Starts loslassen
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode())

    def test_blocked_restart_reports_restarting_and_503s_requests(self):
        self.gate.unlink()                                  # der nächste Start wartet in der Readiness
        self.engine.proc.kill()
        self.engine.proc.wait(timeout=10)
        deadline = time.monotonic() + 15
        while not getattr(self.engine, "starting", False) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.engine.starting, "die Recovery steckt nicht im blockierten Start")
        health = self.get("/health")
        self.assertFalse(health["loaded"])
        self.assertEqual(health["engine_recovery"]["state"], "restarting")
        self.assertEqual(self.get("/slots"), [])
        body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(e.exception.code, 503)             # EngineStarting: "try again shortly"
        # /load bekommt im blockierten Start dieselbe 503-JSON-Antwort statt eines Verbindungsabbruchs
        req = urllib.request.Request(self.base + "/load", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as e2:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(e2.exception.code, 503)
        body2 = json.loads(e2.exception.read().decode())
        self.assertEqual(body2["error"]["type"], "server_error")
        self.assertIn("starting", body2["error"]["message"])
        self.gate.write_text("go")                          # die Readiness kommt durch
        deadline = time.monotonic() + 30
        health = {}
        while time.monotonic() < deadline:
            health = self.get("/health")
            if health.get("loaded"):
                break
            time.sleep(0.1)
        self.assertTrue(health.get("loaded"))
        self.assertTrue(self.get("/slots"))


class HardBudgetPopens(unittest.TestCase):
    """Hartes Budget: ein gebuchter Recovery-Versuch ist genau ein nativer Prozessstart - die internen
    transienten Wiederholungen (STRATA_START_RETRIES) dürfen das Budget nicht unterlaufen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        script = Path(self.tmp.name) / "fake_engine.py"
        script.write_text(TRANSIENT_FAKE)
        self.popens = []
        self._patch = mock.patch.object(server.subprocess, "Popen",
                                        redirect_engine_spawns(script, self.popens))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        # mit Log-Datei: nur dort erkennt transient_start_failure den stillen Exit als transient
        self.engine = StrataEngine("strata", ["--max-context", "4096", "--state", str(self.state)],
                                   log=str(Path(self.tmp.name) / "engine.log"))
        self.addCleanup(self.engine.close)
        self.svc = Service(self.engine, ByteTokenizer(),
                           ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        self.svc.engine_auto_restart = True

    def test_one_tick_is_one_native_spawn_despite_start_retries(self):
        self.assertEqual(len(self.popens), 1)                        # der initiale Start
        self.engine.proc.kill()
        self.engine.proc.wait(timeout=10)
        deadline = time.monotonic() + 10
        while self.engine.alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        # der Recovery-Versuch läuft über restart(1, start_retries=0): der Prozess fällt transient weg,
        # aber es gibt keine interne Wiederholung - genau ein weiterer Popen, dann backoff
        self.assertEqual(self.svc.recovery_tick(), "backoff")
        self.assertEqual(len(self.popens), 2)
        self.assertEqual(self.svc.engine_recovery_status()["attempts_in_window"], 1)

    def test_default_restart_keeps_internal_transient_retries(self):
        self.engine.proc.kill()
        self.engine.proc.wait(timeout=10)
        deadline = time.monotonic() + 10
        while self.engine.alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        before = len(self.popens)
        # der Default-Pfad (manuelles Laden, Requests) bleibt unverändert: restart(tries=1) darf intern bis zu
        # START_RETRIES transiente Wiederholungen machen - hier 1 + 3 = 4 native Starts
        with mock.patch.object(server.time, "sleep"):                # die 2/4/8-s-Wartezeiten abkürzen
            with self.assertRaises(EngineDied):
                self.engine.restart(1)
        self.assertEqual(len(self.popens) - before, 1 + server.START_RETRIES)


class RecoverEndpointOverHttp(unittest.TestCase):
    """POST /engine/recover: der authentifizierte JSON-Stupser weckt nur den Watchdog - er startet nie
    selbst und respektiert Budget, bewusstes Entladen, Disabled und einen gestoppten Worker.
    Echte StrataEngine über dem Fake-Kind; popens zählt die nativen Spawns."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        script = Path(self.tmp.name) / "fake_engine.py"
        script.write_text(FAKE)
        self.popens = []
        self._patch = mock.patch.object(
            server.subprocess, "Popen", redirect_engine_spawns(script, self.popens))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.engine = StrataEngine("strata", ["--max-context", "4096"])
        self.addCleanup(self.engine.close)
        self.svc = Service(self.engine, ByteTokenizer(),
                           ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        self.svc.engine_auto_restart = True
        self.svc.api_key = "testkey"
        self.svc.RECOVERY_POLL_S = 0.05
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _post(self, port, key="testkey", content_type="application/json", extra=None):
        headers = {"Content-Type": content_type}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if extra:
            headers.update(extra)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/engine/recover",
                                     data=b"{}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode()), dict(r.headers.items())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or b"{}"), dict(e.headers.items())

    def post_recover(self, **kw):
        return self._post(self.httpd.server_address[1], **kw)

    def kill_engine(self):
        self.engine.proc.kill()
        self.engine.proc.wait(timeout=10)
        deadline = time.monotonic() + 10
        while self.engine.alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.engine.alive())

    def wait_loaded(self):
        deadline = time.monotonic() + 30
        health = {}
        while time.monotonic() < deadline:
            with urllib.request.urlopen(self.base + "/health", timeout=10) as r:
                health = json.loads(r.read().decode())
            if health.get("loaded"):
                break
            time.sleep(0.1)
        return health

    def test_missing_key_is_401(self):
        code, _, _ = self.post_recover(key=None)
        self.assertEqual(code, 401)

    def test_non_json_is_415_and_foreign_origin_is_403(self):
        code, _, _ = self.post_recover(content_type="text/plain")
        self.assertEqual(code, 415)                              # _own_page verlangt application/json
        code, _, _ = self.post_recover(extra={"Origin": "http://example.test"})
        self.assertEqual(code, 403)                              # eine fremde Seite darf nicht stupsen

    def test_disabled_and_non_native_are_409(self):
        for kw in ({"auto_restart": False}, {"eligible": False}):
            svc = make_service(**kw)
            svc.api_key = "testkey"
            httpd = serve(svc, port=0)
            try:
                code, body, _ = self._post(httpd.server_address[1])
                self.assertEqual(code, 409, kw)
                self.assertIn("engine_recovery", body)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_stopped_worker_is_409(self):
        svc = make_service()                                     # Watchdog läuft nach serve()
        svc.api_key = "testkey"
        httpd = serve(svc, port=0)
        try:
            svc.stop_engine_recovery()                           # gezielt gestoppt: kein Worker zum Wecken da
            code, _, _ = self._post(httpd.server_address[1])
            self.assertEqual(code, 409)
            self.assertFalse(svc.engine.restarts)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_deliberately_unloaded_is_409_and_never_restarts(self):
        svc = make_service()
        svc.api_key = "testkey"
        httpd = serve(svc, port=0)
        try:
            svc.engine.unloaded = True
            svc.engine.alive_v = False                           # bewusst entladen: kein Auferwecken
            code, _, _ = self._post(httpd.server_address[1])
            self.assertEqual(code, 409)
            self.assertFalse(svc.engine.restarts)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_dead_engine_202_then_ready_without_a_request(self):
        self.assertTrue(self.engine.alive())
        initial = len(self.popens)
        # fifo gehalten: der Worker-Tick blockiert am Neustart, bis der
        # Stupser gelandet ist — sonst rast der eigentliche Restart dem POST
        # davon und die Antwort waere 200 statt 202.
        self.svc.fifo.acquire()
        try:
            self.kill_engine()
            code, body, _ = self.post_recover()
            self.assertEqual(code, 202)
            self.assertIn("engine_recovery", body)
        finally:
            self.svc.fifo.release()
        health = self.wait_loaded()
        self.assertTrue(health.get("loaded"),
                        "der geweckte Watchdog hat die Engine nicht zurückgebracht")
        self.assertEqual(len(self.popens), initial + 1)          # genau ein Spawn - vom Worker, nicht der API
        self.assertEqual(self.svc.engine_recovery_status()["attempts_in_window"], 1)

    def test_exhausted_budget_is_429_with_retry_after_and_no_spawn(self):
        initial = len(self.popens)
        with self.svc.status_lock:
            self.svc._recovery_attempts.extend(
                [time.monotonic() - 100.0] * self.svc.RECOVERY_MAX_ATTEMPTS)
        self.kill_engine()
        deadline = time.monotonic() + 10                         # volles Budget -> nächster Tick "exhausted"
        while self.svc.engine_recovery_status()["state"] != "exhausted" and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.svc.engine_recovery_status()["state"], "exhausted")
        code, _, headers = self.post_recover()
        self.assertEqual(code, 429)
        self.assertIn("Retry-After", headers)
        time.sleep(0.3)                                          # auch nach Stupser + Ticks: kein Spawn
        self.assertEqual(len(self.popens), initial)

    def test_concurrent_recover_calls_do_not_multiply_starts(self):
        initial = len(self.popens)
        self.kill_engine()
        results = []

        def call():
            results.append(self.post_recover()[0])

        threads = [threading.Thread(target=call) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(c in (200, 202) for c in results), results)
        self.assertTrue(self.wait_loaded().get("loaded"))
        # beliebig viele Stupser wecken nur: der Worker startet genau einmal
        self.assertEqual(len(self.popens), initial + 1)

    def test_poke_in_restart_init_window_is_202_not_unloaded_409(self):
        """Regression: StrataEngine.__init__ sets unloaded=True again before clearing it at READY
        (~lines 1037->1057).  A poke landing in that constructor window used to get 409
        "unloaded on purpose" although a watchdog restart was in flight (starting=True)."""
        entered = threading.Event()
        release = threading.Event()
        real_read = Path.read_text

        def hold_build_json(self, *a, **kw):
            if self.name == "BUILD.json":
                entered.set()                                   # blocked between unloaded=True and =False
                release.wait(timeout=30)
            return real_read(self, *a, **kw)

        with mock.patch.object(Path, "read_text", hold_build_json):
            self.kill_engine()
            deadline = time.monotonic() + 20
            while not getattr(self.engine, "starting", False) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(getattr(self.engine, "starting", False),
                            "the watchdog never started the restart")
            self.assertTrue(entered.wait(timeout=20), "the restart never reached the BUILD.json read")
            self.assertTrue(self.engine.unloaded)               # inside the window the bug lived in
            code, body, _ = self.post_recover()
            self.assertEqual(code, 202, body)
            release.set()
        self.assertTrue(self.wait_loaded().get("loaded"))


class DrainAndShutdown(unittest.TestCase):
    """Shutdown-Lebenszyklus: kein Spawn waehrend Drain, 409-Poke im Drain, Watchdog-Stop vor engine.close."""

    def svc(self, **kw):
        s = make_service(**kw)
        s.now = [1000.0]
        s._recovery_clock = lambda: s.now[0]
        self.addCleanup(s.stop_engine_recovery)
        return s

    def test_draining_dead_engine_is_not_restarted(self):
        s = self.svc()
        s.engine.alive_v = False
        s.begin_drain()
        state = s.recovery_tick()
        self.assertEqual(state, "idle")
        self.assertEqual(len(s._recovery_attempts), 0)          # kein gebuchter Versuch
        self.assertFalse(s.engine.alive_v)                      # kein Spawn

    def test_recover_poke_during_drain_refuses_409(self):
        s = self.svc()
        s.begin_drain()                            # erst drain, dann Tod: kein Restart-Fenster dazwischen
        s.engine.alive_v = False
        s.start_engine_recovery()
        code, body, retry = s.request_engine_recovery()
        self.assertEqual(code, 409)
        self.assertIsNone(retry)
        self.assertIn("draining", body["error"]["message"])
        self.assertFalse(s._recovery_wake.is_set())             # kein Wake, kein Start
        self.assertFalse(s.engine.alive_v)
        self.assertEqual(len(s._recovery_attempts), 0)

    def test_shutdown_closers_stop_watchdog_before_engine_close(self):
        s = self.svc()
        engine = s.engine
        engine.closed = False
        orig_close = engine.close

        def marked_close():
            engine.closed = s._recovery_stop.is_set()           # Stop muss VOR close signalisiert sein
            orig_close()
        engine.close = marked_close
        order = shutdown_closers(None, s, engine, None, None)
        self.assertIn(s.stop_engine_recovery, order)
        self.assertLess(order.index(s.stop_engine_recovery), order.index(engine.close))
        s._recovery_stop.set()
        s._recovery_wake.set()
        for close in order:
            close()
        self.assertTrue(engine.closed)

    def test_ordinary_shutdown_drain_keeps_pending_and_stops_recovery(self):
        s = self.svc()
        s.start_engine_recovery()
        s.engine.alive_v = False
        s.begin_drain()
        # wie main(): Signal zuerst, dann Closer-Reihenfolge
        s._recovery_stop.set()
        s._recovery_wake.set()
        state = s.recovery_tick()
        self.assertEqual(state, "stopped")
        self.assertEqual(len(s._recovery_attempts), 0)
        self.assertFalse(s.engine.alive_v)


class MainLifecycle(unittest.TestCase):
    """Echte main()-Pfade (Mock-Engine, gebundenes httpd): der Watchdog wird beim Ready-Publish-
    Fehler und beim ordentlichen Shutdown tatsaechlich gestoppt und gejoint, bevor die Engine
    geschlossen wird - inklusive Fruehsignal vor dem potenziell blockierenden httpd.shutdown."""

    def _capture(self, captured, order):
        real_serve = server.serve

        def spy(svc, *a, **kw):
            httpd = real_serve(svc, *a, **kw)
            captured["svc"], captured["httpd"], captured["engine"] = svc, httpd, svc.engine
            orig_stop = svc.stop_engine_recovery

            def rec_stop():
                order.append("watchdog_stop")
                orig_stop()
            svc.stop_engine_recovery = rec_stop
            orig_close = svc.engine.close

            def rec_close():
                order.append(("engine_close", svc._recovery_stop.is_set(),
                              svc._recovery_thread is None or not svc._recovery_thread.is_alive()))
                orig_close()
            svc.engine.close = rec_close
            orig_drain = svc.begin_drain

            def rec_drain():
                order.append(("begin_drain", svc._recovery_stop.is_set()))
                return orig_drain()
            svc.begin_drain = rec_drain
            orig_cancel = svc.cancel_owned_requests

            def rec_cancel():
                order.append("cancelled")
                return orig_cancel()
            svc.cancel_owned_requests = rec_cancel
            orig_sd = httpd.shutdown

            def rec_sd():
                order.append(("httpd_shutdown", svc._recovery_stop.is_set()))
                orig_sd()
            httpd.shutdown = rec_sd
            return httpd
        return spy

    def _cfg(self, tmp):
        cfg = Path(tmp.name) / "strata-test.json"
        cfg.write_text(json.dumps({"engine_auto_restart": True}), encoding="utf-8")
        return cfg

    def test_ready_publish_failure_stops_and_joins_watchdog_before_engine_close(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        order, captured = [], {}
        with mock.patch.object(Service, "_recovery_eligible", lambda self: True), \
                mock.patch.object(server, "MockEngine", lambda *a, **kw: StubEngine()), \
                mock.patch.object(server, "serve", self._capture(captured, order)), \
                mock.patch.object(server.ready_file, "publish", side_effect=OSError("disk full")):
            rc = server.main(["--engine", "mock", "--config", str(self._cfg(tmp)),
                              "--port", "0", "--ready-file", str(Path(tmp.name) / "ready.json")])
        self.assertEqual(rc, 6)
        svc = captured["svc"]
        self.assertTrue(svc._recovery_stop.is_set())
        self.assertIsNone(svc._recovery_thread)                  # gejoint, nicht nur signalisiert
        kinds = [e[0] if isinstance(e, tuple) else e for e in order]
        self.assertLess(kinds.index("watchdog_stop"), kinds.index("engine_close"))
        self.assertTrue(next(e for e in order if e[0] == "httpd_shutdown")[1],
                        "der Stop wurde nicht VOR httpd.shutdown signalisiert")
        close = next(e for e in order if e[0] == "engine_close")
        self.assertTrue(close[1] and close[2], "die Engine wurde vor dem Watchdog-Join geschlossen")

    def test_graceful_shutdown_signals_stop_before_drain_and_close(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        order, captured, events = [], {}, []
        real_sleep = time.sleep

        def interrupt_in_main(*a, **kw):                          # nur der Hauptthread darf ausloesen
            if threading.current_thread() is threading.main_thread():
                raise KeyboardInterrupt
            return real_sleep(*a, **kw)

        def on_event(kind, payload):
            events.append(kind)
            if kind == "ready":                                   # eine offene Anfrage im Drain-Fenster
                svc = captured["svc"]
                self.assertTrue(svc.reserve_inference())
                threading.Timer(0.2, svc.release_inference).start()

        with mock.patch.object(Service, "_recovery_eligible", lambda self: True), \
                mock.patch.object(server, "MockEngine", lambda *a, **kw: StubEngine()), \
                mock.patch.object(server, "serve", self._capture(captured, order)), \
                mock.patch.object(server.time, "sleep", interrupt_in_main):
            rc = server.main(["--engine", "mock", "--config", str(self._cfg(tmp)),
                              "--port", "0", "--shutdown-timeout", "5"],
                             lifecycle_event=on_event, interrupt_exit_code=42)
        self.assertEqual(rc, 42)
        svc = captured["svc"]
        self.assertTrue(svc._recovery_stop.is_set())
        self.assertIn("draining", events)
        self.assertNotIn("cancelled", order, "die rechtzeitig freigegebene Anfrage wurde abgebrochen")
        drain = next(e for e in order if e[0] == "begin_drain")
        self.assertTrue(drain[1], "der Watchdog-Stop kam nicht VOR begin_drain")
        kinds = [e[0] if isinstance(e, tuple) else e for e in order]
        self.assertLess(kinds.index("watchdog_stop"), kinds.index("engine_close"))
        self.assertTrue(svc._recovery_thread is None or not svc._recovery_thread.is_alive())


if __name__ == "__main__":
    unittest.main()
