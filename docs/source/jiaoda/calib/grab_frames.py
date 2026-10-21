import os
import sys
import time
import cv2

DEV = int(sys.argv[1]) if len(sys.argv) > 1 else 0
OUT = sys.argv[2] if len(sys.argv) > 2 else "./frames"
W = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
H = int(sys.argv[4]) if len(sys.argv) > 4 else 720

os.makedirs(OUT, exist_ok=True)

cap = cv2.VideoCapture(DEV)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

if not cap.isOpened():
    print("cannot open /dev/video%d" % DEV)
    sys.exit(1)

print("device /dev/video%d opened, saving to %s" % (DEV, OUT))
print("keys:  SPACE=save frame   q=quit")

n = 0
has_gui = True
try:
    cv2.namedWindow("grab", cv2.WINDOW_NORMAL)
except Exception:
    has_gui = False

while True:
    ok, frame = cap.read()
    if not ok:
        print("read failed")
        break

    if has_gui:
        view = frame.copy()
        cv2.putText(view, "saved:%d  SPACE=save q=quit" % n, (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.imshow("grab", view)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(' '):
            path = os.path.join(OUT, "frame_%03d.png" % n)
            cv2.imwrite(path, frame)
            print("saved %s" % path)
            n += 1
        elif key == ord('q'):
            break
    else:
        path = os.path.join(OUT, "frame_%03d.png" % n)
        cv2.imwrite(path, frame)
        print("saved %s (headless, one per 1.5s, Ctrl-C to stop)" % path)
        n += 1
        time.sleep(1.5)

cap.release()
if has_gui:
    cv2.destroyAllWindows()
print("total saved: %d" % n)
