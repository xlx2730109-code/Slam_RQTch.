#!/usr/bin/env python3
import rospy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Imu

pub_pose = None
pub_imu = None

def cb(msg):
    p = PoseStamped()
    p.header = msg.header
    p.header.frame_id = "map"
    p.pose = msg.pose.pose
    pub_pose.publish(p)
    im = Imu()
    im.header = msg.header
    im.header.frame_id = "base"
    im.orientation = msg.pose.pose.orientation
    im.angular_velocity = msg.twist.twist.angular
    pub_imu.publish(im)

def main():
    global pub_pose, pub_imu
    rospy.init_node("pose_bridge")
    pub_pose = rospy.Publisher("/slam_pose", PoseStamped, queue_size=10)
    pub_imu = rospy.Publisher("/imu", Imu, queue_size=10)
    rospy.Subscriber("/aft_mapped_to_init", Odometry, cb, queue_size=10)
    rospy.spin()

if __name__ == "__main__":
    main()
