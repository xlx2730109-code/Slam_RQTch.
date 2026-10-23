#!/usr/bin/env python3
"""极简巡检：位姿直达点，不用 A*/DWA/栅格地图。
带三重保护：位姿跳变、卡死、超时。"""
import rospy, math, sys, json
from geometry_msgs.msg import Twist, PoseStamped

VX = 0.30
KW = 1.2
WMAX = 0.35
TOL_YAW = 0.12
TOL_POS = 0.25
st = {}

def cb(m):
    q = m.pose.orientation
    st['p'] = (m.pose.position.x, m.pose.position.y,
               math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z)))

def norm(a):
    while a > math.pi: a -= 2*math.pi
    while a < -math.pi: a += 2*math.pi
    return a

def main():
    wps = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    rospy.init_node('patrol_simple', anonymous=True)
    rospy.Subscriber('/slam_pose', PoseStamped, cb, queue_size=1)
    pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
    rospy.sleep(1.5)
    last = None
    for i, w in enumerate(wps):
        gx, gy = w['x'], w['y']
        t0 = rospy.get_time(); ref = None
        while not rospy.is_shutdown():
            p = st.get('p')
            if p is None:
                rospy.sleep(0.1); continue
            x, y, yaw = p
            d = math.hypot(gx-x, gy-y)
            err = norm(math.atan2(gy-y, gx-x) - yaw)
            if last is not None and math.hypot(x-last[0], y-last[1]) > 0.5:
                rospy.logerr('[SAFETY] pose jump at wp%d' % (i+1))
                pub.publish(Twist()); return
            last = (x, y)
            if abs(err) < TOL_YAW:
                if ref is None:
                    ref = (x, y, rospy.get_time())
                elif rospy.get_time() - ref[2] > 3.0:
                    if math.hypot(x-ref[0], y-ref[1]) < 0.04:
                        rospy.logerr('[SAFETY] stuck at wp%d' % (i+1))
                        pub.publish(Twist()); return
                    ref = (x, y, rospy.get_time())
            if d < TOL_POS:
                pub.publish(Twist())
                print('WP%d arrived, %.2f m left, %.1f s' % (i+1, d, rospy.get_time()-t0), flush=True)
                rospy.sleep(1.0); break
            m = Twist()
            if abs(err) > TOL_YAW:
                m.angular.z = max(-WMAX, min(WMAX, KW*err))
            else:
                m.linear.x = VX * max(0.35, 1.0 - abs(err)/0.6)
                m.angular.z = max(-WMAX, min(WMAX, KW*err))
            pub.publish(m)
            rospy.sleep(0.05)
            if rospy.get_time() - t0 > 60:
                pub.publish(Twist()); print('WP%d timeout' % (i+1), flush=True); return
    pub.publish(Twist())
    print('all done', flush=True)

if __name__ == '__main__':
    main()