#!/bin/bash
# 只读：列出 hwmon 传感器、电源轨电压/电流，以及 5 秒内各进程的磁盘写入速率。
echo "=== hwmon"
for h in /sys/class/hwmon/hwmon*; do
  echo "--- $h name=$(cat $h/name 2>/dev/null)"
  for f in $h/in*_label $h/in*_input $h/curr*_input $h/power*_input $h/curr*_label $h/shunt*; do
    [ -r "$f" ] && echo "$(basename $f)=$(cat $f 2>/dev/null)"
  done 2>/dev/null | head -24
done
echo "=== tegra power sysfs"
ls /sys/bus/i2c/drivers/ina3221 2>/dev/null | head -5
echo "=== 5s per-process disk writes"
snap() {
  for p in /proc/[0-9]*; do
    pid=${p#/proc/}
    w=$(awk '/^write_bytes/ {print $2}' "$p/io" 2>/dev/null)
    [ -n "$w" ] && echo "$pid $w"
  done | sort
}
snap > /tmp/io1.txt
sleep 5
snap > /tmp/io2.txt
join -j1 /tmp/io1.txt /tmp/io2.txt | awk '{d=$3-$2; if (d>0) print d, $1}' | sort -rn | head -6 | while read -r d pid; do
  echo "$((d / 5 / 1024)) KB/s pid=$pid $(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-110)"
done
rm -f /tmp/io1.txt /tmp/io2.txt
