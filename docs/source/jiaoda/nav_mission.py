#!/usr/bin/env python3
import os, json, time, math, threading
import rospy
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Int16MultiArray
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2

MISSION = "/dev/shm/jiaoda_mission.json"
CMD = "/dev/shm/jiaoda_nav_cmd"
STATUS = "/dev/shm/jiaoda_nav_status.json"
PHOTO_DIR = os.path.expanduser("~/jiaoda/photos")
os.makedirs(PHOTO_DIR, exist_ok=True)

ARRIVE = 0.35
pose = {"x": None, "y": None}
frame = {"img": None}
br = CvBridge()

def on_pose(m):
    pose["x"] = m.pose.position.x; pose["y"] = m.pose.position.y

def on_img(m):
    try:
        frame["img"] = br.imgmsg_to_cv2(m, "bgr8")
    except Exception:
        pass

def write_status(state, cur, total, msg=""):
    try:
        json.dump({"state": state, "cur": cur, "total": total, "msg": msg, "t": time.time()},
                  open(STATUS + ".tmp", "w")); os.replace(STATUS + ".tmp", STATUS)
    except Exception:
        pass

def read_cmd():
    try:
        c = open(CMD).read().strip(); os.remove(CMD); return c
    except Exception:
        return ""

def snap(route, idx):
    img = frame["img"]
    if img is None:
        return
    name = os.path.join(PHOTO_DIR, "%s_wp%02d_%d.jpg" % (route, idx + 1, int(time.time())))
    cv2.imwrite(name, img)
    rospy.loginfo("photo saved %s", name)

def main():
    rospy.init_node("nav_mission")
    pub_goal = rospy.Publisher("/move_base_simple/goal", PoseStamped, queue_size=1)
    pub_gim = rospy.Publisher("/jiaoda/gimbal", Int16MultiArray, queue_size=1)
    rospy.Subscriber("/slam_pose", PoseStamped, on_pose, queue_size=1)
    rospy.Subscriber("/left_camera/image", Image, on_img, queue_size=1)
    write_status("idle", 0, 0)
    running = False; wps = []; idx = 0; route = "route"
    r = rospy.Rate(5)
    goal_sent = False
    while not rospy.is_shutdown():
        c = read_cmd()
        if c == "start":
            try:
                m = json.load(open(MISSION)); wps = m.get("wps", []); route = m.get("route", "route")
                idx = 0; running = len(wps) > 0; goal_sent = False
                rospy.loginfo("mission start: %d wps", len(wps))
            except Exception as e:
                rospy.logwarn("mission load fail %r", e)
        elif c == "cancel":
            running = False; write_status("idle", idx, len(wps), "cancelled")
        if running and pose["x"] is not None:
            if idx >= len(wps):
                running = False; write_status("done", len(wps), len(wps), "complete"); continue
            w = wps[idx]
            if not goal_sent:
                g = PoseStamped(); g.header.frame_id = "map"; g.header.stamp = rospy.Time.now()
                g.pose.position.x = w["x"]; g.pose.position.y = w["y"]; g.pose.orientation.w = 1.0
                pub_goal.publish(g); goal_sent = True
                write_status("moving", idx, len(wps), "to wp%d" % (idx + 1))
            d = math.hypot(w["x"] - pose["x"], w["y"] - pose["y"])
            if d < ARRIVE:
                write_status("shooting", idx, len(wps), "arrived wp%d" % (idx + 1))
                if w.get("gp") is not None:
                    pub_gim.publish(Int16MultiArray(data=[int(w.get("gt", 0)), int(w.get("gp", 0))]))
                    time.sleep(0.6)
                snap(route, idx)
                time.sleep(0.5)
                idx += 1; goal_sent = False
        r.sleep()

if __name__ == "__main__":
    main()
