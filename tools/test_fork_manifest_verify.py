"""Regressionstests fuer die fail-closed-Pruefung von Deployment-Manifesten."""

import copy
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SOURCE = Path(__file__).resolve().parent / "offline" / "make_manifest.py"
SPEC = importlib.util.spec_from_file_location("make_manifest_tested", SOURCE)
manifest_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_tool)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ManifestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo, self.deploy = self.root / "repo", self.root / "deploy"
        self.repo.mkdir()
        self.deploy.mkdir()
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.root), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
        self.git("init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(
            ".venv-offline/\nterminal/engine/\nwheelhouse/*.whl\n", encoding="utf-8")
        pin_dir = self.repo / "engine" / "third_party" / "strata-ggml"
        pin_dir.mkdir(parents=True)
        self.pin = "a" * 40
        (pin_dir / "UPSTREAM.md").write_text(f"pin: {self.pin}\n", encoding="ascii")
        terminal = self.repo / "terminal"
        terminal.mkdir()
        (terminal / "setup.py").write_text(
            f'LLAMA_CPP_COMMIT = "{self.pin}"\n'
            'CUDA_WHEELS = ["nvidia-cublas==13.0.2.14"]\n'
            'CUDA12_WHEELS = ["nvidia-cublas-cu12==12.9.1.4"]\n', encoding="ascii")
        (terminal / "requirements.txt").write_text(
            "pillow==13.0.0; python_version >= \"3.11\"\n"
            "colorama==0.4.6; sys_platform == \"win32\"\n", encoding="ascii")
        (terminal / "requirements-build.txt").write_text("# keine Test-Build-Helfer\n", encoding="ascii")
        self.wheelhouse = self.repo / "wheelhouse"
        self.wheelhouse.mkdir()
        self.wheel = self.wheelhouse / "example-1.0-py3-none-any.whl"
        self.wheel.write_bytes(b"geprueftes-wheel")
        self.wheel_hash = digest(self.wheel.read_bytes())
        self.extra_wheel = self.wheelhouse / "zusatz-1.0-py3-none-any.whl"
        self.extra_wheel.write_bytes(b"zweites-wheel")
        self.extra_hash = digest(self.extra_wheel.read_bytes())
        (self.wheelhouse / "MANIFEST.sha256").write_text(
            f"{self.wheel_hash}  {self.wheel.name}\n{self.extra_hash}  {self.extra_wheel.name}\n", encoding="ascii")
        self.git("add", ".gitignore", "terminal", "engine/third_party",
                 "wheelhouse/MANIFEST.sha256")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "Testbasis")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        self.venv = self.repo / ".venv-offline"
        self.vpy = self.venv / "bin" / "python"
        self.vpy.parent.mkdir(parents=True)
        self.vpy.write_bytes(b"python-binary")
        self.vpy.chmod(0o755)
        (self.venv / "pyvenv.cfg").write_text(
            "home = /usr/bin\ninclude-system-site-packages = false\nversion = 3.14.4\n", encoding="utf-8")
        self.site = self.venv / "lib" / "python3.14" / "site-packages"
        self.site.mkdir(parents=True)
        for name, version in (("Pillow", "13.0.0"), ("pip", "25.1.1")):
            dist = self.site / f"{name}-{version}.dist-info"
            dist.mkdir()
            (dist / "METADATA").write_text(
                f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n", encoding="utf-8")
        (self.site / "beispiel.py").write_text("wert = 1\n", encoding="utf-8")
        (self.deploy / "strata").write_bytes(b"lokale-engine")
        (self.deploy / "strata").chmod(0o755)
        self.build = {"src": "test", "cuda_dirs": []}
        (self.deploy / "BUILD.json").write_text(json.dumps(self.build), encoding="utf-8")
        self.data = {
            "schema": 2,
            "fork_sha": self.head,
            "baseline_sha": self.head,
            "fork_files": [],
            "fork_commits": [],
            "llama_cpp": {"commit": self.pin, "pin_file": self.pin, "pin_ok": True},
            "deps": {self.wheel.name: self.wheel_hash, self.extra_wheel.name: self.extra_hash},
            "venv": {"path": str(self.venv), **manifest_tool.venv_snapshot(self.vpy)},
            "artifacts": {"strata": {"sha256": digest(b"lokale-engine"), "size": len(b"lokale-engine")}},
            "build": self.build,
            "models": {},
        }

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env, check=True,
                              capture_output=True).stdout

    def verify(self, data=None):
        path = self.deploy / "MANIFEST.json"
        path.write_text(json.dumps(self.data if data is None else data), encoding="utf-8")
        output = io.StringIO()
        with mock.patch.object(manifest_tool, "ROOT", self.repo), redirect_stdout(output):
            result = manifest_tool.verify(path)
        return result, output.getvalue()

    def generate(self):
        engine = self.repo / "terminal" / "engine"
        engine.mkdir(parents=True)
        (engine / "strata").write_bytes(b"lokale-engine")
        (engine / "strata").chmod(0o755)
        (engine / "BUILD.json").write_text(json.dumps(self.build), encoding="utf-8")
        args = ["make_manifest.py", "--baseline", self.head, "--out", str(engine / "MANIFEST.json")]
        with mock.patch.object(manifest_tool, "ROOT", self.repo), mock.patch.object(sys, "argv", args), \
             redirect_stdout(io.StringIO()):
            return manifest_tool.main()

    def test_vollstaendiges_konsistentes_manifest_besteht(self):
        result, output = self.verify()
        self.assertEqual(result, 0, output)

    def test_erzeugtes_manifest_besteht_die_eigene_pruefung(self):
        self.assertEqual(self.generate(), 0)
        output = io.StringIO()
        with mock.patch.object(manifest_tool, "ROOT", self.repo), redirect_stdout(output):
            result = manifest_tool.verify(self.repo / "terminal" / "engine" / "MANIFEST.json")
        self.assertEqual(result, 0, output.getvalue())

    def test_manifest_erstellung_verweigert_manipuliertes_wheel(self):
        self.wheel.write_bytes(b"manipuliertes-wheel")
        with self.assertRaises(SystemExit):
            self.generate()

    def test_manifest_erstellung_verweigert_unbekanntes_wheel(self):
        (self.wheelhouse / "unbekannt-1.0-py3-none-any.whl").write_bytes(b"unbekannt")
        with self.assertRaises(SystemExit):
            self.generate()

    def test_manifest_erstellung_verweigert_fehlende_venv(self):
        self.venv.rename(self.root / "gesicherte-venv")
        with self.assertRaises(SystemExit):
            self.generate()

    def staged_deploy(self):
        target = self.root / "staged"
        target.mkdir()
        (target / "strata").write_bytes(b"lokale-engine")
        (target / "strata").chmod(0o755)
        (target / "BUILD.json").write_text(json.dumps(self.build), encoding="utf-8")
        (target / "strata-test.fork.json").write_text('{"exe":"strata"}', encoding="utf-8")
        (target / "run.sh").write_text("#!/bin/sh\nexec test\n", encoding="utf-8")
        return target

    def seal(self, target):
        args = ["make_manifest.py", "--baseline", self.head, "--deploy-dir", str(target),
                "--config", "strata-test.fork.json", "--out", str(target / "MANIFEST.json")]
        with mock.patch.object(manifest_tool, "ROOT", self.repo), mock.patch.object(sys, "argv", args), \
             redirect_stdout(io.StringIO()):
            return manifest_tool.main()

    def test_versiegeltes_deploy_verzeichnis_wird_attestiert(self):
        target = self.staged_deploy()
        self.assertEqual(self.seal(target), 0)
        sealed = json.loads((target / "MANIFEST.json").read_text(encoding="utf-8"))
        deploy = sealed["deploy"]
        self.assertEqual(deploy["config"]["name"], "strata-test.fork.json")
        self.assertEqual(deploy["config"]["sha256"], digest(b'{"exe":"strata"}'))
        self.assertEqual(deploy["run_sh"], digest(b"#!/bin/sh\nexec test\n"))
        output = io.StringIO()
        with mock.patch.object(manifest_tool, "ROOT", self.repo), redirect_stdout(output):
            self.assertEqual(manifest_tool.verify(target / "MANIFEST.json"), 0, output.getvalue())

    def test_versiegelung_verweigert_fremde_datei_im_deploy(self):
        target = self.staged_deploy()
        (target / "fremd.sh").write_text("x", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.seal(target)

    def test_versiegelung_verweigert_backup_symlink(self):
        target = self.staged_deploy()
        os.symlink("/etc/passwd", target / "x.bak-20261111-120000")
        with self.assertRaises(SystemExit):
            self.seal(target)

    def test_versiegelung_akzeptiert_echte_backups(self):
        target = self.staged_deploy()
        (target / "strata-test.fork.json.bak-20261111-120000").write_text("{}", encoding="utf-8")
        (target / "strata-test.fork.json.bak-20261111-120000-2").write_text("{}", encoding="utf-8")
        self.assertEqual(self.seal(target), 0)

    def test_versiegelung_verlangt_json_config(self):
        target = self.staged_deploy()
        args = ["make_manifest.py", "--baseline", self.head, "--deploy-dir", str(target),
                "--config", "keine-json", "--out", str(target / "MANIFEST.json")]
        with mock.patch.object(manifest_tool, "ROOT", self.repo), mock.patch.object(sys, "argv", args), \
             redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            manifest_tool.main()

    def test_versiegelte_modell_shards_werden_gebunden(self):
        target = self.staged_deploy()
        first = self.root / "model-00001-of-00002.gguf"
        second = self.root / "model-00002-of-00002.gguf"
        vec1 = self.root / "v1.gguf"
        vec2 = self.root / "v2.gguf"
        first.write_bytes(b"one")
        vec1.write_bytes(b"v1")
        vec2.write_bytes(b"v2")
        (target / "strata-test.fork.json").write_text(
            json.dumps({"args": ["--native", str(first), "--mtp", "4"],
                        "user_args": ["--control-vector-scaled", f"{vec1}:0.5,{vec2}:1.0",
                                      "--draft-costs", str(self.root / "not-created.json")]}),
            encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, 'unable to seal'):
            self.seal(target)
        second.write_bytes(b"two")
        self.assertEqual(self.seal(target), 0)
        path = target / "MANIFEST.json"
        inputs = json.loads(path.read_text())["deploy"]["model_inputs"]
        self.assertEqual(inputs[str(second)]["sha256"], digest(b"two"))
        self.assertEqual(inputs[str(vec1)]["sha256"], digest(b"v1"))
        self.assertEqual(inputs[str(vec2)]["sha256"], digest(b"v2"))
        self.assertNotIn(str(self.root / "not-created.json"), inputs)
        second.write_bytes(b"bad")
        output = io.StringIO()
        with mock.patch.object(manifest_tool, "ROOT", self.repo), redirect_stdout(output):
            self.assertEqual(manifest_tool.verify(path), 1)
        self.assertIn("model inputs drifted", output.getvalue())

    def test_split_fallback_wird_abgelehnt(self):
        target = self.staged_deploy()
        (target / "strata-test.fork.json").write_text(
            json.dumps({"exe": "strata", "split_fallback": {"mode": "row"}}), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, 'split_fallback is not supported'):
            self.seal(target)

    def test_bildgenerierung_wird_abgelehnt(self):
        target = self.staged_deploy()
        (target / "strata-test.fork.json").write_text(
            json.dumps({"exe": "strata", "images": {"exe": "/unreviewed"}}), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, 'image generation is not supported'):
            self.seal(target)

    def add_deploy_section(self):
        config = self.deploy / "strata-test.fork.json"
        config.write_text('{"exe":"strata"}', encoding="utf-8")
        run_sh = self.deploy / "run.sh"
        run_sh.write_text("#!/bin/sh\nexec test\n", encoding="utf-8")
        self.data["deploy"] = {"config": {"name": config.name,
                                          "sha256": digest(config.read_bytes())},
                               "run_sh": digest(run_sh.read_bytes()),
                               "model_inputs": {}}

    def test_attestierte_laufdateien_bestehen(self):
        self.add_deploy_section()
        (self.deploy / "strata-test.fork.json.bak-20261111-120000").write_text("{}", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 0, output)

    def test_geaendertes_run_sh_wird_abgelehnt(self):
        self.add_deploy_section()
        (self.deploy / "run.sh").write_text("#!/bin/sh\nexec fremd\n", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_geaenderte_deploy_config_wird_abgelehnt(self):
        self.add_deploy_section()
        (self.deploy / "strata-test.fork.json").write_text('{"exe":"/fremd"}', encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_unverzeichnete_config_wird_abgelehnt(self):
        self.add_deploy_section()
        (self.deploy / "strata-boese.json").write_text("{}", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_fremde_datei_im_deploy_wird_abgelehnt(self):
        self.add_deploy_section()
        (self.deploy / "fremd.sh").write_text("x", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_laufdateien_ohne_deploy_nachweis_werden_abgelehnt(self):
        (self.deploy / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_fremde_deploy_sektion_wird_abgelehnt(self):
        data = copy.deepcopy(self.data)
        data["deploy"] = {"config": {"name": "x.json", "sha256": "a" * 64},
                          "run_sh": "b" * 64, "extra": True}
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_fork_sha_abweichung_wird_abgelehnt(self):
        data = copy.deepcopy(self.data)
        data["fork_sha"] = "b" * 40
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_unsauberer_arbeitsbaum_wird_abgelehnt(self):
        (self.repo / "uncommitted.py").write_text("x = 1\n", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_git_grafts_werden_abgelehnt(self):
        info = self.repo / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "grafts").write_text("b" * 40 + "\n", encoding="ascii")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_manifest_nur_mit_checkout_sha_wird_abgelehnt(self):
        result, output = self.verify({"fork_sha": self.head})
        self.assertEqual(result, 1, output)

    def test_altes_schema_wird_nicht_als_neuer_nachweis_akzeptiert(self):
        data = copy.deepcopy(self.data)
        data["schema"] = 1
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_ignorierter_pin_muss_zum_committeten_setup_passen(self):
        false_pin = "b" * 40
        (self.repo / "engine" / "third_party" / "strata-ggml" / "UPSTREAM.md").write_text(
            f"pin: {false_pin}\n", encoding="ascii")
        data = copy.deepcopy(self.data)
        data["llama_cpp"] = {"commit": false_pin, "pin_file": false_pin, "pin_ok": True}
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_falsche_fork_provenienz_wird_abgelehnt(self):
        for field, value in (("baseline_sha", "0" * 40),
                             ("fork_files", ["nie-committiert.py"]),
                             ("fork_commits", ["b" * 40])):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data[field] = value
                result, output = self.verify(data)
                self.assertEqual(result, 1, output)

    def test_fehlende_pflichtbereiche_werden_abgelehnt(self):
        for field in ("schema", "artifacts", "llama_cpp", "deps", "venv", "build"):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                del data[field]
                result, output = self.verify(data)
                self.assertEqual(result, 1, output)

    def test_leere_artefakte_und_unvollstaendige_venv_werden_abgelehnt(self):
        for field, value in (("artifacts", {}), ("venv", {"path": str(self.vpy.parent.parent)})):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data[field] = value
                result, output = self.verify(data)
                self.assertEqual(result, 1, output)

    def test_manipulierte_engine_wird_abgelehnt(self):
        (self.deploy / "strata").write_bytes(b"geaendert")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_nicht_ausfuehrbare_engine_wird_abgelehnt(self):
        (self.deploy / "strata").chmod(0o644)
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_symlink_als_engine_wird_abgelehnt(self):
        outside = self.root / "andere-engine"
        outside.write_bytes(b"lokale-engine")
        (self.deploy / "strata").unlink()
        (self.deploy / "strata").symlink_to(outside)
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_symlink_ersatz_zwischen_stat_und_hash_wird_abgelehnt(self):
        artifact = self.deploy / "strata"
        outside = self.root / "andere-engine"
        outside.write_bytes(b"lokale-engine")
        real_open, real_os_open = open, os.open
        replaced = False

        def swap(path):
            nonlocal replaced
            if not replaced and path == artifact:
                artifact.rename(self.root / "gesicherte-engine")
                artifact.symlink_to(outside)
                replaced = True

        def file_open(path, *args, **kwargs):
            swap(path)
            return real_open(path, *args, **kwargs)

        def fd_open(path, flags, mode=0o777, **kwargs):
            swap(path)
            return real_os_open(path, flags, mode, **kwargs)

        with mock.patch("builtins.open", side_effect=file_open), \
             mock.patch.object(manifest_tool.os, "open", side_effect=fd_open):
            result, output = self.verify()
        self.assertTrue(replaced)
        self.assertEqual(result, 1, output)

    def test_artefaktpfad_ausserhalb_des_deploys_wird_abgelehnt(self):
        outside = self.root / "ausserhalb"
        outside.write_bytes(b"ausserhalb")
        data = copy.deepcopy(self.data)
        data["artifacts"]["../ausserhalb"] = {"sha256": digest(b"ausserhalb"), "size": len(b"ausserhalb")}
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_nicht_aufgefuehrtes_vision_artefakt_wird_abgelehnt(self):
        (self.deploy / "strata-vision").write_bytes(b"nicht verzeichnet")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_venv_snapshot_fuehrt_keinen_prozess_aus(self):
        with mock.patch.object(manifest_tool.subprocess, "run", side_effect=AssertionError("Prozess gestartet")):
            snapshot = manifest_tool.venv_snapshot(self.vpy)
        self.assertEqual(snapshot["python"], "3.14.4")
        self.assertEqual(snapshot["pip_freeze_count"], 2)

    def test_manifest_erstellung_startet_keinen_venv_ninja(self):
        marker = self.root / "fremdes-ninja"
        ninja = self.vpy.parent / "ninja"
        ninja.write_text(f"#!/bin/sh\nprintf test > {marker!s}\nexit 0\n", encoding="utf-8")
        ninja.chmod(0o755)
        self.assertEqual(self.generate(), 0)
        self.assertFalse(marker.exists())

    def test_manifest_erstellung_startet_keinen_nvcc_aus_path(self):
        marker = self.root / "fremdes-nvcc"
        bindir = self.root / "fake-bin"
        bindir.mkdir()
        nvcc = bindir / "nvcc"
        nvcc.write_text(f"#!/bin/sh\nprintf test > {marker!s}\nexit 0\n", encoding="utf-8")
        nvcc.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(bindir) + ":/usr/bin:/bin"}):
            self.assertEqual(self.generate(), 0)
        self.assertFalse(marker.exists())

    def test_fehlende_paketmetadaten_werden_abgelehnt(self):
        (self.site / "Pillow-13.0.0.dist-info" / "METADATA").unlink()
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_paket_mit_direct_url_wird_abgelehnt(self):
        direct = self.site / "Pillow-13.0.0.dist-info" / "direct_url.json"
        direct.write_text('{"url":"https://invalid.example"}', encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_fifo_in_venv_wird_ohne_oeffnen_abgelehnt(self):
        os.mkfifo(self.site / "fifo")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_code_in_pth_wird_bei_der_pruefung_nicht_ausgefuehrt(self):
        marker = self.root / "ausgefuehrt"
        (self.site / "probe.pth").write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).touch()\n", encoding="utf-8")
        self.data["venv"].update(manifest_tool.venv_snapshot(self.vpy))
        result, output = self.verify()
        self.assertEqual(result, 0, output)
        self.assertFalse(marker.exists())

    def test_geaenderte_venv_datei_wird_abgelehnt(self):
        (self.site / "beispiel.py").write_text("wert = 2\n", encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_geaenderter_python_binary_wird_abgelehnt(self):
        self.vpy.write_bytes(b"manipuliertes-python")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_venv_link_nach_aussen_wird_abgelehnt(self):
        outside = self.root / "andere-datei"
        outside.write_bytes(b"keine-venv-datei")
        (self.site / "ausserhalb.py").symlink_to(outside)
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_interpreter_alias_im_venv_bin_ist_zulaessig(self):
        external = Path("/usr/bin/python3").resolve()
        self.vpy.unlink()
        self.vpy.symlink_to(external)
        (self.vpy.parent / "python-alias").symlink_to("python")
        self.data["venv"].update(manifest_tool.venv_snapshot(self.vpy))
        result, output = self.verify()
        self.assertEqual(result, 0, output)

    def test_venv_interpreter_aus_beliebigem_pfad_wird_abgelehnt(self):
        outside = self.root / "unbekannte-datei"
        outside.write_bytes(b"nicht-geprueft")
        self.vpy.unlink()
        self.vpy.symlink_to(outside)
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_site_packages_aus_beliebigem_pfad_werden_abgelehnt(self):
        outside = self.root / "fremde-site"
        (self.venv / "lib").rename(outside)
        (self.venv / "lib").symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            manifest_tool.venv_snapshot(self.vpy)
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_verzeichnis_ersatz_durch_externen_symlink_wird_abgelehnt(self):
        victim = self.venv / "wechselnd"
        victim.mkdir()
        (victim / "datei").write_bytes(b"original")
        outside = self.root / "fremd"
        outside.mkdir()
        (outside / "datei").write_bytes(b"fremde-daten")
        real_scan, real_open = os.scandir, os.open
        replaced = False

        def swap(path):
            nonlocal replaced
            if not replaced and (str(path) == str(victim) or path == "wechselnd"):
                victim.rename(self.root / "gesichert")
                victim.symlink_to(outside, target_is_directory=True)
                replaced = True

        def scan(path):
            swap(path)
            return real_scan(path)

        def open_fd(path, flags, mode=0o777, **kwargs):
            swap(path)
            return real_open(path, flags, mode, **kwargs)

        with mock.patch.object(manifest_tool.os, "scandir", side_effect=scan), \
             mock.patch.object(manifest_tool.os, "open", side_effect=open_fd):
            with self.assertRaises((OSError, ValueError)):
                manifest_tool.venv_snapshot(self.vpy)
        self.assertTrue(replaced)

    def test_site_verzeichnis_wechsel_wird_vor_fremdem_lesen_abgelehnt(self):
        lib = self.venv / "lib"
        outside = self.root / "fremde-lib"
        real_iterdir, real_open = Path.iterdir, os.open
        real_distribution = importlib.metadata.PathDistribution
        replaced = False

        def swap():
            nonlocal replaced
            if not replaced:
                lib.rename(outside)
                lib.symlink_to(outside, target_is_directory=True)
                replaced = True

        def iterdir(path):
            if path == self.site:
                swap()
            return real_iterdir(path)

        def open_fd(path, flags, mode=0o777, **kwargs):
            if path == "lib":
                swap()
            return real_open(path, flags, mode, **kwargs)

        def distribution(path):
            if path.resolve().is_relative_to(outside):
                raise AssertionError("Fremde Paketmetadaten gelesen")
            return real_distribution(path)

        with mock.patch.object(Path, "iterdir", iterdir), \
             mock.patch.object(manifest_tool.os, "open", side_effect=open_fd), \
             mock.patch.object(importlib.metadata, "PathDistribution", side_effect=distribution):
            with self.assertRaises((OSError, ValueError)):
                manifest_tool.venv_snapshot(self.vpy)
        self.assertTrue(replaced)

    def test_altes_manifest_ohne_venv_dateihashes_wird_abgelehnt(self):
        for field in ("python_executable_sha256", "tree_sha256"):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                del data["venv"][field]
                result, output = self.verify(data)
                self.assertEqual(result, 1, output)

    def test_geaenderte_python_version_wird_abgelehnt(self):
        cfg = self.venv / "pyvenv.cfg"
        cfg.write_text(cfg.read_text().replace("3.14.4", "3.14.5"), encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_geaenderte_paketliste_wird_abgelehnt(self):
        meta = self.site / "Pillow-13.0.0.dist-info" / "METADATA"
        meta.write_text(meta.read_text().replace("13.0.0", "12.3.0"), encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_manipuliertes_wheel_wird_abgelehnt(self):
        self.wheel.write_bytes(b"manipuliertes-wheel")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_unvollstaendige_abhaengigkeitsliste_wird_abgelehnt(self):
        data = copy.deepcopy(self.data)
        del data["deps"][self.extra_wheel.name]
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_fehlendes_wheel_wird_abgelehnt(self):
        self.wheel.unlink()
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def test_manipulierte_build_metadaten_werden_abgelehnt(self):
        (self.deploy / "BUILD.json").write_text('{"src": "veraendert"}', encoding="utf-8")
        result, output = self.verify()
        self.assertEqual(result, 1, output)

    def env_of(self):
        self.assertEqual(self.generate(), 0)
        return json.loads((self.repo / "terminal" / "engine" / "MANIFEST.json").read_text(encoding="utf-8"))["env"]

    def test_env_provenienz_wird_beim_seal_attestiert(self):
        env = self.env_of()
        self.assertEqual(env["cuda_wheels"], "none")
        self.assertRegex(env["declared_pins_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(set(env["requirements_sha256"]),
                         {"requirements.txt", "requirements-build.txt"})

    def test_env_provenienz_besteht_die_pruefung(self):
        self.assertEqual(self.generate(), 0)
        data = json.loads((self.repo / "terminal" / "engine" / "MANIFEST.json").read_text(encoding="utf-8"))
        result, output = self.verify(data)
        self.assertEqual(result, 0, output)

    def test_manifest_ohne_env_besteht_weiter(self):
        result, output = self.verify()
        self.assertEqual(result, 0, output)
        self.assertIn("provenance not attested", output)

    def test_fremdpaket_in_venv_blockiert_die_attestierung(self):
        dist = self.site / "fremdpaket-9.9.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.3\nName: fremdpaket\nVersion: 9.9\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.generate()

    def test_abweichende_paketversion_blockiert_die_attestierung(self):
        dist = self.site / "Pillow-13.0.0.dist-info"
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.3\nName: Pillow\nVersion: 12.3.0\n", encoding="utf-8")
        dist.rename(self.site / "Pillow-12.3.0.dist-info")
        with self.assertRaises(SystemExit):
            self.generate()

    def test_verschobener_pin_blockiert_die_attestierung(self):
        (self.repo / "terminal" / "requirements.txt").write_text("pillow==12.3.0\n", encoding="utf-8")
        self.git("add", "terminal")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "Pin-Wechsel")
        with self.assertRaises(SystemExit):
            self.generate()

    def test_manipulierte_env_sektion_wird_abgelehnt(self):
        data = copy.deepcopy(self.data)
        data["env"] = self.env_of()
        data["env"]["declared_pins_sha256"] = "0" * 64
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_unvollstaendige_env_sektion_wird_abgelehnt(self):
        data = copy.deepcopy(self.data)
        data["env"] = {"cuda_wheels": "none"}
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)

    def test_nach_deploy_eingeschleustes_paket_wird_abgelehnt(self):
        data = copy.deepcopy(self.data)
        data["env"] = self.env_of()
        dist = self.site / "fremdpaket-9.9.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.3\nName: fremdpaket\nVersion: 9.9\n", encoding="utf-8")
        data["venv"].update(manifest_tool.venv_snapshot(self.vpy))
        result, output = self.verify(data)
        self.assertEqual(result, 1, output)


if __name__ == "__main__":
    unittest.main()
