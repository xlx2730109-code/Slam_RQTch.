#!/usr/bin/env python3
"""Verify retained snapshot files without connecting to or starting a robot."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def canonical_bytes(path):
    data = path.read_bytes()
    if b"\0" not in data:
        try:
            return data.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
    return data


def verify(root, manifest):
    root = Path(root).resolve()
    doc = json.loads(Path(manifest).read_text(encoding="utf-8-sig"))
    if doc.get("schema") != 1 or not isinstance(doc.get("files"), dict):
        raise ValueError("unsupported snapshot manifest")
    errors = []
    for name, expected in sorted(doc["files"].items()):
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("unsafe manifest path: " + name)
        path = root / name
        if root not in path.resolve().parents:
            raise ValueError("manifest path escapes repository: " + name)
        if not path.is_file():
            errors.append("missing: " + name)
        elif hashlib.sha256(canonical_bytes(path)).hexdigest() != expected:
            errors.append("changed: " + name)
    return errors


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=root / "deploy/live-manifest-20261023.json")
    args = parser.parse_args()
    try:
        errors = verify(root, args.manifest)
    except (OSError, ValueError, KeyError) as exc:
        print("FAIL:", exc)
        return 2
    for error in errors:
        print("FAIL:", error)
    if errors:
        return 1
    print("PASS: {} snapshot files; integrity only, not robot acceptance".format(
        len(json.loads(args.manifest.read_text(encoding="utf-8-sig"))["files"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
