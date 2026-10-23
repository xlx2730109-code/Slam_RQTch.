#!/bin/bash
source /opt/ros/noetic/setup.bash
source ~/livo2_ws/devel/setup.bash
until rostopic list 2>/dev/null | grep -q /synced/cloud; do sleep 1; done
exec roslaunch fast_livo mapping_unitree_l2.launch rviz:=false
