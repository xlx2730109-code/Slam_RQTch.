#!/bin/bash
set -eo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ "$ROOT" == "@@INSTALL_ROOT@@" ]] || { echo "Copy candidate to @@INSTALL_ROOT@@ first" >&2; exit 1; }
python3 "$ROOT/preflight.py" --build
source /opt/ros/noetic/setup.bash
cmake -S "$ROOT/Sophus_src" -B "$ROOT/Sophus_src/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/Sophus_src/build" --parallel 4
cd "$ROOT/livo2_ws"
catkin_make -j4 -DCMAKE_BUILD_TYPE=Release -DSophus_DIR="$ROOT/Sophus_src/build"
cd "$ROOT/unilidar_sdk2/unitree_lidar_ros"
catkin_make -j4
echo "Build finished. No services installed or started."
