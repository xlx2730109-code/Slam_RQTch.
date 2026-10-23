#!/bin/bash
# 只读：xHCI 报错的起始时间与速率变化、USB 拓扑、谁在占用相机。不打开任何相机设备。
echo "=== now"; date; uptime; cat /proc/uptime
echo "=== xHCI 报错首次出现与每 60 秒计数"
dmesg 2>/dev/null | grep -n -m1 "Set TR Deq Ptr\|unknown event type\|no TDs queued" | cut -c1-140
dmesg 2>/dev/null | grep -E "xhci" | awk '{ t=$1; gsub(/[\[\]]/, "", t); b=int(t/60); c[b]++ } END { for (k in c) print k*60 "s", c[k] }' | sort -n | head -20
echo "=== 报错之前的 USB 事件(前 25 条 usb/uvc/hub)"
dmesg 2>/dev/null | grep -i -E "usb |uvcvideo|hub " | head -25 | cut -c1-170
echo "=== lsusb -t"
lsusb -t 2>&1 | head -30
echo "=== 谁占用相机设备(fuser 仅查询，不打开设备)"
for d in /dev/video*; do echo "$d: $(fuser $d 2>&1 | tr -s ' ')"; done 2>/dev/null | head -12
echo "=== by-path"
ls -l /dev/v4l/by-path/ 2>&1 | awk '{print $9, $10, $11}' | head -12
echo "=== USB 自动挂起/电源管理"
cat /sys/module/usbcore/parameters/autosuspend 2>&1
grep -r . /sys/bus/usb/devices/1-4*/power/control 2>/dev/null | head -8
cat /proc/cmdline | tr ' ' '\n' | grep -i -E "usb|xhci|autosuspend"
echo "=== 控制台相机线程是否在占用(进程 fd)"
pid=$(pgrep -f console_backend.py | head -1); [ -n "$pid" ] && ls -l /proc/$pid/fd 2>/dev/null | grep -i video
pid=$(pgrep -f cam_publisher.py | head -1); [ -n "$pid" ] && ls -l /proc/$pid/fd 2>/dev/null | grep -i video
