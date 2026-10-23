#!/usr/bin/env python3
"""串口自愈：若 20 秒收不到 ESP32 遥测，重启桥接；仍无效则强制 USB 重新枚举。"""
import rospy, subprocess, time, os
from std_msgs.msg import String

last = {'t': time.time()}
def cb(m):
    if 'Serial' in m.data or 'GIMBAL' in m.data:
        last['t'] = time.time()

def run(cmd):
    try:
        subprocess.run(cmd, shell=True, timeout=25)
        return True
    except Exception as e:
        rospy.logerr('serial_guard: %r', e)
        return False

def main():
    rospy.init_node('serial_guard', anonymous=True)
    rospy.Subscriber('/jiaoda/esp_tel', String, cb, queue_size=20)
    rospy.sleep(20)
    restarts = 0
    while not rospy.is_shutdown():
        rospy.sleep(10)
        silent = time.time() - last['t']
        if silent > 20:
            rospy.logwarn('[SERIAL_GUARD] no telemetry for %.0fs, restarting bridge', silent)
            run('systemctl restart jiaoda-control')
            time.sleep(12)
            if time.time() - last['t'] > 20:
                # 不再操作 sysfs authorized：会把 Tegra xHCI 打挂，只能重启恢复
                import os
                if not os.path.exists('/dev/ttyACM0'):
                    rospy.logerr('[SERIAL_GUARD] /dev/ttyACM0 missing (xHCI wedged) - reboot required')
                else:
                    rospy.logwarn('[SERIAL_GUARD] still silent, bridge restart again')
                    run('systemctl restart jiaoda-control')
            last['t'] = time.time()

if __name__ == '__main__':
    main()
