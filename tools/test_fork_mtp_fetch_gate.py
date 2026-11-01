# test_fork_mtp_fetch_gate.py - the standalone MTP fetch helper's download/metadata
# primitives must pass the fork acquisition gate; offline verify stays free.
#
# AST selection of reviewed definitions only - the module body (tls.install,
# constants) is never imported; the __main__ guard is executed separately
# with a stub main.
import argparse
import ast
import collections
import contextlib
import io
import concurrent.futures
import hashlib
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
QUELLE = (ROOT / "tools" / "mtp_fetch.py").read_text(encoding="utf-8")

sys.path.insert(0, str(ROOT))
from strata_control import acquisition  # noqa: E402

PAYLOAD = b"tensor01"
WANT = hashlib.sha256(PAYLOAD).hexdigest()
FNS = ["_final", "get", "check_range", "ranged", "sha256_of", "pinned",
       "resolve_repo", "inventory", "fetch", "verify", "main"]


class PrepSentinel(AssertionError):
    pass


class Rsp:
    """Echter Kontext-Manager als urlopen-Antwort."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _lade():
    baum = ast.parse(QUELLE)
    fns = {n.name: n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name in FNS}
    fehlt = set(FNS) - set(fns)
    assert not fehlt, f"Selektion unvollstaendig: {fehlt}"
    guard = next((n for n in baum.body
                  if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                  and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__"), None)
    ns = {
        "acquisition": acquisition, "argparse": argparse, "collections": collections,
        "concurrent": sys.modules["concurrent"],
        "hashlib": hashlib, "json": json, "os": os, "struct": struct, "sys": sys,
        "threading": threading, "time": time,
        "urllib": SimpleNamespace(request=urllib.request, error=urllib.error),
        "REPO": "https://fixture.invalid/resolve/rev/", "PINNED": "https://fixture.invalid/resolve/rev/",
        "REVISION": "rev", "BAD": 3, "SHA256": {"fixture.mtp.w": WANT},
        "CDN_TTL": 600, "_cdn": {}, "_cdn_lock": threading.Lock(),
        "__doc__": "fixture doc",
        "Progress": mock.Mock(return_value=SimpleNamespace(add=lambda n: None, show=lambda force=False: None, done=0)),
        "connections": lambda: 1,
        "shard_header": mock.Mock(side_effect=PrepSentinel("shard_header")),
        "exit_with_parent": mock.Mock(side_effect=PrepSentinel("exit_with_parent")),
        "lock_folder": mock.Mock(side_effect=PrepSentinel("lock_folder")),
    }
    exec(compile(ast.Module(body=list(fns.values()), type_ignores=[]), "mtp-extract", "exec"), ns)
    return ns, guard


class TestMtpFetchGate(unittest.TestCase):

    def setUp(self):
        self.ns, self.guard = _lade()
        self._tmpdir = tempfile.TemporaryDirectory(prefix="mtp-")
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)

    def _env(self, extra):
        return mock.patch.dict(os.environ, extra, clear=True)

    # ---------- Verweigerung: Primitiven vor erstem Zugriff ----------
    def _verweigert(self, env, erwarte):
        faelle = {
            "get": (lambda: self.ns["get"]("https://fixture.invalid/x", 0, 9, retries=1), "getchain"),
            "resolve_repo": (lambda: self.ns["resolve_repo"](), "urlopen"),
            "inventory": (lambda: self.ns["inventory"](str(self.tmp)), "get"),
            "fetch": (lambda: self.ns["fetch"](str(self.tmp), None), "exists"),
            "ranged": (lambda: next(self.ns["ranged"]("u", 0, 9, 4, 2)), "pool"),
        }
        for name, (call, sentinel) in faelle.items():
            with self.subTest(primitive=name):
                m = mock.Mock(side_effect=PrepSentinel(sentinel))
                if sentinel == "getchain":
                    final = mock.Mock(side_effect=PrepSentinel("_final"))
                    uo = mock.Mock(side_effect=PrepSentinel("urlopen"))
                    patches = [mock.patch.dict(self.ns, {"_final": final}),
                               mock.patch.object(urllib.request, "urlopen", uo)]
                    extra_asserts = lambda: (final.assert_not_called(), uo.assert_not_called())
                elif sentinel == "pool":
                    tpe = mock.Mock(side_effect=PrepSentinel("ThreadPoolExecutor"))
                    patches = [mock.patch.object(concurrent.futures, "ThreadPoolExecutor", tpe)]
                    extra_asserts = lambda: tpe.assert_not_called()
                elif sentinel == "urlopen":
                    patches = [mock.patch.object(urllib.request, "urlopen", m)]
                    extra_asserts = lambda: m.assert_not_called()
                elif sentinel == "get":
                    patches = [mock.patch.dict(self.ns, {"get": m})]
                    extra_asserts = lambda: m.assert_not_called()
                else:
                    patches = [mock.patch.object(os.path, "exists", m)]
                    extra_asserts = lambda: m.assert_not_called()
                with self._env(env), contextlib.ExitStack() as stack:
                    for p in patches:
                        stack.enter_context(p)
                    try:
                        call()
                    except Exception as exc:
                        if not erwarte(exc):
                            raise
                    else:
                        raise AssertionError(f"{name} lief ohne Gate weiter")
                extra_asserts()

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

    # ---------- main: Gate nach verify, vor Parent/Lock ----------
    def test_main_fetch_inventory_denied(self):
        for cmd in ("fetch", "inventory"):
            for env in ({}, {"STRATA_NO_ACQUIRE": "1"}):
                with self.subTest(cmd=cmd, env=env):
                    with self._env(env), mock.patch.object(sys, "argv",
                                                           ["x", cmd, "--out", str(self.tmp)]):
                        try:
                            self.ns["main"]()
                        except acquisition.AcquisitionRefused as e:
                            if env:
                                self.assertNotIsInstance(e, acquisition.ForkAcquisitionRefused)
                            else:
                                self.assertIsInstance(e, acquisition.ForkAcquisitionRefused)
                            self.assertEqual(e.exit_code, 5)
                        else:
                            raise AssertionError("main lief ohne Gate")
                    self.ns["exit_with_parent"].assert_not_called()
                    self.ns["lock_folder"].assert_not_called()

    # ---------- Positiv ----------
    def test_allowed_get_range(self):
        r = Rsp(status=206, headers={"Content-Range": "bytes 0-7/8"},
                read=lambda: PAYLOAD, geturl=lambda: "https://fixture.invalid/x")
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}), \
                mock.patch.object(urllib.request, "urlopen", mock.Mock(return_value=r)) as uo:
            self.assertEqual(self.ns["get"]("https://fixture.invalid/x", 0, 7), PAYLOAD)
        uo.assert_called_once()
        req = uo.call_args.args[0]
        self.assertEqual(req.headers.get("Range"), "bytes=0-7")

    def test_allowed_get_wrong_range_fails(self):
        r = Rsp(status=200, headers={}, read=lambda: b"x", geturl=lambda: "https://fixture.invalid/x")
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}), \
                mock.patch.object(urllib.request, "urlopen", mock.Mock(return_value=r)):
            with self.assertRaises(IOError):
                self.ns["get"]("https://fixture.invalid/x", 0, 7, retries=1)

    def test_allowed_resolve_repo(self):
        r = Rsp(close=mock.Mock())
        with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}), \
                mock.patch.object(urllib.request, "urlopen", mock.Mock(return_value=r)) as uo:
            self.assertEqual(self.ns["resolve_repo"](), self.ns["REPO"])
        uo.assert_called_once()
        self.assertEqual(uo.call_args.args[0].get_method(), "HEAD")
        r.close.assert_called_once()

    def test_allowed_ranged(self):
        with mock.patch.dict(self.ns, {"get": lambda u, a, b: b"chunk%02d" % a}):
            with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}):
                daten = list(self.ns["ranged"]("u", 0, 5, 4, 1))
        self.assertEqual(daten, [b"chunk00", b"chunk04"])

    def test_allowed_fetch(self):
        inv = {"repo": self.ns["REPO"], "total_bytes": 8,
               "tensors": [dict(name="fixture.mtp.w", shard="s.bin", dtype="BF16",
                                shape=[4], start=0, end=7, bytes=8)]}
        (self.tmp / "mtp-inventory.json").write_text(json.dumps(inv))
        with mock.patch.dict(self.ns, {"ranged": lambda u, a, b, c, w: iter([PAYLOAD])}):
            with self._env({"STRATA_FORK_ALLOW_ACQUIRE": "1"}):
                self.ns["fetch"](str(self.tmp), None)
        self.assertEqual((self.tmp / "tensors" / "fixture.mtp.w.bin").read_bytes(), PAYLOAD)
        manifest = json.loads((self.tmp / "mtp-manifest.json").read_text())
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["sha256"], WANT)
        self.assertEqual(manifest[0]["file"], "tensors/fixture.mtp.w.bin")

    # ---------- offline verify bleibt frei ----------
    def test_verify_offline(self):
        tdir = self.tmp / "tensors"
        tdir.mkdir()
        (tdir / "fixture.mtp.w.bin").write_bytes(PAYLOAD)
        for payload, want_bad in ((PAYLOAD, []), (b"corrupt!", ["fixture.mtp.w"])):
            with self.subTest(payload=payload):
                (tdir / "fixture.mtp.w.bin").write_bytes(payload)
                (tdir / "verified.json").unlink(missing_ok=True)
                with self._env({"STRATA_NO_ACQUIRE": "1"}):
                    self.assertEqual(self.ns["verify"](str(self.tmp)), want_bad)

    def test_main_verify_exits(self):
        for bad, code in (([], 0), (["x"], 3)):
            with self.subTest(bad=bad):
                with mock.patch.dict(self.ns, {"verify": lambda o: bad}), \
                        self._env({}), \
                        mock.patch.object(sys, "argv", ["x", "verify", "--out", str(self.tmp)]):
                    with self.assertRaises(SystemExit) as cm:
                        self.ns["main"]()
                self.assertEqual(cm.exception.code, code)
        self.ns["exit_with_parent"].assert_not_called()

    # ---------- __main__-Guard ----------
    def test_main_guard_typed(self):
        for exc in (acquisition.ForkAcquisitionRefused("x", "y"), acquisition.AcquisitionRefused("x", "y")):
            with self.subTest(exc=type(exc).__name__):
                buf = io.StringIO()
                ns = {"__name__": "__main__", "sys": sys, "acquisition": acquisition,
                      "main": mock.Mock(side_effect=exc)}
                with contextlib.redirect_stderr(buf):
                    with self.assertRaises(SystemExit) as cm:
                        exec(compile(ast.Module(body=[self.guard], type_ignores=[]), "guard", "exec"), ns)
                self.assertEqual(cm.exception.code, 5)
                self.assertIn("missing or out of date", buf.getvalue())
                self.assertNotIn("Traceback", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
