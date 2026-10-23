#!/bin/bash
# 回滚 harden.sh 写入的全部配置。用法（Jetson 上，root）：sudo bash rollback.sh
set -u
for u in jiaoda-fastlivo jiaoda-grid jiaoda-nav ssh tailscaled; do
  rm -f "/etc/systemd/system/$u.service.d/90-hardening.conf"
  rmdir "/etc/systemd/system/$u.service.d" 2>/dev/null
done
systemctl disable --now jiaoda-usbpower.service >/dev/null 2>&1
rm -f /etc/systemd/system/jiaoda-usbpower.service
rm -f /etc/systemd/system/jiaoda-campub.service.d/90-hardening.conf
rmdir /etc/systemd/system/jiaoda-campub.service.d 2>/dev/null
systemctl --global unmask tracker-store.service tracker-miner-fs.service tracker-extract.service tracker-writeback.service >/dev/null 2>&1
bak=/home/sjytt/backup/console_backend.py.orig-20261023
[ -f "$bak" ] && install -m 0755 -o sjytt -g sjytt "$bak" /home/sjytt/jiaoda/console_backend.py && systemctl restart jiaoda-console
systemctl disable --now jiaoda-memguard.service jiaoda-netguard.service jiaoda-blackbox.service >/dev/null 2>&1
rm -f /etc/systemd/system/jiaoda-blackbox.service /usr/local/sbin/jiaoda-blackbox.sh
rm -f /etc/systemd/system/user-1000.slice.d/90-hardening.conf
rmdir /etc/systemd/system/user-1000.slice.d 2>/dev/null
rm -f /etc/systemd/system/jiaoda-memguard.service /usr/local/sbin/jiaoda-memguard.sh
rm -f /etc/systemd/system/jiaoda-netguard.service /usr/local/sbin/jiaoda-netguard.sh
rm -f /etc/sysctl.d/90-jiaoda-hardening.conf /etc/NetworkManager/conf.d/99-jiaoda-wifi-powersave.conf
systemctl daemon-reload
echo "已回滚。sysctl 取值需重启后恢复默认；服务限制已移除，重启对应服务后 Nice 恢复。"
