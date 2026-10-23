#!/usr/bin/env python3
import os, sys, json, time, threading, math, glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "console.html")
ROUTES_DIR = os.path.expanduser("~/jiaoda/routes")
MAPS_DIR = os.path.expanduser("~/jiaoda/maps")
os.makedirs(ROUTES_DIR, exist_ok=True)
os.makedirs(MAPS_DIR, exist_ok=True)

PORT = int(os.environ.get("CONSOLE_PORT", "8090"))
ODOM_TOPICS = ["/aft_mapped_to_init", "/Odometry", "/lio_sam/mapping/odometry"]
CMD_VEL_TOPIC = os.environ.get("CMD_VEL_TOPIC", "/cmd_vel")
CAM_INDEX = int(os.environ.get("CAM_INDEX", "0"))
GIMBAL_PORT = os.environ.get("GIMBAL_PORT", "")

state = {
    "pose": None, "hz": 0.0, "nav": "待命",
    "params": {"pspeed": 0.55, "pyaw": 40, "pclear": 0.25, "pstop": 0.5},
    "gimbal": {"p": 0, "t": 0},
    "mapping": False, "map_name": "floor1",
    "ros": False,
}
_odom_ts = []


SHM_MAP = "/dev/shm/jiaoda_map.png"
SHM_SENSORS = "/dev/shm/jiaoda_sensors.json"


def board_temp():
    best = 0.0
    for f in glob.glob("/sys/devices/virtual/thermal/thermal_zone*/temp"):
        try:
            v = int(open(f).read().strip()) / 1000.0
            if v > best:
                best = v
        except Exception:
            pass
    return round(best, 1) if best else None


def read_sensors():
    try:
        if time.time() - os.stat(SHM_SENSORS).st_mtime > 5:
            return {}
        return json.load(open(SHM_SENSORS))
    except Exception:
        return {}


class Ros:
    def __init__(self):
        self.ok = False
        self.pub_cmd = None
        self.pub_gim = None
        self.Int16MultiArray = None
        threading.Thread(target=self._loop, daemon=True).start()

    def _master_online(self):
        try:
            import rosgraph
            return rosgraph.is_master_online()
        except Exception:
            return False

    def _loop(self):
        while True:
            if not self.ok:
                if self._master_online():
                    try:
                        self._connect()
                    except Exception as e:
                        sys.stderr.write("ros connect fail: %r\n" % e)
            else:
                if not self._master_online():
                    sys.stderr.write("ros master lost, exiting for systemd restart\n")
                    os._exit(0)
            time.sleep(3.0)

    def _connect(self):
        import rospy
        from geometry_msgs.msg import Twist
        from nav_msgs.msg import Odometry
        from std_msgs.msg import Int16MultiArray
        rospy.init_node("console_backend", anonymous=True, disable_signals=True)
        self.pub_cmd = rospy.Publisher(CMD_VEL_TOPIC, Twist, queue_size=1)
        self.pub_gim = rospy.Publisher("/jiaoda/gimbal", Int16MultiArray, queue_size=1)
        self.Int16MultiArray = Int16MultiArray
        for tp in ODOM_TOPICS:
            rospy.Subscriber(tp, Odometry, self._on_odom, queue_size=1)
        self.Twist = Twist
        self.ok = True
        state["ros"] = True
        sys.stderr.write("ROS connected\n")

    def _on_odom(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        state["pose"] = {"x": round(p.x, 3), "y": round(p.y, 3), "th": round(yaw, 4)}
        now = time.time()
        _odom_ts.append(now)
        del _odom_ts[:-30]
        if len(_odom_ts) > 1:
            state["hz"] = round((len(_odom_ts) - 1) / (_odom_ts[-1] - _odom_ts[0] + 1e-6), 1)

    def drive(self, v, w):
        if not self.ok:
            return False
        m = self.Twist()
        m.linear.x = float(v) * state["params"]["pspeed"]
        m.angular.z = float(w) * math.radians(state["params"]["pyaw"])
        self.pub_cmd.publish(m)
        return True


class Cam:
    def __init__(self):
        self.frame = None
        self.ok = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        try:
            import cv2
        except Exception:
            return
        while True:
            cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_V4L2)
            if not cap.isOpened():
                self.ok = False
                time.sleep(3)
                continue
            self.ok = True
            while True:
                r, fr = cap.read()
                if not r:
                    break
                ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    self.frame = buf.tobytes()
                time.sleep(0.05)
            cap.release()
            self.ok = False
            time.sleep(1)


ros = Ros()
cam = Cam()


def send_gimbal(p, t):
    state["gimbal"] = {"p": int(p), "t": int(t)}
    pitch = max(-30, min(30, int(t / 45.0 * 30)))
    yaw = max(-30, min(30, int(p / 90.0 * 30)))
    if ros.ok and ros.pub_gim is not None:
        try:
            ros.pub_gim.publish(ros.Int16MultiArray(data=[pitch, yaw]))
        except Exception as e:
            sys.stderr.write("gimbal pub fail: %r\n" % e)
            return False
    return True


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", "/console.html"):
            try:
                b = open(HTML, "rb").read()
            except Exception:
                b = b"console.html missing"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if path == "/api/pose":
            return self._json(state["pose"] or {})
        if path == "/api/ctl/status":
            sns = read_sensors()
            return self._json({"bat": sns.get("bat"), "temp": board_temp(), "hz": state["hz"],
                               "nav": state["nav"], "ros": state["ros"], "sensors": sns.get("ch")})
        if path == "/api/cam/stream.mjpg":
            return self._mjpeg()
        if path == "/api/nav/status":
            try:
                return self._json(json.load(open("/dev/shm/jiaoda_nav_status.json")))
            except Exception:
                return self._json({"state": "idle", "cur": 0, "total": 0})
        if path == "/api/mapinfo":
            try:
                return self._json(json.load(open("/dev/shm/jiaoda_map.json")))
            except Exception:
                return self._json({}, 204)
        if path == "/api/map":
            try:
                b = open(SHM_MAP, "rb").read()
            except Exception:
                return self._json({"ok": False}, 204)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        return self._json({"ok": False, "err": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        b = self._body()
        if path == "/api/ctl/drive":
            return self._json({"ok": ros.drive(b.get("v", 0), b.get("w", 0))})
        if path == "/api/ctl/param":
            state["params"].update({k: v for k, v in b.items()})
            return self._json({"ok": True, "params": state["params"]})
        if path == "/api/ctl/calib_heading":
            return self._json({"ok": True})
        if path.startswith("/api/map/"):
            act = path.rsplit("/", 1)[-1]
            if act == "start":
                state["mapping"] = True; state["nav"] = "建图中"
            elif act in ("freeze", "clear"):
                state["mapping"] = (act != "freeze")
                if act == "clear":
                    open("/dev/shm/jiaoda_map_clear", "w").write("1")
            elif act == "save":
                state["map_name"] = b.get("name", "floor1"); state["mapping"] = False
                open("/dev/shm/jiaoda_map_save", "w").write(state["map_name"])
            elif act == "load":
                open("/dev/shm/jiaoda_map_load", "w").write(b.get("name", "floor1"))
            return self._json({"ok": True, "act": act})
        if path == "/api/gimbal":
            return self._json({"ok": send_gimbal(b.get("p", 0), b.get("t", 0))})
        if path == "/api/nav/start":
            json.dump({"wps": b.get("wps", []), "route": b.get("route", "route")},
                      open("/dev/shm/jiaoda_mission.json", "w"))
            open("/dev/shm/jiaoda_nav_cmd", "w").write("start")
            return self._json({"ok": True, "n": len(b.get("wps", []))})
        if path == "/api/nav/cancel":
            open("/dev/shm/jiaoda_nav_cmd", "w").write("cancel")
            return self._json({"ok": True})
        if path == "/api/route/save":
            name = "default"
            open(os.path.join(ROUTES_DIR, name + ".json"), "w").write(json.dumps(b))
            return self._json({"ok": True, "name": name})
        if path == "/api/route/load":
            name = b.get("name", "default")
            f = os.path.join(ROUTES_DIR, name + ".json")
            if os.path.exists(f):
                return self._json({"ok": True, "wps": json.load(open(f))})
            return self._json({"ok": False}, 404)
        return self._json({"ok": False, "err": "not found"}, 404)

    def _mjpeg(self):
        if not cam.ok:
            return self._json({"ok": False, "err": "no camera"}, 503)
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                f = cam.frame
                if f:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(("Content-Length: %d\r\n\r\n" % len(f)).encode())
                    self.wfile.write(f + b"\r\n")
                time.sleep(0.06)
        except Exception:
            return


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    sys.stderr.write("console backend on :%d  (html=%s)\n" % (PORT, HTML))
    srv.serve_forever()


if __name__ == "__main__":
    main()
