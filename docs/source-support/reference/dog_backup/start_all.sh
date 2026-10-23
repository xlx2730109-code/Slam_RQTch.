#!/bin/bash
# start_all.sh v2 - 一键启动 (修复 nohup sudo 卡密码问题)
# 用法: bash ~/dog_backup/start_all.sh

set +H

LOG_DIR="$HOME/run_logs"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "  Wheeltec 履带车 - 一键启动 v2"
echo "============================================================"
echo ""

# ===== 1. 杀旧进程 =====
echo "[1/4] 清理旧进程..."
pkill -9 -f "ros|slam|lio|orbbec|rslidar|nav_simple|nav_gui|uart|chassis|yesense|nmea|ekf|gemini|ffplay|cmd_vel|lidar_odom|move_base|cloud_to_scan|start_nav" 2>/dev/null
sleep 5
pkill -9 -f "rosmaster|roscore" 2>/dev/null
sleep 2
echo "    OK"
echo ""

# ===== 2. 启动底层系统 (新窗口前台跑, 客户能看到日志) =====
echo "[2/4] 启动底层系统..."
echo "    会打开一个新终端窗口跑 start_nav.sh"
echo "    如果要 sudo 密码, 在新窗口输入"
echo ""

# 优先用 gnome-terminal, 没有则用 xterm
if command -v gnome-terminal &> /dev/null; then
    gnome-terminal --title="底层系统 (start_nav)" -- bash -c "cd ~/dog_backup && bash start_nav.sh; echo ''; echo '按回车关闭'; read" &
elif command -v xterm &> /dev/null; then
    xterm -T "底层系统" -e "cd ~/dog_backup && bash start_nav.sh; echo '按回车关闭'; read" &
else
    echo "    没装 gnome-terminal 或 xterm, 改用后台 nohup"
    cd ~/dog_backup && nohup bash start_nav.sh > "$LOG_DIR/start.log" 2>&1 &
fi

echo "    等待底层系统初始化 (90 秒)..."
echo "    如果新窗口提示要密码, 输入 123456"

# 等启动 + 检查 SLAM 数据
for i in {1..18}; do
    sleep 5
    source /opt/ros/noetic/setup.bash >/dev/null 2>&1
    SLAM_OK=$(timeout 1 rostopic info /slam_pose 2>&1 | grep -c "Type:")
    if [ "$SLAM_OK" = "1" ]; then
        echo "    底层就绪 (用时 $((i*5)) 秒)"
        break
    fi
    echo "    等待中 ($((i*5))s)..."
done
echo ""

# ===== 3. 启动 nav_simple =====
echo "[3/4] 启动 nav_simple..."
source /opt/ros/noetic/setup.bash
nohup python3 -u "$HOME/dog_backup/nav_simple.py" > "$LOG_DIR/nav_simple.log" 2>&1 &
NAV_PID=$!
sleep 3

if ps -p $NAV_PID > /dev/null; then
    echo "    nav_simple 启动成功 (PID=$NAV_PID)"
else
    echo "    nav_simple 启动失败! 查 $LOG_DIR/nav_simple.log"
fi
echo ""

# ===== 4. 启动 nav_gui (前台) =====
echo "[4/4] 启动图形界面..."
echo ""
echo "============================================================"
echo "  使用方法:"
echo "    1. 关闭 GUI 上的 [跟随机器人] 勾选"
echo "    2. 在地图上 [右键] 点车前方 2-3 米的位置"
echo "    3. 点 [>> START NAV] 开始导航"
echo "    4. 紧急停止: 点 [!! CANCEL / E-STOP]"
echo "============================================================"
echo ""

python3 "$HOME/dog_backup/nav_gui.py"

echo ""
echo "GUI 已关闭. 系统仍在后台运行."
echo "完全关闭: pkill -9 -f 'ros|slam|lio|nav_'"
