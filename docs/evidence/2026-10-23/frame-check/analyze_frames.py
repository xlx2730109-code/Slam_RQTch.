import json
import math
import pathlib
import statistics


def rotation(q):
    norm = math.sqrt(sum(v * v for v in q))
    if norm < 1e-12 or not math.isfinite(norm):
        raise ValueError("invalid quaternion")
    x, y, z, w = [v / norm for v in q]
    return [
        [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
        [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)],
    ]


def angle_diff(a, b):
    return math.atan2(math.sin(a - b), math.cos(a - b))


def heading(q, axis):
    r = rotation(q)
    x, y = r[0][axis], r[1][axis]
    return math.atan2(y, x), math.hypot(x, y)


def angular_summary(values):
    anchor = values[0]
    vals = [math.degrees(angle_diff(v, anchor)) for v in values]
    return {"range_deg": max(vals) - min(vals),
            "std_deg": statistics.pstdev(vals),
            "net_deg": vals[-1]}


def analyze(data):
    streams = {s["topic"]: s for s in data["streams"]}
    odom = streams["/aft_mapped_to_init"].get("samples", [])
    imu = streams["/unilidar/imu"].get("samples", [])
    if len(odom) < 2:
        raise ValueError("insufficient odometry")
    q0 = odom[0]["q"]
    norm0 = math.sqrt(sum(v*v for v in q0))
    orientation_changes = []
    for s in odom:
        q = s["q"]
        dot = abs(sum(a*b for a, b in zip(q0, q)))
        dot /= norm0 * math.sqrt(sum(v*v for v in q))
        orientation_changes.append(math.degrees(2*math.acos(min(1, dot))))
    report = {
        "odom_count": len(odom),
        "odom_seconds": odom[-1]["received"] - odom[0]["received"],
        "position_range_m": [max(s["p"][i] for s in odom)-min(s["p"][i] for s in odom)
                             for i in range(3)],
        "full_rotation_max_change_deg": max(orientation_changes),
        "heading_using_sensor_x": angular_summary([heading(s["q"], 0)[0] for s in odom]),
        "heading_using_sensor_z": angular_summary([heading(s["q"], 2)[0] for s in odom]),
        "sensor_x_horizontal_norm_min": min(heading(s["q"], 0)[1] for s in odom),
        "sensor_z_horizontal_norm_min": min(heading(s["q"], 2)[1] for s in odom),
        "mean_acceleration": [statistics.mean(s["a"][i] for s in imu) for i in range(3)] if imu else None,
        "cmd_vel_samples": len(streams["/cmd_vel"].get("samples", [])),
        "limits": ["No physical ground truth collected", "Sensor +Z versus -Z front/back sign unverified",
                   "No runtime source or parameters changed"],
    }
    return report


if __name__ == "__main__":
    path = pathlib.Path(__file__).with_name("streams.json")
    print(json.dumps(analyze(json.loads(path.read_text(encoding="utf-8-sig"))), indent=2))
