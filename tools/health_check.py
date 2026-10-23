#!/usr/bin/env python3
"""Observe ROS messages and read HTTP state without sending robot commands."""
import argparse
from collections import defaultdict
import json
import math
import threading
import time
import urllib.error
import urllib.request

SENSING = {"/unilidar/cloud": 5, "/unilidar/imu": 100, "/synced/cloud": 5,
           "/left_camera/image": 5, "/aft_mapped_to_init": 5,
           "/cloud_registered": 5, "/slam_pose": 5, "/map": 0.4}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("sensing", "control"), default="sensing")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not 3 <= args.seconds <= 30:
        parser.error("seconds must be between 3 and 30")
    try:
        import rospy
        import rostopic
        import rosgraph
    except ImportError as exc:
        print("FAIL: run on the Jetson after sourcing ROS Noetic: " + str(exc))
        return 1
    try:
        if not rosgraph.is_master_online():
            print("FAIL: ROS Master is offline")
            return 1
    except Exception as exc:
        print("FAIL: ROS Master lookup: " + str(exc))
        return 1
    checks = dict(SENSING)
    if args.profile == "control":
        checks["/jiaoda/esp_tel"] = 1
    samples = defaultdict(list)
    telemetry = []
    lock = threading.Lock()
    subscribers = []
    errors = []
    rospy.init_node("slam_repro_health", anonymous=True, disable_signals=True)

    def callback(message, topic):
        with lock:
            samples[topic].append(time.monotonic())
            if topic == "/jiaoda/esp_tel":
                telemetry.append(str(message.data)[:256])

    for topic in checks:
        try:
            kind, _, _ = rostopic.get_topic_class(topic, blocking=False)
            if kind is None:
                errors.append(topic + ": no registered type")
                continue
            subscribers.append(rospy.Subscriber(topic, kind, callback, callback_args=topic, queue_size=20))
        except Exception as exc:
            errors.append(topic + ": " + str(exc))
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline and not rospy.is_shutdown():
        time.sleep(0.05)
    with lock:
        observed = {topic: list(values) for topic, values in samples.items()}
    for topic, minimum in checks.items():
        values = observed.get(topic, [])
        hz = (len(values) - 1) / (values[-1] - values[0]) if len(values) > 1 else 0
        age = time.monotonic() - values[-1] if values else float("inf")
        valid = hz >= minimum and age <= max(1.0, 2.0 / minimum)
        print("%s: %s %.2f Hz; receipt age %.2f s" % ("PASS" if valid else "FAIL", topic, hz, age))
        if not valid:
            errors.append(topic + ": missing, slow or stale observed messages")
    # Bypass user/system proxy settings for the local robot console.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for endpoint, fields in (("/api/pose", ("x", "y", "th")),
                             ("/api/mapinfo", ("x0", "y0top", "mpp", "w", "h"))):
        try:
            with opener.open(args.url.rstrip("/") + endpoint, timeout=3) as response:
                data = json.load(response)
            if not all(key in data and isinstance(data[key], (int, float))
                       and math.isfinite(data[key]) for key in fields):
                raise ValueError("missing or non-numeric fields")
            if endpoint == "/api/mapinfo" and any(data[key] <= 0 for key in ("mpp", "w", "h")):
                raise ValueError("invalid map size or scale")
            print("PASS: HTTP " + endpoint + " structure only")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append("HTTP " + endpoint + ": " + str(exc))
    if telemetry:
        print("INFO: telemetry observed; this does not prove wheel motion or closed-loop velocity")
    for subscriber in subscribers:
        subscriber.unregister()
    for error in errors:
        print("FAIL: " + error)
    print("PASS: data-flow observation only; navigation and restart localization NOT accepted"
          if not errors else "FAIL: data-flow observation")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
