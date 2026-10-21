# Jetson `~/jiaoda` 源码接口审计（只读）

- 审计对象：`sjytt@192.168.55.1:/home/sjytt/jiaoda`，覆盖 **28 个源文件**（12 个顶层 `.py`、12 个 `run*.sh`、`calib/` 下 3 个 `.py` + 1 个 `.sh`），共 2344 行。
- 审计方式：逐个读取源码（`cat -n` / 本地副本逐行核对）+ 只读的 ROS 图查询、`systemd` 状态、`/proc/<pid>/fd`、`/dev`、日志。
- **只读声明**：全程未启动/停止任何进程，未执行 `roslaunch`/`rostopic pub`，未向 Jetson 写入任何文件，未使用 `sudo`，**未打开任何 `/dev/ttyACM*`、`/dev/ttyUSB*` 串口**。
- 采集时间：2026-10-21。运行时事实以当时进程/话题快照为准，详见文末“关键结论”。
- 说明：本目录下没有 ROS service、没有 `rospy.get_param`、没有任何 `__ns`/`__name`/话题重映射参数；**全部可配置项只有环境变量、`argparse` 参数与源码常量**。

---

## 1. 总表：脚本 → 程序 → 作用

| 启动脚本 | 行数 | 启动的程序 | 作用 | systemd 单元 | 开机启用 |
| --- | --- | --- | --- | --- | --- |
| `run.sh` | 4 | `console_backend.py` | 巡检控制台 HTTP 后端 + MJPEG 视频 | `jiaoda-console` | 是 |
| `run_campub.sh` | 5 | `cam_publisher.py` | USB 相机 → `/left_camera/image` | `jiaoda-campub` | 是 |
| `run_control.sh` | 4 | `chassis_gimbal_bridge.py` | `/cmd_vel` + `/jiaoda/gimbal` → 主控串口 | `jiaoda-control` | 是 |
| `run_chassis.sh` | 4 | `cmd_vel_to_pwm.py` | 旧版 `/cmd_vel` → PWM 串口（协议已过期） | `jiaoda-chassis` | **否（disabled）** |
| `run_calib.sh` | 4 | `calib/calib_web.py` | 相机内参/相机-雷达外参标定网页 | `jiaoda-calib` | **否（disabled）** |
| `run_grid.sh` | 4 | `grid_bridge.py` | 点云 + 里程计 → 2D 占据栅格 `/map` | `jiaoda-grid` | 是 |
| `run_fastlivo.sh` | 5 | `roslaunch fast_livo mapping_unitree_l2.launch rviz:=false` | FAST-LIVO2 激光惯性里程计 | `jiaoda-fastlivo` | 是 |
| `run_lidar.sh` | 4 | `roslaunch unitree_lidar_ros run_without_rviz.launch` | 宇树 L2 雷达驱动 | `jiaoda-lidar` | 是 |
| `run_mission.sh` | 4 | `nav_mission.py` | 多点位巡检任务（航点→拍照→云台） | `jiaoda-mission` | 是（**崩溃重启循环**） |
| `run_nav_simple.sh` | 4 | `nav_simple.py` | `A*` + Pure Pursuit + DWA 导航 | `jiaoda-nav` | 是 |
| `run_pose_bridge.sh` | 4 | `pose_bridge.py` | `/aft_mapped_to_init` → `/slam_pose` + `/imu` | `jiaoda-posebridge` | 是 |
| `run_restamp.sh` | 5 | `cloud_restamp.py` | 雷达点云时间戳重打 → `/synced/cloud` | `jiaoda-restamp` | 是 |

补充说明：

| 脚本 | 环境变量 | 前置等待条件 | 备注 |
| --- | --- | --- | --- |
| `run.sh` | 无 | 无（直接 `exec`） | `source /opt/ros/noetic`，`source ~/livo2_ws/devel/setup.bash 2>/dev/null` 允许失败 |
| `run_campub.sh` | `CAMPUB_INDEX=2` | `until rostopic list` 成功（需 ROS Master 已起） | 索引 2 现在已无对应设备，见 §2.2 |
| `run_control.sh` | 无（依赖 `CTL_PORT` 默认值） | `until rostopic list` | 默认端口不存在，见 §2.3 |
| `run_chassis.sh` | 无 | `until rostopic list` | 与固件协议不符且无看门狗，禁用状态是正确选择 |
| `run_calib.sh` | `CALIB_CAM=2` | 无 | 不等待 ROS，但 `calib_web` 需要 `/unilidar/cloud` |
| `run_grid.sh` | 无 | 等待话题 **`/cloud_registered`**（`rostopic list \| grep -q`） | 该话题由 `laserMapping` 发布，即要求 FAST-LIVO 先就绪 |
| `run_fastlivo.sh` | 无 | 等待话题 **`/synced/cloud`** | 即要求 `cloud_restamp` 先就绪（`After=jiaoda-restamp.service`） |
| `run_lidar.sh` | 无 | 无 | `source ~/unilidar_sdk2/unitree_lidar_ros/devel/setup.bash`（该路径存在） |
| `run_mission.sh` | 无 | `until rostopic list` | 见 §2.7 崩溃原因 |
| `run_nav_simple.sh` | 无 | `until rostopic list` | — |
| `run_pose_bridge.sh` | 无 | `until rostopic list` | — |
| `run_restamp.sh` | 无 | 先等 `rostopic list`，再等话题 `/unilidar/cloud` | 两级等待，最健壮 |

启动依赖链（systemd `After=`，`/etc/systemd/system/jiaoda-*.service`）：

```text
jiaoda-lidar ──> jiaoda-campub
             ├─> jiaoda-restamp ──> jiaoda-fastlivo ──> jiaoda-grid
             │                                     ├─> jiaoda-nav
             │                                     ├─> jiaoda-posebridge
             │                                     └─> jiaoda-calib(disabled)
             └─> jiaoda-control
jiaoda-nav ──> jiaoda-mission
```

---

## 2. 逐程序接口清单

### 2.1 `console_backend.py`（304 行）

**职责**：巡检控制台的单文件 HTTP 后端（静态页 `console.html` + 位姿/地图/相机/云台/任务 REST API + ROS 桥），无框架依赖，线程式 `ThreadingHTTPServer`。

**ROS 接口**

| 方向 | 话题 | 类型 | QoS/备注 | 行号 |
| --- | --- | --- | --- | --- |
| 发布 | `CMD_VEL_TOPIC`（默认 `/cmd_vel`） | `geometry_msgs/Twist` | queue 1 | 88 |
| 发布 | `/jiaoda/gimbal` | `std_msgs/Int16MultiArray` | queue 1，`data=[pitch,yaw]` | 89, 160 |
| 订阅 | `/aft_mapped_to_init` | `nav_msgs/Odometry` | queue 1 | 13, 92 |
| 订阅 | `/Odometry` | `nav_msgs/Odometry` | **无发布者（死订阅）** | 13, 92 |
| 订阅 | `/lio_sam/mapping/odometry` | `nav_msgs/Odometry` | **无发布者（死订阅）** | 13, 92 |

**可配置项**

| 变量 | 默认值 | 含义 | 行号 |
| --- | --- | --- | --- |
| `CONSOLE_PORT` | `8090` | HTTP 监听端口（绑 `0.0.0.0`） | 12, 298 |
| `CMD_VEL_TOPIC` | `/cmd_vel` | 速度指令话题名 | 14 |
| `CAM_INDEX` | `0` | OpenCV 相机索引（当前 `/dev/video0` 有效） | 15, 131 |
| `GIMBAL_PORT` | `""` | **定义了但全文未使用**（云台只走 ROS） | 16 |
| `ROUTES_DIR` | `~/jiaoda/routes` | 路线 JSON 目录（启动时 `makedirs`） | 7, 9 |
| `MAPS_DIR` | `~/jiaoda/maps` | 地图目录（仅 `makedirs`，未实际读写） | 8, 10 |
| `SHM_MAP` | `/dev/shm/jiaoda_map.png` | 地图 PNG | 28 |
| `SHM_SENSORS` | `/dev/shm/jiaoda_sensors.json` | 电池/传感器缓存 | 29 |

**常量 / 周期 / 坐标系**

| 项 | 值 | 行号 |
| --- | --- | --- |
| 默认控制参数 `pspeed` | `0.55`（m/s 缩放系数） | 20 |
| 默认控制参数 `pyaw` | `40`（°/s，代码里再转弧度） | 20 |
| `pclear` / `pstop` | `0.25` / `0.5`（**已定义、从未被读取**） | 20 |
| 速度换算 | `linear.x = v*pspeed`；`angular.z = w*radians(pyaw)` | 113–114 |
| 云台映射 | `tilt[-45,45]→pitch[-30,30]`；`pan[-90,90]→yaw[-30,30]` | 156–157 |
| 相机编码 | JPEG quality 70，采集节流 `0.05 s`（≈20 fps） | 141, 144 |
| MJPEG 推送 | 每帧 `sleep 0.06`（≈16 fps） | 292 |
| 里程计频率估计 | 取最近 30 帧做滑窗 | 103–107 |
| TF/frame | 不发布 TF；位姿直接用 odom 的 `x,y,yaw`（不转 frame） | 99–102 |
| ROS 节点名 | `console_backend` + `anonymous=True`（实为 `console_backend_1092_...`） | 87 |

**HTTP API（GET）**

| 路由 | 返回 | 消费方 | 行号 |
| --- | --- | --- | --- |
| `/`、`/index.html`、`/console.html` | `console.html` 原文 | 浏览器 | 190–200 |
| `/api/pose` | `{x,y,th}` 或 `{}` | `console.html:390` | 201–202 |
| `/api/ctl/status` | `{bat,temp,hz,nav,ros,sensors}` | `console.html:390` | 203–206 |
| `/api/cam/stream.mjpg` | `multipart/x-mixed-replace` | `console.html:397` | 207–208, 279–294 |
| `/api/nav/status` | 透传 `/dev/shm/jiaoda_nav_status.json`，失败回落 `{state:"idle",cur:0,total:0}` | `console.html:391` | 209–213 |
| `/api/mapinfo` | `/dev/shm/jiaoda_map.json`，失败 204 | `console.html:404` | 214–218 |
| `/api/map` | `/dev/shm/jiaoda_map.png`，失败 204 JSON | `console.html:404` | 219–230 |

**HTTP API（POST，body 为 JSON）**

| 路由 | body | 行为 | 消费方 | 行号 |
| --- | --- | --- | --- | --- |
| `/api/ctl/drive` | `{v,w}` | 发布 `/cmd_vel`；**无任何限幅** | `console.html:373,345` | 236–237 |
| `/api/ctl/param` | 任意键值 | `state["params"].update(b)`，**任意键都接受** | `console.html:377` | 238–240 |
| `/api/ctl/calib_heading` | `{}` | **空实现**，直接返回 `ok:true` | `console.html:384` | 241–242 |
| `/api/map/start` | — | 仅置 `state["mapping"]=True`，**不下发任何指令** | `console.html:382` | 245–246 |
| `/api/map/freeze` | — | 仅置本地标志，**不影响 `grid_bridge`** | `console.html:382` | 247–248 |
| `/api/map/clear` | — | 写 `/dev/shm/jiaoda_map_clear` | `console.html:382` | 249–250 |
| `/api/map/save` | `{name}` | 写 `/dev/shm/jiaoda_map_save` | `console.html:382` | 251–253 |
| `/api/map/load` | `{name}` | 写 `/dev/shm/jiaoda_map_load` | `console.html:382` | 254–255 |
| `/api/gimbal` | `{p,t}` | 发布 `/jiaoda/gimbal` | `console.html:361` | 257–258 |
| `/api/nav/start` | `{wps,route}` | 写 `/dev/shm/jiaoda_mission.json` + `jiaoda_nav_cmd="start"` | `console.html:343` | 259–263 |
| `/api/nav/cancel` | — | 写 `jiaoda_nav_cmd="cancel"` | `console.html:345` | 264–266 |
| `/api/route/save` | 任意（UI 传 waypoint 数组） | **文件名固定 `default`**，忽略请求里的 name | `console.html:325` | 267–270 |
| `/api/route/load` | `{name}` | 读 `routes/<name>.json`，缺省 `default` | UI 未真正调用（仅日志） | 271–276 |

**安全/兜底**

| 机制 | 阈值/行为 | 行号 |
| --- | --- | --- |
| ROS Master 断线检测 | 每 `3 s` 轮询 `rosgraph.is_master_online()`；在线后自动 `init_node` 重连 | 68–80 |
| Master 掉线处置 | `os._exit(0)` 主动退出，交给 systemd 重启 | 77–79 |
| 传感器缓存过期 | `/dev/shm/jiaoda_sensors.json` 超过 **5 s** 未更新则视为空 | 45–47 |
| 相机断流 | `cap.read()` 失败 → 释放后 `1 s` 重开（索引固定，不遍历） | 137–147 |
| HTTP 错误处理 | `_body()` 解析失败静默回 `{}` | 179–186 |

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| C1 | 服务绑 `0.0.0.0:8090` 且**无任何认证**，同网段即可发 `/api/ctl/drive` 直接驱动底盘 | 298 |
| C2 | `/api/ctl/drive` 对 `v,w` 不做限幅、不做类型校验，`v=100` 会直接乘 `pspeed` 下发 | 236–237 |
| C3 | `/api/ctl/param` 允许写入 `state["params"]` 任意键；`pclear`/`pstop` 无人读取，属“假参数” | 238–240, 20 |
| C4 | `/api/ctl/calib_heading` 是空实现，前端却提示“航向标定完成 ✓” | 241–242 |
| C5 | `/api/map/start`、`/api/map/freeze` 只改本地变量，`grid_bridge` 永远在积分 → 建图“开始/冻结”按钮无效 | 245–248 |
| C6 | `/api/nav/start` 写的两个文件只有 `nav_mission` 会读，而 `nav_mission` 正在崩溃（§2.7）；`nav_simple` 完全不读这两个文件 → 网页“开始巡检”实际无效 | 259–263 |
| C7 | `/api/route/save` 固定写 `default.json`，与前端传的 `name` 无关；`routes/` 目录当前为空 | 267–270 |
| C8 | 同时订阅 `/aft_mapped_to_init`、`/Odometry`、`/lio_sam/mapping/odometry` 三个话题，后两个**永远无数据**，位姿实际只来自第一个 | 13 |
| C9 | `GIMBAL_PORT` 定义后从未使用，`gimbal_driver.py` 根本没被本进程引用 | 16 |
| C10 | 位姿直接用 odom 的 `pose`，未做 `frame_id` 校验/变换；若 SLAM 输出为 `camera_init` 而地图为 `map`，两者混用无告警 | 99–102 |

---

### 2.2 `cam_publisher.py`（28 行）

**职责**：把一路 USB/UVC 相机以 MJPG 1280×720 转成 ROS `sensor_msgs/Image`（`bgr8`）发布，15 Hz。

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 发布 | `CAMPUB_TOPIC`（默认 `/left_camera/image`），`sensor_msgs/Image`，queue 1 | 7, 11 |
| 订阅 | 无 | — |
| Service | 无 | — |
| `CAMPUB_INDEX` | 默认 `2`；`run_campub.sh` 显式设为 `2` | 6 |
| `CAMPUB_TOPIC` | 默认 `/left_camera/image` | 7 |
| 采集格式 | `CAP_V4L2`，FOURCC `MJPG`，1280×720 | 13–16 |
| 频率 | `rospy.Rate(15)` | 17 |
| `frame_id` | 固定字符串 `camera`（该 frame 不在任何 TF 树中） | 23 |
| 时间戳 | `rospy.Time.now()`（不是相机曝光时刻） | 22 |

**安全/兜底**：**没有任何兜底**。`cap.read()` 失败时只是跳过本次发布，不重开设备、不打印日志、不退出。

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| P1 | **默认索引 2 与实机不符**：当前 `/dev/video*` 只有 `0,1,3,4,5,6,7,8`，没有 `video2`（四路 UVC 各自枚举出两个节点，索引 2 被跳过）。重启本节点将直接打不开设备 | 6, 13 |
| P2 | **进程持有已消失设备的 fd**：PID 1094 的 fd 10 指向 `/dev/video2 (deleted)`，即开机时 video2 存在、后来被重新枚举掉了。节点不会重连，`/left_camera/image` 有发布者但**没有数据** | 18–25 |
| P3 | 无 `cap.isOpened()` 判断、无失败计数、无 `logwarn`，故障完全静默 | 13–25 |
| P4 | 无 `rospy.on_shutdown` 释放 `cap`（进程被 kill 时 fd 可能残留） | — |
| P5 | `frame_id="camera"` 与 FAST-LIVO 配置（`img_topic`）之间无 TF 关联，纯靠外参 yaml，重定位时无法追溯 | 23 |

---

### 2.3 `chassis_gimbal_bridge.py`（72 行）

**职责**：唯一与实车主控固件协议匹配的桥接器——把 `/cmd_vel` 与 `/jiaoda/gimbal` 压成一行 5 字段 ASCII 帧，20 Hz 写串口，同时把主控回传按行转成 `/jiaoda/esp_tel`。

**ROS 接口**

| 方向 | 话题 | 类型 | 说明 | 行号 |
| --- | --- | --- | --- | --- |
| 订阅 | `/cmd_vel` | `geometry_msgs/Twist` | queue 1，`t=clamp(vx*THR_K)`，`s=clamp(wz*STR_K)` | 24–26, 50 |
| 订阅 | `/jiaoda/gimbal` | `std_msgs/Int16MultiArray` | `p=data[0]`（俯仰）、`y=data[1]`（偏航），各自 clamp ±30 | 30–31, 51 |
| 发布 | `/jiaoda/esp_tel` | `std_msgs/String` | queue 5，主控上行原始行；**当前无任何订阅者** | 42, 49 |

**可配置项**

| 变量 | 默认值 | 含义 | 行号 |
| --- | --- | --- | --- |
| `CTL_PORT` | `/dev/ttyCH343USB0` | **实机上不存在此节点**；CH343 已被 `cdc_acm` 接管为 `/dev/ttyACM0` | 8 |
| `THR_K` | `55` | 线速度 → 油门量纲系数 | 10 |
| `STR_K` | `45` | 角速度 → 转向量纲系数 | 11 |
| `BAUD`（常量） | `115200` | 8N1，`timeout=0.1`，`write_timeout=0.3` | 9, 54 |

**串口协议（下行，20 Hz）**

```text
"%d,%d,%d,%d,%d\n" % (t, s, p, y, chk)      # 行 66
t = throttle ∈ [-30,30]   (clamp, 行 18–19)
s = steer    ∈ [-30,30]
p = pitch    ∈ [-30,30]   (来自 /jiaoda/gimbal data[0])
y = yaw      ∈ [-30,30]   (来自 /jiaoda/gimbal data[1])
chk = t + s + p + y       (行 64，明文求和，未取模、可能为负)
```

与主控固件自述格式 `throttle,steer,pitch,yaw,checksum`（README K22）字段顺序一致；**但 `chk` 的算法未经固件侧验证**，为二次开发首要确认点。

**安全/兜底**

| 机制 | 阈值/行为 | 行号 |
| --- | --- | --- |
| 速度看门狗 | `/cmd_vel` 超过 **0.5 s** 未更新 → `t=s=0`（仅油门/转向清零） | 61–62 |
| 云台看门狗 | **无**：`p/y` 保持最后一次值，重启/失联后不会回中 | 63 |
| 串口打开重试 | 失败后 `sleep 3` 无限重试，`logwarn` **未做节流**（每 3 s 一条，实测日志刷屏） | 52–56 |
| 写失败 | 静默 `pass`，不重连、不清零 | 65–68 |
| 限幅 | 全部量都 clamp 到 ±30 | 18–19 |

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| G1 | **默认端口 `ttyCH343USB0` 与实机不符**（当前只有 `/dev/ttyACM0` 与 `/dev/ttyACM1`），日志每 3 s 一条 `SerialException(2, ... No such file or directory)`，底盘与云台链路全程未建立；因此 `/cmd_vel` 实际无人消费 | 8, 52–56 |
| G2 | `THR_K=55` 与 `clamp(±30)` 组合：`abs(vx) > 0.545` 即饱和，速度环实际是“开关量”，中间段分辨率极低 | 10, 18 |
| G3 | 云台无失联回中，主控重启后云台停在最后位置 | 63 |
| G4 | 下行 `chk` 为负时（`t+s+p+y<0`）会输出 `-12` 这类带负号的校验字段，若固件按 `uint8` 解析会丢帧 | 64–66 |
| G5 | 上行不做校验和验证、不做帧头过滤，任何一行文本都会进 `/jiaoda/esp_tel` | 38–42 |
| G6 | 打开串口会拉低 DTR/RTS 导致 ESP32 复位一次（README K25），当前端口打不开反而避免了反复复位 | 53–54 |

---

### 2.4 `cmd_vel_to_pwm.py`（52 行，systemd 已禁用）

**职责**：旧版底盘驱动，把 `/cmd_vel` 直接换算成左右轮 PWM，按 `"left,right\n"` 写串口。

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 订阅 | `/cmd_vel`（`Twist`，queue 1） | 45 |
| 发布 | 无 | — |
| 串口 | **硬编码 `/dev/ttyACM0`**，115200 | 7–8 |
| 协议 | `"%d,%d\n" % (left,right)`，PWM `1000..2000`，中位 `1500` | 9–12, 26 |
| 换算 | `left=1500+vx*120-wz*120`，`right=1500+vx*120+wz*120`，先 `±180` 再 `1000..2000` clamp | 21–24 |
| 启动 | `setDTR(False)`、`setRTS(False)`、`sleep 2`、先发一次 `1500,1500` | 40–49 |
| 退出 | 发 `1500,1500`、`sleep 0.1`、`close()` | 30–35 |

**安全/兜底**

| 机制 | 阈值/行为 | 行号 |
| --- | --- | --- |
| 速度看门狗 | **完全没有**：`/cmd_vel` 停发后最后一个 PWM 值永久保持 | 18–28 |
| 限幅 | `±180`（即 `1320..1680`）与 `1000..2000` 双重 clamp | 23–24 |
| 串口异常 | 写失败静默 `pass`；打开失败直接抛异常退出（由 systemd 重启） | 25–28, 39 |
| 退出清零 | 仅 `on_shutdown` 时发中位 | 30–35 |

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| M1 | **协议与固件不符**：固件要求 `throttle,steer,pitch,yaw,checksum` 5 字段，本程序只发 2 字段 PWM，接上也不会被正确解析 | 26 |
| M2 | 硬编码 `/dev/ttyACM0` 正是主控控制口，**启动即打开会复位 ESP32**，且与 `chassis_gimbal_bridge` 争抢同一端口 | 7, 39 |
| M3 | **无速度看门狗**：一旦 `/cmd_vel` 中断（导航崩溃/暂停），底盘会按最后一条指令持续运动，是本目录最危险的缺陷 | 18–28 |
| M4 | `run_chassis.sh` 仍存在且指向它，误执行 `systemctl start jiaoda-chassis` 即会与 `jiaoda-control` 抢串口 | `run_chassis.sh:4` |
| M5 | 速度换算方向与 `chassis_gimbal_bridge` 的 `throttle/steer` 语义不同（这里左右轮差速，那里油门+转向），两者不可混用 | 21–22 |

---

### 2.5 `chassis_bridge.py`（159 行，**未被任何脚本引用**）

**职责**：更早一代 ESP32 桥接（`M`/`A` 指令 + 19 字段 `R` 回传），并写 `/dev/shm/jiaoda_sensors.json` 供控制台读电池。

**ROS 接口**

| 方向 | 话题 | 类型 | 行号 |
| --- | --- | --- | --- |
| 发布 | `/jiaoda/rc` | `std_msgs/Int16MultiArray`（10 通道遥控） | 152 |
| 发布 | `/jiaoda/sensors` | `std_msgs/Int16MultiArray`（8 通道传感器） | 153 |
| 订阅 | `/cmd_vel` | `geometry_msgs/Twist` | 154 |
| 订阅 | `/jiaoda/motor_cmd` | `std_msgs/Int16MultiArray`（5 通道直控） | 155 |

> 运行时证据：`/jiaoda/rc`、`/jiaoda/sensors`、`/jiaoda/motor_cmd` 三个话题**在 ROS 图中完全不存在**（`rostopic info` 无输出），因为该节点未运行。

**可配置项**

| 变量 | 默认值 | 含义 | 行号 |
| --- | --- | --- | --- |
| `ESP32_PORT` | `/dev/ttyUSB0` | **实机无 `/dev/ttyUSB*`**（只有 `ttyACM0/1`） | 7 |
| `ESP32_MAX_DELTA` | `200` | PWM 相对中位的最大偏移 | 13 |
| `ESP32_VX_SCALE` | `150` | 线速度缩放 | 14 |
| `ESP32_WZ_SCALE` | `150` | 角速度缩放 | 15 |
| `ESP32_BAT_EMPTY` | `0` | 电池 ADC 空电值 | 19 |
| `ESP32_BAT_FULL` | `4095` | 电池 ADC 满电值（12 bit） | 20 |
| `SHM`（常量） | `/dev/shm/jiaoda_sensors.json` | 传感器共享内存文件 | 17 |

**串口协议**

| 方向 | 格式 | 说明 | 行号 |
| --- | --- | --- | --- |
| 下行 | `M<left>,<right>\n` | 左右轮 PWM，`1000..2000`，中位 1500 | 64 |
| 下行 | `A<ch0>,<ch1>,<ch2>,<ch3>,<ch4>\n` | 5 路执行器直控 | 71 |
| 上行 | `R` + 19 个 TAB 分隔整数 | `parts[0]=="R"`，`vals[0:10]=rc`，`vals[10:18]=sensors` | 94–108 |
| 上行容错 | — | 行缓冲，`>4096` 字节仍无换行则整段丢弃 | 135–136 |

**安全/兜底**

| 机制 | 阈值/行为 | 行号 |
| --- | --- | --- |
| 串口掉线 | `read` 异常 → 关闭 → `sleep 1` → 下轮重开；打不开则 `sleep 3` 重试并降级运行 | 114–128 |
| 看门狗 | **无**（`/cmd_vel` 停发后 PWM 保持） | 56–64 |
| 限幅 | PWM clamp `±MAX_DELTA` 再 clamp `1000..2000`；电池百分比 clamp `0..100` | 60–63, 78 |
| 原子写 | `写 .tmp` + `os.replace` | 85–89 |
| 退出 | 发一次 `M1500,1500` 再关串口 | 139–146 |

**缺陷**：无看门狗；`/dev/ttyUSB0` 不存在；`write_shm` 的 `bat` 依赖 `BAT_CH=0`（第 0 通道必须是电池 ADC，未在源码中说明依据）；`handle_line` 只做 `int()`，任一字段非数字即整帧丢弃。

---

### 2.6 `gimbal_driver.py`（155 行，纯库，**无任何文件 import 它**）

**职责**：两种云台硬件的抽象——串口舵机云台 `Gimbal`（`"P{p}T{t}\n"`）与 I²C PCA9685 PWM 云台 `GimbalPCA9685`。

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 输入 | `GIMBAL_PORT` 环境变量（默认 `""`，为空则**不打开串口**，静默降级） | 22, 31–33 |
| 限位 | `PAN_MIN/MAX=-90/90`，`TILT_MIN/MAX=-45/45`，`_clamp` 取整并容错非数字 | 3–4, 8–17 |
| 串口帧 | `fmt="P{p}T{t}\n"`，115200，`timeout=0.1` | 21, 26, 36 |
| PCA9685 | I²C bus 1，地址 `0x40`，50 Hz，`us_min/us_max=500/2500`，pan=ch0，tilt=ch1 | 84–91, 105 |
| 预分频 | `round(25e6/(4096*50))-1 = 121` | 108 |
| 角度→脉宽 | `us = 500 + (deg-lo)/(hi-lo) * 2000` | 121–124 |
| 自检 | `__main__` 依次 `set(30,-10)`、`set(200,200)`（验证 clamp）、`center()` | 149–155 |

**缺陷**：`Gimbal._write` 失败后会 `close()` 并立刻 `_open()` 重连，但**不重发本帧**（丢指令且无补偿）；`GimbalPCA9685.set()` 不持锁（`Gimbal` 有锁）；本文件与 `console_backend`/`chassis_gimbal_bridge` 的云台链路**完全无关**，属离线备用实现。

---

### 2.7 `nav_mission.py`（93 行，**当前崩溃重启循环**）

**职责**：巡检任务状态机——读 `/dev/shm` 里的航点表，逐点发布 `/move_base_simple/goal`，到点后转云台、拍照、写状态。

**ROS 接口**

| 方向 | 话题 | 类型 | 行号 |
| --- | --- | --- | --- |
| 发布 | `/move_base_simple/goal` | `geometry_msgs/PoseStamped` | 53, 77–79 |
| 发布 | `/jiaoda/gimbal` | `std_msgs/Int16MultiArray`，`data=[gt,gp]` | 54, 85 |
| 订阅 | `/slam_pose` | `geometry_msgs/PoseStamped` | 55 |
| 订阅 | `/left_camera/image` | `sensor_msgs/Image` → `br.imgmsg_to_cv2(..., "bgr8")` | 56, 24–28 |

**文件契约（`/dev/shm`）**

| 文件 | 方向 | 格式 | 行号 |
| --- | --- | --- | --- |
| `/dev/shm/jiaoda_mission.json` | 读 | `{wps:[{x,y,gp?,gt?}], route}` | 10, 65 |
| `/dev/shm/jiaoda_nav_cmd` | 读（读完即删） | 文本 `start` / `cancel` | 11, 37–41 |
| `/dev/shm/jiaoda_nav_status.json` | 写（`.tmp`+`replace`） | `{state,cur,total,msg,t}`，state ∈ `idle/moving/shooting/done` | 12, 30–35 |
| `~/jiaoda/photos/` | 写 | `<route>_wp<NN>_<unix>.jpg`，**无 json 边车** | 13, 47–48 |

**常量/周期**：`ARRIVE=0.35 m`（行 16）；主循环 `rospy.Rate(5)`（行 59）；到点后 `sleep 0.6`（云台）+ `sleep 0.5`（拍照）串行阻塞（行 86–88）。

**安全/兜底**：无航点到达超时、无重试、无失败上报（只有 `d<ARRIVE` 才推进）；`cancel` 只停状态机、**不发布零速**，也不取消已下发的 goal。

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| N1 | **致命：`from cv_bridge import CvBridge` 在 import 期即失败**（`SystemError: initialization of cv_bridge_boost raised unreported exception`），进程 exit 1，systemd `Restart=always` 每 3 s 重启一次，**restart counter 已达 1817** | 7 |
| N2 | 后果：`/move_base_simple/goal` **无发布者**、`jiaoda_nav_status.json` 从未生成、`~/jiaoda/photos` 目录至今不存在（`makedirs` 在第 14 行，位于崩溃点之后） | 14 |
| N3 | 即使 cv_bridge 修好，控制台 `/api/nav/start` 与 `nav_mission` 之间的握手仍依赖 `/dev/shm` 轮询（`0.5 s` 粒度），无确认/回执 | 62–71 |
| N4 | `w["x"]` / `w["y"]` 直接取值，航点缺字段即 `KeyError` 崩溃 | 78, 81 |
| N5 | 到点判定只看距离，不看朝向；云台指令 `[gt,gp]` 与 `console_backend` 的 `[pitch,yaw]` 顺序一致但语义命名相反（gt=俯仰？gp=偏航？）无文档 | 85 |
| N6 | 拍照不写元数据（对比 `photo.py` 有 json 边车），离线复用时无法追溯位姿/云台角 | 43–49 |

---

### 2.8 `nav_simple.py`（473 行）

**职责**：无 `move_base` 的轻量导航栈——A\* 全局规划（一次）+ Pure Pursuit 取预瞄点 + DWA 在 `(vx, vyaw)` 网格采样避障，20 Hz 输出 `/cmd_vel`。

**ROS 接口**

| 方向 | 话题 | 类型 | QoS/备注 | 行号 |
| --- | --- | --- | --- | --- |
| 发布 | `/cmd_vel` | `geometry_msgs/Twist` | queue 10，20 Hz | 460 |
| 发布 | `/nav_path` | `nav_msgs/Path` | queue 1，`latch=True`，**无订阅者** | 461 |
| 订阅 | `/slam_pose` | `geometry_msgs/PoseStamped` | queue 10，只用 `x,y` | 462, 73–76 |
| 订阅 | `/imu` | `sensor_msgs/Imu` | queue 10，只用 orientation 算 yaw | 463, 79–84 |
| 订阅 | `/map` | `nav_msgs/OccupancyGrid` | queue 1 | 464, 87–94 |
| 订阅 | `/move_base_simple/goal` | `geometry_msgs/PoseStamped` | queue 1 | 465, 128 |
| 订阅 | `/move_base/cancel` | `actionlib_msgs/GoalID` | queue 1 | 466, 159 |
| 订阅 | `/unilidar/cloud` | `sensor_msgs/PointCloud2` | queue 1，`buff_size=2**24` | 467, 97 |

**常量（全部硬编码，无环境变量、无 ROS 参数）**

| 组 | 常量 | 值 | 行号 |
| --- | --- | --- | --- |
| 速度 | `VX_MAX` / `VX_MIN` | `1.0` / `0.5` m/s（**不允许后退**） | 22–23 |
| 速度 | `VYAW_MAX` | `0.8` rad/s | 24 |
| Pure Pursuit | `LOOKAHEAD_DIST` | `0.8` m | 27 |
| DWA | `DWA_VX_SAMPLES`×`DWA_VYAW_SAMPLES` | `5 × 11 = 55` 组采样 | 30–31 |
| DWA | `DWA_PREDICT_T` / `DWA_DT` | `2.0 s` / `0.1 s` → **20 步前向模拟** | 32–33 |
| DWA 权重 | `W_HEAD` / `W_DIST` / `W_VX` / `W_OBST` | `1.5 / 1.0 / 0.3 / 30.0` | 34–37 |
| 车体 | `ROBOT_RADIUS` / `SAFE_DIST` | `0.5 m` / `0.7 m` | 38–39 |
| 到达 | `ARRIVE_FINAL` | `0.30 m` | 42 |
| 符号 | `INVERT_YAW` | `True`（硬编码取反） | 43 |
| A\* | `INFLATE_RADIUS` / `PATH_SIMPLIFY` | `0.5 m` / 每 `4` 个栅格取 1 点 | 46–47 |
| 看门狗 | `WD_S` | `1.5 s` | 50 |
| 控制频率 | `HZ` | `20` | 51 |
| 坐标系 | `/nav_path` 的 `frame_id` | `map` | 348 |

**算法关键约定**

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 地图占用判定 | `occ = map > 50`（未知 `-1` 不膨胀、可穿越） | 177 |
| 膨胀 | `cv2.dilate` 椭圆核，半径 `INFLATE_RADIUS/res`；无 `cv2` 时**退化为不膨胀** | 178–184 |
| 起点/终点纠偏 | 落在障碍里时螺旋搜索最近自由格，最多 30 格 | 185–193 |
| 点云→世界 | 仅用 yaw 旋转 + 车体位置平移 `wx=rx+x*cy-y*sy` | 119–122 |
| 车体滤除矩形 | `-1.30 < x < 0.20`、`-0.60 < y < 0.60`（**雷达坐标系**，假设雷达在车头） | 116 |
| 点云裁剪 | `-0.3 < z < 1.0`，`x²+y² < 36`（6 m 内），每 3 点取 1 点 | 113, 108, 118 |
| DWA 车体采样点 | 6 点：`(0,0)`、`(-0.6,0)`、`(0,±0.5)`、`(-0.6,±0.5)` | 291–293 |
| DWA 碰撞阈值 | 最近点距离 `< ROBOT_RADIUS(0.5 m)` → 该轨迹作废 | 303 |
| 慢速区 | `d_goal < 0.80 m`：`vx ∈ [0.10,0.20]`，`vyaw ∈ ±0.4`，绕过 DWA | 392–404 |
| 脱困 | DWA 全部作废 → 向激光点少的一侧以 `±0.6 rad/s` + `vx=0.05` 原地转 | 417–434 |

**安全/兜底**

| 机制 | 阈值/行为 | 行号 |
| --- | --- | --- |
| 位姿看门狗 | `/slam_pose` 超过 **1.5 s** 未更新 → 每周期发布零 `Twist` | 372–373 |
| IMU 看门狗 | `/imu` 超过 **1.5 s** 未更新 → 发布零 `Twist` | 374–375 |
| 到达停车 | `d_goal < 0.30 m` → 发布零 `Twist` 并清空 goal/path | 384–389 |
| 急停 | `/move_base/cancel` → 清零并 `pub_cmd.publish(Twist())` | 159–165 |
| 限幅 | 全部输出受 `VX/VYAW` 常量约束，慢速区另有限幅 | 397–399 |

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| S1 | **空闲时不发零速**：`if not active or not path or not goal: continue` 直接跳过，`/cmd_vel` 保持最后一条。若下游是 `cmd_vel_to_pwm.py`（无看门狗）会持续运动；只有 `chassis_gimbal_bridge` 的 0.5 s 看门狗能兜住 | 376–377 |
| S2 | DWA 的 `vx` 下界是 `VX_MIN=0.5 m/s`，采样里**没有 0 速与倒车**，狭窄处只能靠 0.1–0.2 m/s 的慢速区或脱困逻辑 | 23, 264 |
| S3 | **不重规划**：文件头注释明确“A\* 规划全局路径（一次，不重规划）”；路径被新障碍堵死后只能一直脱困 | 7, 145 |
| S4 | A\* 在 `rospy` 订阅回调里同步执行（2000×2000=400 万格 Python 堆搜索），**会阻塞所有其它回调**，期间 `/imu`、`/slam_pose` 积压，控制环可能读到旧位姿 | 128–156 |
| S5 | `INVERT_YAW=True` 硬编码：角速度符号依赖固件/装配方向，换主控或改线后车会反向转，需人工改常量重编 | 43, 400, 437 |
| S6 | 点云转世界**忽略雷达外参、安装偏置与横滚/俯仰**，只用 yaw；坡道/颠簸时 2D 投影误差直接进 DWA 碰撞判定 | 100–122 |
| S7 | 车体滤除矩形是雷达坐标系常量（`-1.3..0.2 × ±0.6`），与实际车体 1.26×1.05 m 的对应关系只写在注释里，换安装位置即失效 | 114–116 |
| S8 | 无激光数据时 `lidar_arr=None` → **跳过所有碰撞检查**，以最高 1.0 m/s 盲走 | 268–271, 287 |
| S9 | `find_lookahead` 用“最近路径顶点”而非“最近路径段”，路径自交/回折时可能跳到后方点 | 237–241 |
| S10 | `/nav_path` 发布但**无订阅者**，前端地图也不显示路径 | 461 |
| S11 | `/map` 的未知区（`-1`）按自由通行，A\* 可能穿墙规划 | 177 |
| S12 | DWA 每周期 `55 组 × 20 步 × 6 点` 的 numpy 最近点计算，点云上千点时 CPU 压力大（Orin 上 20 Hz 余量有限） | 273–307 |
| S13 | `on_cloud` 里 `state.get('pos')`/`state.get('imu_yaw')` 在**不持锁**的情况下读取（其余路径都加锁），存在竞态 | 100 |

---

### 2.9 `pose_bridge.py`（32 行）

**职责**：把 FAST-LIVO 的 `nav_msgs/Odometry` 拆成导航用的 `PoseStamped` 与一个“伪 IMU”。

| 方向 | 话题 | 类型 | 关键处理 | 行号 |
| --- | --- | --- | --- | --- |
| 订阅 | `/aft_mapped_to_init` | `nav_msgs/Odometry` | queue 10 | 28 |
| 发布 | `/slam_pose` | `geometry_msgs/PoseStamped` | `frame_id="map"`，`pose=msg.pose.pose` | 26, 11–15 |
| 发布 | `/imu` | `sensor_msgs/Imu` | `frame_id="base"`，orientation 来自 odom 姿态，angular_velocity 来自 odom twist | 27, 16–21 |

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| B1 | `/imu` 不是真 IMU：姿态是 SLAM 融合结果、角速度是里程计 twist，**协方差全部为 0**（默认），下游若按 IMU 权重使用会出错 | 16–21 |
| B2 | `frame_id="base"` 不是 ROS 常用命名（`base_link`），且该 frame 无 TF，`/imu` 无法参与坐标变换 | 18 |
| B3 | 时间戳直接拷贝 odom header；`cloud_restamp` 已把点云时间改成 `now()`，链路时间语义混乱 | 12, 17 |
| B4 | 无参数、无降频/限流：`/aft_mapped_to_init` 多快就转发多快，`/imu` 频率随 SLAM 波动 | — |

---

### 2.10 `grid_bridge.py`（266 行）

**职责**：把 `laserMapping` 的配准点云按里程计位姿积分成 2D 对数几率栅格，1 Hz 发布 `/map`（latch）并渲染 PNG/元数据到 `/dev/shm` 供网页显示；支持保存/加载/清空。

**ROS 接口**

| 方向 | 话题 | 类型 | 说明 | 行号 |
| --- | --- | --- | --- | --- |
| 订阅 | `--cloud`（默认 `/cloud_registered`） | `sensor_msgs/PointCloud2` | queue 1 | 119, 247 |
| 订阅 | `--odom`（默认 `/aft_mapped_to_init`） | `nav_msgs/Odometry` | queue 5 | 118, 248 |
| 发布 | `--map-topic`（默认 `/map`） | `nav_msgs/OccupancyGrid` | queue 1，`latch=True`，1 Hz | 120, 122 |

**可配置项（`argparse`，非 ROS 参数）**

| 参数 | 默认值 | 含义 | 行号 |
| --- | --- | --- | --- |
| `--cloud` | `/cloud_registered` | 输入点云 | 247 |
| `--odom` | `/aft_mapped_to_init` | 输入里程计 | 248 |
| `--map-topic` | `/map` | 输出栅格 | 249 |
| `--frame` | `map` | `OccupancyGrid.header.frame_id` | 250 |
| `--res` | `0.05` | 分辨率 m/格 | 251 |
| `--size` | `2000` | 边长格数（`2000×0.05 = 100 m × 100 m`） | 252 |
| `--zmin` / `--zmax` | `-0.4` / `1.5` | 相对车体 z 的高度带 | 253–254 |
| `--rmax` | `15.0` | 最大距离（米），另设 `d²>0.09` 即 0.3 m 盲区 | 255, 146 |
| `--png` | `/dev/shm/jiaoda_map.png` | 渲染输出 | 256 |
| `--maps-dir` | `~/jiaoda/maps` | `.npz` 地图目录 | 257 |

**文件契约**

| 文件 | 方向 | 内容 | 行号 |
| --- | --- | --- | --- |
| `~/jiaoda/maps/<name>.npz` | 读/写 | `log_odds`(float32, 2000²)、`size`、`res` | 94–106 |
| `/dev/shm/jiaoda_map.png` | 写 | 俯视渲染图（含车体位姿箭头） | 212–214 |
| `/dev/shm/jiaoda_map.json` | 写 | `{x0, y0top, mpp, w, h}`，供网页点击换算 | 215–221 |
| `/dev/shm/jiaoda_map_save` | 读（读完删） | 文本地图名 | 8, 230–234 |
| `/dev/shm/jiaoda_map_load` | 读（读完删） | 文本地图名 | 9, 235–239 |
| `/dev/shm/jiaoda_map_clear` | 读（读完删） | 存在即清空 | 10, 226–228 |

**地图模型（关键参数，二次开发必须复刻）**

| 项 | 值 | 行号 |
| --- | --- | --- |
| 栅格存储 | `log_odds` float32，`clip(-2.0, 5.0)` | 36, 76 |
| 命中增量 | `+0.85` | 75 |
| 空闲增量 | `-0.4`（每条射线只随机抽 25% 端点回填） | 62, 48–52 |
| 栅格化阈值 | `occupied: >0.5`，`free: <-0.3`，其余 `-1`（未知） | 81–82 |
| 世界↔栅格 | `c = origin + x/res`；`r = origin - y/res`（`origin=size//2`） | 39–42 |
| 发布前翻转 | `np.flipud(data)` 以符合 OccupancyGrid 行序 | 169 |
| 地图原点 | `-origin*res = -50.0 m` | 166–167 |
| 渲染 | ROI=数据范围∪车体，pad=20 格，最长边缩放到 ≈900 px，最近邻插值 | 189–204 |
| 渲染周期 | `rospy.Timer(1.0 s)`，同时发布 `/map` 与写 PNG | 122, 152–154 |

**安全/兜底**：位姿未就绪时直接丢弃点云（`if not self.pose["ok"]: return`）；点云少于 20 点、全部被 z/r 过滤掉时直接返回；`Grid` 内所有公开方法都持锁；保存用 `.tmp`+`os.replace` 原子写。

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| R1 | **负坐标截断偏差**：`int(origin + x/res)` 与 `astype(np.int32)` 都是向 0 截断，`-0.5` 与 `+0.5` 落在同一格，原点附近存在半格系统偏差 | 40–41, 65–66 |
| R2 | 射线回填只用 **25% 随机端点**且 `np.random.choice` 无种子 → 同一份数据两次建图结果不同，不可复现 | 48–52 |
| R3 | `parse_xyz` 假设 `x/y/z` 在 offset `0/4/8` 且为 float32、无行填充；忽略 `is_bigendian` 与 `row_step`，换雷达驱动即可能解析错 | 17–28 |
| R4 | 地图永不因回环/重定位而清空或变形，SLAM 位姿跳变会留下“鬼影墙” | — |
| R5 | `/dev/shm/jiaoda_map.json` 直接 `json.dump` 到 `.tmp` 后 `replace`，但 `.json.tmp` 文件名固定，多实例会互踩 | 219–221 |
| R6 | 未知区按 `-1` 发布，`nav_simple` 不膨胀未知区 → 规划可能穿未知区域 | 80–82 |
| R7 | 1 Hz 全量渲染 + PNG 落盘（11 KB/次）在 Orin 上属可接受，但 `render_png` 与 `publish_map` 串行执行，点云回调可能被拖慢 | 152–154 |
| R8 | 无“建图开关”：只要有位姿就一直积分，控制台的 `start/freeze` 按钮对其无影响（见 C5） | 132–150 |

---

### 2.11 `cloud_restamp.py`（10 行）

**职责**：把 `/unilidar/cloud` 的时间戳改写为当前时间后转发到 `/synced/cloud`，绕开雷达与相机的时间同步问题。

| 方向 | 话题 | 类型 | 行号 |
| --- | --- | --- | --- |
| 订阅 | `/unilidar/cloud` | `sensor_msgs/PointCloud2`，queue 4，`buff_size=2**24` | 9 |
| 发布 | `/synced/cloud` | `sensor_msgs/PointCloud2`，queue 4 | 5 |

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| T1 | **原地改写订阅到的消息**（`m.header.stamp = now()`）后重新发布，破坏原时间戳；下游再也拿不到雷达硬件时间 | 6–8 |
| T2 | 用“收到即现在”代替真实同步，等效于把雷达延迟注入到 SLAM 时间对齐中，且延迟随队列积压漂移 | 7 |
| T3 | 没有 `if __name__ == "__main__"`，`init_node` 在 import 期执行，无法被其它模块安全复用 | 4 |
| T4 | 无频率/丢帧统计，链路健康状况不可观测 | — |

---

### 2.12 `photo.py`（61 行，**未被任何文件 import**）

**职责**：独立的拍照工具库——按 `route` + 航点号 + 时间戳落盘 JPG，并写同名 `.json` 元数据边车。

| 函数 | 签名 | 行为 | 行号 |
| --- | --- | --- | --- |
| `capture` | `(cam_index, route, wp_idx, meta=None)` | 每次调用**新开** `VideoCapture`，丢弃 3 帧预热，`cv2.imwrite` | 27–46 |
| `capture_frame` | `(jpg_bytes, route, wp_idx, meta=None)` | 直接写已有 JPEG 字节（可复用网页帧，避免二次开相机） | 49–57 |
| `_paths` | `(route, wp_idx, ts)` | `~/jiaoda/photos/<route>_wp<idx>_<ts>` + `.jpg` / `.json` | 10–13 |
| `_write_meta` | — | `{route, wp_idx, ts, time, jpg, **meta}`，`ensure_ascii=False, indent=2` | 16–24 |

**缺陷**：`capture()` 每张都开关相机（约 1–2 s 开销，且会与其他打开同一 `/dev/videoN` 的进程冲突）；失败时 `r` 可能未定义（`for _ in range(3): r, fr = cap.read()` 若 `isOpened()` 为真但循环 0 次不会发生，风险低但仍是隐式依赖）；`nav_mission.snap()` 自己写了另一套命名与**无 json 边车**的实现，两者不一致。

---

### 2.13 `calib/calib_web.py`（324 行）

**职责**：相机内参 + 相机-雷达外参标定网页（8095），实时 MJPEG、AprilGrid 检测计数、点云投影叠加、内参计算、外参写入 FAST-LIVO 配置。

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 端口 | `CALIB_PORT` 默认 `8095`，绑 `0.0.0.0` | 7, 318 |
| 相机 | `CALIB_CAM` 默认 `0`（`run_calib.sh` 设 `2`），MJPG 1280×720，`sleep 0.03` | 18, 81–84, 102 |
| 检测 | 每 4 帧检测一次，`DICT_APRILTAG_36h11`，兼容 OpenCV 新旧 aruco API | 99–101, 46–54 |
| AprilGrid | 6×6，`TAG_SIZE=0.088 m`，`TAG_SPACING=0.3`（相对间距）→ `PITCH=0.1144 m` | 15–16 |
| 内参默认 | `fx=fy=914.0`，`cx=640.0`，`cy=360.0`，从 `~/livo2_ws/src/FAST-LIVO2/config/camera_unitree.yaml` 覆盖 | 27, 10, 26–35 |
| 外参基座 | `R_BASE=[[0,1,0],[-1,0,0],[0,0,1]]`，`R=Rz·Ry·Rx·R_BASE` | 23, 69 |
| 点云 | 订阅 `/unilidar/cloud`（queue 1），保留最近 4 帧，最多 60000 点 | 123, 120–122 |
| 投影 | `z>0.15 m` 才画，深度 0.5–8 m 映射到 HSV 色环，**逐点 `cv2.circle`**（≤6 万次/帧） | 141, 151–156 |
| 内参求解 | 至少 5 张可用图、每张 ≥4 个 tag，`CALIB_FIX_K3` | 187–189 |
| 外参保存 | 覆写 `unitree_l2.yaml` 的 `Rcl:`/`Pcl:` 两行 | 200–211 |

**HTTP API**

| 方法 | 路由 | body | 行为 | 前端调用 | 行号 |
| --- | --- | --- | --- | --- | --- |
| GET | `/`、`/calib.html` | — | 返回 `calib.html` | — | 265–268 |
| GET | `/status` | — | `{cam,cam_ok,tags,cloud_pts,intr,extr}`（intr/extr 为文件计数） | `calib.html:103` | 269–273 |
| GET | `/extr` | — | 当前 `{rx,ry,rz,tx,ty,tz}` | `calib.html:101` | 274–275 |
| GET | `/stream.mjpg` | — | 原始画面 + tag 检测框 | `calib.html:44` | 276–277 |
| GET | `/project.mjpg` | — | 点云投影叠加画面 | `calib.html:85` | 278–279 |
| POST | `/setcam` | `{i}` | 切换相机索引 | `calib.html:84` | 285–286 |
| POST | `/setextr` | `{rx..tz}` | 更新内存外参（部分键也接受） | `calib.html:99` | 287–291 |
| POST | `/saveextr` | `{}` | **写 `~/livo2_ws/.../unitree_l2.yaml`** | `calib.html:102` | 292–293 |
| POST | `/capture` | `{mode: "intr" 或 "extr"}` | 存 `data/{intr,extr}/NNNN.jpg`；extr 同时存 `NNNN.npy`（4 帧点云拼接） | `calib.html:94` | 294–307 |
| POST | `/intrinsics` | `{}` | 跑 `cv2.calibrateCamera` 并返回 fx/fy/cx/cy/rms/dist | `calib.html:96` | 308–309 |
| POST | `/clear` | `{mode}` | **删除** `data/{intr,extr}/` 下全部文件（含 `.npy`） | `calib.html:95` | 310–313 |

**安全/兜底**：相机打不开时 1 s 重试；无帧时 `/capture` 返回 `{ok:false}`；`save_extr` 失败只写 stderr；`/intrinsics` 在可用图 <5 时明确报错。

**缺陷 / 可疑点**

| 编号 | 问题 | 行号 |
| --- | --- | --- |
| K1 | **`/saveextr` 直接原地覆写工作区外的 FAST-LIVO 配置**（`unitree_l2.yaml`），无备份、无 diff、无校验；写坏后只能靠 git 或手工恢复 | 200–211 |
| K2 | 外参写入只替换以 `Rcl:`/`Pcl:` 开头的行，**缩进固定为 2 空格**，若上游 yaml 改缩进会写出非法 yaml | 205–208 |
| K3 | `/clear` 无二次确认、无回收站，**直接 `os.remove`** 全部标定图与点云 `.npy` | 310–313 |
| K4 | 服务绑 `0.0.0.0:8095` 无认证；同网段可任意改外参并写入 SLAM 配置 | 318 |
| K5 | `run_calib.sh` 设 `CALIB_CAM=2`，而 `/dev/video2` 已不存在 → 页面永远无画面（与 P1 同源） | `run_calib.sh:3` |
| K6 | 投影逐点画圆（最多 6 万次），`/project.mjpg` 多客户端时 CPU 会打满，且无降采样 | 155–156 |
| K7 | `state["cam"]` 被 `CamThread` 与 HTTP 线程同时写，无锁（`frame` 有锁） | 90, 286 |
| K8 | 内参门槛（≥5 张、每张 ≥4 tag）与离线脚本（`calib_intrinsics.py` 建议 ≥20、硬门槛 8）不一致，两套工具结果不可比 | 187 |

---

### 2.14 `calib/calib_intrinsics.py`（144 行）

**职责**：离线内参标定 CLI，读目录图片 → AprilGrid 角点 → `cv2.calibrateCamera` → 打印/落盘 FAST-LIVO 风格 yaml。

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 入参 | `argv[1]=IMG_DIR(./frames)`、`argv[2]=W(1280)`、`argv[3]=H(720)` | 7–9 |
| AprilGrid | 6×6，`0.088 m`，`spacing 0.3`（与 `calib_web` 一致） | 11–16 |
| 图像 | `*.png` + `*.jpg` 排序遍历 | 53–54 |
| 每帧要求 | ≥4 个 tag，`0<=id<36` | 74, 81 |
| 门槛 | `used<8` 只打印警告；**`used>0` 就继续标定** | 95–98 |
| 求解 | `cv2.CALIB_FIX_K3`，输出 rms 与 fx/fy/cx/cy/d0..d3 | 100–102, 108–123 |
| 产物 | `<IMG_DIR>/intrinsics_result.yaml`，含 `scale: 0.5` | 125–138 |

**缺陷**：`scale: 0.5` 硬编码，若标定图是 1280×720 原图而 SLAM 也按原图处理，这个 0.5 会与 `camera_unitree.yaml` 的 `scale: 0.5` 叠加导致内参错配；`used<8` 时继续求解，5 张图的结果不可信；无异常捕获，`calibrateCamera` 失败直接抛栈。

---

### 2.15 `calib/grab_frames.py`（61 行）

**职责**：交互式取帧工具（空格存 PNG、q 退出；无 GUI 时每 1.5 s 自动存一张）。

| 项 | 内容 | 行号 |
| --- | --- | --- |
| 入参 | `argv[1]=DEV(0)`、`argv[2]=OUT(./frames)`、`argv[3]=W(1280)`、`argv[4]=H(720)` | 6–9 |
| 打开 | `cv2.VideoCapture(DEV)` + MJPG + 分辨率设置，失败 `exit(1)` | 13–20 |
| 无 GUI 模式 | `namedWindow` 抛异常 → 每 1.5 s 存一张 | 27–30, 51–56 |
| 产物 | `frame_%03d.png`（PNG，单张可达数 MB） | 45, 52 |

**缺陷**：`DEV=2` 时（若照抄 `run_calib.sh` 的约定）会打不开；PNG 无损但体积大，与 `calib_web` 的 JPEG 流程不统一。

---

### 2.16 `calib/record_calib.sh`（59 行）

**职责**：标定数据采集编排脚本：`frames` / `intr` / `bag` / `bag_dense` / `topics` 五个子命令。

| 子命令 | 动作 | 行号 |
| --- | --- | --- |
| `frames` | `grab_frames.py $CAM_DEV $OUT_DIR/frames $IMG_W $IMG_H` | 29–31 |
| `intr` | `calib_intrinsics.py $OUT_DIR/frames $IMG_W $IMG_H` | 32–34 |
| `bag` | `rosbag record` 录 `IMG_TOPIC + LID_TOPIC + IMU_TOPIC` | 35–41 |
| `bag_dense` | 只录 `LID_TOPIC + IMU_TOPIC`（静置累积稠密点云） | 42–48 |
| `topics` | `rostopic list` + 三个 `timeout 5 rostopic hz` 自检 | 49–55 |

| 环境变量 | 默认值 | 问题 | 行号 |
| --- | --- | --- | --- |
| `IMG_TOPIC` | `/left_camera/image` | 正确 | 6 |
| `LID_TOPIC` | **`/cloud`** | **该话题不存在**（实际为 `/unilidar/cloud` 或 `/cloud_registered`） | 7 |
| `IMU_TOPIC` | **`/imu`** | 这是 `pose_bridge` 合成的伪 IMU，不是 `/unilidar/imu` | 8 |
| `OUT_DIR` | `~/calib_data` | 与 `calib_web` 的 `~/jiaoda/calib/data` 不一致 | 9 |
| `CAM_DEV` | `0` | 与 `calib_web` 的 2 不一致 | 10 |
| `IMG_W/H` | `1280/720` | 一致 | 11–12 |

**缺陷**：`set -e`（行 2）下任一命令失败即整体退出；`bag` 用默认 `LID_TOPIC=/cloud` 会录出**没有点云的空 bag**（`rosbag record` 对不存在话题只告警不报错，`set -e` 也拦不住）。

---

## 3. 全局话题矩阵（源码声明 × 运行时实测）

| 话题 | 类型 | 源码中的发布者 | 源码中的订阅者 | 运行时实测（2026-10-21） |
| --- | --- | --- | --- | --- |
| `/cmd_vel` | `Twist` | `nav_simple`、`console_backend`、`chassis_bridge`(旧)、`cmd_vel_to_pwm`(读) | `chassis_gimbal_bridge` | 2 发布 / 1 订阅；README K26 记录实测约 15.9 Hz 且**全为 0** |
| `/jiaoda/gimbal` | `Int16MultiArray` | `console_backend`、`nav_mission`(崩) | `chassis_gimbal_bridge` | 只有 `console_backend` 在发 |
| `/jiaoda/esp_tel` | `String` | `chassis_gimbal_bridge` | **无** | 发布者存在但串口未开 → 无数据 |
| `/jiaoda/rc` | `Int16MultiArray` | `chassis_bridge`(未运行) | — | **话题不存在** |
| `/jiaoda/sensors` | `Int16MultiArray` | `chassis_bridge`(未运行) | — | **话题不存在** |
| `/jiaoda/motor_cmd` | `Int16MultiArray` | — | `chassis_bridge`(未运行) | **话题不存在** |
| `/slam_pose` | `PoseStamped` | `pose_bridge` | `nav_simple`、`nav_mission`(崩) | 正常 |
| `/imu` | `Imu` | `pose_bridge` | `nav_simple`、`nav_mission`(崩) | 正常（实为 SLAM 姿态） |
| `/aft_mapped_to_init` | `Odometry` | `laserMapping` | `pose_bridge`、`console_backend`、`grid_bridge` | 正常 |
| `/Odometry` | `Odometry` | **无** | `console_backend` | **零消息（死订阅）** |
| `/lio_sam/mapping/odometry` | `Odometry` | **无** | `console_backend` | **不存在/零消息（死订阅）** |
| `/map` | `OccupancyGrid` | `grid_bridge` | `nav_simple` | 正常，1 Hz，latch |
| `/nav_path` | `Path` | `nav_simple` | **无** | **有发布、无订阅** |
| `/move_base_simple/goal` | `PoseStamped` | `nav_mission`(崩) | `nav_simple` | **无发布者** → 导航无法被触发 |
| `/move_base/cancel` | `GoalID` | **无** | `nav_simple` | **无发布者** → 只能 Ctrl-C 停 |
| `/unilidar/cloud` | `PointCloud2` | 雷达驱动 | `nav_simple`、`cloud_restamp`、`calib_web` | 正常 |
| `/synced/cloud` | `PointCloud2` | `cloud_restamp` | `laserMapping` | 正常 |
| `/cloud_registered` | `PointCloud2` | `laserMapping` | `grid_bridge` | 正常 |
| `/left_camera/image` | `Image` | `cam_publisher` | `laserMapping`、`nav_mission`(崩) | **发布者存在但无数据**（P2） |

**结论**：ROS 图中**没有任何 service**（全目录无 `rospy.Service`），跨进程接口只有话题 + `/dev/shm` 文件 + HTTP。

---

## 4. `/dev/shm` 文件契约（跨进程“隐式 API”）

| 文件 | 生产者 | 消费者 | 格式 | 当前状态 |
| --- | --- | --- | --- | --- |
| `/dev/shm/jiaoda_map.png` | `grid_bridge`（1 Hz） | `console_backend` `/api/map` | PNG | 存在（11 634 B） |
| `/dev/shm/jiaoda_map.json` | `grid_bridge`（1 Hz） | `console_backend` `/api/mapinfo` | `{x0,y0top,mpp,w,h}` | 存在（76 B） |
| `/dev/shm/jiaoda_sensors.json` | `chassis_bridge`（未运行） | `console_backend` `/api/ctl/status` | `{ch:[8],bat,bat_raw,t}` | **缺失** → 网页电量恒为空 |
| `/dev/shm/jiaoda_nav_status.json` | `nav_mission`（崩溃） | `console_backend` `/api/nav/status` | `{state,cur,total,msg,t}` | **缺失** → 网页恒 `idle` |
| `/dev/shm/jiaoda_mission.json` | `console_backend` `/api/nav/start` | `nav_mission` | `{wps,route}` | 未生成 |
| `/dev/shm/jiaoda_nav_cmd` | `console_backend` `/api/nav/{start,cancel}` | `nav_mission` | 文本 `start`/`cancel` | 未生成 |
| `/dev/shm/jiaoda_map_save` | `console_backend` | `grid_bridge`（2 Hz 轮询） | 地图名文本 | 按需 |
| `/dev/shm/jiaoda_map_load` | `console_backend` | `grid_bridge` | 地图名文本 | 按需 |
| `/dev/shm/jiaoda_map_clear` | `console_backend` | `grid_bridge` | 存在即清空 | 按需 |

> 这些文件全部**无锁、无版本号、无写入者标识**；二次开发替换任一节点时必须保持文件名与字段名不变。

---

## 5. 串口/协议汇总

| 程序 | 设备 | 波特率 | 下行帧 | 上行帧 | 与固件匹配 |
| --- | --- | --- | --- | --- | --- |
| `chassis_gimbal_bridge.py` | `CTL_PORT`=`/dev/ttyCH343USB0`（**不存在**） | 115200 | `t,s,p,y,chk\n`（20 Hz） | 任意文本行 → `/jiaoda/esp_tel` | **匹配**（字段顺序同固件自述） |
| `cmd_vel_to_pwm.py` | `/dev/ttyACM0`（**实为主控口**） | 115200 | `left,right\n` | 无 | **不匹配**（2 字段 PWM） |
| `chassis_bridge.py` | `/dev/ttyUSB0`（**不存在**） | 115200 | `M<l>,<r>\n` / `A<a,b,c,d,e>\n` | `R`+19 个 TAB 整数 | **不匹配**（旧 ESP32 固件协议） |
| `gimbal_driver.py` | `GIMBAL_PORT`（默认空） | 115200 | `P{p}T{t}\n` | 无 | 独立舵机云台，未接入 |

主控固件自述（README K22，只读验证所得）：`=== Fire Inspection Robot Control System ===`、`RC Mapping: CH1=Steer, CH2=Throttle, CH3=Pitch, CH4=Yaw`、`Serial Format: throttle,steer,pitch,yaw,checksum`、`GIMBAL_PULSE:1500,1500`、约 20 Hz 自报、**`Priority: RC > Serial`**（遥控优先，串口指令会被忽略）。

---

## 6. 关键结论

### 6.1 只有发布者没有订阅者 / 只有订阅者没有发布者

| 类别 | 话题/对象 | 证据 |
| --- | --- | --- |
| **有订阅、无发布者（死订阅）** | `/Odometry` | `console_backend.py:13` 订阅；`rostopic info` 显示 `Publishers: None` |
| | `/lio_sam/mapping/odometry` | 同上，话题从未出现 |
| | `/move_base_simple/goal` | `nav_simple.py:465` 订阅；唯一发布者 `nav_mission` 崩溃 → `Publishers: None` |
| | `/move_base/cancel` | `nav_simple.py:466` 订阅；无人发布 |
| **有发布、无订阅者（空转）** | `/nav_path` | `nav_simple.py:461` 发布；`Subscribers: None` |
| | `/jiaoda/esp_tel` | `chassis_gimbal_bridge.py:49` 发布；无订阅者 |
| **话题完全不存在** | `/jiaoda/rc`、`/jiaoda/sensors`、`/jiaoda/motor_cmd` | `chassis_bridge.py` 未运行，`rostopic info` 无输出 |
| **有发布者但无数据** | `/left_camera/image` | `cam_publisher` 的 fd 指向 `/dev/video2 (deleted)`（P2） |

### 6.2 默认值与实机不符（按影响排序）

| 位置 | 默认值/写死值 | 实机情况 | 后果 |
| --- | --- | --- | --- |
| `chassis_gimbal_bridge.py:8` | `CTL_PORT=/dev/ttyCH343USB0` | 只有 `/dev/ttyACM0`（CH343 走 `cdc_acm`）、`/dev/ttyACM1` | 底盘+云台链路完全未建立；`/cmd_vel` 无人消费 |
| `cam_publisher.py:6` + `run_campub.sh:4` | `CAMPUB_INDEX=2` | `/dev/video0,1,3,4,5,6,7,8`，**无 video2** | 相机节点启动即失败，且不会重连 |
| `run_calib.sh:3` | `CALIB_CAM=2` | 同上 | 标定网页永远无画面 |
| `cmd_vel_to_pwm.py:7` | `/dev/ttyACM0` | 正是主控口，打开会复位 ESP32 | 与 `jiaoda-control` 抢端口；协议还不匹配 |
| `chassis_bridge.py:7` | `ESP32_PORT=/dev/ttyUSB0` | 无 `/dev/ttyUSB*` | 若启用则永远降级运行 |
| `record_calib.sh:7` | `LID_TOPIC=/cloud` | 实际 `/unilidar/cloud`、`/cloud_registered` | 录出无点云的空 bag |
| `record_calib.sh:8` | `IMU_TOPIC=/imu` | 真 IMU 是 `/unilidar/imu`；`/imu` 是 SLAM 派生 | 外参标定用的 IMU 数据来源错误 |
| `nav_simple.py:23` | `VX_MIN=0.5` | 与 `THR_K=55` + clamp±30 组合，0.545 m/s 即饱和 | 低速段无分辨率，慢速区只能靠 0.1–0.2 m/s 特判 |
| `nav_simple.py:43` | `INVERT_YAW=True` | 依赖固件/装配方向，无标定依据 | 换主控后转向反了只会表现为“原地打转” |
| `console_backend.py:20` | `pclear/pstop` | 代码中从未读取 | 网页上两个滑块是假的 |
| `calib_intrinsics.py:115` | `scale: 0.5` | 与 `camera_unitree.yaml` 的 `scale: 0.5` 叠加 | 内参可能被重复缩放 |

### 6.3 缺陷清单（按严重度）

| 等级 | 编号 | 问题 | 位置 |
| --- | --- | --- | --- |
| **严重** | N1 | `nav_mission` 因 `cv_bridge` import 失败无限重启（已 1817 次），任务链路全断 | `nav_mission.py:7` |
| **严重** | M3 | `cmd_vel_to_pwm` 无速度看门狗，`/cmd_vel` 中断后油门保持 | `cmd_vel_to_pwm.py:18–28` |
| **严重** | P1/P2 | 相机索引无设备 + 无重连，`/left_camera/image` 空转，FAST-LIVO 无图像输入 | `cam_publisher.py:6,18–25` |
| **严重** | G1 | 底盘串口默认端口不存在，整条控制链未接通 | `chassis_gimbal_bridge.py:8` |
| **高** | S1 | `nav_simple` 空闲时不发零速，依赖下游看门狗 | `nav_simple.py:376–377` |
| **高** | C1/C2 | 控制台 0.0.0.0 无鉴权、`/api/ctl/drive` 无限幅 | `console_backend.py:237,298` |
| **高** | K1/K4 | 标定网页可无鉴权覆写 FAST-LIVO 配置，无备份 | `calib_web.py:200–211,318` |
| **高** | M1/M2 | 旧底盘脚本协议不符且会复位主控，仍留有启动脚本 | `cmd_vel_to_pwm.py:7,26` + `run_chassis.sh` |
| **中** | S4 | A\* 在 ROS 回调里同步跑，阻塞控制环 | `nav_simple.py:128–156` |
| **中** | S3/S8 | 不重规划；无激光时盲走最高 1.0 m/s | `nav_simple.py:7,287` |
| **中** | C6 | 网页“开始巡检”写入的文件无人消费（`nav_simple` 不读） | `console_backend.py:259–263` |
| **中** | T1 | 点云时间戳被改写为 `now()`，SLAM 时间语义被破坏 | `cloud_restamp.py:7` |
| **中** | R1/R2 | 栅格化负坐标半格偏差；建图随机 25% 采样不可复现 | `grid_bridge.py:40–41,65–66,48–52` |
| **低** | C4/C5/C7 | 航向标定空实现、建图开关无效、路线名固定 `default` | `console_backend.py:241,245,267` |
| **低** | B1/B2 | `/imu` 为伪 IMU 且协方差为 0、frame 名不规范 | `pose_bridge.py:16–21` |

### 6.4 离线二次开发建议（最小稳定契约）

替换或重写任意节点时，建议只依赖下列**已被实机验证过存在**的接口，其余视为内部实现：

| 契约 | 内容 | 方向 |
| --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/Twist`，`vx∈[0,1.0] m/s`，`wz∈±0.8 rad/s`，20 Hz，空闲时**必须补零** | 导航 → 底盘 |
| `/jiaoda/gimbal` | `std_msgs/Int16MultiArray`，`data=[pitch,yaw]`，各 `±30` | 上层 → 云台 |
| 串口帧 | `"%d,%d,%d,%d,%d\n"`：`throttle,steer,pitch,yaw,checksum`，`±30`，20 Hz | 桥接 → 主控 |
| `/aft_mapped_to_init` | `nav_msgs/Odometry`（FAST-LIVO 输出，位姿真值来源） | SLAM → 上层 |
| `/slam_pose` | `PoseStamped`，`frame_id=map` | 定位 → 导航 |
| `/map` | `OccupancyGrid`，`0.05 m`，`2000×2000`，原点 `(-50,-50)`，`-1/0/100` | 建图 → 导航/网页 |
| `/unilidar/cloud` | `PointCloud2`（原始雷达点云，`buff_size≥16 MB`） | 雷达 → 上层 |
| HTTP `:8090/api/*` | 见 §2.1 的两张表 | 网页 ↔ 后端 |
| `/dev/shm/jiaoda_*.json` | 见 §4，文件名与字段名不要改 | 跨进程 |

---

## 附录 A：本机与审计环境

| 项 | 值 |
| --- | --- |
| 目标机 | `sjytt-desktop`，Jetson AGX Orin，Ubuntu 20.04.6 LTS，内核 `5.10.120-tegra`，aarch64 |
| Python | 3.8.10；`numpy 1.17.4`；`cv2 4.2.0`（系统包） |
| ROS | Noetic，Master `:11311` |
| 串口 | `/dev/ttyACM0`（CH343，主控控制口）、`/dev/ttyACM1`（ESP32 原生 USB/JTAG）；**无** `/dev/ttyUSB*`、**无** `/dev/ttyCH343USB0` |
| 视频 | `/dev/video0,1,3,4,5,6,7,8`（四路同型号 UVC，各出 2 个节点）；**无** `/dev/video2` |
| 当前进程 | `console_backend`、`cam_publisher`、`chassis_gimbal_bridge`、`cloud_restamp`、`grid_bridge`、`nav_simple`、`pose_bridge`、`laserMapping`、`unitree_lidar_ros_node`；`nav_mission` 处于重启循环 |
| 服务端口 | 8090 控制台（运行中）、8095 标定页（`jiaoda-calib` 已禁用） |
