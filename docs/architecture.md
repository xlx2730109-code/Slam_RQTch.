# 消防巡检机器人实现与接口

目标：解释源码与2026-10-23原机实际链路，区分历史版本、当前配置和未完成能力。复现进度与固定结论编号见根 `README.md`，原始证据见[实机核查](live-audit-20261023.md)。历史基准为`3b664ba`，本次核对的是后续`9d6e531`及其当前源码。

当前`img_en=0`，FAST-LIVO2直接使用`/unilidar/cloud`和IMU；相机仍用于拍照，`/synced/cloud`仍发布但不是当前SLAM输入。静止定位已经严重发散，以下模块解释不表示当前功能可用或合同验收通过。

## 总体链路

```mermaid
flowchart TD
  lidar[L2 UDP 驱动] --> cloud[/unilidar/cloud]
  lidar --> imu[/unilidar/imu]
  camera[USB RGB 相机] --> image[/left_camera/image]
  cloud --> stamp[cloud_restamp 覆盖头时间]
  stamp --> synced[/synced/cloud]
  cloud --> livo[FAST-LIVO2 LIO]
  imu --> livo
  livo --> odom[/aft_mapped_to_init]
  livo --> points[/cloud_registered]
  odom --> pose[pose_bridge]
  pose --> nav[nav_simple]
  cloud --> nav
  points --> grid[grid_bridge]
  odom --> grid
  grid --> map[/map 与 PNG/NPZ]
  map --> nav
  web[网页控制台] --> mission[nav_mission]
  mission --> goal[/move_base_simple/goal]
  goal --> nav
  image --> mission
  mission --> photos[本地 JPG]
  nav --> cmd[/cmd_vel]
  web --> cmd
  cmd --> bridge[串口控制桥]
  bridge --> esp[ESP32 五字段协议]
  esp --> motor[油门 转向 云台 PWM]
```

当前机器人靠雷达和IMU估计位置；原算法支持视觉融合，但现配置关闭。再根据地图和目标点计算行驶命令。ESP32把命令转换成电调和舵机需要的PWM。上层有定位反馈接口，但底层没有实际轮速闭环；不能把整条链概括为“已经有精确车速控制”。

## 模块与关键接口

| 模块 | 源码 | 输入 | 输出 |
| --- | --- | --- | --- |
| 雷达驱动 | `source/unitree_lidar_ros/include/unitree_lidar_ros.h` | L2 UDP 数据 | 点云、原始 IMU、扫描与雷达 TF |
| 相机发布 | `source/jiaoda/cam_publisher.py` | V4L2 RGB 图像 | `sensor_msgs/Image`，bgr8 |
| 时标转发 | `source/jiaoda/cloud_restamp.py` | 原始点云 | 改写头时间的点云 |
| 融合估计 | `source/FAST-LIVO2/src/LIVMapper.cpp` | 点云、IMU、图像 | `Odometry`、点云、路径与 TF |
| 位姿桥 | `source/jiaoda/pose_bridge.py` | 融合里程计 | `PoseStamped`、合成 `Imu` |
| 栅格 | `source/jiaoda/grid_bridge.py` | 世界点云、里程计 | `/map`、PNG、地图元信息、NPZ |
| 导航 | `source/jiaoda/nav_simple.py` | 地图、位姿、近距点云、目标 | `Twist`、规划路径 |
| 任务 | `source/jiaoda/nav_mission.py` | 航点文件、位姿、定位相机图像 | 目标点、云台、JPG 和任务状态 |
| 控制台 | `source/jiaoda/console_backend.py` | HTTP、里程计、共享文件 | 网页、视频、手动速度与任务命令 |
| 控制桥 | `source/jiaoda/chassis_gimbal_bridge.py` | 速度和云台话题 | 串口五字段帧和遥测字符串 |
| 固件 | `source/firmware/control_1.ino` | RC 脉冲、串口 | 油门/转向/云台 PWM |

本表路径相对 `docs/`。主要启动入口是历史 `source/jiaoda/run*.sh` 和 `source/systemd/`；新候选部署入口见 `reproduction.md`。

## 采集和同步

雷达配置 `source/unitree_lidar_ros/config/config.yaml` 选择 UDP，L2 地址 `192.168.1.62:6101`，PC 地址 `192.168.1.2:6201`。这些是原机配置，不是新机自动发现的地址。

相机发布脚本先用 `CAMPUB_DEV`，未指定才用 `CAMPUB_INDEX`。当前原启动脚本已经绑定 USB by-path，不再是旧手册所写的固定索引3。读取失败连续10帧后重开，打不开约每2秒重试。相机默认输出1280×720、15fps，但驱动是否实际接受设置仍需读取实际画面尺寸。

这里存在三种时间语义：

| 数据 | 当前时间来源 | 影响 |
| --- | --- | --- |
| 原始点云头 | SDK 的 `cloud.stamp` | 当前`use_system_timestamp=true`，历史false配置另行保留 |
| `/synced/cloud` 头 | `rospy.Time.now()` | 只是接收端改时标，不是硬件同步 |
| 原始 IMU 头 | 驱动 `ros::Time::now()` | 接收时刻，不是传感器原始采样时间 |
| RGB 图像头 | 采集后 `rospy.Time.now()` | 包含读取和传输延迟 |
| 融合输出头 | C++ 发布时 `ros::Time::now()` | 不能直接当作滤波状态对应的测量时刻 |

SDK协议定义`time_increment`为秒，工具函数据此累计点内相对时间，并转发为浮点`time`。FAST-LIVO2的`lidar_type=2`对应`VELO16`分支，该分支把`time / 1000.0`存入`curvature`，而后续同步按`curvature / 1000.0`还原秒。2026-10-23实测点内time范围约0.000007723至0.081184，支持百万倍尺度疑点；但尚无修改前后同数据回放，不能把它定为唯一根因或宣称改后精度提高。

PCL输出的 `x/y/z/intensity/time` 是float，`ring`是uint16，与当前读取结构的字段声明相符；字段声明相符不代表扫描时序和合帧语义已验证。`scan_line=18`也不能直接解读为L2物理18线。

## FAST-LIVO2 计算过程

启动 `mapping_unitree_l2.launch` 时加载两份 YAML：主配置进入公共参数空间，相机参数进入 `laserMapping` 节点私有空间。`LIVMapper::readParameters`读取传感器话题、外参、滤波参数等。

1. `standard_pcl_cbk`根据`lidar_type`预处理点云，保存点内时间与帧头时间。
2. `imu_cbk`保存惯性数据并处理时间偏移。
3. `img_cbk`读取相机图像，保存图像时间。
4. `sync_packages`按模式组织数据；启用视觉时按图像时刻切分，当前`img_en=0`走激光惯性模式。
5. IMU传播预测运动状态并辅助点云去畸变。
6. LIO利用点云与体素平面匹配校正状态并更新局部几何地图。
7. VIO利用图像块与视觉地图的光度关系继续校正状态。
8. 发布融合位姿、注册点云、轨迹等结果。

算法核心职责是连续里程计和建图。当前仓库没有找到持久地图全局重定位或回环后端的接入实现。不能因名称含SLAM，就认为开机后会自动在旧地图里找到自己。

`Rcl/Pcl`表示雷达到相机的变换；`extrinsic_R/T`表示雷达与IMU之间的安装关系。实际配置为非零IMU平移和相机90度旋转，旧标定说明中“保持单位阵/0”不能照搬。`camera_unitree.yaml`声明相机1280×720且`scale=0.5`，外部投影检验应明确使用原图还是缩小图及匹配的内参。

原仓库投影叠加图可作几何检查参考；没有完整样本、独立重投影误差与测量报告，不能由一张图推出完整标定精度，也不能推出另一台机器人可直接复用。

## 坐标系与地图

FAST-LIVO2源码实际广播`camera_init -> aft_mapped`。雷达驱动另广播其IMU初始系、IMU系和雷达系。位姿桥把融合数值重新标记为`map/base`，没有显式转换到车体中心。

地图和导航以这些数值直接计算，因此它们可能在同一启动会话内看起来一致，但车体中心与雷达/IMU的偏移、转向符号和重启后的原点都需要分别确认。后续标准化TF时要先测安装外参，不能直接添加全零静态TF。

`grid_bridge`按相对高度和距离过滤世界点云，用log-odds累计占据概率；自由空间只随机抽部分射线清除，因此同一数据重复建图可能不同。发布`OccupancyGrid`时上下翻转，网页PNG用顶部原点，点击地图时需要做y方向转换。

| 资产 | 生成者 | 内容 | 使用边界 |
| --- | --- | --- | --- |
| `/map` | grid | 二维占据栅格 | 给A*，不是三维定位地图 |
| `jiaoda_map.png` | grid | 裁剪与放大的地图图像 | 网页显示，含机器人标记 |
| `jiaoda_map.json` | grid | x0、y0top、mpp、w、h | 网页像素与世界坐标转换 |
| `floor1.npz` | grid | log_odds、size、res | load只恢复数组，不恢复机器人位姿 |

`Grid.load`只比较数组形状，未验证保存分辨率与当前分辨率一致。地图按钮`freeze`只改后端状态，没有通知grid停止积分。保存快照也不等于停止建图。

## 导航如何工作

1. 接收目标点后读取当前位姿和栅格。
2. 地图占据区域膨胀后做8邻域A*；当前未知格`-1`被当作可通行。
3. 全局路径生成一次，后续没有自动重规划。
4. 20Hz循环选路径前方约0.8m的跟踪点。
5. 采样5×11组线速度和角速度，前向模拟2秒，以目标距离、朝向、速度和障碍距离评分。
6. 进入距终点0.8m范围后切为简单比例控制；距终点小于0.30m判为到达。

该实现是DWA风格采样器，没有根据当前速度和加速度构造标准动态窗口。它有位置与合成IMU更新时间检查，但没有雷达接收时间检查。无雷达点、旧雷达点、末端绕过碰撞检查，以及A*失败后直线兜底都必须纳入下一轮修复。

顶部`VYAW_MAX=0.30`并非全局保证：末端分支允许0.4，堵塞分支允许0.6且给0.05前进量。“原地脱困”的注释与实际输出不一致。最终方向还有`INVERT_YAW=True`和固件`-steer`两处符号转换，需要架空逐向验证。

## 任务、云台和拍照

网页写入`/dev/shm/jiaoda_mission.json`和`jiaoda_nav_cmd`。任务节点读取航点并发布`/move_base_simple/goal`，根据`/slam_pose`计算距点距离；小于0.35m后转云台、等0.6秒、保存最新图像，再进下一点。

关键边界：

- 任务0.35m到达阈值大于导航0.30m停车阈值，可能在车尚未停稳时拍照。
- 未验证位姿或图像时间；缓存旧图仍可能保存成功，没有照片新鲜度或写盘成功状态。
- 没有等待云台反馈到位；回传的脉宽也不是实际角度。
- 网页保存`gp/gt`为角度；手动云台会转换为±30协议值，但任务节点直接把角度传给控制桥，存在截断与姿态不一致。
- 任务取消只把本节点`running=False`，没有发`/move_base/cancel`；网页单次零速可被导航后续输出覆盖。
- 任务结束不自动返航；只有明确加入起点航点才可能回起点。
- 当前JPG只有路线、点序号和秒时间文件名，没有完整任务ID、地图ID、位姿、检测结果或上传状态。

`photo.py`能写JPG加JSON元数据，但没有被现用任务导入。优化应先统一记录结构，再接服务器上传，不能把未调用的辅助模块算作已实现功能。

## 串口和固件

```text
Twist.linear.x × THR_K -> 整数限幅±30 -> throttle
Twist.angular.z × STR_K -> 整数限幅±30 -> steer
云台两项限幅±30
四项直接求和 -> checksum
20Hz发送ASCII一行 -> ESP32
```

固件再把非零值分段映射到1000–2000微秒，0映射1500微秒。油门与转向输出给底盘电调/混控器，并非电脑直接控制左右轮速。低速指令也会跨过固定脉宽死区；需要实测`指令 -> 地面速度/转向率`曲线。

| 功能 | 当前实现 | 边界 |
| --- | --- | --- |
| 上位机速度超时 | 0.5s未更新则油门转向归零 | 云台保持旧指令 |
| 固件串口超时 | 0.5s未收到合法帧归中 | RC模式会提前返回串口处理 |
| RC优先 | 两个主通道脉宽有效则RC接管 | 脉宽不记录最后更新时间，丢信号可能保持旧模式 |
| 串口打开 | DTR/RTS在打开前拉低 | 实际复位行为取决于接线，需要现场确认 |
| 断线恢复 | 初始打开失败会重试 | 成功后拔线不会重新建立连接 |
| 遥测 | `GIMBAL_PULSE`及调试文本 | 不提供真实轮速、云台编码角、烟雾或燃气 |

## 网页和公司平台的边界

现有8090网页在Jetson本机运行，HTTP后端只读本地共享状态和发布ROS指令。`/api/pose`没有新鲜度字段，旧缓存也可能正常返回。3D页、路线加载、暂停、拍照按钮和航向标定存在前端或后端占位逻辑。HTTP200不能证明对应动作完成。

没有发现图片上传客户端、服务器地址配置、认证凭据、上传队列、公司数据库或报告模块。本仓库是机器人端原型，后续接公司服务器需要双方明确接口、任务与点位ID、照片原件、数值单位、时间、识别结果、确认和补传机制。

## 已落实与下一轮优化

本轮新增离线基准检查、单一设备配置、候选目录生成、独立ROS Master、消息就绪等待和只读健康检查。新部署默认停在感知验收，不自动启动导航、串口控制或任务。

下一轮优先统一控制仲裁与取消语义，然后处理雷达时效、近终点避障、全局限速、串口恢复和固件RC时效。时间同步与点内时间单位应通过录包单独验证。持久地图重定位是后续旧路线复用的必要条件。所有待办的固定编号保存在根README，避免多处维护进度。
