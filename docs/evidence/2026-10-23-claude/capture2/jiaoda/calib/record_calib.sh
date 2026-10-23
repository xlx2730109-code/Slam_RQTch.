#!/usr/bin/env bash
set -e

source /opt/ros/noetic/setup.bash

IMG_TOPIC="${IMG_TOPIC:-/left_camera/image}"
LID_TOPIC="${LID_TOPIC:-/cloud}"
IMU_TOPIC="${IMU_TOPIC:-/imu}"
OUT_DIR="${OUT_DIR:-$HOME/calib_data}"
CAM_DEV="${CAM_DEV:-0}"
IMG_W="${IMG_W:-1280}"
IMG_H="${IMG_H:-720}"

mkdir -p "$OUT_DIR"
HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
    echo "usage: $0 <cmd>"
    echo "  frames        grab intrinsic images from /dev/video${CAM_DEV} -> \$OUT_DIR/frames"
    echo "  intr          run cv2 intrinsic calibration on \$OUT_DIR/frames"
    echo "  bag           rosbag record img+cloud+imu for cam-lidar extrinsic"
    echo "  bag_dense     rosbag record cloud+imu only (dense-cloud accumulation)"
    echo "  topics        list current topics/hz to verify names before recording"
    echo ""
    echo "env overrides: IMG_TOPIC LID_TOPIC IMU_TOPIC OUT_DIR CAM_DEV IMG_W IMG_H"
}

case "${1:-}" in
    frames)
        python3 "$HERE/grab_frames.py" "$CAM_DEV" "$OUT_DIR/frames" "$IMG_W" "$IMG_H"
        ;;
    intr)
        python3 "$HERE/calib_intrinsics.py" "$OUT_DIR/frames" "$IMG_W" "$IMG_H"
        ;;
    bag)
        STAMP="$(date +%Y%m%d_%H%M%S)"
        echo "recording $IMG_TOPIC $LID_TOPIC $IMU_TOPIC -> $OUT_DIR/camlidar_${STAMP}.bag"
        echo "hold the robot STILL facing a scene with strong straight edges; Ctrl-C to stop"
        rosbag record -O "$OUT_DIR/camlidar_${STAMP}.bag" \
            "$IMG_TOPIC" "$LID_TOPIC" "$IMU_TOPIC"
        ;;
    bag_dense)
        STAMP="$(date +%Y%m%d_%H%M%S)"
        echo "recording $LID_TOPIC $IMU_TOPIC -> $OUT_DIR/dense_${STAMP}.bag"
        echo "keep robot STILL 20-40s so L2 sweeps accumulate a dense cloud; Ctrl-C to stop"
        rosbag record -O "$OUT_DIR/dense_${STAMP}.bag" \
            "$LID_TOPIC" "$IMU_TOPIC"
        ;;
    topics)
        rostopic list
        echo "---"
        echo "image hz:"; timeout 5 rostopic hz "$IMG_TOPIC" || true
        echo "cloud hz:"; timeout 5 rostopic hz "$LID_TOPIC" || true
        echo "imu hz:";   timeout 5 rostopic hz "$IMU_TOPIC" || true
        ;;
    *)
        usage
        ;;
esac
