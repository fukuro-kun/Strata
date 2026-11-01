# test_fork_component_dest.py — Manifest-unpack_to darf die Installations-Stage nicht verlassen.
#
# Unit-Test gegen das echte (gepruefte) strata_control.components — kein Netz, kein Modell,
# nur eigene Fixture-Verzeichnisse. Red/Positiv-Beweis pro Fall.
import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strata_control.components import Artifact, Component, ComponentStore, UnsafeArchive  # noqa: E402
from strata_control.targets import ComponentError                                        # noqa: E402

PAYLOAD = b"dummy bytes"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def _component(unpack_to, fmt="file", payload=PAYLOAD, name="payload.bin"):
    art = Artifact(name=name, url=None, sha256=hashlib.sha256(payload).hexdigest(),
                   bytes=len(payload), format=fmt, unpack_to=unpack_to)
    return Component(id="test-component", version="1.0", kind="engine", backend="cpu",
                     platforms=("linux-x86_64",), artifacts=(art,))


def _tar_bytes():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"inner"
        info = tarfile.TarInfo("inner.txt"); info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestUnpackToConfinement(unittest.TestCase):

    def _store(self):
        root = Path(tempfile.mkdtemp(prefix="cdt-"))
        self.addCleanup(shutil.rmtree, root, True)
        return root, ComponentStore(root / "store")

    def _install(self, store, comp, **kw):
        return store.install(comp, payloads={a.name: PAYLOAD for a in comp.artifacts},
                             target="linux-x86_64", backend="cpu", **kw)

    def _assert_complete(self, store, comp, rel):
        dest = store.cached(comp)
        self.assertIsNotNone(dest)
        self.assertEqual((dest / rel / "payload.bin").read_bytes(), PAYLOAD)
        self.assertIn(comp.version, store.state()["components"][comp.id]["installed"])

    def _assert_nothing(self, store, comp, *must_not_exist):
        for p in must_not_exist:
            self.assertFalse(Path(p).exists(), f"Flucht geschrieben: {p}")
        self.assertIsNone(store.cached(comp))
        cache = store.root / "cache"
        self.assertEqual(list(cache.iterdir()) if cache.exists() else [], [])

    # ---------- valide Faelle ----------
    def test_root_values_accepted(self):
        for unpack_to in (None, "", ".", "./"):
            with self.subTest(unpack_to=unpack_to):
                root, store = self._store()
                comp = _component(unpack_to)
                dest = self._install(store, comp)
                self.assertTrue((dest / ".complete").exists())
                self._assert_complete(store, comp, "")

    def test_nested_accepted(self):
        for unpack_to in ("nested/bin", "nested\\bin"):
            with self.subTest(unpack_to=unpack_to):
                root, store = self._store()
                comp = _component(unpack_to)
                dest = self._install(store, comp)
                self.assertTrue((dest / ".complete").exists())
                self._assert_complete(store, comp, "nested/bin")

    # ---------- Fokussierte Negativ-Faelle (Red-Lauf) ----------
    def test_parent_escape_refused(self):
        for unpack_to in ("../escape", "a/../../escape", "..\\escape"):
            with self.subTest(unpack_to=unpack_to):
                root, store = self._store()
                comp = _component(unpack_to)
                with self.assertRaises(UnsafeArchive):
                    self._install(store, comp)
                self._assert_nothing(store, comp, store.root / "cache" / "escape")

    def test_absolute_escape_refused(self):
        root, store = self._store()
        for unpack_to in (str(root / "escape-absolute"), "C:/escape", "C:escape",
                          "\\\\server\\share"):
            with self.subTest(unpack_to=unpack_to):
                comp = _component(unpack_to)
                with self.assertRaises(UnsafeArchive):
                    self._install(store, comp)
                self._assert_nothing(store, comp, root / "escape-absolute")

    def test_non_string_unpack_to_refused(self):
        for unpack_to in (42, ["sub"], {"path": "sub"}):
            with self.subTest(unpack_to=unpack_to):
                root, store = self._store()
                comp = _component(unpack_to)
                with self.assertRaises(ComponentError):
                    self._install(store, comp)
                self._assert_nothing(store, comp)

    # ---------- Symlink-/Archiv-Faelle ----------
    def test_symlink_escape_refused(self):
        root, store = self._store()
        outside = root / "outside"; outside.mkdir()
        comp = _component("bridge/sub")
        def _obtain(artifact, *, source=None, payloads=None):
            staging = next((store.root / "cache").glob(".*.partial"))
            (staging / "bridge").symlink_to(outside, target_is_directory=True)
            return payloads[artifact.name]
        with mock.patch.object(store, "_obtain", side_effect=_obtain):
            with self.assertRaises(UnsafeArchive):
                self._install(store, comp)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertIsNone(store.cached(comp))

    def test_tar_unpack_to_escape_refused(self):
        root, store = self._store()
        blob = _tar_bytes()
        art = Artifact(name="payload.bin", url=None, sha256=hashlib.sha256(blob).hexdigest(),
                       bytes=len(blob), format="tar.gz", unpack_to="../archive-out")
        comp = Component(id="test-component", version="1.0", kind="engine", backend="cpu",
                         platforms=("linux-x86_64",), artifacts=(art,))
        with self.assertRaises(UnsafeArchive):
            store.install(comp, payloads={"payload.bin": blob},
                          target="linux-x86_64", backend="cpu")
        self._assert_nothing(store, comp, store.root / "cache" / "archive-out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
