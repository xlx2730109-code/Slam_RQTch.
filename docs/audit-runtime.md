# Jetson AGX Orin 运行时"启动 / 恢复"机制审计（只读）

- 审计对象：`sjytt@192.168.55.1`（`sjytt-desktop`，Ubuntu 20.04.6 LTS / L4T R35.4.1 / 内核 5.10.120-tegra，8 核，61 GiB 内存）
- 审计时间：2026-10-21 13:13 – 13:20 CST
- 审计方式：SSH 只读命令；未执行任何 `systemctl start/stop/restart/enable/disable`，未写 Jetson 任何文件，未使用 `sudo`，未打开 `/dev/ttyACM0`、`/dev/ttyACM1`。为确认数据链路，短暂执行了 `rostopic list / info / hz`（只订阅、不发布）和本机 `curl http://127.0.0.1:8090/`。
- 标注约定：**【实测】**＝命令输出直接得到；**【推测】**＝由实测推断、未做验证；**【需 root】**＝当前权限不足、未验证。

---

## 0. 结论速览（TL;DR）

1. **有开机自启，而且是 systemd 托管，不是 crontab/autostart/rc.local。** `/etc/systemd/system/` 下有 12 个 `jiaoda-*.service`，其中 **10 个已 enable**（`jiaoda-calib`、`jiaoda-chassis` 为 disabled）。**【实测】**
2. **重启 Jetson 后这套 SLAM/导航栈会自动起来。** 实测本次开机后约 **15 秒**（内核 monotonic +15.0 s）10 个服务被同时拉起，其中 9 个常驻服务正常运行，ROS Master、雷达、FAST-LIVO、8090 控制台全部就位，无需人工干预。**【实测】**
3. **自动启动 ≠ 全栈可用。** 当前有三个真实故障：
   - `jiaoda-mission.service` 崩溃重启 **1800+ 次**（`nav_mission.py` 里 `import cv_bridge` 在 `import cv2` 之前，必然 `SystemError`）。**【实测】**
   - `cam_publisher.py` 固定 `CAMPUB_INDEX=2`，但 `/dev/video2` 已不存在（现存 0,1,3,4,5,6,7,8），导致 `/left_camera/image` **无任何消息** → FAST-LIVO 无图 → `/aft_mapped_to_init`、`/cloud_registered`、`/slam_pose` 全部静默。**【实测】**
   - 开机初期系统时钟停在 **2026-09-10 17:12**（比真实时间早约 40 天 17.5 小时），约 11:32 才被 NTP 校正；**重启后 11:32 之前的日志时间戳不可信**。**【实测现象 / 推测机制】**

---

## 1. 审计边界与"需 root"项

| 项目 | 结果 |
| --- | --- |
| 是否执行过写操作 | 否。未启动/停止/重启任何进程，未写 Jetson 文件 |
| 是否执行 sudo | 否（任务禁止） |
| 串口 /dev/ttyACM0、/dev/ttyACM1 | 未 open（仅 `ls`/源码/配置文件中出现路径） |
| root 用户 crontab | **【需 root】** `/var/spool/cron/crontabs/root` 不可读，未验证；`sjytt` 用户 crontab 为空【实测】 |
| /etc/sudoers.d 等 | 未读（与启动机制无关） |
| 进程环境变量 | 通过 `/proc/<pid>/environ` 读取（同用户可读）【实测】 |

---

## 2. 当前进程树（缩进文本）

时间说明：`ps lstart` 因开机时钟错乱显示 2026-10-21 10:43:34，但 `/proc/<pid>` 的 ctime 是 2026-09-10 17:12:46（见 §11.3）。**判断先后请用"开机后秒数"（systemd monotonic）**。所有**服务主进程**的父进程（PPID）都是 **1**，即由 systemd 直接拉起（`Type=simple`）。

```text
systemd(1)                                    ← PID 1，/sbin/init
├─ jiaoda-console.service      (+15.037s) → python3 -u console_backend.py            PID 1092  :8090
├─ jiaoda-lidar.service        (+15.040s) → roslaunch unitree_lidar_ros run_without_rviz.launch   PID 1093
│   ├─ rosmaster --core -p 11311 -w 3          PID 2209   (+17s)   ← ROS Master，:11311
│   ├─ rosout __name:=rosout                   PID 2287   (+17s)
│   └─ unitree_lidar_ros_node                  PID 2292   (+18s)   ← /unilidar/cloud 12 Hz
├─ jiaoda-campub.service       (+15.043s) → python3 -u cam_publisher.py              PID 1094  （无出图，见 §11.2）
├─ jiaoda-control.service      (+15.047s) → python3 -u chassis_gimbal_bridge.py      PID 1098  （/dev/ttyCH343USB0）
├─ jiaoda-restamp.service      (+15.050s) → python3 -u cloud_restamp.py              PID 1102  （/unilidar/cloud → /synced/cloud 12 Hz）
├─ jiaoda-fastlivo.service     (+15.053s) → roslaunch fast_livo mapping_unitree_l2.launch rviz:=false   PID 1103
│   └─ fastlivo_mapping __name:=laserMapping   PID 2735   (+22s)   ← 当前无图像输入，未产出里程计
├─ jiaoda-grid.service         (+15.057s) → python3 -u grid_bridge.py                PID 1105  （等 /cloud_registered）
├─ jiaoda-nav.service          (+15.060s) → python3 -u nav_simple.py                 PID 1106  （/cmd_vel 20 Hz 空转）
├─ jiaoda-posebridge.service   (+15.066s) → python3 -u pose_bridge.py                PID 1113
└─ jiaoda-mission.service      (崩溃重启) → python3 -u nav_mission.py                PID 每次重启变化，NRestarts=1806+
```

补充实测：

- `rosnode list` 稳定节点 10 个：`/cam_publisher`、`/chassis_gimbal_bridge`、`/cloud_restamp`、`/console_backend_1092_1789031571163`、`/grid_bridge`、`/laserMapping`、`/nav_simple`、`/pose_bridge`、`/rosout`、`/unitree_lidar_ros_node`。
- 两个 `roslaunch` 进程的 PPID 均为 1（不是从终端继承的），确认由 systemd 直接启动，**不是** `nohup`/终端里手工起的。
- `console_backend` 的 `rosnode` 名字带 `_1092_1789031571163` 后缀，是因为 `rospy.init_node(..., anonymous=True)`。
- `ps -eo pid,ppid,pgid,sid`：每个服务一个独立 PGID/SID（systemd 默认），互不共享控制终端。

---

## 3. 启动顺序（实测时间线）

`systemctl show -p ActiveEnterTimestampMonotonic`（单位 µs，自内核启动）：

| 顺序 | 服务 | 开机后时间 | 实际动作 |
| --- | --- | --- | --- |
| 1 | jiaoda-console | +15.037 s | console_backend.py 先起，后台线程每 3 s 探测 Master |
| 2 | jiaoda-lidar | +15.040 s | roslaunch → **由它创建 rosmaster(:11311)** |
| 3 | jiaoda-campub | +15.043 s | 脚本内 `until rostopic list` 等 Master |
| 4 | jiaoda-control | +15.047 s | 同上，等 Master |
| 5 | jiaoda-restamp | +15.050 s | 等 Master + `/unilidar/cloud` |
| 6 | jiaoda-fastlivo | +15.053 s | 等 `/synced/cloud` |
| 7 | jiaoda-grid | +15.057 s | 等 `/cloud_registered` |
| 8 | jiaoda-nav | +15.060 s | 等 Master |
| 9 | jiaoda-posebridge | +15.066 s | 等 Master |
| 10 | jiaoda-mission | 一直重启 | 启动即崩（§11.1） |

要点：

- 9 个服务在 **约 29 毫秒内**全部 fork 出来。`After=` 只保证"启动任务先后派发"，`Type=simple` 不会等上一个服务真正就绪，所以**没有真正的启动屏障**。
- 真正的同步靠脚本里的 `until rostopic list` / `until rostopic list | grep -q /unilidar/cloud` 轮询，这是这套系统"能自动起来"的关键设计。
- 实测节点出生时间：rosmaster +17 s、rosout +17 s、unitree_lidar_ros_node +18 s、fastlivo_mapping +22 s（`ps lstart` 10:43:36/37/41）。
- 结论：**从内核启动到 ROS Master 可用约 17 秒，到 FAST-LIVO 进程就位约 22 秒**；剩余链路取决于外部设备（雷达网络、相机）。

---

## 4. 脚本清单与调用关系

`/home/sjytt/jiaoda/` 下实测 **12 个** `run*.sh`（`run.sh` + 11 个 `run_*.sh`，任务描述中的"13 个左右"以实测为准），全部 `-rwxrwxr-x`。

| 脚本 | 启动内容 | 关键依赖 / 等待条件 | 是否被自动调用 | 调用者 |
| --- | --- | --- | --- | --- |
| `run.sh` | `python3 -u console_backend.py`（HTTP :8090） | `source /opt/ros/noetic` + `livo2_ws/devel`（后者失败也继续） | 是 | `jiaoda-console.service`（enabled） |
| `run_lidar.sh` | `roslaunch unitree_lidar_ros run_without_rviz.launch` → **同时创建 rosmaster 与 rosout** | `unilidar_sdk2/.../devel`；雷达 UDP `192.168.1.62:6101`，本机 `eth1=192.168.1.2` | 是 | `jiaoda-lidar.service`（enabled） |
| `run_restamp.sh` | `cloud_restamp.py` | 先等 Master，再等 `/unilidar/cloud` | 是 | `jiaoda-restamp.service` |
| `run_campub.sh` | `cam_publisher.py`，`CAMPUB_INDEX=2` | 等 Master；`/dev/video2`（**当前不存在**） | 是 | `jiaoda-campub.service` |
| `run_control.sh` | `chassis_gimbal_bridge.py` | 等 Master；`CTL_PORT=/dev/ttyCH343USB0`（未出现，见 README K24） | 是 | `jiaoda-control.service` |
| `run_fastlivo.sh` | `roslaunch fast_livo mapping_unitree_l2.launch rviz:=false` | `livo2_ws/devel`；等 `/synced/cloud`；需要相机图像 | 是 | `jiaoda-fastlivo.service` |
| `run_grid.sh` | `grid_bridge.py`（点云→2D 栅格，写 `/dev/shm/jiaoda_map.*`） | 等 `/cloud_registered` | 是 | `jiaoda-grid.service` |
| `run_nav_simple.sh` | `nav_simple.py`（A* + Pure Pursuit + DWA） | 等 Master | 是 | `jiaoda-nav.service` |
| `run_pose_bridge.sh` | `pose_bridge.py`（`/aft_mapped_to_init` → `/slam_pose` + `/imu`） | 等 Master；上游 `/aft_mapped_to_init` | 是 | `jiaoda-posebridge.service` |
| `run_mission.sh` | `nav_mission.py`（航点任务、拍照） | 等 Master；`cv_bridge`（**import 顺序错误，启动即崩**） | 是，但永远失败 | `jiaoda-mission.service`（enabled，重启 1800+ 次） |
| `run_calib.sh` | `calib/calib_web.py`，`CALIB_CAM=2`，:8095 | 无 | **否** | `jiaoda-calib.service`（**disabled**），只能手动 |
| `run_chassis.sh` | `cmd_vel_to_pwm.py`（写 `/dev/ttyACM0`，DTR 会复位 ESP32） | 等 Master；串口 | **否** | `jiaoda-chassis.service`（**disabled**），只能手动 |

调用关系（实测，无环、无脚本互调）：

```text
systemd ──ExecStart──> run_*.sh ──exec──> python3 / roslaunch ──> rosmaster / rosout / 节点
```

- 所有脚本都以 `exec` 结尾，因此 systemd 的 `MainPID` 就是最终的 python/roslaunch 进程（实测 `MainPID=1092/1093/1103…`）。
- **没有任何脚本调用另一个脚本**；`console_backend.py` 也不 spawn 子进程（它只写 `/dev/shm/jiaoda_*.json|png`、`jiaoda_nav_cmd`，由 `nav_*.py` 轮询）。
- `run_*.sh` 不读 `~/.bashrc`，各自 `source /opt/ros/noetic/setup.bash`，所以**交互 shell 的环境与服务环境是两套**。
- `~/dog_backup/start_all.sh` 会 `pkill -9 -f "ros|slam|lio|..."`，**不要在当前栈运行时执行**（README K20 已警告，本次未执行）。

---

## 5. 开机自启机制（逐项排查）

### 5.1 systemd（唯一生效的机制）【实测】

`/etc/systemd/system/` 下 12 个自定义单元，全部 `User=sjytt`、`Type=simple`、`Restart=always`、`RestartSec=3~5`、`WantedBy=multi-user.target`：

| 单元 | ExecStart | After | enabled |
| --- | --- | --- | --- |
| jiaoda-console.service | run.sh | network.target | ✅ |
| jiaoda-lidar.service | run_lidar.sh | network.target | ✅ |
| jiaoda-restamp.service | run_restamp.sh | jiaoda-lidar | ✅ |
| jiaoda-campub.service | run_campub.sh | jiaoda-lidar | ✅ |
| jiaoda-control.service | run_control.sh | jiaoda-lidar | ✅ |
| jiaoda-fastlivo.service | run_fastlivo.sh | jiaoda-restamp | ✅ |
| jiaoda-grid.service | run_grid.sh | jiaoda-fastlivo | ✅ |
| jiaoda-nav.service | run_nav_simple.sh | jiaoda-fastlivo | ✅ |
| jiaoda-posebridge.service | run_pose_bridge.sh | jiaoda-fastlivo | ✅ |
| jiaoda-mission.service | run_mission.sh | jiaoda-nav | ✅（但崩溃循环） |
| jiaoda-calib.service | run_calib.sh | jiaoda-fastlivo | ❌ disabled |
| jiaoda-chassis.service | run_chassis.sh | jiaoda-lidar | ❌ disabled |

- 使能证据：`/etc/systemd/system/multi-user.target.wants/` 内有 10 个 `jiaoda-*.service -> /etc/systemd/system/...` 软链（9 月 10 日创建）。**【实测】**
- 无 `jiaoda-*.timer`、无 `.path` 单元、无用户级单元（`~/.config/systemd/user/` 不存在）。**【实测】**
- `systemctl get-default` = `graphical.target`；L4T 的图形栈与这些服务无依赖关系，**即使不登录桌面，multi-user 阶段也会启动**。**【实测 + 推断】**

### 5.2 其他机制排查结果

| 机制 | 结果 |
| --- | --- |
| `crontab -l`（sjytt） | `no crontab for sjytt`【实测】 |
| `/etc/crontab`、`/etc/cron.d/` | 只有系统默认条目（anacron/e2scrub），无 ros/jiaoda【实测】 |
| root crontab | **【需 root】** 未读 |
| `~/.config/autostart/*.desktop` | 目录不存在【实测】 |
| `/etc/xdg/autostart/` | 无 jiaoda/ros 相关项【实测】 |
| `/etc/rc.local` | 不存在【实测】 |
| `~/.bashrc` | 末尾只有 `source /opt/ros/noetic/setup.bash` 和 `source ~/rslidar_ws/devel/setup.bash`，**没有任何自动启动命令**【实测】 |
| `~/.profile`、`~/.xsessionrc`、`/etc/profile.d` | 无 ROS/jiaoda 自启内容【实测】 |
| GDM | `AutomaticLoginEnable=true`、`AutomaticLogin=sjytt`（自动登录桌面，但不启动 ROS 栈）【实测】 |
| `~/.bash_history` | 无近期 systemctl/roslaunch 记录（mtime 2026-06-18），说明本次栈不是手工起的【实测】 |

### 5.3 明确回答

> **重启 Jetson 后，这套 SLAM/导航栈会不会自动起来？**
>
> **会。** 由 systemd 在 `multi-user.target` 阶段自动拉起 10 个 `jiaoda-*.service`（内核启动后约 15 秒，Master 约 17 秒可用）。**不需要登录桌面、不需要打开终端、不需要 crontab。**
>
> 但要注意两点：
> 1. `jiaoda-mission.service` 会进入无限崩溃-重启循环（每 3~5 秒一次），日志/CPU 持续被占用；
> 2. "服务起来了"不代表"数据通了"——相机索引失效会让 FAST-LIVO 静默不出里程计（见 §11.2）。

---

## 6. ROS 环境

| 项目 | 实测值 |
| --- | --- |
| ROS 发行版 | `/opt/ros/noetic` 存在；`ROS_DISTRO=noetic`、`ROS_VERSION=1`、`ROS_PYTHON_VERSION=3` |
| Python | 3.8（Ubuntu 20.04 系统 python3） |
| `ROS_MASTER_URI` | **`http://localhost:11311`**（在 1093/1103/1092 的 `/proc/<pid>/environ` 中一致） |
| `ROS_IP` / `ROS_HOSTNAME` | **均未设置**（所以节点 XML-RPC 用主机名 `sjytt-desktop` 注册，见 `rosnode` URI） |
| 工作区 source | 服务脚本各自 source，不依赖 `.bashrc`；`console`/`fastlivo` source `~/livo2_ws/devel/setup.bash`，`lidar` source `~/unilidar_sdk2/unitree_lidar_ros/devel/setup.bash` |
| 交互 shell | `~/.bashrc` 末尾 source `noetic` + `~/rslidar_ws/devel/setup.bash`（覆盖顺序会让交互终端优先看到 rslidar 包） |
| catkin 工作区 | `~/livo2_ws`（FAST-LIVO2 overlay）、`~/unilidar_sdk2/unitree_lidar_ros`（雷达，独立工作区）、`~/rslidar_ws`（已构建、当前栈未用）、`~/unilidar_sdk`（旧版雷达 SDK） |
| `roslaunch` 版本行为 | `unitree_lidar_ros` 的 launch 里带 `respawn="true"`；`fast_livo` 的 launch 用 `rviz:=false` 关掉 RViz |

实测网络（与雷达链路相关）：

```text
eth1    192.168.1.2/24      ← 宇树雷达网段（配置里 lidar_ip=192.168.1.62, pc_ip=192.168.1.2）
wlan0   172.20.10.8/28      ← xlx
l4tbr0  192.168.55.1/24     ← USB 设备模式（本次 SSH 入口）
```

---

## 7. 构建状态

### 7.1 `~/livo2_ws`（FAST-LIVO2）

- `src/`：`FAST-LIVO2`、`rpg_vikit`；`package.xml` 共 4 个包：`FAST-LIVO2`、`rpg_vikit/vikit_py`、`vikit_common`、`vikit_ros`。【实测】
- `devel/lib/` 可执行/库（mtime 2026-09-10）：
  - `fast_livo/fastlivo_mapping`（154 416 B，**12:22**，栈实际使用）
  - `libimu_proc.so`、`liblaser_mapping.so`、`liblio.so`、`libpre.so`、`libvio.so`、`libvikit_common.so`、`libvikit_ros.so`
  - `vikit_common/test_vk_common_{triangulation,patch_score,camera}`
- `devel/.catkin` 存在；`build/` 存在（12:18），但 **`build/.catkin` 不存在**，且 `build/CATKIN_IGNORE` 是个 0 字节文件（不影响运行，重编时注意）。【实测】
- 最近构建：**2026-09-10 12:18–12:22**（`catkin_make`，见 `p1_build.sh` / `p1_fix.sh`）。【实测】
- 源码 HEAD：`FAST-LIVO2` = `0d2c034`，`rpg_vikit` = `6c886c8`（有未提交的 `config/*.yaml`、`launch/mapping_unitree_l2.launch`）。【实测】

### 7.2 `~/unilidar_sdk2/unitree_lidar_ros`（雷达驱动）

- `devel/lib/unitree_lidar_ros/unitree_lidar_ros_node`（296 768 B，**2026-06-18 16:48**）【实测】
- `build/` 存在（06-18 16:47）；`devel/.catkin` 存在；`build/.catkin` 不存在【实测】
- `src/` 是标准 catkin 工作区（`CMakeLists.txt` 软链到 `/opt/ros/noetic/share/catkin/cmake/toplevel.cmake`）
- launch：`run_without_rviz.launch`（实际使用，无 RViz）、`run.launch`、`run_lidar2.launch`（第二台雷达，未使用）
- 配置 `config.yaml`：`initialize_type: 2`（UDP 模式）、`lidar_ip: 192.168.1.62`、`pc_ip: 192.168.1.2`、`lidar_port: 6101`、`cloud_scan_num: 18`；`serial_port: /dev/ttyACM0` 仅在该文件里作为备用字段出现，**当前节点走 UDP**。【实测 + 推断】

### 7.3 其他

- `~/rslidar_ws`：build/devel 齐全（2026-06-17），当前没有任何服务使用。
- `~/Sophus_src`：265 MB（含 .git），`make install` 过（`p1_build.sh` 用 `sudo` 装 Sophus，`p1_fix.sh` 打过 `so2.cpp` 补丁）。

---

## 8. 磁盘、内存、大文件

| 项目 | 实测值 |
| --- | --- |
| 根分区 | `/dev/mmcblk0p1` 57 G，已用 11 G，可用 44 G（19%） |
| inode | 3 792 896，已用 232 332（7%） |
| 内存 | 总 61 GiB，已用 14 GiB，free 44 GiB，buff/cache 2.2 GiB，available 45 GiB |
| Swap | 30 GiB，已用 0 |
| `/home/sjytt/.ros/log` | **89 MB**（其中 `c90328e6-…` 单目录 52 MB，`ca933c96-…` 13 MB） |
| 家目录占用 | 约 601 MB（不含 `.cache`）：`Sophus_src` 265 MB、`livo2_ws` 175 MB（其中 FAST-LIVO2 160 MB，`.git` 90 MB）、`.ros` 90 MB |
| rosbag | **未发现任何 `.bag` / `.bag.active`**（`find /home/sjytt`） |
| 其他大文件 | `~/build.log` 20 KB、`~/build2.log` 21 KB、`~/wheeltec.tar.gz` 26 KB（只读位） |

结论：磁盘余量充足；**没有 rosbag 落盘机制**，故障复盘只能靠 `.ros/log` 与 journal，且当前日志无轮转（见 §9）。

---

## 9. 日志位置与命名规律

### 9.1 两套日志

1. **`~/.ros/log/`（ROS 节点日志，89 MB）**
   - 子目录：`<run-id UUID>/`，每次 `roslaunch` 创建一套；`latest` 软链指向 `ca933c96-acf7-11f1-89b0-3c6d66b13904`（本次运行，09-10 17:12 创建）。
   - latest 目录内容：
     | 文件 | 大小 | 写入者 |
     | --- | --- | --- |
     | `master.log` | 471 KB | rosmaster |
     | `rosout.log` | 13 MB | rosout（聚合日志，最大） |
     | `roslaunch-sjytt-desktop-1093.log` | 12 KB | 雷达 roslaunch |
     | `roslaunch-sjytt-desktop-1103.log` | 7 KB | FAST-LIVO roslaunch |
     | `unitree_lidar_ros_node-2-stdout.log` | 36 B | 雷达节点 stdout |
     | `rosout-1-stdout.log` | 151 B | rosout stdout |
   - 顶层 `*.log`（rospy 直连节点，文件名=节点名）：
     - `cam_publisher.log`、`grid_bridge.log`、`nav_simple.log`、`pose_bridge.log`、`cloud_restamp.log`、`chassis_gimbal_bridge.log`（**最大 592 KB，仍在写**）
     - `console_backend_<pid>_<epoch_ms>.log`（anonymous 节点名带 PID+时间戳）
     - 历史/一次性：`cmd_vel_to_pwm.log`、`calib_web_*.log`、`rostopic_*.log`、`tf_monitor_*`、`nav_gui_*`、`fwdtest_*` 等
2. **journald（stdout/stderr，`run_fastlivo.sh[2735]` 等标签）**
   - `journalctl -u jiaoda-*` 可读（用户在 `adm` 组）。
   - FAST-LIVO 的算法统计表（LIO/VIO Time）全部打到 journal，**这是排查建图问题最有用的一路**。
   - `journalctl -u jiaoda-mission` 可直接看到 `cv_bridge` 崩溃堆栈。

### 9.2 命名规律小结

| 命名 | 含义 |
| --- | --- |
| `<node>.log` | 固定名节点（非 anonymous） |
| `<node>_<pid>_<epoch_ms>.log` | `anonymous=True` 的节点 |
| `<run-id>/master.log`、`rosout.log` | 本次 roslaunch 会话 |
| `<run-id>/<node>-<N>-stdout.log` | roslaunch 捕获的节点 stdout |

⚠️ **无 logrotate、无清理策略**：`~/.ros/log` 已积累 89 MB、12 个历史 run-id，最早到 2026-06-17。长期运行需人工清理（本次只读，未清理）。

---

## 10. 网络服务与端口

| 端口 | 进程 | PID / 父进程 | 谁启动 | systemd 托管 |
| --- | --- | --- | --- | --- |
| 11311 | rosmaster | 2209 / PPID **1093**（roslaunch） | **由 `jiaoda-lidar.service` 的 roslaunch 隐式创建** | 是（经 lidar 服务） |
| 8090 | python3 console_backend | 1092 / PPID 1 | `jiaoda-console.service` → `run.sh` | 是 |
| 8095 | —（未监听） | — | `jiaoda-calib.service` 为 disabled，未启动 | 否 |
| 22 | sshd | — | 系统 ssh.service | 是 |

其他（ROS 节点 XML-RPC 随机高端口，属正常）：1092/1094/1098/1102/1103/1105/1106/1113/2287/2292/2735 各监听 1~2 个随机端口。

**关键点：ROS Master 不是独立服务**，它寄生在 `jiaoda-lidar.service` 的 roslaunch 里。因此：

- 停掉/重启 `jiaoda-lidar.service` 会连带杀掉 Master，**整栈抖动**；
- 反过来说，`jiaoda-lidar` 挂了，其余节点会因失联而退出，再被 systemd 逐个重启（`run_*.sh` 里的 `until rostopic list` 会等新 Master）。

实测 HTTP：`curl http://127.0.0.1:8090/` → `200`。`/api/ctl/status`、`/api/map`、`/api/cam/stream.mjpg` 等由 `console_backend.py` 提供。

---

## 11. 当前运行态的四个问题（恢复后必检）

### 11.1 `jiaoda-mission.service` 无限崩溃（实测，根因已定位）

```text
NRestarts=1806+   ActiveState=activating / SubState=auto-restart   Result=exit-code
journal: nav_mission.py line 7, in <module>  from cv_bridge import CvBridge
         SystemError: initialization of cv_bridge_boost raised unreported exception
```

根因（**实测复现**）：

```bash
python3 -c "import cv_bridge"      # ✗ SystemError
python3 -c "import cv2, cv_bridge" # ✓ OK
```

`nav_mission.py` 的 import 顺序是 `import cv_bridge`（第 7 行）在 `import cv2`（第 8 行）之前；这台机器上 `cv_bridge_boost` 必须在 `cv2` 之后加载。`cam_publisher.py` 恰好是 `import ... cv2` 在前，所以同环境下正常。**修复方法：把 `import cv2` 移到 `import cv_bridge` 之前（或 `import cv2` 后 `import cv_bridge`）**——本次只读审计**未修改**。

影响：航点任务/拍照功能完全不可用，且每 3 秒重启一次，持续写 journal。

### 11.2 相机索引漂移导致 SLAM 静默失效（实测）

- `run_campub.sh`：`export CAMPUB_INDEX=2` → `cv2.VideoCapture(2)` → `/dev/video2`
- 实际设备：`/dev/video0,1,3,4,5,6,7,8`（**没有 2**；`fuser /dev/video2` → "does not exist"）
- 现象链：`/unilidar/cloud` 12 Hz ✅、`/synced/cloud` 12 Hz ✅、`/cmd_vel` 20 Hz ✅、`/tf` 506 Hz ✅，但
  `/left_camera/image` **无消息** → `/aft_mapped_to_init` **无消息** → `/cloud_registered` **无消息** → `/slam_pose` **无消息**。
- `cam_publisher` 进程本身活着（rospy 节点已注册、日志正常），`cap.read()` 失败后只是空转，**不报错、不退出**，因此 systemd 也不会重启它。
- 时间线佐证：`/dev/video*` 节点时间戳为 09-10 17:49（按 §11.3 换算约为**今天 11:19**），说明本次运行中发生过一次 USB 重新枚举、编号随之改变；`journalctl -u jiaoda-fastlivo` 在 09-10 17:15:46 仍打出 `[INFO] Get image, its header time: …`，说明**开机初期相机是有帧的**，之后才因重枚举丢失 `/dev/video2`。

修复方向（未执行）：把 `CAMPUB_INDEX` 改成实际可用的索引，或用 udev 规则按 USB 物理路径绑定固定软链（README K9 有四个摄像头的物理路径）。

### 11.3 开机时钟错乱（实测现象，机制未验证）

| 证据 | 值 |
| --- | --- |
| `/proc/uptime` / `uptime -s` | 9 062 s / 2026-10-21 10:43:20 |
| `/proc/stat btime` | 1792550599 → 2026-10-21 10:43:19 CST |
| systemd `ExecMainStartTimestamp`（9 个服务） | **2026-09-10 17:12:46** |
| `/proc/1092`、`/proc/1093` 的 ctime | **2026-09-10 17:12:46** |
| `journalctl -b` 首条 | 2026-09-10 17:15:46 |
| `systemd-timesyncd` 首次同步 | **2026-10-21 11:32:46**（1.pool.ntp.org） |
| `who -b` / `last reboot` | 1970-01-01 08:00（utmp 在时钟还是 1970 时写入） |
| 当前时间 | 2026-10-21 13:1x CST，RTC/NTP 已同步 |

**【推测·未验证】** 开机时 RTC 无有效时间，系统回落到 2026-09-10 17:12（约上次关机时刻）；服务在此时刻启动并写日志；约 49 分钟后 `systemd-timesyncd` 校正，时钟**前跳约 40 天 17.5 小时**。

**运维影响（重要）**：

- 重启后 **11:32 之前**的 `~/.ros/log/*`、`journalctl` 时间戳都要 **+40 天 17.5 小时** 才是真实时间；
- 不能靠日志时间戳判断启动顺序，必须用 `systemctl show -p ActiveEnterTimestampMonotonic` 或 `ps -o etime`；
- 故障复盘时先确认 `timedatectl` 的 `System clock synchronized: yes`，否则结论会被时间误导。

### 11.4 `jiaoda-control` 的串口名不匹配（沿用 README K24，本次未操作）

`chassis_gimbal_bridge.py` 默认 `CTL_PORT=/dev/ttyCH343USB0`，但该芯片以 CDC 模式枚举为 `/dev/ttyACM0`，因此桥接会每 3 秒重试打开、始终连不上。**本次未打开任何串口、未验证当前是否能连**（禁止项）。替代脚本 `cmd_vel_to_pwm.py` 写死 `/dev/ttyACM0`，但对应服务 `jiaoda-chassis.service` 是 disabled。

---

## 12. 恢复步骤草案（从"刚开机、什么都没跑"到"完整栈起来"）

> 前提：**Jetson 已经开机并完成 systemd 启动**。以下命令为运维手册内容，本次审计**未执行**。

### 方案 A：什么都不做（推荐，验证自启）

```bash
# 1. 等待约 20 秒
sleep 20
# 2. 看 10 个单元是否 active
systemctl list-units 'jiaoda-*' --no-pager
# 3. 看 Master 与 8090
ss -ltnp | grep -E '11311|8090'
```

预期：9 个 `active (running)` + 1 个 `activating (auto-restart)`（mission）。

### 方案 B：systemd 手动拉起（服务被 stop 过、或想按序重启）

```bash
source /opt/ros/noetic/setup.bash

# ① 先起雷达（它同时创建 ROS Master）
sudo systemctl start jiaoda-lidar.service
until rostopic list >/dev/null 2>&1; do sleep 1; done   # 约 2~5 秒

# ② 起依赖 Master 的节点（脚本内部还会各自等话题）
sudo systemctl start jiaoda-restamp.service jiaoda-campub.service jiaoda-control.service
sudo systemctl start jiaoda-fastlivo.service
sudo systemctl start jiaoda-grid.service jiaoda-nav.service jiaoda-posebridge.service jiaoda-console.service

# ③ mission 先别起（已知崩溃）；修好再起
# sudo systemctl start jiaoda-mission.service
```

停整套（顺序相反，**必须先停别人再停 lidar**，否则 Master 一死全体抖动）：

```bash
sudo systemctl stop jiaoda-console jiaoda-mission jiaoda-posebridge jiaoda-nav \
  jiaoda-grid jiaoda-campub jiaoda-control jiaoda-fastlivo jiaoda-restamp jiaoda-lidar
```

> 注意：`Restart=always` 意味着 `kill -9` 后 3~5 秒会被拉起；**只有 `systemctl stop` 才能让它保持停止**。

### 方案 C：纯手动前台拉起（调试用，不依赖 systemd）

按依赖顺序开多个终端（每个脚本会自己等前置话题）：

```bash
# 终端 1：雷达 + Master
bash ~/jiaoda/run_lidar.sh
# 终端 2：点云转发
bash ~/jiaoda/run_restamp.sh
# 终端 3：SLAM（需要相机图像，先确认 /left_camera/image 有帧）
bash ~/jiaoda/run_fastlivo.sh
# 终端 4：栅格
bash ~/jiaoda/run_grid.sh
# 终端 5：导航
bash ~/jiaoda/run_nav_simple.sh
# 终端 6：位姿桥
bash ~/jiaoda/run_pose_bridge.sh
# 终端 7：相机（先改对索引）
CAMPUB_INDEX=<可用索引> bash ~/jiaoda/run_campub.sh
# 终端 8：控制台
bash ~/jiaoda/run.sh
```

⚠️ 不要用 `~/dog_backup/start_all.sh`：它会 `pkill -9 -f "ros|slam|lio|..."`，把当前栈连同 SSH 会话里的一切相关进程杀掉。

### 方案 D：恢复后验证清单（按"数据链"顺序）

| 检查 | 命令 | 通过标准 |
| --- | --- | --- |
| Master | `rostopic list` | 能列出话题，不报 `Unable to communicate with master` |
| 节点 | `rosnode list` | ≥10 个节点 |
| 雷达 | `rostopic hz /unilidar/cloud` | ≈12 Hz |
| 转发 | `rostopic hz /synced/cloud` | ≈12 Hz |
| 相机 | `rostopic hz /left_camera/image` | **必须 >0**（当前 0，见 §11.2） |
| SLAM | `rostopic hz /aft_mapped_to_init` | >0（当前 0） |
| 栅格 | `rostopic hz /cloud_registered` | >0（当前 0） |
| 位姿 | `rostopic hz /slam_pose` | >0（当前 0） |
| 控制台 | `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/` | `200` |
| 端口 | `ss -ltnp \| grep -E '11311\|8090'` | 两个都在 |
| 时间 | `timedatectl \| grep synchronized` | `yes` |

判定原则：**`/unilidar/cloud` 有、`/left_camera/image` 无 ⇒ 相机索引问题，不是 SLAM 问题。**

---

## 13. 重启后的恢复清单（可直接复制执行）

```bash
# ===== 0. 登录（USB 网 192.168.55.1）=====
ssh sjytt@192.168.55.1

# ===== 1. 等自启完成（约 20 s），确认单元状态 =====
sleep 20
systemctl list-units 'jiaoda-*' --no-pager
timedatectl | grep -E 'synchronized|Local time'

# ===== 2. 确认 Master / 控制台 =====
source /opt/ros/noetic/setup.bash
ss -ltnp | grep -E '11311|8090'
rostopic list >/dev/null && echo "MASTER_OK"
curl -s -o /dev/null -w 'CONSOLE_HTTP=%{http_code}\n' http://127.0.0.1:8090/

# ===== 3. 数据链自检 =====
rosnode list
timeout 5 rostopic hz /unilidar/cloud        # 期望 ~12 Hz
timeout 5 rostopic hz /synced/cloud          # 期望 ~12 Hz
timeout 5 rostopic hz /left_camera/image     # 期望 >0，当前为 0 → 查相机索引
timeout 5 rostopic hz /aft_mapped_to_init    # 期望 >0，当前为 0
timeout 5 rostopic hz /slam_pose             # 期望 >0，当前为 0

# ===== 4. 若某个单元没起来（按依赖顺序补起）=====
sudo systemctl start jiaoda-lidar.service
until rostopic list >/dev/null 2>&1; do sleep 1; done
sudo systemctl start jiaoda-restamp.service jiaoda-campub.service jiaoda-control.service \
  jiaoda-fastlivo.service jiaoda-grid.service jiaoda-nav.service \
  jiaoda-posebridge.service jiaoda-console.service

# ===== 5. 已知缺陷处理（需要写权限，本次审计未执行）=====
# 5.1 mission 崩溃：把 nav_mission.py 的 import cv2 提到 import cv_bridge 之前
#     sudo systemctl restart jiaoda-mission.service
# 5.2 相机索引：确认可用 /dev/videoN 后改 run_campub.sh 的 CAMPUB_INDEX（或建 udev 软链）
#     sudo systemctl restart jiaoda-campub.service
# 5.3 底盘串口：CTL_PORT 指向 /dev/ttyACM0（注意 open 会复位 ESP32，先架空轮子、关遥控）
#     sudo systemctl restart jiaoda-control.service

# ===== 6. 关闭开机自启（如需临时改为手动）=====
# sudo systemctl disable jiaoda-lidar jiaoda-restamp jiaoda-fastlivo jiaoda-campub \
#   jiaoda-control jiaoda-grid jiaoda-nav jiaoda-posebridge jiaoda-console jiaoda-mission
```

---

## 14. 实测 / 推测 对照

| 结论 | 定性 | 依据 |
| --- | --- | --- |
| 10 个 `jiaoda-*.service` 已 enable，开机自动启动 | **实测** | `list-unit-files`、`multi-user.target.wants` 软链、本次开机进程 |
| 重启后栈会自动起来 | **实测** | 开机后 15 s 内 9 个服务 active、Master :11311 可用 |
| 启动顺序 = console/lidar 最先，其余并行 | **实测** | `ActiveEnterTimestampMonotonic` 15.037–15.066 s |
| Master 由 lidar 的 roslaunch 创建 | **实测** | `rosmaster` 的 PPID = 1093 |
| 无 crontab / autostart / rc.local 自启 | **实测** | 逐项命令输出（root crontab 除外） |
| mission 崩溃根因是 cv_bridge/cv2 import 顺序 | **实测** | 两种 import 顺序的对照复现 |
| 相机索引 2 不存在导致链路中断 | **实测** | 设备列表无 `/dev/video2`，四个话题均无消息 |
| 开机时钟早 40 天、11:32 被 NTP 校正 | **实测现象** | `btime` vs `/proc` ctime vs timesyncd 日志 |
| 时钟回落到上次关机时刻（RTC 无电池） | **推测·未验证** | 现象一致，但未查 RTC/fake-hwclock |
| 雷达走 UDP 而非串口 | **推测·未验证** | `initialize_type: 2` + UDP IP 配置 + 12 Hz 点云；未抓包 |
| 相机在时钟 09-10 17:49（约今天 11:19）重新枚举导致编号变化 | **推测·未验证** | `/dev/video*` mtime + 现有编号缺 2 |
| root crontab 无 jiaoda 条目 | **需 root·未验证** | 无权读取 `/var/spool/cron/crontabs/root` |

---

## 附录：路径速查

| 用途 | 路径 |
| --- | --- |
| 应用脚本 | `/home/sjytt/jiaoda/` |
| systemd 单元 | `/etc/systemd/system/jiaoda-*.service` |
| ROS 日志 | `/home/sjytt/.ros/log/`（`latest` 软链） |
| ROS 环境 | `/opt/ros/noetic/` |
| FAST-LIVO 工作区 | `/home/sjytt/livo2_ws/`（包：`fast_livo`、`vikit_*`） |
| 雷达工作区 | `/home/sjytt/unilidar_sdk2/unitree_lidar_ros/` |
| 雷达配置 | `.../src/unitree_lidar_ros/config/config.yaml` |
| 地图/路线 | `/home/sjytt/jiaoda/maps/floor1.npz`、`/home/sjytt/jiaoda/routes/`（空） |
| 运行时 IPC | `/dev/shm/jiaoda_*.json`、`/dev/shm/jiaoda_map.png` |
| 控制台页面 | `http://192.168.55.1:8090/`（代码：`console.html`） |
| 风险脚本（勿执行） | `/home/sjytt/dog_backup/start_all.sh` |
