#!/bin/bash
# sshd 自愈：本地探测 banner，连续 3 次失败就重启 ssh
FAIL=0
while true; do
  sleep 20
  OUT=$(timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/22; head -c 4 <&3' 2>/dev/null)
  if [ "$OUT" = "SSH-" ]; then
    FAIL=0
  else
    FAIL=$((FAIL+1))
    logger -t sshguard "health check failed ${FAIL}: '${OUT}'"
    if [ "$FAIL" -ge 3 ]; then
      logger -t sshguard "restarting ssh"
      systemctl restart ssh
      sleep 5
      FAIL=0
    fi
  fi
done
