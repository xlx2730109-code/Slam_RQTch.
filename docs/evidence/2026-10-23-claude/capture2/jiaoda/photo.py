import os, json, time

PHOTO_DIR = os.path.expanduser("~/jiaoda/photos")


def _ts():
    return time.strftime("%Y%m%d_%H%M%S")


def _paths(route, wp_idx, ts):
    base = "%s_wp%s_%s" % (route, wp_idx, ts)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    return os.path.join(PHOTO_DIR, base + ".jpg"), os.path.join(PHOTO_DIR, base + ".json")


def _write_meta(meta_path, jpg_path, route, wp_idx, ts, meta):
    rec = {
        "route": route, "wp_idx": wp_idx, "ts": ts, "time": time.time(),
        "jpg": jpg_path,
    }
    if meta:
        rec.update(meta)
    with open(meta_path, "w") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)


def capture(cam_index, route, wp_idx, meta=None):
    ts = _ts()
    jpg_path, meta_path = _paths(route, wp_idx, ts)
    ok = False
    try:
        import cv2
        cap = cv2.VideoCapture(cam_index, cv2.CAP_V4L2)
        if cap.isOpened():
            for _ in range(3):
                r, fr = cap.read()
            if r:
                ok = cv2.imwrite(jpg_path, fr)
        cap.release()
    except Exception as e:
        import sys
        sys.stderr.write("capture fail: %r\n" % e)
    if ok:
        _write_meta(meta_path, jpg_path, route, wp_idx, ts, meta)
        return {"ok": True, "jpg": jpg_path, "json": meta_path}
    return {"ok": False, "jpg": jpg_path}


def capture_frame(jpg_bytes, route, wp_idx, meta=None):
    ts = _ts()
    jpg_path, meta_path = _paths(route, wp_idx, ts)
    if not jpg_bytes:
        return {"ok": False, "jpg": jpg_path}
    with open(jpg_path, "wb") as f:
        f.write(jpg_bytes)
    _write_meta(meta_path, jpg_path, route, wp_idx, ts, meta)
    return {"ok": True, "jpg": jpg_path, "json": meta_path}


if __name__ == "__main__":
    print(capture(0, "test", 0, {"pose": {"x": 1, "y": 2}, "gimbal": {"p": 10, "t": -5}}))
