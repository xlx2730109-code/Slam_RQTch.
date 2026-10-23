#!/usr/bin/env python3
"""沿走廊直行：不依赖 SLAM yaw，只用雷达左右墙距离居中；前方到墙停车。
用法: corridor_follow.py <目标里程 m>"""
import rospy, math, sys, numpy as np
from geometry_msgs.msg import Twist
from sensor_msgs.msg import PointCloud2
import sensor_msgs.point_cloud2 as pc2

VX = 0.28
K  = 1.6
WMAX = 0.30
STOP_FRONT = 1.00
TARGET = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
STOP_ANG = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

cloud = {}
def cb(m):
    pts = np.array(list(pc2.read_points(m, field_names=('x','y','z'), skip_nans=True)), np.float32)
    if len(pts) == 0:
        return
    msk = (np.abs(pts[:,2]) < 0.6) & (pts[:,0]**2 + pts[:,1]**2 < 25)
    cloud['p'] = pts[msk][:, :2]

def sector_d(p, a0, a1, rmax=3.0):
    if len(p) == 0: return None
    ang = np.degrees(np.arctan2(p[:,1], p[:,0]))
    r = np.linalg.norm(p, axis=1)
    sel = (ang >= a0) & (ang < a1) & (r < rmax)
    return float(np.median(r[sel])) if sel.sum() >= 5 else None

def main():
    rospy.init_node('corridor_follow', anonymous=True)
    rospy.Subscriber('/unilidar/cloud', PointCloud2, cb, queue_size=1)
    pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
    rospy.sleep(1.5)
    t0 = rospy.get_time()
    travelled = 0.0
    while not rospy.is_shutdown():
        p = cloud.get('p')
        if p is None:
            rospy.sleep(0.1); continue
        L = sector_d(p, 55, 125)
        R = sector_d(p, -125, -55)
        F = sector_d(p, -12, 12, rmax=4.0)
        if L is None or R is None:
            pub.publish(Twist()); print('左右墙不可见，停车', flush=True); break
        if F is not None and F < STOP_FRONT:
            pub.publish(Twist()); print('前方 %.2f m 有障碍，停车' % F, flush=True); break
        if rospy.get_time() - t0 > 60:
            pub.publish(Twist()); print('超时停车', flush=True); break
        # 左右差 -> 转向；离哪边近就往另一边修
        err = (L - R)
        m = Twist()
        m.angular.z = max(-WMAX, min(WMAX, K * err * 0.5))
        m.linear.x = VX * max(0.4, 1.0 - min(abs(err), 1.0))
        pub.publish(m)
        if abs(err) < 0.15 and F is not None:
            travelled += VX * 0.05
            if travelled >= TARGET:
                pub.publish(Twist()); print('到达 %.2f m，停车' % travelled, flush=True); break
        rospy.sleep(0.05)
    pub.publish(Twist())

if __name__ == '__main__':
    main()
