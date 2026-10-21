#!/usr/bin/env python3
import os, rospy, cv2
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

IDX = int(os.environ.get("CAMPUB_INDEX", "2"))
TOPIC = os.environ.get("CAMPUB_TOPIC", "/left_camera/image")

def main():
    rospy.init_node("cam_publisher")
    pub = rospy.Publisher(TOPIC, Image, queue_size=1)
    br = CvBridge()
    cap = cv2.VideoCapture(IDX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    r = rospy.Rate(15)
    while not rospy.is_shutdown():
        ok, fr = cap.read()
        if ok:
            m = br.cv2_to_imgmsg(fr, "bgr8")
            m.header.stamp = rospy.Time.now()
            m.header.frame_id = "camera"
            pub.publish(m)
        r.sleep()

if __name__ == "__main__":
    main()
