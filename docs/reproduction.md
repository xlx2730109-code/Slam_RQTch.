# 同配置 Jetson 复现步骤

目标：在另一台同配置机器人上分阶段重建软件，分别验收构建、数据链、建图、运动、任务和跨重启定位。

当前只完成离线文件与生成工具验证，尚未在新Jetson编译，也未执行任何机器人运动测试。默认候选不启用底盘和巡检任务。

## 复现对象

| 对象 | 历史基准 | 新机必须补查 |
| --- | --- | --- |
| 计算板 | Jetson AGX Orin Developer Kit | 准确型号、内存、存储 |
| 系统 | Ubuntu20.04、L4T R35.4.1、内核5.10.120-tegra | 系统版本与依赖清单 |
| ROS | Noetic、Python3.8 | 实际安装与环境加载 |
| 编译依赖 | GCC9.4、CMake3.16、Eigen3.3.7、PCL1.10、Boost1.71 | 新机安装版本与编译结果 |
| Python依赖 | 原记录numpy1.17.4、cv2 4.2.0、pyserial3.4、PyYAML5.3.1 | 版本与导入成功记录 |
| 雷达 | 一台Unitree L2，UDP | 网卡名、IP、供电、点云字段 |
| 相机 | UVC RGB，定位图像1280×720 | 物理角色、by-path、实际尺寸与标定 |
| 主控 | ESP32-S3，Arduino-ESP32 3.x API | Arduino核心精确版本、板型和固件选项 |
| 电调和云台 | 油门/转向PWM接口 | 供电、接线、脉宽响应、方向和急停 |

历史版本是对齐目标，不是安装锁文件。仓库不包含JetPack镜像、所有apt包或Arduino板级工具链，不能承诺全程离线。不要为了对齐表格直接升级或降级原机器人环境。

## 阶段0 离线准备

在仓库根目录检查原机源码、Python3.8语法兼容性和XML结构。

```bash
python3 -B tools/reproduce.py audit
```

检查会报告233个基准文件、旧netwatch空单元，以及未使用的`vikit_py/depthmap_utils.py`含Python2语法。后者不在当前Python运行入口中；不能据此声称所有厂商辅助脚本都能在Python3执行。

创建自己的设备配置，字段格式参照`deploy/robot.example.json`。配置副本及候选输出在本地调试期间存入用户指定E盘临时任务目录；要保留的正式设备配置另按用户指定位置管理。必核字段：

| 字段 | 作用 | 要求 |
| --- | --- | --- |
| user | systemd运行用户 | 新Jetson真实用户 |
| install_root | 候选目标目录 | `/home/<user>/<独立目录>`，目录名仅字母数字下划线连字符 |
| camera_device | 定位相机 | 新机验证过的`/dev/v4l/by-path/...` |
| serial_device | 五字段主控口 | 原生USB调试口与控制口需要分清 |
| console_camera_index | 网页视频相机索引 | 仍是索引，存在漂移风险；新机需验证 |
| console_port | 本机网页端口 | 避免8095和11311冲突 |
| lidar_pc_ip/lidar_ip | 雷达局域网 | 两者不同，并核对网卡实际配置 |

Windows生成离线候选，不覆盖已有目录。

```powershell
python -B tools/reproduce.py stage --config deploy/robot.example.json --output E:\HuanCun\AI_tmp\GPT\tmp_20261022_slam_repro\candidate
```

生成工具不会启动服务、改网卡或刷固件。临时候选用完可删除；需要长期保留时另按用户指定目录归档。

候选部署到配置的`install_root`后结构如下，下面路径以相对候选目录表示。

```text
candidate/
├── firmware/                    两份独立Arduino草图，不能合并编译
├── jiaoda/                      路径已适配的原应用副本
├── livo2_ws/src/                 FAST-LIVO2与rpg_vikit
├── reference_maps/              旧机地图，只作参考
├── Sophus_src/                  原版本源码
├── systemd/                     新前缀jiaoda-repro单元
├── unilidar_sdk2/               雷达catkin工作区与SDK
├── build.sh                     只构建，不启动服务
├── candidate-sha256.json         输出文件哈希
├── candidate.json                配置、基准及生成改动记录
├── health_check.py               ROS与HTTP只读检查
├── preflight.py                  环境和设备检查
└── run_node.sh                   消息等待和节点运行入口
```

生成器对原副本的适配列在`candidate.json`：应用绝对路径、雷达IP和FAST-LIVO2本地Sophus库搜索路径；候选不复制旧根目录`run*.sh`，统一使用生成的`run_node.sh`。没有修正原算法和运动控制缺陷，不能绕过后续验收直接上地运行。

## 阶段1 环境与编译

在新Jetson上记录系统身份。

```bash
cat /etc/nv_tegra_release
```

记录操作系统和CPU架构。

```bash
uname -a
```

将候选复制到配置的独立目录，再检查构建依赖。下方命令假设示例用户与目录；如果配置更换了用户名，需要对应替换。

```bash
python3 /home/sjytt/slam_repro/preflight.py --build
```

依赖包括ROS Noetic、catkin、编译工具、Eigen、PCL、OpenCV、Boost，以及`cv_bridge`、`pcl_ros`、`image_transport`、`eigen_conversions`、`tf`、numpy、pyserial和PyYAML。以本机apt仓库和项目`package.xml/CMakeLists.txt`核对安装，不复用历史文档中过时的添加软件源命令。校准工具另要求`cv2.aruco`，应单独检查，避免pip OpenCV替换ROS所用ABI。

环境检查通过后构建。该操作只在新机候选路径写构建产物，不执行`sudo make install`。

```bash
bash /home/sjytt/slam_repro/build.sh
```

构建顺序为Sophus、FAST-LIVO2工作区、雷达工作区。Sophus通过显式`Sophus_DIR`和候选库路径使用。原CMake版本与新版CMake兼容性、库链接、Python厂商包安装行为尚需实际验证；失败时保留原始错误，不用“能生成文件”代替编译成功。

## 阶段2 静止感知与建图

确认候选与旧栈分时运行：话题、ROS11311端口、相机、串口、HTTP端口和`/dev/shm`文件均有共享。新启动脚本拒绝与active旧单元并行，但手工进程仍须现场排查。不要运行旧宽泛`pkill`脚本。

手动配置雷达网卡前，先核对真实接口名和现有地址；生成工具不会代改NetworkManager。

```bash
ip -4 addr
```

检查相机稳定路径。

```bash
ls -l /dev/v4l/by-path/
```

检查主控口身份，本阶段不打开串口。

```bash
ls -l /dev/serial/by-id/
```

先用多个终端前台启动，不安装自启。各命令在独立终端执行。

启动独立Master。

```bash
bash /home/sjytt/slam_repro/run_node.sh roscore
```

启动雷达。

```bash
bash /home/sjytt/slam_repro/run_node.sh lidar
```

启动点云时标转发。

```bash
bash /home/sjytt/slam_repro/run_node.sh restamp
```

启动定位相机。

```bash
bash /home/sjytt/slam_repro/run_node.sh campub
```

启动融合估计。

```bash
bash /home/sjytt/slam_repro/run_node.sh fastlivo
```

启动位姿桥。

```bash
bash /home/sjytt/slam_repro/run_node.sh posebridge
```

启动栅格。

```bash
bash /home/sjytt/slam_repro/run_node.sh grid
```

启动本机控制台；没有控制桥时不产生底盘串口指令。

```bash
bash /home/sjytt/slam_repro/run_node.sh console
```

在另一个已加载ROS环境的终端做并行接收检查。

```bash
python3 /home/sjytt/slam_repro/health_check.py --profile sensing
```

这只检查窗口内的实际接收频率、末条消息接收新鲜度和HTTP字段。它没有证明硬件测量时间正确、地图精度合格、照片可上传或机器人能避障。

记录同一段原始数据用于回放。输出`.bag`是现场正式验收证据，须放到新机明确指定的验收数据目录，不沿用Windows临时目录。

```bash
rosbag record -O /path/to/acceptance/session01.bag /unilidar/cloud /unilidar/imu /synced/cloud /left_camera/image /aft_mapped_to_init /cloud_registered /slam_pose /map
```

此处`/path/to/acceptance`是待用户指定的目录，不能原样执行。回放分析时记录点云字段、点内时间范围、时间单调性、传感器延迟、矩形场地尺寸误差和重复运行差异。

## 阶段3 控制与任务

运行控制前先完成根README高优先级缺陷的修复及离线检查。候选仍保留原型行为：取消不传到导航、雷达无失效时效、末端绕过DWA和RC模式时效等问题尚未修复。

架空后按以下顺序验收，每项保留指令、反馈和实际动作记录：

1. 主控控制口和五字段协议，确认RC与串口当前模式。
2. 前后与左右方向，明确`INVERT_YAW`、固件反向及电调接线的组合。
3. 失去速度指令、串口断开、RC信号丢失、Jetson程序退出时的停车。
4. 串口拔插恢复与任务取消，防止旧命令恢复。
5. 地面低速测车速、转向率、制动距离和障碍边界。
6. 多点导航停车后再拍照，确认图像新鲜度、实际云台姿态、任务与点位元数据。

主控两份`.ino`是独立草图，原Arduino核心精确版本和USB CDC选项未归档。必须核对串口`Serial`实际走CH343 UART还是原生USB，不能只凭ESP32-S3板型推断。

## 阶段4 持久地图与服务托管

跨重启功能需要新增全局定位/重定位层、地图身份、位姿变换与路线绑定。仅恢复`floor1.npz`和旧航点不能完成这一步。先验证同会话，再验证关机、移动机器人和重新开机后的旧地图定位。

前台感知验收通过后，才将候选`systemd/`单元安装到新机系统目录并手动启动感知服务。安装与自启是不同动作；先使用`systemctl start`，通过重启验收后才决定`enable`。本轮没有执行任何安装或服务启动，也不提供自动启用全控制栈的一键命令。

## 本轮离线验证记录

| 检查 | 本轮结果 | 能证明什么 |
| --- | --- | --- |
| 基准文件清单 | 233项一致 | 源码和原快照一致，文本统一LF |
| Python语法与XML | 活跃应用和工具语法通过；13份XML可解析 | 不证明ROS导入和C++可编译 |
| 配置与路径 | 拒绝危险路径、非法字段、端口冲突与旧输出目录 | 限定生成目标和输入形式 |
| 候选生成 | 更换Linux用户后路径一致、11份单元生成 | 不绑定原用户，不启动设备 |
| 输出哈希 | 测试候选逐文件校验通过 | 生成副本内容可追踪 |
| 原基准保护 | 生成前后清单一致 | 没有改写原机导出运行代码 |
| 测试清理 | 临时测试副本自动删除 | 不遗留测试部署树 |

2026-10-22离线回归共7个测试通过。两份Bash模板经`bash -n`解析通过；Windows运行健康检查按预期报告缺少`rospy`，未伪装成真机通过。

Windows离线测试命令需要已授权的E盘临时目录。

```powershell
$env:SLAM_TEST_TMP='E:\HuanCun\AI_tmp\GPT\tmp_20261022_slam_repro'
```

执行测试。

```powershell
python -B -m unittest discover -s tests -v
```

这些检查只读取或生成本地副本，不使用机器人硬件。任务总进度与下一步统一维护在根README。
