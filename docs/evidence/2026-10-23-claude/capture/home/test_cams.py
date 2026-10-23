import cv2

for i in [0, 2, 4, 6]:
    cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
    ret, frame = cap.read()
    if ret and frame is not None:
        print(f"/dev/video{i}: OK, shape={frame.shape}")
        cv2.imwrite(f"/home/sjytt/camera_{i}.jpg", frame)
    else:
        print(f"/dev/video{i}: ERROR")
    cap.release()
