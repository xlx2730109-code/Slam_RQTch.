# 补齐记录与待核对清单（2026-10-23）

> 后续核查更新：已通过SSH对照252个对应常规文件，全部与当前本地源码一致。`img_en=0`、`use_system_timestamp=true`及导航`.30/.26`现已在当前仓库与运行参数中核实；下文“未写入仓库、明天核对”等为提交前的历史记录，不再代表最新状态。漂移改善数值仍只是原记录，未由本轮独立重测。详见[实机核查](../live-audit-20261023.md)。
>
> 下文的一键同步命令暂勿执行：`tools/sync-from-jetson.ps1`存在Host自动变量冲突、组件路径合并和直接覆盖等风险。本轮没有运行它。依赖清单已归档，但系统镜像、完整rosbag、实烧固件版本和新机标定仍缺；“从来没有录过”未能由全盘历史证实，只能说明本次未取得。

## 为什么有这个文件

`docs/source/` 里最初只有 2026-10-21 13:22 从机器上导出的快照。之后的调试过程中，
机器上又新增/修改了若干文件，**没有及时回写仓库**。2026-10-23 本次提交按会话记录把这批文件补回，
但它们**不是从机器上直接导出的**，明天连上 Jetson 后必须逐项核对。

## 一、按会话记录重建的文件（待核对）

| 文件 | 作用 | 核对要点 |
| --- | --- | --- |
| `jiaoda/safe_stop.py` | 关机/停服务前发 2 秒中位帧 | 是否在机器上存在、行数一致 |
| `jiaoda/power_log.sh` | 记录 19V 电压到 `~/power.log` | 采样间隔、hwmon 路径 |
| `jiaoda/record_cmd.py` | 录摇杆 `/cmd_vel` | — |
| `jiaoda/replay_cmd.py` | 按时间轴回放 | — |
| `jiaoda/replay_by_distance.py` | 按里程回放（推荐） | — |
| `jiaoda/patrol_simple.py` | 位姿直达点巡检（带三道保护） | — |
| `jiaoda/corridor_follow.py` | 雷达沿墙直行 | 已修正"里程不累加"的 bug |
| `jiaoda/teach_record.py` | 录位姿轨迹 | — |
| `systemd/jiaoda-netwatch.service` | Wi-Fi 看护（原仓库该文件为 0 字节） | 内容是否与机器一致 |
| `systemd/jiaoda-powerlog.service` | 电压记录单元 | 机器上是否已安装 |
| `systemd/jiaoda-safe-stop.service` | 关机前回中位单元 | 机器上是否已 enable |
| `systemd/jiaoda-control.service` | 补上 `ExecStop` + `TimeoutStopSec` | 机器上已是此版本 |

## 二、已知的配置差异（未写入仓库，等核对后再决定）

| 文件 | 仓库里的值 | 机器上最后一次已知值 | 影响 |
| --- | --- | --- | --- |
| `FAST-LIVO2/config/unitree_l2.yaml` → `img_en` | `1` | `0`（关视觉，纯激光惯性） | 静止 yaw 漂移 1.87 → 0.42 °/s |
| `unitree_lidar_ros/config/config.yaml` → `use_system_timestamp` | `false` | 曾改 `true`（随后整栈重启，最终值未确认） | 关系到 `cloud_restamp` 是否必需 |
| `jiaoda/nav_simple.py` | `VX_MAX=0.20`，无安全守卫 | `VX_MAX=0.30`、`VX_MIN=0.26`、`VYAW_MAX=0.30`，另有 `POSE_JUMP` 与 `STUCK_GUARD` | 限速与失控保护 |

> 这三处是**实测调优结果**，不是随意改动，核对后应保留到仓库。

## 三、仍然缺的（需要机器在线才能补）

| 项 | 原因 |
| --- | --- |
| 完整系统镜像 / apt 包清单 | 需要 `dpkg --get-selections`、`pip freeze`、`nv_tegra_release` 导出 |
| 新机标定报告 | 只有原机的 `Rcl/Pcl`，换硬件必须重标 |
| 实机运行记录（rosbag） | 从来没有录过 |
| 机器上 `~/jiaoda` 的最终文件清单 | 需要 `find` 对比，确认没有遗漏脚本 |

## 四、明天连上机器后的核对顺序

```bash
# 1. 全量同步（本仓库 tools/sync-from-jetson.ps1 或手工 scp）
.\tools\sync-from-jetson.ps1 -Host 192.168.55.1

# 2. 对比文件清单
ssh sjytt@192.168.55.1 'cd ~/jiaoda && find . -type f ! -name "*.pyc" | sort' > /tmp/remote.txt

# 3. 逐项确认本文第一节的 12 个文件

# 4. 确认第二节三处配置的最终值，决定是否写回仓库

# 5. 导出环境清单
ssh sjytt@192.168.55.1 'dpkg --get-selections > /tmp/apt.txt; pip3 freeze > /tmp/pip.txt'
```
