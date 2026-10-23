#!/bin/bash
source /opt/ros/noetic/setup.bash
export CALIB_CAM=2
exec python3 -u /home/sjytt/jiaoda/calib/calib_web.py
