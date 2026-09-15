"""LIBERO-90 legacy grasp-profile sampling rules.

This adapter is loaded only when the ``libero90_legacy`` skill pack is active.
It keeps the historical LIBERO-90 tuned grasp profiles out of the default
tiptop recovery path while preserving identical problem/debug and real cuTAMP
sampling behavior for the legacy pack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from experiments.robot.libero.tiptop_repro.libero_panda_frames import quat_wxyz_to_matrix

DEFAULT_GRASP_SAMPLER_PROFILE = "libero_topdown"
NATIVE_GRASP_SAMPLER_PROFILES = frozenset({"native", "cutamp_native"})
BOWL_RIM_OPEN_DRAWER_POINT_PROFILE_INDICES = {
    "bowl_rim_open_drawer_p0_topdown_v1": 0,
    "bowl_rim_open_drawer_p2_topdown_v1": 2,
    "bowl_rim_open_drawer_p4_topdown_v1": 4,
}
BOWL_RIM_GRASP_SAMPLER_PROFILES = frozenset(
    {
        "bowl_rim_radial_topdown_v1",
        "bowl_rim_tangent_topdown_v1",
        "bowl_rim_cardinal_mixed_topdown_v1",
        "bowl_rim_diagonal_mixed_topdown_v1",
        "bowl_rim_away_from_open_drawer_topdown_v1",
        *BOWL_RIM_OPEN_DRAWER_POINT_PROFILE_INDICES.keys(),
    }
)
SMALL_SHALLOW_BOWL_GRASP_SAMPLER_PROFILES = frozenset({"bowl_rim_small_shallow_diagonal_topdown_v1"})
MUG_BODY_GRASP_SAMPLER_PROFILES = frozenset({"mug_body_side_avoid_handle_v1"})
MUG_HANDLE_GRASP_SAMPLER_PROFILES = frozenset(
    {
        "mug_handle_topdown_v1",
        "mug_handle_then_body_side_v1",
        "mug_handle_local_pos_x_topdown_v1",
        "mug_handle_local_neg_x_topdown_v1",
        "mug_handle_local_pos_x_then_body_side_v1",
        "mug_handle_local_neg_x_then_body_side_v1",
    }
)
MOKA_POT_HANDLE_GRASP_SAMPLER_PROFILES = frozenset({"moka_pot_handle_topdown_v1"})
CAN_BODY_GRASP_SAMPLER_PROFILES = frozenset({"can_body_lower_side_v1", "can_body_orthogonal_lower_side_v1"})
FLAT_BOX_GRASP_SAMPLER_PROFILES = frozenset(
    {
        "flat_box_topdown_short_side_v1",
        "flat_box_topdown_short_side_deep_v1",
        "flat_box_topdown_short_side_book_v1",
    }
)
CARTON_BODY_GRASP_SAMPLER_PROFILES = frozenset(
    {
        "carton_body_vertical_deep_v1",
        "carton_upright_body_side_v1",
        "carton_fallen_body_side_v1",
    }
)
TOPDOWN_GRASP_SAMPLER_PROFILES = (
    frozenset({"libero_topdown", "hollow_bowl_rim_topdown"})
    | BOWL_RIM_GRASP_SAMPLER_PROFILES
    | SMALL_SHALLOW_BOWL_GRASP_SAMPLER_PROFILES
    | MUG_BODY_GRASP_SAMPLER_PROFILES
    | MUG_HANDLE_GRASP_SAMPLER_PROFILES
    | MOKA_POT_HANDLE_GRASP_SAMPLER_PROFILES
    | CAN_BODY_GRASP_SAMPLER_PROFILES
    | FLAT_BOX_GRASP_SAMPLER_PROFILES
    | CARTON_BODY_GRASP_SAMPLER_PROFILES
)
ALLOWED_GRASP_SAMPLER_PROFILES = TOPDOWN_GRASP_SAMPLER_PROFILES | NATIVE_GRASP_SAMPLER_PROFILES
GRASP_SAMPLER_PROFILE_ALIASES = {"": DEFAULT_GRASP_SAMPLER_PROFILE, "default": DEFAULT_GRASP_SAMPLER_PROFILE}
ALLOWED_SKILL_GRASP_PROFILES = (
    "default",
    *sorted(ALLOWED_GRASP_SAMPLER_PROFILES),
)
ADAPTER_NAME = "libero90_legacy_grasp_profiles"
PROFILE_IDS = frozenset(ALLOWED_GRASP_SAMPLER_PROFILES - NATIVE_GRASP_SAMPLER_PROFILES - {"libero_topdown", "hollow_bowl_rim_topdown"})


@dataclass(frozen=True)
class LocalGraspSample:
    xyz: Tuple[float, float, float]
    rpy: Tuple[float, float, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def xyzrpy(self) -> List[float]:
        return [*self.xyz, *self.rpy]


def normalize_grasp_sampler_profile(value: Any) -> str:
    raw = str(value or DEFAULT_GRASP_SAMPLER_PROFILE).strip()
    profile = GRASP_SAMPLER_PROFILE_ALIASES.get(raw, raw)
    if profile not in ALLOWED_GRASP_SAMPLER_PROFILES:
        allowed = sorted((*ALLOWED_GRASP_SAMPLER_PROFILES, *GRASP_SAMPLER_PROFILE_ALIASES))
        raise ValueError(f"unknown_grasp_sampler_profile:{raw}; allowed={allowed}")
    return profile


def is_native_grasp_sampler_profile(profile: str) -> bool:
    return normalize_grasp_sampler_profile(profile) in NATIVE_GRASP_SAMPLER_PROFILES


def _dims3(dims: Iterable[float], default: Tuple[float, float, float]) -> np.ndarray:
    arr = np.asarray(list(dims), dtype=np.float64).reshape(-1)
    if arr.size < 3:
        arr = np.pad(arr, (0, 3 - arr.size), constant_values=0.0)
    fallback = np.asarray(default, dtype=np.float64)
    arr = arr[:3]
    arr = np.where(np.abs(arr) > 1e-9, arr, fallback)
    return np.maximum(arr, 1e-4)


def wrap_yaw_rad(value: float) -> float:
    return float((value + np.pi) % (2.0 * np.pi) - np.pi)


def rot_z(yaw: float) -> np.ndarray:
    c = float(np.cos(yaw))
    s = float(np.sin(yaw))
    return np.asarray([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def matrix_to_xyz_rpy(matrix: Any) -> List[float]:
    rot = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    pitch = float(np.arcsin(np.clip(rot[0, 2], -1.0, 1.0)))
    cp = float(np.cos(pitch))
    if abs(cp) > 1e-8:
        roll = float(np.arctan2(-rot[1, 2], rot[2, 2]))
        yaw = float(np.arctan2(-rot[0, 1], rot[0, 0]))
    else:
        roll = float(np.arctan2(rot[2, 1], rot[1, 1]))
        yaw = 0.0
    return [float(roll), float(pitch), wrap_yaw_rad(yaw)]


def pose7_rotation_matrix(pose: Optional[List[float]]) -> np.ndarray:
    if pose is None:
        return np.eye(3, dtype=np.float64)
    arr = np.asarray(pose, dtype=np.float64).reshape(-1)
    if arr.size < 7:
        return np.eye(3, dtype=np.float64)
    return quat_wxyz_to_matrix(arr[3:7])


def _ellipse_point(half_x: float, half_y: float, direction: Tuple[float, float], frac: float) -> Tuple[float, float]:
    dx, dy = direction
    return float(frac * half_x * dx), float(frac * half_y * dy)


def _sample(x: float, y: float, z: float, roll: float, pitch: float, yaw: float, **metadata: Any) -> LocalGraspSample:
    return LocalGraspSample(
        xyz=(float(x), float(y), float(z)),
        rpy=(float(roll), float(pitch), wrap_yaw_rad(float(yaw))),
        metadata=dict(metadata),
    )


def _topdown_samples(dims: Iterable[float], *, rim: bool) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.06, 0.06, 0.04))
    half_x = max(float(ext[0]) * 0.5, 1e-4)
    half_y = max(float(ext[1]) * 0.5, 1e-4)
    half_height = max(float(ext[2]) * 0.5, 1e-4)
    yaw_choices = [0.0, 0.5 * np.pi, np.pi, -0.5 * np.pi, 0.25 * np.pi, -0.25 * np.pi, 0.75 * np.pi, -0.75 * np.pi]
    if rim:
        z_values = [
            max(0.0, half_height - 0.018),
            max(0.0, half_height - 0.028),
        ]
        xy_offsets: List[Tuple[float, float]] = []
        for frac in (0.78, 0.86):
            xy_offsets.extend(
                [
                    (frac * half_x, 0.0),
                    (-frac * half_x, 0.0),
                    (0.0, frac * half_y),
                    (0.0, -frac * half_y),
                ]
            )
    else:
        z_values = [max(0.0, half_height - 0.02)]
        lateral = 0.35 * min(half_x, half_y)
        xy_offsets = [
            (0.0, 0.0),
            (lateral, 0.0),
            (-lateral, 0.0),
            (0.0, lateral),
            (0.0, -lateral),
        ]
    samples: List[LocalGraspSample] = []
    for yaw in yaw_choices:
        for z in z_values:
            for dx, dy in xy_offsets:
                samples.append(_sample(dx, dy, z, 0.0, 0.0, yaw, world_yaw=wrap_yaw_rad(yaw)))
    return samples


def _bowl_rim_samples(
    profile: str,
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.15, 0.15, 0.05))
    half_x = max(float(ext[0]) * 0.5, 1e-4)
    half_y = max(float(ext[1]) * 0.5, 1e-4)
    half_height = max(float(ext[2]) * 0.5, 1e-4)
    z_values = [max(0.0, half_height - 0.022), max(0.0, half_height - 0.032)]
    radial_fracs = [0.72, 0.82]
    inv_sqrt2 = float(1.0 / np.sqrt(2.0))
    cardinal = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)]
    diagonal = [
        (inv_sqrt2, inv_sqrt2),
        (-inv_sqrt2, inv_sqrt2),
        (inv_sqrt2, -inv_sqrt2),
        (-inv_sqrt2, -inv_sqrt2),
    ]

    open_drawer_point_id = ""
    if profile in BOWL_RIM_OPEN_DRAWER_POINT_PROFILE_INDICES:
        world_from_obj = pose7_rotation_matrix(pose)
        ranked = []
        for direction in [*cardinal, *diagonal]:
            dx, dy = _ellipse_point(half_x, half_y, direction, 1.0)
            world_offset = world_from_obj @ np.asarray([dx, dy, 0.0], dtype=np.float64)
            ranked.append((float(world_offset[1]), float(world_offset[0]), direction))
        point_index = BOWL_RIM_OPEN_DRAWER_POINT_PROFILE_INDICES[profile]
        directions = [sorted(ranked, key=lambda item: (item[0], item[1]))[point_index][2]]
        radial_fracs = [0.82]
        yaw_mode = "tangent"
        open_drawer_point_id = f"P{point_index}"
    elif profile == "bowl_rim_away_from_open_drawer_topdown_v1":
        world_from_obj = pose7_rotation_matrix(pose)
        ranked = []
        for direction in diagonal:
            dx, dy = _ellipse_point(half_x, half_y, direction, 1.0)
            world_offset = world_from_obj @ np.asarray([dx, dy, 0.0], dtype=np.float64)
            ranked.append((float(world_offset[1]), direction))
        away_directions = [direction for world_y, direction in sorted(ranked, key=lambda item: item[0]) if world_y < -1e-6]
        directions = away_directions or [direction for _, direction in sorted(ranked, key=lambda item: item[0])[:2]]
        radial_fracs = [0.82]
        yaw_mode = "tangent"
    elif profile == "bowl_rim_diagonal_mixed_topdown_v1":
        directions = diagonal
        yaw_mode = "mixed"
    elif profile == "bowl_rim_cardinal_mixed_topdown_v1":
        directions = cardinal
        yaw_mode = "mixed"
    elif profile == "bowl_rim_tangent_topdown_v1":
        directions = [*cardinal, *diagonal]
        yaw_mode = "tangent"
    else:
        directions = [*cardinal, *diagonal]
        yaw_mode = "radial"

    samples: List[LocalGraspSample] = []
    for z in z_values:
        for frac in radial_fracs:
            for direction in directions:
                dx, dy = _ellipse_point(half_x, half_y, direction, frac)
                theta = float(np.arctan2(dy, dx))
                if yaw_mode == "radial":
                    yaws = [theta, theta + np.pi]
                elif yaw_mode == "tangent":
                    yaws = [theta + 0.5 * np.pi, theta - 0.5 * np.pi]
                else:
                    yaws = [theta, theta + np.pi, theta + 0.5 * np.pi, theta - 0.5 * np.pi]
                for yaw in yaws:
                    samples.append(
                        _sample(
                            dx,
                            dy,
                            z,
                            0.0,
                            0.0,
                            yaw,
                            world_yaw=wrap_yaw_rad(yaw),
                            away_from_open_drawer=profile == "bowl_rim_away_from_open_drawer_topdown_v1",
                            open_drawer_point_id=open_drawer_point_id,
                        )
                    )
    return samples


def _mug_body_side_samples(dims: Iterable[float]) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.10, 0.10, 0.10))
    half_x = max(float(ext[0]) * 0.5, 1e-4)
    half_y = max(float(ext[1]) * 0.5, 1e-4)
    half_height = max(float(ext[2]) * 0.5, 1e-4)
    body_radius = max(0.35 * min(half_x, half_y), 0.018)
    z_values = [max(0.0, half_height - 0.034)]
    inv_sqrt2 = float(1.0 / np.sqrt(2.0))
    directions = [
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
        (inv_sqrt2, inv_sqrt2),
        (-inv_sqrt2, inv_sqrt2),
        (inv_sqrt2, -inv_sqrt2),
        (-inv_sqrt2, -inv_sqrt2),
    ]
    samples: List[LocalGraspSample] = []
    for z in z_values:
        for dx_unit, dy_unit in directions:
            dx = float(body_radius * dx_unit)
            dy = float(body_radius * dy_unit)
            theta = float(np.arctan2(dy, dx))
            for yaw in (theta, theta + 0.5 * np.pi, theta - 0.5 * np.pi):
                samples.append(_sample(dx, dy, z, 0.0, 0.0, yaw, world_yaw=wrap_yaw_rad(yaw)))
    return samples


def _mug_handle_topdown_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
    handle_axis_index: int = 1,
    handle_axis_sign: float = 1.0,
    include_body_side_fallback: bool = False,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.13, 0.18, 0.11))
    half = 0.5 * ext
    half_x = max(float(half[0]), 1e-4)
    half_y = max(float(half[1]), 1e-4)
    half_z = max(float(half[2]), 1e-4)
    handle_axis_index = 0 if int(handle_axis_index) == 0 else 1
    tangent_axis_index = 1 - handle_axis_index
    handle_sign = 1.0 if float(handle_axis_sign) >= 0.0 else -1.0
    world_from_obj = pose7_rotation_matrix(pose)
    tangent_axis = _horizontal_unit(world_from_obj[:, tangent_axis_index], fallback_yaw=0.0)
    handle_axis = handle_sign * _horizontal_unit(
        world_from_obj[:, handle_axis_index],
        fallback_yaw=0.5 * np.pi if handle_axis_index == 1 else 0.0,
    )
    tangent_yaw = float(np.arctan2(float(tangent_axis[1]), float(tangent_axis[0])))
    handle_yaw = float(np.arctan2(float(handle_axis[1]), float(handle_axis[0])))

    handle_half = half_y if handle_axis_index == 1 else half_x
    tangent_half = half_x if handle_axis_index == 1 else half_y
    side_offsets = [0.84 * handle_half, max(0.84 * handle_half, min(0.98 * handle_half, handle_half - 0.002))]
    tangent_jitter = min(0.010, 0.20 * tangent_half)
    tangent_offsets = [0.0, tangent_jitter, -tangent_jitter]
    height = max(float(ext[2]), 1e-4)
    z_offsets = [0.45 * height, 0.60 * height, 0.72 * height]
    yaws = [tangent_yaw, handle_yaw]

    samples: List[LocalGraspSample] = []
    for z_offset in z_offsets:
        for side_offset in side_offsets:
            for tangent_offset in tangent_offsets:
                world_offset = float(tangent_offset) * tangent_axis + float(side_offset) * handle_axis
                world_offset = np.asarray(world_offset, dtype=np.float64).copy()
                world_offset[2] += float(z_offset)
                for yaw in yaws:
                    samples.append(
                        _sample_from_world_offset(
                            world_from_obj,
                            world_offset,
                            yaw,
                            mug_mode="handle_topdown",
                            grasp_intent="handle_only",
                            handle_axis_index=handle_axis_index,
                            handle_axis_sign=handle_sign,
                            handle_side=(
                                f"local_{'positive' if handle_sign > 0.0 else 'negative'}_"
                                f"{'x' if handle_axis_index == 0 else 'y'}"
                            ),
                            handle_side_offset=float(side_offset),
                            handle_tangent_offset=float(tangent_offset),
                            handle_z_offset=float(z_offset),
                            half_x=half_x,
                            half_y=half_y,
                            half_z=half_z,
                        )
                    )
    if include_body_side_fallback:
        for sample in _mug_body_side_samples(dims):
            metadata = dict(sample.metadata)
            metadata["mug_mode"] = "body_side_fallback"
            metadata["grasp_intent"] = "body_side_fallback"
            samples.append(LocalGraspSample(xyz=sample.xyz, rpy=sample.rpy, metadata=metadata))
    return samples


def _moka_pot_handle_topdown_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.08, 0.15, 0.15))
    half = 0.5 * ext
    half_x = max(float(half[0]), 1e-4)
    half_y = max(float(half[1]), 1e-4)
    half_z = max(float(half[2]), 1e-4)
    world_from_obj = pose7_rotation_matrix(pose)
    local_x_axis = _horizontal_unit(world_from_obj[:, 0], fallback_yaw=0.0)
    handle_axis = _horizontal_unit(world_from_obj[:, 1], fallback_yaw=0.5 * np.pi)
    x_yaw = float(np.arctan2(float(local_x_axis[1]), float(local_x_axis[0])))
    yaws = [x_yaw, x_yaw + np.pi]
    x_offsets = [0.0]
    outer_handle_y = max(0.78 * half_y, min(0.96 * half_y, half_y - 0.002))
    y_offsets = [0.78 * half_y, 0.88 * half_y, outer_handle_y]
    z_offsets = [0.38 * half_z, 0.54 * half_z, 0.70 * half_z]

    samples: List[LocalGraspSample] = []
    for z in z_offsets:
        for y in y_offsets:
            for x in x_offsets:
                world_offset = float(x) * local_x_axis + float(y) * handle_axis
                world_offset = np.asarray(world_offset, dtype=np.float64).copy()
                world_offset[2] += float(z)
                for yaw in yaws:
                    samples.append(
                        _sample_from_world_offset(
                            world_from_obj,
                            world_offset,
                            yaw,
                            moka_mode="handle_topdown",
                            grasp_intent="handle_only",
                            handle_side="local_positive_y",
                            handle_y_offset=float(y),
                            handle_z_offset=float(z),
                            half_x=half_x,
                            half_y=half_y,
                            half_z=half_z,
                        )
                    )
    return samples


def _can_body_lower_side_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
    orthogonal_lower: bool = False,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.07, 0.07, 0.08))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    vertical_scores = np.abs(world_from_obj[2, :])
    top_axis = int(np.argmax(vertical_scores))
    horizontal_axes = [idx for idx in range(3) if idx != top_axis]
    body_radius = max(min(float(half[axis]) for axis in horizontal_axes), 0.024)
    if orthogonal_lower:
        z_values = [0.08 * body_radius, 0.22 * body_radius, 0.36 * body_radius]
        lateral = 0.06 * body_radius
        yaw_choices = [0.0, 0.5 * np.pi, np.pi, -0.5 * np.pi]
    else:
        z_values = [0.24 * body_radius, 0.42 * body_radius, 0.60 * body_radius]
        lateral = 0.10 * body_radius
        yaw_choices = [0.0, 0.5 * np.pi, np.pi, -0.5 * np.pi, 0.25 * np.pi, -0.25 * np.pi]
    world_offsets = [(0.0, 0.0), (lateral, 0.0), (-lateral, 0.0), (0.0, lateral), (0.0, -lateral)]

    samples: List[LocalGraspSample] = []
    for z in z_values:
        for dx_world, dy_world in world_offsets:
            world_offset = np.asarray([dx_world, dy_world, z], dtype=np.float64)
            local = world_from_obj.T @ world_offset
            for yaw in yaw_choices:
                object_from_grasp = world_from_obj.T @ rot_z(float(yaw))
                rpy = matrix_to_xyz_rpy(object_from_grasp)
                samples.append(
                    LocalGraspSample(
                        xyz=tuple(local.astype(float).tolist()),
                        rpy=tuple(rpy),
                        metadata={
                            "world_yaw": wrap_yaw_rad(float(yaw)),
                            "top_axis": top_axis,
                            "body_radius": body_radius,
                            "orthogonal_lower": bool(orthogonal_lower),
                        },
                    )
                )
    return samples


def _small_shallow_bowl_rim_samples(dims: Iterable[float]) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.08, 0.08, 0.035))
    half_x = max(float(ext[0]) * 0.5, 1e-4)
    half_y = max(float(ext[1]) * 0.5, 1e-4)
    half_height = max(float(ext[2]) * 0.5, 1e-4)
    z_values = [
        max(0.004, 0.26 * half_height),
        max(0.005, 0.36 * half_height),
    ]
    radial_fracs = [0.58, 0.70]
    inv_sqrt2 = float(1.0 / np.sqrt(2.0))
    directions = [
        (inv_sqrt2, inv_sqrt2),
        (-inv_sqrt2, inv_sqrt2),
        (inv_sqrt2, -inv_sqrt2),
        (-inv_sqrt2, -inv_sqrt2),
    ]

    samples: List[LocalGraspSample] = []
    for z in z_values:
        for frac in radial_fracs:
            for direction in directions:
                dx, dy = _ellipse_point(half_x, half_y, direction, frac)
                theta = float(np.arctan2(dy, dx))
                for yaw in (theta + 0.5 * np.pi, theta - 0.5 * np.pi):
                    samples.append(_sample(dx, dy, z, 0.0, 0.0, yaw, world_yaw=wrap_yaw_rad(yaw)))
    return samples


def _flat_box_topdown_short_side_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
    deep: bool = False,
    book: bool = False,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.035, 0.035, 0.035))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    vertical_scores = np.abs(world_from_obj[2, :])
    top_axis = int(np.argmax(vertical_scores))
    top_sign = 1.0 if float(world_from_obj[2, top_axis]) >= 0.0 else -1.0
    horizontal_axes = [idx for idx in range(3) if idx != top_axis]
    short_axis = min(horizontal_axes, key=lambda idx: float(half[idx]))
    long_axis = max(horizontal_axes, key=lambda idx: float(half[idx]))
    long_world = np.asarray(world_from_obj[:, long_axis], dtype=np.float64)
    if float(np.linalg.norm(long_world[:2])) < 1e-6:
        long_world = np.asarray([1.0, 0.0, 0.0], dtype=np.float64)
    long_yaw = float(np.arctan2(float(long_world[1]), float(long_world[0])))
    yaws = [long_yaw, long_yaw + np.pi, long_yaw + 0.5 * np.pi, long_yaw - 0.5 * np.pi]
    top_half = float(half[top_axis])
    if deep:
        # Keep top-down alignment but close clearly into the body for very thin boxes.
        top_coords = [-0.35 * top_half]
        long_offsets = [0.0, 0.08 * float(half[long_axis]), -0.08 * float(half[long_axis])]
    elif book:
        # Standing book: pinch a few cm below the crown, still above mid-body.
        # Caddy compartments only fit the book when the grasp locks the thin edge;
        # the orthogonal yaw pair lets the planner grab the wide face and fail later.
        yaws = [long_yaw, long_yaw + np.pi]
        top_depths = [0.025, 0.032]
        top_coords = [max(0.20 * top_half, top_half - float(depth)) for depth in top_depths]
        long_offsets = [0.0, 0.22 * float(half[long_axis]), -0.22 * float(half[long_axis])]
    else:
        top_depths = [min(0.004, 0.45 * top_half), min(0.007, 0.70 * top_half)]
        top_coords = [max(0.0, top_half - float(depth)) for depth in top_depths]
        long_offsets = [0.0, 0.22 * float(half[long_axis]), -0.22 * float(half[long_axis])]

    samples: List[LocalGraspSample] = []
    for unsigned_top_coord in top_coords:
        top_coord = top_sign * float(unsigned_top_coord)
        depth_from_top = top_half - float(unsigned_top_coord)
        for long_offset in long_offsets:
            local = np.zeros(3, dtype=np.float64)
            local[top_axis] = top_coord
            local[long_axis] = float(long_offset)
            for yaw in yaws:
                object_from_grasp = world_from_obj.T @ rot_z(yaw)
                rpy = matrix_to_xyz_rpy(object_from_grasp)
                samples.append(
                    LocalGraspSample(
                        xyz=tuple(local.astype(float).tolist()),
                        rpy=tuple(rpy),
                        metadata={
                            "world_yaw": wrap_yaw_rad(float(yaw)),
                            "top_axis": top_axis,
                            "short_axis": short_axis,
                            "long_axis": long_axis,
                            "book_thin_side_only": bool(book),
                            "deep": bool(deep),
                            "depth_from_top": depth_from_top,
                        },
                    )
                )
    return samples


def _carton_body_vertical_deep_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.055, 0.055, 0.13))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    vertical_scores = np.abs(world_from_obj[2, :])
    top_axis = int(np.argmax(vertical_scores))
    top_sign = 1.0 if float(world_from_obj[2, top_axis]) >= 0.0 else -1.0
    horizontal_axes = [idx for idx in range(3) if idx != top_axis]
    short_axis = min(horizontal_axes, key=lambda idx: float(half[idx]))
    long_axis = max(horizontal_axes, key=lambda idx: float(half[idx]))
    long_world = np.asarray(world_from_obj[:, long_axis], dtype=np.float64)
    if float(np.linalg.norm(long_world[:2])) < 1e-6:
        long_world = np.asarray([1.0, 0.0, 0.0], dtype=np.float64)
    long_yaw = float(np.arctan2(float(long_world[1]), float(long_world[0])))
    yaws = [long_yaw, long_yaw + np.pi, long_yaw + 0.5 * np.pi, long_yaw - 0.5 * np.pi]
    top_half = float(half[top_axis])
    top_coords = [0.22 * top_half, 0.02 * top_half, -0.16 * top_half]
    long_offsets = [0.0, 0.12 * float(half[long_axis]), -0.12 * float(half[long_axis])]

    samples: List[LocalGraspSample] = []
    for unsigned_top_coord in top_coords:
        top_coord = top_sign * float(unsigned_top_coord)
        depth_from_top = top_half - float(unsigned_top_coord)
        for long_offset in long_offsets:
            local = np.zeros(3, dtype=np.float64)
            local[top_axis] = top_coord
            local[long_axis] = float(long_offset)
            for yaw in yaws:
                object_from_grasp = world_from_obj.T @ rot_z(yaw)
                rpy = matrix_to_xyz_rpy(object_from_grasp)
                samples.append(
                    LocalGraspSample(
                        xyz=tuple(local.astype(float).tolist()),
                        rpy=tuple(rpy),
                        metadata={
                            "world_yaw": wrap_yaw_rad(float(yaw)),
                            "top_axis": top_axis,
                            "short_axis": short_axis,
                            "long_axis": long_axis,
                            "depth_from_top": depth_from_top,
                        },
                    )
                )
    return samples


def _horizontal_unit(vec: np.ndarray, fallback_yaw: float = 0.0) -> np.ndarray:
    xy = np.asarray([float(vec[0]), float(vec[1]), 0.0], dtype=np.float64)
    norm = float(np.linalg.norm(xy[:2]))
    if norm < 1e-6:
        xy = np.asarray([float(np.cos(fallback_yaw)), float(np.sin(fallback_yaw)), 0.0], dtype=np.float64)
        norm = 1.0
    return xy / norm


def _sample_from_world_offset(
    world_from_obj: np.ndarray,
    world_offset: np.ndarray,
    yaw: float,
    **metadata: Any,
) -> LocalGraspSample:
    local = world_from_obj.T @ np.asarray(world_offset, dtype=np.float64).reshape(3)
    object_from_grasp = world_from_obj.T @ rot_z(float(yaw))
    rpy = matrix_to_xyz_rpy(object_from_grasp)
    return LocalGraspSample(
        xyz=tuple(local.astype(float).tolist()),
        rpy=tuple(rpy),
        metadata={**metadata, "world_yaw": wrap_yaw_rad(float(yaw)), "world_offset": world_offset.astype(float).tolist()},
    )


def _carton_upright_body_side_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.055, 0.055, 0.13))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    height_half = max(float(np.max(half)), 0.045)
    body_half = max(float(np.partition(half, 1)[1]), 0.022)

    # HOPE milk/orange-juice cartons expose their semantic upright axis as
    # local +Y. Use world offsets so world-frame AABBs do not get interpreted
    # as object-frame extents a second time.
    ridge_axis = _horizontal_unit(world_from_obj[:, 2], fallback_yaw=0.0)
    ridge_yaw = float(np.arctan2(float(ridge_axis[1]), float(ridge_axis[0])))
    longitudinal_jitter = 0.10 * body_half
    # The HOPE cartons have a gable ridge near the top. Keep the simple upright
    # body samples, but rotate the gripper 90 degrees away from the ridge-closing
    # orientation so the fingers close on the carton sides instead.
    z_offsets = [
        max(0.0, height_half - 0.028),
        max(0.0, height_half - 0.036),
        max(0.0, height_half - 0.024),
    ]
    xy_offsets = [
        np.zeros(3, dtype=np.float64),
        longitudinal_jitter * ridge_axis,
        -longitudinal_jitter * ridge_axis,
    ]
    yaws = [ridge_yaw, ridge_yaw + np.pi]

    samples: List[LocalGraspSample] = []
    for z_offset in z_offsets:
        for xy_offset in xy_offsets:
            world_offset = np.asarray(xy_offset, dtype=np.float64).copy()
            world_offset[2] += float(z_offset)
            for yaw in yaws:
                samples.append(
                    _sample_from_world_offset(
                        world_from_obj,
                        world_offset,
                        yaw,
                        carton_mode="upright_body_side",
                        carton_grasp_intent="rotated_side_wall_avoid_gable_ridge",
                        height_half=height_half,
                        body_half=body_half,
                        depth_from_top=height_half - float(z_offset),
                        ridge_yaw=wrap_yaw_rad(ridge_yaw),
                    )
                )
    return samples


def _carton_fallen_body_side_samples(
    dims: Iterable[float],
    *,
    pose: Optional[List[float]] = None,
) -> List[LocalGraspSample]:
    ext = _dims3(dims, (0.055, 0.055, 0.13))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    long_half = max(float(np.max(half)), 0.045)
    body_half = max(float(np.partition(half, 1)[1]), 0.022)

    carton_axis = _horizontal_unit(world_from_obj[:, 1], fallback_yaw=0.0)
    long_yaw = float(np.arctan2(float(carton_axis[1]), float(carton_axis[0])))
    yaws = [long_yaw, long_yaw + np.pi, long_yaw + 0.5 * np.pi, long_yaw - 0.5 * np.pi]
    long_offsets = [0.0, 0.18 * long_half, -0.18 * long_half]
    z_offsets = [
        max(0.0, body_half - 0.014),
        max(0.0, body_half - 0.020),
        max(0.0, body_half - 0.026),
    ]

    samples: List[LocalGraspSample] = []
    for z_offset in z_offsets:
        for long_offset in long_offsets:
            world_offset = float(long_offset) * carton_axis
            world_offset = np.asarray(world_offset, dtype=np.float64).copy()
            world_offset[2] += float(z_offset)
            for yaw in yaws:
                samples.append(
                    _sample_from_world_offset(
                        world_from_obj,
                        world_offset,
                        yaw,
                        carton_mode="fallen_body_side",
                        long_half=long_half,
                        body_half=body_half,
                        depth_from_top=body_half - float(z_offset),
                    )
                )
    return samples


def sample_grasp_profile(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool,
    pose: Optional[List[float]] = None,
) -> List[LocalGraspSample]:
    normalized = normalize_grasp_sampler_profile(profile)
    if normalized in MUG_BODY_GRASP_SAMPLER_PROFILES:
        return _mug_body_side_samples(dims)
    if normalized in MUG_HANDLE_GRASP_SAMPLER_PROFILES:
        handle_axis_index = 1
        handle_axis_sign = 1.0
        if "local_pos_x" in normalized:
            handle_axis_index = 0
            handle_axis_sign = 1.0
        elif "local_neg_x" in normalized:
            handle_axis_index = 0
            handle_axis_sign = -1.0
        return _mug_handle_topdown_samples(
            dims,
            pose=pose,
            handle_axis_index=handle_axis_index,
            handle_axis_sign=handle_axis_sign,
            include_body_side_fallback=normalized.endswith("_then_body_side_v1"),
        )
    if normalized in MOKA_POT_HANDLE_GRASP_SAMPLER_PROFILES:
        return _moka_pot_handle_topdown_samples(dims, pose=pose)
    if normalized in CAN_BODY_GRASP_SAMPLER_PROFILES:
        return _can_body_lower_side_samples(
            dims,
            pose=pose,
            orthogonal_lower=normalized == "can_body_orthogonal_lower_side_v1",
        )
    if normalized == "carton_upright_body_side_v1":
        return _carton_upright_body_side_samples(dims, pose=pose)
    if normalized == "carton_fallen_body_side_v1":
        return _carton_fallen_body_side_samples(dims, pose=pose)
    if normalized in CARTON_BODY_GRASP_SAMPLER_PROFILES:
        return _carton_body_vertical_deep_samples(dims, pose=pose)
    if normalized in SMALL_SHALLOW_BOWL_GRASP_SAMPLER_PROFILES:
        return _small_shallow_bowl_rim_samples(dims)
    if normalized in FLAT_BOX_GRASP_SAMPLER_PROFILES:
        return _flat_box_topdown_short_side_samples(
            dims,
            pose=pose,
            deep=normalized == "flat_box_topdown_short_side_deep_v1",
            book=normalized == "flat_box_topdown_short_side_book_v1",
        )
    if normalized in BOWL_RIM_GRASP_SAMPLER_PROFILES and rim:
        return _bowl_rim_samples(normalized, dims, pose=pose)
    if normalized in TOPDOWN_GRASP_SAMPLER_PROFILES:
        return _topdown_samples(dims, rim=rim)
    raise ValueError(f"grasp sampler profile does not provide top-down samples: {normalized}")


def sample_grasp_profile_xyzrpy(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool,
    pose: Optional[List[float]] = None,
) -> List[List[float]]:
    return [sample.xyzrpy() for sample in sample_grasp_profile(profile, dims, rim=rim, pose=pose)]


def profile_gripper_width(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool = False,
    radius: Optional[float] = None,
    pose: Optional[List[float]] = None,
) -> float:
    normalized = normalize_grasp_sampler_profile(profile)
    ext = _dims3(dims, (0.06, 0.06, 0.04))
    half = 0.5 * ext
    if normalized in MUG_BODY_GRASP_SAMPLER_PROFILES:
        body_radius = max(0.35 * min(float(half[0]), float(half[1])), 0.018)
        return float(np.clip(2.0 * body_radius, 0.025, 0.075))
    if normalized in MUG_HANDLE_GRASP_SAMPLER_PROFILES:
        return float(np.clip(0.76 * min(float(half[0]), float(half[1])), 0.030, 0.046))
    if normalized in MOKA_POT_HANDLE_GRASP_SAMPLER_PROFILES:
        return float(np.clip(0.86 * min(float(half[0]), float(half[1])), 0.030, 0.040))
    if normalized in SMALL_SHALLOW_BOWL_GRASP_SAMPLER_PROFILES:
        return float(np.clip(1.65 * min(float(half[0]), float(half[1])), 0.025, 0.070))
    if normalized in FLAT_BOX_GRASP_SAMPLER_PROFILES:
        world_from_obj = pose7_rotation_matrix(pose)
        top_axis = int(np.argmax(np.abs(world_from_obj[2, :])))
        horizontal_axes = [idx for idx in range(3) if idx != top_axis]
        short_half = min(float(half[axis]) for axis in horizontal_axes)
        return float(np.clip(2.25 * short_half, 0.025, 0.075))
    if normalized == "carton_upright_body_side_v1":
        short_half = min(float(value) for value in half)
        return float(np.clip(2.55 * short_half, 0.060, 0.078))
    if normalized == "carton_fallen_body_side_v1":
        short_half = min(float(value) for value in half)
        return float(np.clip(2.35 * short_half, 0.052, 0.078))
    if normalized in CARTON_BODY_GRASP_SAMPLER_PROFILES:
        world_from_obj = pose7_rotation_matrix(pose)
        top_axis = int(np.argmax(np.abs(world_from_obj[2, :])))
        horizontal_axes = [idx for idx in range(3) if idx != top_axis]
        short_half = min(float(half[axis]) for axis in horizontal_axes)
        return float(np.clip(2.12 * short_half, 0.035, 0.078))
    if normalized in CAN_BODY_GRASP_SAMPLER_PROFILES:
        world_from_obj = pose7_rotation_matrix(pose)
        top_axis = int(np.argmax(np.abs(world_from_obj[2, :])))
        horizontal_axes = [idx for idx in range(3) if idx != top_axis]
        body_radius = max(min(float(half[axis]) for axis in horizontal_axes), 0.024)
        return float(np.clip(2.15 * body_radius, 0.040, 0.078))
    if normalized in BOWL_RIM_GRASP_SAMPLER_PROFILES or rim:
        return float(np.clip(1.80 * min(float(half[0]), float(half[1])), 0.025, 0.085))
    fallback_radius = max(float(radius or 0.0), max(float(half[0]), float(half[1])))
    return float(np.clip(2.2 * fallback_radius, 0.025, 0.085))
