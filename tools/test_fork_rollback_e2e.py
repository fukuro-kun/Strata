"""Netzlose Rollback-Tests mit isoliertem Git-Repository und Test-Deploys."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


OFFLINE = Path(__file__).resolve().parent / "offline"
SPEC = importlib.util.spec_from_file_location("rollback_manifest_tested", OFFLINE / "make_manifest.py")
manifest_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_tool)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RollbackE2E(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.root), "LC_ALL": "C",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
        self.git("init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(
            ".venv-offline/\nwheelhouse/*.whl\n", encoding="utf-8")
        (self.repo / ".gitattributes").write_text("filter-file filter=probe\n", encoding="ascii")
        (self.repo / "filter-file").write_text("original\n", encoding="ascii")
        self.offline = self.repo / "tools" / "offline"
        self.offline.mkdir(parents=True)
        for name in ("make_manifest.py", "rollback.sh"):
            shutil.copy2(OFFLINE / name, self.offline / name)
        pin_dir = self.repo / "engine" / "third_party" / "strata-ggml"
        pin_dir.mkdir(parents=True)
        self.pin = "a" * 40
        (pin_dir / "UPSTREAM.md").write_text(f"pin: {self.pin}\n", encoding="ascii")
        terminal = self.repo / "terminal"
        terminal.mkdir()
        (terminal / "setup.py").write_text(f'LLAMA_CPP_COMMIT = "{self.pin}"\n', encoding="ascii")
        wh = self.repo / "wheelhouse"
        wh.mkdir()
        wheel = wh / "example-1.0-py3-none-any.whl"
        wheel.write_bytes(b"wheel")
        wheel_hash = digest(b"wheel")
        (wh / "MANIFEST.sha256").write_text(f"{wheel_hash}  {wheel.name}\n", encoding="ascii")
        self.git("add", ".gitignore", ".gitattributes", "filter-file", "terminal",
                 "engine/third_party", "tools", "wheelhouse/MANIFEST.sha256")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "Testbasis")
        head = self.git("rev-parse", "HEAD").decode().strip()
        self.venv = self.repo / ".venv-offline"
        python = self.venv / "bin" / "python"
        python.parent.mkdir(parents=True)
        self.marker = self.root / "code-ausgefuehrt"
        python.write_text(f"#!/bin/sh\nprintf test > {self.marker!s}\nexit 99\n", encoding="utf-8")
        python.chmod(0o755)
        (self.venv / "pyvenv.cfg").write_text(
            "home = /usr/bin\ninclude-system-site-packages = false\nversion = 3.14.4\n", encoding="utf-8")
        self.site = self.venv / "lib" / "python3.14" / "site-packages"
        dist = self.site / "pip-25.1.1.dist-info"
        dist.mkdir(parents=True)
        (dist / "METADATA").write_text("Metadata-Version: 2.3\nName: pip\nVersion: 25.1.1\n", encoding="utf-8")
        (self.site / "probe.pth").write_text(
            f"import pathlib; pathlib.Path({str(self.marker)!r}).touch()\n", encoding="utf-8")
        (self.site / "test.py").write_text("wert = 1\n", encoding="utf-8")
        self.releases = self.root / "releases"
        self.releases.mkdir()
        self.old, self.new = self.releases / "old", self.releases / "new"
        self.old.mkdir()
        self.new.mkdir()
        (self.old / "strata").write_bytes(b"engine")
        (self.old / "strata").chmod(0o755)
        build = {"src": "test"}
        (self.old / "BUILD.json").write_text(json.dumps(build), encoding="utf-8")
        self.manifest = {
            "schema": 2, "fork_sha": head,
            "baseline_sha": head, "fork_files": [], "fork_commits": [],
            "llama_cpp": {"commit": self.pin, "pin_file": self.pin, "pin_ok": True},
            "deps": {wheel.name: wheel_hash},
            "venv": {"path": str(self.venv), **manifest_tool.venv_snapshot(python)},
            "artifacts": {"strata": {"sha256": digest(b"engine"), "size": len(b"engine")}},
            "build": build, "models": {},
        }
        self.write_manifest()
        (self.releases / "current").symlink_to(self.new)
        (self.releases / "previous").symlink_to(self.old)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env, check=True,
                              capture_output=True).stdout

    def write_manifest(self):
        (self.old / "MANIFEST.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def rollback(self, *args):
        return subprocess.run(["/bin/bash", str(self.offline / "rollback.sh"), "--deploy-root", str(self.releases),
                               "--no-restart", *args], env=self.env, capture_output=True, text=True, timeout=30)

    def unchanged(self, expect_lock=False):
        self.assertEqual((self.releases / "current").resolve(), self.new)
        self.assertEqual((self.releases / "previous").resolve(), self.old)
        self.assertFalse(self.marker.exists())
        # Fehlerpfade geben das eigene Lock frei; ein fremd gepflanztes bleibt stehen
        self.assertEqual((self.releases / ".strata-deploy.lock").exists(), expect_lock)

    def test_konsistentes_ziel_ohne_venv_code_umschaltbar(self):
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.releases / "current").resolve(), self.old)
        self.assertEqual((self.releases / "previous").resolve(), self.new)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.releases / ".strata-deploy.lock").exists())

    def test_rollback_verweigert_gleichzeitigen_wechsel(self):
        lock = self.releases / ".strata-deploy.lock"
        lock.mkdir()
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.unchanged(expect_lock=True)
        self.assertTrue(lock.is_dir())

    def test_unvollstaendiges_manifest_laest_symlinks_unveraendert(self):
        self.manifest = {"fork_sha": self.manifest["fork_sha"]}
        self.write_manifest()
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def test_venv_drift_laest_symlinks_unveraendert(self):
        (self.site / "test.py").write_text("wert = 2\n", encoding="utf-8")
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def test_git_aus_manipuliertem_path_wird_nicht_ausgefuehrt(self):
        fake_dir = self.root / "fake-bin"
        fake_dir.mkdir()
        fake_git = fake_dir / "git"
        fake_git.write_text(f"#!/bin/sh\nprintf test > {self.marker!s}\nexit 99\n", encoding="utf-8")
        fake_git.chmod(0o755)
        self.env["PATH"] = str(fake_dir) + ":/usr/bin:/bin"
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.marker.exists())

    def test_git_fsmonitor_hook_wird_nicht_ausgefuehrt(self):
        hook = self.root / "fsmonitor-hook"
        hook.write_text(f"#!/bin/sh\nprintf test > {self.marker!s}\nexit 0\n", encoding="utf-8")
        hook.chmod(0o755)
        self.git("config", "core.fsmonitor", str(hook))
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.marker.exists())

    def test_git_clean_filter_wird_nicht_ausgefuehrt(self):
        hook = self.root / "clean-filter"
        hook.write_text(f"#!/bin/sh\nprintf test > {self.marker!s}\n/bin/cat\n", encoding="utf-8")
        hook.chmod(0o755)
        self.git("config", "filter.probe.clean", str(hook))
        (self.repo / "filter-file").write_text("ersatz12\n", encoding="ascii")
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def test_nicht_ausfuehrbare_engine_laest_symlinks_unveraendert(self):
        (self.old / "strata").chmod(0o644)
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def test_explizites_ziel_ausserhalb_des_deploy_roots_wird_verweigert(self):
        outside = self.root / "fremdes-deploy"
        shutil.copytree(self.old, outside)
        result = self.rollback("../fremdes-deploy")
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def add_deploy_section(self):
        config = self.old / "strata-test.fork.json"
        config.write_text('{"exe":"strata"}', encoding="utf-8")
        run_sh = self.old / "run.sh"
        run_sh.write_text("#!/bin/sh\nexec test\n", encoding="utf-8")
        self.manifest["deploy"] = {"config": {"name": config.name,
                                              "sha256": digest(config.read_bytes())},
                                   "run_sh": digest(run_sh.read_bytes()),
                                   "model_inputs": {}}
        self.write_manifest()

    def test_attestierte_laufdateien_umschaltbar(self):
        self.add_deploy_section()
        result = self.rollback()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.releases / "current").resolve(), self.old)

    def test_laufdateien_ohne_deploy_nachweis_werden_verweigert(self):
        (self.old / "run.sh").write_text("#!/bin/sh\nexec fremd\n", encoding="utf-8")
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def test_manipuliertes_run_sh_wird_verweigert(self):
        self.add_deploy_section()
        (self.old / "run.sh").write_text("#!/bin/sh\nexec fremd\n", encoding="utf-8")
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.unchanged()

    def test_previous_symlink_ausserhalb_des_deploy_roots_wird_verweigert(self):
        outside = self.root / "fremdes-deploy"
        shutil.copytree(self.old, outside)
        previous = self.releases / "previous"
        previous.unlink()
        previous.symlink_to(outside)
        result = self.rollback()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.releases / "current").resolve(), self.new)
        self.assertEqual(previous.resolve(), outside)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
