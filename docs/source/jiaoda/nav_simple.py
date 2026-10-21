#!/usr/bin/env python3
"""
nav_simple.py v8 - A* 全局规划 + Pure Pursuit 路径跟踪 + DWA 局部避障
  
  数据流:
    收到 goal -> A* 规划全局路径 (一次, 不重规划)
                ↓
    控制循环 (20 Hz):
      Pure Pursuit: 在路径上找 lookahead 点 (前方 ~0.8m)
      DWA: 采样 (vx, vyaw) 网格, 用激光检测碰撞, 评分选最优
      发送 cmd_vel
"""
import math, threading, struct, heapq, time
import rospy
import numpy as np
from geometry_msgs.msg import PoseStamped, Twist
from sensor_msgs.msg import PointCloud2, Imu
from nav_msgs.msg import OccupancyGrid, Path
from actionlib_msgs.msg import GoalID

# ===== 速度限制 =====
VX_MAX        = 1.0
VX_MIN        = 0.5   # 不允许后退 (车不能后退)
VYAW_MAX      = 0.8

# ===== Pure Pursuit =====
LOOKAHEAD_DIST = 0.8   # 路径上前方多远找跟踪点

# ===== DWA =====
DWA_VX_SAMPLES   = 5    # vx 采样数
DWA_VYAW_SAMPLES = 11   # vyaw 采样数
DWA_PREDICT_T    = 2.0  # 预测时间 (秒)
DWA_DT           = 0.1  # 预测步长
DWA_W_HEAD       = 1.5  # 朝向 lookahead 权重
DWA_W_DIST       = 1.0  # 距 lookahead 近权重
DWA_W_VX         = 0.3  # 速度优先权重
DWA_W_OBST       = 30.0  # 避障权重 (大)
ROBOT_RADIUS     = 0.5  # 车体半径
SAFE_DIST        = 0.7  # 离激光点最小安全距离

# ===== 到达 =====
ARRIVE_FINAL  = 0.30
INVERT_YAW    = True

# ===== A* =====
INFLATE_RADIUS = 0.5
PATH_SIMPLIFY  = 4

# ===== 其他 =====
WD_S = 1.5
HZ   = 20

state = {
    'pos': None, 'pos_t': 0,
    'imu_yaw': None, 'imu_t': 0,
    'goal': None, 'active': False,
    'path': None,
    'map': None, 'map_meta': None,
    'lidar_world_pts': [],     # 世界坐标的近距离激光点 (用于 DWA 碰撞检测)
}
lock = threading.Lock()
pub_cmd = None
pub_path = None


def normalize_angle(a):
    while a >  math.pi: a -= 2*math.pi
    while a < -math.pi: a += 2*math.pi
    return a


# ===== ROS 回调 =====
def on_pose(msg):
    with lock:
        state['pos'] = (msg.pose.position.x, msg.pose.position.y)
        state['pos_t'] = rospy.get_time()


def on_imu(msg):
    q = msg.orientation
    yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z))
    with lock:
        state['imu_yaw'] = yaw
        state['imu_t'] = rospy.get_time()


def on_map(msg):
    w = msg.info.width; h = msg.info.height
    arr = np.array(msg.data, dtype=np.int8).reshape((h, w))
    with lock:
        state['map'] = arr
        state['map_meta'] = (msg.info.origin.position.x,
                             msg.info.origin.position.y,
                             msg.info.resolution, w, h)


def on_cloud(msg):
    """收激光点云, 转世界坐标存起来供 DWA 用"""
    if msg.fields is None or len(msg.fields) < 3: return
    pos = state.get('pos'); imu_yaw = state.get('imu_yaw')
    if pos is None or imu_yaw is None: return
    rx, ry = pos
    cy = math.cos(imu_yaw); sy = math.sin(imu_yaw)
    
    ps = msg.point_step
    n = len(msg.data) // ps
    pts = []
    for i in range(0, n, 3):
        off = i * ps
        try: x, y, z = struct.unpack_from('<fff', msg.data, off)
        except struct.error: continue
        if math.isnan(x) or math.isnan(y) or math.isnan(z): continue
        if not (-0.3 < z < 1.0): continue
        # 矩形过滤车身: 雷达在车前部, 车身在雷达后方
        # 排除车身投影矩形: -1.3m < x < 0.2m, -0.6m < y < 0.6m
        if -1.30 < x < 0.20 and -0.60 < y < 0.60: continue  # 车身
        d2 = x*x + y*y
        if d2 > 36: continue     # 6m 外不要
        # 转世界坐标
        wx = rx + x*cy - y*sy
        wy = ry + x*sy + y*cy
        pts.append((wx, wy))
    
    with lock:
        state['lidar_world_pts'] = pts


def on_goal(msg):
    gx, gy = msg.pose.position.x, msg.pose.position.y
    with lock:
        pos = state['pos']
        imu_yaw = state['imu_yaw']
        occ_map = state['map']
        meta = state['map_meta']
    
    if pos is None or imu_yaw is None:
        rospy.logwarn("[GOAL] 没位姿数据"); return
    
    d = math.hypot(gx-pos[0], gy-pos[1])
    rospy.loginfo(f"[GOAL] ({gx:+.2f}, {gy:+.2f}), 距离 {d:.2f}m")
    
    # A* 规划
    path = None
    if occ_map is not None and meta is not None:
        path = plan_astar(pos[0], pos[1], gx, gy, occ_map, meta)
    if path is None or len(path) < 2:
        rospy.logwarn("[A*] 找不到路径, 直走")
        path = [pos, (gx, gy)]
    else:
        rospy.loginfo(f"[A*] 路径 {len(path)} 个 waypoint")
    
    with lock:
        state['goal'] = (gx, gy)
        state['active'] = True
        state['path'] = path
    publish_path(path)


def on_cancel(msg):
    with lock:
        state['active'] = False
        state['goal'] = None
        state['path'] = None
    pub_cmd.publish(Twist())
    rospy.logwarn("[CANCEL] 已停")


# ===== A* (一次性全局规划) =====
def plan_astar(sx, sy, gx, gy, occ_map, meta):
    ox, oy, res, w, h = meta
    def w2g(wx, wy): return int((wx-ox)/res), int((wy-oy)/res)
    def g2w(gxc, gyc): return ox+(gxc+0.5)*res, oy+(gyc+0.5)*res
    sgx, sgy = w2g(sx, sy)
    ggx, ggy = w2g(gx, gy)
    if not (0<=sgx<w and 0<=sgy<h and 0<=ggx<w and 0<=ggy<h):
        return None
    occ = (occ_map > 50).astype(np.uint8)
    inflate = max(1, int(INFLATE_RADIUS/res))
    try:
        import cv2
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (inflate*2+1, inflate*2+1))
        inflated = cv2.dilate(occ, kernel)
    except Exception:
        inflated = occ
    def find_free(cx, cy):
        for r in range(1, 30):
            for ddx in range(-r, r+1):
                for ddy in range(-r, r+1):
                    nx, ny = cx+ddx, cy+ddy
                    if 0<=nx<w and 0<=ny<h and inflated[ny, nx]==0: return nx, ny
        return cx, cy
    if inflated[sgy, sgx]: sgx, sgy = find_free(sgx, sgy)
    if inflated[ggy, ggx]: ggx, ggy = find_free(ggx, ggy)
    
    open_set = [(0.0, sgx, sgy)]
    came_from = {}
    g_score = {(sgx, sgy): 0.0}
    closed = set()
    dirs = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]
    costs = [1.0]*4 + [1.414]*4
    while open_set:
        f, cx, cy = heapq.heappop(open_set)
        if (cx, cy) in closed: continue
        closed.add((cx, cy))
        if abs(cx-ggx)<=1 and abs(cy-ggy)<=1:
            cells = [(cx, cy)]
            cur = (cx, cy)
            while cur in came_from:
                cur = came_from[cur]; cells.append(cur)
            cells.reverse()
            simp = cells[::PATH_SIMPLIFY]
            if cells and simp[-1] != cells[-1]: simp.append(cells[-1])
            world_path = [g2w(c[0], c[1]) for c in simp]
            world_path[-1] = (gx, gy)
            return world_path
        for (ddx, ddy), cost in zip(dirs, costs):
            nx, ny = cx+ddx, cy+ddy
            if not (0<=nx<w and 0<=ny<h): continue
            if (nx, ny) in closed: continue
            if inflated[ny, nx]: continue
            ng = g_score[(cx, cy)] + cost
            if ng < g_score.get((nx, ny), float('inf')):
                g_score[(nx, ny)] = ng
                hcost = math.sqrt((nx-ggx)**2 + (ny-ggy)**2)
                heapq.heappush(open_set, (ng+hcost, nx, ny))
                came_from[(nx, ny)] = (cx, cy)
    return None


# ===== Pure Pursuit: 找 lookahead 点 =====
def find_lookahead(rx, ry, path, look_dist=LOOKAHEAD_DIST):
    """从路径上找 lookahead 点: 距车体最近的路径段, 沿前方走 look_dist"""
    if not path or len(path) < 2:
        return path[-1] if path else (rx, ry)
    
    # 找最近路径点
    min_d = float('inf'); min_i = 0
    for i, (px, py) in enumerate(path):
        d = math.hypot(px-rx, py-ry)
        if d < min_d:
            min_d = d; min_i = i
    
    # 从最近点开始沿路径找累计 look_dist 远的点
    accum = 0.0
    for i in range(min_i, len(path)-1):
        ax, ay = path[i]; bx, by = path[i+1]
        seg_len = math.hypot(bx-ax, by-ay)
        if accum + seg_len >= look_dist:
            # 在这段上插值
            t = (look_dist - accum) / max(seg_len, 1e-6)
            return (ax + t*(bx-ax), ay + t*(by-ay))
        accum += seg_len
    
    # 路径走完
    return path[-1]


# ===== DWA: 在 (vx, vyaw) 网格里找最优 =====
def dwa_select(rx, ry, ryaw, look_x, look_y, lidar_pts):
    """采样 (vx, vyaw), 模拟运动, 评分选最优. 返回 (vx, vyaw)"""
    best_score = -1e9
    best_vx, best_vyaw = 0.0, 0.0
    
    vx_list = np.linspace(VX_MIN, VX_MAX, DWA_VX_SAMPLES)
    vyaw_list = np.linspace(-VYAW_MAX, VYAW_MAX, DWA_VYAW_SAMPLES)
    
    # 转 lidar 到 numpy 加速
    if lidar_pts:
        lidar_arr = np.array(lidar_pts)
    else:
        lidar_arr = None
    
    for vx in vx_list:
        for vyaw in vyaw_list:
            # 模拟 DWA_PREDICT_T 秒后的轨迹
            sim_x, sim_y, sim_yaw = rx, ry, ryaw
            steps = int(DWA_PREDICT_T / DWA_DT)
            min_obst_d = float('inf')
            valid = True
            
            for _ in range(steps):
                sim_yaw = normalize_angle(sim_yaw + vyaw * DWA_DT)
                sim_x += vx * math.cos(sim_yaw) * DWA_DT
                sim_y += vx * math.sin(sim_yaw) * DWA_DT
                
                # 碰撞检查: 检查车体 5 个采样点 (中心 + 4 角)
                if lidar_arr is not None and len(lidar_arr) > 0:
                    cy_b = math.cos(sim_yaw); sy_b = math.sin(sim_yaw)
                    # 车体长 1.26m 宽 1.05m (基于雷达坐标系: 雷达在车前)
                    # 采样点: 雷达位置 + 车后 -0.6m 中心 + 4 个角
                    bx_local = [0.0, -0.6, 0.0, -0.6, 0.0]
                    by_local = [0.0, 0.0, +0.5, +0.5, -0.5]
                    bx_local += [-0.6]; by_local += [-0.5]
                    min_d_step = float('inf')
                    for blx, bly in zip(bx_local, by_local):
                        wx_p = sim_x + blx*cy_b - bly*sy_b
                        wy_p = sim_y + blx*sy_b + bly*cy_b
                        dx = lidar_arr[:, 0] - wx_p
                        dy = lidar_arr[:, 1] - wy_p
                        d = np.sqrt(dx*dx + dy*dy).min()
                        if d < min_d_step:
                            min_d_step = d
                    if min_d_step < ROBOT_RADIUS:
                        valid = False
                        break
                    if min_d_step < min_obst_d:
                        min_obst_d = min_d_step
            
            if not valid:
                continue
            
            # 评分:
            # 1. 终点距离 lookahead 越近越好
            d_look = math.hypot(sim_x - look_x, sim_y - look_y)
            score_dist = -d_look
            
            # 2. 朝向 lookahead
            target_yaw = math.atan2(look_y - sim_y, look_x - sim_x)
            yerr = abs(normalize_angle(target_yaw - sim_yaw))
            score_head = -yerr
            
            # 3. 速度
            score_vx = vx
            
            # 4. 远离障碍 (clearance) - 软约束
            if min_obst_d < float('inf'):
                # < SAFE_DIST 大幅扣分, > SAFE_DIST 线性奖励 (最多 +2)
                if min_obst_d < SAFE_DIST:
                    score_obst = -2.0 * (SAFE_DIST - min_obst_d) / SAFE_DIST
                else:
                    score_obst = min((min_obst_d - SAFE_DIST), 2.0)
            else:
                score_obst = 2.0
            
            score = (DWA_W_DIST*score_dist + DWA_W_HEAD*score_head +
                     DWA_W_VX*score_vx + DWA_W_OBST*score_obst)
            
            if score > best_score:
                best_score = score
                best_vx = vx; best_vyaw = vyaw
    
    return best_vx, best_vyaw, best_score


def publish_path(path):
    msg = Path()
    msg.header.stamp = rospy.Time.now()
    msg.header.frame_id = 'map'
    for wx, wy in path:
        ps = PoseStamped()
        ps.header = msg.header
        ps.pose.position.x = wx; ps.pose.position.y = wy
        ps.pose.orientation.w = 1.0
        msg.poses.append(ps)
    pub_path.publish(msg)


# ===== 主控制 =====
def loop():
    rate = rospy.Rate(HZ)
    last_log = 0
    while not rospy.is_shutdown():
        rate.sleep()
        with lock:
            pos = state['pos']; pos_t = state['pos_t']
            imu_yaw = state['imu_yaw']; imu_t = state['imu_t']
            goal = state['goal']; active = state['active']
            path = state['path']
            lidar_pts = state['lidar_world_pts']

        # 看门狗
        if pos is None or rospy.get_time() - pos_t > WD_S:
            pub_cmd.publish(Twist()); continue
        if imu_yaw is None or rospy.get_time() - imu_t > WD_S:
            pub_cmd.publish(Twist()); continue
        if not active or not path or not goal:
            continue

        rx, ry = pos
        gx, gy = goal
        d_goal = math.hypot(gx-rx, gy-ry)

        # 到达 - 强制停车
        if d_goal < ARRIVE_FINAL:
            pub_cmd.publish(Twist())  # 零速命令
            with lock:
                state['active'] = False; state['goal'] = None; state['path'] = None
            rospy.loginfo(f"[ARRIVE] OK d={d_goal:.2f}m")
            continue
        
        # 接近终点 - 慢速直走 (绕过 DWA, 避免冲过头转圈)
        SLOW_ZONE = ARRIVE_FINAL + 0.5  # 进入 SLOW_ZONE 后用简单控制
        if d_goal < SLOW_ZONE:
            target_yaw = math.atan2(gy - ry, gx - rx)
            yerr = normalize_angle(target_yaw - imu_yaw)
            # 速度: 距离越近越慢 (从 0.20 缓降到 0.10)
            vx = max(0.10, min(0.20, d_goal * 0.3))
            # 朝向修正: 小角度修正
            vyaw = max(-0.4, min(0.4, yerr * 1.0))
            vyaw_out = -vyaw if INVERT_YAW else vyaw
            m = Twist()
            m.linear.x = vx
            m.angular.z = vyaw_out
            pub_cmd.publish(m)
            if rospy.get_time() - last_log > 0.5:
                last_log = rospy.get_time()
                rospy.loginfo(f"[FINAL] d_goal={d_goal:.2f}m vx={vx:.2f} vyaw={vyaw:+.2f}")
            continue

        # Pure Pursuit: 找 lookahead 点
        look = LOOKAHEAD_DIST if d_goal > LOOKAHEAD_DIST else d_goal
        look_x, look_y = find_lookahead(rx, ry, path, look)

        # DWA: 选最优 (vx, vyaw)
        vx, vyaw, sc = dwa_select(rx, ry, imu_yaw, look_x, look_y, lidar_pts)
        
        # 没有可行动作 (全部碰撞), 原地转向脱困
        if vx == 0 and vyaw == 0:
            # 向激光点少的方向转
            if lidar_pts:
                cy_ = math.cos(imu_yaw); sy_ = math.sin(imu_yaw)
                left = right = 0
                for px, py in lidar_pts:
                    dx_ = px-rx; dy_ = py-ry
                    bx_ = dx_*cy_ + dy_*sy_; by_ = -dx_*sy_ + dy_*cy_
                    if 0 < bx_ < 2.0:
                        if by_ > 0: left += 1
                        else: right += 1
                vyaw = 0.6 if left <= right else -0.6
                vx = 0.05
                rospy.logwarn_throttle(1.0, f"[STUCK] DWA 全堵, pts={len(lidar_pts)} 原地转 (左={left}, 右={right})")
            else:
                # 没激光数据, 默认前进
                vx = 0.10; vyaw = 0.0

        # INVERT_YAW
        vyaw_out = -vyaw if INVERT_YAW else vyaw

        m = Twist()
        m.linear.x = vx
        m.angular.z = vyaw_out
        pub_cmd.publish(m)

        if rospy.get_time() - last_log > 0.5:
            last_log = rospy.get_time()
            rospy.loginfo(f"[CTRL] d_goal={d_goal:.2f}m look=({look_x:+.2f},{look_y:+.2f}) "
                         f"vx={vx:.2f} vyaw={vyaw:+.2f} score={sc:+.2f} pts={len(lidar_pts)}")


def main():
    global pub_cmd, pub_path
    print("=" * 60)
    print("  nav_simple v8 - A* + Pure Pursuit + DWA")
    print(f"  VX_MAX={VX_MAX} VYAW_MAX={VYAW_MAX} INVERT_YAW={INVERT_YAW}")
    print(f"  LOOKAHEAD={LOOKAHEAD_DIST}m  ARRIVE={ARRIVE_FINAL}m")
    print(f"  DWA: {DWA_VX_SAMPLES}x{DWA_VYAW_SAMPLES} samples, predict {DWA_PREDICT_T}s")
    print(f"  ROBOT_RADIUS={ROBOT_RADIUS}m  SAFE_DIST={SAFE_DIST}m")
    print("=" * 60)
    rospy.init_node('nav_simple', disable_signals=True)
    pub_cmd  = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
    pub_path = rospy.Publisher('/nav_path', Path, queue_size=1, latch=True)
    rospy.Subscriber('/slam_pose',              PoseStamped,    on_pose,   queue_size=10)
    rospy.Subscriber('/imu',                    Imu,            on_imu,    queue_size=10)
    rospy.Subscriber('/map',                    OccupancyGrid,  on_map,    queue_size=1)
    rospy.Subscriber('/move_base_simple/goal',  PoseStamped,    on_goal,   queue_size=1)
    rospy.Subscriber('/move_base/cancel',       GoalID,         on_cancel, queue_size=1)
    rospy.Subscriber('/unilidar/cloud',         PointCloud2,    on_cloud,  queue_size=1, buff_size=2**24)
    threading.Thread(target=loop, daemon=True).start()
    rospy.spin()


if __name__ == "__main__":
    main()
