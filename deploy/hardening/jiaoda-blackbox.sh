#!/bin/bash
# 黑匣子：每秒记录一行系统状态并落盘，异常停机后查看日志末尾即可知道停机前几秒的负载、I/O 压力与正在运行的进程。
# 以 root 运行，开销很小（每秒一次读取 /proc 与一次 ps）。日志文件超过 20 MB 时轮转为 .1。
LOG="${LOG:-/home/sjytt/blackbox.log}"
MAX_BYTES="${MAX_BYTES:-20971520}"
DISK="${DISK:-mmcblk0}"

prev_r=""; prev_w=""; i=0
while :; do
  ts=$(date +%H:%M:%S)
  read -r l1 _ _ run _ < /proc/loadavg
  avail=$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
  temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
  read -r r w < <(awk '{print $3, $7}' "/sys/block/$DISK/stat" 2>/dev/null)
  if [ -n "$prev_r" ]; then rd=$(( (r - prev_r) / 2 )); wr=$(( (w - prev_w) / 2 )); else rd=0; wr=0; fi
  prev_r=$r; prev_w=$w
  ioP=$(awk '/^some/ {split($2, a, "="); print a[2]}' /proc/pressure/io 2>/dev/null)
  cpuP=$(awk '/^some/ {split($2, a, "="); print a[2]}' /proc/pressure/cpu 2>/dev/null)
  top=$(ps -eo pcpu,args --sort=-pcpu 2>/dev/null | awk 'NR>1 && NR<=4 {c=$1; $1=""; printf "%s%%:%s | ", c, substr($0, 2, 70)}')
  ses=$(who | wc -l)
  echo "$ts load=$l1 run=$run avail=${avail}M temp=$temp rd=${rd}K/s wr=${wr}K/s ioP=$ioP cpuP=$cpuP ses=$ses top=[$top]" >> "$LOG"
  i=$(( i + 1 ))
  if [ $(( i % 2 )) -eq 0 ]; then
    sync "$LOG" 2>/dev/null
    if [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt "$MAX_BYTES" ]; then mv -f "$LOG" "$LOG.1"; fi
  fi
  sleep 1
done
