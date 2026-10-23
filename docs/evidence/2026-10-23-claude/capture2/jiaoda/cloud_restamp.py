#!/usr/bin/env python3
import rospy
from sensor_msgs.msg import PointCloud2
rospy.init_node("cloud_restamp", anonymous=False, disable_signals=True)
pub = rospy.Publisher("/synced/cloud", PointCloud2, queue_size=4)
def cb(m):
    m.header.stamp = rospy.Time.now()
    pub.publish(m)
rospy.Subscriber("/unilidar/cloud", PointCloud2, cb, queue_size=4, buff_size=2**24)
rospy.spin()
