# 消防巡检机器人 · Jetson SLAM/导航系统开发手册

> 目的：**换一台电脑、断开本次会话，只靠这份文件也能把整套系统复现出来并继续开发**。
> 适用设备：NVIDIA Jetson AGX Orin Developer Kit，主机名 `sjytt-desktop`，用户 `sjytt`。
> 本文所有结论均来自 2026-10-21 的只读实测（命令、日志、`/proc`、话题频率），少数推断已在文中注明。
> 源码/配置原件已导出到 [`docs/source/`](docs/source/)，配合第 14 章可从零重建。

**目录**：[0 现状](#0-当前状态速览先看这个) · [1 上手](#1-十分钟上手) · [2 总览](#2-系统总览) · [3 拓扑](#3-运行时拓扑) · [4 启动](#4-启动机制与恢复) · [5 SLAM](#5-slamfast-livo2--宇树-l2) · [6 导航](#6-导航nav_simplepy-v8) · [7 底盘](#7-底盘与云台) · [8 视觉](#8-视觉) · [9 网页](#9-web-控制台8090) · [10 数据](#10-数据资产与备份) · [11 开发](#11-二次开发指南) · [12 排障](#12-故障速查表) · [13 问题](#13-已知问题清单按优先级) · [14 复现](#14-从零复现换一台新-jetson-也能重建) · [15 重做](#15-如果重做一个更好的架构建议)

---

## 0. 当前状态速览（先看这个）

> **2026-10-21 13:30 更新**：三个 P0 已修复并验证，系统现在是真的闭环了。修复前的故障态见 0.1。

| 子系统 | 状态 | 证据（2026-10-21 13:30 实测） |
| --- | --- | --- |
| 宇树 L2 雷达 | ✅ 正常 | `/unilidar/cloud` 11.94 Hz，`/unilidar/imu` 252.8 Hz |
| 点云转发 | ✅ 正常 | `/synced/cloud` 11.97 Hz |
| 相机发布 | ✅ 已恢复 | `/left_camera/image` **14.98 Hz**，`/dev/video3` |
| FAST-LIVO2 | ✅ 已恢复 | `/aft_mapped_to_init` **11.96 Hz**，VIO 特征点 1755 |
| 定位 `/slam_pose` | ✅ 已恢复 | 与 SLAM 同频；`/api/pose` 实时变化 |
| 2D 建图 | ✅ 已恢复 | `/map` 1 Hz 且内容持续更新（PNG 哈希变化） |
| 导航 `nav_simple` | ✅ 就绪 | 定位输入正常；无目标时不发 `cmd_vel`（符合设计） |
| 底盘串口 | ✅ 已接通 | `serial opened: /dev/ttyACM0 @115200`，`/jiaoda/esp_tel` 9.96 Hz 回传 `GIMBAL_PULSE:1500,1500` |
| 网页控制台 8090 | ✅ 可访问 | HTTP 200，地图与位姿均为实时 |
| 标定页 8095 | ⛔ 未启用 | `jiaoda-calib` 为 disabled（按需启用） |
| 巡检任务 | ✅ 已修复 | `jiaoda-mission` active，不再崩溃重启 |
| 视觉-雷达外参 | ✅ 已验证 | `Rcl` 90° + `Pcl` 0；点云投影精确贴合地面与墙面（`docs/extr-check-overlay.jpg`） |

**一句话**：软件栈完整可用，外参也验证过是准的——这套系统现在是真能干活的状态。

### 0.1 2026-10-21 13:27–13:30 修复记录

| # | 问题 | 改动 | 验证 |
| --- | --- | --- | --- |
| 1 | 相机索引失效且不重连 | 重写 `cam_publisher.py`：`by-path`/索引双模式、2 s 重试、连续 10 帧失败自动重开、手动编码 `bgr8` 去掉 `cv_bridge` 依赖；`run_campub.sh` 改 `CAMPUB_INDEX=3` | 14.98 Hz，fd → `/dev/video3` ✓ |
| 2 | `nav_mission` 崩溃循环 | 第 7/8 行对调，`import cv2` 提到 `cv_bridge` 之前 | `active`，重启计数不再增长 ✓ |
| 3 | 底盘串口名错位 | `CTL_PORT` 默认改 `/dev/ttyACM0`；打开前把 DTR/RTS 置低，避免每次启动复位 ESP32 | `serial opened`，遥测 9.96 Hz ✓ |

备份：`~/backup/jiaoda-before-fix-1021-1327.tar.gz`。修复后的源码已同步到 [`docs/source/jiaoda/`](docs/source/jiaoda/)。

> 修复前的状态（保留作对照）：相机进程持有 `/dev/video2 (deleted)` → 图像 0 Hz → SLAM 全部输出静默 → 导航空转、网页显示冻结快照、任务服务崩溃循环 1800+ 次。

---

## 1. 十分钟上手

### 1.1 怎么连上去

| 方式 | 地址 | 说明 |
| --- | --- | --- |
| **USB（首选）** | `ssh sjytt@192.168.55.1` | Jetson 的 `l4tbr0` 网桥，本机 USB 网卡 `192.168.55.100/24`，已配置 ed25519 免密，`ping` < 1 ms |
| **Wi-Fi（跑车时用）** | `ssh sjytt@172.20.10.14`（固定）<br>`172.20.10.8`（DHCP，会变） | 热点 `xlx`，网段 `172.20.10.0/28`（**只有 .1–.14**）；`wlan0` 同时持有 DHCP 地址和固定地址 `.14`，固定地址已写入 NetworkManager，重启后仍在 |
| 以太网 | `eth1 = 192.168.1.2`、`eth0` 无 IP | 雷达专用网段，别在上面乱加地址（见 12.3） |

> Windows 上如果浏览器打不开 `192.168.55.1:8090`，通常是本机 Clash 代理劫持了内网请求。用 `ssh -L 8090:127.0.0.1:8090 sjytt@192.168.55.1` 建隧道后访问 `http://127.0.0.1:8090` 即可（`127.*` 在代理绕过列表里）。

### 1.2 30 秒健康检查

```bash
# 1) 服务全不全
systemctl list-units 'jiaoda*' --all --no-legend

# 2) ROS 节点
source /opt/ros/noetic/setup.bash
rosnode list

# 3) 雷达有没有数据（应约 12 Hz）
timeout 4 rostopic hz /unilidar/cloud

# 4) SLAM 有没有输出（当前会"no new messages"）
timeout 4 rostopic hz /aft_mapped_to_init

# 5) 相机有没有出图（当前会"no new messages"）
timeout 4 rostopic hz /left_camera/image

# 6) 网页与位姿
curl -s http://127.0.0.1:8090/api/pose
```

判读：3 有、4/5 无 = 当前已知故障（相机链路断，见 8.2）。4/5 都有 = 系统健康。

### 1.3 重启整套栈

系统用 systemd 托管，逐个重启即可，**不需要 `roslaunch` 手工起**：

```bash
sudo systemctl restart jiaoda-lidar        # 它会顺带拉起 ROS Master（见 4.3）
sudo systemctl restart jiaoda-restamp
sudo systemctl restart jiaoda-campub
sudo systemctl restart jiaoda-fastlivo
sudo systemctl restart jiaoda-grid
sudo systemctl restart jiaoda-posebridge
sudo systemctl restart jiaoda-nav
sudo systemctl restart jiaoda-control
sudo systemctl restart jiaoda-console
```

顺序很重要：下游脚本都以 `until rostopic list`、`until rostopic list | grep <topic>` 作为前置等待，乱序也不会崩，但会多等几秒。

### 1.4 打开网页

`http://192.168.55.1:8090/`（或隧道后的 `http://127.0.0.1:8090/`），标题「巡检机器人控制台」。

---

## 2. 系统总览

| 项 | 值 |
| --- | --- |
| 计算平台 | Jetson AGX Orin Developer Kit（`t186ref`） |
| 系统 | Ubuntu 20.04.6 LTS，aarch64，Jetson Linux / L4T **R35.4.1** |
| 内核 | `5.10.120-tegra` |
| 内存 / 磁盘 | 61 GiB（用 14 GiB）／ `/` 57 G（用 11 G，19%） |
| ROS | **Noetic**，`/opt/ros/noetic`，`ROS_MASTER_URI=http://localhost:11311` |
| Python | 3.8.10；`numpy 1.17.4`；`cv2 4.2.0`；`cv_bridge` 有导入顺序坑（见 12.5） |
| 主代码 | `/home/sjytt/jiaoda`（**无 Git**，需自行备份） |
| SLAM 工作区 | `/home/sjytt/livo2_ws`（catkin：`FAST-LIVO2`、`rpg_vikit`） |
| 雷达工作区 | `/home/sjytt/unilidar_sdk2/unitree_lidar_ros`（catkin） |
| 备份/旧版 | `/home/sjytt/dog_backup`、`/home/sjytt/unilidar_sdk`（第一代） |
| 日志 | `/home/sjytt/.ros/log/`（约 90 MB） |

### 2.1 硬件连接（实测）

| 设备 | 接口 | 标识 | 节点 |
| --- | --- | --- | --- |
| 宇树 L2 雷达 | `eth1` 192.168.1.2 | 雷达 192.168.1.62:6101 → PC 6201 | `/unilidar/*` |
| ESP32 主控 | USB `1-4.3` | WCH **CH343** `1a86:55d3`，SN `5B14050145` | `/dev/ttyACM0` |
| ESP32 调试口 | USB `1-4.4` | Espressif `303a:1001`，SN `E8:F6:0A:85:8F:04` | `/dev/ttyACM1` |
| 4 路 UVC 相机 | USB `1-4.2.x` | Sonix `0c45:6366`，四台序列号均为 `SN0001` | `/dev/video0…8` |
| USB 网卡 | USB `1-4.1` | `1a86:5397`，MAC `6c:1f:f7:eb:48:3f` | `eth0`（无 IP） |

---

## 3. 运行时拓扑

### 3.1 进程与单元（10 个运行中 + 2 个已禁用）

| systemd 单元 | 启动脚本 | 程序 | 作用 | enabled |
| --- | --- | --- | --- | --- |
| `jiaoda-lidar` | `run_lidar.sh` | `roslaunch unitree_lidar_ros run_without_rviz.launch` | 雷达驱动，**并顺带启动 ROS Master** | ✅ |
| `jiaoda-restamp` | `run_restamp.sh` | `cloud_restamp.py` | 点云时间戳改写为 `now()` → `/synced/cloud` | ✅ |
| `jiaoda-campub` | `run_campub.sh` | `cam_publisher.py` | 相机 → `/left_camera/image` | ✅ |
| `jiaoda-fastlivo` | `run_fastlivo.sh` | `roslaunch fast_livo mapping_unitree_l2.launch rviz:=false` | SLAM 主程序 `laserMapping` | ✅ |
| `jiaoda-grid` | `run_grid.sh` | `grid_bridge.py` | 点云 → 2D 栅格 → `/map` + PNG | ✅ |
| `jiaoda-posebridge` | `run_pose_bridge.sh` | `pose_bridge.py` | `/aft_mapped_to_init` → `/slam_pose` + `/imu` | ✅ |
| `jiaoda-nav` | `run_nav_simple.sh` | `nav_simple.py` | A\* + Pure Pursuit + DWA → `/cmd_vel` | ✅ |
| `jiaoda-control` | `run_control.sh` | `chassis_gimbal_bridge.py` | `/cmd_vel` + 云台 → 串口帧 | ✅ |
| `jiaoda-console` | `run.sh` | `console_backend.py` | 网页后端 8090 | ✅ |
| `jiaoda-mission` | `run_mission.sh` | `nav_mission.py` | 巡检任务调度 | ✅（崩溃循环） |
| `jiaoda-chassis` | `run_chassis.sh` | `cmd_vel_to_pwm.py` | **旧版**底盘直驱（协议不符） | ⛔ disabled |
| `jiaoda-calib` | `run_calib.sh` | `calib/calib_web.py` | 相机-雷达标定页 8095 | ⛔ disabled |

> `jiaoda-chassis` 与 `jiaoda-control` 是两套互斥实现，同开会抢同一个串口。当前只启用后者。

### 3.2 节点表（10 个）

| 节点 | 订阅 | 发布 |
| --- | --- | --- |
| `/unitree_lidar_ros_node` | — | `/unilidar/cloud`、`/unilidar/imu`、`/unilidar/laserscan`、`/tf` |
| `/cloud_restamp` | `/unilidar/cloud` | `/synced/cloud` |
| `/cam_publisher` | — | `/left_camera/image` |
| `/laserMapping`（FAST-LIVO2） | `/synced/cloud`、`/unilidar/imu`、`/left_camera/image` | `/aft_mapped_to_init`、`/cloud_registered`、`/Laser_map`、`/path`、`/rgb_img`、`/tf` 等 20+ 个 |
| `/pose_bridge` | `/aft_mapped_to_init` | `/slam_pose`、`/imu` |
| `/grid_bridge` | `/cloud_registered`、`/aft_mapped_to_init` | `/map` |
| `/nav_simple` | `/slam_pose`、`/imu`、`/map`、`/unilidar/cloud`、`/move_base_simple/goal`、`/move_base/cancel` | `/cmd_vel`、`/nav_path` |
| `/chassis_gimbal_bridge` | `/cmd_vel`、`/jiaoda/gimbal` | `/jiaoda/esp_tel` |
| `/console_backend` | `/aft_mapped_to_init`、`/Odometry`、`/lio_sam/mapping/odometry` | `/cmd_vel`、`/jiaoda/gimbal` |
| `/nav_mission` | —（启动即崩） | 计划：`/move_base_simple/goal`、`/jiaoda/gimbal` |

### 3.3 关键话题与实测频率

| 话题 | 类型 | 发布者 | 实测 |
| --- | --- | --- | --- |
| `/unilidar/cloud` | `PointCloud2` | 雷达驱动 | **11.94 Hz** ✅ |
| `/unilidar/imu` | `Imu` | 雷达驱动 | **252.8 Hz** ✅ |
| `/synced/cloud` | `PointCloud2` | cloud_restamp | **11.97 Hz** ✅ |
| `/aft_mapped_to_init` | `Odometry` | laserMapping | **0**（发布者注册但无消息）❌ |
| `/slam_pose` | `PoseStamped` | pose_bridge | **0** ❌ |
| `/cloud_registered` | `PointCloud2` | laserMapping | **0** ❌ |
| `/Laser_map` | `PointCloud2` | laserMapping | **0** ❌ |
| `/map` | `OccupancyGrid` | grid_bridge | 1.1 Hz，内容**不变**（冻结）⚠️ |
| `/left_camera/image` | `Image` | cam_publisher | **0** ❌ |
| `/cmd_vel` | `Twist` | nav_simple / console | 15.9 Hz，**全为 0** ⚠️ |
| `/jiaoda/esp_tel` | `String` | chassis_gimbal_bridge | 0（串口未开）❌ |
| `/Odometry`、`/lio_sam/mapping/odometry` | `Odometry` | **无** | 死订阅（console 在等）❌ |
| `/move_base_simple/goal`、`/move_base/cancel` | — | **无**（nav_mission 崩了） | nav_simple 收不到目标 ⛔ |

### 3.4 服务与 TF

- **没有任何自定义 ROS service**（全目录无 `rospy.Service`）。跨进程接口只有：话题 + `/dev/shm` 文件 + HTTP。
- TF 只有雷达自家人：`unilidar_imu_initial → unilidar_imu → unilidar_lidar`，约 510 Hz。
- **没有** `map → odom → base_link`，也**没有**相机坐标系。导航不依赖 TF，直接用 `/slam_pose` 的坐标值 + `/imu` 的 yaw。

---

## 4. 启动机制与恢复

### 4.1 谁启动 ROS Master

`jiaoda-lidar` 的 `roslaunch` 是第一个起来的，它**顺带创建了 `rosmaster`（PID 2209，端口 11311）和 `rosout`**。其余单元的脚本都会先阻塞等待 `rostopic list` 可用。

> 含义：**雷达单元是整套系统的事实上的入口**。它挂了，Master 就没了，后面全部起不来。

### 4.2 启动脚本的等待逻辑

```bash
# run_lidar.sh：直接起
# run_restamp.sh：等 master，再等 /unilidar/cloud 出现
# run_fastlivo.sh：等 /synced/cloud 出现（只等话题存在，不等数据）
# run_grid.sh：等 /cloud_registered 出现
# 其余：等 master
```

⚠️ 因为只是「等话题名出现」，所以**相机没数据、SLAM 不出结果，这些服务照样会"成功"启动**——这正是当前故障能长期隐藏的原因。

### 4.3 开机行为

12 个单元里 10 个 enabled，**开机会自动拉起整套栈**。实测时间线（monotonic）：

| 时刻 | 事件 |
| --- | --- |
| +15 s | 10 个 `jiaoda-*` 服务全部被拉起 |
| +17 s | ROS Master `:11311` 就绪 |
| +22 s | `jiaoda-fastlivo` 完成等待并启动 |

`jiaoda-calib`、`jiaoda-chassis` 为 disabled。`crontab`、`~/.config/autostart`、`/etc/rc.local` 均无相关配置，`.bashrc` 只 source 环境。

服务进程内的 ROS 环境：`ROS_MASTER_URI=http://localhost:11311`，`ROS_IP`/`ROS_HOSTNAME` **未设置**（单机运行没问题，多机联调时必须补）。

### 4.4 冷启动恢复清单（从"什么都没跑"开始）

```bash
sudo systemctl start jiaoda-lidar       # 含 ROS Master
sudo systemctl start jiaoda-restamp
sudo systemctl start jiaoda-campub
sudo systemctl start jiaoda-fastlivo
sudo systemctl start jiaoda-grid
sudo systemctl start jiaoda-posebridge
sudo systemctl start jiaoda-nav
sudo systemctl start jiaoda-control
sudo systemctl start jiaoda-console
# 任务调度待修好 cv_bridge 后再启
# sudo systemctl start jiaoda-mission
```

### 4.5 时钟陷阱（排障必读）

Jetson 的 RTC 在断电后不保持，**开机瞬间系统时间会回到上次关机时刻**，NTP 同步后才跳到正确时间。本次实测：

- 开机时系统时间为 `2026-09-10 17:12`（比真实时间早 **40 天 17.5 小时**）；
- `2026-10-21 11:32:46` 由 timesyncd 校正到真实时间（日志 `Initial synchronization to time server ...`）。

后果：`/home/sjytt/.ros/log/` 里今天产生的日志**时间戳写着 9 月 10 日**，`ps` 的 `lstart` 也会前后不一致。判断进程新旧请看 `etime`（已运行时长），不要看日志日期。日志目录约 89 MB 且**无轮转**，长期运行需自行清理。

---

## 5. SLAM（FAST-LIVO2 + 宇树 L2）

### 5.1 数据流

```
雷达 L2 (192.168.1.62:6101) ──UDP──> unitree_lidar_ros_node ──> /unilidar/cloud (11.9Hz)
                                                             └─> /unilidar/imu (253Hz)
                                                                     │
                                            cloud_restamp ──> /synced/cloud (时间戳改为 now())
                                                                     │
相机 /dev/video? ──cam_publisher──> /left_camera/image ──────────────┤
                                                                     ▼
                                                          FAST-LIVO2 (/laserMapping)
                                                                     │
              ┌──────────────────────────────────────────────────────┼─────────────────────┐
              ▼                        ▼                             ▼                     ▼
    /aft_mapped_to_init        /cloud_registered              /Laser_map              /rgb_img
              │                        │
      pose_bridge                 grid_bridge ──> /map (0.05 m, 2000×2000)
              │
     /slam_pose + /imu ──> nav_simple ──> /cmd_vel ──> chassis_gimbal_bridge ──> 串口
```

### 5.2 参数（`/home/sjytt/livo2_ws/src/FAST-LIVO2/config/unitree_l2.yaml`）

| 组 | 参数 | 值 | 说明 |
| --- | --- | --- | --- |
| common | `img_topic` | `/left_camera/image` | 图像输入 |
| | `lid_topic` | `/synced/cloud` | 点云输入 |
| | `imu_topic` | `/unilidar/imu` | IMU 输入 |
| | `img_en` | **1** | **必须为 1**，缺图像则整条链路不出结果 |
| extrin_calib | `extrinsic_T` | `[-0.007698, -0.014655, 0.00667]` m | 雷达-IMU 平移 |
| | `extrinsic_R` | 单位阵 | 雷达-IMU 旋转 |
| | `Rcl` / `Pcl` | 90° 旋转 / 原点 | 相机-雷达外参 |
| preprocess | `lidar_type` | 2 | 宇树 L2 |
| | `scan_line` | 18 | 线数 |
| | `blind` | 0.5 m | 盲区 |
| lio | `voxel_size` | 0.5 m | 体素降采样 |
| | `max_layer` / `max_points_num` | 2 / 50 | 分层与点数 |
| vio | `patch_size` / `patch_pyrimid_level` | 8 / 4 | 光度块 |
| | `outlier_threshold` | 1000 | 外点阈值 |
| local_map | `map_sliding_en` | false | 不滑窗，全局地图 |
| pcd_save | `pcd_save_en` | false | **不落盘 PCD** |

相机内参（`config/camera_unitree.yaml`）：`1280×720`，`scale: 0.5`，`fx=fy=914.0`，`cx=640.0`，`cy=360.0`，畸变全 0。

### 5.3 雷达驱动配置（`unilidar_sdk2/unitree_lidar_ros/src/unitree_lidar_ros/config/config.yaml`）

| 项 | 值 |
| --- | --- |
| `initialize_type` | 2 = **UDP 模式** |
| `lidar_ip` / `lidar_port` | 192.168.1.62 / 6101 |
| `pc_ip` / `pc_port` | 192.168.1.2 / 6201 |
| `cloud_scan_num` | 18 |
| `cloud_frame` / `imu_frame` | `unilidar_lidar` / `unilidar_imu` |
| `serial_port` / `baudrate` | `/dev/ttyACM0` / 4000000 ⚠️ **仅在串口模式生效；这个端口正是 ESP32 主控口，切勿把 `initialize_type` 改成 1** |

### 5.4 输出含义

| 话题 | 用途 |
| --- | --- |
| `/aft_mapped_to_init` | **位姿真值**，nav_simple 的定位来源（经 pose_bridge） |
| `/cloud_registered` | 世界坐标系点云，grid_bridge 用它建 2D 图 |
| `/Laser_map` | 累积地图点云 |
| `/path` | 轨迹 |
| `/rgb_img` | 回投影图像（由 laserMapping 自己发布，不是相机直出） |

### 5.5 当前故障：为什么"有进程没输出"

1. 开机时相机以旧编号枚举（含 `video2`），`cam_publisher` 打开 `video2` 成功；
2. 时钟校正前的 `17:36:58`（真实约 11:07），内核连续 10 条 `uvcvideo: Failed to resubmit video URB (-19)`——旧设备掉线（-19 = ENODEV）；
3. `17:49:00`（真实约 11:20）四路相机重新枚举（`usb 1-4.2.x: New USB device found, idVendor=0c45`），节点号变成 `0,1,3,4,5,6,7,8`，**`video2` 不复存在**；
4. `cam_publisher` **不重连**，fd 一直指向 `/dev/video2 (deleted)`，`cap.read()` 永远失败；
5. `img_en=1` 的 FAST-LIVO2 收不到图像 → 不进入建图循环 → 所有输出话题沉默；
6. 下游全部拿到"空输入"，`nav_simple` 只能 20 Hz 发零速保平安。

**验证命令**：`ls -l /proc/1094/fd | grep video` → `10 -> /dev/video2 (deleted)`。

> 注意日志时间戳是时钟校正前的（9 月 10 日），对应真实时间是 11:07 / 11:20。

---

## 6. 导航（`nav_simple.py` v8）

自研导航栈，**不用 move_base**。473 行。

### 6.1 算法

```
收到目标点 → A* 全局规划（一次，不重规划）
     ↓ 20 Hz 控制循环
Pure Pursuit：沿路径找前方 0.8 m 的 lookahead 点
DWA：采样 5×11 组 (vx, vyaw)，2 s 前向预测，激光碰撞检测，按 4 项权重打分
     ↓
发布 /cmd_vel
```

### 6.2 参数（源码常量）

| 参数 | 值 | 含义 |
| --- | --- | --- |
| `VX_MAX` / `VX_MIN` | 1.0 / 0.5 m/s | **不允许后退**，最低 0.5 |
| `VYAW_MAX` | 0.8 rad/s | 最大角速度 |
| `LOOKAHEAD_DIST` | 0.8 m | 前视距离 |
| `DWA_*_SAMPLES` | 5 × 11 | vx / vyaw 采样 |
| `DWA_PREDICT_T` / `DWA_DT` | 2.0 s / 0.1 s | 预测时长与步长 |
| `DWA_W_HEAD/DIST/VX/OBST` | 1.5 / 1.0 / 0.3 / 30.0 | 评分权重（避障权重最大） |
| `ROBOT_RADIUS` / `SAFE_DIST` | 0.5 m / 0.7 m | 车体半径与安全距离 |
| `ARRIVE_FINAL` | 0.30 m | 到点判定 |
| `INVERT_YAW` | True | **转向反装标志**，换主控后若原地打转就改这里 |
| `INFLATE_RADIUS` / `PATH_SIMPLIFY` | 0.5 m / 4 | 地图膨胀与路径简化 |
| `WD_S` / `HZ` | 1.5 s / 20 Hz | 看门狗与频率 |

### 6.3 接口

- 输入：`/slam_pose`（位置）、`/imu`（yaw）、`/map`（A\* 用）、`/unilidar/cloud`（DWA 避障，只取 6 m 内、z∈(-0.3,1.0)、剔除车身矩形）、`/move_base_simple/goal`、`/move_base/cancel`
- 输出：`/cmd_vel`、`/nav_path`（当前**无人订阅**）

### 6.4 安全逻辑

- 位姿或 IMU 超过 1.5 s 未更新 → 发零速；
- 到点 0.3 m 内 → 强制零速并清状态；进入 0.8 m 缓速区改走简单比例控制（0.10–0.20 m/s）；
- DWA 全碰撞 → 原地转向脱困。

### 6.5 怎么让它动

目前唯一的入口 `/move_base_simple/goal` **没有发布者**（原设计由 `nav_mission` 发，而它崩了）。手工测试：

```bash
rostopic pub -1 /move_base_simple/goal geometry_msgs/PoseStamped \
'{header: {frame_id: "map"}, pose: {position: {x: 2.0, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}'
```

⚠️ 前提：定位必须先是活的（当前不是），且底盘必须已接通。**在轮子离地前不要执行。**

### 6.6 地图格式

`/map`：`OccupancyGrid`，分辨率 **0.05 m**，**2000×2000**，原点 `(-50, -50)`，`frame_id=map`，取值 `-1/0/100`。
落盘：`~/jiaoda/maps/floor1.npz`（`log_odds` float32 2000×2000 + `size` + `res`）；网页用图 `/dev/shm/jiaoda_map.png`。

---

## 7. 底盘与云台

### 7.1 链路

```
/cmd_vel (Twist) ─┐
                  ├─> chassis_gimbal_bridge ─> 串口 "/dev/ttyACM0" @115200 ─> ESP32 主控
/jiaoda/gimbal ───┘        20 Hz, 5 字段帧                    ↑
                                                    /jiaoda/esp_tel（回传遥测）
```

### 7.2 串口协议（与固件自述一致）

- 下行：`"%d,%d,%d,%d,%d\n"` = `throttle,steer,pitch,yaw,checksum`，取值限幅 **±30**，**20 Hz**；`checksum` 目前是四者直接相加（未取模，见 13.3）。
- 换算：`throttle = clamp(linear.x × 55)`，`steer = clamp(angular.z × 45)`。
- 看门狗：`/cmd_vel` 超过 **0.5 s** 没更新 → 自动清零。
- 上行：任意文本行 → `/jiaoda/esp_tel`（当前无人订阅）。

### 7.3 固件行为（只读读取得知）

```
=== Fire Inspection Robot Control System ===
RC Mapping: CH1=Steer, CH2=Throttle, CH3=Pitch, CH4=Yaw
Serial Format: throttle,steer,pitch,yaw,checksum
Priority: RC > Serial
```

- **`Priority: RC > Serial`**：遥控器有信号时，串口指令被完全忽略。联调前必须先关遥控器。
- **怎么判断它现在收不收串口**：固件每收一帧合法指令都会回一行 `Serial T:x S:y P:x Y:y`。若发 `/cmd_vel` 后 `/jiaoda/esp_tel` 里**没有**这行，就是还在 RC 模式（2026-10-21 实测就是这种情况：发了 1.5 s 的 0.08 m/s，车没动，回显 0 行）。
- **⚠️ 固件 bug：拔掉接收机后必须重启主控才会切模式。** `pulseWidths[]` 只在下沿中断里更新，信号消失后**保留最后一次的值**；`isRCActive()` 只看数值范围，所以会一直返回 true，永远不进 `RC Signal Lost` 分支。实测：拔接收机后不重启，仍然 0 回显；**给 ESP32 复位一次**后，开机日志里不再出现 `Mode: RC Control`，串口立即生效（实测 `Serial T:16` 正常回显）。
- **复位主控的正确姿势**：给 `RTS` 一个脉冲（`p.rts=True; sleep(0.15); p.rts=False`）是正常复位；单独拉 `DTR` 会把它打进 **DOWNLOAD 模式**（日志 `boot:0x23 (DOWNLOAD(USB/UART0))` + `waiting for download`），这时固件不跑，需要再用 RTS 复位一次。
- 自报 `GIMBAL_PULSE:1500,1500`（约 20 Hz），云台中位。
- **打开串口会因 DTR→EN 让 ESP32 复位一次**，属正常现象，不是故障。

### 7.4 急停

网页「急停」按钮 → `POST /api/nav/cancel` + `POST /api/ctl/drive {v:0,w:0}`。
物理层最可靠的手段仍是**断电**或关遥控器。软件急停依赖串口链路，而该链路当前是断的。

---

## 8. 视觉

### 8.1 四路相机映射（实测抓帧确认）

| USB 口 | 节点 | 占用者 | 画面 |
| --- | --- | --- | --- |
| `1-4.2.2` | `video0/1` | console（按需打开） | 走廊「安全出口」方向 |
| `1-4.2.1.3` | `video3/4` | 空闲 | 长走廊 + 蓝色展板，视角最低最广 |
| `1-4.2.3` | `video5/6` | 空闲 | 棕色木门特写，视野窄 |
| `1-4.2.4` | `video7/8` | 空闲 | 工位前用笔记本的人 |

四台全是**同型号 RGB**（`0c45:6366`，2592×1944 MJPG，序列号同为 `SN0001`），**没有热成像、没有深度相机**。`/dev/v4l/by-id` 因序列号冲突只有一个条目，稳定映射只能用 `by-path`。

### 8.2 `cam_publisher` 的缺陷（2026-10-21 已修复）

**修复前**（保留说明故障原理）：

```python
IDX = int(os.environ.get("CAMPUB_INDEX", "2"))   # 第 6 行：写死 2
cap = cv2.VideoCapture(IDX, cv2.CAP_V4L2)        # 第 13 行：只打开一次，永不重开
```

设备重新枚举后 `video2` 消失，进程不重连、不报错、不打日志，话题有发布者但零数据。

**修复后**（现版本）：

- 支持 `CAMPUB_DEV`（稳定 by-path）/`CAMPUB_INDEX` 双模式，当前 `CAMPUB_INDEX=3`；
- 打不开就每 2 s 重试；连续 10 帧读失败自动 `release()` 重开；
- 手动填 `sensor_msgs/Image`（`bgr8`），**不再 import `cv_bridge`**，绕开导入顺序坑；
- 分辨率/帧率可用 `CAMPUB_W/H/FPS` 覆盖。

复现方式见 [`docs/source/jiaoda/cam_publisher.py`](docs/source/jiaoda/cam_publisher.py)。原版备份在 `~/backup/jiaoda-before-fix-1021-1327.tar.gz`。

### 8.3 标定页 8095

代码在 `~/jiaoda/calib/calib_web.py`（`CALIB_PORT` 默认 8095），启动脚本 `run_calib.sh`（`CALIB_CAM=2`，同样指向已消失的 video2）。对应单元 `jiaoda-calib` 为 disabled。启用方式：`sudo systemctl enable --now jiaoda-calib`。

⚠️ 该页的 `/saveextr` 会**直接覆写** `unitree_l2.yaml` 且不备份。

---

## 9. Web 控制台（8090）

- 后端：`console_backend.py`（304 行，`ThreadingHTTPServer`，监听 `0.0.0.0:8090`，**无鉴权**）
- 前端：同目录 `console.html`（单文件，约 28 KB，「巡检机器人控制台」）
- 摄像头流：按需打开 `video0`，输出 MJPEG 到 `/api/cam/stream.mjpg`

### 9.1 HTTP API

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/pose` | 当前位姿（来自 `/aft_mapped_to_init` 等三选一） |
| GET | `/api/ctl/status` | 电量、温度、雷达 hz、导航状态 |
| GET | `/api/mapinfo` | 地图元信息 `{x0,y0top,mpp,w,h}` |
| GET | `/api/map` | 地图 PNG（读 `/dev/shm/jiaoda_map.png`） |
| GET | `/api/cam/stream.mjpg` | MJPEG 视频流 |
| GET | `/api/nav/status` | 任务状态（读 `/dev/shm/jiaoda_nav_status.json`） |
| POST | `/api/ctl/drive` | 直接给速度 **（无限幅，注意）** |
| POST | `/api/ctl/param` | 调参（`pspeed/pyaw/pclear/pstop`，其中后两个未被真正使用） |
| POST | `/api/ctl/calib_heading` | 航向标定（空实现） |
| POST | `/api/gimbal` | 云台 |
| POST | `/api/nav/start` | 开始巡检（写 `/dev/shm/jiaoda_mission.json`，但**无人消费**） |
| POST | `/api/nav/cancel` | 取消 |
| POST | `/api/route/save`、`/api/route/load` | 路线存取（`~/jiaoda/routes`） |
| POST | `/api/map/save`、`/api/map/load`、`/api/map/clear` | 地图存取（`~/jiaoda/maps`） |

### 9.2 跨进程 `/dev/shm` 契约（隐式 API）

| 文件 | 生产者 | 消费者 |
| --- | --- | --- |
| `jiaoda_map.png` / `jiaoda_map.json` | grid_bridge | 网页地图 |
| `jiaoda_sensors.json` | chassis_bridge（未运行） | 网页电量（**恒空**） |
| `jiaoda_nav_status.json` | nav_mission（崩） | 网页任务状态（**恒 idle**） |
| `jiaoda_mission.json` / `jiaoda_nav_cmd` | 网页 | nav_mission |
| `jiaoda_map_save` / `_load` / `_clear` | 网页 | grid_bridge |

> 这些文件无锁、无版本号。**二次开发替换节点时必须保持文件名与字段名不变。**

---

## 10. 数据资产与备份

| 路径 | 内容 | 备注 |
| --- | --- | --- |
| `~/jiaoda` | 主代码（2234 行 Python） | **无 Git**，改前先 `tar` 备份 |
| `~/jiaoda/maps/floor1.npz` | 2D 地图（log_odds 2000×2000） | 22 KB |
| `~/jiaoda/routes/` | 巡检路线 JSON | 目前为空 |
| `~/jiaoda/photos/` | 巡检拍照 | **尚未创建**（mission 崩溃） |
| `~/.ros/log/` | 各节点日志 | 约 90 MB，时间戳受 4.5 影响 |
| `~/livo2_ws` | FAST-LIVO2 + rpg_vikit 源码与构建产物 | 最近构建 2026-09-10 12:22 |
| `~/unilidar_sdk2` | 雷达 SDK | 可执行文件构建于 2026-06-18 |

---

## 11. 二次开发指南

### 11.1 改代码的完整流程

```bash
tar czf ~/jiaoda-$(date +%m%d-%H%M).tar.gz ~/jiaoda      # 1. 备份
vim ~/jiaoda/xxx.py                                      # 2. 改
python3 -m py_compile ~/jiaoda/xxx.py                    # 3. 语法检查
sudo systemctl restart jiaoda-<对应单元>                  # 4. 重启单个服务
journalctl -u jiaoda-<单元> -f                           # 5. 看日志
```

### 11.2 改 SLAM 需要重新编译

```bash
cd ~/livo2_ws
catkin_make -j4          # 或 catkin build fast_livo
source devel/setup.bash
sudo systemctl restart jiaoda-fastlivo
```

改参数（yaml）不用编译，直接重启 `jiaoda-fastlivo` 即可。

当前构建产物时间：`livo2_ws/devel/lib/fast_livo/fastlivo_mapping` = 2026-09-10 12:22；`unilidar_sdk2/.../unitree_lidar_ros_node` = 2026-06-18 16:48。`devel/.catkin` 标记存在，支持增量构建。

### 11.3 加一个新节点

```bash
# 1) 写 ~/jiaoda/my_node.py（记得 source /opt/ros/noetic/setup.bash）
# 2) 加执行权限 chmod +x
# 3) 复制一个 unit 模板：
sudo cp /etc/systemd/system/jiaoda-nav.service /etc/systemd/system/jiaoda-mynode.service
# 4) 改 Description / ExecStart / After
sudo systemctl daemon-reload && sudo systemctl enable --now jiaoda-mynode
```

### 11.4 调试技巧

- 看谁在发：`rostopic info /话题`
- 看频率：`timeout 4 rostopic hz /话题`
- 看内容：`rostopic echo -n 1 /话题`
- 看节点连接：`rosnode info /节点`
- 看串口占用：`ls -l /proc/<pid>/fd | grep tty`
- 看 USB 重枚举：`journalctl -k | tail -50`

---

## 12. 故障速查表

| 症状 | 最可能原因 | 检查 | 处理 |
| --- | --- | --- | --- |
| 发 `/cmd_vel` 车"不动"、但固件有 `Serial` 回显 | **机器人被架起来了**，轮子空转不产生位移 | 看轮子是否接触地面 | 放回地面再测；架起时只能验证"轮子转不转"，不能验证位姿 |
| 发 `/cmd_vel` 车不动、无 `Serial` 回显 | 固件在 RC 模式（接收机有信号，含失控保护值） | `timeout 5 rostopic echo /jiaoda/esp_tel \| grep Serial` | 拔接收机 → **重启 ESP32**（RTS 脉冲）|
| 拔了接收机还是 0 回显 | 固件 `pulseWidths` 保留旧值，不重启不切模式 | 同上 | 复位主控一次 |
| `/unilidar/cloud` 无数据、`eth1` 显示 `NO-CARRIER` | 雷达网线松/断，或雷达断电 | `cat /sys/class/net/eth1/carrier`（1=通） | 插回 RJ45；`ping 192.168.1.62` |
| 网页地图有图、位姿不动 | SLAM 停摆（相机无图） | `rostopic hz /aft_mapped_to_init` | 修相机索引后重启 fastlivo |
| `/left_camera/image` 无数据 | 相机索引失效 | `ls -l /proc/1094/fd \| grep video` | 改 `CAMPUB_INDEX` 或加重连 |
| 发 `/cmd_vel` 车不动 | 串口名错 / RC 优先 / 急停 | 看 bridge 日志、遥控器是否开着 | 改 `CTL_PORT=/dev/ttyACM0`；关遥控器 |
| `ttyCH343USB0` 打不开 | CH343 以 CDC 模式枚举成 `ttyACM0` | `ls /dev/ttyACM*` | 用 `/dev/ttyACM0`，别装 ch343.ko |
| 网页打不开 | 本机代理劫持 | `curl --noproxy '*'` 试 | 建 SSH 隧道走 127.0.0.1 |
| 日志时间全是 9 月 10 日 | RTC 未保持 | `timedatectl` | 正常现象，看 `etime` |
| 服务反复重启 | 见 13.1、13.2 | `systemctl status` | 修 `cv_bridge` / 相机索引 |
| 地图越走越糊 | `grid_bridge` 随机 25% 回填 | 看 13.3 | 需要改算法 |

### 12.1 网络注意

- `eth0` 与 `eth1` **在同一个二层网段**（同一台交换机），`eth0` 上只能看到 `192.168.1.62` 的广播 ARP。
- **不要给 `eth0` 配 `192.168.1.3/24`**：会与 `eth1` 的 `192.168.1.2/24` 冲突，可能搞断雷达链路。
- 设计图里的第二台雷达 `192.168.1.63` 与网口相机**当前不存在**。
- 热点 `xlx` 是 **`172.20.10.0/28`**，可用地址只有 `.1–.14`。给 `wlan0` 加固定地址时必须落在这个范围内（`.88` 这种在网段外，加了解析不到，实测踩过）。
- 固定地址的持久化命令：`sudo nmcli con mod xlx +ipv4.addresses 172.20.10.14/28`（保留 `ipv4.method=auto`，DHCP 照常）。

---

## 13. 已知问题清单（按优先级）

> 编号沿用 [docs/audit-code.md](docs/audit-code.md) 的缺陷编号，便于交叉检索；P0/P1/P2 表示修复优先级。

### 13.1 P0 · 已修复（2026-10-21 13:30）

| 编号 | 问题 | 位置 | 处理 |
| --- | --- | --- | --- |
| P1 | `cam_publisher` 打开不存在的 `video2`，且不重连、不报错 | `cam_publisher.py`、`run_campub.sh` | **已重写**：重连 + 索引 3 + 去掉 cv_bridge 依赖 |
| P2 | 串口默认值 `/dev/ttyCH343USB0` 不存在 | `chassis_gimbal_bridge.py:8` | **已改** `/dev/ttyACM0`，并关闭 DTR 复位 |

### 13.2 P1 · 严重但可绕过

| 编号 | 问题 | 位置 | 状态 |
| --- | --- | --- | --- |
| N1 | `nav_mission` 因 `cv_bridge` 导入失败无限重启 | `nav_mission.py:7` | **已修复**（对调 import） |
| M3 | 旧 `cmd_vel_to_pwm.py` 无速度看门狗（已 disabled，勿启用） | `cmd_vel_to_pwm.py:18-28` | 未动，保持禁用 |
| C1 | 控制台无鉴权，`/api/ctl/drive` 无限幅 | `console_backend.py:237` | **未修，仍暴露** |
| CL1 | 标定页可无鉴权覆写 FAST-LIVO 配置且不备份 | `calib_web.py:200-211` | 未动（服务未启用） |

### 13.3 P2 · 影响精度/可维护性

| 编号 | 问题 | 说明 |
| --- | --- | --- |
| T1 | `cloud_restamp` 用 `now()` 覆盖雷达时间戳 | 破坏 SLAM 时间语义 |
| R1 | `grid_bridge` 负坐标半格偏差 | 栅格化偏移 |
| R2 | 建图随机 25% 回填 | 同一份数据两次建图结果不同 |
| S3/S8 | 不重规划；无激光时仍按最高 1.0 m/s 走 | 需要改安全策略 |
| B1 | `/imu` 是伪 IMU（协方差为 0，frame 名 `base` 不规范） | pose_bridge 里拼出来的 |
| — | `chksum` 是四值直接相加未取模 | 固件如何校验待确认 |
| — | 三个串口协议并存（`t,s,p,y,chk` / `left,right` / `M<l>,<r>`） | 只有第一种与固件匹配 |

---

## 14. 从零复现（换一台新 Jetson 也能重建）

> 本章目标：拿到一台空白 Jetson AGX Orin + 同样外设，照着做完就能得到和现在**等价**的系统。
> 本次所有源码/配置原件已导出到 [`docs/source/`](docs/source/)，可直接当"出厂镜像"用。

### 14.1 物料清单

| 部件 | 规格 | 关键点 |
| --- | --- | --- |
| 计算单元 | Jetson AGX Orin Developer Kit | JetPack 5.1.x（L4T **35.4.1**） |
| 激光雷达 | 宇树 **Unitree L2** | 出厂 IP `192.168.1.62`，UDP 6101 → 6201 |
| 主控 | ESP32-S3 开发板（板载 WCH CH343） | 串口 115200，协议见 7.2 |
| 相机 | 4× UVC（Sonix `0c45:6366`，2592×1944 MJPG） | **四个序列号相同**，必须用 USB 口位区分 |
| USB Hub | 有源 USB 2.0/3.0 Hub | 相机全部挂在它下面 |
| 网络 | 板载 RJ45（`eth1`）+ 交换机 | 雷达与 `eth0` 在同一条二层网络 |

接线顺序（对照 `docs/jetson-hardware-topology-2026-10-21.png`）：
`Jetson USB → Hub → 4 路相机 / ESP32`；`Jetson eth1 → 交换机 → L2 雷达`。

### 14.2 软件版本矩阵（本机实测版本，复现请对齐）

| 组件 | 版本 |
| --- | --- |
| Ubuntu | 20.04.6 LTS (focal), aarch64 |
| 内核 | 5.10.120-tegra（L4T R35.4.1） |
| ROS | Noetic（`packages.ros.org` focal 源），roscpp 1.17.4 |
| GCC / CMake | 9.4.0 / 3.16.3 |
| Eigen / PCL / Boost / OpenCV | 3.3.7 / 1.10.0 / 1.71 / **4.2.0** |
| Python | 3.8.10；numpy **1.17.4**、pyserial **3.4**、PyYAML **5.3.1** |
| FAST-LIVO2 | `hku-mars/FAST-LIVO2` @ **0d2c034** |
| rpg_vikit | `xuankuzcr/rpg_vikit` @ **6c886c8** |
| Sophus | `strasdat/Sophus` @ **a621ff2e** |
| unitree_lidar_ros | `unitreerobotics/unilidar_sdk2` @ **0e3c51f** |

> OpenCV 必须是 4.2.0（Ubuntu 20.04 自带）。**不要**用 pip 升级 numpy/opencv，否则 `cv_bridge` 必崩（见 14.12）。

### 14.3 步骤 1：系统与依赖

```bash
# 1) 刷 JetPack 5.1.2（L4T 35.4.1）到 Orin，完成首次开机
# 2) ROS Noetic
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu focal main" \
  > /etc/apt/sources.list.d/ros-latest.list'
sudo apt-key adv --keyserver 'hkp://keyserver.ubuntu.com:80' \
  --recv-key C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654
sudo apt update && sudo apt install -y ros-noetic-desktop-full
sudo rosdep init && rosdep update
echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc

# 3) 编译与运行依赖
sudo apt install -y build-essential cmake git libeigen3-dev libpcl-dev \
  libopencv-dev libboost-all-dev python3-pip python3-serial python3-yaml \
  ros-noetic-cv-bridge ros-noetic-pcl-ros ros-noetic-image-transport \
  ros-noetic-eigen-conversions ros-noetic-tf
```

### 14.4 步骤 2：编译 Sophus

源码**已随仓库提供**（`docs/source/Sophus_src`，140 KB）：

```bash
cp -r <本仓库>/docs/source/Sophus_src ~/Sophus_src
cd ~/Sophus_src && mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j4 && sudo make install
```

> 本机其实**没有 install**：`CMakeCache.txt` 里 `Sophus_DIR=/home/sjytt/Sophus_src/build`，是靠这个路径找到的。复现时建议直接 `make install` 到 `/usr/local`，省得每次传路径。

### 14.5 步骤 3：FAST-LIVO2 + rpg_vikit

**源码已随仓库提供，不需要联网 clone**（`docs/source/` 里是完整可编译代码，含本机改过的三个文件）：

```bash
mkdir -p ~/livo2_ws/src
cp -r <本仓库>/docs/source/FAST-LIVO2  ~/livo2_ws/src/
cp -r <本仓库>/docs/source/rpg_vikit   ~/livo2_ws/src/
cd ~/livo2_ws && catkin_make -j4 -DCMAKE_BUILD_TYPE=Release
source ~/livo2_ws/devel/setup.bash
# 若找不到 Sophus：catkin_make -DSophus_DIR=$HOME/Sophus_src/build
```

想用上游仓库也行（两者等价）：`hku-mars/FAST-LIVO2@0d2c034` + `xuankuzcr/rpg_vikit@6c886c8`，再覆盖 `config/unitree_l2.yaml`、`config/camera_unitree.yaml`、`launch/mapping_unitree_l2.launch` 三个文件。

### 14.6 步骤 4：雷达驱动

**包和 SDK 都随仓库提供**。注意：ROS 包的 `CMakeLists.txt` 用**相对路径** `../../../unitree_lidar_sdk`
引用 SDK 的头文件和 `lib/aarch64/libunilidar_sdk2.a`，**少放 SDK 就编不过**：

```bash
mkdir -p ~/unilidar_sdk2/unitree_lidar_ros/src
cp -r <本仓库>/docs/source/unitree_lidar_sdk  ~/unilidar_sdk2/
cp -r <本仓库>/docs/source/unitree_lidar_ros  ~/unilidar_sdk2/unitree_lidar_ros/src/
cd ~/unilidar_sdk2/unitree_lidar_ros && catkin_make
```

部署后的目录形状必须是：

```
~/unilidar_sdk2/
├── unitree_lidar_sdk/          # include/ + lib/aarch64/
└── unitree_lidar_ros/
    └── src/unitree_lidar_ros/  # 这个包
```

雷达参数在 `config/config.yaml`：`initialize_type=2`（UDP）、`lidar_ip=192.168.1.62`、`pc_ip=192.168.1.2`、端口 6101/6201。

### 14.7 步骤 5：部署 `~/jiaoda`

```bash
cp -r <本仓库>/docs/source/jiaoda ~/jiaoda
chmod +x ~/jiaoda/run_*.sh ~/jiaoda/*.py
mkdir -p ~/jiaoda/maps ~/jiaoda/routes
```

### 14.8 步骤 6：网络

```bash
# eth1 固定 IP（雷达网段）
sudo nmcli con add type ethernet ifname eth1 con-name lidar-eth ip4 192.168.1.2/24
sudo nmcli con up lidar-eth
ip -4 addr show eth1        # 应显示 192.168.1.2/24
ping -c 2 192.168.1.62
```

### 14.9 步骤 7：systemd 托管

```bash
sudo cp <本仓库>/docs/source/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
for s in lidar restamp campub fastlivo grid posebridge nav control console; do
  sudo systemctl enable --now jiaoda-$s
done
# mission 可选：sudo systemctl enable --now jiaoda-mission
```

> 单元文件里的 `ExecStart` 指向 `~/jiaoda/run_*.sh`，如果换用户/换路径要一起改。

### 14.10 步骤 8：验收清单

| 检查项 | 命令 | 期望 |
| --- | --- | --- |
| 服务 | `systemctl list-units 'jiaoda*'` | 9 个 active |
| 雷达 | `timeout 4 rostopic hz /unilidar/cloud` | ≈ 12 Hz |
| 转发 | `timeout 4 rostopic hz /synced/cloud` | ≈ 12 Hz |
| 相机 | `timeout 4 rostopic hz /left_camera/image` | ≥ 10 Hz（**本机当前为 0，见 8.2**） |
| SLAM | `timeout 4 rostopic hz /aft_mapped_to_init` | ≥ 10 Hz |
| 定位 | `timeout 4 rostopic hz /slam_pose` | 同 SLAM |
| 地图 | `curl -s :8090/api/mapinfo` | 返回 `mpp/w/h` |
| 网页 | `curl -s -o /dev/null -w '%{http_code}' :8090/` | 200 |
| 底盘 | `journalctl -u jiaoda-control -n 20` | 无 ENOENT |

### 14.11 相机-雷达标定（**已验证可用**）

当前值：`Rcl = [0,1,0,-1,0,0,0,0,1]`（绕 Z 轴 90°）、`Pcl = [0,0,0]`；内参 `fx=fy=914.0`、`cx=640.0`、`cy=360.0`、畸变全 0。

**2026-10-21 实测验证**：取同一时刻的一帧图像与 `/synced/cloud`，按 `p_cam = Rcl·p_lidar + Pcl` 投影叠加，结果见 [`docs/extr-check-overlay.jpg`](docs/extr-check-overlay.jpg)。

- 地面点云形成**笔直的放射线**并准确落在真实地面上；
- 左右墙面、玻璃隔断上的点与画面中的结构边界**贴合**；
- 4818 个点中 1937 个落在视野内，分布合理。

结论：**外参是标定过的、可用的**。此前依据 `calib/calib_cam_lidar.md` 里"当前是单位阵占位"那句判断它未标定，是**误判——那份文档过时了**，实际 yaml 里已经是标好的 90° 旋转 + 零平移（相机与雷达同轴安装，平移接近 0 是合理的）。

**什么时候需要重标**：换相机、改动相机/雷达安装位置、换雷达。

复跑验证的最小脚本（Jetson 上跑，机器人保持静止）：

```python
# 订阅 /left_camera/image 与 /synced/cloud，各取一帧
R = np.array([0,1,0, -1,0,0, 0,0,1], np.float32).reshape(3,3)   # = Rcl
T = np.array([0,0,0], np.float32)                                # = Pcl
pc = pts @ R.T + T
u = 914.0*pc[:,0]/pc[:,2] + 640.0
v = 914.0*pc[:,1]/pc[:,2] + 360.0
# 画到图上，地面线贴合即正确
```

> 注：`calib/data/` 里那批旧图用的是 **2×2 的 6×6 ArUco 板**，而 `calib_intrinsics.py` 假设的是 **6×6 AprilGrid 36h11**（`TAG_SIZE=0.088`、间距 0.3），所以那批图跑不出结果——是**两套板型对不上**，不影响现有已标定的参数。要重标请按脚本假设的板型拍，或改脚本的 `TAG_COLS/TAG_ROWS/TAG_SIZE/TAG_SPACING`。

- [`docs/source/jiaoda/calib/calib_intrinsics.md`](docs/source/jiaoda/calib/calib_intrinsics.md)（75 行）
- [`docs/source/jiaoda/calib/calib_cam_lidar.md`](docs/source/jiaoda/calib/calib_cam_lidar.md)（107 行）

**内参（纯 cv2 + AprilGrid，无需 Kalibr）**

```bash
python3 calib/grab_frames.py 0 ./frames 1280 720   # ≥20 张，覆盖四角/远近/±20~45°倾斜
python3 calib/calib_intrinsics.py ./frames 1280 720
# 合格标准：RMS 重投影误差 < 0.5 px；cx,cy 接近 (640,360)
# 结果写入 camera_unitree.yaml 的 cam_fx/fy/cx/cy/d0..d3
```

**外参（推荐 `hku-mars/livox_camera_calib`，无靶标）**

1. 找有大量直角/门框/货架的静态场景；
2. 机器人**完全静止 20–40 s**，让 L2 把稀疏帧累积成稠密点云；
3. 同时抓一张同视角的图；
4. 用 `calib.launch` 离线标一次，看它输出的点云-图像叠加图，边缘重合即成功；
5. 输出直接是 `p_camera = R·p_lidar + t`，`Rcl`（行主序 9 个数）、`Pcl`（米）填回 yaml。

**兜底方案**：AprilGrid 同名点 + `cv2.solvePnP`（精度依赖手点，适合交叉验证）。
**方向搞反**：`Rcl = R_lcᵀ`、`Pcl = -R_lcᵀ·t_lc`。

> 已有的原始采集数据在 `docs/source/jiaoda/calib/data/`：`extr/` 8 组 jpg+npy（点云）、`intr/` 5 张标定图，可直接复算。

⚠️ 文档与代码有出入：`calib_cam_lidar.md` 说把 `Rcl/Pcl` 填进 `camera_unitree.yaml`，但**实际读取的是 `unitree_l2.yaml` 的 `extrin_calib` 段**（`calib_web.py` 里的 `MAIN_YAML` 也指向它）。以代码为准。

### 14.12 复现陷阱（踩过，别重复）

| 陷阱 | 现象 | 规避 |
| --- | --- | --- |
| `cv_bridge` 导入顺序 | `SystemError: initialization of cv_bridge_boost` | 任何脚本**先 `import cv2` 再 `import cv_bridge`** |
| 相机设备号漂移 | `/dev/video2` 消失 | 用 `by-path`，并给采集程序加重连 |
| `cv2.VideoCapture` 不重连 | 有发布者、零数据、无报错 | 采集循环里检测 `isOpened()/read()` 失败就重开 |
| CH343 被认成 `ttyACM0` | `/dev/ttyCH343USB0` 不存在 | 用 `ttyACM0`；别装 `ch343.ko` |
| ROS Master 寄生 | 停雷达 → 全栈塌 | 单独 `roscore` 服务，或用 `roslaunch --wait` |
| RTC 不保持 | 日志时间错 40 天 | 装 RTC 电池，或开机强制 `ntpdate` |
| `libopencv-dev` 与 pip opencv 混装 | 符号冲突 | 只用 apt 版本 |
| 四个相机同序列号 | `by-id` 只有一个 | 用 USB 物理口 `by-path` |

---

## 15. 如果重做一个更好的（架构建议）

现在这套是"能跑起来的原型"：2234 行 Python 全部堆在一个目录、无 Git、无测试、无 TF 树、无鉴权。要做得更好，建议按下面顺序改。

### 15.1 结构：把单体拆成包

| 现状 | 更好 |
| --- | --- |
| 12 个 `.py` 平铺在 `~/jiaoda` | 拆成 catkin 包：`jiaoda_driver` / `jiaoda_nav` / `jiaoda_web` / `jiaoda_msgs` |
| 跨进程靠 `/dev/shm/*.json` | 自定义 msg + 话题；状态用 `rosbridge` 或参数服务器 |
| 启动靠 12 个 systemd 单元 | 一个 `roslaunch` + 单元只负责 launch |
| 无 Git | 立刻 `git init`，按节点拆提交 |

### 15.2 设备：稳定命名 + 自愈

- 相机：`/dev/v4l/by-path/...` 固定映射，采集端加"打不开就重试"循环（当前 P0 的根因就是缺这两条）。
- 底盘：为 `1a86:55d3` 写 udev 规则生成 `/dev/jiaoda-chassis`，别用 `ttyACMx`。
- 启动顺序：所有节点对"数据"做超时判断，而不是对"话题名存在"做判断（当前 `run_fastlivo.sh` 只 grep 话题名，所以空跑也算成功）。

### 15.3 坐标与里程计

- 现在 TF 只有 `unilidar_*`，没有 `map→odom→base_link`，nav 只能用原始 `PoseStamped`。
- 补一条标准 TF 链：`map → odom → base_link → {lidar, camera, imu}`，`/odom` 由轮速或 SLAM 输出。
- `/Odometry` 目前是死订阅（console 在等），要么去掉，要么真的发布。

### 15.4 安全（优先级最高）

| 风险 | 现在就有的问题 | 改法 |
| --- | --- | --- |
| 网络无鉴权 | `0.0.0.0:8090` + `/api/ctl/drive` 无限幅，谁都能让车动 | 加 token/白名单；后端强制限幅（`vx≤0.3` 等） |
| 急停依赖软件 | 串口断了急停就失效 | 独立硬件急停回路；看门狗断电 |
| RC 与串口抢控制 | 固件 `RC > Serial`，但上位机不知道 | 固件回报当前模式，上位机据此禁发 |
| 无碰撞兜底 | `nav_simple` 无激光时仍最高 1.0 m/s | 无点云/无定位立即零速并上报 |

### 15.5 可观测性

- 录包：现在**一条 rosbag 都没有**。加一个"异常自动录 30 s"的环形缓冲。
- 日志：89 MB 无轮转，配 `logrotate`。
- 指标：`/cmd_vel`、定位频率、串口丢帧率上报到网页（`/api/ctl/status` 里的 `hz` 现在恒 0）。

### 15.6 工程质量

- 单元测试：A\*、DWA 打分、栅格化（现在 `grid_bridge` 负坐标半格偏差 + 25% 随机回填，不可复现）。
- 时间戳：`cloud_restamp` 用 `now()` 覆盖雷达时间戳，破坏 SLAM 时间语义——应改成"保留原时间戳 + 单独记录到达时间"。
- 配置版本化：外参虽已验证，但只存在于 yaml 里、没有标定报告与版本记录；建议把标定结果、日期、验证图一并纳入 Git。
- 依赖锁定：`requirements.txt` + 固定 apt 版本，避免某次 `apt upgrade` 把 `cv_bridge` 弄坏。

### 15.7 建议路线图

| 阶段 | 目标 | 工作量 |
| --- | --- | --- |
| 第 1 周 | 修好相机重连 + 底盘端口 + `cv_bridge`，让系统真正闭环 | 1–2 天 |
| 第 2 周 | 加 TF 树与 `/odom`，把 nav 迁到标准接口 | 3–5 天 |
| 第 3 周 | 安全加固（鉴权、限幅、硬件急停）、日志与录包 | 3–5 天 |
| 第 4 周 | 拆包、加测试、Git 化，形成可复现构建 | 1 周 |

---

### 14.13 主控固件（源码已归档）

**源码找到了**：[`docs/source/firmware/control_1.ino`](docs/source/firmware/control_1.ino)（321 行）+ [`ReadRC.ino`](docs/source/firmware/ReadRC.ino)（RC 测试草图）。Arduino 框架，ESP32-S3。

实机行为与源码完全对得上（串口横幅、帧格式、超时值都一致），**不需要再从芯片里 dump 二进制**。

关键实现（`control_1.ino`）：

| 项 | 值 |
| --- | --- |
| 底盘电调 | `THROTTLE_PIN 21`、`STEER_PIN 47`；50 Hz、13 bit、`PWM_MAX 8191` |
| 云台舵机 | `GIMBAL_PITCH_PIN 48`、`GIMBAL_YAW_PIN 45` |
| RC 输入 | 10 通道，`{1,2,42,41,40,39,38,37,36,35}`，上升/下降沿中断测脉宽 |
| RC 映射 | CH1 转向、CH2 油门、CH3 俯仰、CH4 偏航、CH5 保存（边沿触发） |
| 速度→脉宽 | `-30..30` → `1000..2000 µs`；`0`→1500；正向 1600–2000，反向 1000–1400（中位 ±100 µs 为死区） |
| 串口 | 115200，`throttle,steer,pitch,yaw,checksum`，校验为四值直接相加 |
| 模式 | `MODE_RC` / `MODE_SERIAL` / `MODE_IDLE`，**RC 有效时直接 return，不处理串口** |
| 超时 | RC 200 ms、串口 500 ms，超时即回中位 |
| 上报 | 每 100 ms 发 `GIMBAL_PULSE:<p>,<y>`，另在调试时回 `Serial T:.. S:..` |

两个容易踩的实现细节：

1. **转向是反的**：`setChassisSignal()` 里 `s_us = speedToMicroseconds(-steer)` —— 转向通道取负。上位机的 `nav_simple` 用 `INVERT_YAW=True` 再反一次，两边配合才对；
2. **串口校验不做取模**：`throttle+steer+pitch+yaw == chk`，范围 ±120，D 位足够，暂无溢出风险。

**硬件副作用**：CH343 的 DTR 接了 EN，**打开串口会让 ESP32 复位一次**。桥接程序已改成打开前把 DTR/RTS 置低，避免每次重启都复位。

**烧录**：Arduino IDE 选 `ESP32S3 Dev Module`，USB 口用 `1-4.4`（原生 USB）或 `1-4.3`（CH343），115200 上传即可。

---

## 附录 A：原始实测记录（2026-10-21）

### A. 设备与访问
- **K1** NVIDIA Jetson AGX Orin DevKit，`sjytt-desktop`，Ubuntu 20.04.6 LTS、aarch64、L4T R35.4.1、内核 `5.10.120-tegra`。
- **K2** `l4tbr0` = 192.168.55.1/24，本机 192.168.55.100，SSH `0.0.0.0:22`，USB SSH 可用。
- **K3** 不配置 Windows OpenSSH Server，不做远程跳板。

### B. 网络
- **K4** Wi-Fi `xlx`（wlan0，172.20.10.8/28，网关 172.20.10.1），DHCP 会变。
- **K5** NM 状态：`xlx/wlan0` 已连、`eth1/lidar-eth` 已连、`eth0` 无 IPv4、`l4tbr0` 为 USB 网桥。
- **K6** `eth1` 192.168.1.2/24，邻居 192.168.1.62 可达。
- **K7** `eth0` 为 WCH USB 网卡 `1a86:5397` SN `6C1FF7EB483F`，有载波无 IP。
- **K8** 旧记录的 `asd` / 192.168.43.114 已失效。

### C. 设计图与实际
设计图见 `docs/jetson-hardware-topology-2026-10-21.png`，仅代表设计目标。四路相机实为同型号 RGB；第二台雷达与网口相机未发现；ESP32 已验证为控制口。

### D. 相机
- **K9** 四路 UVC 物理路径：`1-4.2.1.3`→video3/4、`1-4.2.2`→video0/1、`1-4.2.3`→video5/6、`1-4.2.4`→video7/8。
- **K10** 四台标识完全相同（`0c45:6366`，SN `SN0001`），无法靠名字区分角色。
- **K11** 另有 Realtek 蓝牙 `13d3:3549`。

### E. ESP32 / 雷达 / ROS
- **K12** ESP32 两个 USB 口：原生 USB（ttyACM1，JTAG）与 CH343（ttyACM0，控制台）。
- **K13** 运行节点：cam_publisher、console_backend、unitree_lidar_ros_node、laserMapping、nav_simple、chassis_gimbal_bridge、pose_bridge、grid_bridge、cloud_restamp。
- **K14** 关键话题见 3.3。
- **K15** ROS Master 在 11311。
- **K22** `/dev/ttyACM0` 即主控控制口，固件协议与 bridge 一致。
- **K23** 固件 `Priority: RC > Serial`。
- **K24** 桥接失联是端口名错位，非硬件断线；`ch343.ko` 无效。
- **K25** 打开 ttyACM0 会复位 ESP32，属预期。
- **K26** `/cmd_vel` 15.9 Hz 全 0；`/Odometry` 无消息。

### F. 网页与代码
- **K16** 8090 可访问，标题「巡检机器人控制台」。
- **K17** 8095 未监听，代码在 `calib/calib_web.py`，`run_calib.sh` 未启用。
- **K18** 主代码 `~/jiaoda`；`~/dog_backup` 为旧版。
- **K19** Git 状态：FAST-LIVO2 `0d2c034` 有未跟踪配置；`unilidar_sdk` 有修改；`jiaoda`/`dog_backup` 无 Git。

### G. 脚本风险
- **K20** `~/dog_backup/start_all.sh` 会按宽泛进程名强杀 ROS/SLAM，**不要在当前栈运行时执行**。

### H. 凭据
- **K21** 本文件不保存任何密码、密钥、口令。

### 仓库版本状态（2026-10-21 快照）

| 目录 | HEAD | 状态 |
| --- | --- | --- |
| `~/livo2_ws/src/FAST-LIVO2` | `0d2c034` | **未跟踪** `config/camera_unitree.yaml`、`config/unitree_l2.yaml`、`launch/mapping_unitree_l2.launch` |
| `~/livo2_ws/src/rpg_vikit` | `6c886c8` | 干净 |
| `~/rslidar_ws/src/rslidar_sdk` | `78d2abb` | 干净（未使用） |
| `~/rslidar_ws/.../rs_driver` | `4eeadac` | 嵌套仓库，detached HEAD |
| `~/unilidar_sdk` | `1bd7d95` | `config/config.yaml`、`include/unitree_lidar_ros.h` 已修改 |
| `~/unilidar_sdk2` | `0e3c51f` | `config.yaml` 已修改，有 `config2.yaml`、`run_lidar2.launch` |
| `~/Sophus_src` | `a621ff2e` | detached HEAD，`so2.cpp` 已修改 |
| `~/ch343ser_linux` | `b5515b9` | `driver/` 下有编译产物（当前无用） |
| `~/jiaoda`、`~/dog_backup` | — | **无 `.git`**，必须手工备份 |

### 待完成（T）
- **T1** 确认四路相机与物理位置的固定映射（已抓帧，位置待现场确认）。
- **T2** `eth0` 实际接的是交换机；第二台雷达 `.63` 链路不存在。**不要**配 192.168.1.3。
- **T3** 底盘联调：轮子离地、关遥控器、`CTL_PORT=/dev/ttyACM0`、0.1 m/s 起步。
- **T4** 显示屏/键鼠/交换机现场确认。
- **T5** 重启后复核自启、相机、雷达、Master、8090。
- **T6** 对未提交改动先备份/提交，尤其是 FAST-LIVO2 的三个本地配置。
- **T7** 确认底盘有无里程计回传（`/Odometry` 空）。

---

## 附录 B：文件索引

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `console_backend.py` | 304 | 网页后端 + 直接发 cmd_vel/云台 |
| `nav_simple.py` | 473 | A\* + Pure Pursuit + DWA |
| `grid_bridge.py` | 266 | 点云 → 2D 栅格 → `/map` + PNG/NPZ |
| `cam_publisher.py` | 28 | 相机 → ROS Image |
| `chassis_gimbal_bridge.py` | 72 | cmd_vel + 云台 → 串口 |
| `chassis_bridge.py` | 159 | 旧 ESP32 协议（未运行） |
| `gimbal_driver.py` | 155 | 独立舵机云台库（未被引用） |
| `cmd_vel_to_pwm.py` | 52 | 旧底盘直驱（disabled） |
| `nav_mission.py` | 93 | 巡检任务（崩） |
| `pose_bridge.py` | 32 | 位姿转发 |
| `cloud_restamp.py` | 10 | 点云时间戳改写 |
| `photo.py` | 61 | 拍照（未被引用） |
| `calib/calib_web.py` | 324 | 标定页 8095 |
| `calib/calib_intrinsics.py` | 144 | 内参标定 |
| `calib/grab_frames.py` | 61 | 抓帧 |
| `console.html` | — | 单页前端 |

---

## 附录 C：审计材料与源码包

- [docs/source/](docs/source/)：**自包含复现包**（`docs/source/README.md` 有部署对照表）——
  `jiaoda/` 全部应用代码、`FAST-LIVO2/` 完整可编译源码（含本地 3 个改动）、`rpg_vikit/`、
  `Sophus_src/`、`unitree_lidar_ros/` + `unitree_lidar_sdk/`（含 aarch64 预编译库）、
  `firmware/`（ESP32 固件）、`systemd/`（12 个单元）、`verify.sh`（部署自检）。
  **clone 本仓库后不需要再访问任何其他仓库。**
- [docs/source/firmware/](docs/source/firmware/)：`control_1.ino`（321 行，主控固件）+ `ReadRC.ino`（RC 测试）
- [docs/extr-check-overlay.jpg](docs/extr-check-overlay.jpg)：**外参验证图**——雷达点云投影到相机画面，地面线贴合即外参正确
- [docs/audit-code.md](docs/audit-code.md)：`~/jiaoda` 全部源码逐文件接口审计（840 行）
- [docs/audit-runtime.md](docs/audit-runtime.md)：启动机制、进程树、自启排查、构建状态、恢复方案（528 行）
- 相机抓帧存证：`docs/cam-video3-2026-10-21.jpg`、`cam-video5-*.jpg`、`cam-video7-*.jpg`、`slam-camera-frame.jpg`
- 地图快照：`docs/jetson-map-2026-10-21.png`
- 拓扑设计图：`docs/jetson-hardware-topology-2026-10-21.png`
