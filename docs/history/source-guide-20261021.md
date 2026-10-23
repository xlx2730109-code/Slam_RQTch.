# 复现包说明历史快照

本文件保留旧部署说明。当前入口为仓库根目录 `README.md` 和 `docs/reproduction.md`。下面的“一键部署”未经新机器完整验收，不直接执行。

这是从**实机**导出的源码与配置快照，配合 README 第 14 章可从零重建同款系统。

**本目录已包含重建所需的全部源码与依赖**（含第三方库 Sophus、L2 SDK 及预编译静态库），
任何一台电脑 `git clone` 本仓库后都**不需要再访问其他仓库，也不需要这台机器**。
唯一不在仓库里的是工具链本身（Ubuntu/JetPack、ROS Noetic、Arduino IDE），版本见 README 14.2。

## 目录 → 目标路径对照

| 本仓库目录 | 部署到 Jetson 的位置 | 说明 |
| --- | --- | --- |
| `jiaoda/` | `~/jiaoda/` | 应用层全部 Python + 前端 + 标定工具 + 地图 |
| `FAST-LIVO2/` | `~/livo2_ws/src/FAST-LIVO2/` | SLAM 主程序（已含本机改过的 3 个配置） |
| `rpg_vikit/` | `~/livo2_ws/src/rpg_vikit/` | FAST-LIVO2 依赖的视觉工具包 |
| `Sophus_src/` | `~/Sophus_src/` | FAST-LIVO2 编译依赖（李群库，需先装） |
| `unitree_lidar_ros/` | `~/unilidar_sdk2/unitree_lidar_ros/src/unitree_lidar_ros/` | 宇树 L2 驱动（ROS1 包） |
| `unitree_lidar_sdk/` | `~/unilidar_sdk2/unitree_lidar_sdk/` | L2 SDK 头文件 + 预编译静态库；**雷达包用相对路径 `../../../unitree_lidar_sdk` 引用它，缺了编不过** |
| `systemd/` | `/etc/systemd/system/` | 12 个 `jiaoda-*.service` |
| `firmware/` | 任意（Arduino 工程目录） | ESP32 主控固件 `control_1.ino` + `ReadRC.ino` |
| `verify.sh` | `~/jiaoda/verify.sh` | 部署后一键自检 |

## 一键部署（假设本仓库已拷到 Jetson 的 `~/repro`）

```bash
set -e
R=~/repro/docs/source

# 1) 应用层
cp -r $R/jiaoda ~/jiaoda
chmod +x ~/jiaoda/run_*.sh ~/jiaoda/*.py
cp $R/verify.sh ~/jiaoda/verify.sh && chmod +x ~/jiaoda/verify.sh

# 2) Sophus（FAST-LIVO2 的编译依赖，必须先装）
cp -r $R/Sophus_src ~/Sophus_src
cd ~/Sophus_src && mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j4 && sudo make install

# 3) SLAM 工作区
mkdir -p ~/livo2_ws/src
cp -r $R/FAST-LIVO2 $R/rpg_vikit ~/livo2_ws/src/
cd ~/livo2_ws && catkin_make -j4 -DCMAKE_BUILD_TYPE=Release

# 4) 雷达工作区（SDK 必须放在包的上一级，CMakeLists 用相对路径引用）
mkdir -p ~/unilidar_sdk2/unitree_lidar_ros/src
cp -r $R/unitree_lidar_sdk  ~/unilidar_sdk2/
cp -r $R/unitree_lidar_ros  ~/unilidar_sdk2/unitree_lidar_ros/src/
cd ~/unilidar_sdk2/unitree_lidar_ros && catkin_make

# 5) 开机自启
sudo cp $R/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
for s in lidar restamp campub fastlivo grid posebridge nav control console; do
  sudo systemctl enable --now jiaoda-$s
done

# 6) 自检
~/jiaoda/verify.sh
```

> 若 `catkin_make` 报找不到 Sophus，加 `-DSophus_DIR=$HOME/Sophus_src/build`（本机就是这么用的，
> 当时没执行 `make install`）。

## 版本与来源

| 组件 | 版本 / 提交 |
| --- | --- |
| FAST-LIVO2 | `hku-mars/FAST-LIVO2` @ `0d2c034`（含本地 3 处未提交改动） |
| rpg_vikit | `xuankuzcr/rpg_vikit` @ `6c886c8` |
| Sophus | `strasdat/Sophus` @ `a621ff2e`（源码，140 KB） |
| unitree_lidar_ros | `unitreerobotics/unilidar_sdk2` @ `0e3c51f`（`config.yaml` 本地改过） |
| unitree_lidar_sdk | 同上仓库，含 `lib/aarch64/libunilidar_sdk2.a` 预编译静态库 |
| ESP32 固件 | Arduino-ESP32 **3.x**（`ledcAttach(pin, freq, res)` 是 3.0 才有的 API） |
| 导出时间 | 2026-10-21 |

## 注意

- `FAST-LIVO2/` 未包含上游的 `pics/`、`Supplementary/`、`Log/`（纯文档与运行日志，共 ~58 MB）。
- `unitree_lidar_ros/` 未包含 `build/`、`devel/`（编译产物，需自行生成）。
- 四个相机序列号相同，部署后**设备号可能与本机不同**，用 `cam_publisher.py` 的
  `CAMPUB_INDEX` / `CAMPUB_DEV` 指定，别写死 `/dev/videoN`。
