# 原机软硬件清单（2026-10-23）
目标：一处列全原机的硬件、软件与配置，使新机复现时可逐项对照。来源均为原机只读采集，路径相对 `docs/evidence/2026-10-23-claude/`；另一份采集见 `docs/evidence/2026-10-23/`。

状态含义：**实测**为本次直接读到；**文档**为资料记载、本次未核实；**未知**为未能获取。

## 一、硬件

| 部件 | 型号与关键参数 | 状态 | 来源 |
| --- | --- | --- | --- |
| 计算板 | Jetson AGX Orin Developer Kit，tegra234，内存 62802 MB，eMMC 57 GB（ext4，已用约 26%，寿命 0–10%） | 实测 | `capture/cmd/model.txt`、`emmc.txt`、`df.txt` |
| 电源模式 | `MODE_30W`：8 核在线（CPU 0–7，最高 1.73 GHz），CPU 8–11 离线，GPU 最高 612 MHz | 实测 | `capture/cmd/nvpmodel.txt`、`capture2/cmd`（jetson_clocks） |
| 激光雷达 | 宇树 L2 一台，`192.168.1.62`，UDP 6101→6201，点云约 12 Hz、IMU 约 251 Hz；第二台的配置存在但未接入 | 实测 | `capture/cmd/ip-addr.txt`、`capture2/cmd/lidar-ping.txt` |
| 雷达网口 | `eth1`，板载以太网（驱动 `nvethernet`），本机 `192.168.1.2/24`，连雷达往返约 0.45 ms | 实测 | `capture/cmd/net-drivers.txt`、`capture2/cmd/lidar-ping.txt` |
| USB 百兆网卡 | `eth0`，WCH `1a86:5397`，挂在 USB 集线器上，当前无线缆 | 实测 | `capture/cmd/usb-devices.txt` |
| Wi-Fi 与蓝牙 | Wi-Fi 为 PCIe 的 Realtek rtl8822ce；蓝牙为 USB 的 Realtek `13d3:3549` | 实测 | `capture/cmd/net-drivers.txt`、`capture2/cmd/rfkill.txt` |
| 摄像头 | 三个 Sonix `0c45:6366` USB 2.0 UVC 相机，型号与序列号相同；MJPG 最高 2592×1944@30，YUYV 在 1280×720 仅 10 fps | 实测 | `capture2/cmd/v4l2-formats.txt` |
| 相机稳定路径 | `4.2.1.3`→`video2`（定位）、`4.2.2`→`video0`（网页）、`4.2.4`→`video4`（空闲）。序号会漂移，须用 by-path | 实测 | `capture/cmd/v4l-bypath.txt` |
| 主控 | ESP32-S3，两个 USB 口：`ttyACM0` 为 CH343（`1a86:55d3`，控制串口），`ttyACM1` 为 Espressif 原生 USB 调试口 | 实测 | `capture2/cmd/udev-esp.txt` |
| 主控固件 | `control_1.ino` 在仓库中；机器上实际烧录的版本无法读取 | 未知 | `docs/source/firmware/` |
| USB 拓扑 | 根口 4 接 4 口 USB 2.0 集线器（`0bda:5420`），其下：USB 网卡、两级 Genesys 集线器（挂三个相机）、CH343、Espressif。USB 3.0 集线器链（`0bda:0420`）无设备 | 实测 | `capture/cmd/lsusb-t.txt`、`usb-devices.txt` |
| 供电测量 | 19 V 轨 19.01–19.11 V，5 V 轨 5.04–5.05 V，约 3.1 万个采样无低于 18.5 V | 实测 | `capture/home/power.log` |
| 电池与底盘 | 29.4 V、20 Ah 锂电池，履带底盘，电调与电机 | 文档 | 资料 S5 |
| 显示器 | 采集时无显示输出；GDM 自动登录用户 `sjytt` | 实测 | `capture2/cmd/drm.txt`、`gdm.txt` |
| 风扇与温度 | `nvfancontrol` 运行；CPU 约 43 ℃ | 实测 | `capture2/cmd/fan.txt`、`capture/cmd/thermal.txt` |
| 热成像、烟雾、燃气、深度相机、灭火机构 | 资料中的设计项，原机无对应设备或程序 | 未接入 | 资料 S6、`docs/live-audit-20261023.md` |

## 二、系统与基础软件

| 项 | 值 | 状态 | 来源 |
| --- | --- | --- | --- |
| 系统 | Ubuntu 20.04.6，内核 5.10.120-tegra，L4T R35.4.1，aarch64 | 实测 | `capture/cmd/os-release.txt`、`uname.txt` |
| 启动参数 | `console=ttyTCU0,115200`、`net.ifnames=0`、根分区 `mmcblk0p1` | 实测 | `capture/cmd/cmdline.txt` |
| 时钟 | 同步为 yes，NTP 运行；机器有 RTC | 实测 | `capture/cmd/timedatectl.txt` |
| systemd 与 cgroup | systemd 245，cgroup v1（混合） | 实测 | `capture/cmd/systemd-version.txt`、`cgroup.txt` |
| 交换 | 8 个 zram 共约 31 GiB | 实测 | `capture/cmd/swap.txt` |
| ROS | Noetic，共 207 个包，含 `move_base`、`amcl`、`map_server`、`robot_localization`、`tf2`、`pcl_ros`、`cv_bridge` | 实测 | `capture2/cmd/ros-packages.txt` |
| Python | 3.8.10；numpy 1.17.4、cv2 4.2.0、pyserial 3.4、PyYAML 5.3.1 | 实测 | `capture/cmd/python-modules.txt` |
| 编译链 | GCC 9.4、CMake 3.16.3、Eigen 3.3.7、PCL 1.10、OpenCV 4.2.0（apt 版） | 实测 | `../2026-10-23/build-runtime.json` |
| CUDA 与推理 | apt 中仅有 `nvidia-l4t-core`、`nvidia-l4t-cuda` 驱动库；无 CUDA 工具包、TensorRT、cuDNN，`nvcc` 不在 PATH，未装 JetPack 元包 | 实测 | `capture2/cmd/cuda.txt`、`../2026-10-23/apt-packages.tsv` |
| 开发工具 | 机器上无 Arduino CLI、PlatformIO、esptool | 实测 | `capture/cmd/esp-tools.txt` |
| 全部包版本 | apt 2646 项，pip 126 项 | 实测 | `../2026-10-23/apt-packages.tsv`、`python-packages.json` |
| 远程访问 | Tailscale 1.104.2；`ssh`（22）与 `sshd-2222`（2222）；Wi-Fi 为手机热点，经中继，不能直连 | 实测 | `capture/cmd/tailscale-version.txt`、`sshd-2222.txt` |
| 桌面索引服务 | GNOME tracker 原先持续写盘约 2.8 MB/s，已被停用 | 实测 | `probes/probe_rails_out.txt` |

## 三、应用与算法软件

| 组件 | 版本与位置 | 本地修改 | 来源 |
| --- | --- | --- | --- |
| FAST-LIVO2 | HKU 上游 `0d2c034`，`~/livo2_ws/src/FAST-LIVO2`；2026-09-10 编译 | 仅新增 `config/camera_unitree.yaml`、`config/unitree_l2.yaml`、`launch/mapping_unitree_l2.launch` | `capture/src-state/livo2_ws_src_FAST-LIVO2.status.txt` |
| rpg_vikit | `6c886c8` | 无 | `capture/src-state/livo2_ws_src_rpg_vikit.status.txt` |
| Sophus | `a621ff2`，`~/Sophus_src` | `sophus/so2.cpp` 一处补丁，补丁文件已保存 | `capture/src-state/Sophus_src.local.patch` |
| 雷达 SDK v2 | `unilidar_sdk2` `0e3c51f`（v2.0.10），当前使用 | `config.yaml` 改为系统时间戳，另有第二台雷达配置与 launch | `capture/src-state/unilidar_sdk2.*` |
| 雷达 SDK v1 | `unilidar_sdk` v1.0.16，**含双雷达配置** `config_radar0.yaml`、`config_radar1.yaml`、`run_radar0_radar1.launch` | 修改过驱动头文件与配置 | `capture2/other/unilidar_sdk_v1/` |
| 未启用的驱动 | `~/rslidar_ws`（已构建，未使用）、`~/ch343ser_linux` | — | `capture2/cmd/rslidar-ws.txt` |
| 自研应用 | `~/jiaoda`，约 60 个文件，当前版本逐字节保存在 `capture2/jiaoda/`，源码基准在 `docs/source/jiaoda/` | 见 `evidence README` 的核对结果 | `capture2/jiaoda.sha256` |
| 编译产物 | `fastlivo_mapping` 与 `unitree_lidar_ros_node` 的哈希已记录 | — | `capture/cmd/binaries.txt` |
| 构建过程 | 克隆、依赖、Sophus 补丁与 `catkin_make` 的脚本在 `capture/home/p1_*.sh` | — | `capture/home/` |

## 四、服务

| 类别 | 服务 | 说明 |
| --- | --- | --- |
| 感知与定位 | `jiaoda-lidar`、`jiaoda-restamp`、`jiaoda-campub`、`jiaoda-fastlivo`、`jiaoda-posebridge`、`jiaoda-grid` | 主链，`restamp` 的输出当前无人消费 |
| 导航与任务 | `jiaoda-nav`、`jiaoda-mission`、`jiaoda-console`、`jiaoda-control` | 导航、任务、网页与串口桥 |
| 原有保护 | `jiaoda-slamguard`、`jiaoda-serialguard`、`jiaoda-sshguard`、`jiaoda-powerlog`、`jiaoda-safe-stop` | SLAM 发散重启、串口自愈、sshd 守卫、电压记录、关机保护 |
| 本次新增 | `jiaoda-memguard`、`jiaoda-netguard`、`jiaoda-blackbox`、`jiaoda-usbpower` | 见 `deploy/hardening/` |
| 其他 | `sshd-2222`、`tailscaled`、GDM、`jiaoda-netwatch`（被 mask） | — |
| 已停用 | `jiaoda-calib`、`jiaoda-chassis` | 旧工具，勿启用 |

全部单元原文及覆盖配置见 `capture/etc/etc/systemd/system/`，生效后的合并结果见 `capture/cmd/units-effective.txt`。

## 五、未能获取与需现场确认

| 项 | 原因或需要 |
| --- | --- |
| 主控实际烧录固件 | 需通过串口或烧录工具读取，涉及复位主控，须架空并经确认 |
| 电机、电调、遥控接收机、电池型号 | 属机械与电气实物，需人工记录 |
| 相机与雷达的外参、内参标定报告 | 仅有 yaml 数值与一张投影叠加图，无原始误差报告 |
| 第二台 L2、第四个建图相机 | 机器上未接入，需确认实物是否存在 |
| 显示屏型号与连接 | 采集时无显示输出 |
| 一段完整的 rosbag | 从未录制 |
