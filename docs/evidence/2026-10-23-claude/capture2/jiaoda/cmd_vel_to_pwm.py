#!/usr/bin/env python3
import rospy
import serial
import time
from geometry_msgs.msg import Twist

PORT = "/dev/ttyACM0"
BAUD = 115200
NEUTRAL = 1500
MAX_DELTA = 180
VX_SCALE = 120
WZ_SCALE = 120
ser = None

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def cb(msg):
    if ser is None:
        return
    left = NEUTRAL + int(msg.linear.x * VX_SCALE - msg.angular.z * WZ_SCALE)
    right = NEUTRAL + int(msg.linear.x * VX_SCALE + msg.angular.z * WZ_SCALE)
    left = clamp(left, NEUTRAL - MAX_DELTA, NEUTRAL + MAX_DELTA)
    right = clamp(right, NEUTRAL - MAX_DELTA, NEUTRAL + MAX_DELTA)
    try:
        ser.write(("%d,%d\n" % (left, right)).encode())
    except Exception:
        pass

def shutdown():
    if ser is not None:
        try:
            ser.write(b"1500,1500\n"); time.sleep(0.1); ser.close()
        except Exception:
            pass

if __name__ == "__main__":
    rospy.init_node("cmd_vel_to_pwm")
    ser = serial.Serial(PORT, BAUD, timeout=0.1, write_timeout=0.3)
    try:
        ser.setDTR(False); ser.setRTS(False)
    except Exception:
        pass
    time.sleep(2)
    rospy.Subscriber("/cmd_vel", Twist, cb, queue_size=1)
    try:
        ser.write(b"1500,1500\n")
    except Exception:
        pass
    rospy.on_shutdown(shutdown)
    rospy.loginfo("cmd_vel_to_pwm ready -> %s", PORT)
    rospy.spin()
