#!/bin/bash
# 内存守卫：可用内存过低时先重启 SLAM，仍不足则直接结束其进程，防止整机卡死而失联。
# 以 root 运行，仅读取 /proc/meminfo，自身开销可忽略。阈值可用环境变量覆盖。
WARN_MB="${WARN_MB:-8192}"      # 低于此值连续 STRIKES 次，重启 SLAM 与栅格
CRIT_MB="${CRIT_MB:-3072}"      # 低于此值立即结束 SLAM 进程
STRIKES="${STRIKES:-3}"
INTERVAL="${INTERVAL:-2}"       # 检查间隔，秒
COOLDOWN="${COOLDOWN:-90}"      # 两次重启的最小间隔，秒
UNITS="${UNITS:-jiaoda-fastlivo jiaoda-grid}"
PATTERN="${PATTERN:-fastlivo_mapping}"

strikes=0
last_restart=0

log() { echo "[memguard] $*"; }

while :; do
  avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  avail_mb=$(( ${avail_kb:-0} / 1024 ))
  now=$(date +%s)
  if [ "$avail_mb" -lt "$CRIT_MB" ]; then
    log "可用内存 ${avail_mb} MB 低于 ${CRIT_MB} MB，结束 ${PATTERN}"
    pkill -9 -f "$PATTERN"
    strikes=0
  elif [ "$avail_mb" -lt "$WARN_MB" ]; then
    strikes=$(( strikes + 1 ))
    if [ "$strikes" -ge "$STRIKES" ] && [ $(( now - last_restart )) -ge "$COOLDOWN" ]; then
      log "可用内存 ${avail_mb} MB 低于 ${WARN_MB} MB 连续 ${strikes} 次，重启 ${UNITS}"
      # shellcheck disable=SC2086
      systemctl restart $UNITS
      last_restart=$now
      strikes=0
    fi
  else
    strikes=0
  fi
  sleep "$INTERVAL"
done
