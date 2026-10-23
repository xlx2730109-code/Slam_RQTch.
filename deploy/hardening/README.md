# 防失联加固
目标：SLAM 发散或内存暴涨时，Jetson 仍可通过 SSH 与 Tailscale 访问，并能自动恢复。

| 文件 | 作用 |
| --- | --- |
| `harden.sh` | 应用或查看加固，可重复执行 |
| `rollback.sh` | 删除 `harden.sh` 写入的全部配置 |
| `jiaoda-memguard.sh`、`jiaoda-memguard.service` | 内存守卫，由 `harden.sh` 安装 |

## 依据

| 事实 | 来源 | 状态 |
| --- | --- | --- |
| 掉线发生在 SLAM 发散期间，提交说明写明发散会占满 CPU 并导致 SSH 连不上 | 提交 `add0f7e` | 用户记录 |
| 发散期间内存已用 31 GiB，上次健康审计为 14 GiB | 2026-10-23 22:01 的 `free -m` 与 `audit-runtime.md` | 实测 |
| 掉线时 `tailscale ping` 有回复而 TCP 22 超时 | 2026-10-23 22:30 起多次尝试 | 实测，说明网络层存在、处理 SSH 的进程被拖慢 |
| FAST-LIVO2 以 `-ffast-math` 编译，NaN 不会触发常规判断 | `docs/source/FAST-LIVO2/CMakeLists.txt` 第 24 行 | 源码 |
| 现有 `slam_guard.py` 仅在位置超过 500 m 连续 5 次时重启，重启使坐标原点与 2D 地图重置 | `docs/source/jiaoda/slam_guard.py` | 源码 |
| 交换为 zram 时，内存暴涨会因压缩占满 CPU | 推测，未核对 `swapon --show` | 推测 |

## 措施

| 措施 | 防的问题 |
| --- | --- |
| `jiaoda-fastlivo` 内存上限 12G、CPU 上限 400%、Nice 5、优先被内存不足处理选中 | SLAM 吃光内存和 CPU |
| `sshd`、`tailscaled` 的 `OOMScoreAdjust` 为 -1000、-900，CPU 份额调高 | 登录入口被结束或饿死 |
| `jiaoda-memguard`：可用内存低于 8 GiB 连续 3 次重启 SLAM，低于 3 GiB 立即结束 | 上限未生效或交换拖慢时的兜底 |
| `vm.swappiness=10`、`kernel.panic=15`、保留应急内存 | 抖动与内核崩溃后无法恢复 |
| 关闭 Wi-Fi 省电 | 热点链路间歇掉包 |
| 限制 `jiaoda-fastlivo` 的日志速率 | 每帧约 40 行输出占用 journald 与存储 |

## 使用

在 Jetson 上以 root 运行：

```bash
sudo bash harden.sh apply
```

查看当前限制：

```bash
sudo bash harden.sh status
```

回滚：

```bash
sudo bash rollback.sh
```

## 未纳入，待决定

| 项 | 说明 |
| --- | --- |
| 硬件看门狗 `RuntimeWatchdogSec` | 系统完全卡死时自动重启，可保证重新上线；会在卡死时中断任务，需确认 `/dev/watchdog` 与驱动后启用 |
| 根因修复 | 本目录只限制后果。发散本身需修复点内时间单位并回放验证，见 `docs/better-design.md` |
