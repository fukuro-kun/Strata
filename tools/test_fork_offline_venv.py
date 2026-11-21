"""Regressionen fuer die Offline-Venv ohne Netzwerk oder produktive Daten."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "offline" / "make_venv.sh"


def make_wheel(folder, project, dependency=None):
    name = project.replace("-", "_")
    wheel = folder / f"{name}-1.0-py3-none-any.whl"
    dist = f"{name}-1.0.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {project}\nVersion: 1.0\n"
    if dependency:
        metadata += f"Requires-Dist: {dependency}\n"
    contents = {
        f"{name}/__init__.py": "",
        f"{dist}/METADATA": metadata,
        f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = f"{dist}/RECORD"
    contents[record] = "".join(f"{entry},,\n" for entry in [*contents, record])
    with zipfile.ZipFile(wheel, "w") as archive:
        for entry, data in contents.items():
            archive.writestr(entry, data)
    return wheel


class OfflineVenv(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        offline = self.repo / "tools" / "offline"
        offline.mkdir(parents=True)
        self.script = offline / "make_venv.sh"
        shutil.copy2(SCRIPT, self.script)
        shutil.copy2(SCRIPT.parent / "lock_python_deps.py", offline / "lock_python_deps.py")
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.root), "LC_ALL": "C"}

    def run_script(self):
        return subprocess.run(
            ["/bin/bash", str(self.script), "--python", "/usr/bin/python3", "--cuda", "none"],
            env=self.env, capture_output=True, text=True, timeout=90,
        )

    def test_pythonpath_kann_ensurepip_nicht_ersetzen(self):
        poison = self.root / "poison"
        poison.mkdir()
        marker = self.root / "ausgefuehrt"
        (poison / "ensurepip.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8",
        )
        self.env["PYTHONPATH"] = str(poison)
        self.assertNotEqual(self.run_script().returncode, 0)  # Wheelhouse fehlt.
        self.assertFalse(marker.exists())

    def test_path_kann_systemwerkzeuge_nicht_ersetzen(self):
        fake_dir = self.root / "fake-bin"
        fake_dir.mkdir()
        marker = self.root / "ausgefuehrt"
        fake = fake_dir / "dirname"
        fake.write_text(
            f"#!/bin/sh\n/usr/bin/touch {str(marker)!r}\nexec /usr/bin/dirname \"$@\"\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        self.env["PATH"] = f"{fake_dir}:/usr/bin:/bin"
        self.assertNotEqual(self.run_script().returncode, 0)  # Wheelhouse fehlt.
        self.assertFalse(marker.exists())

    def prepare_untracked_wheel(self, dependency=None):
        external = self.root / "external"
        external.mkdir()
        make_wheel(external, "strata-test-untracked", dependency)

        wheelhouse = self.repo / "wheelhouse"
        wheelhouse.mkdir()
        dummy = wheelhouse / "unrelated-1.0-py3-none-any.whl"
        dummy.write_bytes(b"kein verwendetes Wheel")
        digest = hashlib.sha256(dummy.read_bytes()).hexdigest()
        (wheelhouse / "MANIFEST.sha256").write_text(f"{digest}  {dummy.name}\n", encoding="ascii")
        terminal = self.repo / "terminal"
        terminal.mkdir(exist_ok=True)
        (terminal / "requirements.txt").write_text("strata-test-untracked==1.0\n", encoding="ascii")
        (terminal / "requirements-build.txt").write_text("", encoding="ascii")
        (terminal / "setup.py").write_text("CUDA_WHEELS = []\nCUDA12_WHEELS = []\n", encoding="ascii")
        return external

    def assert_untracked_wheel_not_installed(self):
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("installing requirements.txt", result.stdout, result.stdout + result.stderr)
        packages = self.repo / ".venv-offline" / "lib"
        installed = list(packages.glob("python*/site-packages/strata_test_untracked"))
        self.assertEqual(installed, [], result.stdout + result.stderr)
        return result

    def test_pip_find_links_aus_umgebung_ist_nicht_weitere_quelle(self):
        external = self.prepare_untracked_wheel()
        self.env["PIP_FIND_LINKS"] = str(external)
        self.env["PIP_CONFIG_FILE"] = os.devnull
        result = self.assert_untracked_wheel_not_installed()
        self.assertIn("No matching distribution found", result.stderr)

    def test_pip_konfigurationsdatei_ist_nicht_weitere_quelle(self):
        external = self.prepare_untracked_wheel()
        config = self.root / "pip.conf"
        config.write_text(f"[global]\nfind-links = {external}\n", encoding="utf-8")
        self.env["PIP_CONFIG_FILE"] = str(config)
        result = self.assert_untracked_wheel_not_installed()
        self.assertIn("No matching distribution found", result.stderr)

    def test_requirements_koennen_keinen_direkten_dateilink_einschleusen(self):
        external = self.prepare_untracked_wheel()
        wheel = external / "strata_test_untracked-1.0-py3-none-any.whl"
        (self.repo / "terminal" / "requirements.txt").write_text(
            f"strata-test-untracked @ {wheel.as_uri()}\n", encoding="ascii",
        )
        result = self.assert_untracked_wheel_not_installed()
        self.assertIn("ungueltiger Abhaengigkeits-Pin", result.stderr)

    def test_wheel_metadaten_laden_keine_direkte_abhaengigkeit_nach(self):
        dependency = self.root / "external" / "strata_test_dependency-1.0-py3-none-any.whl"
        external = self.prepare_untracked_wheel(f"strata-test-dependency @ {dependency.as_uri()}")
        make_wheel(external, "strata-test-dependency")
        wheel = external / "strata_test_untracked-1.0-py3-none-any.whl"
        shutil.copy2(wheel, self.repo / "wheelhouse" / wheel.name)
        with (self.repo / "wheelhouse" / "MANIFEST.sha256").open("a", encoding="ascii") as manifest:
            manifest.write(f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n")
        result = self.run_script()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertTrue("strata-test-dependency" in output or "strata_test_dependency" in output, output)
        self.assertNotIn(f"Processing {dependency}", output)
        packages = self.repo / ".venv-offline" / "lib"
        self.assertEqual(list(packages.glob("python*/site-packages/strata_test_dependency")), [])

    def test_wheel_nach_manifestpruefung_veraendert_wird_abgelehnt(self):
        external = self.prepare_untracked_wheel()
        wheel = external / "strata_test_untracked-1.0-py3-none-any.whl"
        wheelhouse = self.repo / "wheelhouse"
        shutil.copy2(wheel, wheelhouse / wheel.name)
        with (wheelhouse / "MANIFEST.sha256").open("a", encoding="ascii") as manifest:
            manifest.write(f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n")
        source = self.script.read_text(encoding="utf-8")
        marker = 'UNEXPECTED="$(cd "$WH" && comm -23'
        self.assertEqual(source.count(marker), 1)
        source = source.replace(marker, f'printf manipulation >> "$WH/{wheel.name}"\n' + marker)
        self.script.write_text(source, encoding="utf-8")
        result = self.assert_untracked_wheel_not_installed()
        self.assertIn("THESE PACKAGES DO NOT MATCH THE HASHES", result.stderr)

    def test_zusaetzliches_wheel_bricht_vor_venv_erstellung_ab(self):
        external = self.prepare_untracked_wheel()
        wheel = external / "strata_test_untracked-1.0-py3-none-any.whl"
        shutil.copy2(wheel, self.repo / "wheelhouse" / wheel.name)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("files not in MANIFEST", result.stderr)
        self.assertFalse((self.repo / ".venv-offline").exists())

    def test_manipuliertes_wheel_bricht_vor_venv_erstellung_ab(self):
        self.prepare_untracked_wheel()
        (self.repo / "wheelhouse" / "unrelated-1.0-py3-none-any.whl").write_bytes(b"geaendert")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wheelhouse failed MANIFEST", result.stderr)
        self.assertFalse((self.repo / ".venv-offline").exists())

    def test_venv_kollision_nach_vorabpruefung_laesst_fremden_ordner_unberuehrt(self):
        self.prepare_untracked_wheel()
        source = self.script.read_text(encoding="utf-8")
        marker = 'info "creating $VENV with '
        self.assertEqual(source.count(marker), 1)
        source = source.replace(marker, '/usr/bin/mkdir "$VENV"\nprintf fremd > "$VENV/sentinel"\n' + marker)
        self.script.write_text(source, encoding="utf-8")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.repo / ".venv-offline" / "sentinel").read_text(), "fremd")
        self.assertFalse((self.repo / ".venv-offline" / "bin" / "python").exists())

    def test_auch_defekter_venv_symlink_wird_zurueckgewiesen(self):
        self.prepare_untracked_wheel()
        (self.repo / ".venv-offline").symlink_to(self.root / "nicht-vorhanden")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("already exists", result.stderr)
        self.assertFalse((self.root / "nicht-vorhanden").exists())

    def test_manifestwechsel_nach_pruefung_schleust_keine_wheels_ein(self):
        external = self.prepare_untracked_wheel()
        wheel = external / "strata_test_untracked-1.0-py3-none-any.whl"
        shutil.copy2(wheel, self.repo / "wheelhouse" / wheel.name)
        source = self.script.read_text(encoding="utf-8")
        marker = 'UNEXPECTED="$(cd "$WH" && comm -23'
        self.assertEqual(source.count(marker), 1)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        source = source.replace(
            marker, f'printf "{digest}  {wheel.name}\\n" >> "$WH/MANIFEST.sha256"\n' + marker,
        )
        self.script.write_text(source, encoding="utf-8")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        packages = self.repo / ".venv-offline" / "lib"
        self.assertEqual(list(packages.glob("python*/site-packages/strata_test_untracked")), [],
                         result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
