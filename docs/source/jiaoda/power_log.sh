#!/bin/bash
# 记录 19V 输入轨电压，用于定位断电瞬间
LOG=/home/sjytt/power.log
[ -f "$LOG" ] || echo "# ts  V19  V5" > "$LOG"
i=0
while true; do
  ts=$(date +%H:%M:%S.%3N)
  v1=$(cat /sys/class/hwmon/hwmon3/in1_input 2>/dev/null)
  v3=$(cat /sys/class/hwmon/hwmon3/in3_input 2>/dev/null)
  echo "$ts $v1 $v3" >> "$LOG"
  i=$((i+1)); [ $((i % 10)) -eq 0 ] && sync
  sleep 0.2
done
