"""Sensor-only bridge from LIBERO / robosuite observations to RGB-D input.

Only this adapter may inspect ``env.sim`` for camera calibration, depth near /
far planes, and simulation time. No scene object, geom, site, contact, goal or
success data crosses the returned observation boundary.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from .rgbd_observation import REQUIRED_ROBOT_STATE_KEYS, ROBOT_STATE_KEYS, RGBDObservation


def _robot_state(obs: Mapping[str, Any]) -> dict[str, Any]:
    missing = REQUIRED_ROBOT_STATE_KEYS - obs.keys()
    if missing:
        raise ValueError("missing robot proprioception: " + ", ".join(sorted(missing)))
    result: dict[str, Any] = {}
    for key in sorted(ROBOT_STATE_KEYS & obs.keys()):
        value = np.asarray(obs[key], dtype=np.float64)
        if not np.isfinite(value).all():
            raise ValueError(f"nonfinite robot proprioception: {key}")
        result[key] = value.reshape(-1).astype(float).tolist()
    return result


def capture_libero_rgbd(
    env: Any,
    obs: Mapping[str, Any],
    *,
    episode_id: str,
    env_step: int,
    camera_id: str,
) -> RGBDObservation:
    """Capture an already-rendered RGB-D pair without advancing simulation.

    This is designed for LIBERO's robosuite 1.4.1 wrapper. The installed
    version must be checked before using it with another simulator build.
    """

    import robosuite
    from robosuite import macros
    from robosuite.utils.camera_utils import (
        get_camera_extrinsic_matrix,
        get_camera_intrinsic_matrix,
        get_real_depth_map,
    )

    if robosuite.__version__ != "1.4.1":
        raise RuntimeError(f"unverified robosuite version: {robosuite.__version__}")
    convention = str(macros.IMAGE_CONVENTION)
    if convention not in {"opengl", "opencv"}:
        raise ValueError(f"unsupported robosuite image convention: {convention}")
    rgb_key, depth_key = f"{camera_id}_image", f"{camera_id}_depth"
    if rgb_key not in obs or depth_key not in obs:
        raise ValueError(f"camera {camera_id!r} has no synchronized RGB and depth observation")

    rgb = np.asarray(obs[rgb_key])
    raw_depth = np.asarray(obs[depth_key], dtype=np.float64)
    if raw_depth.ndim == 3 and raw_depth.shape[2] == 1:
        raw_depth = raw_depth[:, :, 0]
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8 or raw_depth.shape != rgb.shape[:2]:
        raise ValueError(f"camera {camera_id!r} requires aligned uint8 RGB and depth")
    if not np.isfinite(raw_depth).all() or np.any((raw_depth < 0.0) | (raw_depth > 1.0)):
        raise ValueError("robosuite depth must be a finite normalized buffer in [0, 1]")

    sim = env.sim
    height, width = raw_depth.shape
    K = get_camera_intrinsic_matrix(sim, camera_id, height, width)
    T_world_camera = get_camera_extrinsic_matrix(sim, camera_id)
    depth_m = np.asarray(get_real_depth_map(sim, raw_depth), dtype=np.float32)
    # Depth-buffer 1.0 is the far plane, not an observed surface.
    depth_valid = (raw_depth < 1.0) & np.isfinite(depth_m) & (depth_m > 0.0)
    depth_m = np.where(depth_valid, depth_m, np.nan).astype(np.float32)

    if convention == "opengl":
        rgb = rgb[::-1, :, :]
        depth_m = depth_m[::-1, :]
        depth_valid = depth_valid[::-1, :]
    return RGBDObservation(
        episode_id=episode_id,
        env_step=env_step,
        timestamp_s=float(sim.data.time),
        camera_id=camera_id,
        rgb=np.ascontiguousarray(rgb, dtype=np.uint8),
        depth_m=np.ascontiguousarray(depth_m),
        depth_valid=np.ascontiguousarray(depth_valid),
        K=K,
        T_world_camera=T_world_camera,
        robot_state=_robot_state(obs),
        calibration_version=f"robosuite-{robosuite.__version__}-{convention}-camera-utils-v1",
    )
