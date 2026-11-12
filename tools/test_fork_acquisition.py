"""Fork default-deny for acquisition primitives (STRATA_FORK_ALLOW_ACQUIRE gate).

    python tools/test_fork_acquisition.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from strata_control import acquisition          # noqa: E402
from strata_control import components            # noqa: E402

ALLOW = acquisition.FORK_ALLOW_ENV
NO = acquisition.ENV


def _env(**kw):
    keep = {k: v for k, v in os.environ.items() if k not in (ALLOW, NO)}
    keep.update({k: v for k, v in kw.items() if v is not None})
    return mock.patch.dict(os.environ, keep, clear=True)


class Gate(unittest.TestCase):
    def test_default_refuses_typed_exit5_with_offline_hint(self):
        with _env(), self.assertRaises(acquisition.ForkAcquisitionRefused) as c:
            acquisition.require("a download")
        self.assertEqual(c.exception.exit_code, 5)
        self.assertIn("OFFLINE_BUILD", str(c.exception))
        self.assertIsInstance(c.exception, acquisition.AcquisitionRefused)

    def test_non_exact_values_refuse(self):
        for bad in ("0", "true", "yes", "", "on", "10", " 1"):
            with self.subTest(v=bad), _env(**{ALLOW: bad}), \
                    self.assertRaises(acquisition.ForkAcquisitionRefused):
                acquisition.require("a download")

    def test_exact_one_allows(self):
        with _env(**{ALLOW: "1"}):
            self.assertIsNone(acquisition.require("a download"))

    def test_no_acquire_wins_over_allow(self):
        with _env(**{ALLOW: "1", NO: "1"}), \
                self.assertRaises(acquisition.AcquisitionRefused):
            acquisition.require("a download")

    def test_forbidden_context_wins_over_allow(self):
        with _env(**{ALLOW: "1"}), acquisition.forbidden(), \
                self.assertRaises(acquisition.AcquisitionRefused):
            acquisition.require("a download")

    def test_upstream_command_hints_never_reach_the_message(self):
        """A caller's 'strata update'/'./setup.sh' must not leak into the fork refusal."""
        for cmd in ("./setup.sh", "strata update", "strata install"):
            with self.subTest(cmd=cmd), _env(), \
                    self.assertRaises(acquisition.ForkAcquisitionRefused) as c:
                acquisition.require("x", cmd)
            text = str(c.exception)
            self.assertIn("OFFLINE_BUILD", text)
            self.assertIn("OFFLINE_BUILD", c.exception.command)
            self.assertNotIn(cmd, text)
            self.assertNotIn(cmd, c.exception.command)

    def test_component_fetch_refused_before_any_network(self):
        """Components._fetch gates on acquisition.require before tls.install/urlopen."""
        with tempfile.TemporaryDirectory() as td:
            c = components.ComponentStore(Path(td))
            a = components.Artifact(name="x.bin", url="https://x.invalid/x", sha256="0" * 64, bytes=1)
            with _env(), mock.patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(acquisition.ForkAcquisitionRefused):
                    c._obtain(a, source=None, payloads=None)
            self.assertEqual(urlopen.call_count, 0)

    def test_serving_path_never_acquires(self):
        """Import-time + serve() of a mock engine under default deny: nothing acquires."""
        with _env(), mock.patch("urllib.request.urlopen") as urlopen:
            from serve.frontend import ChatTemplate
            from serve.server import ByteTokenizer, MockEngine, Service, serve
            svc = Service(MockEngine(ByteTokenizer(), "Hi.", max_context=1024), ByteTokenizer(),
                          ChatTemplate(Path(__file__).resolve().parent.parent / "serve/chat_template.jinja"))
            httpd = serve(svc, port=0)
            httpd.shutdown(); httpd.server_close()
        self.assertEqual(urlopen.call_count, 0)


REPO = Path(__file__).resolve().parent.parent


class RunServerWrapper(unittest.TestCase):
    """The production offline starter exports the deny guards before it spawns."""

    def _fixture(self, td: str) -> Path:
        root = Path(td) / "repo"
        (root / "tools/offline").mkdir(parents=True)
        (root / ".venv-offline/bin").mkdir(parents=True)
        (root / "serve").mkdir(parents=True)
        shutil.copy(REPO / "tools/offline/run_server.sh", root / "tools/offline/run_server.sh")
        py = root / ".venv-offline/bin/python"
        py.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "json.dump({k: os.environ.get(k) for k in "
            "('STRATA_NO_ACQUIRE','STRATA_FORK_ALLOW_ACQUIRE','STRATA_NO_HANDOVER')},"
            " open(sys.argv[1] + '.env.json', 'w'))\n")
        py.chmod(0o755)
        server = root / "serve/server.py"
        server.write_text("import sys\nopen(sys.argv[1] + '.ran','w').write('x')\n")
        return root

    def test_inherited_allow1_still_serves_no_acquire(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._fixture(td)
            env = {**os.environ, "STRATA_FORK_ALLOW_ACQUIRE": "1",
                   "STRATA_NO_ACQUIRE": "0", "STRATA_NO_HANDOVER": "0"}
            r = subprocess.run(
                ["bash", "tools/offline/run_server.sh", "--mock"],
                cwd=root, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            recorded = next((json.loads(p.read_text())
                             for p in root.rglob("*.env.json")), {})
            self.assertEqual(recorded.get("STRATA_NO_ACQUIRE"), "1")
            self.assertEqual(recorded.get("STRATA_NO_HANDOVER"), "1")
            self.assertEqual(recorded.get("STRATA_FORK_ALLOW_ACQUIRE"), "1")

    def test_missing_config_fails_before_spawn(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._fixture(td)
            r = subprocess.run(
                ["bash", "tools/offline/run_server.sh", "no-such.json"],
                cwd=root, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(list(root.rglob("*.env.json")),
                             "server must not spawn on missing config")


if __name__ == "__main__":
    unittest.main()
