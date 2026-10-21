import os
import glob
import sys
import numpy as np
import cv2

IMG_DIR = sys.argv[1] if len(sys.argv) > 1 else "./frames"
IMG_W = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
IMG_H = int(sys.argv[3]) if len(sys.argv) > 3 else 720

TAG_COLS = 6
TAG_ROWS = 6
TAG_SIZE = 0.088
TAG_SPACING = 0.3

PITCH = TAG_SIZE * (1.0 + TAG_SPACING)


def tag_object_corners(tag_id):
    r = tag_id // TAG_COLS
    c = tag_id % TAG_COLS
    x = c * PITCH
    y = r * PITCH
    s = TAG_SIZE
    return np.array([
        [x,     y,     0.0],
        [x + s, y,     0.0],
        [x + s, y + s, 0.0],
        [x,     y + s, 0.0],
    ], dtype=np.float32)


def build_dictionary_and_params():
    if hasattr(cv2.aruco, "Dictionary_get"):
        dictionary = cv2.aruco.Dictionary_get(cv2.aruco.DICT_APRILTAG_36h11)
        params = cv2.aruco.DetectorParameters_create()
        return dictionary, params, "legacy"
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    return dictionary, detector, "new"


def detect(gray, dictionary, params, mode):
    if mode == "legacy":
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary, parameters=params)
    else:
        corners, ids, _ = params.detectMarkers(gray)
    return corners, ids


def main():
    files = sorted(glob.glob(os.path.join(IMG_DIR, "*.png")) +
                   glob.glob(os.path.join(IMG_DIR, "*.jpg")))
    if not files:
        print("no images in %s" % IMG_DIR)
        return

    dictionary, params, mode = build_dictionary_and_params()

    obj_points = []
    img_points = []
    used = 0
    size = None

    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if size is None:
            size = (gray.shape[1], gray.shape[0])
        corners, ids = detect(gray, dictionary, params, mode)
        if ids is None or len(ids) < 4:
            print("skip %s tags=%s" % (os.path.basename(f), 0 if ids is None else len(ids)))
            continue
        op = []
        ip = []
        for k in range(len(ids)):
            tid = int(ids[k][0])
            if tid < 0 or tid >= TAG_COLS * TAG_ROWS:
                continue
            oc = tag_object_corners(tid)
            ic = corners[k].reshape(4, 2).astype(np.float32)
            op.append(oc)
            ip.append(ic)
        if len(op) < 4:
            print("skip %s valid_tags=%d" % (os.path.basename(f), len(op)))
            continue
        obj_points.append(np.concatenate(op, axis=0))
        img_points.append(np.concatenate(ip, axis=0))
        used += 1
        print("use  %s tags=%d" % (os.path.basename(f), len(op)))

    if used < 8:
        print("too few usable frames (%d), grab more (>=20 recommended)" % used)
        if used == 0:
            return

    flags = cv2.CALIB_FIX_K3
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, size, None, None, flags=flags)

    fx = K[0, 0]; fy = K[1, 1]; cx = K[0, 2]; cy = K[1, 2]
    d = dist.reshape(-1)
    d0 = float(d[0]); d1 = float(d[1]); d2 = float(d[2]); d3 = float(d[3])

    print("")
    print("=== RESULT (frames used: %d, RMS reproj err: %.4f px) ===" % (used, rms))
    print("image size: %dx%d" % (size[0], size[1]))
    print("")
    print("cam_model: Pinhole")
    print("cam_width: %d" % size[0])
    print("cam_height: %d" % size[1])
    print("scale: 0.5")
    print("cam_fx: %.6f" % fx)
    print("cam_fy: %.6f" % fy)
    print("cam_cx: %.6f" % cx)
    print("cam_cy: %.6f" % cy)
    print("cam_d0: %.6f" % d0)
    print("cam_d1: %.6f" % d1)
    print("cam_d2: %.6f" % d2)
    print("cam_d3: %.6f" % d3)

    out = os.path.join(IMG_DIR, "intrinsics_result.yaml")
    with open(out, "w") as fp:
        fp.write("cam_model: Pinhole\n")
        fp.write("cam_width: %d\n" % size[0])
        fp.write("cam_height: %d\n" % size[1])
        fp.write("scale: 0.5\n")
        fp.write("cam_fx: %.6f\n" % fx)
        fp.write("cam_fy: %.6f\n" % fy)
        fp.write("cam_cx: %.6f\n" % cx)
        fp.write("cam_cy: %.6f\n" % cy)
        fp.write("cam_d0: %.6f\n" % d0)
        fp.write("cam_d1: %.6f\n" % d1)
        fp.write("cam_d2: %.6f\n" % d2)
        fp.write("cam_d3: %.6f\n" % d3)
    print("")
    print("written: %s" % out)


if __name__ == "__main__":
    main()
