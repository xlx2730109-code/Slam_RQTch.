# 相机内参标定（现场步骤，板子只有 OpenCV，无 Kalibr）

目标：求出前视相机的 `fx fy cx cy` 和畸变 `d0 d1 d2 d3`（= k1 k2 p1 p2），
填进 `../fastlivo/camera_unitree.yaml`。

标定分辨率必须和 Fast-LIVO2 里跑的一致：**1280x720**（camera_unitree.yaml 现值）。
若最终跑别的分辨率，就用那个分辨率重标一遍，内参不能跨分辨率缩放着用。

---

## 推荐路径 A：纯 OpenCV + 你手上的 AprilGrid（首选，板子现成能跑）

板子上只有 `cv2 4.2`，`cv2.aruco` 内置 `DICT_APRILTAG_36h11`，正好是 AprilGrid 用的家族。
脚本 `calib_intrinsics.py` 直接检测每个 tag 的 4 个角点，按 6x6 几何生成 3D 对应点，
再用 `cv2.calibrateCamera` 解算。不需要 Kalibr、不需要编译。

### 1. 录制标定图（要点）
用 `grab_frames.py` 从 `/dev/video0` 抓图（或用 record_calib.sh frames）：
```
python3 grab_frames.py 0 ./frames 1280 720
```
- 板子平铺在硬板上（不能有翘曲、褶皱），光照均匀、无反光/过曝。
- **≥ 20 张**，越多越稳；每张都要能看到大部分 tag。
- 覆盖要全：
  - 距离：近（板占画面 2/3）、中、远（板占 1/4）各拍几张。
  - 角度：正对 1~2 张，其余让板相对相机**倾斜 20°~45°**（上下左右都要有）。
  - 位置：把板分别摆到画面**四个角和中心**，让畸变在边角被充分观测到。
- 相机和板都别晃，抓的瞬间要静止（避免运动模糊）。

### 2. 解算
```
python3 calib_intrinsics.py ./frames 1280 720
```
输出会直接打印成 camera_unitree.yaml 的字段，并写到 `./frames/intrinsics_result.yaml`。

### 3. 判定是否合格
- 脚本打印的 **RMS 重投影误差** 应 `< 0.5 px`（好），`> 1.0 px` 说明有糊图/翘板/张数不够，重拍。
- `cx cy` 应接近图像中心（约 640, 360），偏太多说明样本角度/位置不够均匀。
- `fx fy` 两者应接近（同一像元），差异过大要警惕。

### 4. 填参数
把 8 个 `cam_*` 值抄进 `../fastlivo/camera_unitree.yaml`（`cam_width/height` 用实际分辨率）。

> 说明：脚本用 `CALIB_FIX_K3`，输出的畸变就是 `[k1, k2, p1, p2]`，正好对上
> Fast-LIVO2 pinhole 的 `cam_d0..d3`。这是标准 radtan（plumb_bob）模型。

---

## 备选路径 A2：标准棋盘格（若 AprilGrid 检测不稳）

若现场 AprilGrid 打印质量差、tag 检测数总是不足，可临时打印一张
**标准国际象棋盘**（例如 9x6 内角点，方格边长实测，如 25mm）。棋盘角点检测在 cv2 里
最稳。把 `calib_intrinsics.py` 的 tag 检测换成：
```
cv2.findChessboardCorners(gray, (9,6))  ->  cv2.cornerSubPix(...)
```
对应 objectPoints 用 `np.mgrid` 按方格边长生成，再 `cv2.calibrateCamera`。
录制要点（角度/距离/铺满四角）与路径 A 完全一致。

---

## 路径 B：装 Kalibr（可选，一般不需要）

Kalibr 内参精度更高、还能顺带做多相机/相机-IMU，但：
- Noetic 下装 Kalibr 需要 `catkin build` 一堆依赖（suitesparse、boost、ceres…），
  在 Orin 上编译较重且耗时——**本工具包不做这步，交给你决定**。
- 若要装：
  1. 用 `../aprilgrid.yaml` 作为 `--target`。
  2. `rosbag record /left_camera/image`（相机话题）录一段缓慢移动板子的包。
  3. `kalibr_calibrate_cameras --bag xxx.bag --topics /left_camera/image \
     --models pinhole-radtan --target aprilgrid.yaml`
  4. 从输出的 `-camchain.yaml` 里读 `intrinsics: [fx, fy, cx, cy]` 和
     `distortion_coeffs: [k1, k2, p1, p2]`，同样抄进 camera_unitree.yaml。

结论：**现场首选路径 A（纯 cv2 + 现成 AprilGrid）**，够用、零编译、当场出结果。
