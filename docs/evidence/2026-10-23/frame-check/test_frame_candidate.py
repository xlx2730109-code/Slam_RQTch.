import json
import math
import pathlib
import unittest

import frame_candidate as frame
from analyze_frames import angle_diff, angular_summary


class FrameTests(unittest.TestCase):
    def test_front_mount_axes(self):
        mount = frame.mounting("+z", "+x")
        self.assertEqual(frame.sensor_to_body((0, 0, 1), mount), (1, 0, 0))
        self.assertEqual(frame.sensor_to_body((1, 0, 0), mount), (0, 0, 1))
        self.assertEqual(frame.sensor_to_body((0, -1, 0), mount), (0, 1, 0))

    def test_rear_mount_axes(self):
        mount = frame.mounting("-z", "+x")
        self.assertEqual(frame.sensor_to_body((0, 0, -1), mount), (1, 0, 0))
        self.assertEqual(frame.sensor_to_body((1, 0, 0), mount), (0, 0, 1))
        self.assertEqual(frame.sensor_to_body((0, 1, 0), mount), (0, 1, 0))

    def test_right_handed_basis(self):
        for direction in ("+z", "-z"):
            mount = frame.mounting(direction, "+x")
            self.assertEqual(frame.cross(mount[0], mount[1]), mount[2])

    def test_front_and_rear_differ_by_pi(self):
        q = (0, -math.sqrt(0.5), 0, math.sqrt(0.5))
        a = frame.body_heading(q, frame.mounting("+z", "+x"))
        b = frame.body_heading(q, frame.mounting("-z", "+x"))
        self.assertAlmostEqual(abs(angle_diff(a, b)), math.pi)

    def test_rejects_invalid_or_vertical_forward(self):
        with self.assertRaises(ValueError):
            frame.mounting("+x", "+x")
        with self.assertRaises(ValueError):
            frame.body_heading((0, 0, 0, 0), frame.mounting("+z", "+x"))
        with self.assertRaises(ValueError):
            frame.body_heading((0, 0, 0, 1), frame.mounting("+z", "+x"))

    def test_collected_sample_heading(self):
        data = json.loads(pathlib.Path(__file__).with_name("streams.json").read_text(encoding="utf-8-sig"))
        samples = next(s["samples"] for s in data["streams"] if s["topic"] == "/aft_mapped_to_init")
        for direction in ("+z", "-z"):
            headings = [frame.body_heading(s["q"], frame.mounting(direction, "+x")) for s in samples]
            self.assertLess(angular_summary(headings)["range_deg"], 1.0)


if __name__ == "__main__":
    unittest.main()
