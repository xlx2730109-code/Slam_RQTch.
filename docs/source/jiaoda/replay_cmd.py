#!/usr/bin/env python3
"""回放摇杆指令：按原时间轴重发 /cmd_vel"""
import rospy, json, sys
from geometry_msgs.msg import Twist
F = sys.argv[1] if len(sys.argv) > 1 else "/home/sjytt/jiaoda/teach_cmd.jsonl"
SPEED = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
rows = [json.loads(l) for l in open(F)]
if not rows:
    print('空文件'); sys.exit(1)
rospy.init_node('replay_cmd', anonymous=True)
pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
rospy.sleep(1.0)
t0 = rows[0]['t']
start = rospy.get_time()
print('回放 %d 条，时长 %.1f s' % (len(rows), (rows[-1]['t']-t0)/SPEED), flush=True)
for r in rows:
    target = start + (r['t']-t0)/SPEED
    while rospy.get_time() < target and not rospy.is_shutdown():
        m = Twist(); m.linear.x = r['v']; m.angular.z = r['w']
        pub.publish(m); rospy.sleep(0.02)
pub.publish(Twist())
print('回放结束', flush=True)