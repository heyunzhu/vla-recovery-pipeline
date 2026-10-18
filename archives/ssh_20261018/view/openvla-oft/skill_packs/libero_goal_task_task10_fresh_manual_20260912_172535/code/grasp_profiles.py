"""Fresh task10 grasp adapter for the cream-cheese flat pack."""

ADAPTER_NAME = "libero_goal_task10_fresh_grasp"
PROFILE_IDS = (
    "cream_cheese_flat_pack_short_side_deep_v1",
    "cream_cheese_flat_pack_pose_shallow_narrow_v2",
)

_PI = 3.141592653589793


class _Sample:
    def __init__(self, xyz, rpy, metadata=None):
        self.xyz = tuple(float(value) for value in xyz)
        self.rpy = tuple(float(value) for value in rpy)
        self.metadata = dict(metadata or {})

    def xyzrpy(self):
        return [*self.xyz, *self.rpy]

    def __eq__(self, other):
        return (
            isinstance(other, _Sample)
            and self.xyz == other.xyz
            and self.rpy == other.rpy
            and self.metadata == other.metadata
        )

    def __repr__(self):
        return "_Sample(xyz=%r, rpy=%r, metadata=%r)" % (self.xyz, self.rpy, self.metadata)


def _dims3(dims):
    values = []
    for index in range(3):
        try:
            raw = float(list(dims)[index])
        except (TypeError, ValueError, IndexError):
            raw = (0.018, 0.043, 0.081)[index]
        values.append(max(abs(raw), 0.001))
    return values


def _clamp(value, low, high):
    return min(max(float(value), float(low)), float(high))


def _wrap_yaw(value):
    out = (float(value) + _PI) % (2.0 * _PI) - _PI
    return out


def _sample(x, y, z, yaw, **metadata):
    wrapped = _wrap_yaw(yaw)
    data = dict(metadata)
    data.setdefault("world_yaw", wrapped)
    return _Sample((x, y, z), (0.0, 0.0, wrapped), data)


def _sample_xyzrpy(xyz, rpy, world_yaw, **metadata):
    wrapped = _wrap_yaw(world_yaw)
    data = dict(metadata)
    data.setdefault("world_yaw", wrapped)
    return _Sample(tuple(float(value) for value in xyz), tuple(float(value) for value in rpy), data)


def _pose_top_axis(pose):
    try:
        values = [float(value) for value in list(pose)]
    except (TypeError, ValueError):
        values = []
    if len(values) < 7:
        return 2, 1.0
    w, x, y, z = values[3:7]
    norm = (w * w + x * x + y * y + z * z) ** 0.5
    if norm <= 1e-9:
        return 2, 1.0
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    world_up_dots = [
        2.0 * (x * z - y * w),
        2.0 * (y * z + x * w),
        1.0 - 2.0 * (x * x + y * y),
    ]
    axis = max(range(3), key=lambda index: abs(world_up_dots[index]))
    sign = 1.0 if world_up_dots[axis] >= 0.0 else -1.0
    return axis, sign


def _pose_topdown_rpy_choices(top_axis, top_sign):
    if top_axis == 0 and top_sign < 0.0:
        return [
            (_PI, -0.5 * _PI, 0.0),
            (0.5 * _PI, -0.5 * _PI, 0.0),
            (0.0, -0.5 * _PI, 0.0),
            (-0.5 * _PI, -0.5 * _PI, 0.0),
        ]
    return [
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.5 * _PI),
        (0.0, 0.0, _PI),
        (0.0, 0.0, -0.5 * _PI),
    ]


def _pose_shallow_narrow_samples(ext, pose):
    half = [0.5 * float(value) for value in ext]
    top_axis, top_sign = _pose_top_axis(pose)
    tangent_axes = [axis for axis in range(3) if axis != top_axis]
    long_axis = max(tangent_axes, key=lambda axis: half[axis])
    short_axis = min(tangent_axes, key=lambda axis: half[axis])
    thin = min(half)
    depths = [_clamp(0.55 * thin, 0.004, 0.007), _clamp(0.85 * thin, 0.006, 0.010)]
    offsets = [(0.0, 0.0), (0.18 * half[long_axis], 0.0), (-0.18 * half[long_axis], 0.0), (0.0, 0.10 * half[short_axis]), (0.0, -0.10 * half[short_axis])]
    world_yaws = [0.0, 0.5 * _PI, _PI, -0.5 * _PI]
    rpy_choices = _pose_topdown_rpy_choices(top_axis, top_sign)
    samples = []
    rank = 0
    for world_yaw, local_rpy in zip(world_yaws, rpy_choices):
        for depth in depths:
            base = [0.0, 0.0, 0.0]
            base[top_axis] = top_sign * max(0.0, half[top_axis] - depth)
            for along_long, along_short in offsets:
                xyz = list(base)
                xyz[long_axis] = along_long
                xyz[short_axis] = along_short
                samples.append(_sample_xyzrpy(xyz, local_rpy, world_yaw, rank=rank, depth_from_top=depth, top_axis=top_axis, top_sign=top_sign, strategy="cream_cheese_flat_pack_pose_shallow_narrow"))
                rank += 1
    return samples


def sample_grasp_profile(profile, dims, *, rim=False, pose=None, **kwargs):
    if profile not in PROFILE_IDS:
        raise ValueError("unknown grasp profile: %s" % profile)
    ext = _dims3(dims)
    half_x = 0.5 * ext[0]
    half_y = 0.5 * ext[1]
    half_z = 0.5 * ext[2]
    thin = min(half_x, half_y, half_z)

    # The cream-cheese mesh is a thin flat pack. Default top-down samples close
    if profile == "cream_cheese_flat_pack_pose_shallow_narrow_v2":
        return _pose_shallow_narrow_samples(ext, pose)

    # too shallow and use diagonal yaws; keep a small, deeper cardinal set.
    depths = [
        _clamp(1.35 * thin, 0.010, 0.018),
        _clamp(2.05 * thin, 0.014, 0.026),
    ]
    lateral_y = 0.22 * half_y
    offsets = [
        (0.0, 0.0),
        (0.0, lateral_y),
        (0.0, -lateral_y),
    ]
    yaws = [0.0, _PI, 0.5 * _PI, -0.5 * _PI]

    samples = []
    rank = 0
    for yaw in yaws:
        for depth in depths:
            z = max(0.0, half_z - depth)
            for dx, dy in offsets:
                samples.append(
                    _sample(
                        dx,
                        dy,
                        z,
                        yaw,
                        rank=rank,
                        depth_from_top=depth,
                        strategy="cream_cheese_flat_pack_short_side_deep",
                    )
                )
                rank += 1
    return samples


def sample_grasp_profile_xyzrpy(profile, dims, *, rim=False, pose=None, **kwargs):
    return [sample.xyzrpy() for sample in sample_grasp_profile(profile, dims, rim=rim, pose=pose, **kwargs)]


def profile_gripper_width(profile, dims, *, rim=False, radius=None, pose=None, **kwargs):
    if profile not in PROFILE_IDS:
        raise ValueError("unknown grasp profile: %s" % profile)
    ext = _dims3(dims)
    if profile == "cream_cheese_flat_pack_pose_shallow_narrow_v2":
        return _clamp(1.90 * min(ext), 0.026, 0.040)
    width = 1.25 * max(ext[0], ext[1])
    return _clamp(width, 0.045, 0.075)
