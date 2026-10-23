#!/bin/bash
# start_nav.sh v6 - LIO-SAM odom + slam_grid + move_base (A* + DWA)
set -u

WORKDIR="$HOME/dog_backup"
WS="$HOME/tracked_nav_ws"
ORBBEC_WS="$HOME/orbbec_ws"

ODOM_TOPIC="/lio_sam/mapping/odometry"
LIDAR_TOPIC="/rslidar_points"

CAMERA_RTSP="${CAMERA_RTSP:-}"

LOG_DIR="$HOME/run_logs"
mkdir -p "$LOG_DIR"
for f in bringup liosam orbbec slam move_base; do : > "$LOG_DIR/${f}.log"; done

source /opt/ros/noetic/setup.bash
source "$WS/devel/setup.bash"

if ! rospack find sensor_bringup >/dev/null 2>&1; then
    echo "❌ sensor_bringup 找不到"; exit 1
fi

[ -f "$WORKDIR/slam_grid_ros1.py" ]    || { echo "❌ 缺 slam_grid_ros1.py"; exit 1; }

echo "🧹 清残留..."
sudo pkill -9 -f "roslaunch|rosmaster|rosout|rviz|move_base|amcl|map_server|ekf|navsat|chassis_node|rslidar|yesense|nmea|slam_grid|lio_sam|lidar_odom|orbbec|gemini|cmd_vel_bridge|uart" 2>/dev/null
pkill -9 -f "ffplay" 2>/dev/null
sleep 3

PIDS=()
cleanup() {
    echo ""
    echo "🛑 退出..."
    for pid in "${PIDS[@]}"; do kill -INT "$pid" 2>/dev/null; done
    sleep 1
    for pid in "${PIDS[@]}"; do kill -9 "$pid" 2>/dev/null; done
    sudo pkill -9 -f "roslaunch|rosmaster|rosout|rslidar|chassis_node|yesense|nmea|slam_grid|lio_sam|orbbec|gemini|move_base|uart" 2>/dev/null
    pkill -9 -f "ffplay" 2>/dev/null
    echo "✅ 全停"
    exit 0
}
trap cleanup INT TERM

# 1. 传感器栈 (bringup_all 已经 include 了 uart 替代 chassis_node)
echo "▶️  bringup..."
roslaunch sensor_bringup bringup_all.launch use_camera:=false >> "$LOG_DIR/bringup.log" 2>&1 &
PIDS+=($!)
sleep 4

echo "⏳ 等 master..."
for i in {1..40}; do rostopic list >/dev/null 2>&1 && break; sleep 1; done
if ! rostopic list >/dev/null 2>&1; then
    echo "❌ master 起不来"; tail -30 "$LOG_DIR/bringup.log"; cleanup
fi
echo "✅ master OK"

echo "⏳ 等 $LIDAR_TOPIC ..."
for i in {1..30}; do
    [ "$(timeout 1 rostopic hz $LIDAR_TOPIC 2>&1 | grep -c 'average rate')" -gt 0 ] && break
    sleep 1
done

# 2. Orbbec
if [ -f "$ORBBEC_WS/devel/setup.bash" ]; then
    echo "▶️  orbbec..."
    bash -c "
        source /opt/ros/noetic/setup.bash
        source $ORBBEC_WS/devel/setup.bash
        roslaunch orbbec_camera gemini_330_series.launch
    " >> "$LOG_DIR/orbbec.log" 2>&1 &
    PIDS+=($!)
    sleep 4
fi

# 3. LIO-SAM
echo "▶️  LIO-SAM..."
roslaunch lio_sam_config mapping.launch open_rviz:=false >> "$LOG_DIR/liosam.log" 2>&1 &
PIDS+=($!)
sleep 6

echo "⏳ 等 LIO-SAM 出 $ODOM_TOPIC ..."
for i in {1..60}; do
    [ "$(timeout 1 rostopic hz $ODOM_TOPIC 2>&1 | grep -c 'average rate')" -gt 0 ] && break
    sleep 1
done

# 4. SLAM (现在会发 /map + tf map->odom)
echo "▶️  slam_grid..."
python3 -u "$WORKDIR/slam_grid_ros1.py" \
    _odom_topic:=$ODOM_TOPIC \
    _lidar_topic:=$LIDAR_TOPIC >> "$LOG_DIR/slam.log" 2>&1 &
PIDS+=($!)
sleep 3

# 5. move_base (A* + DWA)
echo "▶️  move_base..."
PIDS+=($!)
sleep 3

# 6. 摄像头窗口可选
if [ -n "$CAMERA_RTSP" ] && [ -n "${DISPLAY:-}" ] && command -v ffplay &>/dev/null; then
    ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay -framedrop \
           -window_title "Camera" -x 800 -y 450 -loglevel error \
           "$CAMERA_RTSP" >/dev/null 2>&1 &
    PIDS+=($!)
fi

sleep 2
echo ""
echo "============================================================"
echo "  全部启动完成 (LIO-SAM odom + slam_grid + move_base A*/DWA)"
echo "============================================================"
echo "  另开终端开 viewer:"
echo "    source /opt/ros/noetic/setup.bash"
echo "    python3 ~/dog_backup/slam_viewer.py"
echo ""
echo "  导航流程:"
echo "    1. viewer 按 l 加载地图"
echo "    2. v 视觉重定位"
echo "    3. 右键点目标 -> move_base 自动 A* 规划 + DWA 避障"
echo "    4. c 取消"
echo ""
echo "  Ctrl+C 退出"
echo "============================================================"

tail -F "$LOG_DIR"/*.log 2>/dev/null
