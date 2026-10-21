#!/bin/bash
# 部署后自检脚本（在 Jetson 上运行）
# 用法: ~/jiaoda/verify.sh
source /opt/ros/noetic/setup.bash 2>/dev/null
export ROS_MASTER_URI=${ROS_MASTER_URI:-http://127.0.0.1:11311}

PASS=0; FAIL=0
ok()   { printf "  \033[32mPASS\033[0m  %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAIL=$((FAIL+1)); }

rate() { timeout 6 rostopic hz "$1" 2>&1 | grep -o 'average rate: [0-9.]*' | tail -1 | awk '{print $3}'; }
gt()   { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a>b)}'; }

echo "== 1. systemd 服务 =="
for s in lidar restamp campub fastlivo grid posebridge nav control console; do
  st=$(systemctl is-active jiaoda-$s 2>/dev/null)
  [ "$st" = "active" ] && ok "jiaoda-$s" || bad "jiaoda-$s ($st)"
done

echo "== 2. ROS 话题频率 =="
for t in /unilidar/cloud:5 /unilidar/imu:100 /synced/cloud:5 \
         /left_camera/image:5 /aft_mapped_to_init:5 /slam_pose:5; do
  topic=${t%:*}; min=${t#*:}
  r=$(rate "$topic")
  if [ -n "$r" ] && gt "$r" "$min"; then ok "$topic = ${r} Hz"
  else bad "$topic = ${r:-0} Hz (期望 > ${min})"; fi
done

echo "== 3. 底盘串口 =="
if timeout 6 rostopic hz /jiaoda/esp_tel 2>&1 | grep -q "average rate"; then
  ok "/jiaoda/esp_tel 有回传（串口已连通）"
else
  bad "/jiaoda/esp_tel 无数据（检查 CTL_PORT / 串口占用）"
fi

echo "== 4. 网页与接口 =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 4 http://127.0.0.1:8090/ 2>/dev/null)
[ "$code" = "200" ] && ok "控制台 HTTP 200" || bad "控制台 HTTP $code"
curl -s -m 4 http://127.0.0.1:8090/api/mapinfo | grep -q mpp \
  && ok "/api/mapinfo 正常" || bad "/api/mapinfo 异常"
curl -s -m 4 http://127.0.0.1:8090/api/pose | grep -q '"x"' \
  && ok "/api/pose 正常" || bad "/api/pose 异常"

echo
echo "结果: $PASS 通过, $FAIL 失败"
[ "$FAIL" -eq 0 ] && echo "系统自检通过。" || echo "存在失败项，请按 README 第 12 章排查。"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
