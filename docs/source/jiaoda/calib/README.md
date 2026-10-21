# 相机-雷达标定工具包（北京交大室内履带巡检机器人）

给 Fast-LIVO2 提供：**相机内参**（fx fy cx cy + 畸变）+ **相机↔宇树L2外参**（Rcl/Pcl）。

平台：Jetson AGX Orin / ROS1 Noetic / Python3.8，板子只有 `rospy numpy cv2(4.2)`，**没有 Kalibr**。
标定板：打印的 **AprilGrid 6x6，tag=88mm**（36h11 家族）。
主雷达：宇树 L2（`/cloud` 点云 + `/imu`）。相机 4 路：`/dev/video0,2,4,6`（前视用 video0）。

铁律：本工具包**只在本地生成文件，不连板子、不代跑编译/长任务**。下面命令都由你在板子上手动执行。

---

## 文件清单

| 文件 | 作用 |
|------|------|
| `aprilgrid.yaml` | Kalibr 格式标定板定义；含**用尺子实测 tagSize/tagSpacing** 的方法 |
| `calib_intrinsics.md` | 内参标定现场步骤（首选纯 cv2 方案，含 Kalibr 备选） |
| `calib_intrinsics.py` | cv2.aruco 检测 AprilGrid + cv2.calibrateCamera，直接吐 camera_unitree 字段 |
| `grab_frames.py` | 从 /dev/videoN 抓标定图（有GUI按空格存，无GUI每1.5s自动存） |
| `calib_cam_lidar.md` | 相机↔L2 外参：首选 HKU livox_camera_calib，备选 AprilGrid 手动 PnP |
| `record_calib.sh` | 一站式：抓图 / 跑内参 / rosbag 录 img+cloud+imu / 录稠密点云 / 查话题 |
| `README.md` | 本文件，串起全流程 |

---

## 全流程（照着做）

### 第 0 步：确认标定板尺寸
打开 `aprilgrid.yaml`，按里面注释**用尺子实测** tagSize 和 tagSpacing，
和 0.088 / 0.3 对不上就改掉。尺度错会让外参平移带比例误差。

### 第 1 步：先标相机内参
```
cd ~/<本目录>            # 把这几个文件拷到板子任意目录
chmod +x record_calib.sh

./record_calib.sh topics     # 先确认话题名 /left_camera/image /cloud /imu 对不对
./record_calib.sh frames     # 抓 >=20 张，覆盖远近/倾斜/画面四角（详见 calib_intrinsics.md）
./record_calib.sh intr       # 解算，打印并写出 intrinsics_result.yaml
```
合格判据：RMS 重投影误差 `< 0.5px`，cx/cy 接近图像中心。
把 8 个 `cam_*` 值填进 `../fastlivo/camera_unitree.yaml`。

### 第 2 步：再标相机↔L2 外参
先确保内参已填好（外参标定要用）。推荐 **livox_camera_calib**（targetless）：
```
./record_calib.sh bag_dense  # 机器人静止20~40s，累积L2稠密点云（+同期抓1张图）
```
按 `calib_cam_lidar.md` 跑 livox_camera_calib，得到 R,t →
`Rcl`（行主序9数）、`Pcl`（3数）填进 `../fastlivo/camera_unitree.yaml`。
装不起来就用文档里的 **AprilGrid 手动 PnP** 兜底。

> 若要录相机+雷达+IMU 同步包（供离线复标/排查）：`./record_calib.sh bag`

### 第 3 步：开启视觉融合
参数都填好后，在 `../fastlivo/unitree_l2.yaml` 里把：
```
common:
  img_en: 0   ->   img_en: 1
```
然后 `../fastlivo/run_fastlivo.sh` 启动，rviz 里看点云是否正确上色、位姿是否稳。
上色错位/发散 → 多半是外参方向反了或内参没填对，回第 1/2 步核对（外参求逆见 calib_cam_lidar.md）。

---

## 现场需要用户配合的动作（清单）
1. 用尺子实测标定板 tagSize 与相邻 tag 间隙，确认/修正 `aprilgrid.yaml`。
2. 把 AprilGrid 平铺/贴在**硬质无翘曲**板上。
3. 抓内参图：≥20 张，覆盖远近、±20~45°倾斜、画面四角+中心，光照均匀无反光，抓时静止。
4. 外参采集：找**多直线边缘**的静态场景，机器人**完全静止 20~40s** 让 L2 累积稠密点云。
5. （若走 livox_camera_calib）在板子或一台 x86 机上**编译一次**该离线工具——本包不代跑。
6. 目视检查：点云投影叠加图边缘是否对齐、rviz 上色是否正确。
