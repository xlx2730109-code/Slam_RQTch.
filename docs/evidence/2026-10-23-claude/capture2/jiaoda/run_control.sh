#!/bin/bash
source /opt/ros/noetic/setup.bash
until rostopic list >/dev/null 2>&1; do sleep 1; done
# 实测标定：throttle 1≈0.26 m/s, 3≈0.35, 6≈0.59 -> 取 THR_K=6.7 使 cmd_vel 接近真实 m/s
export THR_K=6.7
export STR_K=6.7
export CTL_PORT=/dev/ttyACM0
exec python3 -u /home/sjytt/jiaoda/chassis_gimbal_bridge.py
