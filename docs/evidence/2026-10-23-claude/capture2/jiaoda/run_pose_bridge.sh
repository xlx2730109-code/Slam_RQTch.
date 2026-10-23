#!/bin/bash
source /opt/ros/noetic/setup.bash
until rostopic list >/dev/null 2>&1; do sleep 1; done
exec python3 -u /home/sjytt/jiaoda/pose_bridge.py
