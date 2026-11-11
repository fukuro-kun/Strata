"""Grenzfaelle fuer die aus dem Wheel-Manifest erzeugten pip-Pins."""

import unittest

from tools.offline.lock_python_deps import lock_requirements, manifest_hashes


class OfflineRequirements(unittest.TestCase):
    def setUp(self):
        self.hash_a = "a" * 64
        self.hash_b = "b" * 64
        self.manifest = (
            f"{self.hash_a}  demo_pkg-1.2-cp312-cp312-manylinux_x86_64.whl\n"
            f"{self.hash_b}  demo_pkg-1.2-cp314-cp314-manylinux_x86_64.whl\n"
        )

    def test_mehrere_plattform_wheels_und_marker(self):
        hashes = manifest_hashes(self.manifest)
        actual = lock_requirements(hashes, '# Kommentar\nDemo-Pkg==1.2; python_version >= "3.12"\n')
        self.assertEqual(actual, 'Demo-Pkg==1.2; python_version >= "3.12"'
                         f' --hash=sha256:{self.hash_a} --hash=sha256:{self.hash_b}\n')

    def test_fremde_version_erhaelt_keinen_hash(self):
        self.assertEqual(lock_requirements(manifest_hashes(self.manifest),
                                          'demo-pkg==1.1; python_version < "3.11"\n'),
                         'demo-pkg==1.1; python_version < "3.11"\n')

    def test_nur_feste_pins_und_ausgewaehlte_marker_sind_zulaessig(self):
        invalid = (
            "-r weitere.txt",
            "--find-links https://example.invalid/",
            "demo-pkg @ file:///tmp/demo.whl",
            "demo-pkg>=1.2",
            'demo-pkg==1.2; python_version >= "3.12" --find-links /tmp',
            'demo-pkg==1.2; os_name == "posix"',
        )
        for pin in invalid:
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                lock_requirements(manifest_hashes(self.manifest), pin + "\n")

    def test_manifest_verweigert_dateipfade_und_nicht_wheels(self):
        invalid = (
            "",
            f"{self.hash_a}  ../fremd-1-py3-none-any.whl\n",
            f"{self.hash_a}  demo-1.2.tar.gz\n",
            f"{self.hash_a}  demo.whl\n",
            f"{self.hash_a.upper()}  demo-1.2-py3-none-any.whl\n",
            self.manifest + self.manifest.splitlines()[0] + "\n",
        )
        for manifest in invalid:
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                manifest_hashes(manifest)


if __name__ == "__main__":
    unittest.main()
