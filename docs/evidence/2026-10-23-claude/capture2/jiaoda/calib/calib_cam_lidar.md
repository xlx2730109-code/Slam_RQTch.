# 相机 ↔ 宇树 L2 雷达 外参标定

目标：求出 Fast-LIVO2 需要的 `Rcl`（3x3，9 个数，行主序）和 `Pcl`（3x1 平移，米），
填进 `../fastlivo/camera_unitree.yaml`（当前是单位阵占位）。

## 约定（务必先搞清方向，最容易搞反）

Fast-LIVO2 里 `Rcl / Pcl` 是把 **雷达坐标系下的点变换到相机坐标系**：

```
p_camera = Rcl * p_lidar + Pcl
```

也就是 “LiDAR → Camera” 的外参（T_cl）。下面两种方法拿到结果后，
都要确认方向是不是这个；反了就求逆（见文末）。

前提：内参必须**先标好**（见 calib_intrinsics.md），外参标定要用到内参。

---

## 推荐方案：HKU livox_camera_calib（targetless，靠场景边缘）

仓库：`hku-mars/livox_camera_calib`。无靶标，靠环境里的直线边缘（门框、墙角、
桌沿、货架、管路）自动对齐点云边缘和图像边缘，一次单帧即可，精度高、现场最省事。

### 为什么适合宇树 L2
L2 是旋转/非重复扫描式，**静止一段时间能把稀疏单帧累积成稠密点云**——这正是
livox_camera_calib 需要的（它要一帧稠密有序的场景点云来提边缘）。

### 现场步骤
1. **选场景**：找一处有大量清晰直角/直线边缘的静态场景（室内墙角+门框+货架最好），
   相机能完整看到、雷达也能扫到同一片区域。避免全是平坦白墙（没边缘对不齐）。
2. **采稠密点云**：机器人**保持完全静止 20~40 秒**，用
   `record_calib.sh bag_dense` 录 `/cloud`（+`/imu`），或在板上把多帧
   `/cloud` 累加成一个稠密 pcd（工具自带累积节点也可）。
   静止是关键——动了点云会拖影，边缘就废了。
3. **同时存一张对齐时刻的相机图**（同一静止时段用 grab_frames.py 抓 1 张即可）。
4. **准备配置**：
   - 相机内参 `fx fy cx cy` + 畸变（用刚标好的值）。
   - 图像尺寸 1280x720。
   - 点云 pcd + 图像 png 路径。
5. **运行标定**（离线、只跑一次）：
   ```
   roslaunch livox_camera_calib calib.launch
   ```
   工具会做粗配准→边缘提取→非线性优化，输出 4x4 外参矩阵 / R,t，
   并给出点云投影到图像的叠加图供你目视检查（边缘对齐即成功）。

> 编译提醒：livox_camera_calib 依赖 PCL + Ceres + OpenCV，需要 `catkin_make` 编译一次。
> 本工具包**不代跑编译/不连板子**；这步由你在板子或一台 x86 机器上完成（离线工具，
> 标一次就够，不进机器人常驻服务）。若板上编译吃力，可在 x86 上编译、用同一份
> pcd+png+内参离线标定，外参结果与硬件无关，直接拿来用。

### 输出如何转成 Rcl / Pcl
livox_camera_calib 输出的外参是 **“LiDAR 点投到相机” 的变换**，即
`p_camera = R * p_lidar + t`。这与 Fast-LIVO2 的定义**一致**，直接：
- `Rcl` = 输出的 3x3 旋转 `R`，按**行主序**展平成 9 个数填入。
- `Pcl` = 输出的平移 `t`（米），3 个数填入。

务必看它给的叠加投影图：点云边缘和图像边缘重合 = 对；整体偏移/镜像 = 方向反了，按文末求逆。

---

## 备选方案：基于 AprilGrid 的手动 PnP（无需编译，纯 cv2）

思路：AprilGrid 板同时被相机和雷达“看见”，各自取同名点，PnP 解出外参。
适合 livox_camera_calib 一时装不起来、或想快速验证时用。

### 步骤
1. 把 AprilGrid 板**贴在一块平整硬板**上，竖直立在相机+雷达都能清楚看到处，
   距离 1.5~3m，让板占雷达若干个扫描点（L2 静止累积 20s 提高板面点密度）。
2. **相机侧**：抓 1 张图，用 aruco 检测 AprilGrid 得到各 tag 角点的像素坐标，
   角点对应的板面 3D 坐标由 6x6 几何已知（同 calib_intrinsics.py 的 `tag_object_corners`）。
   这些是“板坐标系”下的点。
3. **雷达侧**：把静止累积的 `/cloud` 存成 pcd，在 CloudCompare / rviz 里
   手动量出**板平面上 4 个及以上易辨认点**（如板四角）在**雷达坐标系**下的 3D 坐标。
   建议在板四角贴反光标或做角标，便于在点云里定位。
4. **解 PnP**：用第 2、3 步得到的“同一批物理点”的
   （雷达系 3D）↔（相机像素 2D + 已知内参）对应关系，`cv2.solvePnP`：
   ```
   ok, rvec, tvec = cv2.solvePnP(pts_lidar_3d, pts_img_2d, K, dist,
                                 flags=cv2.SOLVEPNP_ITERATIVE)
   R, _ = cv2.Rodrigues(rvec)
   ```
   这里 `pts_lidar_3d` 用**雷达系**坐标、`pts_img_2d` 用图像像素，
   解出的 `R, tvec` 就是 `p_camera = R * p_lidar + tvec`，即
   `Rcl = R`（行主序 9 个数）、`Pcl = tvec`（米）。
5. **验证**：把点云用 Rcl/Pcl 投影回图像，看板角/边缘是否落在图上对应位置。
   误差大就多取几组同名点、换更易辨认的角标重解。

> 手动 PnP 精度取决于你在点云里点同名点的准度，一般不如 livox_camera_calib；
> 优先用推荐方案，PnP 作为兜底/交叉验证。

---

## 方向搞反了怎么办（求逆）

若验证发现投影整体错位、且怀疑外参是 “Camera → LiDAR”（T_lc）而非需要的 T_cl，
取逆即可：

```
Rcl = R_lc^T
Pcl = - R_lc^T * t_lc
```

填完后到 `../fastlivo/camera_unitree.yaml`，`Rcl` 写 9 个数（行主序），`Pcl` 写 3 个数。
`extrinsic_R / extrinsic_T`（IMU↔LiDAR）保持单位阵/0（L2 内部已对齐 IMU 与雷达），不用动。
