#!/usr/bin/env python3
"""Audit the exported baseline and prepare a non-starting Jetson candidate."""
import argparse
import ast
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import warnings
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "source"
MANIFEST = ROOT / "deploy" / "baseline-manifest.json"
BASELINE = "3b664ba1444c3299b9201ffdb775e98cc1ebd45e"
COMPONENTS = {
    "jiaoda": "jiaoda",
    "FAST-LIVO2": "livo2_ws/src/FAST-LIVO2",
    "rpg_vikit": "livo2_ws/src/rpg_vikit",
    "Sophus_src": "Sophus_src",
    "unitree_lidar_ros": "unilidar_sdk2/unitree_lidar_ros/src/unitree_lidar_ros",
    "unitree_lidar_sdk": "unilidar_sdk2/unitree_lidar_sdk",
    "firmware": "firmware",
}
PROGRAMS = {
    "restamp": "cloud_restamp.py", "campub": "cam_publisher.py",
    "grid": "grid_bridge.py", "posebridge": "pose_bridge.py",
    "nav": "nav_simple.py", "control": "chassis_gimbal_bridge.py",
    "console": "console_backend.py", "mission": "nav_mission.py",
}
SENSING = ("lidar", "restamp", "campub", "fastlivo", "grid", "posebridge", "console")
NODES = ("roscore",) + SENSING + ("nav", "control", "mission")


def canonical(path):
    data = path.read_bytes()
    if b"\0" not in data:
        try:
            data.decode("utf-8")
            return data.replace(b"\r\n", b"\n")
        except UnicodeDecodeError:
            pass
    return data


def inventory():
    return {p.relative_to(SOURCE).as_posix(): hashlib.sha256(canonical(p)).hexdigest()
            for p in sorted(SOURCE.rglob("*"))
            if p.is_file() and p != SOURCE / "README.md"}


def audit():
    errors = []
    doc = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    expected = doc["files"]
    actual = inventory()
    for name in sorted(set(expected) | set(actual)):
        if expected.get(name) != actual.get(name):
            errors.append("baseline mismatch: " + name)
    scripts = list(SOURCE.rglob("*.py")) + list((ROOT / "tools").glob("*.py"))
    scripts += list((ROOT / "deploy" / "templates").glob("*.py"))
    for path in scripts:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path),
                          feature_version=(3, 8))
        except (SyntaxError, ValueError) as exc:
            if path == SOURCE / "rpg_vikit/vikit_py/src/vikit_py/depthmap_utils.py":
                print("KNOWN GAP: unused vendor depthmap_utils.py is Python 2; not a runtime entry")
            else:
                errors.append("Python 3.8 syntax: %s: %s" % (path.relative_to(ROOT), exc))
    xmls = list(SOURCE.rglob("*.launch")) + list(SOURCE.rglob("package.xml"))
    for path in xmls:
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            errors.append("XML: %s: %s" % (path.relative_to(ROOT), exc))
    for component in ("FAST-LIVO2", "unitree_lidar_ros", "Sophus_src"):
        folder = SOURCE / component
        text = (folder / "CMakeLists.txt").read_text(encoding="utf-8-sig")
        for relative in re.findall(r"\bsrc/[A-Za-z0-9_./-]+\.cpp\b", text):
            if not (folder / relative).is_file():
                errors.append("missing CMake source: %s/%s" % (component, relative))
    for name in ("aarch64", "x86_64"):
        path = SOURCE / "unitree_lidar_sdk" / "lib" / name / "libunilidar_sdk2.a"
        if not path.is_file() or not path.read_bytes().startswith(b"!<arch>\n"):
            errors.append("invalid SDK archive: " + name)
    empty_units = [p.name for p in (SOURCE / "systemd").glob("*.service") if not p.stat().st_size]
    for name in empty_units:
        print("KNOWN GAP: empty historical unit excluded from candidate: " + name)
    docs = [ROOT / "README.md", SOURCE / "README.md",
            ROOT / "docs/architecture.md", ROOT / "docs/reproduction.md"]
    for path in docs:
        for target in re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", path.read_text(encoding="utf-8-sig")):
            if target.startswith(("http:", "https:", "#")):
                continue
            if not (path.parent / target.split("#", 1)[0]).exists():
                errors.append("broken local link: %s -> %s" % (path.relative_to(ROOT), target))
    print("Baseline files: %d; Python syntax: %d; XML: %d" % (len(actual), len(scripts), len(xmls)))
    for error in errors:
        print("FAIL: " + error)
    print("PASS: offline structure/integrity only" if not errors else "FAIL: offline audit")
    return errors


def load_config(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    keys = {"schema", "user", "install_root", "camera_device", "serial_device",
            "console_camera_index", "console_port", "lidar_pc_ip", "lidar_ip"}
    if set(config) != keys or config["schema"] != 1:
        raise ValueError("config requires exactly the schema-1 example fields")
    user = config["user"]
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise ValueError("invalid Linux user")
    install = config["install_root"]
    if not re.fullmatch(r"/home/" + re.escape(user) + r"/[A-Za-z0-9_-]+", install):
        raise ValueError("install_root must be a dedicated /home/<user>/<directory>")
    for field in ("camera_device", "serial_device"):
        value = config[field]
        if not re.fullmatch(r"/dev/[A-Za-z0-9_./:-]+", value) or ".." in PurePosixPath(value).parts:
            raise ValueError("invalid device path: " + field)
    for field in ("lidar_pc_ip", "lidar_ip"):
        ipaddress.IPv4Address(config[field])
    for field, low, high in (("console_camera_index", 0, 99), ("console_port", 1024, 65535)):
        if type(config[field]) is not int or not low <= config[field] <= high:
            raise ValueError("invalid integer: " + field)
    if config["console_port"] in (8095, 11311):
        raise ValueError("console port conflicts with calibration or ROS Master")
    if config["lidar_pc_ip"] == config["lidar_ip"]:
        raise ValueError("PC and lidar IP must differ")
    return config


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def render(template, config):
    text = (ROOT / "deploy" / "templates" / template).read_text(encoding="utf-8")
    for key, value in config.items():
        text = text.replace("@@" + key.upper() + "@@", str(value))
    if "@@" in text:
        raise ValueError("unresolved template variable: " + template)
    return text


def stage(config_path, output):
    config = load_config(config_path)
    errors = audit()
    if errors:
        raise ValueError("baseline audit failed")
    output = output.resolve()
    if output.exists():
        raise ValueError("output already exists; choose a new directory")
    if ROOT == output or ROOT in output.parents:
        raise ValueError("candidate must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    install = config["install_root"]
    changes = []
    for component, destination in COMPONENTS.items():
        ignored = shutil.ignore_patterns("run*.sh", "net_watchdog.sh") if component == "jiaoda" else None
        shutil.copytree(SOURCE / component, output / destination, ignore=ignored)
    changes.append("jiaoda: legacy root launch scripts excluded; use generated run_node.sh")
    # Only a generated deployment copy receives relocatable paths.
    for path in sorted((output / "jiaoda").rglob("*.py")):
        original = path.read_text(encoding="utf-8-sig")
        relocated = original.replace("/home/sjytt/jiaoda", install + "/jiaoda")
        relocated = relocated.replace("~/jiaoda", install + "/jiaoda")
        relocated = relocated.replace("~/livo2_ws", install + "/livo2_ws")
        if relocated != original:
            write_text(path, relocated)
            changes.append(path.relative_to(output).as_posix() + ": deployment paths")
    lidar_yaml = output / COMPONENTS["unitree_lidar_ros"] / "config/config.yaml"
    text = lidar_yaml.read_text(encoding="utf-8-sig")
    for key, value in (("pc_ip", config["lidar_pc_ip"]), ("lidar_ip", config["lidar_ip"])):
        text, count = re.subn(r'^' + key + r':.*$', key + ': "' + value + '"', text, flags=re.M)
        if count != 1:
            raise ValueError("unexpected lidar config field: " + key)
    write_text(lidar_yaml, text)
    changes.append(str(lidar_yaml.relative_to(output)) + ": configured IPs")
    cmake = output / COMPONENTS["FAST-LIVO2"] / "CMakeLists.txt"
    text = cmake.read_text(encoding="utf-8-sig")
    anchor = "# Add libraries"
    if text.count(anchor) != 1:
        raise ValueError("unexpected FAST-LIVO2 CMake structure")
    text = text.replace(anchor, "link_directories(${Sophus_LIBRARY_DIRS})\n\n" + anchor)
    write_text(cmake, text)
    changes.append(str(cmake.relative_to(output)) + ": local Sophus link search")
    maps = output / "jiaoda/maps"
    if maps.exists():
        maps.rename(output / "reference_maps")
    for folder in ("jiaoda/maps", "jiaoda/routes", "jiaoda/photos", "systemd"):
        (output / folder).mkdir(parents=True, exist_ok=True)
    for folder in ("pcd", "image", "result", "ref_cur_combine"):
        (output / COMPONENTS["FAST-LIVO2"] / "Log" / folder).mkdir(parents=True, exist_ok=True)
    for name in ("build.sh", "run_node.sh", "preflight.py"):
        write_text(output / name, render(name, config))
    shutil.copy2(ROOT / "tools/health_check.py", output / "health_check.py")
    for name in NODES:
        requires = "" if name == "roscore" else "Requires=jiaoda-repro-roscore.service\nAfter=jiaoda-repro-roscore.service\n"
        unit = ("[Unit]\nDescription=SLAM reproduction candidate %s\nAfter=network.target\n%s"
                "[Service]\nType=simple\nUser=%s\nWorkingDirectory=%s\n"
                "ExecStart=/bin/bash %s/run_node.sh %s\nRestart=on-failure\nRestartSec=5\n"
                "[Install]\nWantedBy=multi-user.target\n") % (name, requires, config["user"], install, install, name)
        write_text(output / "systemd" / ("jiaoda-repro-" + name + ".service"), unit)
    report = {"schema": 1, "baseline_commit": BASELINE, "config": config,
              "default_profile": list(SENSING), "not_started": ["nav", "control", "mission"],
              "changes": changes, "status": "offline candidate; no hardware acceptance"}
    write_text(output / "candidate.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    hashes = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(output.rglob("*")) if p.is_file()}
    write_text(output / "candidate-sha256.json", json.dumps(hashes, indent=2) + "\n")
    print("Candidate generated: " + str(output))
    print("No build, installation, network configuration, services or devices were started.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("manifest")
    generate = sub.add_parser("stage")
    generate.add_argument("--config", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "manifest":
            if MANIFEST.exists():
                raise ValueError("baseline manifest already exists; never overwrite silently")
            data = {"schema": 1, "commit": BASELINE, "normalization": "UTF-8 text CRLF to LF; binary raw",
                    "files": inventory()}
            write_text(MANIFEST, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            print("Baseline manifest created: %d files" % len(data["files"]))
            return 0
        if args.command == "audit":
            return 1 if audit() else 0
        stage(args.config, args.output)
        return 0
    except (OSError, ValueError, ET.ParseError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
