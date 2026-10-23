#!/usr/bin/env python3
import os, json, time, threading
import rospy
from geometry_msgs.msg import Twist
from std_msgs.msg import Int16MultiArray

PORT = os.environ.get("ESP32_PORT", "/dev/ttyUSB0")
BAUD = 115200

NEUTRAL = 1500
PWM_MIN = 1000
PWM_MAX = 2000
MAX_DELTA = int(os.environ.get("ESP32_MAX_DELTA", "200"))
VX_SCALE = float(os.environ.get("ESP32_VX_SCALE", "150"))
WZ_SCALE = float(os.environ.get("ESP32_WZ_SCALE", "150"))

SHM = "/dev/shm/jiaoda_sensors.json"
BAT_CH = 0
BAT_EMPTY = float(os.environ.get("ESP32_BAT_EMPTY", "0"))
BAT_FULL = float(os.environ.get("ESP32_BAT_FULL", "4095"))

ser = None
ser_lock = threading.Lock()
pub_rc = None
pub_sensors = None


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def open_serial():
    global ser
    try:
        import serial
        ser = serial.Serial(PORT, BAUD, timeout=0.1)
        time.sleep(1.0)
        rospy.loginfo("esp32 serial open: %s", PORT)
        return True
    except Exception as e:
        ser = None
        rospy.logwarn_throttle(10, "esp32 serial unavailable (%s): %r -- degraded", PORT, e)
        return False


def send_line(s):
    if ser is None:
        return
    try:
        with ser_lock:
            ser.write(s.encode("ascii"))
    except Exception as e:
        rospy.logwarn_throttle(10, "esp32 write fail: %r", e)


def cb_cmd_vel(msg):
    vx, wz = msg.linear.x, msg.angular.z
    left = NEUTRAL + int(vx * VX_SCALE - wz * WZ_SCALE)
    right = NEUTRAL + int(vx * VX_SCALE + wz * WZ_SCALE)
    left = clamp(left, NEUTRAL - MAX_DELTA, NEUTRAL + MAX_DELTA)
    right = clamp(right, NEUTRAL - MAX_DELTA, NEUTRAL + MAX_DELTA)
    left = clamp(left, PWM_MIN, PWM_MAX)
    right = clamp(right, PWM_MIN, PWM_MAX)
    send_line("M%d,%d\n" % (left, right))


def cb_motor_cmd(msg):
    d = [int(x) for x in list(msg.data)[:5]]
    d += [NEUTRAL] * (5 - len(d))
    d = [clamp(x, PWM_MIN, PWM_MAX) for x in d]
    send_line("A%d,%d,%d,%d,%d\n" % tuple(d))


def bat_percent(raw):
    if BAT_FULL <= BAT_EMPTY:
        return None
    p = (raw - BAT_EMPTY) * 100.0 / (BAT_FULL - BAT_EMPTY)
    return int(round(clamp(p, 0, 100)))


def write_shm(sensors):
    raw = sensors[BAT_CH] if len(sensors) > BAT_CH else None
    obj = {"ch": sensors, "bat": bat_percent(raw) if raw is not None else None,
           "bat_raw": raw, "t": time.time()}
    try:
        tmp = SHM + ".tmp"
        with open(tmp, "w") as f:
            f.write(json.dumps(obj))
        os.replace(tmp, SHM)
    except Exception as e:
        rospy.logwarn_throttle(10, "shm write fail: %r", e)


def handle_line(text):
    parts = text.strip().split("\t")
    if len(parts) < 19 or parts[0] != "R":
        return
    try:
        vals = [int(x) for x in parts[1:19]]
    except ValueError:
        return
    rc = vals[:10]
    sensors = vals[10:18]
    if pub_rc is not None:
        m = Int16MultiArray(); m.data = rc; pub_rc.publish(m)
    if pub_sensors is not None:
        m = Int16MultiArray(); m.data = sensors; pub_sensors.publish(m)
    write_shm(sensors)


def reader_loop():
    buf = ""
    while not rospy.is_shutdown():
        if ser is None:
            if not open_serial():
                time.sleep(3.0)
            continue
        try:
            chunk = ser.read(256)
        except Exception as e:
            rospy.logwarn_throttle(10, "esp32 read fail: %r", e)
            try:
                ser.close()
            except Exception:
                pass
            globals()["ser"] = None
            time.sleep(1.0)
            continue
        if not chunk:
            continue
        buf += chunk.decode("ascii", "ignore")
        while "\n" in buf:
            ln, buf = buf.split("\n", 1)
            handle_line(ln)
        if len(buf) > 4096:
            buf = ""


def on_shutdown():
    if ser is not None:
        try:
            send_line("M%d,%d\n" % (NEUTRAL, NEUTRAL))
            time.sleep(0.2)
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    rospy.init_node("chassis_bridge")
    open_serial()
    pub_rc = rospy.Publisher("/jiaoda/rc", Int16MultiArray, queue_size=1)
    pub_sensors = rospy.Publisher("/jiaoda/sensors", Int16MultiArray, queue_size=1)
    rospy.Subscriber("/cmd_vel", Twist, cb_cmd_vel, queue_size=1)
    rospy.Subscriber("/jiaoda/motor_cmd", Int16MultiArray, cb_motor_cmd, queue_size=1)
    rospy.on_shutdown(on_shutdown)
    threading.Thread(target=reader_loop, daemon=True).start()
    rospy.loginfo("chassis_bridge started: /cmd_vel + /jiaoda/motor_cmd -> %s ; /jiaoda/rc + /jiaoda/sensors <- uplink", PORT)
    rospy.spin()
