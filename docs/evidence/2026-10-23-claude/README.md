# 原机采集（第二份，2026-10-23）
目标：记录原机的系统、硬件、软件与运行状态，使不连接机器也能核对和复现。与 `../2026-10-23/`（另一份采集）互补，不重复其内容。

| 目录 | 内容 | 采集脚本 |
| --- | --- | --- |
| `capture/` | 系统、设备、网络、服务、`/etc` 配置、家目录脚本、源码仓库状态与本地补丁、构建参数 | `tools/jetson_capture.sh` |
| `capture2/` | 硬件细节、`~/jiaoda` 当前全部文件及哈希、未启用的软件、ROS 包 | `tools/jetson_capture_hw.sh` |
| `probes/` | 逐项探查的原始输出：电源轨、磁盘写入、USB 拓扑与报错、源码哈希比对、黑匣子样本 | `probes/*.sh` |

## 采集方式与边界

- 通过 Tailscale SSH 只读采集，采集脚本以最低 CPU 与磁盘优先级在后台运行，输出分文件落盘。
- 未读取 systemd 日志，未打开串口，相机仅做能力查询，未发布任何 ROS 消息，未发送运动指令。
- 脱敏：MAC 地址、运营商分配的全局 IPv6 地址、Tailscale 账号名已打码；Wi-Fi 密码、SSH 密钥、Tailscale 节点密钥、命令历史未采集。
- 家目录构建脚本 `p1_build.sh`、`p1_fix.sh` 及两份构建日志含明文 sudo 密码，已替换为 `<REDACTED-PASSWORD>`。机器上的原文件未改动，见 `../../stability-20261023.md` 的待办。

## 核对结果

| 比对 | 结果 | 依据 |
| --- | --- | --- |
| `~/jiaoda` 与仓库 `docs/source/jiaoda/` | 22:01 时 76 个文件中 75 个一致；23:51 时 61 个文件中 54 个一致 | `probes/remote_jiaoda_sha.txt`、`capture2/jiaoda.sha256` |
| 23:51 的差异 | `console_backend.py` 为本次补丁；`floor1.npz`、`routes/default.json` 为用户新数据；新增 `serial_guard.py`、`run_serialguard.sh`、`teach_run1.jsonl`，已补入 `docs/source/` | 同上 |
| FAST-LIVO2 工作区 | 144 个文件中 111 个一致，其余 33 个为上游自带的文档、结果与图片 | `probes/remote_livo2_src_sha.txt` |
| 雷达驱动源码 | 12 个文件全部一致 | `capture/cmd/lidar-src-sha.txt` |
| 服务单元 | 仓库缺 `jiaoda-serialguard.service`，已补入；另有本次新增的加固单元在 `deploy/hardening/` | `capture/etc/etc/systemd/system/` |

## 关键事实索引

| 主题 | 位置 |
| --- | --- |
| 系统版本、CPU 与电源模式（30W、8 核、1.73 GHz） | `capture/cmd/uname.txt`、`jetson_clocks.txt`、`nvpmodel.txt` |
| 启动参数（串口控制台 `ttyTCU0`、`net.ifnames=0`） | `capture/cmd/cmdline.txt` |
| USB 设备与集线器层级 | `capture/cmd/usb-devices.txt`、`lsusb-t.txt`、`probes/probe3_out.txt` |
| 网卡与驱动（`eth1` 板载以太网接雷达，`eth0` 为 USB 百兆网卡，`wlan0` 为 PCIe 的 rtl8822ce） | `capture/cmd/net-drivers.txt`、`ip-addr.txt` |
| 相机型号、格式与稳定路径 | `capture2/cmd/v4l2-list.txt`、`v4l2-formats.txt`、`capture/cmd/v4l-bypath.txt` |
| 两个串口的身份（CH343 为 `ttyACM0`，Espressif 为 `ttyACM1`） | `capture2/cmd/udev-esp.txt` |
| 源码仓库本地修改与补丁（Sophus、雷达 SDK） | `capture/src-state/` |
| 编译参数与可执行文件哈希 | `capture/cmd/cmake-livo2.txt`、`binaries.txt` |
| 构建过程脚本（克隆、依赖、Sophus 补丁、catkin） | `capture/home/p1_clone.sh`、`p1_build.sh`、`p1_fix.sh` |
| 旧版雷达 SDK 的双雷达配置与启动文件 | `capture2/other/unilidar_sdk_v1/` |
| 全部服务单元及本次新增的覆盖配置 | `capture/etc/etc/systemd/system/` |
| 电压记录与黑匣子 | `capture/home/power.log`、`blackbox.log` |
| 改动前的应用备份 | `capture/home/backup/jiaoda-before-fix-1021-1327.tar.gz` |
