#!/bin/bash
# 原机信息一次性采集（只读）。在 Jetson 上以 root 运行：sudo bash jetson_capture.sh
# 输出目录：/home/sjytt/capture_<日期>/，完成后生成 DONE 文件。
# 约束：不读取 systemd 日志；不打开相机或串口设备；不包含 Wi-Fi 密码、SSH 密钥、Tailscale 节点密钥、命令历史。
# 每条命令设 20 秒超时，单条失败不影响后续。
OUT="${OUT:-/home/sjytt/capture_$(date +%Y%m%d)}"
H=/home/sjytt
mkdir -p "$OUT/cmd" "$OUT/etc" "$OUT/home" "$OUT/src-state"
rm -f "$OUT/DONE"
echo "start $(date -Is)" > "$OUT/PROGRESS"

run() {  # run <名称> <命令...>：把命令及其输出写入 cmd/<名称>.txt
  local name="$1"; shift
  { echo "\$ $*"; timeout 20 "$@" 2>&1; echo "[exit=$?]"; } > "$OUT/cmd/$name.txt"
}
sh_() {  # sh_ <名称> <shell 命令串>
  local name="$1"; shift
  { echo "\$ $*"; timeout 20 bash -c "$*" 2>&1; echo "[exit=$?]"; } > "$OUT/cmd/$name.txt"
}
cp_() {  # cp_ <源路径...>：复制小文件到 etc/，保留相对路径
  local f
  for f in "$@"; do
    [ -f "$f" ] && [ "$(stat -c %s "$f")" -lt 400000 ] && install -D -m 0644 "$f" "$OUT/etc$f"
  done
}

echo "1 system" >> "$OUT/PROGRESS"
run uname uname -a
run os-release cat /etc/os-release
run nv_tegra_release cat /etc/nv_tegra_release
sh_ model "cat /proc/device-tree/model; echo; cat /proc/device-tree/chosen/ecid 2>/dev/null | head -c 0"
run lscpu lscpu
run meminfo head -n 6 /proc/meminfo
run lsblk lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
run df df -h
run mount findmnt -l
run swap swapon --show
run uptime uptime
run date date
run timedatectl timedatectl
run nvpmodel nvpmodel -q
run jetson_clocks jetson_clocks --show
sh_ cmdline "cat /proc/cmdline"
run sysctl-selected sysctl vm.swappiness vm.min_free_kbytes kernel.panic kernel.printk net.core.rmem_max net.core.rmem_default net.core.wmem_max
run lsmod lsmod
run cgroup stat -fc %T /sys/fs/cgroup
run systemd-version systemctl --version
run cron-root crontab -l
run cron-user sudo -u sjytt crontab -l
sh_ thermal "for z in /sys/class/thermal/thermal_zone*; do echo \"\$(cat \$z/type)=\$(cat \$z/temp)\"; done"
sh_ emmc "cat /sys/class/mmc_host/mmc0/mmc0:0001/life_time; cat /sys/block/mmcblk0/queue/scheduler"
sh_ tune2fs "tune2fs -l /dev/mmcblk0p1 | head -60"
sh_ hwmon-rails "for h in /sys/class/hwmon/hwmon*; do echo \"--- \$h name=\$(cat \$h/name)\"; for f in \$h/in*_label \$h/in*_input \$h/curr*_input \$h/shunt*; do [ -r \$f ] && echo \"\$(basename \$f)=\$(cat \$f)\"; done; done"
run watchdog-dev ls -l /dev/watchdog /dev/watchdog0

echo "2 devices" >> "$OUT/PROGRESS"
run lsusb lsusb
run lsusb-t lsusb -t
run lspci lspci
sh_ usb-devices "for d in /sys/bus/usb/devices/[0-9]*; do [ -r \$d/idVendor ] && echo \"\$(basename \$d) \$(cat \$d/idVendor):\$(cat \$d/idProduct) \$(cat \$d/product 2>/dev/null) [\$(cat \$d/manufacturer 2>/dev/null)] speed=\$(cat \$d/speed) power=\$(cat \$d/power/control 2>/dev/null)\"; done"
sh_ usb-autosuspend "cat /sys/module/usbcore/parameters/autosuspend"
run v4l-bypath ls -l /dev/v4l/by-path /dev/v4l/by-id
run serial-byid ls -l /dev/serial/by-id /dev/serial/by-path
sh_ video-udev "for v in /dev/video0 /dev/video2 /dev/video4; do echo \"--- \$v\"; udevadm info -q property -n \$v | grep -E 'ID_V4L_PRODUCT|ID_PATH=|ID_MODEL=|ID_VENDOR_ID|ID_MODEL_ID|ID_SERIAL'; done"
run ip-addr ip -d addr
run ip-route ip route
run ip-link-stats ip -s link
run ss-listen ss -ltnup
sh_ net-drivers "for n in eth0 eth1 wlan0; do echo \"\$n -> \$(readlink -f /sys/class/net/\$n/device 2>/dev/null | sed 's#.*/devices/##') driver=\$(basename \$(readlink -f /sys/class/net/\$n/device/driver 2>/dev/null))\"; done"
run nmcli-dev nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev
run nmcli-con nmcli -t -f NAME,TYPE,DEVICE,AUTOCONNECT con show
sh_ nmcli-xlx "nmcli con show xlx | grep -v -i -E 'psk|password|secret'"
sh_ nmcli-lidar-eth "nmcli con show lidar-eth | grep -v -i -E 'psk|password|secret'"
sh_ iw-link "iw dev wlan0 link; iw dev wlan0 get power_save"
run iptables iptables -S
run tailscale-version tailscale version
sh_ tailscale-status "tailscale status 2>&1 | sed -E 's/[a-zA-Z0-9._-]+@/<account>@/'"
run dmesg-boot-nonxhci bash -c "dmesg -T | grep -v -i xhci | head -n 500"
run dmesg-xhci-summary bash -c "dmesg | grep -i xhci | sed -E 's/^\[[^]]*\] //; s/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -8"

echo "3 etc" >> "$OUT/PROGRESS"
cp_ /etc/fstab /etc/hosts /etc/hostname /etc/environment /etc/default/locale
cp_ /etc/systemd/system.conf /etc/systemd/journald.conf /etc/systemd/timesyncd.conf /etc/systemd/logind.conf
cp_ /boot/extlinux/extlinux.conf /etc/nv_boot_control.conf /etc/nvpmodel.conf /var/lib/nvpmodel/status /etc/fake-hwclock.data
cp_ /etc/rc.local /etc/crontab /etc/ssh/sshd_config
for f in /etc/NetworkManager/conf.d/* /etc/modprobe.d/* /etc/sysctl.d/* /etc/udev/rules.d/* /etc/netplan/* /etc/ssh/sshd_config.d/* /etc/cron.d/* /etc/security/limits.d/* /etc/xdg/autostart/tracker*; do cp_ "$f"; done
for f in /etc/systemd/system/*.service /etc/systemd/system/*.timer /etc/systemd/system/*.d/*.conf /usr/local/sbin/jiaoda-*; do cp_ "$f"; done
sh_ units-enabled "systemctl list-unit-files --state=enabled --no-pager"
sh_ units-jiaoda "systemctl list-units 'jiaoda-*' --all --no-pager"
sh_ units-effective "for u in \$(systemctl list-unit-files 'jiaoda-*' --no-legend | awk '{print \$1}'); do echo \"##### \$u\"; systemctl cat \$u --no-pager; done"
sh_ units-props "for u in \$(systemctl list-units 'jiaoda-*' --no-legend --all | awk '{print \$1}' | grep service); do echo \"##### \$u\"; systemctl show \$u -p MainPID -p NRestarts -p Nice -p OOMScoreAdjust -p CPUQuotaPerSecUSec -p MemoryLimit -p Environment -p ExecStart --no-pager | cut -c1-300; done"
run timers systemctl list-timers --all --no-pager
sh_ sshd-2222 "systemctl cat sshd-2222.service --no-pager"

echo "4 home" >> "$OUT/PROGRESS"
sh_ home-listing "find $H -maxdepth 2 -not -path '$H/.cache/*' -not -path '$H/.local/*' -not -path '*/.git/*' -not -path '$H/.ros/*' -printf '%M %u %s %TY-%Tm-%Td %TH:%TM %p\n' | sort -k6 | head -n 1500"
for f in "$H"/*.sh "$H"/*.md "$H"/*.txt "$H"/*.log "$H"/*.py "$H"/*.yaml "$H"/.bashrc "$H"/.profile; do
  [ -f "$f" ] && [ "$(stat -c %s "$f")" -lt 300000 ] && install -D -m 0644 "$f" "$OUT/home/$(basename "$f")"
done
[ -d "$H/backup" ] && cp -a "$H/backup" "$OUT/home/backup"
sh_ jiaoda-photos "ls -la $H/jiaoda/photos 2>&1 | head -50; ls -la $H/jiaoda/maps $H/jiaoda/routes 2>&1"
sh_ ros-log-listing "ls -la $H/.ros/log/ | head -40; ls -la $H/.ros/log/latest/ 2>&1 | head -40"
mkdir -p "$OUT/home/ros-log-tails"
for f in "$H"/.ros/log/latest/*.log; do
  [ -f "$f" ] && case "$f" in */rosout.log|*/master.log) ;; *) tail -n 300 "$f" > "$OUT/home/ros-log-tails/$(basename "$f")";; esac
done
for f in "$H"/blackbox.log "$H"/power.log; do [ -f "$f" ] && cp "$f" "$OUT/home/$(basename "$f")"; done

echo "5 src-state" >> "$OUT/PROGRESS"
for d in livo2_ws/src/FAST-LIVO2 livo2_ws/src/rpg_vikit Sophus_src unilidar_sdk2 unilidar_sdk; do
  p="$H/$d"
  [ -d "$p/.git" ] || continue
  n=$(echo "$d" | tr '/' '_')
  { echo "## $d"; git -C "$p" log -1 --format='%H %ad %s' --date=iso; git -C "$p" remote -v; git -C "$p" status --short | head -50; } > "$OUT/src-state/$n.status.txt" 2>&1
  git -C "$p" diff > "$OUT/src-state/$n.local.patch" 2>/dev/null
  [ -s "$OUT/src-state/$n.local.patch" ] || rm -f "$OUT/src-state/$n.local.patch"
done
sh_ cmake-livo2 "grep -E '^(CMAKE_BUILD_TYPE|CMAKE_CXX_FLAGS|CMAKE_CXX_FLAGS_RELEASE|CMAKE_PREFIX_PATH|Sophus_DIR|CMAKE_INSTALL_PREFIX)' $H/livo2_ws/build/CMakeCache.txt"
sh_ cmake-unilidar "grep -E '^(CMAKE_BUILD_TYPE|CMAKE_CXX_FLAGS|CMAKE_PREFIX_PATH)' $H/unilidar_sdk2/unitree_lidar_ros/build/CMakeCache.txt"
sh_ ws-listing "ls -la $H/livo2_ws $H/livo2_ws/src $H/unilidar_sdk2 $H/unilidar_sdk2/unitree_lidar_ros 2>&1"
sh_ lidar-src-sha "cd $H/unilidar_sdk2/unitree_lidar_ros/src && find . -type f -not -path '*/.git/*' -exec sha256sum {} + | sort -k2"
sh_ binaries "sha256sum $H/livo2_ws/devel/lib/fast_livo/fastlivo_mapping $H/unilidar_sdk2/unitree_lidar_ros/devel/lib/unitree_lidar_ros/unitree_lidar_ros_node 2>&1; ls -la $H/livo2_ws/devel/lib/ $H/livo2_ws/devel/lib/fast_livo 2>&1 | head -30"
sh_ catkin-env "source /opt/ros/noetic/setup.bash; env | grep -E '^(ROS_|CMAKE_PREFIX_PATH|PYTHONPATH|LD_LIBRARY_PATH)'"
sh_ esp-tools "which arduino-cli platformio pio esptool.py esptool 2>&1; ls -d $H/.arduino15 $H/Arduino $H/.platformio 2>&1"
sh_ python-modules "python3 -c 'import sys,numpy,cv2,serial,yaml; print(sys.version); print(numpy.__version__, cv2.__version__, serial.VERSION, yaml.__version__)'"

echo "6 sizes" >> "$OUT/PROGRESS"
sh_ du-top "cd $H && for d in *; do [ -d \"\$d\" ] && echo \"\$(du -s --apparent-size \"\$d\" 2>/dev/null | cut -f1) KB  \$d\"; done | sort -rn | head -30"

chown -R sjytt:sjytt "$OUT"
echo "done $(date -Is)" >> "$OUT/PROGRESS"
echo "OK" > "$OUT/DONE"
