#!/bin/bash
# 确保 wlan0 拿到地址；没有就重连 xlx。开机 30 s 后跑一次，之后每 2 分钟巡检。
has_ip() { ip -4 addr show wlan0 2>/dev/null | grep -q "inet "; }
[ "$(nmcli -t -f DEVICE,STATE device status | grep '^wlan0:' | cut -d: -f2)" = "connected" ] || true
if has_ip; then exit 0; fi
for i in 1 2 3; do
  nmcli con up xlx >/dev/null 2>&1
  sleep 4
  has_ip && exit 0
done
logger -t netwatch "wlan0 still has no IP after 3 retries"
exit 0
