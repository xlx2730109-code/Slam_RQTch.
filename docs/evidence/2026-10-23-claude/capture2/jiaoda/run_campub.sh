#!/bin/bash
source /opt/ros/noetic/setup.bash
until rostopic list >/dev/null 2>&1; do sleep 1; done
# 按 USB 物理口绑定（1-4.2.1.3，前视相机），避免 /dev/videoN 漂移
export CAMPUB_DEV=/dev/v4l/by-path/platform-3610000.xhci-usb-0:4.2.1.3:1.0-video-index0
exec python3 -u /home/sjytt/jiaoda/cam_publisher.py
