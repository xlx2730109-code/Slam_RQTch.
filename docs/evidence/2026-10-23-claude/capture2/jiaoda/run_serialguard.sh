#!/bin/bash
source /opt/ros/noetic/setup.bash
export ROS_MASTER_URI=http://127.0.0.1:11311
until rostopic list >/dev/null 2>&1; do sleep 1; done
exec python3 -u /home/sjytt/jiaoda/serial_guard.py
