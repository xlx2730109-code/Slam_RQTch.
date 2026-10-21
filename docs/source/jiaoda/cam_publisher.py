#!/usr/bin/env python3
"""Camera -> ROS Image, with auto-reconnect.

替换原版：原版只打开一次设备且不重连，设备重新枚举后永久失效。
支持稳定设备名 CAMPUB_DEV（如 /dev/v4l/by-path/...），否则退回 CAMPUB_INDEX。
手动编码成 bgr8，去掉 cv_bridge 依赖（避免 cv_bridge 导入顺序坑）。
"""
import os, time
import rospy
import cv2
from sensor_msgs.msg import Image

TOPIC = os.environ.get("CAMPUB_TOPIC", "/left_camera/image")
DEV   = os.environ.get("CAMPUB_DEV", "")
IDX   = int(os.environ.get("CAMPUB_INDEX", "0"))
W     = int(os.environ.get("CAMPUB_W", "1280"))
H     = int(os.environ.get("CAMPUB_H", "720"))
FPS   = float(os.environ.get("CAMPUB_FPS", "15"))

def open_cap():
    src = DEV if DEV else IDX
    cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    return cap

def main():
    rospy.init_node("cam_publisher")
    pub = rospy.Publisher(TOPIC, Image, queue_size=1)
    cap = None
    last_try = 0.0
    fails = 0
    rate = rospy.Rate(FPS)
    while not rospy.is_shutdown():
        if cap is None:
            if time.time() - last_try >= 2.0:
                last_try = time.time()
                cap = open_cap()
                if cap is None:
                    rospy.logwarn_throttle(30, "open %s fail, retrying", DEV or IDX)
                    rate.sleep()
                    continue
                rospy.loginfo("camera opened: %s", DEV or IDX)
                fails = 0
        ok, fr = cap.read()
        if not ok or fr is None:
            fails += 1
            if fails >= 10:
                rospy.logwarn("read failed %d times, reopening", fails)
                cap.release()
                cap = None
                fails = 0
            time.sleep(0.1)
            continue
        fails = 0
        m = Image()
        m.header.stamp = rospy.Time.now()
        m.header.frame_id = "camera"
        m.height, m.width = fr.shape[:2]
        m.encoding = "bgr8"
        m.is_bigendian = 0
        m.step = m.width * 3
        m.data = fr.tobytes()
        pub.publish(m)
        rate.sleep()

if __name__ == "__main__":
    main()
