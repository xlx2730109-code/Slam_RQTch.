#!/bin/bash
source /opt/ros/noetic/setup.bash
source ~/livo2_ws/devel/setup.bash 2>/dev/null
exec python3 -u ~/jiaoda/console_backend.py
