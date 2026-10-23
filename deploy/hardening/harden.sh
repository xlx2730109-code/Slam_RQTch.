#!/bin/bash
# 防失联加固：限制 SLAM 相关进程的内存与 CPU，保护 sshd 与 tailscaled，安装内存守卫。
# 用法（Jetson 上，root）：
#   sudo bash harden.sh apply [--no-restart]   应用；默认重启 jiaoda-fastlivo 与 jiaoda-grid 使 Nice 生效
#   sudo bash harden.sh status                 查看当前生效的限制
# 回滚：sudo bash rollback.sh
# 本脚本可重复执行，只写入 /etc/systemd/system/*.d/、/etc/sysctl.d/、/etc/NetworkManager/conf.d/ 与 /usr/local/sbin/。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEM_LIMIT="${MEM_LIMIT:-12G}"        # jiaoda-fastlivo 内存上限；整机 61 GiB，正常运行远低于此值
CPU_QUOTA="${CPU_QUOTA:-400%}"       # jiaoda-fastlivo CPU 上限，8 核中为 sshd 等保留至少 4 核
ACTION="${1:-status}"
RESTART=1
[ "${2:-}" = "--no-restart" ] && RESTART=0

if [ "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)" = "cgroup2fs" ]; then CG=2; else CG=1; fi

dropin() {  # dropin <unit> <name>，配置从标准输入读取
  local dir="/etc/systemd/system/$1.d"
  mkdir -p "$dir"
  cat > "$dir/$2.conf"
}

patch_console() {
  local dst=/home/sjytt/jiaoda/console_backend.py bak=/home/sjytt/backup/console_backend.py.orig-20261023
  [ -f "$HERE/patches/console_backend.py" ] || return 0
  cmp -s "$HERE/patches/console_backend.py" "$dst" && return 0
  mkdir -p /home/sjytt/backup
  [ -f "$bak" ] || cp -p "$dst" "$bak"
  install -m 0755 -o sjytt -g sjytt "$HERE/patches/console_backend.py" "$dst"
  chown sjytt:sjytt "$bak" 2>/dev/null
  systemctl restart jiaoda-console 2>/dev/null
}

status() {
  echo "cgroup 版本: v$CG"
  echo "systemd: $(systemctl --version | head -1)"
  for u in jiaoda-fastlivo jiaoda-grid jiaoda-nav ssh tailscaled; do
    echo "--- $u"
    systemctl show "$u" -p Nice -p OOMScoreAdjust -p CPUQuotaPerSecUSec -p MemoryLimit -p MemoryMax -p CPUShares -p CPUWeight 2>/dev/null
  done
  echo "--- 运行中进程 oom_score_adj"
  for p in sshd tailscaled; do
    pid="$(pgrep -o -x "$p")"
    [ -n "$pid" ] && echo "$p($pid)=$(cat /proc/$pid/oom_score_adj)"
  done
  echo "--- sysctl"
  sysctl vm.swappiness vm.min_free_kbytes kernel.panic 2>/dev/null
  echo "--- jiaoda-memguard: $(systemctl is-active jiaoda-memguard 2>/dev/null)"
  echo "--- jiaoda-netguard: $(systemctl is-active jiaoda-netguard 2>/dev/null)"
  echo "--- jiaoda-blackbox: $(systemctl is-active jiaoda-blackbox 2>/dev/null)"
  echo "--- jiaoda-usbpower: $(systemctl is-active jiaoda-usbpower 2>/dev/null) autosuspend=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null)"
  echo "--- tracker 进程数: $(pgrep -fc /usr/libexec/tracker)"
  echo "--- 内核控制台级别: $(cat /proc/sys/kernel/printk)"
  cmp -s "$HERE/patches/console_backend.py" /home/sjytt/jiaoda/console_backend.py && echo "--- console_backend: 已是补丁版" || echo "--- console_backend: 基线版"
  systemctl show user-1000.slice -p CPUQuotaPerSecUSec -p MemoryLimit -p MemoryMax 2>/dev/null
  sw=/sys/fs/cgroup/memory/system.slice/jiaoda-fastlivo.service/memory.swappiness
  [ -r "$sw" ] && echo "fastlivo cgroup swappiness=$(cat $sw)"
  swapon --show 2>/dev/null
}

apply() {
  # 1. SLAM：限制内存与 CPU，降低优先级，优先被内存不足处理选中；限制日志速率以减轻 journald 负担
  if [ "$CG" = 2 ]; then
    MEM_LINE="MemoryMax=$MEM_LIMIT
MemorySwapMax=0
CPUWeight=50"
    SSH_LINE="CPUWeight=1000"
    SWAP_LINE=""
  else
    MEM_LINE="MemoryLimit=$MEM_LIMIT
CPUShares=256"
    SSH_LINE="CPUShares=2048"
    # v1 无法用 systemd 限制交换，改为启动后把该 cgroup 的 swappiness 置 0。
    # 服务以普通用户运行，必须加 + 前缀以 root 权限执行，否则写入被拒绝且错误被忽略。
    SWAP_LINE="ExecStartPost=-+/bin/sh -c 'echo 0 > /sys/fs/cgroup/memory/system.slice/jiaoda-fastlivo.service/memory.swappiness'"
  fi

  # StandardOutput=null：丢弃 FAST-LIVO2 每帧约 40 行的统计输出（约 250 行/秒，占用 journald 与存储）；
  # 警告和错误走标准错误，仍写入 journal。排查时用 rosbag，或手动前台运行查看完整输出。
  dropin jiaoda-fastlivo.service 90-hardening <<EOF
[Service]
Nice=5
OOMScoreAdjust=700
CPUQuota=$CPU_QUOTA
$MEM_LINE
StandardOutput=null
$SWAP_LINE
EOF

  # 2. 栅格与导航：降低优先级并限制 CPU
  for u in jiaoda-grid jiaoda-nav; do
    dropin "$u.service" 90-hardening <<EOF
[Service]
Nice=10
OOMScoreAdjust=600
CPUQuota=150%
EOF
  done

  # 3. sshd 与 tailscaled：不被内存不足处理选中，CPU 份额优先
  dropin ssh.service 90-hardening <<EOF
[Service]
OOMScoreAdjust=-1000
$SSH_LINE
EOF
  dropin tailscaled.service 90-hardening <<EOF
[Service]
OOMScoreAdjust=-900
$SSH_LINE
EOF

  # 3b. 相机发布降为 5 Hz：当前 SLAM 未启用视觉（img_en=0），图像仅供任务拍照；启用视觉时需恢复 15 Hz
  dropin jiaoda-campub.service 90-hardening <<EOF
[Service]
Environment=CAMPUB_FPS=5
EOF

  # 4. 内核参数：少用交换（交换为 zram 时会占用 CPU 压缩），保留应急内存，内核崩溃后自动重启；
  #    kernel.printk 把控制台级别降到 1，避免 USB 主控报错刷屏时同步写入慢速串口控制台而卡住 CPU
  cat > /etc/sysctl.d/90-jiaoda-hardening.conf <<EOF
vm.swappiness = 10
kernel.panic = 15
kernel.printk = 1 4 1 7
EOF
  dmesg -n 1
  cur="$(sysctl -n vm.min_free_kbytes 2>/dev/null || echo 0)"
  if [ "${cur:-0}" -lt 262144 ]; then echo "vm.min_free_kbytes = 262144" >> /etc/sysctl.d/90-jiaoda-hardening.conf; fi
  sysctl --system >/dev/null 2>&1

  # 5. Wi-Fi 省电关闭（热点链路常因省电丢包）；仅写配置，下次重连生效，不在此刻重载网络
  mkdir -p /etc/NetworkManager/conf.d
  printf '[connection]\nwifi.powersave = 2\n' > /etc/NetworkManager/conf.d/99-jiaoda-wifi-powersave.conf
  command -v iw >/dev/null 2>&1 && iw dev wlan0 set power_save off 2>/dev/null

  # 6. 内存守卫与网络守卫
  install -m 0755 "$HERE/jiaoda-memguard.sh" /usr/local/sbin/jiaoda-memguard.sh
  install -m 0644 "$HERE/jiaoda-memguard.service" /etc/systemd/system/jiaoda-memguard.service
  install -m 0755 "$HERE/jiaoda-netguard.sh" /usr/local/sbin/jiaoda-netguard.sh
  install -m 0644 "$HERE/jiaoda-netguard.service" /etc/systemd/system/jiaoda-netguard.service
  install -m 0755 "$HERE/jiaoda-blackbox.sh" /usr/local/sbin/jiaoda-blackbox.sh
  install -m 0644 "$HERE/jiaoda-blackbox.service" /etc/systemd/system/jiaoda-blackbox.service
  install -m 0644 "$HERE/jiaoda-usbpower.service" /etc/systemd/system/jiaoda-usbpower.service

  # 桌面文件索引服务（tracker）对机器人无用，却持续写盘约 2.8 MB/s 并占 CPU，停用并结束进程
  systemctl --global mask tracker-store.service tracker-miner-fs.service tracker-extract.service tracker-writeback.service >/dev/null 2>&1
  pkill -f /usr/libexec/tracker 2>/dev/null

  # 控制台摄像头改为按需打开（基线版本常驻读取相机，占用共享的 USB 2.0 带宽）
  patch_console

  # 远程登录会话（含各类自动化工具）的资源上限，防止一条重命令拖垮整机；SLAM 服务不在此 slice，不受影响
  mkdir -p /etc/systemd/system/user-1000.slice.d
  if [ "$CG" = 2 ]; then
    printf '[Slice]\nCPUQuota=300%%\nMemoryMax=16G\n' > /etc/systemd/system/user-1000.slice.d/90-hardening.conf
  else
    printf '[Slice]\nCPUQuota=300%%\nMemoryLimit=16G\n' > /etc/systemd/system/user-1000.slice.d/90-hardening.conf
  fi

  systemctl daemon-reload
  systemctl enable jiaoda-memguard.service jiaoda-netguard.service jiaoda-blackbox.service jiaoda-usbpower.service >/dev/null 2>&1
  systemctl restart jiaoda-memguard.service jiaoda-netguard.service jiaoda-blackbox.service jiaoda-usbpower.service

  # 对已运行的 SLAM 立即把交换倾向置 0（cgroup v1）
  sw=/sys/fs/cgroup/memory/system.slice/jiaoda-fastlivo.service/memory.swappiness
  [ "$CG" = 1 ] && [ -w "$sw" ] && echo 0 > "$sw"

  # 7. 对已运行的 sshd 与 tailscaled 立即生效，无需重启服务（保持当前连接）
  for p in sshd tailscaled; do
    pid="$(pgrep -o -x "$p")"
    if [ -n "$pid" ]; then
      [ "$p" = sshd ] && echo -1000 > /proc/$pid/oom_score_adj || echo -900 > /proc/$pid/oom_score_adj
    fi
  done

  if [ "$RESTART" = 1 ]; then
    systemctl restart jiaoda-fastlivo jiaoda-grid
  fi
  echo "已应用。"
  status
}

case "$ACTION" in
  apply) apply ;;
  status) status ;;
  *) echo "用法: $0 apply [--no-restart] | status"; exit 2 ;;
esac
