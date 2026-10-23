#!/usr/bin/env python3
"""录制位姿轨迹（示教用），每 0.4 s 一个点"""
import rospy, json, math, time
from geometry_msgs.msg import PoseStamped
OUT = "/home/sjytt/jiaoda/teach_track.jsonl"
cur = {}
def cb(m):
    q = m.pose.orientation
    cur['x'] = m.pose.position.x; cur['y'] = m.pose.position.y
    cur['yaw'] = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
rospy.init_node('teach_record', anonymous=True)
rospy.Subscriber('/slam_pose', PoseStamped, cb, queue_size=1)
r = rospy.Rate(2.5)
f = open(OUT, 'w')
while not rospy.is_shutdown():
    if 'x' in cur:
        f.write(json.dumps({'t': round(time.time(),2), 'x': round(cur['x'],3),
                            'y': round(cur['y'],3), 'yaw': round(cur['yaw'],3)}) + "\n")
        f.flush()
    r.sleep()