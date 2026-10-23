#!/bin/bash
check() { timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1; head -c 4 <&3" 2>/dev/null | grep -q '^SSH-'; }
logstate() { echo "$(date +%H:%M:%S) pids=$(ps -e --no-headers | wc -l) load=$(cut -d' ' -f1 /proc/loadavg) audit=$(systemctl is-active auditd 2>/dev/null) disk=$(df -h / | awk 'NR==2{print $5}')" >> /home/sjytt/state.log; }
i=0
while true; do
  sleep 20
  i=$((i+1))
  if ! check 22; then logger -t sshguard "port22 fail"; logstate; systemctl restart ssh; sleep 3; fi
  if ! check 2222; then logger -t sshguard "port2222 fail"; logstate; systemctl restart sshd-2222; sleep 3; fi
  [ $((i % 15)) -eq 0 ] && logstate
done
