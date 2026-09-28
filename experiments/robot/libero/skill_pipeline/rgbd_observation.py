"""Replayable, calibrated RGB-D input for visual recovery.

This module deliberately accepts arrays and robot proprioception, never an
environment or simulator handle.  A simulator-specific sensor adapter must
convert depth to optical-Z meters and align image orientation before creating
an observation here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np


SCHEMA_VERSION = 2
ROBOT_STATE_KEYS = frozenset(
    {
        "robot0_joint_pos",
        "robot0_joint_vel",
        "robot0_gripper_qpos",
        "robot0_eef_pos",
        "robot0_eef_quat",
        "gripper_command",
    }
)
REQUIRED_ROBOT_STATE_KEYS = frozenset(
    {"robot0_joint_pos", "robot0_gripper_qpos", "robot0_eef_pos", "robot0_eef_quat"}
)


@dataclass(frozen=True)
class RGBDObservation:
    episode_id: str
    env_step: int
    timestamp_s: float
    camera_id: str
    rgb: np.ndarray
    depth_m: np.ndarray
    depth_valid: np.ndarray
    K: np.ndarray
    T_world_camera: np.ndarray
    robot_state: Mapping[str, Any]
    calibration_version: str

    def __post_init__(self) -> None:
        rgb = np.asarray(self.rgb)
        depth = np.asarray(self.depth_m)
        valid = np.asarray(self.depth_valid)
        K = np.asarray(self.K, dtype=np.float64)
        transform = np.asarray(self.T_world_camera, dtype=np.float64)
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError("rgb must be uint8[H,W,3]")
        if depth.shape != rgb.shape[:2] or depth.dtype != np.float32:
            raise ValueError("depth_m must be float32[H,W] aligned with rgb")
        if valid.shape != depth.shape or valid.dtype != np.bool_:
            raise ValueError("depth_valid must be bool[H,W] aligned with depth_m")
        if np.any(valid & (~np.isfinite(depth) | (depth <= 0))):
            raise ValueError("valid depth must be finite optical-Z meters greater than zero")
        if K.shape != (3, 3) or not np.isfinite(K).all() or K[0, 0] <= 0 or K[1, 1] <= 0:
            raise ValueError("K must be a finite 3x3 intrinsic matrix with positive focal lengths")
        if not np.allclose(K[2], [0, 0, 1], atol=1e-8):
            raise ValueError("K must use homogeneous pixel coordinates")
        if transform.shape != (4, 4) or not np.isfinite(transform).all():
            raise ValueError("T_world_camera must be a finite 4x4 transform")
        if not np.allclose(transform[3], [0, 0, 0, 1], atol=1e-8):
            raise ValueError("T_world_camera must be homogeneous")
        rotation = transform[:3, :3]
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-4) or not np.isclose(
            np.linalg.det(rotation), 1.0, atol=1e-4
        ):
            raise ValueError("T_world_camera must contain a proper rotation")
        if not self.episode_id or not self.camera_id or not self.calibration_version:
            raise ValueError("episode_id, camera_id, and calibration_version are required")
        if self.env_step < 0:
            raise ValueError("env_step must be nonnegative")
        if not np.isfinite(self.timestamp_s) or self.timestamp_s < 0:
            raise ValueError("timestamp_s must be a nonnegative simulation timestamp")
        if not isinstance(self.robot_state, Mapping):
            raise ValueError("robot_state must be a mapping of proprioceptive values")
        if not REQUIRED_ROBOT_STATE_KEYS.issubset(self.robot_state) or set(self.robot_state) - ROBOT_STATE_KEYS:
            raise ValueError("robot_state must contain only the allowed proprioceptive keys")
        try:
            json.dumps(self.robot_state, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("robot_state must be finite JSON data") from exc


def unproject_world(observation: RGBDObservation) -> np.ndarray:
    """Return world-space points for valid pixel centers, in row-major order."""

    rows, cols = np.nonzero(observation.depth_valid)
    if not len(rows):
        return np.empty((0, 3), dtype=np.float64)
    pixels = np.stack((cols + 0.5, rows + 0.5, np.ones_like(cols)), axis=0).astype(np.float64)
    rays = np.linalg.solve(np.asarray(observation.K, dtype=np.float64), pixels)
    camera_points = rays * observation.depth_m[rows, cols].astype(np.float64)
    transform = np.asarray(observation.T_world_camera, dtype=np.float64)
    return (transform[:3, :3] @ camera_points + transform[:3, 3:4]).T


def save_observation(observation: RGBDObservation, directory: str | Path) -> None:
    """Save one frame without pickle or lossy depth conversion."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": observation.episode_id,
        "env_step": observation.env_step,
        "timestamp_s": observation.timestamp_s,
        "camera_id": observation.camera_id,
        "source": "simulator_rgbd",
        "calibration_version": observation.calibration_version,
        "depth_convention": "optical_z_meters",
        "image_convention": "origin_top_left_x_right_y_down",
        "pixel_sample": "center_at_index_plus_half",
        "K": np.asarray(observation.K, dtype=float).tolist(),
        "T_world_camera": np.asarray(observation.T_world_camera, dtype=float).tolist(),
        "robot_state": dict(observation.robot_state),
    }
    np.savez_compressed(
        target / "rgbd.npz",
        rgb=observation.rgb,
        depth_m=observation.depth_m,
        depth_valid=observation.depth_valid,
    )
    (target / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )


def load_observation(directory: str | Path) -> RGBDObservation:
    source = Path(directory)
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported RGB-D observation schema")
    if metadata.get("depth_convention") != "optical_z_meters":
        raise ValueError("RGB-D observation requires optical-Z depth in meters")
    if metadata.get("image_convention") != "origin_top_left_x_right_y_down":
        raise ValueError("unsupported RGB-D image convention")
    if metadata.get("pixel_sample") != "center_at_index_plus_half":
        raise ValueError("unsupported RGB-D pixel sample convention")
    with np.load(source / "rgbd.npz", allow_pickle=False) as arrays:
        return RGBDObservation(
            episode_id=str(metadata["episode_id"]),
            env_step=int(metadata["env_step"]),
            timestamp_s=float(metadata["timestamp_s"]),
            camera_id=str(metadata["camera_id"]),
            rgb=arrays["rgb"],
            depth_m=arrays["depth_m"],
            depth_valid=arrays["depth_valid"],
            K=np.asarray(metadata["K"], dtype=np.float64),
            T_world_camera=np.asarray(metadata["T_world_camera"], dtype=np.float64),
            robot_state=metadata["robot_state"],
            calibration_version=str(metadata["calibration_version"]),
        )
