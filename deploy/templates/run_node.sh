#!/bin/bash
set -eo pipefail
ROOT="@@INSTALL_ROOT@@"
source /opt/ros/noetic/setup.bash
export ROS_MASTER_URI=http://127.0.0.1:11311
export ROS_HOSTNAME=127.0.0.1
export LD_LIBRARY_PATH="$ROOT/Sophus_src/build:${LD_LIBRARY_PATH:-}"
export CTL_PORT="@@SERIAL_DEVICE@@"
export CAMPUB_DEV="@@CAMERA_DEVICE@@"
export CAM_INDEX=@@CONSOLE_CAMERA_INDEX@@
export CONSOLE_PORT=@@CONSOLE_PORT@@
node="${1:-}"
case "$node" in
  roscore|lidar|restamp|campub|fastlivo|grid|posebridge|nav|control|console|mission) ;;
  *) echo "Unknown candidate node" >&2; exit 2 ;;
esac
for old in lidar restamp campub fastlivo grid posebridge nav control console mission chassis calib; do
  if systemctl is-active --quiet "jiaoda-$old.service"; then
    echo "Refusing parallel use with active original service jiaoda-$old" >&2
    exit 1
  fi
done
# The historical applications use shared /dev/shm paths; run one stack at a time.
wait_data() {
  timeout 12 rostopic echo -n 1 "$1" >/dev/null 2>&1 || {
    echo "No messages on $1" >&2; exit 1;
  }
}
if [[ "$node" == roscore ]]; then
  if rostopic list >/dev/null 2>&1; then
    echo "An existing ROS Master is online; candidate will not take it over" >&2
    exit 1
  fi
  exec roscore
fi
timeout 12 bash -c 'until rostopic list >/dev/null 2>&1; do sleep 0.5; done'
case "$node" in
  lidar)
    source "$ROOT/unilidar_sdk2/unitree_lidar_ros/devel/setup.bash"
    exec roslaunch --wait unitree_lidar_ros run_without_rviz.launch ;;
  fastlivo)
    wait_data /synced/cloud
    wait_data /unilidar/imu
    wait_data /left_camera/image
    source "$ROOT/livo2_ws/devel/setup.bash"
    exec roslaunch --wait fast_livo mapping_unitree_l2.launch rviz:=false ;;
  restamp) wait_data /unilidar/cloud ;;
  grid) wait_data /cloud_registered ;;
  posebridge) wait_data /aft_mapped_to_init ;;
  nav) wait_data /slam_pose; wait_data /imu; wait_data /map; wait_data /unilidar/cloud ;;
  mission) wait_data /slam_pose; wait_data /left_camera/image ;;
esac
case "$node" in
  restamp) script=cloud_restamp.py ;;
  campub) script=cam_publisher.py ;;
  grid) script=grid_bridge.py ;;
  posebridge) script=pose_bridge.py ;;
  nav) script=nav_simple.py ;;
  control) script=chassis_gimbal_bridge.py ;;
  console) script=console_backend.py ;;
  mission) script=nav_mission.py ;;
esac
exec python3 -u "$ROOT/jiaoda/$script"
