"""Task-local grasp profiles for LIBERO-PRO goal-task mining."""

from __future__ import annotations

from typing import Iterable

import numpy as np

from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    LocalGraspSample,
    matrix_to_xyz_rpy,
    pose7_rotation_matrix,
    rot_z,
    wrap_yaw_rad,
)

ADAPTER_NAME = "libero_goal_task_grasp_profiles"
PROFILE_IDS = frozenset(
    {
        "cream_cheese_flat_box_topdown_deep_v1",
        "plate_rim_edge_topdown_v1",
        "carton_upright_body_side_v1",
    }
)


def _dims3(dims: Iterable[float], default: tuple[float, float, float]) -> np.ndarray:
    arr = np.asarray(list(dims), dtype=np.float64).reshape(-1)
    if arr.size < 3:
        arr = np.pad(arr, (0, 3 - arr.size), constant_values=0.0)
    arr = arr[:3]
    fallback = np.asarray(default, dtype=np.float64)
    arr = np.where(np.abs(arr) > 1e-9, arr, fallback)
    return np.maximum(arr, 1e-4)


def _flat_box_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None = None,
) -> list[LocalGraspSample]:
    ext = _dims3(dims, (0.080, 0.055, 0.020))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    vertical_scores = np.abs(world_from_obj[2, :])
    top_axis = int(np.argmax(vertical_scores))
    top_sign = 1.0 if float(world_from_obj[2, top_axis]) >= 0.0 else -1.0
    horizontal_axes = [idx for idx in range(3) if idx != top_axis]
    long_axis = max(horizontal_axes, key=lambda idx: float(half[idx]))
    long_world = np.asarray(world_from_obj[:, long_axis], dtype=np.float64)
    if float(np.linalg.norm(long_world[:2])) < 1e-6:
        long_world = np.asarray([1.0, 0.0, 0.0], dtype=np.float64)
    long_yaw = float(np.arctan2(float(long_world[1]), float(long_world[0])))

    top_half = float(half[top_axis])
    top_coords = [-0.35 * top_half, -0.15 * top_half]
    long_offsets = [0.0, 0.08 * float(half[long_axis]), -0.08 * float(half[long_axis])]
    yaws = [long_yaw, long_yaw + np.pi, long_yaw + 0.5 * np.pi, long_yaw - 0.5 * np.pi]

    samples: list[LocalGraspSample] = []
    for unsigned_top_coord in top_coords:
        local = np.zeros(3, dtype=np.float64)
        local[top_axis] = top_sign * float(unsigned_top_coord)
        depth_from_top = top_half - float(unsigned_top_coord)
        for long_offset in long_offsets:
            local[long_axis] = float(long_offset)
            for yaw in yaws:
                object_from_grasp = world_from_obj.T @ rot_z(float(yaw))
                samples.append(
                    LocalGraspSample(
                        xyz=tuple(local.astype(float).tolist()),
                        rpy=tuple(matrix_to_xyz_rpy(object_from_grasp)),
                        metadata={
                            "world_yaw": wrap_yaw_rad(float(yaw)),
                            "top_axis": top_axis,
                            "long_axis": long_axis,
                            "depth_from_top": float(depth_from_top),
                            "profile": "cream_cheese_flat_box_topdown_deep_v1",
                        },
                    )
                )
    return samples


def _ellipse_point(half_x: float, half_y: float, direction: tuple[float, float], frac: float) -> tuple[float, float]:
    dx, dy = direction
    norm = max((dx * dx + dy * dy) ** 0.5, 1e-9)
    ux = float(dx) / norm
    uy = float(dy) / norm
    denom = ((ux / max(half_x, 1e-6)) ** 2 + (uy / max(half_y, 1e-6)) ** 2) ** 0.5
    scale = float(frac) / max(denom, 1e-9)
    return ux * scale, uy * scale


def _plate_rim_edge_topdown_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None = None,
) -> list[LocalGraspSample]:
    ext = _dims3(dims, (0.140, 0.140, 0.020))
    half = 0.5 * ext
    half_x = max(float(half[0]), 1e-4)
    half_y = max(float(half[1]), 1e-4)
    half_height = max(float(half[2]), 1e-4)
    world_from_obj = pose7_rotation_matrix(pose)

    z_values = [
        max(0.0, 0.20 * half_height),
        max(0.0, 0.45 * half_height),
    ]
    radial_fracs = [0.78, 0.88]
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

    samples: list[LocalGraspSample] = []
    for z in z_values:
        for frac in radial_fracs:
            for direction in directions:
                dx, dy = _ellipse_point(half_x, half_y, direction, frac)
                local = np.asarray([dx, dy, z], dtype=np.float64)
                world_dir = np.asarray(world_from_obj[:, :2] @ np.asarray([dx, dy], dtype=np.float64), dtype=np.float64)
                if float(np.linalg.norm(world_dir[:2])) < 1e-6:
                    theta = float(np.arctan2(dy, dx))
                else:
                    theta = float(np.arctan2(float(world_dir[1]), float(world_dir[0])))
                # Radial and tangent yaw choices both keep the gripper top-down while
                # letting cuTAMP choose whether the fingers straddle or slide along the rim.
                for yaw in (theta, theta + np.pi, theta + 0.5 * np.pi, theta - 0.5 * np.pi):
                    object_from_grasp = world_from_obj.T @ rot_z(float(yaw))
                    samples.append(
                        LocalGraspSample(
                            xyz=tuple(local.astype(float).tolist()),
                            rpy=tuple(matrix_to_xyz_rpy(object_from_grasp)),
                            metadata={
                                "world_yaw": wrap_yaw_rad(float(yaw)),
                                "radial_fraction": float(frac),
                                "rim_direction": [float(direction[0]), float(direction[1])],
                                "profile": "plate_rim_edge_topdown_v1",
                            },
                        )
                    )
    return samples


CARTON_PROFILE = "carton_upright_body_side_v1"

# Height bands as a fraction of the object's total height, measured from the table.
# The milk / orange-juice carton body is 0.1095 m of its 0.1312 m (body top = 83.4%), and the
# gable roof above it narrows to a 5.9 mm ridge, so every band must stay at or below ~0.82.
# Swept on dev seeds 51-65 (four arms, both axes, 60 episodes each): 0.70 -> 7/60 with planner
# infeasibility as the dominant failure, 0.75 -> 52/60, 0.80 -> 60/60, while the generic sampler
# managed 18/40 on the same seeds. 0.80 is therefore the admitted constant.
CARTON_GRASP_HEIGHT_FRACTIONS: tuple[float, ...] = (0.80,)
# closing axis runs along the object's x axis, which is the direction of the gable ridge;
# 0 and pi place the same finger pair with opposite wrist roll, giving cuTAMP an IK alternative.
CARTON_GRASP_YAWS: tuple[float, ...] = (0.0, np.pi)


def _carton_body_side_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None = None,
) -> list[LocalGraspSample]:
    """Top-down samples on the flat body sides of an upright gable-top carton.

    Grasps explicitly avoid the roof: the samples sit at ``CARTON_GRASP_HEIGHT_FRACTIONS`` of the
    object height, and the fingers close along the object's x axis (parallel to the ridge), so they
    clamp the two flat side faces that run up to the eaves.
    """
    ext = _dims3(dims, (0.0525, 0.0531, 0.1312))
    height = float(ext[2])
    half_height = 0.5 * height
    samples: list[LocalGraspSample] = []
    for fraction in CARTON_GRASP_HEIGHT_FRACTIONS:
        z_local = float(fraction) * height - half_height
        for yaw in CARTON_GRASP_YAWS:
            samples.append(
                LocalGraspSample(
                    xyz=(0.0, 0.0, z_local),
                    rpy=(0.0, 0.0, wrap_yaw_rad(float(yaw))),
                    metadata={
                        "profile": CARTON_PROFILE,
                        "height_fraction": float(fraction),
                        "height_above_table_m": float(fraction) * height,
                        "body_top_m": 0.834 * height,
                        "closing_axis": "object_x_parallel_to_ridge",
                    },
                )
            )
    return samples


def sample_grasp_profile(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool = False,
    pose: list[float] | None = None,
) -> list[LocalGraspSample]:
    normalized = str(profile)
    if normalized == "cream_cheese_flat_box_topdown_deep_v1":
        return _flat_box_samples(dims, pose=pose)
    if normalized == "plate_rim_edge_topdown_v1":
        return _plate_rim_edge_topdown_samples(dims, pose=pose)
    if normalized == CARTON_PROFILE:
        return _carton_body_side_samples(dims, pose=pose)
    raise ValueError(f"unknown LIBERO-PRO goal-task grasp profile: {profile}")


def profile_gripper_width(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool = False,
    radius: float | None = None,
    pose: list[float] | None = None,
) -> float:
    normalized = str(profile)
    ext = _dims3(dims, (0.080, 0.055, 0.020))
    if normalized == "plate_rim_edge_topdown_v1":
        rim_width = max(float(ext[2]) * 2.2, 0.035)
        return float(np.clip(rim_width, 0.035, 0.060))
    if normalized == CARTON_PROFILE:
        # body cross-section is square; leave a couple of millimetres of clearance per side
        body_short_side = min(float(ext[0]), float(ext[1]))
        return float(np.clip(body_short_side + 0.006, 0.030, 0.080))
    if normalized != "cream_cheese_flat_box_topdown_deep_v1":
        raise ValueError(f"unknown LIBERO-PRO goal-task grasp profile: {profile}")
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)
    top_axis = int(np.argmax(np.abs(world_from_obj[2, :])))
    horizontal_axes = [idx for idx in range(3) if idx != top_axis]
    short_half = min(float(half[axis]) for axis in horizontal_axes)
    return float(np.clip(2.25 * short_half, 0.025, 0.075))
