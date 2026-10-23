#!/bin/bash
# 回滚 harden.sh 写入的全部配置。用法（Jetson 上，root）：sudo bash rollback.sh
set -u
for u in jiaoda-fastlivo jiaoda-grid jiaoda-nav ssh tailscaled; do
  rm -f "/etc/systemd/system/$u.service.d/90-hardening.conf"
  rmdir "/etc/systemd/system/$u.service.d" 2>/dev/null
done
systemctl disable --now jiaoda-memguard.service jiaoda-netguard.service >/dev/null 2>&1
rm -f /etc/systemd/system/jiaoda-memguard.service /usr/local/sbin/jiaoda-memguard.sh
rm -f /etc/systemd/system/jiaoda-netguard.service /usr/local/sbin/jiaoda-netguard.sh
rm -f /etc/sysctl.d/90-jiaoda-hardening.conf /etc/NetworkManager/conf.d/99-jiaoda-wifi-powersave.conf
systemctl daemon-reload
echo "已回滚。sysctl 取值需重启后恢复默认；服务限制已移除，重启对应服务后 Nice 恢复。"
