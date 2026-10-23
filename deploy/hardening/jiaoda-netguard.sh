#!/bin/bash
# 网络守卫：Jetson 自检外网与 Tailscale，持续失效时逐级自愈，避免热点抖动后一直失联。
# 以 root 运行。动作按失效持续时间逐级升级，默认不重启整机（REBOOT_AFTER=0）。
# 只判断“本机能否联网”；对端（手机热点关闭、Windows 端离线）无法由本脚本恢复。
INTERVAL="${INTERVAL:-30}"            # 检查间隔，秒
IFACE="${IFACE:-wlan0}"
PROBES="${PROBES:-223.5.5.5 114.114.114.114}"   # 外网探测地址，任一可达即视为联网
T_TAILSCALED="${T_TAILSCALED:-120}"   # 已联网但 Tailscale 未运行达此秒数，重启 tailscaled
T_WIFI="${T_WIFI:-120}"               # 断网达此秒数，重连 Wi-Fi
T_RADIO="${T_RADIO:-300}"             # 断网达此秒数，关开无线电
T_NM="${T_NM:-600}"                   # 断网达此秒数，重启 NetworkManager
REBOOT_AFTER="${REBOOT_AFTER:-0}"     # 断网达此秒数则重启整机；0 表示不启用
DRY_RUN="${DRY_RUN:-0}"               # 1：只记录不执行动作
ONCE="${ONCE:-0}"                     # 1：只检查一轮后退出，用于测试

log() { echo "[netguard] $*"; }
act() { log "动作: $*"; [ "$DRY_RUN" = 1 ] || "$@" >/dev/null 2>&1; }

net_ok() {
  local p
  for p in $PROBES; do
    ping -c 1 -W 3 -I "$IFACE" "$p" >/dev/null 2>&1 && return 0
  done
  return 1
}

ts_ok() {
  command -v tailscale >/dev/null 2>&1 || return 0
  tailscale status --json 2>/dev/null | grep -q '"BackendState": "Running"'
}

net_down_since=0
ts_down_since=0
did_wifi=0; did_radio=0; did_nm=0

while :; do
  now=$(date +%s)
  if net_ok; then
    [ "$net_down_since" -ne 0 ] && log "网络已恢复"
    net_down_since=0; did_wifi=0; did_radio=0; did_nm=0
    if ts_ok; then
      [ "$ts_down_since" -ne 0 ] && log "Tailscale 已恢复"
      ts_down_since=0
    else
      [ "$ts_down_since" -eq 0 ] && ts_down_since=$now && log "Tailscale 未运行"
      if [ $(( now - ts_down_since )) -ge "$T_TAILSCALED" ]; then
        act systemctl restart tailscaled
        ts_down_since=$now
      fi
    fi
  else
    [ "$net_down_since" -eq 0 ] && net_down_since=$now && log "外网不可达"
    d=$(( now - net_down_since ))
    if [ "$d" -ge "$T_WIFI" ] && [ "$did_wifi" -eq 0 ]; then act nmcli device connect "$IFACE"; did_wifi=1; fi
    if [ "$d" -ge "$T_RADIO" ] && [ "$did_radio" -eq 0 ]; then
      act nmcli radio wifi off; [ "$DRY_RUN" = 1 ] || sleep 3; act nmcli radio wifi on; did_radio=1
    fi
    if [ "$d" -ge "$T_NM" ] && [ "$did_nm" -eq 0 ]; then act systemctl restart NetworkManager; did_nm=1; fi
    if [ "$REBOOT_AFTER" -gt 0 ] && [ "$d" -ge "$REBOOT_AFTER" ]; then act systemctl reboot; fi
  fi
  [ "$ONCE" = 1 ] && exit 0
  sleep "$INTERVAL"
done
