import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools/verify_snapshot.py"
spec = importlib.util.spec_from_file_location("snapshot", TOOL)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


@unittest.skipUnless(os.environ.get("CODEX_TEST_TMPDIR"), "Set CODEX_TEST_TMPDIR to disposable storage")
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["CODEX_TEST_TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "source.txt"
        self.file.write_bytes(b"line\r\n")
        self.manifest = self.root / "manifest.json"
        self.save({"source.txt": hashlib.sha256(b"line\n").hexdigest()})

    def save(self, files):
        self.manifest.write_text(json.dumps({"schema": 1, "files": files}), encoding="utf-8")

    def test_clean_and_line_endings(self):
        self.assertEqual([], snapshot.verify(self.root, self.manifest))

    def test_bom(self):
        self.file.write_bytes(b"\xef\xbb\xbfline\r\n")
        self.assertEqual([], snapshot.verify(self.root, self.manifest))

    def test_binary(self):
        data = b"\x00\r\n\xff"
        self.file.write_bytes(data)
        self.save({"source.txt": hashlib.sha256(data).hexdigest()})
        self.assertEqual([], snapshot.verify(self.root, self.manifest))

    def test_changed(self):
        self.file.write_bytes(b"changed")
        self.assertEqual(["changed: source.txt"], snapshot.verify(self.root, self.manifest))

    def test_missing(self):
        self.file.unlink()
        self.assertEqual(["missing: source.txt"], snapshot.verify(self.root, self.manifest))

    def test_traversal_rejected(self):
        self.save({"../outside": "0" * 64})
        with self.assertRaises(ValueError):
            snapshot.verify(self.root, self.manifest)

    def test_absolute_rejected(self):
        self.save({"C:/outside": "0" * 64})
        with self.assertRaises(ValueError):
            snapshot.verify(self.root, self.manifest)

    def test_schema_rejected(self):
        self.manifest.write_text('{"schema":2,"files":{}}', encoding="utf-8")
        with self.assertRaises(ValueError):
            snapshot.verify(self.root, self.manifest)


if __name__ == "__main__":
    unittest.main()
