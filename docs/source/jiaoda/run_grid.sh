#!/bin/bash
source /opt/ros/noetic/setup.bash
until rostopic list 2>/dev/null | grep -q /cloud_registered; do sleep 1; done
exec python3 -u /home/sjytt/jiaoda/grid_bridge.py
