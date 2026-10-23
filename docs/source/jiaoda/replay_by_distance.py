#!/usr/bin/env python3
"""按里程回放：用 /slam_pose 的位移推进录制进度，距离准，不受打滑影响。
用法: replay_by_distance.py <jsonl> [速度上限 m/s]"""
import rospy, json, sys, math
from geometry_msgs.msg import Twist, PoseStamped

F = sys.argv[1]
VMAX = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
rows = [json.loads(l) for l in open(F)]
if not rows:
    print('空记录'); sys.exit(1)

# 累积里程表
cum = [0.0]
for a, b in zip(rows, rows[1:]):
    cum.append(cum[-1] + abs(b['v']) * max(0.0, b['t'] - a['t']))
total = cum[-1]

st = {}
def cb(m):
    st['p'] = (m.pose.position.x, m.pose.position.y)
rospy.init_node('replay_dist', anonymous=True)
rospy.Subscriber('/slam_pose', PoseStamped, cb, queue_size=1)
pub = rospy.Publisher('/cmd_vel', Twist, queue_size=5)
rospy.sleep(1.5)

p0 = st.get('p'); last = p0; stuck_t = rospy.get_time()
print('目标里程 %.2f m' % total, flush=True)
i = 0
while not rospy.is_shutdown():
    p = st.get('p')
    if p is None or p0 is None:
        rospy.sleep(0.05); continue
    moved = math.hypot(p[0]-p0[0], p[1]-p0[1])
    while i+1 < len(cum) and cum[i+1] <= moved:
        i += 1
    if moved >= total - 0.03 or i >= len(rows)-1:
        break
    r = rows[i]
    m = Twist()
    m.linear.x = max(-VMAX, min(VMAX, r['v']))
    m.angular.z = max(-0.6, min(0.6, r['w']))
    pub.publish(m)
    if math.hypot(p[0]-last[0], p[1]-last[1]) > 0.02:
        last = p; stuck_t = rospy.get_time()
    if rospy.get_time() - stuck_t > 4.0:
        print('卡住 4 秒，停止', flush=True); break
    rospy.sleep(0.05)
pub.publish(Twist())
p = st.get('p')
print('完成，实际前进 %.2f m' % math.hypot(p[0]-p0[0], p[1]-p0[1]), flush=True)
