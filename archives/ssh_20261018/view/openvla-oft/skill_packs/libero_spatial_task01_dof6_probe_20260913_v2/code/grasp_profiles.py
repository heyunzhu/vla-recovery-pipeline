"""Task-local grasp profiles for LIBERO spatial task01 mining."""

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
from skill_packs.libero90_legacy.code.grasp_profiles import (
    profile_gripper_width as _legacy_profile_gripper_width,
)
from skill_packs.libero90_legacy.code.grasp_profiles import (
    sample_grasp_profile as _legacy_sample_grasp_profile,
)

ADAPTER_NAME = "libero_spatial_task01_grasp_profiles"
PROFILE_IDS = frozenset(
    {
        "task01_black_bowl_inward_diagonal_rim_v1",
        "task01_black_bowl_stable_outer_topdown_v2",
        "task01_black_bowl_low_rim_contact_v3",
        "bowl_rim_diagonal_mixed_topdown_v1",
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


def _radial_close_yaw(radial_world_xy: np.ndarray) -> float:
    vec = np.asarray(radial_world_xy, dtype=np.float64).reshape(2)
    norm = float(np.linalg.norm(vec))
    if norm < 1e-8:
        vec = np.asarray([1.0, 0.0], dtype=np.float64)
    else:
        vec = vec / norm
    return wrap_yaw_rad(float(np.arctan2(float(vec[0]), -float(vec[1]))))


def _sample(local: np.ndarray, world_yaw: float, world_from_obj: np.ndarray, **metadata) -> LocalGraspSample:
    object_from_grasp = world_from_obj.T @ rot_z(float(world_yaw))
    return LocalGraspSample(
        xyz=tuple(float(x) for x in local.tolist()),
        rpy=tuple(matrix_to_xyz_rpy(object_from_grasp)),
        metadata={"world_yaw": wrap_yaw_rad(world_yaw), **metadata},
    )


def _black_bowl_inward_diagonal_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None,
) -> list[LocalGraspSample]:
    ext = _dims3(dims, (0.107, 0.107, 0.051))
    half = 0.5 * ext
    half_x = float(half[0])
    half_y = float(half[1])
    half_z = float(half[2])
    world_from_obj = pose7_rotation_matrix(pose)

    diagonal_dirs = [
        np.asarray([1.0, 1.0, 0.0], dtype=np.float64),
        np.asarray([1.0, -1.0, 0.0], dtype=np.float64),
        np.asarray([-1.0, 1.0, 0.0], dtype=np.float64),
        np.asarray([-1.0, -1.0, 0.0], dtype=np.float64),
    ]
    cardinal_dirs = [
        np.asarray([1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([-1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([0.0, 1.0, 0.0], dtype=np.float64),
        np.asarray([0.0, -1.0, 0.0], dtype=np.float64),
    ]
    z_values = [
        max(0.0035, half_z - 0.021),
        max(0.0015, half_z - 0.024),
    ]

    samples: list[LocalGraspSample] = []
    for group, dirs, frac_values in (
        ("diagonal_inward", diagonal_dirs, (0.58, 0.66)),
        ("cardinal_inward_fallback", cardinal_dirs, (0.56,)),
    ):
        for direction in dirs:
            direction = direction / max(float(np.linalg.norm(direction[:2])), 1e-8)
            radial_world = world_from_obj @ direction
            base_yaw = _radial_close_yaw(radial_world[:2])
            yaw_offsets = (0.0, np.deg2rad(8.0), -np.deg2rad(8.0)) if group == "diagonal_inward" else (0.0,)
            for frac in frac_values:
                local = np.asarray(
                    [frac * half_x * float(direction[0]), frac * half_y * float(direction[1]), 0.0],
                    dtype=np.float64,
                )
                for z in z_values:
                    local[2] = float(z)
                    for yaw_offset in yaw_offsets:
                        samples.append(
                            _sample(
                                local.copy(),
                                base_yaw + float(yaw_offset),
                                world_from_obj,
                                profile="task01_black_bowl_inward_diagonal_rim_v1",
                                family=group,
                                radius_fraction=float(frac),
                                z_from_center=float(z),
                                yaw_offset_rad=float(yaw_offset),
                            )
                        )
    return samples


def _black_bowl_stable_outer_topdown_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None,
) -> list[LocalGraspSample]:
    ext = _dims3(dims, (0.107, 0.107, 0.051))
    half = 0.5 * ext
    half_x = float(half[0])
    half_y = float(half[1])
    half_z = float(half[2])
    world_from_obj = pose7_rotation_matrix(pose)

    rim_dirs = [
        np.asarray([1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([-1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([0.0, 1.0, 0.0], dtype=np.float64),
        np.asarray([0.0, -1.0, 0.0], dtype=np.float64),
    ]
    yaw_choices = [
        0.0,
        0.5 * np.pi,
        np.pi,
        -0.5 * np.pi,
        0.25 * np.pi,
        -0.25 * np.pi,
        0.75 * np.pi,
        -0.75 * np.pi,
    ]
    z_values = [
        max(0.006, half_z - 0.012),
        max(0.004, half_z - 0.018),
    ]

    samples: list[LocalGraspSample] = []
    for direction in rim_dirs:
        local = np.asarray(
            [0.82 * half_x * float(direction[0]), 0.82 * half_y * float(direction[1]), 0.0],
            dtype=np.float64,
        )
        radial_world = world_from_obj @ direction
        radial_yaw = _radial_close_yaw(radial_world[:2])
        for z in z_values:
            local[2] = float(z)
            for yaw in yaw_choices:
                samples.append(
                    _sample(
                        local.copy(),
                        float(yaw),
                        world_from_obj,
                        profile="task01_black_bowl_stable_outer_topdown_v2",
                        family="stable_outer_topdown",
                        radius_fraction=0.82,
                        z_from_center=float(z),
                        world_yaw_choice=float(yaw),
                        radial_reference_yaw=float(radial_yaw),
                    )
                )
    return samples


def _black_bowl_low_rim_contact_samples(
    dims: Iterable[float],
    *,
    pose: list[float] | None,
) -> list[LocalGraspSample]:
    ext = _dims3(dims, (0.107, 0.107, 0.051))
    half = 0.5 * ext
    half_x = float(half[0])
    half_y = float(half[1])
    half_z = float(half[2])
    world_from_obj = pose7_rotation_matrix(pose)

    rim_dirs = [
        np.asarray([1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([-1.0, 0.0, 0.0], dtype=np.float64),
        np.asarray([0.0, 1.0, 0.0], dtype=np.float64),
        np.asarray([0.0, -1.0, 0.0], dtype=np.float64),
    ]
    yaw_choices = [
        0.0,
        0.5 * np.pi,
        np.pi,
        -0.5 * np.pi,
        0.25 * np.pi,
        -0.25 * np.pi,
        0.75 * np.pi,
        -0.75 * np.pi,
    ]
    z_values = [
        max(0.003, half_z - 0.020),
        max(0.0015, half_z - 0.024),
    ]

    samples: list[LocalGraspSample] = []
    for direction in rim_dirs:
        local = np.asarray(
            [0.82 * half_x * float(direction[0]), 0.82 * half_y * float(direction[1]), 0.0],
            dtype=np.float64,
        )
        radial_world = world_from_obj @ direction
        radial_yaw = _radial_close_yaw(radial_world[:2])
        for z in z_values:
            local[2] = float(z)
            for yaw in yaw_choices:
                samples.append(
                    _sample(
                        local.copy(),
                        float(yaw),
                        world_from_obj,
                        profile="task01_black_bowl_low_rim_contact_v3",
                        family="low_rim_contact",
                        radius_fraction=0.82,
                        z_from_center=float(z),
                        world_yaw_choice=float(yaw),
                        radial_reference_yaw=float(radial_yaw),
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
    name = str(profile)
    if name == "task01_black_bowl_inward_diagonal_rim_v1":
        return _black_bowl_inward_diagonal_samples(dims, pose=pose)
    if name == "task01_black_bowl_stable_outer_topdown_v2":
        return _black_bowl_stable_outer_topdown_samples(dims, pose=pose)
    if name == "task01_black_bowl_low_rim_contact_v3":
        return _black_bowl_low_rim_contact_samples(dims, pose=pose)
    if name == "bowl_rim_diagonal_mixed_topdown_v1":
        return _legacy_sample_grasp_profile(name, dims, rim=True, pose=pose)
    raise ValueError(f"unknown task01 grasp profile: {profile}")


def profile_gripper_width(
    profile: str,
    dims: Iterable[float],
    *,
    rim: bool = False,
    radius: float | None = None,
    pose: list[float] | None = None,
) -> float:
    name = str(profile)
    if name == "bowl_rim_diagonal_mixed_topdown_v1":
        return _legacy_profile_gripper_width(name, dims, rim=True, radius=radius, pose=pose)
    if name not in PROFILE_IDS:
        raise ValueError(f"unknown task01 grasp profile: {profile}")
    ext = _dims3(dims, (0.107, 0.107, 0.051))
    short_half = 0.5 * min(float(ext[0]), float(ext[1]))
    if name in {"task01_black_bowl_stable_outer_topdown_v2", "task01_black_bowl_low_rim_contact_v3"}:
        return float(np.clip(1.42 * short_half, 0.058, 0.078))
    return float(np.clip(1.25 * short_half, 0.048, 0.070))
