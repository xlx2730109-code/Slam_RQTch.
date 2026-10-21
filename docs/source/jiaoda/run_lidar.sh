#!/bin/bash
source /opt/ros/noetic/setup.bash
source ~/unilidar_sdk2/unitree_lidar_ros/devel/setup.bash
exec roslaunch unitree_lidar_ros run_without_rviz.launch
