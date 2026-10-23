#!/bin/bash
# 只读：存储健康、文件系统错误记录、内核存储报错、日志体积、近 5 秒日志来源、桌面索引服务。
echo "=== now"; date; uptime
echo "=== root fs"
findmnt -no SOURCE,FSTYPE,OPTIONS / 2>&1
echo "=== tune2fs 错误相关字段"
tune2fs -l /dev/mmcblk0p1 2>&1 | grep -i -E "state|error|mount count|last mounted|last checked|features|Lifetime" | head -14
echo "=== 当前开机 dmesg 存储/I-O 报错"
dmesg -T 2>&1 | grep -i -E "mmc[0-9]|mmcblk|blk_update|I/O error|EXT4-fs|Buffer I/O|hung task|timeout|reset" | tail -15
echo "=== I/O 调度与队列"
cat /sys/block/mmcblk0/queue/scheduler 2>&1
echo "=== journal 目录(只看大小，不读内容)"
ls -la /var/log/journal/*/ 2>&1 | head -12
journalctl --disk-usage 2>&1
echo "=== 近 5 秒 journal 来源计数"
journalctl --since "-5s" --no-pager -o json 2>/dev/null | python3 -c '
import sys, json, collections
c = collections.Counter()
for l in sys.stdin:
    try:
        d = json.loads(l)
    except Exception:
        continue
    c[d.get("_SYSTEMD_UNIT") or d.get("SYSLOG_IDENTIFIER") or "?"] += 1
for k, v in c.most_common(8):
    print(v, k)
'
echo "=== 桌面索引服务 tracker"
ps -eo pid,pcpu,rss,etimes,args | grep -i "[t]racker" | cut -c1-120
ls /usr/lib/systemd/user/ 2>/dev/null | grep -i tracker | head -10
ls /etc/xdg/autostart/ 2>/dev/null | grep -i tracker | head
echo "=== 体积(仅少数目录)"
for d in /home/sjytt/.cache/tracker /home/sjytt/.local/share/tracker /home/sjytt/.ros/log /home/sjytt/backup; do
  [ -e "$d" ] && echo "$(du -sh "$d" 2>/dev/null | cut -f1)  $d"
done
df -h / | tail -1
