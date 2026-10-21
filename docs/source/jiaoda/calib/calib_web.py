#!/usr/bin/env python3
import os, sys, json, time, glob, math, threading
import numpy as np
import cv2
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("CALIB_PORT", "8095"))
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.expanduser("~/jiaoda/calib/data")
CAM_YAML = os.path.expanduser("~/livo2_ws/src/FAST-LIVO2/config/camera_unitree.yaml")
MAIN_YAML = os.path.expanduser("~/livo2_ws/src/FAST-LIVO2/config/unitree_l2.yaml")
os.makedirs(os.path.join(DATA, "intr"), exist_ok=True)
os.makedirs(os.path.join(DATA, "extr"), exist_ok=True)

TAG_COLS, TAG_ROWS, TAG_SIZE, TAG_SPACING = 6, 6, 0.088, 0.3
PITCH = TAG_SIZE * (1.0 + TAG_SPACING)

state = {"cam": int(os.environ.get("CALIB_CAM", "0")), "frame": None, "tags": 0,
         "cloud_pts": 0, "cam_ok": False}
lock = threading.Lock()
clouds = []
extr = {"rx": 0.0, "ry": 0.0, "rz": 0.0, "tx": 0.0, "ty": 0.0, "tz": 0.0}
R_BASE = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], np.float64)


def load_K():
    d = {"cam_fx": 914.0, "cam_fy": 914.0, "cam_cx": 640.0, "cam_cy": 360.0}
    try:
        for ln in open(CAM_YAML):
            for k in d:
                if ln.strip().startswith(k + ":"):
                    d[k] = float(ln.split(":")[1].strip())
    except Exception:
        pass
    return d["cam_fx"], d["cam_fy"], d["cam_cx"], d["cam_cy"]


def make_detector():
    if hasattr(cv2.aruco, "Dictionary_get"):
        dd = cv2.aruco.Dictionary_get(cv2.aruco.DICT_APRILTAG_36h11)
        return ("legacy", dd, cv2.aruco.DetectorParameters_create())
    dd = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    return ("new", dd, cv2.aruco.ArucoDetector(dd, cv2.aruco.DetectorParameters()))


DET = make_detector()


def detect_markers(gray):
    if DET[0] == "legacy":
        c, ids, _ = cv2.aruco.detectMarkers(gray, DET[1], parameters=DET[2])
    else:
        c, ids, _ = DET[2].detectMarkers(gray)
    return c, ids


def euler_R(rx, ry, rz):
    rx, ry, rz = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def current_Rt():
    R = euler_R(extr["rx"], extr["ry"], extr["rz"]) @ R_BASE
    t = np.array([extr["tx"], extr["ty"], extr["tz"]], np.float64)
    return R, t


class CamThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.cap = None; self.want = state["cam"]

    def open(self, idx):
        if self.cap is not None:
            self.cap.release(); self.cap = None
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap = cap; return cap.isOpened()

    def run(self):
        n = 0
        while True:
            if self.want != state["cam"] or self.cap is None:
                state["cam"] = self.want; state["cam_ok"] = self.open(self.want)
                if not state["cam_ok"]:
                    time.sleep(1.0); continue
            ok, fr = self.cap.read()
            if not ok:
                state["cam_ok"] = False; time.sleep(0.5); continue
            n += 1
            with lock:
                state["frame"] = fr
            if n % 4 == 0:
                _, ids = detect_markers(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
                state["tags"] = 0 if ids is None else len(ids)
            time.sleep(0.03)


cam = CamThread()


def ros_thread():
    try:
        import rospy
        from sensor_msgs.msg import PointCloud2
        import sensor_msgs.point_cloud2 as pc2
        rospy.init_node("calib_web", anonymous=True, disable_signals=True)

        def cb(msg):
            pts = np.array([[p[0], p[1], p[2]] for i, p in enumerate(
                pc2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)) if i < 60000], np.float64)
            if len(pts) == 0:
                return
            clouds.append(pts)
            del clouds[:-4]
            state["cloud_pts"] = sum(len(c) for c in clouds)
        rospy.Subscriber("/unilidar/cloud", PointCloud2, cb, queue_size=1)
        rospy.spin()
    except Exception as e:
        sys.stderr.write("ros calib fail: %r\n" % e)


cam.start()
threading.Thread(target=ros_thread, daemon=True).start()


def project_overlay(fr):
    out = fr.copy()
    if not clouds:
        return out
    pl = np.concatenate(clouds, 0)
    R, t = current_Rt()
    pc = (R @ pl.T).T + t
    z = pc[:, 2]
    m = z > 0.15
    pc = pc[m]; z = z[m]
    fx, fy, cx, cy = load_K()
    u = (fx * pc[:, 0] / z + cx).astype(np.int32)
    v = (fy * pc[:, 1] / z + cy).astype(np.int32)
    H, W = out.shape[:2]
    ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u = u[ok]; v = v[ok]; zz = z[ok]
    if len(zz) == 0:
        return out
    zc = np.clip(zz, 0.5, 8.0)
    hue = (180 * (zc - 0.5) / 7.5).astype(np.uint8)
    hsv = np.stack([hue, np.full_like(hue, 255), np.full_like(hue, 255)], 1).reshape(-1, 1, 3)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).reshape(-1, 3)
    for i in range(len(u)):
        cv2.circle(out, (int(u[i]), int(v[i])), 2, (int(bgr[i, 0]), int(bgr[i, 1]), int(bgr[i, 2])), -1)
    cv2.putText(out, "proj pts: %d" % len(u), (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    return out


def tag_obj(tid):
    r = tid // TAG_COLS; c = tid % TAG_COLS
    x = c * PITCH; y = r * PITCH; s = TAG_SIZE
    return np.array([[x, y, 0], [x+s, y, 0], [x+s, y+s, 0], [x, y+s, 0]], np.float32)


def run_intrinsics():
    files = sorted(glob.glob(os.path.join(DATA, "intr", "*.jpg")))
    op, ip, size, used = [], [], None, 0
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if size is None:
            size = (g.shape[1], g.shape[0])
        c, ids = detect_markers(g)
        if ids is None or len(ids) < 4:
            continue
        oo, ii = [], []
        for k in range(len(ids)):
            tid = int(ids[k][0])
            if 0 <= tid < TAG_COLS * TAG_ROWS:
                oo.append(tag_obj(tid)); ii.append(c[k].reshape(4, 2).astype(np.float32))
        if len(oo) >= 4:
            op.append(np.concatenate(oo, 0)); ip.append(np.concatenate(ii, 0)); used += 1
    if used < 5:
        return {"ok": False, "err": "usable images %d (<5). AprilGrid detect failed" % used}
    rms, K, dist, _, _ = cv2.calibrateCamera(op, ip, size, None, None, flags=cv2.CALIB_FIX_K3)
    return {"ok": True, "used": used, "rms": round(float(rms), 4),
            "fx": round(float(K[0, 0]), 3), "fy": round(float(K[1, 1]), 3),
            "cx": round(float(K[0, 2]), 3), "cy": round(float(K[1, 2]), 3),
            "w": size[0], "h": size[1], "dist": [round(float(x), 6) for x in dist.reshape(-1)[:4]]}


def save_extr():
    R, t = current_Rt()
    Rl = ", ".join("%.6f" % x for x in R.reshape(-1))
    Pl = ", ".join("%.6f" % x for x in t)
    try:
        lines = open(MAIN_YAML).read().splitlines()
        out = []
        for ln in lines:
            s = ln.strip()
            if s.startswith("Rcl:"):
                out.append("  Rcl: [%s]" % Rl)
            elif s.startswith("Pcl:"):
                out.append("  Pcl: [%s]" % Pl)
            else:
                out.append(ln)
        open(MAIN_YAML, "w").write("\n".join(out) + "\n")
        return True
    except Exception as e:
        sys.stderr.write("save_extr fail %r\n" % e); return False


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    def _mjpeg(self, proj):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.end_headers()
        try:
            while True:
                with lock:
                    fr = None if state["frame"] is None else state["frame"].copy()
                if fr is not None:
                    img = project_overlay(fr) if proj else self._detoverlay(fr)
                    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(("Content-Length: %d\r\n\r\n" % len(buf)).encode())
                        self.wfile.write(buf.tobytes() + b"\r\n")
                time.sleep(0.08)
        except Exception:
            return

    def _detoverlay(self, fr):
        out = fr.copy()
        c, ids = detect_markers(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
        if ids is not None and len(ids):
            cv2.aruco.drawDetectedMarkers(out, c, ids)
        n = 0 if ids is None else len(ids)
        col = (0, 220, 0) if n >= 12 else (0, 165, 255) if n > 0 else (0, 0, 255)
        cv2.putText(out, "AprilTags: %d" % n, (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, col, 3)
        return out

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/calib.html"):
            b = open(os.path.join(HERE, "calib.html"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p == "/status":
            return self._j({"cam": state["cam"], "cam_ok": state["cam_ok"], "tags": state["tags"],
                            "cloud_pts": state["cloud_pts"],
                            "intr": len(glob.glob(os.path.join(DATA, "intr", "*.jpg"))),
                            "extr": len(glob.glob(os.path.join(DATA, "extr", "*.jpg")))})
        if p == "/extr":
            return self._j(extr)
        if p == "/stream.mjpg":
            return self._mjpeg(False)
        if p == "/project.mjpg":
            return self._mjpeg(True)
        return self._j({"err": "not found"}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        b = self._body()
        if p == "/setcam":
            cam.want = int(b.get("i", 0)); return self._j({"ok": True})
        if p == "/setextr":
            for k in extr:
                if k in b:
                    extr[k] = float(b[k])
            return self._j({"ok": True, "extr": extr})
        if p == "/saveextr":
            return self._j({"ok": save_extr(), "extr": extr})
        if p == "/capture":
            mode = b.get("mode", "intr")
            with lock:
                fr = None if state["frame"] is None else state["frame"].copy()
            if fr is None:
                return self._j({"ok": False, "err": "no frame"})
            d = os.path.join(DATA, "intr" if mode == "intr" else "extr")
            idx = len(glob.glob(os.path.join(d, "*.jpg")))
            name = os.path.join(d, "%04d" % idx)
            cv2.imwrite(name + ".jpg", fr)
            if mode == "extr" and clouds:
                np.save(name + ".npy", np.concatenate(clouds, 0))
            _, ids = detect_markers(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
            return self._j({"ok": True, "count": idx + 1, "tags": 0 if ids is None else len(ids)})
        if p == "/intrinsics":
            return self._j(run_intrinsics())
        if p == "/clear":
            for f in glob.glob(os.path.join(DATA, "intr" if b.get("mode") == "intr" else "extr", "*")):
                os.remove(f)
            return self._j({"ok": True})
        return self._j({"err": "not found"}, 404)


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    sys.stderr.write("calib web on :%d\n" % PORT)
    srv.serve_forever()


if __name__ == "__main__":
    main()
