"""Offline checks; scratch location must be explicitly provided by the caller."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("reproduce", ROOT / "tools/reproduce.py")
reproduce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reproduce)


class ReproductionTests(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("SLAM_TEST_TMP")
        if not base:
            raise RuntimeError("Set SLAM_TEST_TMP to the authorized E-drive task directory")
        self.tmp = tempfile.TemporaryDirectory(prefix="repro-test-", dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.config = json.loads((ROOT / "deploy/robot.example.json").read_text(encoding="utf-8"))

    def config_path(self):
        path = self.folder / "robot.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        return path

    def test_baseline_integrity_and_structure(self):
        self.assertEqual(reproduce.audit(), [])

    def test_rejects_unsafe_install_paths(self):
        for target in ("/", "/home/sjytt", "/home/sjytt/../other", "/home/sjytt/x;echo"):
            with self.subTest(target=target):
                self.config["install_root"] = target
                with self.assertRaises(ValueError):
                    reproduce.load_config(self.config_path())

    def test_rejects_shell_and_device_injection(self):
        self.config["camera_device"] = "/dev/video0;touch /tmp/x"
        with self.assertRaises(ValueError):
            reproduce.load_config(self.config_path())

    def test_rejects_unknown_fields(self):
        self.config["enable_motion"] = True
        with self.assertRaises(ValueError):
            reproduce.load_config(self.config_path())

    def test_rejects_invalid_network_and_ports(self):
        for key, value in (("lidar_ip", "invalid"), ("console_port", True),
                           ("console_port", 8095), ("console_camera_index", -1)):
            original = self.config[key]
            self.config[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    reproduce.load_config(self.config_path())
            self.config[key] = original

    def test_stage_isolated_relocatable_and_inert(self):
        before = reproduce.inventory()
        self.config["user"] = "robot"
        self.config["install_root"] = "/home/robot/slam_repro"
        output = self.folder / "candidate"
        reproduce.stage(self.config_path(), output)
        self.assertEqual(before, reproduce.inventory())
        report = json.loads((output / "candidate.json").read_text())
        self.assertEqual(report["not_started"], ["nav", "control", "mission"])
        self.assertTrue((output / "reference_maps/floor1.npz").is_file())
        self.assertEqual(list((output / "jiaoda/maps").iterdir()), [])
        self.assertTrue((output / "livo2_ws/src/FAST-LIVO2/src/LIVMapper.cpp").is_file())
        self.assertTrue((output / "livo2_ws/src/FAST-LIVO2/Log/result").is_dir())
        self.assertEqual(list((output / "jiaoda").glob("run*.sh")), [])
        units = list((output / "systemd").glob("*.service"))
        self.assertEqual(len(units), 11)
        self.assertFalse((output / "systemd/jiaoda-netwatch.service").exists())
        for unit in units:
            text = unit.read_text()
            self.assertIn("User=robot", text)
            self.assertIn("ExecStart=/bin/bash /home/robot/slam_repro/run_node.sh", text)
            self.assertNotIn("/home/sjytt", text)
        for path in (output / "jiaoda").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("~/jiaoda", text)
            self.assertNotIn("~/livo2_ws", text)
        manifest = json.loads((output / "candidate-sha256.json").read_text())
        for path, digest in manifest.items():
            self.assertEqual(hashlib.sha256((output / path).read_bytes()).hexdigest(), digest)
        for name in ("build.sh", "run_node.sh", "preflight.py"):
            self.assertNotIn(b"\r\n", (output / name).read_bytes())
            self.assertNotIn("@@", (output / name).read_text())
        with self.assertRaises(ValueError):
            reproduce.stage(self.config_path(), output)

    def test_normalized_hashes_match_across_text_line_endings(self):
        path = self.folder / "source.cpp"
        path.write_bytes(b"int main() {}\r\n")
        self.assertEqual(reproduce.canonical(path), b"int main() {}\n")
        path.write_bytes(b"\x00\r\n")
        self.assertEqual(reproduce.canonical(path), b"\x00\r\n")


if __name__ == "__main__":
    unittest.main()
