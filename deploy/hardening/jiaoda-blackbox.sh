#!/bin/bash
# 黑匣子：每秒记录一行系统状态并落盘，异常停机后查看日志末尾即可知道停机前几秒的状态。
# 以 root 运行，开销很小。日志文件超过 20 MB 时轮转为 .1。
# 字段：load 负载；run 可运行进程；avail 可用内存；temp CPU 温度（毫摄氏度）；rd/wr 磁盘读写；
#       ioP/cpuP 压力指标（avg10）；D 处于不可中断等待（多为等磁盘）的进程数；xhci USB 主控每秒中断数；
#       kmsg 内核日志最后一条；ses 登录会话数；top 占 CPU 最高的三个进程。
LOG="${LOG:-/home/sjytt/blackbox.log}"
MAX_BYTES="${MAX_BYTES:-20971520}"
DISK="${DISK:-mmcblk0}"

xhci_irq() { grep -i xhci /proc/interrupts | awk '{for (i = 2; i <= NF; i++) if ($i ~ /^[0-9]+$/) s += $i} END {print s + 0}'; }

prev_r=""; prev_w=""; prev_x=""; i=0
while :; do
  ts=$(date +%H:%M:%S)
  read -r l1 _ _ run _ < /proc/loadavg
  avail=$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
  temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
  read -r r w < <(awk '{print $3, $7}' "/sys/block/$DISK/stat" 2>/dev/null)
  if [ -n "$prev_r" ]; then rd=$(( (r - prev_r) / 2 )); wr=$(( (w - prev_w) / 2 )); else rd=0; wr=0; fi
  prev_r=$r; prev_w=$w
  x=$(xhci_irq)
  if [ -n "$prev_x" ]; then xr=$(( x - prev_x )); else xr=0; fi
  prev_x=$x
  ioP=$(awk '/^some/ {split($2, a, "="); print a[2]}' /proc/pressure/io 2>/dev/null)
  cpuP=$(awk '/^some/ {split($2, a, "="); print a[2]}' /proc/pressure/cpu 2>/dev/null)
  dstate=$(ps -eo stat 2>/dev/null | grep -c '^D')
  kmsg=$(dmesg 2>/dev/null | tail -n 1 | cut -c1-90)
  top=$(ps -eo pcpu,args --sort=-pcpu 2>/dev/null | awk 'NR>1 && NR<=4 {c=$1; $1=""; printf "%s%%:%s | ", c, substr($0, 2, 60)}')
  ses=$(who | wc -l)
  echo "$ts load=$l1 run=$run avail=${avail}M temp=$temp rd=${rd}K/s wr=${wr}K/s ioP=$ioP cpuP=$cpuP D=$dstate xhci=${xr}/s ses=$ses kmsg=[$kmsg] top=[$top]" >> "$LOG"
  i=$(( i + 1 ))
  if [ $(( i % 2 )) -eq 0 ]; then
    sync "$LOG" 2>/dev/null
    if [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt "$MAX_BYTES" ]; then mv -f "$LOG" "$LOG.1"; fi
  fi
  sleep 1
done
