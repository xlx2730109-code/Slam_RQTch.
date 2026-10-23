#!/usr/bin/env python3
"""SLAM 发散保护：位姿跑飞(|x|或|y| > LIMIT)连续 N 次 -> 重启 fastlivo+grid。
避免发散后空转把 CPU 占满、导致 SSH 连不上。"""
import rospy, subprocess, time
from geometry_msgs.msg import PoseStamped

LIMIT = 500.0        # m，正常室内不会超过
NEED  = 5            # 连续次数
COOLDOWN = 120.0     # 两次重启最小间隔

state = {'bad': 0, 'last': 0.0}

def cb(m):
    x, y = m.pose.position.x, m.pose.position.y
    if abs(x) > LIMIT or abs(y) > LIMIT:
        state['bad'] += 1
    else:
        state['bad'] = 0
    if state['bad'] >= NEED and time.time() - state['last'] > COOLDOWN:
        state['last'] = time.time()
        state['bad'] = 0
        rospy.logerr('[GUARD] pose diverged (%.0f, %.0f), restarting SLAM', x, y)
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'jiaoda-fastlivo', 'jiaoda-grid'])

def main():
    rospy.init_node('slam_guard', anonymous=True)
    rospy.Subscriber('/slam_pose', PoseStamped, cb, queue_size=5)
    rospy.loginfo('[GUARD] watching /slam_pose, limit %.0f m', LIMIT)
    rospy.spin()

if __name__ == '__main__':
    main()
