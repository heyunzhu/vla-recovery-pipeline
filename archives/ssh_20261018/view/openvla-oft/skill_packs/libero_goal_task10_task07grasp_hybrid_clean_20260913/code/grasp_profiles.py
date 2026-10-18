"""Task-local grasp profiles for LIBERO-PRO goal-swap task07 mining."""

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

ADAPTER_NAME = "libero_goal_swap_task07_grasp_profiles"
TASK07_PROFILE_ID = "cream_cheese_flat_box_topdown_deep_v1"
LEVEL_PROFILE_ID = "cream_cheese_flat_box_level_topdown_v1"
PROFILE_IDS = frozenset({TASK07_PROFILE_ID, LEVEL_PROFILE_ID})


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
                            "profile": TASK07_PROFILE_ID,
                        },
                    )
                )
    return samples


def _level_topdown_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None = None,
) -> list[LocalGraspSample]:
    """Cream-cheese flat-box grasps with a level world-frame top-down wrist.

    The task07 profile inferred the top axis from the object pose. In task10 the
    cream-cheese collision cuboid is the useful frame: its thinnest dimension is
    the package thickness. This profile anchors offsets to that thin axis and
    keeps the final grasp orientation to world-yaw-only rotations.
    """

    ext = _dims3(dims, (0.080, 0.055, 0.020))
    half = 0.5 * ext
    world_from_obj = pose7_rotation_matrix(pose)

    thin_axis = int(np.argmin(half))
    planar_axes = [idx for idx in range(3) if idx != thin_axis]
    long_axis = max(planar_axes, key=lambda idx: float(half[idx]))
    short_axis = min(planar_axes, key=lambda idx: float(half[idx]))

    thin_world = np.asarray(world_from_obj[:, thin_axis], dtype=np.float64)
    top_sign = 1.0 if float(thin_world[2]) >= 0.0 else -1.0

    long_world = np.asarray(world_from_obj[:, long_axis], dtype=np.float64)
    if float(np.linalg.norm(long_world[:2])) < 1e-6:
        long_world = np.asarray([1.0, 0.0, 0.0], dtype=np.float64)
    long_yaw = float(np.arctan2(float(long_world[1]), float(long_world[0])))

    thin_half = float(half[thin_axis])
    depth_fracs = [1.15, 1.35]
    long_offsets = [0.0, 0.06 * float(half[long_axis]), -0.06 * float(half[long_axis])]
    short_offsets = [0.0, 0.12 * float(half[short_axis]), -0.12 * float(half[short_axis])]
    yaws = [long_yaw, long_yaw + np.pi]

    samples: list[LocalGraspSample] = []
    for depth_frac in depth_fracs:
        depth_from_top = float(depth_frac * thin_half)
        local_thin = top_sign * float(thin_half - depth_from_top)
        for long_offset in long_offsets:
            for short_offset in short_offsets:
                local = np.zeros(3, dtype=np.float64)
                local[thin_axis] = local_thin
                local[long_axis] = float(long_offset)
                local[short_axis] = float(short_offset)
                for yaw in yaws:
                    object_from_grasp = world_from_obj.T @ rot_z(float(yaw))
                    world_from_grasp = world_from_obj @ object_from_grasp
                    finger_axis_z_abs = max(
                        abs(float(world_from_grasp[2, 0])),
                        abs(float(world_from_grasp[2, 1])),
                    )
                    approach_axis_z_abs = abs(float(world_from_grasp[2, 2]))
                    if finger_axis_z_abs > 1e-6 or approach_axis_z_abs < 1.0 - 1e-6:
                        continue
                    samples.append(
                        LocalGraspSample(
                            xyz=tuple(local.astype(float).tolist()),
                            rpy=tuple(matrix_to_xyz_rpy(object_from_grasp)),
                            metadata={
                                "world_yaw": wrap_yaw_rad(float(yaw)),
                                "thin_axis": thin_axis,
                                "top_axis": thin_axis,
                                "long_axis": long_axis,
                                "short_axis": short_axis,
                                "depth_from_top": depth_from_top,
                                "finger_axis_z_abs": float(finger_axis_z_abs),
                                "approach_axis_z_abs": float(approach_axis_z_abs),
                                "wrist_roll_abs": 0.0,
                                "level_topdown": True,
                                "profile": LEVEL_PROFILE_ID,
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
    profile_id = str(profile)
    if profile_id == TASK07_PROFILE_ID:
        return _flat_box_samples(dims, pose=pose)
    if profile_id == LEVEL_PROFILE_ID:
        return _level_topdown_samples(dims, pose=pose)
    else:
        raise ValueError(f"unknown task07 grasp profile: {profile}")


def profile_gripper_width(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool = False,
    radius: float | None = None,
    pose: list[float] | None = None,
) -> float:
    profile_id = str(profile)
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"unknown task07 grasp profile: {profile}")
    ext = _dims3(dims, (0.080, 0.055, 0.020))
    half = 0.5 * ext
    if profile_id == LEVEL_PROFILE_ID:
        thin_axis = int(np.argmin(half))
        horizontal_axes = [idx for idx in range(3) if idx != thin_axis]
    else:
        world_from_obj = pose7_rotation_matrix(pose)
        top_axis = int(np.argmax(np.abs(world_from_obj[2, :])))
        horizontal_axes = [idx for idx in range(3) if idx != top_axis]
    short_half = min(float(half[axis]) for axis in horizontal_axes)
    return float(np.clip(2.25 * short_half, 0.025, 0.075))
