"""Isolierte Tests fuer Deploy- und Server-Launcher ohne echte Dienste."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


OFFLINE = Path(__file__).resolve().parent / "offline"


class DeployLauncher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.offline = self.repo / "tools" / "offline"
        self.offline.mkdir(parents=True)
        for name in ("deploy_local.sh", "run_server.sh", "reapply_required_args.py"):
            shutil.copy2(OFFLINE / name, self.offline / name)
        generator = self.offline / "make_manifest.py"
        generator.write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "if '--print-head-sha' in sys.argv:\n"
            "    print('a' * 40); raise SystemExit(0)\n"
            "if '--verify' in sys.argv:\n"
            "    raise SystemExit(0)\n"
            "p = Path(sys.argv[sys.argv.index('--out') + 1])\n"
            "p.write_text(json.dumps({'fork_sha': 'a' * 40}))\n", encoding="utf-8")
        engine = self.repo / "terminal" / "engine"
        engine.mkdir(parents=True)
        (engine / "strata").write_bytes(b"test-engine")
        (engine / "strata").chmod(0o755)
        (engine / "BUILD.json").write_text('{"src":"test"}', encoding="utf-8")
        wheelhouse = self.repo / "wheelhouse"
        wheelhouse.mkdir()
        wheel = wheelhouse / "test.whl"
        wheel.write_bytes(b"test-wheel")
        wheel_hash = hashlib.sha256(b"test-wheel").hexdigest()
        (wheelhouse / "MANIFEST.sha256").write_text(f"{wheel_hash}  {wheel.name}\n", encoding="ascii")
        self.vpy = self.repo / ".venv-offline" / "bin" / "python"
        self.vpy.parent.mkdir(parents=True)
        self.probe = self.root / "venv-start"
        self.validator_marker = self.root / "venv-config-check"
        self.vpy.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = "-" ]; then printf test > "$VALIDATOR_OUTPUT"; printf "OK:\\n"; exit 0; fi\n'
            'printf "%s" "${PYTHONDONTWRITEBYTECODE:-unset}" > "$PROBE_OUTPUT"\n',
            encoding="utf-8")
        self.vpy.chmod(0o755)
        server = self.repo / "terminal" / "serve"
        server.mkdir(parents=True)
        (server / "server.py").write_text("", encoding="utf-8")
        self.config = self.root / "test.json"
        self.config.write_text(json.dumps({"exe": str(engine / "strata"), "cwd": str(engine), "args": []}),
                               encoding="utf-8")
        self.fake_dir = self.root / "fake-bin"
        self.fake_dir.mkdir()
        self.fake_marker = self.root / "fremdes-python"
        fake_python = self.fake_dir / "python3"
        fake_python.write_text(f"#!/bin/sh\nprintf test > {self.fake_marker!s}\nexit 23\n", encoding="utf-8")
        fake_python.chmod(0o755)
        self.env = {"PATH": str(self.fake_dir) + ":/usr/bin:/bin", "HOME": str(self.root),
                    "LC_ALL": "C", "PROBE_OUTPUT": str(self.probe), "VALIDATOR_OUTPUT": str(self.validator_marker),
                    "PYTHONDONTWRITEBYTECODE": "0"}
        self.deploy_root = self.root / "releases"

    def test_deploy_nutzt_keinen_python_aus_dem_path(self):
        result = subprocess.run(
            ["/bin/bash", str(self.offline / "deploy_local.sh"), str(self.config),
             "--deploy-root", str(self.deploy_root), "--no-unit"],
            env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.fake_marker.exists())
        self.assertFalse(self.probe.exists())
        target = (self.deploy_root / "current").resolve()
        self.assertTrue(target.is_dir())
        self.assertTrue((target / "MANIFEST.json").is_file())
        self.assertTrue((target / "run.sh").is_file())
        self.assertEqual(json.loads((target / self.config.name).read_text())["exe"], str(target / "strata"))
        self.assertFalse((self.deploy_root / ".strata-deploy.lock").exists())

    def test_deploy_verweigert_gleichzeitigen_wechsel(self):
        self.deploy_root.mkdir()
        lock = self.deploy_root / ".strata-deploy.lock"
        lock.mkdir()
        result = subprocess.run(
            ["/bin/bash", str(self.offline / "deploy_local.sh"), str(self.config),
             "--deploy-root", str(self.deploy_root), "--no-unit"],
            env=self.env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(lock.is_dir())
        self.assertFalse((self.deploy_root / "current").exists())

    def test_kollision_nach_vorabpruefung_belaesst_fremdes_staging(self):
        script = self.offline / "deploy_local.sh"
        source = script.read_text(encoding="utf-8")
        source = source.replace("/usr/bin/date -u +%Y%m%dT%H%M%SZ", "/usr/bin/printf 20261111T000000Z")
        marker = 'info "staging $DEST"'
        self.assertIn(marker, source)
        source = source.replace(marker, '/usr/bin/mkdir -p "$DEST"\nprintf fremd > "$DEST/sentinel"\n' + marker)
        script.write_text(source, encoding="utf-8")
        result = subprocess.run(
            ["/bin/bash", str(script), str(self.config), "--deploy-root", str(self.deploy_root), "--no-unit"],
            env=self.env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.deploy_root / "aaaaaaaa-20261111T000000Z" / "sentinel").read_text(), "fremd")
        self.assertFalse((self.deploy_root / "current").exists())
        self.assertFalse((self.deploy_root / ".strata-deploy.lock").exists())   # auch im Fehlerpfad freigegeben

    def test_stage_only_laesst_aktive_pfade_unveraendert(self):
        self.deploy_root.mkdir()
        old = self.deploy_root / "old"
        older = self.deploy_root / "older"
        old.mkdir()
        older.mkdir()
        (self.deploy_root / "current").symlink_to(old)
        (self.deploy_root / "previous").symlink_to(older)
        result = subprocess.run(
            ["/bin/bash", str(self.offline / "deploy_local.sh"), str(self.config),
             "--deploy-root", str(self.deploy_root), "--stage-only"],
            env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.deploy_root / "current").resolve(), old)
        self.assertEqual((self.deploy_root / "previous").resolve(), older)
        self.assertFalse((self.root / ".config" / "systemd" / "user").exists())
        self.assertFalse((self.deploy_root / ".strata-deploy.lock").exists())
        sealed = [p for p in self.deploy_root.iterdir()
                  if p.is_dir() and p.name.startswith("aaaaaaaa-")]
        self.assertEqual(len(sealed), 1)
        self.assertTrue((sealed[0] / "MANIFEST.json").is_file())

    def test_server_verbietet_bytecode_schreiben_im_laufzeit_venv(self):
        result = subprocess.run(["/bin/bash", str(self.offline / "run_server.sh"), "--mock"],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.probe.read_text(), "1")
        self.assertFalse(self.fake_marker.exists())

    def test_server_prueft_config_ohne_venv_python(self):
        result = subprocess.run(["/bin/bash", str(self.offline / "run_server.sh"), str(self.config)],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.validator_marker.exists())
        self.assertEqual(self.probe.read_text(), "1")


if __name__ == "__main__":
    unittest.main()
