#!/usr/bin/env python3
"""录制摇杆指令：把 /cmd_vel 按时间轴存成 jsonl"""
import rospy, json, time, sys
from geometry_msgs.msg import Twist
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/sjytt/jiaoda/teach_cmd.jsonl"
def cb(m):
    with open(OUT, 'a') as f:
        f.write(json.dumps({'t': round(time.time(), 3),
                            'v': round(m.linear.x, 3),
                            'w': round(m.angular.z, 3)}) + "\n")
rospy.init_node('record_cmd', anonymous=True)
open(OUT, 'w').close()
rospy.Subscriber('/cmd_vel', Twist, cb, queue_size=50)
rospy.spin()