#!/bin/bash
# 原机补充采集（只读）：硬件细节、未启用的软件、~/jiaoda 当前全部文件。
# 在 Jetson 上以 root 运行：sudo bash jetson_capture_hw.sh
# 输出目录：/home/sjytt/capture2_<日期>/，完成后生成 DONE。
# 约束：不读 systemd 日志；不打开串口；相机只做能力查询（不取流）；不含密钥与命令历史。
OUT="${OUT:-/home/sjytt/capture2_$(date +%Y%m%d)}"
H=/home/sjytt
mkdir -p "$OUT/cmd" "$OUT/jiaoda" "$OUT/other"
rm -f "$OUT/DONE"
echo "start $(date -Is)" > "$OUT/PROGRESS"

sh_() { local name="$1"; shift; { echo "\$ $*"; timeout 25 bash -c "$*" 2>&1; echo "[exit=$?]"; } > "$OUT/cmd/$name.txt"; }

echo "1 jiaoda" >> "$OUT/PROGRESS"
# ~/jiaoda 全部文件（排除照片、缓存、已在仓库中的标定原始数据），并给出哈希清单
( cd "$H/jiaoda" && find . -type f ! -path './photos/*' ! -path './__pycache__/*' ! -path './calib/data/*' ! -name '*.pyc' -exec sha256sum {} + | sort -k2 ) > "$OUT/jiaoda.sha256"
tar -C "$H/jiaoda" --exclude=./photos --exclude=./__pycache__ --exclude=./calib/data --exclude='*.pyc' -cf - . | tar -C "$OUT/jiaoda" -xf -
sh_ jiaoda-photos "ls -la $H/jiaoda/photos 2>&1 | head -40"
sh_ usr-local "ls -la /usr/local/bin /usr/local/sbin /opt 2>&1"
for f in /usr/local/bin/* /usr/local/sbin/*; do [ -f "$f" ] && [ "$(stat -c %s "$f")" -lt 200000 ] && install -D -m 0644 "$f" "$OUT/other$f"; done

echo "2 hardware" >> "$OUT/PROGRESS"
sh_ dev-nodes "ls -l /dev | head -n 400"
sh_ cpuinfo "cat /proc/cpuinfo | grep -E 'processor|model name|CPU part|CPU implementer' | sort | uniq -c | head"
sh_ meminfo-full "cat /proc/meminfo | head -n 20"
sh_ tegrastats "timeout 4 tegrastats --interval 1000 2>&1 | head -n 4"
sh_ i2c "i2cdetect -l 2>&1; ls /sys/bus/i2c/devices 2>&1 | head -40"
sh_ fan "cat /sys/devices/pwm-fan/cur_pwm /sys/devices/pwm-fan/target_pwm 2>&1; ls /sys/class/hwmon/*/pwm1 2>&1; systemctl is-active nvfancontrol"
sh_ drm "for c in /sys/class/drm/card*-*; do echo \"\$c: \$(cat \$c/status 2>/dev/null) \$(cat \$c/enabled 2>/dev/null)\"; done; ls /sys/class/drm"
sh_ gdm "cat /etc/gdm3/custom.conf 2>&1 | grep -v '^#' | grep -v '^$'; loginctl list-sessions --no-legend 2>&1"
sh_ rfkill "rfkill list 2>&1; lsmod | grep -E 'rtl|bt|cfg80211|brcm' | head"
sh_ cuda "ls /usr/local/ 2>&1; cat /usr/local/cuda/version.json 2>/dev/null | head -20; nvcc --version 2>&1 | tail -3; dpkg -l | grep -E 'nvidia-jetpack|nvidia-l4t-core|tensorrt|libcudnn|cuda-toolkit|vpi|opencv' | awk '{print \$2, \$3}' | head -40"
sh_ v4l2-list "v4l2-ctl --list-devices 2>&1 | head -40"
sh_ v4l2-formats "for d in /dev/video0 /dev/video4; do echo \"=== \$d\"; v4l2-ctl -d \$d --list-formats-ext 2>&1 | head -60; done"
sh_ v4l2-camera-ctrls "v4l2-ctl -d /dev/video4 --all 2>&1 | head -40"
sh_ lidar-ping "ping -c 3 -W 2 192.168.1.62 2>&1 | tail -4"
sh_ lidar-arp "ip neigh show dev eth1 2>&1 | sed -E 's/([0-9a-f]{2}:){5}[0-9a-f]{2}/xx:xx:xx:xx:xx:xx/'"
sh_ eth1-eth "ethtool eth1 2>&1 | head -20; ethtool -i eth1 2>&1"
sh_ udev-esp "udevadm info -q property -n /dev/ttyACM0 2>&1 | grep -E 'ID_VENDOR|ID_MODEL|ID_SERIAL|ID_PATH|ID_USB_DRIVER'; udevadm info -q property -n /dev/ttyACM1 2>&1 | grep -E 'ID_VENDOR|ID_MODEL|ID_SERIAL|ID_PATH|ID_USB_DRIVER'"
sh_ gpio "ls /sys/class/gpio 2>&1 | head; gpioinfo 2>&1 | head -5"
sh_ nvidia-power-tools "which nvpmodel jetson_clocks tegrastats i2cdetect v4l2-ctl ethtool iw gpioinfo 2>&1"

echo "3 software-not-in-main-stack" >> "$OUT/PROGRESS"
sh_ rslidar-ws "ls -la $H/rslidar_ws $H/rslidar_ws/src 2>&1 | head -30; find $H/rslidar_ws/src -maxdepth 2 -name package.xml 2>/dev/null | head"
sh_ unilidar-sdk-v1 "ls -la $H/unilidar_sdk 2>&1 | head -20; ls $H/unilidar_sdk/unitree_lidar_ros/src/unitree_lidar_ros/launch $H/unilidar_sdk/unitree_lidar_ros/src/unitree_lidar_ros/config 2>&1"
for f in "$H"/unilidar_sdk/unitree_lidar_ros/src/unitree_lidar_ros/config/config_radar0.yaml "$H"/unilidar_sdk/unitree_lidar_ros/src/unitree_lidar_ros/config/config_radar1.yaml "$H"/unilidar_sdk/unitree_lidar_ros/src/unitree_lidar_ros/launch/run_radar0_radar1.launch; do
  [ -f "$f" ] && install -D -m 0644 "$f" "$OUT/other/unilidar_sdk_v1/$(basename "$f")"
done
sh_ wheeltec "ls -la $H/wheeltec* 2>&1 | head; tar -tzf $H/wheeltec.tar.gz 2>&1 | head -20"
sh_ home-hidden "ls -la $H | grep '^d' | awk '{print \$9}' | tr '\n' ' '"
sh_ ros-packages "source /opt/ros/noetic/setup.bash; rospack list-names | wc -l; rospack list-names | grep -E 'fast_livo|vikit|unitree|cv_bridge|pcl|tf2|navigation|move_base|amcl|map_server|twist_mux|robot_localization' "
sh_ ros-runtime "source /opt/ros/noetic/setup.bash; rosnode list 2>&1; rostopic list 2>&1 | head -80"

echo "done $(date -Is)" >> "$OUT/PROGRESS"
chown -R sjytt:sjytt "$OUT"
echo OK > "$OUT/DONE"
