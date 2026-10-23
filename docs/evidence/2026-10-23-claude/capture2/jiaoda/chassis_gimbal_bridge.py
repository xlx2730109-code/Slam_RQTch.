#!/usr/bin/env python3
"""chassis + gimbal -> serial bridge.

改动（相对原版）：
  1. 默认端口 /dev/ttyACM0（CH343 以 CDC 模式枚举，系统里没有 ttyCH343USB0）；
  2. 打开前把 DTR/RTS 置低，避免每次启动把 ESP32 复位；
  3. 协议、限幅、看门狗保持不变。
"""
import os, threading, time
import rospy
import serial
from geometry_msgs.msg import Twist
from std_msgs.msg import String, Int16MultiArray

PORT = os.environ.get("CTL_PORT", "/dev/ttyACM0")
BAUD = 115200
THR_K = float(os.environ.get("THR_K", "55"))
STR_K = float(os.environ.get("STR_K", "45"))

ser = None
cmd = {"t": 0, "s": 0, "p": 0, "y": 0}
lock = threading.Lock()
last_drive = 0.0

def clamp(v):
    return max(-30, min(30, int(v)))

def on_cmd_vel(m):
    global last_drive
    with lock:
        cmd["t"] = clamp(m.linear.x * THR_K)
        cmd["s"] = clamp(m.angular.z * STR_K)
    last_drive = time.time()

def on_gimbal(m):
    with lock:
        cmd["p"] = clamp(m.data[0])
        cmd["y"] = clamp(m.data[1])

def open_port():
    p = serial.Serial()
    p.port = PORT
    p.baudrate = BAUD
    p.timeout = 0.1
    p.write_timeout = 0.3
    p.dtr = False
    p.rts = False
    p.open()
    p.dtr = False
    p.rts = False
    return p

def reader(pub):
    buf = b""
    while not rospy.is_shutdown():
        try:
            buf += ser.read(64)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                s = line.decode(errors="replace").strip()
                if s:
                    pub.publish(s)
        except Exception:
            time.sleep(0.2)

def main():
    global ser
    rospy.init_node("chassis_gimbal_bridge")
    pub = rospy.Publisher("/jiaoda/esp_tel", String, queue_size=5)
    rospy.Subscriber("/cmd_vel", Twist, on_cmd_vel, queue_size=1)
    rospy.Subscriber("/jiaoda/gimbal", Int16MultiArray, on_gimbal, queue_size=1)
    while ser is None and not rospy.is_shutdown():
        try:
            ser = open_port()
            rospy.loginfo("serial opened: %s @%d", PORT, BAUD)
        except Exception as e:
            rospy.logwarn("open %s fail: %r", PORT, e)
            time.sleep(3)
    threading.Thread(target=reader, args=(pub,), daemon=True).start()
    r = rospy.Rate(20)
    while not rospy.is_shutdown():
        with lock:
            if time.time() - last_drive > 0.5:
                cmd["t"] = 0; cmd["s"] = 0
            t, s, p, y = cmd["t"], cmd["s"], cmd["p"], cmd["y"]
        chk = t + s + p + y
        try:
            ser.write(("%d,%d,%d,%d,%d\n" % (t, s, p, y, chk)).encode())
        except Exception:
            pass
        r.sleep()

if __name__ == "__main__":
    main()
