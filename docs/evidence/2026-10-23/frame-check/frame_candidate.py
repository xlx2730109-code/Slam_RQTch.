"""Offline candidate: sensor mounting geometry, not deployed to the robot."""
import math


def cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def mounting(forward_axis, up_axis):
    axes = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0),
            "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
    forward, up = axes[forward_axis], axes[up_axis]
    if sum(a*b for a, b in zip(forward, up)) != 0:
        raise ValueError("forward and up axes must be perpendicular")
    return (forward, cross(up, forward), up)


def sensor_to_body(point, mount):
    return tuple(sum(a*b for a, b in zip(row, point)) for row in mount)


def world_sensor_rotation(q):
    length = math.sqrt(sum(v*v for v in q))
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError("invalid quaternion")
    x, y, z, w = (v/length for v in q)
    return ((1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)),
            (2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)),
            (2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)))


def world_body_rotation(q, mount):
    world_sensor = world_sensor_rotation(q)
    return tuple(tuple(sum(world_sensor[i][k]*mount[j][k] for k in range(3))
                       for j in range(3)) for i in range(3))


def body_heading(q, mount):
    rotation = world_body_rotation(q, mount)
    x, y = rotation[0][0], rotation[1][0]
    if math.hypot(x, y) < 0.2:
        raise ValueError("body forward direction is nearly vertical")
    return math.atan2(y, x)
