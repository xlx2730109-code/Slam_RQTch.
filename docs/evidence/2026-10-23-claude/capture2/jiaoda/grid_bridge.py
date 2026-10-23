#!/usr/bin/env python3
import os, sys, time, math, json, argparse, threading
import numpy as np
import rospy
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import PointCloud2

CMD_SAVE  = "/dev/shm/jiaoda_map_save"
CMD_LOAD  = "/dev/shm/jiaoda_map_load"
CMD_CLEAR = "/dev/shm/jiaoda_map_clear"


def parse_xyz(msg):
    n = msg.width * msg.height
    if n == 0:
        return np.empty((0, 3), np.float32)
    off = {f.name: f.offset for f in msg.fields}
    ps = msg.point_step
    buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    rows = buf.shape[0] // ps
    raw = buf[:rows * ps].reshape(rows, ps)[:n]

    def comp(name, d):
        o = off.get(name, d)
        return raw[:, o:o + 4].copy().view(np.float32).reshape(-1)

    p = np.stack([comp('x', 0), comp('y', 4), comp('z', 8)], axis=1)
    return p[np.isfinite(p).all(axis=1)]


class Grid:
    def __init__(self, size, res):
        self.size = size
        self.res = res
        self.origin = size // 2
        self.log = np.zeros((size, size), np.float32)
        self.lock = threading.Lock()

    def w2rc(self, wx, wy):
        c = int(self.origin + wx / self.res)
        r = int(self.origin - wy / self.res)
        return r, c

    def _carve(self, grr, grc, rows, cols):
        n = len(rows)
        if n == 0:
            return
        k = max(1, n // 4)
        idx = np.random.choice(n, k, replace=False) if n > k else np.arange(n)
        lg = self.log
        sz = self.size
        for i in idx:
            dr = int(rows[i]) - grr
            dc = int(cols[i]) - grc
            steps = max(abs(dr), abs(dc), 1)
            if steps > sz:
                continue
            s = np.linspace(0.0, 1.0, steps, endpoint=False)
            rr = (grr + dr * s).astype(np.int32)
            cc = (grc + dc * s).astype(np.int32)
            m = (rr >= 0) & (rr < sz) & (cc >= 0) & (cc < sz)
            lg[rr[m], cc[m]] -= 0.4

    def integrate(self, rx, ry, pts_xy):
        c = (self.origin + pts_xy[:, 0] / self.res).astype(np.int32)
        r = (self.origin - pts_xy[:, 1] / self.res).astype(np.int32)
        m = (c >= 0) & (c < self.size) & (r >= 0) & (r < self.size)
        r = r[m]
        c = c[m]
        if len(r) == 0:
            return
        grr, grc = self.w2rc(rx, ry)
        with self.lock:
            self._carve(grr, grc, r, c)
            np.add.at(self.log, (r, c), 0.85)
            np.clip(self.log, -2.0, 5.0, out=self.log)

    def to_int8(self):
        with self.lock:
            data = np.full((self.size, self.size), -1, dtype=np.int8)
            data[self.log < -0.3] = 0
            data[self.log > 0.5] = 100
        return data

    def clear(self):
        with self.lock:
            self.log[:] = 0.0

    def save(self, path):
        with self.lock:
            lg = self.log.copy()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp.npz"
        np.savez_compressed(tmp, log_odds=lg, size=self.size, res=self.res)
        os.replace(tmp, path)

    def load(self, path):
        if not os.path.exists(path):
            return False
        d = np.load(path)
        lg = d["log_odds"]
        if lg.shape != (self.size, self.size):
            return False
        with self.lock:
            self.log = lg.astype(np.float32)
        return True


class Bridge:
    def __init__(self, a):
        self.a = a
        self.grid = Grid(a.size, a.res)
        self.pose = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0, "ok": False}
        self.plock = threading.Lock()
        self.maps_dir = os.path.expanduser(a.maps_dir)
        os.makedirs(self.maps_dir, exist_ok=True)

        rospy.Subscriber(a.odom, Odometry, self.on_odom, queue_size=5)
        rospy.Subscriber(a.cloud, PointCloud2, self.on_cloud, queue_size=1)
        self.pub = rospy.Publisher(a.map_topic, OccupancyGrid, queue_size=1, latch=True)
        self.seq = 0
        rospy.Timer(rospy.Duration(1.0), self.on_timer)
        threading.Thread(target=self.cmd_loop, daemon=True).start()

    def on_odom(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self.plock:
            self.pose.update(x=p.x, y=p.y, z=p.z, yaw=yaw, ok=True)

    def on_cloud(self, msg):
        with self.plock:
            if not self.pose["ok"]:
                return
            rx, ry, rz = self.pose["x"], self.pose["y"], self.pose["z"]
        pts = parse_xyz(msg)
        if len(pts) < 20:
            return
        dz = pts[:, 2] - rz
        zmask = (dz > self.a.zmin) & (dz < self.a.zmax)
        pts = pts[zmask]
        if len(pts) == 0:
            return
        d2 = (pts[:, 0] - rx) ** 2 + (pts[:, 1] - ry) ** 2
        rmask = (d2 > 0.09) & (d2 < self.a.rmax * self.a.rmax)
        pts = pts[rmask]
        if len(pts) == 0:
            return
        self.grid.integrate(rx, ry, pts[:, :2])

    def on_timer(self, event):
        self.publish_map()
        self.render_png()

    def publish_map(self):
        data = self.grid.to_int8()
        msg = OccupancyGrid()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = self.a.frame
        msg.header.seq = self.seq
        self.seq += 1
        msg.info.resolution = self.a.res
        msg.info.width = self.a.size
        msg.info.height = self.a.size
        msg.info.origin.position.x = -self.grid.origin * self.a.res
        msg.info.origin.position.y = -self.grid.origin * self.a.res
        msg.info.origin.orientation.w = 1.0
        msg.data = np.flipud(data).ravel().astype(np.int8).tolist()
        self.pub.publish(msg)

    def render_png(self):
        try:
            import cv2
        except Exception:
            return
        with self.grid.lock:
            lg = self.grid.log
            occ = lg > 0.5
            fre = lg < -0.3
            known = occ | fre
            if not known.any():
                return
            rr = np.where(known.any(axis=1))[0]
            cc = np.where(known.any(axis=0))[0]
        with self.plock:
            px, py, yaw = self.pose["x"], self.pose["y"], self.pose["yaw"]
        prr, pcc = self.grid.w2rc(px, py)
        pad = 20
        r0 = max(0, min(int(rr[0]), prr) - pad)
        r1 = min(self.grid.size, max(int(rr[-1]), prr) + pad)
        c0 = max(0, min(int(cc[0]), pcc) - pad)
        c1 = min(self.grid.size, max(int(cc[-1]), pcc) + pad)
        with self.grid.lock:
            sub = self.grid.log[r0:r1, c0:c1]
        h, w = sub.shape
        img = np.full((h, w, 3), (60, 42, 30), np.uint8)
        img[sub < -0.3] = (250, 250, 250)
        img[sub > 0.5] = (32, 26, 22)
        scale = 1
        if max(h, w) > 0:
            scale = max(1, int(900 // max(h, w)))
        if scale > 1:
            img = cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
        rx = int((pcc - c0) * scale)
        ry = int((prr - r0) * scale)
        rad = max(4, 4 * scale)
        cv2.circle(img, (rx, ry), rad, (216, 101, 21), -1)
        tx = int(rx + math.cos(yaw) * rad * 2.2)
        ty = int(ry - math.sin(yaw) * rad * 2.2)
        cv2.line(img, (rx, ry), (tx, ty), (255, 255, 255), max(2, scale))
        tmp = self.a.png + ".tmp.png"
        if cv2.imwrite(tmp, img):
            os.replace(tmp, self.a.png)
        meta = {"x0": float((c0 - self.grid.origin) * self.a.res),
                "y0top": float((self.grid.origin - r0) * self.a.res),
                "mpp": float(self.a.res / scale),
                "w": int(w * scale), "h": int(h * scale)}
        mtmp = "/dev/shm/jiaoda_map.json.tmp"
        json.dump(meta, open(mtmp, "w"))
        os.replace(mtmp, "/dev/shm/jiaoda_map.json")

    def cmd_loop(self):
        while not rospy.is_shutdown():
            try:
                if os.path.exists(CMD_CLEAR):
                    os.remove(CMD_CLEAR)
                    self.grid.clear()
                    rospy.loginfo("[grid] cleared")
                if os.path.exists(CMD_SAVE):
                    name = open(CMD_SAVE).read().strip() or "floor1"
                    os.remove(CMD_SAVE)
                    self.grid.save(os.path.join(self.maps_dir, name + ".npz"))
                    rospy.loginfo("[grid] saved %s" % name)
                if os.path.exists(CMD_LOAD):
                    name = open(CMD_LOAD).read().strip() or "floor1"
                    os.remove(CMD_LOAD)
                    ok = self.grid.load(os.path.join(self.maps_dir, name + ".npz"))
                    rospy.loginfo("[grid] load %s -> %s" % (name, ok))
            except Exception as e:
                rospy.logwarn("[grid] cmd err %r" % e)
            time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", default="/cloud_registered")
    ap.add_argument("--odom", default="/aft_mapped_to_init")
    ap.add_argument("--map-topic", dest="map_topic", default="/map")
    ap.add_argument("--frame", default="map")
    ap.add_argument("--res", type=float, default=0.05)
    ap.add_argument("--size", type=int, default=2000)
    ap.add_argument("--zmin", type=float, default=-0.4)
    ap.add_argument("--zmax", type=float, default=1.5)
    ap.add_argument("--rmax", type=float, default=15.0)
    ap.add_argument("--png", default="/dev/shm/jiaoda_map.png")
    ap.add_argument("--maps-dir", dest="maps_dir", default="~/jiaoda/maps")
    a = ap.parse_args()
    rospy.init_node("grid_bridge", anonymous=False, disable_signals=True)
    Bridge(a)
    rospy.loginfo("[grid] cloud=%s odom=%s -> %s + %s" % (a.cloud, a.odom, a.map_topic, a.png))
    rospy.spin()


if __name__ == "__main__":
    main()
