"""Compact MuJoCo geometry used to select articulation grasp profiles.

The descriptor intentionally contains geometry only.  Dataset/suite/task IDs
must never participate in profile selection.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np


def _as_vec(value: Any, size: int = 3) -> np.ndarray | None:
    try:
        out = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if out.size < size or not bool(np.all(np.isfinite(out[:size]))):
        return None
    return out[:size]


def _handle_position(joint: Mapping[str, Any], handle_geom: str) -> np.ndarray | None:
    pose = (joint.get("geom_poses") or {}).get(handle_geom)
    try:
        matrix = np.asarray(pose, dtype=np.float64).reshape(4, 4)
    except (TypeError, ValueError):
        return None
    position = matrix[:3, 3]
    return position if bool(np.all(np.isfinite(position))) else None


def _point_aabb_distance(point: np.ndarray, center: np.ndarray, half_extents: np.ndarray) -> float:
    return float(np.linalg.norm(np.maximum(np.abs(point - center) - half_extents, 0.0)))


def _segment_aabb_distance(
    start: np.ndarray,
    end: np.ndarray,
    center: np.ndarray,
    half_extents: np.ndarray,
    *,
    samples: int = 129,
) -> float:
    # The selector is called once per recovery query.  Dense sampling is both
    # deterministic and sufficiently accurate for the centimetre-scale guard
    # bands used by the admitted profiles.
    fractions = np.linspace(0.0, 1.0, max(2, int(samples)), dtype=np.float64)[:, None]
    points = start[None, :] + fractions * (end - start)[None, :]
    delta = np.maximum(np.abs(points - center[None, :]) - half_extents[None, :], 0.0)
    return float(np.min(np.linalg.norm(delta, axis=1)))


def describe_articulation_scene(scene: Any) -> dict[str, Any]:
    """Return a trace-safe geometry snapshot from an already-read scene."""

    from experiments.robot.libero.tiptop_repro.geometry import estimate_object_geometry
    from experiments.robot.libero.tiptop_repro.libero_panda_frames import quat_wxyz_to_matrix

    base_position = np.zeros(3, dtype=np.float64)
    world_from_base = np.eye(3, dtype=np.float64)
    frame_candidates = list(
        dict(getattr(scene, "robot_joint_debug", {}) or {}).get("frame_candidates") or []
    )
    base_row = next(
        (row for row in frame_candidates if str(row.get("name") or "") == "robot0_base"),
        None,
    )
    if isinstance(base_row, Mapping):
        candidate_position = _as_vec(base_row.get("pos_world"))
        candidate_quat = _as_vec(base_row.get("quat_world_wxyz"), 4)
        if candidate_position is not None:
            base_position = candidate_position
        if candidate_quat is not None:
            world_from_base = quat_wxyz_to_matrix(candidate_quat)
    base_from_world_rotation = world_from_base.T

    def point_in_base(value: Any) -> list[float]:
        point = _as_vec(value)
        if point is None:
            return []
        return (base_from_world_rotation @ (point - base_position)).astype(float).tolist()

    def direction_in_base(value: Any) -> list[float]:
        direction = _as_vec(value)
        if direction is None:
            return []
        return (base_from_world_rotation @ direction).astype(float).tolist()

    joints: dict[str, Any] = {}
    for name, raw in dict(getattr(scene, "articulation_structure", {}) or {}).items():
        if not isinstance(raw, Mapping):
            continue
        geom_positions: dict[str, list[float]] = {}
        for geom_name, pose in dict(raw.get("geom_poses") or {}).items():
            try:
                matrix = np.asarray(pose, dtype=np.float64).reshape(4, 4)
            except (TypeError, ValueError):
                continue
            if bool(np.all(np.isfinite(matrix[:3, 3]))):
                geom_positions[str(geom_name)] = point_in_base(matrix[:3, 3])
        joints[str(name)] = {
            "joint_type": str(raw.get("joint_type") or ""),
            "body_name": str(raw.get("body_name") or ""),
            "axis": direction_in_base(raw.get("axis")),
            "anchor": point_in_base(raw.get("anchor")),
            "reference_position": raw.get("reference_position"),
            "joint_range": list(raw.get("joint_range") or []),
            "geom_positions": geom_positions,
        }

    obstacles: list[dict[str, Any]] = []
    for name, obj in dict(getattr(scene, "objects", {}) or {}).items():
        try:
            proxy = estimate_object_geometry(obj, scene)
        except (AttributeError, TypeError, ValueError):
            continue
        center = _as_vec(proxy.center)
        half_extents = _as_vec(proxy.half_extents)
        if center is None or half_extents is None:
            continue
        center_base = base_from_world_rotation @ (center - base_position)
        half_extents_base = np.abs(base_from_world_rotation) @ np.maximum(half_extents, 1e-4)
        obstacles.append(
            {
                "name": str(name),
                "center": center_base.astype(float).tolist(),
                "half_extents": half_extents_base.astype(float).tolist(),
                "source": str(proxy.source),
            }
        )
    return {
        "frame": "robot_base",
        "base_position_world": base_position.astype(float).tolist(),
        "joints": joints,
        "obstacles": obstacles,
    }


def articulation_selection_features(
    geometry: Mapping[str, Any],
    selector: Mapping[str, Any],
) -> tuple[dict[str, float], dict[str, Any]]:
    """Build invariant, numeric features for one selector definition."""

    joint_name = str(selector.get("joint_name") or "")
    handle_geom = str(selector.get("handle_geom") or "")
    joint = dict((geometry.get("joints") or {}).get(joint_name) or {})
    geom_positions = dict(joint.get("geom_positions") or {})
    handle = _as_vec(geom_positions.get(handle_geom))
    axis = _as_vec(joint.get("axis"))
    anchor = _as_vec(joint.get("anchor"))
    if handle is None or axis is None or anchor is None:
        missing = [
            key
            for key, value in (("handle", handle), ("axis", axis), ("anchor", anchor))
            if value is None
        ]
        return {}, {"status": "missing_geometry", "missing": missing, "joint_name": joint_name, "handle_geom": handle_geom}
    norm = float(np.linalg.norm(axis))
    if norm <= 1e-9:
        return {}, {"status": "invalid_axis", "joint_name": joint_name}
    axis = axis / norm
    current = float(joint.get("reference_position") or 0.0)
    target = float(selector.get("target_joint_position", current))
    pull_end = handle + axis * (target - current)

    excluded = [str(item).lower() for item in (selector.get("exclude_obstacle_name_contains") or [])]
    nearest: dict[str, Any] | None = None
    for raw in geometry.get("obstacles") or []:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name") or "")
        if any(token and token in name.lower() for token in excluded):
            continue
        center = _as_vec(raw.get("center"))
        half_extents = _as_vec(raw.get("half_extents"))
        if center is None or half_extents is None:
            continue
        clearance = _segment_aabb_distance(handle, pull_end, center, np.maximum(half_extents, 1e-4))
        if nearest is None or clearance < float(nearest["clearance_m"]):
            nearest = {
                "name": name,
                "center": center,
                "half_extents": half_extents,
                "clearance_m": clearance,
            }

    features = {
        "handle_x": float(handle[0]),
        "handle_y": float(handle[1]),
        "handle_z": float(handle[2]),
        "anchor_x": float(anchor[0]),
        "anchor_y": float(anchor[1]),
        "anchor_z": float(anchor[2]),
        "pull_axis_x": float(axis[0]),
        "pull_axis_y": float(axis[1]),
        "pull_axis_z": float(axis[2]),
    }
    nearest_debug: dict[str, Any] | None = None
    if nearest is not None:
        relative = nearest["center"] - handle
        features.update(
            {
                "nearest_obstacle_clearance_m": float(nearest["clearance_m"]),
                "nearest_obstacle_rel_x": float(relative[0]),
                "nearest_obstacle_rel_y": float(relative[1]),
                "nearest_obstacle_rel_z": float(relative[2]),
                "nearest_obstacle_half_x": float(nearest["half_extents"][0]),
                "nearest_obstacle_half_y": float(nearest["half_extents"][1]),
                "nearest_obstacle_half_z": float(nearest["half_extents"][2]),
            }
        )
        nearest_debug = {
            "name": nearest["name"],
            "clearance_m": float(nearest["clearance_m"]),
            "relative_center": relative.astype(float).tolist(),
            "half_extents": nearest["half_extents"].astype(float).tolist(),
        }
    return features, {
        "status": "ok",
        "frame": str(geometry.get("frame") or ""),
        "joint_name": joint_name,
        "handle_geom": handle_geom,
        "handle_position": handle.astype(float).tolist(),
        "anchor": anchor.astype(float).tolist(),
        "pull_axis": axis.astype(float).tolist(),
        "pull_end": pull_end.astype(float).tolist(),
        "nearest_obstacle": nearest_debug,
    }


def normalized_prototype_score(
    actual: Mapping[str, float],
    prototype: Mapping[str, Any],
    scales: Mapping[str, Any],
) -> tuple[float | None, dict[str, float]]:
    residuals: dict[str, float] = {}
    for name, expected in prototype.items():
        if name not in actual or name not in scales:
            return None, residuals
        scale = float(scales[name])
        if not math.isfinite(scale) or scale <= 0.0:
            return None, residuals
        residuals[str(name)] = (float(actual[name]) - float(expected)) / scale
    if not residuals:
        return None, residuals
    score = math.sqrt(sum(value * value for value in residuals.values()) / len(residuals))
    return float(score), residuals
