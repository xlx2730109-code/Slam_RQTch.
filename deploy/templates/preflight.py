#!/usr/bin/env python3
"""Read-only build/runtime prerequisites; never open devices or change services."""
import argparse
import getpass
from pathlib import Path
import platform
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    errors = []
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        errors.append("baseline target requires Linux aarch64 Jetson")
    if getpass.getuser() != "@@USER@@":
        errors.append("run as configured user @@USER@@")
    if sys.version_info[:2] != (3, 8):
        errors.append("baseline Python must be 3.8")
    os_release = Path("/etc/os-release")
    if not os_release.is_file() or 'VERSION_ID="20.04"' not in os_release.read_text():
        errors.append("baseline OS must be Ubuntu 20.04")
    release = Path("/etc/nv_tegra_release")
    if not release.is_file() or not release.read_text().startswith("# R35 (release), REVISION: 4.1"):
        errors.append("baseline Jetson Linux must be R35.4.1")
    if not Path("/opt/ros/noetic/setup.bash").is_file():
        errors.append("ROS Noetic is missing")
    if not args.build:
        for path in ("@@CAMERA_DEVICE@@", "@@SERIAL_DEVICE@@"):
            if not Path(path).exists():
                errors.append("device missing: " + path)
    try:
        import cv2
        from cv_bridge import CvBridge
        import numpy
        import serial
        import yaml
        if cv2.__version__ != "4.2.0":
            errors.append("baseline OpenCV must be 4.2.0")
        print("cv2=%s numpy=%s serial=%s" % (cv2.__version__, numpy.__version__, serial.__version__))
    except ImportError as exc:
        errors.append("Python dependency: " + str(exc))
    except Exception as exc:
        errors.append("Python ABI/import failure: " + str(exc))
    for error in errors:
        print("FAIL: " + error)
    print("PASS: prerequisites only" if not errors else "FAIL: prerequisites")
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
