from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from .engine_capabilities import SUPPORTED_EXECUTOR_OPTION_KEYS, canonical_place_yaw_policy
from .geometry import estimate_object_geometry, estimate_table_z
from .libero_panda_frames import base_to_world_position, robot_base_pose
from .optimized_executor import GoalSatisfactionResult, _scene_holding, goal_satisfied
from .mujoco_compat import model_name_to_id, model_names
from .scene_reader import ObjectState, SceneState, read_scene
from .task_parser import ParsedTask


@dataclass
class TipTopExecutionTrace:
    plan_reason: str
    plan_steps: List[str]
    executed_steps: List[str] = field(default_factory=list)
    num_env_steps: int = 0
    done: bool = False
    success: bool = False
    goal_satisfied: bool = False
    handoff_to_vla: bool = False
    abort_episode: bool = False
    abort_reason: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LiberoRobotClientConfig:
    gripper_steps: int = 8
    gripper_close_value: float = 1.0
    gripper_open_value: float = -1.0
    gripper_closed_threshold: float = 0.012
    gripper_open_threshold: float = 0.02
    trajectory_max_delta: float = 0.08
    trajectory_gain: float = 1.0
    default_dt: float = 1.0
    trajectory_reached_threshold: float = 0.020
    trajectory_final_reached_threshold: float = 0.010
    trajectory_waypoint_spacing: float = 0.020
    trajectory_waypoint_max_steps: int = 30
    trajectory_stall_window: int = 3
    trajectory_min_step_progress: float = 0.0005
    trajectory_min_motion: float = 0.002
    trajectory_action_scale: float = 0.05
    trajectory_max_cmd: float = 1.0
    orientation_reached_threshold: float = 0.15
    orientation_final_reached_threshold: float = 0.08
    orientation_waypoint_spacing: float = 0.20
    orientation_action_scale: float = 0.50
    orientation_max_cmd: float = 1.0
    # OSC often stalls a few centimeters short of a planned grasp/place pose.
    # These bounds are for "close enough to keep using the planned q_end", not
    # for abandoning the plan and grabbing whatever is nearby.
    near_goal_position_m: float = 0.04
    near_goal_orientation_rad: float = 0.25
    pick_reach_position_m: float = 0.015
    pose_tracking_tail_m: float = 0.08
    grasp_approach_max_steps: int = 20
    grasp_close_steps: int = 24
    grasp_close_dwell_steps: int = 6
    grasp_close_aperture_drop: float = 0.010
    grasp_lift_probe_m: float = 0.03
    grasp_lift_probe_max_steps: int = 12
    grasp_lift_follow_m: float = 0.006
    recovery_entry_lift_m: float = 0.0
    recovery_entry_lift_max_steps: int = 0
    recovery_entry_lift_reached_m: float = 0.008
    recovery_entry_lift_gripper_value: float = 0.0
    recovery_entry_escape_profile: str = ""
    recovery_entry_retreat_m: float = 0.0
    recovery_entry_retreat_max_steps: int = 0
    recovery_entry_retreat_reached_m: float = 0.012
    grasp_close_max_xy_m: float = 0.10
    grasp_close_max_above_m: float = 0.12
    joint_interp_max_l2_rad: float = 1.2
    joint_interp_max_abs_rad: float = 0.6
    # Place: cheap transport, then a reserved vertical drop. Open only if the
    # object is actually over the surface, not because OSC got within 4 cm.
    place_reserve_steps: int = 80
    place_hover_clearance_m: float = 0.08
    place_rim_clearance_m: float = 0.02
    place_lift_max_steps: int = 30
    place_lift_reached_m: float = 0.008
    place_lift_min_clearance_m: float = 0.04
    place_hover_max_steps: int = 25
    place_hover_reached_m: float = 0.02
    held_transfer_keep_z: bool = False
    held_transfer_z_margin_m: float = 0.0
    held_transfer_max_descent_m: float = 0.005
    held_transfer_max_steps: int = 0
    held_transfer_reached_m: float = 0.012
    place_yaw_after_hover: str = ""
    place_yaw_after_hover_max_steps: int = 36
    place_yaw_step_rad: float = 0.16
    place_yaw_max_cmd: float = 0.30
    place_yaw_reached_rad: float = 0.12
    place_held_object_xy_align: bool = False
    place_align_reached_m: float = 0.012
    place_align_center_tolerance_m: float = 0.008
    place_footprint_release_tolerance_m: float = 0.0
    place_align_step_clip_m: float = 0.020
    place_align_max_iters: int = 4
    place_align_max_steps_per_iter: int = 10
    place_align_retry_lift_m: float = 0.015
    place_align_retry_lift_max_steps: int = 10
    place_drop_closed_loop_align: bool = False
    place_drop_align_slices: int = 1
    place_drop_max_steps: int = 50
    place_drop_reached_m: float = 0.015
    place_drop_align_xy_m: float = 0.05
    place_release_xy_m: float = 0.022
    place_release_xy_min_m: float = 0.015
    place_release_margin_m: float = 0.008
    place_xy_correct_max_steps: int = 16
    place_release_z_max_m: float = 0.07
    place_open_dwell_steps: int = 6
    place_retreat_m: float = 0.03
    place_retreat_max_steps: int = 12


def client_config_from_recovery_hints(recovery_hints: Mapping[str, Any] | None) -> LiberoRobotClientConfig | None:
    if not isinstance(recovery_hints, Mapping):
        return None
    params = recovery_hints.get("params")
    if not isinstance(params, Mapping):
        return None
    executor = params.get("executor")
    if not isinstance(executor, Mapping):
        executor = {}

    unknown_executor_keys = sorted(
        str(key).strip()
        for key in executor
        if str(key).strip() not in SUPPORTED_EXECUTOR_OPTION_KEYS
    )
    if unknown_executor_keys:
        raise ValueError(
            "unsupported executor recovery hint option(s): "
            + ", ".join(unknown_executor_keys)
        )

    updates: Dict[str, Any] = {}
    if "grasp_close_max_above_m" in executor:
        max_above = float(executor["grasp_close_max_above_m"])
        updates["grasp_close_max_above_m"] = max(0.03, min(max_above, 0.22))
    if "grasp_lift_probe_m" in executor:
        lift_m = float(executor["grasp_lift_probe_m"])
        updates["grasp_lift_probe_m"] = max(0.0, min(lift_m, 0.10))
    if "grasp_lift_probe_max_steps" in executor:
        max_steps = int(executor["grasp_lift_probe_max_steps"])
        updates["grasp_lift_probe_max_steps"] = max(0, min(max_steps, 60))
    if "grasp_lift_follow_m" in executor:
        follow_m = float(executor["grasp_lift_follow_m"])
        updates["grasp_lift_follow_m"] = max(0.001, min(follow_m, 0.08))
    if "recovery_entry_lift_m" in executor:
        lift_m = float(executor["recovery_entry_lift_m"])
        updates["recovery_entry_lift_m"] = max(0.0, min(lift_m, 0.12))
    if "recovery_entry_lift_max_steps" in executor:
        max_steps = int(executor["recovery_entry_lift_max_steps"])
        updates["recovery_entry_lift_max_steps"] = max(0, min(max_steps, 60))
    if "recovery_entry_lift_reached_m" in executor:
        reached_m = float(executor["recovery_entry_lift_reached_m"])
        updates["recovery_entry_lift_reached_m"] = max(0.001, min(reached_m, 0.05))
    if "recovery_entry_lift_gripper_value" in executor:
        gripper = float(executor["recovery_entry_lift_gripper_value"])
        updates["recovery_entry_lift_gripper_value"] = max(-1.0, min(gripper, 1.0))
    profile = str(
        os.environ.get("TIPTOP_RECOVERY_ENTRY_ESCAPE_PROFILE")
        or executor.get("recovery_entry_escape_profile")
        or ""
    ).strip()
    if profile:
        updates["recovery_entry_escape_profile"] = profile
    if "recovery_entry_retreat_m" in executor:
        retreat_m = float(executor["recovery_entry_retreat_m"])
        updates["recovery_entry_retreat_m"] = max(0.0, min(retreat_m, 0.16))
    if "recovery_entry_retreat_max_steps" in executor:
        max_steps = int(executor["recovery_entry_retreat_max_steps"])
        updates["recovery_entry_retreat_max_steps"] = max(0, min(max_steps, 80))
    if "recovery_entry_retreat_reached_m" in executor:
        reached_m = float(executor["recovery_entry_retreat_reached_m"])
        updates["recovery_entry_retreat_reached_m"] = max(0.001, min(reached_m, 0.05))
    if "place_hover_clearance_m" in executor:
        clearance = float(executor["place_hover_clearance_m"])
        updates["place_hover_clearance_m"] = max(0.0, min(clearance, 0.20))
    if "place_hover_max_steps" in executor:
        max_steps = int(executor["place_hover_max_steps"])
        updates["place_hover_max_steps"] = max(1, min(max_steps, 80))
    if "place_hover_reached_m" in executor:
        reached_m = float(executor["place_hover_reached_m"])
        updates["place_hover_reached_m"] = max(0.001, min(reached_m, 0.05))
    if "place_lift_min_clearance_m" in executor:
        clearance = float(executor["place_lift_min_clearance_m"])
        updates["place_lift_min_clearance_m"] = max(0.0, min(clearance, 0.15))
    if "place_lift_max_steps" in executor:
        max_steps = int(executor["place_lift_max_steps"])
        updates["place_lift_max_steps"] = max(0, min(max_steps, 80))
    if "place_lift_reached_m" in executor:
        reached_m = float(executor["place_lift_reached_m"])
        updates["place_lift_reached_m"] = max(0.001, min(reached_m, 0.05))
    if "held_transfer_keep_z" in executor:
        updates["held_transfer_keep_z"] = bool(executor["held_transfer_keep_z"])
    if "held_transfer_z_margin_m" in executor:
        margin = float(executor["held_transfer_z_margin_m"])
        updates["held_transfer_z_margin_m"] = max(0.0, min(margin, 0.08))
    if "held_transfer_max_descent_m" in executor:
        descent = float(executor["held_transfer_max_descent_m"])
        updates["held_transfer_max_descent_m"] = max(0.0, min(descent, 0.03))
    if "held_transfer_max_steps" in executor:
        max_steps = int(executor["held_transfer_max_steps"])
        updates["held_transfer_max_steps"] = max(0, min(max_steps, 120))
    if "held_transfer_reached_m" in executor:
        reached = float(executor["held_transfer_reached_m"])
        updates["held_transfer_reached_m"] = max(0.001, min(reached, 0.04))
    raw_yaw = canonical_place_yaw_policy(executor.get("place_yaw_after_hover"))
    if raw_yaw in {"world_z_thin_x", "thin_horizontal_along_world_x"}:
        updates["place_yaw_after_hover"] = "world_z_thin_x"
    elif "place_yaw_after_hover" in executor:
        updates["place_yaw_after_hover"] = ""
    if "place_yaw_after_hover_max_steps" in executor:
        max_steps = int(executor["place_yaw_after_hover_max_steps"])
        updates["place_yaw_after_hover_max_steps"] = max(0, min(max_steps, 60))
    if "place_yaw_step_rad" in executor:
        step = float(executor["place_yaw_step_rad"])
        updates["place_yaw_step_rad"] = max(0.06, min(step, 0.35))
    if "place_yaw_max_cmd" in executor:
        cmd = float(executor["place_yaw_max_cmd"])
        updates["place_yaw_max_cmd"] = max(0.08, min(cmd, 0.60))
    if "place_held_object_xy_align" in executor:
        updates["place_held_object_xy_align"] = bool(executor["place_held_object_xy_align"])
    if "place_align_reached_m" in executor:
        reached = float(executor["place_align_reached_m"])
        updates["place_align_reached_m"] = max(0.001, min(reached, 0.04))
    if "place_align_center_tolerance_m" in executor:
        center_tol = float(executor["place_align_center_tolerance_m"])
        updates["place_align_center_tolerance_m"] = max(0.001, min(center_tol, 0.04))
    if "place_footprint_release_tolerance_m" in executor:
        footprint_tol = float(executor["place_footprint_release_tolerance_m"])
        updates["place_footprint_release_tolerance_m"] = max(0.0, min(footprint_tol, 0.01))
    if "place_align_step_clip_m" in executor:
        step = float(executor["place_align_step_clip_m"])
        updates["place_align_step_clip_m"] = max(0.004, min(step, 0.04))
    if "place_align_max_iters" in executor:
        max_iters = int(executor["place_align_max_iters"])
        updates["place_align_max_iters"] = max(0, min(max_iters, 8))
    if "place_align_max_steps_per_iter" in executor:
        max_steps = int(executor["place_align_max_steps_per_iter"])
        updates["place_align_max_steps_per_iter"] = max(1, min(max_steps, 30))
    if "place_align_retry_lift_m" in executor:
        lift_m = float(executor["place_align_retry_lift_m"])
        updates["place_align_retry_lift_m"] = max(0.0, min(lift_m, 0.04))
    if "place_align_retry_lift_max_steps" in executor:
        max_steps = int(executor["place_align_retry_lift_max_steps"])
        updates["place_align_retry_lift_max_steps"] = max(0, min(max_steps, 30))
    if "place_drop_closed_loop_align" in executor:
        updates["place_drop_closed_loop_align"] = bool(executor["place_drop_closed_loop_align"])
    if "place_drop_align_slices" in executor:
        slices = int(executor["place_drop_align_slices"])
        updates["place_drop_align_slices"] = max(1, min(slices, 6))
    if "place_drop_max_steps" in executor:
        max_steps = int(executor["place_drop_max_steps"])
        updates["place_drop_max_steps"] = max(1, min(max_steps, 160))
    if "place_drop_reached_m" in executor:
        reached_m = float(executor["place_drop_reached_m"])
        updates["place_drop_reached_m"] = max(0.001, min(reached_m, 0.05))
    if "place_drop_align_xy_m" in executor:
        xy_m = float(executor["place_drop_align_xy_m"])
        updates["place_drop_align_xy_m"] = max(0.001, min(xy_m, 0.10))
    if "place_release_xy_m" in executor:
        xy_m = float(executor["place_release_xy_m"])
        updates["place_release_xy_m"] = max(0.001, min(xy_m, 0.08))
    if "place_release_xy_min_m" in executor:
        xy_m = float(executor["place_release_xy_min_m"])
        updates["place_release_xy_min_m"] = max(0.001, min(xy_m, 0.08))
    if "place_release_margin_m" in executor:
        margin_m = float(executor["place_release_margin_m"])
        updates["place_release_margin_m"] = max(0.0, min(margin_m, 0.05))
    if "place_release_z_max_m" in executor:
        z_max_m = float(executor["place_release_z_max_m"])
        updates["place_release_z_max_m"] = max(0.0, min(z_max_m, 0.20))
    if "place_open_dwell_steps" in executor:
        dwell_steps = int(executor["place_open_dwell_steps"])
        updates["place_open_dwell_steps"] = max(0, min(dwell_steps, 30))
    if "place_retreat_m" in executor:
        retreat_m = float(executor["place_retreat_m"])
        updates["place_retreat_m"] = max(0.0, min(retreat_m, 0.12))
    if "place_retreat_max_steps" in executor:
        max_steps = int(executor["place_retreat_max_steps"])
        updates["place_retreat_max_steps"] = max(0, min(max_steps, 60))
    geometry_hints = params.get("geometry_hints")
    region = {}
    if isinstance(geometry_hints, Mapping):
        maybe_region = geometry_hints.get("placement_region")
        if isinstance(maybe_region, Mapping):
            region = maybe_region
    if not updates.get("place_yaw_after_hover"):
        policy = canonical_place_yaw_policy(region.get("place_yaw_policy"))
        if policy in {"world_z_thin_x", "thin_horizontal_along_world_x"}:
            updates["place_yaw_after_hover"] = "world_z_thin_x"
    if not updates:
        return None
    return replace(LiberoRobotClientConfig(), **updates)


def _confirmed_holding_latch_object(latch: Dict[str, Any] | None) -> Optional[str]:
    if not isinstance(latch, dict) or not bool(latch.get("active")):
        return None
    obj_name = str(latch.get("object_name") or "")
    return obj_name or None


def _clear_confirmed_holding_latch(latch: Dict[str, Any] | None, reason: str) -> Dict[str, Any]:
    if not isinstance(latch, dict) or not latch:
        return {}
    previous = {k: v for k, v in latch.items() if k != "previous"}
    latch.clear()
    latch.update({"active": False, "clear_reason": str(reason), "previous": previous})
    return dict(latch)


def _set_confirmed_holding_latch(
    latch: Dict[str, Any] | None,
    obj_name: str,
    *,
    source: str,
    label: str,
    snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(latch, dict):
        return {}
    snap = dict(snapshot or {})
    latch.clear()
    latch.update(
        {
            "active": True,
            "object_name": str(obj_name),
            "source": str(source),
            "label": str(label),
            "confidence": 0.92,
            "object_followed": snap.get("object_followed"),
            "object_lift_m": snap.get("object_lift_m"),
            "aperture": snap.get("aperture"),
            "bilateral_contact": snap.get("bilateral_contact"),
            "raw_holding_evidence": dict(snap.get("holding_evidence") or {}),
        }
    )
    return dict(latch)


def _apply_confirmed_holding_latch(scene: SceneState, latch: Dict[str, Any] | None) -> bool:
    obj_name = _confirmed_holding_latch_object(latch)
    if not obj_name:
        return False
    if scene.gripper_open:
        _clear_confirmed_holding_latch(latch, "gripper_open")
        return False
    if obj_name not in scene.objects:
        _clear_confirmed_holding_latch(latch, "object_missing")
        return False
    raw = dict(scene.holding_evidence or {})
    if raw.get("status") == "holding" and str(raw.get("object_name") or "") == obj_name:
        return True
    scene.holding_evidence = {
        "status": "holding",
        "object_name": obj_name,
        "confidence": float((latch or {}).get("confidence", 0.92)),
        "source": "lift_probe_latch",
        "latched": True,
        "gripper_closed": True,
        "gripper_aperture_abs_mean": float(np.mean(np.abs(scene.gripper_qpos))),
        "raw_holding_evidence": raw,
    }
    return True


def _valid_cartesian_waypoints(waypoints: Iterable[Iterable[float]]) -> List[np.ndarray]:
    valid: List[np.ndarray] = []
    for waypoint in waypoints:
        point = np.asarray(list(waypoint), dtype=np.float32).reshape(-1)
        if point.size >= 3 and np.all(np.isfinite(point[:3])):
            valid.append(point[:3].copy())
    return valid


def _compress_cartesian_waypoints(waypoints: List[np.ndarray], min_spacing: float) -> List[np.ndarray]:
    if not waypoints:
        return []
    spacing = max(0.0, float(min_spacing))
    selected = [waypoints[0]]
    for point in waypoints[1:-1]:
        if float(np.linalg.norm(point - selected[-1])) >= spacing:
            selected.append(point)
    if len(waypoints) > 1 and not np.array_equal(selected[-1], waypoints[-1]):
        selected.append(waypoints[-1])
    return selected


def _quat_xyzw_to_matrix(quat: Any) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64).reshape(-1)[:4]
    q = q / max(float(np.linalg.norm(q)), 1e-12)
    x, y, z, w = q
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _matrix_to_quat_xyzw(matrix: Any) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    trace = float(np.trace(m))
    if trace > 0.0:
        scale = np.sqrt(trace + 1.0) * 2.0
        quat = np.asarray([(m[2, 1] - m[1, 2]) / scale, (m[0, 2] - m[2, 0]) / scale, (m[1, 0] - m[0, 1]) / scale, 0.25 * scale])
    else:
        idx = int(np.argmax(np.diag(m)))
        if idx == 0:
            scale = np.sqrt(max(1.0 + m[0, 0] - m[1, 1] - m[2, 2], 1e-12)) * 2.0
            quat = np.asarray([0.25 * scale, (m[0, 1] + m[1, 0]) / scale, (m[0, 2] + m[2, 0]) / scale, (m[2, 1] - m[1, 2]) / scale])
        elif idx == 1:
            scale = np.sqrt(max(1.0 + m[1, 1] - m[0, 0] - m[2, 2], 1e-12)) * 2.0
            quat = np.asarray([(m[0, 1] + m[1, 0]) / scale, 0.25 * scale, (m[1, 2] + m[2, 1]) / scale, (m[0, 2] - m[2, 0]) / scale])
        else:
            scale = np.sqrt(max(1.0 + m[2, 2] - m[0, 0] - m[1, 1], 1e-12)) * 2.0
            quat = np.asarray([(m[0, 2] + m[2, 0]) / scale, (m[1, 2] + m[2, 1]) / scale, 0.25 * scale, (m[1, 0] - m[0, 1]) / scale])
    quat = quat / max(float(np.linalg.norm(quat)), 1e-12)
    return quat if quat[3] >= 0.0 else -quat


def _rotation_vector(matrix: Any) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    cosine = float(np.clip((np.trace(m) - 1.0) * 0.5, -1.0, 1.0))
    angle = float(np.arccos(cosine))
    if angle < 1e-7:
        return np.zeros(3, dtype=np.float32)
    if np.pi - angle < 1e-5:
        eigvals, eigvecs = np.linalg.eig(m)
        axis = np.real(eigvecs[:, int(np.argmin(np.abs(eigvals - 1.0)))])
        axis = axis / max(float(np.linalg.norm(axis)), 1e-12)
    else:
        axis = np.asarray([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]])
        axis = axis / max(2.0 * np.sin(angle), 1e-12)
    return (axis * angle).astype(np.float32)


def _orientation_error(target_xyzw: Any, current_xyzw: Any) -> np.ndarray:
    return _rotation_vector(_quat_xyzw_to_matrix(target_xyzw) @ _quat_xyzw_to_matrix(current_xyzw).T)


def _wrap_yaw_rad(value: float) -> float:
    return float((float(value) + np.pi) % (2.0 * np.pi) - np.pi)


def _nearest_signed_yaw_delta(current_yaw: float, targets: Iterable[float]) -> Tuple[float, float]:
    current = _wrap_yaw_rad(current_yaw)
    best_target = current
    best_delta = 0.0
    found = False
    for raw in targets:
        target = _wrap_yaw_rad(raw)
        delta = _wrap_yaw_rad(target - current)
        if not found or abs(delta) < abs(best_delta) - 1e-9:
            best_target = target
            best_delta = delta
            found = True
    return best_target, best_delta


def _apply_world_yaw_to_quat_xyzw(quat_xyzw: Any, delta_yaw: float) -> np.ndarray:
    cosine = float(np.cos(delta_yaw))
    sine = float(np.sin(delta_yaw))
    rot_z = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    return _matrix_to_quat_xyzw(rot_z @ _quat_xyzw_to_matrix(quat_xyzw)).astype(np.float32)


def _object_local_half_extents(obj: ObjectState) -> np.ndarray:
    geoms = list((getattr(obj, "geometry", None) or {}).get("geoms") or [])
    best: Optional[np.ndarray] = None
    best_vol = -1.0
    for geom in geoms:
        size = np.asarray(geom.get("size", []), dtype=np.float64).reshape(-1)
        if size.size < 2:
            continue
        extents = np.array([0.015, 0.055, 0.067], dtype=np.float64)
        extents[: min(3, size.size)] = np.maximum(size[: min(3, size.size)], 1e-4)
        vol = float(np.prod(extents))
        if vol > best_vol:
            best_vol = vol
            best = extents
    if best is None:
        return np.asarray([0.015, 0.055, 0.067], dtype=np.float64)
    return best


def _object_thin_horizontal_yaw(scene: SceneState, obj_name: Optional[str]) -> Optional[float]:
    obj = scene.objects.get(obj_name) if obj_name else None
    if obj is None or obj.quat is None:
        return None
    quat_wxyz = np.asarray(obj.quat, dtype=np.float64).reshape(-1)[:4]
    if quat_wxyz.size < 4 or not np.all(np.isfinite(quat_wxyz)):
        return None
    quat_xyzw = np.asarray([quat_wxyz[1], quat_wxyz[2], quat_wxyz[3], quat_wxyz[0]], dtype=np.float64)
    rotation = _quat_xyzw_to_matrix(quat_xyzw)
    extents = _object_local_half_extents(obj)
    best: Optional[Tuple[float, float, float]] = None
    for idx in range(3):
        axis = rotation[:, idx]
        horizontal = float(np.linalg.norm(axis[:2]))
        if horizontal < 0.55:
            continue
        yaw = float(np.arctan2(axis[1], axis[0]))
        cand = (float(extents[idx]), -horizontal, yaw)
        if best is None or cand < best:
            best = cand
    if best is None:
        return None
    return _wrap_yaw_rad(best[2])


def _world_z_yaw_pose_waypoints(
    position: np.ndarray,
    start_quat_xyzw: np.ndarray,
    delta_yaw: float,
    step_rad: float,
) -> List[Dict[str, Any]]:
    step = max(0.06, float(step_rad))
    count = max(1, int(np.ceil(abs(float(delta_yaw)) / step)))
    count = min(count, 12)
    xyz = np.asarray(position, dtype=float).reshape(-1)[:3].astype(float).tolist()
    waypoints: List[Dict[str, Any]] = []
    for idx in range(1, count + 1):
        frac = float(idx) / float(count)
        quat = _apply_world_yaw_to_quat_xyzw(start_quat_xyzw, float(delta_yaw) * frac)
        waypoints.append({"position": xyz, "quat_xyzw": quat.astype(float).tolist()})
    return waypoints


def _compress_pose_waypoints(
    waypoints: List[Dict[str, np.ndarray]],
    position_spacing: float,
    orientation_spacing: float,
) -> List[Dict[str, np.ndarray]]:
    if not waypoints:
        return []
    selected = [waypoints[0]]
    for waypoint in waypoints[1:-1]:
        pos_delta = float(np.linalg.norm(waypoint["position"] - selected[-1]["position"]))
        rot_delta = float(np.linalg.norm(_orientation_error(waypoint["quat_xyzw"], selected[-1]["quat_xyzw"])))
        if pos_delta >= position_spacing or rot_delta >= orientation_spacing:
            selected.append(waypoint)
    if len(waypoints) > 1:
        last = waypoints[-1]
        if not (
            np.array_equal(selected[-1]["position"], last["position"])
            and np.array_equal(selected[-1]["quat_xyzw"], last["quat_xyzw"])
        ):
            selected.append(last)
    return selected


def _near_planned_goal(pos_error: float, rot_error: float, cfg: LiberoRobotClientConfig) -> bool:
    return float(pos_error) <= float(cfg.near_goal_position_m) and float(rot_error) <= float(cfg.near_goal_orientation_rad)


def _near_planned_position(pos_error: float, cfg: LiberoRobotClientConfig) -> bool:
    return float(pos_error) <= float(cfg.near_goal_position_m)


def _object_name_from_label(label: str) -> Optional[str]:
    text = str(label or "")
    if "(" not in text:
        return None
    name = text.split("(", 1)[1].split(",", 1)[0].strip().rstrip(")")
    return name or None


def _plan_target_object(executable_plan: List[Dict[str, Any]], idx: int) -> Optional[str]:
    for step in list(executable_plan[idx:]) + list(reversed(executable_plan[:idx])):
        name = _object_name_from_label(str(step.get("label") or ""))
        if name:
            return name
    return None


def _object_world_z(scene: SceneState, obj_name: str) -> Optional[float]:
    obj = scene.objects.get(obj_name)
    if obj is None or obj.pos is None:
        return None
    return float(obj.pos[2])


def _bilateral_target_contact(scene: SceneState, obj_name: str) -> bool:
    """True if both fingers touch the target. Aperture does not matter."""
    target = _match_scene_object(obj_name, scene) or str(obj_name or "")
    if not target:
        return False
    evidence = dict(getattr(scene, "holding_evidence", None) or {})
    for cand in evidence.get("candidates") or []:
        name = str(cand.get("object_name") or "")
        matched = _match_scene_object(name, scene) or name
        if matched == target and bool(cand.get("bilateral_contact")):
            return True
    sides = set()
    for contact in getattr(scene, "contacts", None) or []:
        obj = contact.get("finger_object")
        side = contact.get("finger_side")
        matched = _match_scene_object(str(obj or ""), scene) if obj else None
        if matched == target and side:
            sides.add(str(side))
    return "left" in sides and "right" in sides


def _ee_near_grasp_target(
    scene: SceneState,
    obj_name: str,
    cfg: LiberoRobotClientConfig,
) -> Tuple[bool, Dict[str, Any]]:
    """True if the gripper is around the object, not closing in free space."""
    matched = _match_scene_object(obj_name, scene) or str(obj_name or "")
    obj = scene.objects.get(matched) if matched else None
    details: Dict[str, Any] = {"object": matched or obj_name}
    if obj is None or obj.pos is None:
        return False, details
    ee = np.asarray(scene.ee_pos[:3], dtype=np.float32)
    pos = np.asarray(obj.pos[:3], dtype=np.float32)
    xy = float(np.linalg.norm(ee[:2] - pos[:2]))
    z_delta = float(ee[2] - pos[2])
    geom = estimate_object_geometry(obj, scene)
    radius = max(float(geom.radius or 0.0), 0.04)
    max_xy = max(float(cfg.grasp_close_max_xy_m), radius + 0.02)
    max_above = float(cfg.grasp_close_max_above_m)
    near = bool(xy <= max_xy and -0.03 <= z_delta <= max_above)
    details.update({"xy_m": xy, "z_delta_m": z_delta, "max_xy_m": max_xy, "max_above_m": max_above, "near": near})
    return near, details


def _holding_snapshot(scene: SceneState, obj_name: str) -> Dict[str, Any]:
    pinch = _bilateral_target_contact(scene, obj_name)
    return {
        "holding": bool(_scene_holding(scene, obj_name)),
        "bilateral_contact": bool(pinch),
        "object_z": _object_world_z(scene, obj_name),
        "gripper_open": bool(scene.gripper_open),
        "aperture": float(np.mean(np.abs(scene.gripper_qpos))) if scene.gripper_qpos is not None else None,
        "holding_evidence": dict(getattr(scene, "holding_evidence", None) or {}),
    }


def _scene_grasp_debug_snapshot(scene: SceneState, obj_name: Optional[str]) -> Dict[str, Any]:
    obj = scene.objects.get(obj_name) if obj_name else None
    return {
        "ee_xyz": scene.ee_pos[:3].astype(float).tolist(),
        "ee_quat": scene.ee_quat[:4].astype(float).tolist(),
        "gripper_qpos": None if scene.gripper_qpos is None else scene.gripper_qpos.astype(float).tolist(),
        "aperture": float(np.mean(np.abs(scene.gripper_qpos))) if scene.gripper_qpos is not None else None,
        "object": obj_name,
        "object_xyz": None if obj is None or obj.pos is None else obj.pos[:3].astype(float).tolist(),
        "holding": bool(_scene_holding(scene, obj_name)) if obj_name else False,
        "holding_evidence": dict(getattr(scene, "holding_evidence", None) or {}),
    }


def _planned_close_pose_from_executable(
    env: Any,
    executable_plan: List[Dict[str, Any]],
    close_idx: int,
    label: str,
    reference_quat_xyzw: Any,
) -> Dict[str, Any]:
    for step_idx in range(int(close_idx) - 1, -1, -1):
        step = executable_plan[step_idx]
        if str(step.get("type") or "") != "trajectory":
            continue
        if str(step.get("label") or "") != str(label or ""):
            continue
        positions = step.get("positions") or []
        if not positions:
            continue
        joint_path = np.asarray(positions, dtype=np.float32)
        poses = _joint_path_to_ee_pose_waypoints(env, joint_path, reference_quat_xyzw)
        out: Dict[str, Any] = {
            "planned_close_step_idx": step_idx,
            "planned_close_num_waypoints": int(len(positions)),
        }
        if joint_path.ndim == 2 and joint_path.shape[0] > 0:
            out["planned_close_q"] = joint_path[-1].astype(float).tolist()
        if poses:
            out["planned_close_xyz"] = list(poses[-1]["position"])
            out["planned_close_quat_xyzw"] = list(poses[-1]["quat_xyzw"])
        return out
    return {}


def _settle_and_confirm_holding(
    client: "LiberoRobotClient",
    obj_name: str,
    label: str,
    remaining_steps: int,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Confirm grasp by pinch or object-follow, not by fully-closed fingers.

    Always dwell, then always probe a short lift when budget remains. Success if
    both fingers touch the target or the object rises with the gripper. Aperture
    is recorded only.
    """
    events: List[Dict[str, Any]] = []
    cfg = client.cfg
    close_value = float(cfg.gripper_close_value)
    obj_name = _match_scene_object(obj_name, client.get_scene()) or obj_name

    dwell = min(max(0, int(cfg.grasp_close_dwell_steps)), max(0, int(remaining_steps)))
    if dwell > 0 and not client.done:
        client._gripper_action(close_value, steps=dwell, label=f"{label}:close_dwell")
        remaining_steps = max(0, int(remaining_steps) - dwell)
    scene = client.get_scene()
    after_dwell = _holding_snapshot(scene, obj_name)
    events.append({"step": label, "event": "grasp_close_dwell", "steps": dwell, **after_dwell})
    pinch_dwell = bool(after_dwell.get("bilateral_contact"))
    if client.done:
        return True, events

    lift_m = float(cfg.grasp_lift_probe_m)
    lift_budget = min(max(0, int(cfg.grasp_lift_probe_max_steps)), max(0, int(remaining_steps)))
    if lift_m <= 0.0 or lift_budget <= 0:
        return pinch_dwell, events

    z_before = after_dwell.get("object_z")
    ee = scene.ee_pos[:3].astype(np.float32).copy()
    quat = scene.ee_quat[:4].astype(np.float32).copy()
    goal = ee.copy()
    goal[2] = float(goal[2] + lift_m)
    lift = client.execute_cartesian_pose_waypoints(
        [{"position": goal.astype(float).tolist(), "quat_xyzw": quat.astype(float).tolist()}],
        gripper=close_value,
        max_steps=lift_budget,
        label=f"{label}:lift_probe",
    )
    scene = client.get_scene()
    after_lift = _holding_snapshot(scene, obj_name)
    z_after = after_lift.get("object_z")
    object_lift = (
        None
        if z_before is None or z_after is None
        else float(z_after) - float(z_before)
    )
    followed = bool(object_lift is not None and object_lift >= float(cfg.grasp_lift_follow_m))
    pinch_lift = bool(after_lift.get("bilateral_contact"))
    confirmed = bool(pinch_dwell or pinch_lift or followed or client.done)
    events.append(
        {
            "step": label,
            "event": "grasp_lift_probe",
            "lift_m": lift_m,
            "object_lift_m": object_lift,
            "object_followed": followed,
            "bilateral_contact": pinch_lift,
            "confirmed": confirmed,
            "lift_result": {k: v for k, v in lift.items() if k not in {"waypoints"}},
            **after_lift,
        }
    )
    return confirmed, events


def _gripper_hold_value(
    label: str,
    closed: bool,
    cfg: LiberoRobotClientConfig,
    *,
    preserve_closed: bool = False,
) -> float:
    if preserve_closed:
        return float(cfg.gripper_close_value)
    low = str(label or "").lower()
    if "pick(" in low or "movefree" in low:
        return float(cfg.gripper_open_value)
    if "place(" in low:
        return float(cfg.gripper_close_value if closed else cfg.gripper_open_value)
    return float(cfg.gripper_close_value if closed else cfg.gripper_open_value)


def _call_hook(hook_bridge: Any, name: str, payload: Dict[str, Any]) -> Any:
    if hook_bridge is None:
        return None
    fn = getattr(hook_bridge, name, None)
    if not callable(fn):
        return None
    return fn(payload)


def _apply_trajectory_hook(
    hook_bridge: Any,
    state: Dict[str, Any],
    default_hold: float,
) -> Tuple[bool, float, Dict[str, Any]]:
    override = _call_hook(hook_bridge, "before_trajectory_step", state)
    skip = False
    hold = float(default_hold)
    meta: Dict[str, Any] = {}
    if not isinstance(override, dict):
        return skip, hold, meta
    skip = bool(override.get("skip"))
    if override.get("keep_gripper_closed") and override.get("gripper_hold_value") is None:
        close_value = state.get("gripper_close_value")
        if close_value is not None:
            override = {**override, "gripper_hold_value": close_value}
    if override.get("gripper_hold_value") is not None:
        hold = float(override["gripper_hold_value"])
    fired = bool(skip or override.get("gripper_hold_value") is not None or override.get("keep_gripper_closed"))
    if fired:
        meta = {
            "hook_fired": True,
            "skill_id": override.get("skill_id") or "",
            "backend": override.get("backend") or "",
            "keep_gripper_closed": bool(override.get("keep_gripper_closed")),
        }
    return skip, hold, meta


def _plan_has_place(executable_plan: Iterable[Dict[str, Any]]) -> bool:
    return any("place(" in str(step.get("label") or "").lower() for step in executable_plan)


def _front_budget(client: "LiberoRobotClient", max_env_steps: int, reserve: bool) -> int:
    remaining = max(0, int(max_env_steps) - int(client.num_env_steps))
    if not reserve:
        return remaining
    return max(0, remaining - max(0, int(client.cfg.place_reserve_steps)))


def _held_transfer_protected_z(start_z: float, planned_endpoint_z: float, cfg: LiberoRobotClientConfig) -> float:
    if not bool(cfg.held_transfer_keep_z):
        return float(planned_endpoint_z)
    start = float(start_z)
    endpoint = float(planned_endpoint_z)
    margin = max(0.0, float(cfg.held_transfer_z_margin_m))
    max_descent = max(0.0, float(cfg.held_transfer_max_descent_m))
    return max(start + margin, start - max_descent, endpoint)


def _match_scene_object(name: Optional[str], scene: SceneState) -> Optional[str]:
    if not name:
        return None
    if name in scene.objects:
        return name
    low = str(name).lower()
    hits = [key for key in scene.objects if low in key.lower() or key.lower() in low]
    return hits[0] if hits else None


def _place_args_from_label_details(label: str, scene: SceneState) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    text = str(label or "")
    if "(" not in text:
        return None, None, None
    inside = text.split("(", 1)[1].rsplit(")", 1)[0]
    parts = [part.strip() for part in inside.split(",") if part.strip()]
    obj_name = _match_scene_object(parts[0] if parts else None, scene)
    surface_name = None
    surface_label = None
    for part in parts[1:]:
        low = part.lower()
        if low.startswith(("pose", "q", "grasp")):
            continue
        surface_label = part
        surface_name = _match_scene_object(part, scene)
        if surface_name:
            break
    return obj_name, surface_name, surface_label


def _place_args_from_label(label: str, scene: SceneState) -> Tuple[Optional[str], Optional[str]]:
    obj_name, surface_name, _surface_label = _place_args_from_label_details(label, scene)
    return obj_name, surface_name


def _last_place_joint_path(executable_plan: List[Dict[str, Any]], start_idx: int) -> Optional[np.ndarray]:
    last = None
    for step in executable_plan[start_idx:]:
        stype = str(step.get("type") or "")
        label = str(step.get("label") or "").lower()
        if stype == "trajectory" and "place(" in label:
            positions = step.get("positions") or []
            if positions:
                last = np.asarray(positions, dtype=np.float32)
            continue
        break
    return last


def _aabb_lower_upper(scene: SceneState, obj_name: Optional[str]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    obj = scene.objects.get(obj_name) if obj_name else None
    if obj is None:
        return None, None
    geom = estimate_object_geometry(obj, scene)
    center = np.asarray(geom.center if geom.center is not None else obj.pos, dtype=np.float64).reshape(-1)[:3]
    he = np.full(3, 0.03, dtype=np.float64)
    raw = np.asarray(geom.half_extents or [], dtype=np.float64).reshape(-1)
    if raw.size:
        he[: min(3, raw.size)] = raw[: min(3, raw.size)]
    he = np.maximum(he, 1e-4)
    return (center - he).astype(np.float64), (center + he).astype(np.float64)


def _object_half_xy(scene: SceneState, obj_name: Optional[str]) -> Tuple[float, float]:
    obj = scene.objects.get(obj_name) if obj_name else None
    if obj is None:
        return 0.028, 0.028
    geom = estimate_object_geometry(obj, scene)
    he = list(geom.half_extents or [])
    hx = max(0.015, float(he[0])) if he else max(0.015, float(geom.radius) * 0.7)
    hy = max(0.015, float(he[1])) if len(he) >= 2 else hx
    return hx, hy


_RELEASE_OPENING_METADATA_KEYS = (
    "surface_label",
    "support_surface",
    "source_bddl_region",
    "source_bddl_qualified_region",
    "coordinate_frame",
    "planner_frame",
    "planner_frame_method",
    "planner_frame_origin_world",
    "planner_frame_quat_world_wxyz",
    "opening_frame_conversion_applied",
    "opening_frame_conversion_reason",
    "opening_center_xy_planner",
    "opening_center_xy_world",
    "support_z_planner",
    "support_z_world",
    "inner_bounds_coordinate_frame",
    "release_mode",
    "release_z_offset_m",
    "release_z_tolerance_m",
    "release_xy_margin_m",
    "planner_support_z_m",
    "inner_bounds_source",
    "source_site_name",
    "site_margin_m",
    "floor_clearance_m",
    "geometry_profile",
    "geometry_profile_adapter_path",
    "geometry_profile_adapter_warning",
    "inner_bounds_adapter",
    "inner_bounds_adapter_path",
    "inner_bounds_profile",
)


def _copy_release_opening_metadata(opening: Dict[str, Any], metadata: Mapping[str, Any]) -> Dict[str, Any]:
    for key in _RELEASE_OPENING_METADATA_KEYS:
        if key in metadata:
            opening[key] = metadata[key]
    return opening


def _complete_opening_mapping(opening: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(opening, Mapping):
        return None
    required = ("x_min", "x_max", "y_min", "y_max", "support_z")
    if not all(key in opening for key in required):
        return None
    try:
        out = dict(opening)
        for key in required:
            out[key] = float(opening[key])
    except (TypeError, ValueError):
        return None
    if out["x_max"] <= out["x_min"] or out["y_max"] <= out["y_min"]:
        return None
    return out


def _serialized_caddy_compartment_opening(
    surface_name: Optional[str],
    surface_label: Optional[str],
    serialized_opening: Optional[Mapping[str, Any]],
    compartment: str,
) -> Optional[Dict[str, Any]]:
    opening = _complete_opening_mapping(serialized_opening)
    if opening is None:
        return None
    frame = str(opening.get("coordinate_frame") or "").strip().lower()
    if frame and frame != "world":
        return None
    inner_source = str(opening.get("inner_bounds_source") or "").strip().lower()
    source_site = str(opening.get("source_site_name") or "").strip().lower()
    if not (
        inner_source.startswith("libero90_desk_caddy")
        or ("desk_caddy" in source_site and "contain_region" in source_site)
    ):
        return None
    original_source = str(opening.get("source") or opening.get("inner_bounds_source") or "")
    opening.update(
        {
            "source": "caddy_compartment_serialized",
            "source_opening_source": original_source,
            "surface_label": surface_label or str(opening.get("surface_label") or ""),
            "surface_resolved": surface_name,
            "compartment": compartment,
            "executor_opening_source": "serialized_planner_opening",
        }
    )
    return opening


def _float_from_mapping(mapping: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(mapping.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _release_mode(opening: Optional[Mapping[str, Any]]) -> str:
    return str((opening or {}).get("release_mode") or "").strip().lower()


def _opening_bounds(scene: SceneState, surface_name: Optional[str]) -> Optional[Dict[str, Any]]:
    obj = scene.objects.get(surface_name) if surface_name else None
    if obj is None:
        return None
    geom = estimate_object_geometry(obj, scene)
    metadata = dict(geom.metadata or {})
    inner = metadata.get("inner_bounds") or {}
    if all(key in inner for key in ("x_min", "x_max", "y_min", "y_max")):
        support_z = inner.get("support_z", inner.get("z_min", obj.pos[2] if obj.pos is not None else 0.0))
        opening = {
            "x_min": float(inner["x_min"]),
            "x_max": float(inner["x_max"]),
            "y_min": float(inner["y_min"]),
            "y_max": float(inner["y_max"]),
            "support_z": float(support_z),
            "source": "inner_bounds",
        }
        return _copy_release_opening_metadata(opening, metadata)
    lower, upper = _aabb_lower_upper(scene, surface_name)
    if lower is None or upper is None:
        return None
    opening = {
        "x_min": float(lower[0]),
        "x_max": float(upper[0]),
        "y_min": float(lower[1]),
        "y_max": float(upper[1]),
        "support_z": float(lower[2]),
        "source": "aabb",
    }
    return _copy_release_opening_metadata(opening, metadata)


def _caddy_compartment_from_surface_label(surface_label: Optional[str]) -> str:
    low = str(surface_label or "").strip().lower()
    if "caddy" not in low:
        return ""
    for compartment in ("front", "back", "left", "right"):
        if f"_{compartment}_" in low or low.endswith(f"_{compartment}"):
            return compartment
    return ""


def _caddy_compartment_opening_from_scene(
    scene: SceneState,
    surface_name: Optional[str],
    surface_label: Optional[str],
    serialized_opening: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    compartment = _caddy_compartment_from_surface_label(surface_label)
    if not compartment:
        return None
    if not surface_name or "caddy" not in str(surface_name).lower():
        return None
    serialized = serialized_opening if isinstance(serialized_opening, Mapping) else {}
    return _serialized_caddy_compartment_opening(surface_name, surface_label, serialized, compartment)


def _xy_in_bounds(xy: np.ndarray, bounds: Optional[Dict[str, Any]], slop: float = 1e-6) -> bool:
    if not bounds:
        return False
    return bool(
        float(bounds["x_min"]) - slop <= float(xy[0]) <= float(bounds["x_max"]) + slop
        and float(bounds["y_min"]) - slop <= float(xy[1]) <= float(bounds["y_max"]) + slop
    )


def _opening_center_xy(bounds: Dict[str, Any]) -> np.ndarray:
    return np.asarray(
        [0.5 * (float(bounds["x_min"]) + float(bounds["x_max"])), 0.5 * (float(bounds["y_min"]) + float(bounds["y_max"]))],
        dtype=np.float32,
    )


def _margin_shrunk_opening(bounds: Dict[str, Any], margin: float) -> Dict[str, Any]:
    x_min = float(bounds["x_min"]) + float(margin)
    x_max = float(bounds["x_max"]) - float(margin)
    y_min = float(bounds["y_min"]) + float(margin)
    y_max = float(bounds["y_max"]) - float(margin)
    if x_min > x_max or y_min > y_max:
        center = _opening_center_xy(bounds)
        x_min = x_max = float(center[0])
        y_min = y_max = float(center[1])
    out = dict(bounds)
    out.update({"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "source": "high_drop_release_opening"})
    return out


def _high_drop_release_opening(opening: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _release_mode(opening) != "high_drop_into_compartment":
        return None
    margin = max(0.0, min(0.05, _float_from_mapping(opening, "release_xy_margin_m", 0.0)))
    return _margin_shrunk_opening(opening, margin)


def _release_z_max(opening: Dict[str, Any], cfg: LiberoRobotClientConfig) -> float:
    z_max = float(cfg.place_release_z_max_m)
    if _release_mode(opening) == "high_drop_into_compartment":
        offset = max(0.0, min(0.20, _float_from_mapping(opening, "release_z_offset_m", z_max)))
        tolerance = max(0.0, min(0.10, _float_from_mapping(opening, "release_z_tolerance_m", 0.04)))
        z_max = max(z_max, offset + tolerance)
    return z_max


def _planned_virtual_opening(
    target_xy: np.ndarray,
    support_z: float,
    cfg: LiberoRobotClientConfig,
) -> Dict[str, Any]:
    half_span = max(float(cfg.place_drop_align_xy_m), float(cfg.place_release_xy_min_m), 0.035)
    return {
        "x_min": float(target_xy[0] - half_span),
        "x_max": float(target_xy[0] + half_span),
        "y_min": float(target_xy[1] - half_span),
        "y_max": float(target_xy[1] + half_span),
        "support_z": float(support_z),
        "source": "planned_virtual_surface",
    }


def _opening_from_serialized_step(step: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    raw = step.get("surface_opening") if isinstance(step, Mapping) else None
    if not isinstance(raw, Mapping):
        return None
    if not all(key in raw for key in ("x_min", "x_max", "y_min", "y_max")):
        return None
    support_z = raw.get("support_z", raw.get("z_min", raw.get("z", 0.0)))
    try:
        opening = {
            "x_min": float(raw["x_min"]),
            "x_max": float(raw["x_max"]),
            "y_min": float(raw["y_min"]),
            "y_max": float(raw["y_max"]),
            "support_z": float(support_z),
            "source": str(raw.get("source") or "serialized_surface_opening"),
        }
    except (TypeError, ValueError):
        return None
    for key in _RELEASE_OPENING_METADATA_KEYS:
        if key in raw:
            opening[key] = raw[key]
    return opening


def _planner_frame_pose_from_opening(
    opening: Mapping[str, Any],
    scene: SceneState,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    origin_raw = opening.get("planner_frame_origin_world")
    quat_raw = opening.get("planner_frame_quat_world_wxyz")
    try:
        origin = np.asarray(origin_raw, dtype=np.float64).reshape(-1)[:3]
        quat = np.asarray(quat_raw, dtype=np.float64).reshape(-1)[:4]
    except (TypeError, ValueError):
        origin = np.zeros(0, dtype=np.float64)
        quat = np.zeros(0, dtype=np.float64)
    if origin.size == 3 and quat.size == 4 and np.all(np.isfinite(origin)) and np.all(np.isfinite(quat)):
        return origin, quat
    base_pose = robot_base_pose(scene)
    if base_pose is None:
        return None
    base_origin, base_quat, _base_source = base_pose
    return base_origin, base_quat


def _opening_to_world_frame(opening: Optional[Mapping[str, Any]], scene: SceneState) -> Optional[Dict[str, Any]]:
    if not isinstance(opening, Mapping):
        return None
    out = dict(opening)
    frame = str(out.get("coordinate_frame") or "").strip().lower()
    planner_frame = str(out.get("planner_frame") or "").strip().lower()
    planner_like = frame in {"planner_frame", "robot_base", "robot0_base"} or planner_frame in {
        "robot0_base",
        "mount0_base",
        "mount0_controller_box",
        "mount0_pedestal",
    }
    if not planner_like:
        out.setdefault("coordinate_frame", "world")
        out.setdefault("opening_frame_conversion_applied", False)
        out.setdefault("opening_frame_conversion_reason", "already_world_or_unspecified")
        return out
    pose = _planner_frame_pose_from_opening(out, scene)
    if pose is None:
        out["opening_frame_conversion_applied"] = False
        out["opening_frame_conversion_reason"] = "missing_planner_frame_pose"
        return out
    origin_world, quat_world_wxyz = pose
    try:
        x_min = float(out["x_min"])
        x_max = float(out["x_max"])
        y_min = float(out["y_min"])
        y_max = float(out["y_max"])
        support_z = float(out["support_z"])
    except (KeyError, TypeError, ValueError):
        out["opening_frame_conversion_applied"] = False
        out["opening_frame_conversion_reason"] = "invalid_opening_bounds"
        return out

    corners = np.asarray(
        [
            [x_min, y_min, support_z],
            [x_min, y_max, support_z],
            [x_max, y_min, support_z],
            [x_max, y_max, support_z],
        ],
        dtype=np.float64,
    )
    world_corners = np.stack(
        [base_to_world_position(corner, origin_world, quat_world_wxyz) for corner in corners],
        axis=0,
    )
    center = np.asarray([0.5 * (x_min + x_max), 0.5 * (y_min + y_max), support_z], dtype=np.float64)
    world_center = base_to_world_position(center, origin_world, quat_world_wxyz)

    out.update(
        {
            "x_min": float(np.min(world_corners[:, 0])),
            "x_max": float(np.max(world_corners[:, 0])),
            "y_min": float(np.min(world_corners[:, 1])),
            "y_max": float(np.max(world_corners[:, 1])),
            "support_z": float(world_center[2]),
            "coordinate_frame": "world",
            "opening_frame_conversion_applied": True,
            "opening_frame_conversion_reason": "planner_frame_to_world",
            "opening_center_xy_planner": [float(center[0]), float(center[1])],
            "opening_center_xy_world": [float(world_center[0]), float(world_center[1])],
            "support_z_planner": support_z,
            "support_z_world": float(world_center[2]),
        }
    )
    return out


def _shrunk_opening(bounds: Dict[str, Any], hx: float, hy: float, margin: float) -> Dict[str, float]:
    x_min = float(bounds["x_min"]) + float(hx) + float(margin)
    x_max = float(bounds["x_max"]) - float(hx) - float(margin)
    y_min = float(bounds["y_min"]) + float(hy) + float(margin)
    y_max = float(bounds["y_max"]) - float(hy) - float(margin)
    if x_min > x_max or y_min > y_max:
        center = _opening_center_xy(bounds)
        return {
            "x_min": float(center[0]),
            "x_max": float(center[0]),
            "y_min": float(center[1]),
            "y_max": float(center[1]),
            "shrunk": False,
        }
    return {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "shrunk": True}


def _shrunk_span_m(shrunk: Dict[str, Any]) -> float:
    return min(
        max(float(shrunk.get("x_max", 0.0) - shrunk.get("x_min", 0.0)), 0.0),
        max(float(shrunk.get("y_max", 0.0) - shrunk.get("y_min", 0.0)), 0.0),
    )


def _place_lift_target_z(ee_z: float, surf_top: float, hanging: float, cfg: LiberoRobotClientConfig) -> float:
    """Keep the vessel above the rim while translating; rim_clearance is for the drop only."""
    return max(
        float(ee_z),
        float(surf_top) + float(cfg.place_hover_clearance_m) + float(hanging),
    )


def _high_drop_release_target_ee_z(
    scene: SceneState,
    obj_name: Optional[str],
    support_z: float,
    opening: Optional[Mapping[str, Any]],
) -> Tuple[Optional[float], Dict[str, Any]]:
    if _release_mode(opening) != "high_drop_into_compartment":
        return None, {}
    obj = scene.objects.get(obj_name) if obj_name else None
    if obj is None or obj.pos is None:
        return None, {"release_mode": "high_drop_into_compartment", "reason": "missing_object_state"}
    ee_z = float(scene.ee_pos[2])
    obj_z = float(obj.pos[2])
    ee_to_object_z = ee_z - obj_z
    release_z_offset = max(0.0, min(0.20, _float_from_mapping(opening or {}, "release_z_offset_m", 0.10)))
    target_object_z = float(support_z) + release_z_offset
    target_ee_z = target_object_z + ee_to_object_z
    return target_ee_z, {
        "release_mode": "high_drop_into_compartment",
        "release_z_offset_m": release_z_offset,
        "target_object_z": target_object_z,
        "ee_to_object_z": ee_to_object_z,
        "target_ee_z": target_ee_z,
    }


def _place_release_accepts(details: Dict[str, Any], cfg: LiberoRobotClientConfig) -> bool:
    if not details.get("z_ok") or not details.get("in_opening"):
        return False
    if str(details.get("release_mode") or "").strip().lower() == "high_drop_into_compartment":
        if details.get("requires_footprint_release"):
            center_dist = details.get("footprint_center_xy_dist")
            if center_dist is None:
                center_dist = details.get("xy_dist", float("inf"))
            return _footprint_contained_with_tolerance(
                details,
                float(cfg.place_footprint_release_tolerance_m),
            ) and float(center_dist) <= float(cfg.place_align_center_tolerance_m)
        return bool(details.get("in_release_opening", details.get("in_opening")))
    xy_dist = float(details.get("xy_dist") or 1e9)
    align = float(cfg.place_drop_align_xy_m)
    shrunk = details.get("shrunk_opening") or {}
    if not shrunk.get("shrunk") or _shrunk_span_m(shrunk) < align:
        return xy_dist <= align
    return bool(details.get("in_shrunk"))


def _footprint_contained_with_tolerance(details: Mapping[str, Any], tolerance_m: float) -> bool:
    if bool(details.get("footprint_contained")):
        return True
    if details.get("footprint_fits") is False:
        return False
    violation = details.get("footprint_violation_m")
    if violation is None:
        return False
    return float(violation) <= max(0.0, float(tolerance_m))


def _xy_half_extent_m(obj: ObjectState, scene: SceneState) -> float:
    geom = estimate_object_geometry(obj, scene)
    he = list(geom.half_extents or [])
    if len(he) >= 2:
        return max(0.015, min(float(he[0]), float(he[1])))
    return max(0.015, float(geom.radius) * 0.7)


def _place_footprint_limits(
    scene: SceneState,
    obj_name: Optional[str],
    surface_name: Optional[str],
    cfg: LiberoRobotClientConfig,
    opening_override: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {"object": obj_name, "surface": surface_name}
    opening = dict(opening_override) if isinstance(opening_override, Mapping) else _opening_bounds(scene, surface_name)
    hx, hy = _object_half_xy(scene, obj_name)
    details.update({"object_hx_m": float(hx), "object_hy_m": float(hy)})
    if opening is None:
        details["allowed_xy_m"] = float(cfg.place_release_xy_min_m)
        return details
    shrunk = _shrunk_opening(opening, hx, hy, float(cfg.place_release_margin_m))
    center = _opening_center_xy(opening)
    details.update(
        {
            "opening": dict(opening),
            "shrunk_opening": dict(shrunk),
            "opening_center_xy": center.astype(float).tolist(),
            "allowed_xy_m": float(
                max(
                    cfg.place_release_xy_min_m,
                    0.5 * min(max(shrunk["x_max"] - shrunk["x_min"], 0.0), max(shrunk["y_max"] - shrunk["y_min"], 0.0)),
                )
            ),
        }
    )
    return details


def _place_release_geometry(
    scene: SceneState,
    obj_name: Optional[str],
    surface_name: Optional[str],
    cfg: LiberoRobotClientConfig,
    opening_override: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    details = _place_footprint_limits(scene, obj_name, surface_name, cfg, opening_override=opening_override)
    if not obj_name:
        details["release_guard_reason"] = "missing_object_name"
        return False, details
    obj = scene.objects.get(obj_name)
    if obj is None or obj.pos is None:
        details["release_guard_reason"] = "missing_object_state"
        return False, details
    opening = details.get("opening")
    shrunk = details.get("shrunk_opening")
    if not opening or not shrunk:
        details["release_guard_reason"] = "missing_opening_bounds"
        return False, details
    release_opening = _high_drop_release_opening(opening)
    surface_label = str(opening.get("surface_label") or "")
    requires_footprint_release = _is_book_caddy_compartment_release(
        obj_name,
        surface_name,
        surface_label,
        opening,
    )
    safe_opening = _safe_release_opening_xy(opening, cfg)
    object_footprint = _object_xy_footprint(scene, obj_name)
    footprint_details: Dict[str, Any] = {}
    if object_footprint is not None and safe_opening is not None:
        _delta, footprint_details = _footprint_center_alignment_delta(
            object_footprint,
            safe_opening,
            float(cfg.place_align_center_tolerance_m),
        )
    xy = np.asarray(obj.pos[:2], dtype=np.float32)
    center = _opening_center_xy(opening)
    support_z = float(opening.get("support_z", obj.pos[2]))
    z_delta = float(obj.pos[2] - support_z)
    in_full = _xy_in_bounds(xy, opening)
    in_release_opening = _xy_in_bounds(xy, release_opening) if release_opening else in_full
    in_shrunk = bool(shrunk.get("shrunk")) and _xy_in_bounds(xy, shrunk)
    xy_dist = float(np.linalg.norm(xy - center))
    release_z_max = _release_z_max(opening, cfg)
    z_ok = bool(-0.04 <= z_delta <= release_z_max)
    details.update(
        {
            "object_xy": xy.astype(float).tolist(),
            "xy_dist": xy_dist,
            "z_delta": z_delta,
            "object_z": float(obj.pos[2]),
            "support_z": support_z,
            "release_mode": _release_mode(opening),
            "release_z_max_m": release_z_max,
            "release_opening": release_opening,
            "safe_opening_xy": safe_opening,
            "object_footprint_xy": object_footprint,
            "footprint_delta_xy": footprint_details.get("delta_xy"),
            "containment_delta_xy": footprint_details.get("containment_delta_xy"),
            "footprint_violation_m": footprint_details.get("footprint_violation_m"),
            "footprint_center_xy": footprint_details.get("footprint_center_xy"),
            "safe_center_xy": footprint_details.get("safe_center_xy"),
            "footprint_center_delta_xy": footprint_details.get("footprint_center_delta_xy"),
            "footprint_center_xy_dist": footprint_details.get("footprint_center_xy_dist"),
            "center_tolerance_m": footprint_details.get("center_tolerance_m"),
            "footprint_centered": footprint_details.get("centered"),
            "footprint_contained": footprint_details.get("contained"),
            "footprint_contained_with_tolerance": _footprint_contained_with_tolerance(
                footprint_details,
                float(cfg.place_footprint_release_tolerance_m),
            ),
            "footprint_release_tolerance_m": float(cfg.place_footprint_release_tolerance_m),
            "footprint_fits": footprint_details.get("fits"),
            "oversize_axes": footprint_details.get("oversize_axes"),
            "requires_footprint_release": requires_footprint_release,
            "in_opening": in_full,
            "in_release_opening": in_release_opening,
            "in_shrunk": in_shrunk,
            "z_ok": z_ok,
        }
    )
    ok = _place_release_accepts(details, cfg)
    if ok:
        details["release_guard_reason"] = "ok"
    elif not z_ok:
        details["release_guard_reason"] = "z_not_in_release_band"
    elif not in_full:
        details["release_guard_reason"] = "xy_not_in_opening"
    elif release_opening is not None and not in_release_opening:
        details["release_guard_reason"] = "xy_not_in_release_opening"
    elif requires_footprint_release and not _footprint_contained_with_tolerance(
        details,
        float(cfg.place_footprint_release_tolerance_m),
    ):
        details["release_guard_reason"] = "footprint_not_contained"
    elif requires_footprint_release and not bool(details.get("footprint_centered")):
        details["release_guard_reason"] = "footprint_center_not_aligned"
    elif bool(shrunk.get("shrunk")) and not in_shrunk:
        details["release_guard_reason"] = "xy_not_in_shrunk_opening"
    else:
        details["release_guard_reason"] = "xy_alignment_too_large"
    return ok, details


def _object_xy_footprint(scene: SceneState, obj_name: Optional[str]) -> Optional[Dict[str, float]]:
    lower, upper = _aabb_lower_upper(scene, obj_name)
    if lower is None or upper is None:
        return None
    return {
        "x_min": float(lower[0]),
        "x_max": float(upper[0]),
        "y_min": float(lower[1]),
        "y_max": float(upper[1]),
    }


def _safe_release_opening_xy(opening: Optional[Mapping[str, Any]], cfg: LiberoRobotClientConfig) -> Optional[Dict[str, Any]]:
    if not isinstance(opening, Mapping):
        return None
    if not all(key in opening for key in ("x_min", "x_max", "y_min", "y_max")):
        return None
    base = dict(opening)
    safe = _high_drop_release_opening(base)
    if safe is None:
        safe = _margin_shrunk_opening(base, float(cfg.place_release_margin_m))
        safe["source"] = "safe_release_opening"
    return safe


def _footprint_containment_delta(
    footprint: Mapping[str, Any],
    safe: Mapping[str, Any],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    details: Dict[str, Any] = {"axes": {}, "oversize_axes": []}
    deltas: List[float] = []
    residuals: List[float] = []
    violations: List[float] = []
    for axis in ("x", "y"):
        lo = float(footprint[f"{axis}_min"])
        hi = float(footprint[f"{axis}_max"])
        safe_lo = float(safe[f"{axis}_min"])
        safe_hi = float(safe[f"{axis}_max"])
        if hi < lo:
            lo, hi = hi, lo
        if safe_hi < safe_lo:
            safe_lo, safe_hi = safe_hi, safe_lo
        span = max(0.0, hi - lo)
        safe_span = max(0.0, safe_hi - safe_lo)
        violation = max(0.0, safe_lo - lo, hi - safe_hi)
        fits = span <= safe_span + 1e-9
        if not fits:
            delta = 0.5 * (safe_lo + safe_hi) - 0.5 * (lo + hi)
            reason = "oversize_center"
            details["oversize_axes"].append(axis)
        elif lo < safe_lo:
            delta = safe_lo - lo
            reason = "min_outside"
        elif hi > safe_hi:
            delta = safe_hi - hi
            reason = "max_outside"
        else:
            delta = 0.0
            reason = "inside"
        shifted_lo = lo + delta
        shifted_hi = hi + delta
        residual = max(0.0, safe_lo - shifted_lo, shifted_hi - safe_hi)
        deltas.append(float(delta))
        residuals.append(float(residual))
        violations.append(float(violation))
        details["axes"][axis] = {
            "min": lo,
            "max": hi,
            "safe_min": safe_lo,
            "safe_max": safe_hi,
            "span_m": span,
            "safe_span_m": safe_span,
            "fits": fits,
            "reason": reason,
            "delta_m": float(delta),
            "violation_m": float(violation),
            "residual_after_delta_m": float(residual),
        }
    delta_xy = np.asarray(deltas, dtype=np.float32)
    details.update(
        {
            "delta_xy": delta_xy.astype(float).tolist(),
            "delta_norm_m": float(np.linalg.norm(delta_xy)),
            "footprint_violation_m": float(max(violations) if violations else 0.0),
            "residual_after_delta_m": float(max(residuals) if residuals else 0.0),
            "contained": bool(max(violations) <= 1e-9 if violations else True),
            "fits": bool(not details["oversize_axes"]),
        }
    )
    return delta_xy, details


def _rect_center_xy(rect: Mapping[str, Any]) -> np.ndarray:
    return np.asarray(
        [
            0.5 * (float(rect["x_min"]) + float(rect["x_max"])),
            0.5 * (float(rect["y_min"]) + float(rect["y_max"])),
        ],
        dtype=np.float32,
    )


def _shift_footprint_xy(footprint: Mapping[str, Any], delta_xy: np.ndarray) -> Dict[str, float]:
    delta = np.asarray(delta_xy, dtype=np.float32).reshape(-1)[:2]
    return {
        "x_min": float(footprint["x_min"]) + float(delta[0]),
        "x_max": float(footprint["x_max"]) + float(delta[0]),
        "y_min": float(footprint["y_min"]) + float(delta[1]),
        "y_max": float(footprint["y_max"]) + float(delta[1]),
    }


def _footprint_center_alignment_delta(
    footprint: Mapping[str, Any],
    safe: Mapping[str, Any],
    center_tolerance_m: float,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    containment_delta, containment = _footprint_containment_delta(footprint, safe)
    footprint_center = _rect_center_xy(footprint)
    safe_center = _rect_center_xy(safe)
    desired_center_delta = safe_center - footprint_center
    axis_deltas: List[float] = []
    axis_details: Dict[str, Any] = {}
    for axis_idx, axis in enumerate(("x", "y")):
        lo = float(footprint[f"{axis}_min"])
        hi = float(footprint[f"{axis}_max"])
        safe_lo = float(safe[f"{axis}_min"])
        safe_hi = float(safe[f"{axis}_max"])
        if hi < lo:
            lo, hi = hi, lo
        if safe_hi < safe_lo:
            safe_lo, safe_hi = safe_hi, safe_lo
        span = max(0.0, hi - lo)
        safe_span = max(0.0, safe_hi - safe_lo)
        requested = float(desired_center_delta[axis_idx])
        if span <= safe_span + 1e-9:
            min_delta = safe_lo - lo
            max_delta = safe_hi - hi
            delta = min(max(requested, min_delta), max_delta)
            reason = "center_clamped_to_containment" if abs(delta - requested) > 1e-9 else "center"
        else:
            min_delta = max_delta = None
            delta = float(containment_delta[axis_idx])
            reason = "oversize_center"
        axis_deltas.append(float(delta))
        axis_details[axis] = {
            "requested_center_delta_m": requested,
            "delta_m": float(delta),
            "min_containment_delta_m": min_delta,
            "max_containment_delta_m": max_delta,
            "reason": reason,
        }
    delta_xy = np.asarray(axis_deltas, dtype=np.float32)
    shifted_footprint = _shift_footprint_xy(footprint, delta_xy)
    _shifted_delta, shifted = _footprint_containment_delta(shifted_footprint, safe)
    shifted_center = footprint_center + delta_xy
    center_delta_after = safe_center - shifted_center
    center_dist = float(np.linalg.norm(safe_center - footprint_center))
    center_dist_after = float(np.linalg.norm(center_delta_after))
    center_tol = max(0.0, float(center_tolerance_m))
    current_centered = bool(center_dist <= center_tol)
    centered_after = bool(center_dist_after <= center_tol)
    details = dict(containment)
    details.update(
        {
            "alignment_policy": "footprint_center_and_containment",
            "containment_delta_xy": containment_delta.astype(float).tolist(),
            "delta_xy": delta_xy.astype(float).tolist(),
            "axis_alignment": axis_details,
            "footprint_center_xy": footprint_center.astype(float).tolist(),
            "safe_center_xy": safe_center.astype(float).tolist(),
            "footprint_center_delta_xy": desired_center_delta.astype(float).tolist(),
            "footprint_center_xy_dist": center_dist,
            "center_tolerance_m": center_tol,
            "centered": current_centered,
            "shifted_footprint_xy": shifted_footprint,
            "center_delta_after_xy": center_delta_after.astype(float).tolist(),
            "center_dist_after_delta_m": center_dist_after,
            "centered_after_delta": centered_after,
            "contained_after_delta": shifted.get("contained"),
            "footprint_violation_after_delta_m": shifted.get("footprint_violation_m"),
            "success_after_delta": bool(shifted.get("contained")) and bool(centered_after),
            "alignment_error_m": max(
                float(containment.get("footprint_violation_m", 0.0) or 0.0),
                max(0.0, center_dist - center_tol),
            ),
        }
    )
    return delta_xy, details


def _ee_xy_for_bowl_over_plate(scene: SceneState, obj_name: Optional[str], plate_xy: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    ee_xy = scene.ee_pos[:2].astype(np.float32)
    obj = scene.objects.get(obj_name) if obj_name else None
    if obj is None or obj.pos is None:
        return plate_xy.astype(np.float32), np.zeros(2, dtype=np.float32), None
    bowl_xy = np.asarray(obj.pos[:2], dtype=np.float32)
    offset = bowl_xy - ee_xy
    return (np.asarray(plate_xy, dtype=np.float32) - offset).astype(np.float32), offset, bowl_xy


def _move_ee_xyz(
    client: "LiberoRobotClient",
    goal_xyz: np.ndarray,
    gripper: float,
    max_steps: int,
    reached_m: float,
    label: str,
) -> Dict[str, Any]:
    cfg = client.cfg
    old = (
        cfg.near_goal_position_m,
        cfg.trajectory_final_reached_threshold,
        cfg.trajectory_reached_threshold,
        cfg.trajectory_waypoint_max_steps,
    )
    try:
        limit = max(1, int(max_steps))
        reached = max(0.001, float(reached_m))
        cfg.near_goal_position_m = reached
        cfg.trajectory_final_reached_threshold = reached
        cfg.trajectory_reached_threshold = min(float(cfg.trajectory_reached_threshold), reached)
        cfg.trajectory_waypoint_max_steps = limit
        return client.execute_cartesian_waypoints(
            [np.asarray(goal_xyz, dtype=float).reshape(3).tolist()],
            gripper=float(gripper),
            max_steps=limit,
            label=label,
        )
    finally:
        (
            cfg.near_goal_position_m,
            cfg.trajectory_final_reached_threshold,
            cfg.trajectory_reached_threshold,
            cfg.trajectory_waypoint_max_steps,
        ) = old


_ENTRY_RETREAT_BLOCKER_HINTS = ("cabinet", "drawer")
_ENTRY_ESCAPE_PROFILES: Dict[str, Dict[str, Any]] = {
    "current_away_blocker": {
        "lift_m": 0.100,
        "lift_max_steps": 30,
        "lift_reached_m": 0.008,
        "steps": [
            {"kind": "away_blocker", "distance_m": 0.080, "max_steps": 28, "reached_m": 0.015},
        ],
    },
    "high_lift_then_away": {
        "lift_m": 0.120,
        "lift_max_steps": 36,
        "lift_reached_m": 0.008,
        "steps": [
            {"kind": "away_blocker", "distance_m": 0.100, "max_steps": 34, "reached_m": 0.015},
        ],
    },
    "target_side_stage": {
        "lift_m": 0.100,
        "lift_max_steps": 30,
        "lift_reached_m": 0.008,
        "steps": [
            {
                "kind": "target_side_stage",
                "stand_off_m": 0.110,
                "max_xy_motion_m": 0.180,
                "max_steps": 36,
                "reached_m": 0.018,
            },
        ],
    },
    "table_front_escape": {
        "lift_m": 0.120,
        "lift_max_steps": 36,
        "lift_reached_m": 0.008,
        "steps": [
            {"kind": "front_away_blocker", "distance_m": 0.120, "max_steps": 40, "reached_m": 0.018},
        ],
    },
    "two_step_escape": {
        "lift_m": 0.120,
        "lift_max_steps": 36,
        "lift_reached_m": 0.008,
        "steps": [
            {"kind": "away_blocker", "distance_m": 0.060, "max_steps": 24, "reached_m": 0.015},
            {
                "kind": "target_side_stage",
                "stand_off_m": 0.120,
                "max_xy_motion_m": 0.160,
                "max_steps": 36,
                "reached_m": 0.018,
            },
        ],
    },
}


def _entry_retreat_direction_xy(scene: SceneState) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Return a unit XY direction that moves away from the nearest drawer/cabinet blocker."""
    ee_xy = np.asarray(scene.ee_pos[:2], dtype=np.float32)
    candidates: List[Dict[str, Any]] = []
    for obj in scene.objects.values():
        low = str(obj.name or "").lower()
        if obj.pos is None or not any(token in low for token in _ENTRY_RETREAT_BLOCKER_HINTS):
            continue
        xy = np.asarray(obj.pos[:2], dtype=np.float32)
        dist = float(np.linalg.norm(ee_xy - xy))
        candidates.append({"name": obj.name, "xy": xy, "distance_m": dist, "source": "scene_object"})

    contact_names = []
    for contact in scene.contacts or []:
        for key in ("finger_object", "object1", "object2"):
            name = contact.get(key)
            low = str(name or "").lower()
            if name and any(token in low for token in _ENTRY_RETREAT_BLOCKER_HINTS):
                contact_names.append(str(name))
    if contact_names:
        contact_set = set(contact_names)
        for cand in candidates:
            if str(cand["name"]) in contact_set:
                cand["source"] = "contact_object"
                cand["distance_m"] = -1.0 + float(cand["distance_m"])

    candidates.sort(key=lambda item: float(item["distance_m"]))
    details: Dict[str, Any] = {
        "strategy": "away_from_nearest_drawer_or_cabinet",
        "candidate_count": len(candidates),
        "contact_blocker_names": sorted(set(contact_names)),
    }
    if candidates:
        blocker = candidates[0]
        direction = ee_xy - np.asarray(blocker["xy"], dtype=np.float32)
        norm = float(np.linalg.norm(direction))
        details.update(
            {
                "blocker_name": blocker["name"],
                "blocker_xy": np.asarray(blocker["xy"], dtype=np.float32).astype(float).tolist(),
                "blocker_source": blocker["source"],
                "raw_direction_xy": direction.astype(float).tolist(),
                "raw_norm_m": norm,
            }
        )
        if norm >= 1e-4:
            unit = (direction / norm).astype(np.float32)
            details["direction_xy"] = unit.astype(float).tolist()
            return unit, details

    # Last resort: move opposite the table-side positive X direction. This path
    # should rarely be used; the event records it explicitly for diagnosis.
    fallback = np.asarray([-1.0, 0.0], dtype=np.float32)
    details.update({"strategy": "fallback_negative_x", "direction_xy": fallback.astype(float).tolist()})
    return fallback, details


def _entry_front_escape_direction_xy(scene: SceneState) -> Tuple[np.ndarray, Dict[str, Any]]:
    away, details = _entry_retreat_direction_xy(scene)
    direction = np.asarray([away[0], min(float(away[1]), -0.45)], dtype=np.float32)
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-6:
        direction = np.asarray([0.0, -1.0], dtype=np.float32)
    else:
        direction = direction / norm
    out = dict(details)
    out.update({"strategy": "front_biased_away_from_drawer_or_cabinet", "direction_xy": direction.astype(float).tolist()})
    return direction.astype(np.float32), out


def _entry_target_object(scene: SceneState) -> Tuple[Optional[ObjectState], Dict[str, Any]]:
    ee_xy = np.asarray(scene.ee_pos[:2], dtype=np.float32)
    scored: List[Tuple[int, float, str, ObjectState]] = []
    for obj in scene.objects.values():
        low = str(obj.name or "").lower()
        if obj.pos is None or "bowl" not in low:
            continue
        score = 0 if ("black" in low or "akita" in low) else 1
        dist = float(np.linalg.norm(np.asarray(obj.pos[:2], dtype=np.float32) - ee_xy))
        scored.append((score, dist, obj.name, obj))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    details = {"candidate_count": len(scored)}
    if not scored:
        return None, details
    obj = scored[0][3]
    details.update({"target_name": obj.name, "target_xy": obj.pos[:2].astype(float).tolist()})
    return obj, details


def _entry_stage_target_from_spec(
    scene: SceneState,
    spec: Mapping[str, Any],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    current = scene.ee_pos[:3].astype(np.float32).copy()
    kind = str(spec.get("kind") or "away_blocker")
    if kind == "front_away_blocker":
        direction, details = _entry_front_escape_direction_xy(scene)
        goal = current.copy()
        goal[:2] += direction * float(spec.get("distance_m", 0.10))
        details.update({"kind": kind, "target_ee_pos": goal.astype(float).tolist()})
        return goal, details

    if kind == "target_side_stage":
        target, target_details = _entry_target_object(scene)
        away, away_details = _entry_retreat_direction_xy(scene)
        details = {"kind": kind, "target": target_details, "away": away_details}
        if target is None or target.pos is None:
            goal = current.copy()
            goal[:2] += away * float(spec.get("distance_m", 0.08))
            details.update({"fallback": "away_blocker_no_target", "target_ee_pos": goal.astype(float).tolist()})
            return goal, details
        direction = away
        blocker_xy = away_details.get("blocker_xy")
        if isinstance(blocker_xy, list) and len(blocker_xy) >= 2:
            raw = np.asarray(target.pos[:2], dtype=np.float32) - np.asarray(blocker_xy[:2], dtype=np.float32)
            raw_norm = float(np.linalg.norm(raw))
            if raw_norm >= 1e-4:
                direction = (raw / raw_norm).astype(np.float32)
        stand_off = float(spec.get("stand_off_m", 0.11))
        goal = current.copy()
        goal[:2] = np.asarray(target.pos[:2], dtype=np.float32) + direction * stand_off
        max_xy = float(spec.get("max_xy_motion_m", 0.0) or 0.0)
        delta = goal[:2] - current[:2]
        delta_norm = float(np.linalg.norm(delta))
        if max_xy > 0.0 and delta_norm > max_xy:
            goal[:2] = current[:2] + delta * (max_xy / max(delta_norm, 1e-6))
            details["xy_motion_clipped_m"] = max_xy
        details.update(
            {
                "direction_xy": direction.astype(float).tolist(),
                "stand_off_m": stand_off,
                "target_ee_pos": goal.astype(float).tolist(),
            }
        )
        return goal, details

    direction, details = _entry_retreat_direction_xy(scene)
    goal = current.copy()
    goal[:2] += direction * float(spec.get("distance_m", 0.08))
    details.update({"kind": kind, "target_ee_pos": goal.astype(float).tolist()})
    return goal, details


def _entry_escape_plan_from_config(cfg: LiberoRobotClientConfig) -> Dict[str, Any]:
    profile_name = str(cfg.recovery_entry_escape_profile or "").strip()
    if profile_name:
        profile = _ENTRY_ESCAPE_PROFILES.get(profile_name)
        if profile is not None:
            return {"profile": profile_name, **profile}
        return {
            "profile": profile_name,
            "profile_error": "unknown_recovery_entry_escape_profile",
            "lift_m": cfg.recovery_entry_lift_m,
            "lift_max_steps": cfg.recovery_entry_lift_max_steps,
            "lift_reached_m": cfg.recovery_entry_lift_reached_m,
            "steps": [
                {
                    "kind": "away_blocker",
                    "distance_m": cfg.recovery_entry_retreat_m,
                    "max_steps": cfg.recovery_entry_retreat_max_steps,
                    "reached_m": cfg.recovery_entry_retreat_reached_m,
                }
            ],
        }
    return {
        "profile": "legacy_lift_then_optional_away",
        "lift_m": cfg.recovery_entry_lift_m,
        "lift_max_steps": cfg.recovery_entry_lift_max_steps,
        "lift_reached_m": cfg.recovery_entry_lift_reached_m,
        "steps": [
            {
                "kind": "away_blocker",
                "distance_m": cfg.recovery_entry_retreat_m,
                "max_steps": cfg.recovery_entry_retreat_max_steps,
                "reached_m": cfg.recovery_entry_retreat_reached_m,
            }
        ],
    }


def execute_recovery_entry_lift(
    env: Any,
    obs: Dict[str, Any],
    client_cfg: LiberoRobotClientConfig | None = None,
    max_env_steps: int = 120,
    step_callback: Callable[[Dict[str, Any], Dict[str, Any]], None] | None = None,
    holding_latch: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Move the end effector to a cleaner entry pose before recovery planning."""
    cfg = client_cfg or LiberoRobotClientConfig()
    client = LiberoRobotClient(env, obs, cfg=cfg, step_callback=step_callback, holding_latch=holding_latch)
    start_scene = client.get_scene()
    start_pos = start_scene.ee_pos[:3].astype(np.float32).copy()
    escape_plan = _entry_escape_plan_from_config(cfg)
    lift_m = max(0.0, float(escape_plan.get("lift_m", cfg.recovery_entry_lift_m)))
    max_steps = min(max(0, int(escape_plan.get("lift_max_steps", cfg.recovery_entry_lift_max_steps))), max(0, int(max_env_steps)))
    reached_m = max(0.001, float(escape_plan.get("lift_reached_m", cfg.recovery_entry_lift_reached_m)))
    gripper = float(np.clip(cfg.recovery_entry_lift_gripper_value, -1.0, 1.0))
    step_specs = [dict(item) for item in (escape_plan.get("steps") or []) if isinstance(item, Mapping)]
    target_pos = start_pos.copy()
    target_pos[2] = float(target_pos[2] + lift_m)
    event: Dict[str, Any] = {
        "event": "recovery_entry_lift",
        "executed": False,
        "success": False,
        "escape_profile": str(escape_plan.get("profile") or ""),
        "escape_profile_error": escape_plan.get("profile_error"),
        "escape_step_specs": step_specs,
        "configured_lift_m": lift_m,
        "max_steps": max_steps,
        "reached_m": reached_m,
        "gripper_value": gripper,
        "start_ee_pos": start_pos.astype(float).tolist(),
        "target_ee_pos": target_pos.astype(float).tolist(),
        "rotation_cmd_locked": True,
        "xy_cmd_locked": True,
        "retreat_rotation_cmd_locked": True,
        "env_steps": 0,
        "steps": [],
    }
    if lift_m <= 0.0 or max_steps <= 0:
        event["reason"] = "entry_lift_disabled"
        end_scene = client.get_scene()
        event["end_ee_pos"] = end_scene.ee_pos[:3].astype(float).tolist()
        return client.get_obs(), event

    steps: List[Dict[str, Any]] = []
    for _ in range(max_steps):
        scene = client.get_scene()
        before = scene.ee_pos[:3].astype(np.float32).copy()
        z_error = float(target_pos[2] - before[2])
        if z_error <= reached_m:
            break
        dz = min(z_error, float(cfg.trajectory_max_delta))
        action = np.zeros(7, dtype=np.float32)
        action[2] = np.clip(
            float(cfg.trajectory_gain) * dz / max(float(cfg.trajectory_action_scale), 1e-6),
            0.0,
            float(cfg.trajectory_max_cmd),
        )
        action[6] = gripper
        if abs(float(action[2])) <= 1e-6:
            break
        client._step(action, label="recovery_entry_lift", phase="recovery_entry_lift", step_type="trajectory")
        after = client.get_scene().ee_pos[:3].astype(np.float32).copy()
        steps.append(
            {
                "before_ee_pos": before.astype(float).tolist(),
                "after_ee_pos": after.astype(float).tolist(),
                "z_error_before_m": z_error,
                "z_error_after_m": float(target_pos[2] - after[2]),
                "action": action.astype(float).tolist(),
            }
        )
        if client.done:
            break

    end_scene = client.get_scene()
    end_pos = end_scene.ee_pos[:3].astype(np.float32).copy()
    actual_lift = float(end_pos[2] - start_pos[2])
    final_z_error = float(target_pos[2] - end_pos[2])
    success = bool(final_z_error <= reached_m or actual_lift >= max(0.0, lift_m - reached_m))
    escape_step_events: List[Dict[str, Any]] = []
    for step_idx, spec in enumerate(step_specs):
        step_kind = str(spec.get("kind") or "away_blocker")
        step_max = int(spec.get("max_steps", cfg.recovery_entry_retreat_max_steps))
        if step_kind in {"away_blocker", "front_away_blocker"} and float(spec.get("distance_m", 0.0) or 0.0) <= 0.0:
            escape_step_events.append(
                {
                    "step_idx": step_idx,
                    "kind": step_kind,
                    "executed": False,
                    "success": True,
                    "reason": "zero_distance",
                }
            )
            continue
        if client.done:
            escape_step_events.append(
                {
                    "step_idx": step_idx,
                    "kind": step_kind,
                    "executed": False,
                    "success": False,
                    "reason": "env_done_before_step",
                }
            )
            success = False
            break
        remaining_steps = max(0, int(max_env_steps) - int(client.num_env_steps))
        step_steps = min(max(0, step_max), remaining_steps)
        if step_steps <= 0:
            escape_step_events.append(
                {
                    "step_idx": step_idx,
                    "kind": step_kind,
                    "executed": False,
                    "success": False,
                    "reason": "no_remaining_recovery_budget",
                }
            )
            success = False
            break
        retreat_start = client.get_scene().ee_pos[:3].astype(np.float32).copy()
        retreat_target, target_details = _entry_stage_target_from_spec(client.get_scene(), spec)
        reached = max(0.001, float(spec.get("reached_m", cfg.recovery_entry_retreat_reached_m)))
        retreat_result = _move_ee_xyz(
            client,
            retreat_target,
            gripper=gripper,
            max_steps=step_steps,
            reached_m=reached,
            label=f"recovery_entry_{step_kind}",
        )
        retreat_end = client.get_scene().ee_pos[:3].astype(np.float32).copy()
        step_event = {
            "step_idx": step_idx,
            "kind": step_kind,
            "executed": True,
            "success": bool(retreat_result.get("success")),
            "error": str(retreat_result.get("error") or ""),
            "start_ee_pos": retreat_start.astype(float).tolist(),
            "target_ee_pos": retreat_target.astype(float).tolist(),
            "end_ee_pos": retreat_end.astype(float).tolist(),
            "xy_motion_m": float(np.linalg.norm(retreat_end[:2] - retreat_start[:2])),
            "endpoint_error_m": float(np.linalg.norm(retreat_target - retreat_end)),
            "env_steps": int(retreat_result.get("env_steps") or 0),
            "target_details": target_details,
            "result": retreat_result,
        }
        escape_step_events.append(step_event)
        success = bool(success and step_event["success"])
        if not step_event["success"]:
            break
    final_scene = client.get_scene()
    legacy_retreat_event = escape_step_events[0] if escape_step_events else {"executed": False, "success": True}
    event.update(
        {
            "executed": True,
            "success": bool(success),
            "done": bool(client.done),
            "end_ee_pos": end_pos.astype(float).tolist(),
            "final_ee_pos": final_scene.ee_pos[:3].astype(float).tolist(),
            "ee_lift_m": actual_lift,
            "xy_shift_m": float(np.linalg.norm(final_scene.ee_pos[:2] - start_pos[:2])),
            "final_z_error_m": final_z_error,
            "env_steps": int(client.num_env_steps),
            "steps": steps,
            "escape_steps": escape_step_events,
            "retreat": legacy_retreat_event,
            "client_events": list(client.events),
        }
    )
    return client.get_obs(), event


def _rotate_held_object_world_z_yaw(
    client: "LiberoRobotClient",
    obj_name: Optional[str],
    gripper: float,
    remaining_steps: int,
    label: str,
) -> Dict[str, Any]:
    """After hover, rotate only about world z so the thin edge lines up with +x."""
    cfg = client.cfg
    policy = str(getattr(cfg, "place_yaw_after_hover", "") or "").strip().lower()
    if policy not in {"world_z_thin_x", "thin_horizontal_along_world_x"}:
        return {"success": True, "skipped": "policy_off", "env_steps": 0}
    remaining = max(0, int(remaining_steps))
    if remaining <= 0:
        return {"success": True, "skipped": "no_budget", "env_steps": 0, "continued": True}
    now = client.get_scene()
    current_yaw = _object_thin_horizontal_yaw(now, obj_name)
    hx, hy = _object_half_xy(now, obj_name)
    if current_yaw is None:
        return {
            "success": True,
            "skipped": "no_object_yaw",
            "env_steps": 0,
            "continued": True,
            "object_hx_m": float(hx),
            "object_hy_m": float(hy),
        }
    target_yaw, delta_yaw = _nearest_signed_yaw_delta(current_yaw, (0.0, np.pi))
    reached = max(0.06, float(cfg.place_yaw_reached_rad))
    if abs(delta_yaw) <= reached:
        return {
            "success": True,
            "skipped": "already_aligned",
            "env_steps": 0,
            "current_yaw_rad": float(current_yaw),
            "target_yaw_rad": float(target_yaw),
            "delta_yaw_rad": float(delta_yaw),
            "object_hx_m": float(hx),
            "object_hy_m": float(hy),
        }
    waypoints = _world_z_yaw_pose_waypoints(
        now.ee_pos[:3],
        now.ee_quat,
        delta_yaw,
        float(cfg.place_yaw_step_rad),
    )
    if not waypoints:
        return {"success": True, "skipped": "no_waypoints", "env_steps": 0, "continued": True}
    budget = min(int(cfg.place_yaw_after_hover_max_steps), remaining)
    old = (
        cfg.orientation_max_cmd,
        cfg.orientation_action_scale,
        cfg.orientation_waypoint_spacing,
        cfg.trajectory_waypoint_max_steps,
        cfg.orientation_final_reached_threshold,
        cfg.orientation_reached_threshold,
    )
    try:
        cfg.orientation_max_cmd = min(float(cfg.orientation_max_cmd), float(cfg.place_yaw_max_cmd))
        cfg.orientation_action_scale = min(float(cfg.orientation_action_scale), 0.40)
        cfg.orientation_waypoint_spacing = min(float(cfg.orientation_waypoint_spacing), max(0.08, float(cfg.place_yaw_step_rad) * 0.85))
        per_wp = max(4, min(8, budget // max(1, len(waypoints))))
        cfg.trajectory_waypoint_max_steps = per_wp
        cfg.orientation_reached_threshold = min(float(cfg.orientation_reached_threshold), 0.18)
        cfg.orientation_final_reached_threshold = max(float(cfg.orientation_final_reached_threshold), reached)
        result = client.execute_cartesian_pose_waypoints(
            waypoints,
            gripper=float(gripper),
            max_steps=budget,
            label=f"{label}:place_hover_yaw",
        )
    finally:
        (
            cfg.orientation_max_cmd,
            cfg.orientation_action_scale,
            cfg.orientation_waypoint_spacing,
            cfg.trajectory_waypoint_max_steps,
            cfg.orientation_final_reached_threshold,
            cfg.orientation_reached_threshold,
        ) = old
    after = client.get_scene()
    after_yaw = _object_thin_horizontal_yaw(after, obj_name)
    after_hx, after_hy = _object_half_xy(after, obj_name)
    compact = {k: v for k, v in result.items() if k != "waypoints"}
    compact.update(
        {
            "continued": True,
            "current_yaw_rad": float(current_yaw),
            "target_yaw_rad": float(target_yaw),
            "delta_yaw_rad": float(delta_yaw),
            "final_yaw_rad": None if after_yaw is None else float(after_yaw),
            "object_hx_m": float(after_hx),
            "object_hy_m": float(after_hy),
            "initial_object_hx_m": float(hx),
            "initial_object_hy_m": float(hy),
        }
    )
    return compact


def _is_caddy_compartment_release(
    surface_name: Optional[str],
    surface_label: Optional[str],
    opening: Optional[Mapping[str, Any]],
) -> bool:
    low = " ".join(
        [
            str(surface_name or ""),
            str(surface_label or ""),
            str((opening or {}).get("surface_label") or ""),
            str((opening or {}).get("source") or ""),
        ]
    ).lower()
    return "caddy" in low and any(part in low for part in ("front", "back", "left", "right"))


def _is_book_caddy_compartment_release(
    obj_name: Optional[str],
    surface_name: Optional[str],
    surface_label: Optional[str],
    opening: Optional[Mapping[str, Any]],
) -> bool:
    return "book" in str(obj_name or "").lower() and _is_caddy_compartment_release(
        surface_name,
        surface_label,
        opening,
    )


def _execute_place_held_object_xy_align(
    client: "LiberoRobotClient",
    obj_name: Optional[str],
    surface_name: Optional[str],
    surface_label: Optional[str],
    release_opening: Optional[Mapping[str, Any]],
    target_xy: np.ndarray,
    gripper: float,
    remaining_steps: int,
    label: str,
) -> Tuple[Dict[str, Any], int]:
    cfg = client.cfg
    remaining = max(0, int(remaining_steps))
    event: Dict[str, Any] = {
        "success": True,
        "error": "",
        "executed": False,
        "env_steps": 0,
        "surface_label": surface_label,
        "surface_resolved": surface_name,
        "opening_source": None if release_opening is None else release_opening.get("source"),
        "opening_center_xy": np.asarray(target_xy, dtype=float).reshape(-1)[:2].astype(float).tolist(),
    }
    if not bool(cfg.place_held_object_xy_align):
        event["skipped"] = "disabled"
        return event, remaining
    if not obj_name:
        event.update({"success": False, "error": "missing_object_name", "skipped": "missing_object_name"})
        return event, remaining
    if not isinstance(release_opening, Mapping):
        event.update({"success": False, "error": "missing_opening", "skipped": "missing_opening"})
        return event, remaining
    caddy_compartment = _is_caddy_compartment_release(surface_name, surface_label, release_opening)
    book_caddy_compartment = _is_book_caddy_compartment_release(obj_name, surface_name, surface_label, release_opening)
    if not caddy_compartment:
        event["skipped"] = "non_caddy_compartment"
        return event, remaining
    max_iters = min(max(0, int(cfg.place_align_max_iters)), remaining)
    if max_iters <= 0:
        event["skipped"] = "no_budget"
        return event, remaining

    reached = max(0.001, float(cfg.place_align_reached_m))
    center_tolerance = max(reached, float(cfg.place_align_center_tolerance_m))
    footprint_tolerance = max(0.0, float(cfg.place_footprint_release_tolerance_m))
    step_clip = max(0.004, float(cfg.place_align_step_clip_m))
    per_iter_steps = max(1, int(cfg.place_align_max_steps_per_iter))
    target_xy = np.asarray(target_xy, dtype=np.float32).reshape(-1)[:2]
    iterations: List[Dict[str, Any]] = []
    executed = False
    final_geom: Dict[str, Any] = {}
    final_footprint: Optional[Dict[str, float]] = None
    final_safe_opening: Optional[Dict[str, Any]] = None
    final_footprint_details: Dict[str, Any] = {}
    final_alignment_mode = "center_fallback"
    final_alignment_error = float("inf")
    final_err = float("inf")
    final_in_opening = False
    retry_lift_count = 0
    for idx in range(max_iters):
        now = client.get_scene()
        ok, geom = _place_release_geometry(now, obj_name, surface_name, cfg, opening_override=dict(release_opening))
        final_geom = geom
        final_err = float(geom.get("xy_dist", float("inf")))
        final_in_opening = bool(geom.get("in_release_opening") or geom.get("in_opening") or ok)
        object_xy = np.asarray(geom.get("object_xy") or [], dtype=np.float32).reshape(-1)
        if object_xy.size < 2:
            obj = now.objects.get(obj_name)
            if obj is None or obj.pos is None:
                event.update(
                    {
                        "success": False,
                        "error": "missing_object_state",
                        "skipped": "missing_object_state",
                        "iterations": iterations,
                    }
                )
                return event, remaining
            object_xy = np.asarray(obj.pos[:2], dtype=np.float32)

        current_xy = np.asarray(now.ee_pos[:2], dtype=np.float32)
        safe_opening = _safe_release_opening_xy(release_opening, cfg)
        footprint = _object_xy_footprint(now, obj_name)
        footprint_details: Optional[Dict[str, Any]] = None
        alignment_mode = "center_fallback"
        align_error = final_err
        if footprint is not None and safe_opening is not None:
            if book_caddy_compartment:
                delta, footprint_details = _footprint_center_alignment_delta(
                    footprint,
                    safe_opening,
                    center_tolerance,
                )
                alignment_mode = "footprint_center_and_containment"
                align_error = float(footprint_details.get("alignment_error_m", float("inf")))
            else:
                delta, footprint_details = _footprint_containment_delta(footprint, safe_opening)
                alignment_mode = "footprint_containment"
                align_error = float(footprint_details.get("footprint_violation_m", float("inf")))
            ee_target_xy = current_xy + delta
            grasp_offset = object_xy[:2] - current_xy
            final_footprint = footprint
            final_safe_opening = safe_opening
            final_footprint_details = footprint_details
        else:
            ee_target_xy, grasp_offset, _ = _ee_xy_for_bowl_over_plate(now, obj_name, target_xy)
            delta = ee_target_xy - current_xy

        final_alignment_mode = alignment_mode
        final_alignment_error = align_error
        footprint_contained = _footprint_contained_with_tolerance(footprint_details or {}, footprint_tolerance)
        footprint_centered = bool((footprint_details or {}).get("centered"))
        should_stop = (
            footprint_contained and footprint_centered
            if alignment_mode == "footprint_center_and_containment"
            else footprint_contained
            if alignment_mode == "footprint_containment"
            else align_error <= reached
        )
        if should_stop:
            skipped = "already_aligned"
            if alignment_mode == "footprint_center_and_containment":
                skipped = "already_centered_and_contained"
            elif alignment_mode == "footprint_containment":
                skipped = "already_contained"
            iterations.append(
                {
                    "iter": idx,
                    "skipped": skipped,
                    "alignment_mode": alignment_mode,
                    "object_xy": object_xy[:2].astype(float).tolist(),
                    "object_footprint_xy": footprint,
                    "safe_opening_xy": safe_opening,
                    "footprint": footprint_details,
                    "footprint_violation_m": None
                    if footprint_details is None
                    else float(footprint_details.get("footprint_violation_m", 0.0)),
                    "footprint_center_xy_dist": None
                    if footprint_details is None
                    else footprint_details.get("footprint_center_xy_dist"),
                    "center_tolerance_m": center_tolerance,
                    "footprint_contained_with_tolerance": footprint_contained,
                    "footprint_release_tolerance_m": footprint_tolerance,
                    "xy_dist": final_err,
                    "alignment_error_m": align_error,
                    "in_opening": final_in_opening,
                    "release_guard_reason": geom.get("release_guard_reason"),
                }
            )
            break

        delta_norm = float(np.linalg.norm(delta))
        if delta_norm <= 1e-5 or (
            alignment_mode not in {"footprint_containment", "footprint_center_and_containment"} and delta_norm <= reached
        ):
            skipped = "ee_already_at_target"
            if alignment_mode == "footprint_center_and_containment":
                skipped = (
                    "footprint_oversize"
                    if (footprint_details or {}).get("oversize_axes")
                    else "footprint_center_delta_below_threshold"
                )
            elif alignment_mode == "footprint_containment":
                skipped = "footprint_oversize" if (footprint_details or {}).get("oversize_axes") else "footprint_delta_below_threshold"
            iterations.append(
                {
                    "iter": idx,
                    "skipped": skipped,
                    "alignment_mode": alignment_mode,
                    "object_xy": object_xy[:2].astype(float).tolist(),
                    "object_footprint_xy": footprint,
                    "safe_opening_xy": safe_opening,
                    "footprint": footprint_details,
                    "footprint_violation_m": None
                    if footprint_details is None
                    else float(footprint_details.get("footprint_violation_m", 0.0)),
                    "footprint_center_xy_dist": None
                    if footprint_details is None
                    else footprint_details.get("footprint_center_xy_dist"),
                    "center_tolerance_m": center_tolerance,
                    "footprint_contained_with_tolerance": footprint_contained,
                    "footprint_release_tolerance_m": footprint_tolerance,
                    "target_ee_xy": ee_target_xy.astype(float).tolist(),
                    "grasp_offset_xy": grasp_offset.astype(float).tolist(),
                    "xy_dist": final_err,
                    "alignment_error_m": align_error,
                    "in_opening": final_in_opening,
                    "release_guard_reason": geom.get("release_guard_reason"),
                }
            )
            break

        clipped_delta = delta
        clipped = False
        if delta_norm > step_clip:
            clipped_delta = delta * (step_clip / max(delta_norm, 1e-6))
            clipped = True
        goal_xy = current_xy + clipped_delta
        goal = np.asarray([float(goal_xy[0]), float(goal_xy[1]), float(now.ee_pos[2])], dtype=np.float32)
        budget = min(per_iter_steps, remaining)
        if budget <= 0:
            break
        move = _move_ee_xyz(
            client,
            goal,
            gripper,
            budget,
            min(reached, max(0.005, float(np.linalg.norm(clipped_delta)) * 0.5)),
            f"{label}:held_object_xy_align",
        )
        used = int(move.get("env_steps") or 0)
        remaining = max(0, remaining - used)
        executed = True
        after = client.get_scene()
        ok_after, geom_after = _place_release_geometry(
            after,
            obj_name,
            surface_name,
            cfg,
            opening_override=dict(release_opening),
        )
        final_geom = geom_after
        final_err = float(geom_after.get("xy_dist", float("inf")))
        final_in_opening = bool(geom_after.get("in_release_opening") or geom_after.get("in_opening") or ok_after)
        footprint_after = _object_xy_footprint(after, obj_name)
        footprint_details_after: Optional[Dict[str, Any]] = None
        align_error_after = final_err
        if alignment_mode == "footprint_containment" and footprint_after is not None and safe_opening is not None:
            _, footprint_details_after = _footprint_containment_delta(footprint_after, safe_opening)
            align_error_after = float(footprint_details_after.get("footprint_violation_m", float("inf")))
            final_footprint = footprint_after
            final_safe_opening = safe_opening
            final_footprint_details = footprint_details_after
        elif alignment_mode == "footprint_center_and_containment" and footprint_after is not None and safe_opening is not None:
            _, footprint_details_after = _footprint_center_alignment_delta(
                footprint_after,
                safe_opening,
                center_tolerance,
            )
            align_error_after = float(footprint_details_after.get("alignment_error_m", float("inf")))
            final_footprint = footprint_after
            final_safe_opening = safe_opening
            final_footprint_details = footprint_details_after
        final_alignment_mode = alignment_mode
        final_alignment_error = align_error_after
        iterations.append(
            {
                "iter": idx,
                "alignment_mode": alignment_mode,
                "object_xy_before": object_xy[:2].astype(float).tolist(),
                "object_footprint_xy_before": footprint,
                "object_footprint_xy_after": footprint_after,
                "safe_opening_xy": safe_opening,
                "footprint_before": footprint_details,
                "footprint_after": footprint_details_after,
                "footprint_violation_before_m": None
                if footprint_details is None
                else float(footprint_details.get("footprint_violation_m", 0.0)),
                "footprint_violation_after_m": None
                if footprint_details_after is None
                else float(footprint_details_after.get("footprint_violation_m", 0.0)),
                "footprint_center_xy_dist_before_m": None
                if footprint_details is None
                else footprint_details.get("footprint_center_xy_dist"),
                "footprint_center_xy_dist_after_m": None
                if footprint_details_after is None
                else footprint_details_after.get("footprint_center_xy_dist"),
                "center_tolerance_m": center_tolerance,
                "footprint_contained_with_tolerance_before": _footprint_contained_with_tolerance(
                    footprint_details or {},
                    footprint_tolerance,
                ),
                "footprint_contained_with_tolerance_after": _footprint_contained_with_tolerance(
                    footprint_details_after or {},
                    footprint_tolerance,
                ),
                "footprint_release_tolerance_m": footprint_tolerance,
                "target_ee_xy": ee_target_xy.astype(float).tolist(),
                "commanded_ee_xy": goal_xy.astype(float).tolist(),
                "grasp_offset_xy": grasp_offset.astype(float).tolist(),
                "xy_dist_before": float(geom.get("xy_dist", final_err)),
                "xy_dist_after": final_err,
                "alignment_error_before_m": align_error,
                "alignment_error_after_m": align_error_after,
                "step_xy_m": float(np.linalg.norm(clipped_delta)),
                "clipped": clipped,
                "in_opening_after": final_in_opening,
                "release_guard_reason_after": geom_after.get("release_guard_reason"),
                "move": {k: v for k, v in move.items() if k != "waypoints"},
            }
        )
        footprint_contained_after = _footprint_contained_with_tolerance(
            footprint_details_after or {},
            footprint_tolerance,
        )
        footprint_centered_after = bool((footprint_details_after or {}).get("centered"))
        if client.done or (
            footprint_contained_after and footprint_centered_after
            if alignment_mode == "footprint_center_and_containment"
            else footprint_contained_after
            if alignment_mode == "footprint_containment"
            else final_alignment_error <= reached
        ):
            break
        if used <= 0 or (not bool(move.get("success", False)) and move.get("error")):
            if (
                book_caddy_compartment
                and retry_lift_count < 1
                and remaining > 0
                and float(cfg.place_align_retry_lift_m) > 0.0
                and int(cfg.place_align_retry_lift_max_steps) > 0
            ):
                lift_scene = client.get_scene()
                lift_goal = lift_scene.ee_pos[:3].astype(np.float32).copy()
                lift_goal[2] = float(lift_goal[2] + float(cfg.place_align_retry_lift_m))
                lift = _move_ee_xyz(
                    client,
                    lift_goal,
                    gripper,
                    min(int(cfg.place_align_retry_lift_max_steps), remaining),
                    max(0.004, float(cfg.place_lift_reached_m)),
                    f"{label}:held_object_xy_align_retry_lift",
                )
                used_lift = int(lift.get("env_steps") or 0)
                retry_lift_count += 1
                remaining = max(0, remaining - used_lift)
                iterations[-1]["retry_lift"] = {k: v for k, v in lift.items() if k != "waypoints"}
                if used_lift > 0 and not client.done:
                    continue
            break

    final_success = bool(event.get("success", True))
    final_error = str(event.get("error") or "")
    if final_alignment_mode == "footprint_center_and_containment":
        final_success = _footprint_contained_with_tolerance(final_footprint_details, footprint_tolerance) and bool(
            final_footprint_details.get("centered", False)
        )
        if not final_success:
            final_error = (
                "place_footprint_oversize"
                if final_footprint_details.get("oversize_axes")
                else "place_footprint_not_contained"
                if not _footprint_contained_with_tolerance(final_footprint_details, footprint_tolerance)
                else "place_footprint_center_not_aligned"
            )
    elif final_alignment_mode == "footprint_containment":
        final_success = _footprint_contained_with_tolerance(final_footprint_details, footprint_tolerance)
        if not final_success:
            final_error = (
                "place_footprint_oversize"
                if final_footprint_details.get("oversize_axes")
                else "place_footprint_not_contained"
            )
    event.update(
        {
            "success": final_success,
            "error": final_error,
            "executed": executed,
            "skipped": "" if executed else event.get("skipped", "already_aligned"),
            "iterations": iterations,
            "env_steps": max(0, int(remaining_steps) - remaining),
            "alignment_mode": final_alignment_mode,
            "final_alignment_error_m": final_alignment_error,
            "final_xy_dist": final_err,
            "final_in_opening": final_in_opening,
            "release_guard_reason": final_geom.get("release_guard_reason"),
            "object_xy": final_geom.get("object_xy"),
            "xy_dist": final_geom.get("xy_dist", final_err),
            "object_footprint_xy": final_footprint,
            "safe_opening_xy": final_safe_opening,
            "footprint_delta_xy": final_footprint_details.get("delta_xy"),
            "containment_delta_xy": final_footprint_details.get("containment_delta_xy"),
            "footprint_violation_m": final_footprint_details.get("footprint_violation_m"),
            "final_footprint_violation_m": final_footprint_details.get("footprint_violation_m"),
            "footprint_center_xy": final_footprint_details.get("footprint_center_xy"),
            "safe_center_xy": final_footprint_details.get("safe_center_xy"),
            "footprint_center_delta_xy": final_footprint_details.get("footprint_center_delta_xy"),
            "footprint_center_xy_dist": final_footprint_details.get("footprint_center_xy_dist"),
            "final_footprint_center_xy_dist": final_footprint_details.get("footprint_center_xy_dist"),
            "center_tolerance_m": final_footprint_details.get("center_tolerance_m"),
            "footprint_centered": final_footprint_details.get("centered"),
            "residual_after_delta_m": final_footprint_details.get("residual_after_delta_m"),
            "footprint_contained": final_footprint_details.get("contained"),
            "footprint_contained_with_tolerance": _footprint_contained_with_tolerance(
                final_footprint_details,
                footprint_tolerance,
            ),
            "footprint_release_tolerance_m": footprint_tolerance,
            "footprint_fits": final_footprint_details.get("fits"),
            "oversize_axes": final_footprint_details.get("oversize_axes"),
        }
    )
    return event, remaining


def _execute_place_hover_and_drop(
    client: "LiberoRobotClient",
    executable_plan: List[Dict[str, Any]],
    start_idx: int,
    remaining_steps: int,
    label: str,
) -> Dict[str, Any]:
    """Lift clear of the rim, translate over the opening, then drop vertically."""
    cfg = client.cfg
    close_value = float(cfg.gripper_close_value)
    open_value = float(cfg.gripper_open_value)
    remaining = max(0, int(remaining_steps))
    scene = client.get_scene()
    obj_name, surface_name, surface_label = _place_args_from_label_details(label, scene)
    serialized_opening = None
    if 0 <= start_idx < len(executable_plan):
        serialized_opening = _opening_to_world_frame(_opening_from_serialized_step(executable_plan[start_idx]), scene)
    for step in executable_plan[start_idx:]:
        if "place(" not in str(step.get("label") or "").lower():
            break
        found_obj, found_surface, found_surface_label = _place_args_from_label_details(str(step.get("label") or ""), scene)
        obj_name = obj_name or found_obj
        surface_name = surface_name or found_surface
        surface_label = surface_label or found_surface_label
        serialized_opening = serialized_opening or _opening_to_world_frame(_opening_from_serialized_step(step), scene)

    joint_path = _last_place_joint_path(executable_plan, start_idx)
    planned_end = None
    if joint_path is not None:
        poses = _joint_path_to_ee_pose_waypoints(client.env, joint_path, scene.ee_quat)
        if poses:
            planned_end = np.asarray(poses[-1]["position"], dtype=np.float32).reshape(-1)[:3]

    surface = scene.objects.get(surface_name) if surface_name else None
    ee = scene.ee_pos[:3].astype(np.float32)
    opening = _opening_bounds(scene, surface_name)
    caddy_opening = _caddy_compartment_opening_from_scene(scene, surface_name, surface_label, serialized_opening)
    is_caddy_compartment_surface = bool(
        _caddy_compartment_from_surface_label(surface_label)
        and surface_name
        and "caddy" in str(surface_name).lower()
    )
    if caddy_opening is not None:
        opening = caddy_opening
    elif is_caddy_compartment_surface:
        return {
            "success": False,
            "error": "caddy_compartment_missing_serialized_opening",
            "opened": False,
            "events": [
                {
                    "event": "place_opening_error",
                    "surface": surface_name,
                    "surface_label": surface_label,
                    "reason": "caddy compartment placement requires serialized planner opening metadata",
                }
            ],
        }
    release_opening = opening or serialized_opening
    if release_opening is not None:
        target_xy = _opening_center_xy(release_opening)
        support_z = float(release_opening["support_z"])
    elif surface is not None and surface.pos is not None:
        target_xy = np.asarray(surface.pos[:2], dtype=np.float32)
        support_z = float(surface.pos[2])
    elif planned_end is not None:
        target_xy = planned_end[:2].copy()
        support_z = float(estimate_table_z(scene))
        release_opening = _planned_virtual_opening(target_xy, support_z, cfg)
    else:
        return {"success": False, "error": "place_missing_surface_and_planned_end", "opened": False}
    book_caddy_release = _is_book_caddy_compartment_release(obj_name, surface_name, surface_label, release_opening)

    obj_lower, _obj_upper = _aabb_lower_upper(scene, obj_name)
    _surf_lower, surf_upper = _aabb_lower_upper(scene, surface_name)
    obj_bottom = float(obj_lower[2]) if obj_lower is not None else float(ee[2] - 0.08)
    surf_top = float(surf_upper[2]) if surf_upper is not None else float(support_z + 0.04)
    hanging = max(0.01, float(ee[2]) - obj_bottom)
    lift_z = _place_lift_target_z(float(ee[2]), float(surf_top), hanging, cfg)
    drop_z = float(support_z) + float(cfg.place_rim_clearance_m) * 0.25 + hanging
    high_drop_ee_z, high_drop_details = _high_drop_release_target_ee_z(scene, obj_name, support_z, release_opening)
    if high_drop_ee_z is not None:
        drop_z = max(drop_z, float(high_drop_ee_z))
    if planned_end is not None:
        drop_z = max(drop_z, float(planned_end[2]) - 0.02)
    drop_z = min(drop_z, lift_z)

    limits = _place_footprint_limits(scene, obj_name, surface_name, cfg, opening_override=release_opening)
    ee_target_xy, grasp_offset, bowl_xy = _ee_xy_for_bowl_over_plate(scene, obj_name, target_xy)
    events: List[Dict[str, Any]] = [
        {
            "event": "place_targets",
            "object": obj_name,
            "surface": surface_name,
            "surface_label": surface_label,
            "surface_resolved": surface_name,
            "opening_source": None if release_opening is None else release_opening.get("source"),
            "opening_center_xy": target_xy.astype(float).tolist(),
            "opening_frame": None if release_opening is None else release_opening.get("coordinate_frame"),
            "opening_frame_conversion_applied": (
                None if release_opening is None else release_opening.get("opening_frame_conversion_applied")
            ),
            "opening_frame_conversion_reason": (
                None if release_opening is None else release_opening.get("opening_frame_conversion_reason")
            ),
            "opening_center_xy_planner": None if release_opening is None else release_opening.get("opening_center_xy_planner"),
            "opening_center_xy_world": None if release_opening is None else release_opening.get("opening_center_xy_world"),
            "support_z_planner": None if release_opening is None else release_opening.get("support_z_planner"),
            "support_z_world": None if release_opening is None else release_opening.get("support_z_world"),
            "object_aabb_bottom": obj_bottom,
            "surface_aabb_top": surf_top,
            "hanging_m": hanging,
            "lift_z": float(lift_z),
            "drop_z": float(drop_z),
            "high_drop_release": high_drop_details,
            "planned_end": None if planned_end is None else planned_end.astype(float).tolist(),
            "grasp_offset_xy": grasp_offset.astype(float).tolist(),
            "bowl_xy": None if bowl_xy is None else bowl_xy.astype(float).tolist(),
            **limits,
        }
    ]

    def _object_xy_error() -> Tuple[float, np.ndarray, np.ndarray, bool, Dict[str, Any]]:
        now = client.get_scene()
        ee_goal, offset, obj_xy = _ee_xy_for_bowl_over_plate(now, obj_name, target_xy)
        ok, geom = _place_release_geometry(now, obj_name, surface_name, cfg, opening_override=release_opening)
        err = float(geom.get("xy_dist", float("inf")))
        return err, ee_goal, offset, bool(geom.get("in_opening") or ok), geom

    lift_budget = min(int(cfg.place_lift_max_steps), remaining)
    lift_reached = float(cfg.place_lift_reached_m)
    already_high = float(ee[2]) >= float(lift_z) - lift_reached
    lift_result: Dict[str, Any] = {
        "success": True,
        "error": "",
        "skipped": "already_clear",
        "ee_z": float(ee[2]),
        "lift_z": float(lift_z),
        "surf_top": float(surf_top),
        "hanging_m": float(hanging),
        "env_steps": 0,
    }
    if lift_budget > 0 and not client.done and not already_high:
        lift_goal = np.asarray([float(ee[0]), float(ee[1]), float(lift_z)], dtype=np.float32)
        lift_result = _move_ee_xyz(
            client, lift_goal, close_value, lift_budget, lift_reached, f"{label}:lift"
        )
        lift_result["ee_z"] = float(ee[2])
        lift_result["lift_z"] = float(lift_z)
        lift_result["surf_top"] = float(surf_top)
        lift_result["hanging_m"] = float(hanging)
        remaining = max(0, remaining - int(lift_result.get("env_steps") or 0))
    events.append({"event": "place_lift", **{k: v for k, v in lift_result.items() if k != "waypoints"}})
    if client.done:
        return {"success": True, "error": "", "opened": False, "done": True, "place_events": events}

    after_lift = client.get_scene()
    obj_lower_now, _ = _aabb_lower_upper(after_lift, obj_name)
    obj_bottom_now = float(obj_lower_now[2]) if obj_lower_now is not None else float(after_lift.ee_pos[2] - hanging)
    bowl_clearance = float(obj_bottom_now - surf_top)
    events.append(
        {
            "event": "place_lift_clearance",
            "ee_z": float(after_lift.ee_pos[2]),
            "object_aabb_bottom": obj_bottom_now,
            "surface_aabb_top": float(surf_top),
            "bowl_clearance_m": bowl_clearance,
            "min_clearance_m": float(cfg.place_lift_min_clearance_m),
        }
    )
    if bowl_clearance < float(cfg.place_lift_min_clearance_m) and not client.done:
        if book_caddy_release:
            return {
                "success": False,
                "error": "place_lift_too_low",
                "opened": False,
                "abort_episode": True,
                "abort_reason": "book_caddy_place_lift_too_low",
                "bowl_clearance_m": bowl_clearance,
                "place_events": events,
            }
        return {
            "success": True,
            "error": "place_lift_too_low",
            "opened": False,
            "handoff_to_vla": True,
            "bowl_clearance_m": bowl_clearance,
            "place_events": events,
        }

    bowl_err, ee_target_xy, grasp_offset, in_opening, geom = _object_xy_error()
    hover_z = float(client.get_scene().ee_pos[2])
    if bool(cfg.held_transfer_keep_z) and remaining > 0 and not client.done:
        current = client.get_scene().ee_pos[:3].astype(np.float32)
        planned_z = float(planned_end[2]) if planned_end is not None else hover_z
        protected_z = _held_transfer_protected_z(float(current[2]), planned_z, cfg)
        guard_budget = min(
            remaining,
            int(cfg.held_transfer_max_steps) if int(cfg.held_transfer_max_steps) > 0 else remaining,
        )
        guard_result: Dict[str, Any] = {
            "success": True,
            "error": "",
            "skipped": "already_at_protected_z",
            "env_steps": 0,
        }
        if protected_z > float(current[2]) + float(cfg.held_transfer_reached_m) and guard_budget > 0:
            guard_goal = np.asarray([float(current[0]), float(current[1]), protected_z], dtype=np.float32)
            guard_result = _move_ee_xyz(
                client,
                guard_goal,
                close_value,
                guard_budget,
                float(cfg.held_transfer_reached_m),
                f"{label}:held_transfer_keep_z_lift",
            )
            remaining = max(0, remaining - int(guard_result.get("env_steps") or 0))
        after_guard = client.get_scene()
        events.append(
            {
                "event": "held_transfer_keep_z",
                "phase": "pre_place_hover",
                "start_z": float(current[2]),
                "planned_endpoint_z": planned_z,
                "protected_z": float(protected_z),
                "final_ee_z": float(after_guard.ee_pos[2]),
                "max_descent_m": float(cfg.held_transfer_max_descent_m),
                "z_margin_m": float(cfg.held_transfer_z_margin_m),
                **{k: v for k, v in guard_result.items() if k != "waypoints"},
            }
        )
        if client.done:
            return {"success": True, "error": "", "opened": False, "done": True, "place_events": events}
        if not bool(guard_result.get("success", False)):
            return {
                "success": False,
                "error": str(guard_result.get("error") or "held_transfer_keep_z_failed"),
                "opened": False,
                "place_events": events,
            }
        hover_z = float(after_guard.ee_pos[2])
    hover = np.asarray([float(ee_target_xy[0]), float(ee_target_xy[1]), hover_z], dtype=np.float32)
    hover_budget = min(int(cfg.place_hover_max_steps), remaining)
    hover_result: Dict[str, Any] = {"success": False, "error": "place_hover_no_budget"}
    if hover_budget > 0 and not client.done:
        hover_result = _move_ee_xyz(client, hover, close_value, hover_budget, float(cfg.place_hover_reached_m), f"{label}:hover")
        remaining = max(0, remaining - int(hover_result.get("env_steps") or 0))
    events.append({"event": "place_hover", **{k: v for k, v in hover_result.items() if k != "waypoints"}})
    if client.done:
        return {"success": True, "error": "", "opened": False, "done": True, "place_events": events}

    bowl_err, ee_target_xy, grasp_offset, in_opening, geom = _object_xy_error()
    events.append(
        {
            "event": "place_hover_xy",
            "ee_xy_to_opening": float(np.linalg.norm(client.get_scene().ee_pos[:2] - target_xy)),
            "bowl_xy_to_opening": bowl_err,
            "in_opening": in_opening,
            "grasp_offset_xy": grasp_offset.astype(float).tolist(),
            "surface_label": surface_label,
            "surface_resolved": surface_name,
            "opening_source": None if release_opening is None else release_opening.get("source"),
            "release_guard_reason": geom.get("release_guard_reason"),
            "object_xy": geom.get("object_xy"),
            "xy_dist": geom.get("xy_dist"),
        }
    )
    if (not in_opening) and bowl_err > float(cfg.place_drop_align_xy_m) and remaining > 4 and not client.done:
        correct = np.asarray(
            [float(ee_target_xy[0]), float(ee_target_xy[1]), float(client.get_scene().ee_pos[2])],
            dtype=np.float32,
        )
        corr = _move_ee_xyz(
            client,
            correct,
            close_value,
            min(int(cfg.place_xy_correct_max_steps), remaining),
            max(float(cfg.place_release_xy_min_m), 0.012),
            f"{label}:hover_xy_correct",
        )
        remaining = max(0, remaining - int(corr.get("env_steps") or 0))
        events.append({"event": "place_hover_xy_correct", **{k: v for k, v in corr.items() if k != "waypoints"}})
        bowl_err, ee_target_xy, grasp_offset, in_opening, geom = _object_xy_error()
        events.append(
            {
                "event": "place_hover_xy_after_correct",
                "bowl_xy_to_opening": bowl_err,
                "in_opening": in_opening,
                "surface_label": surface_label,
                "surface_resolved": surface_name,
                "opening_source": None if release_opening is None else release_opening.get("source"),
                "release_guard_reason": geom.get("release_guard_reason"),
                "object_xy": geom.get("object_xy"),
                "xy_dist": geom.get("xy_dist"),
            }
        )
    if (not in_opening) and bowl_err > float(cfg.place_drop_align_xy_m):
        if book_caddy_release:
            return {
                "success": False,
                "error": "place_hover_xy_not_aligned",
                "opened": False,
                "abort_episode": True,
                "abort_reason": "book_caddy_place_hover_xy_not_aligned",
                "bowl_xy_to_opening": bowl_err,
                "surface_label": surface_label,
                "surface_resolved": surface_name,
                "opening_source": None if release_opening is None else release_opening.get("source"),
                "release_guard_reason": geom.get("release_guard_reason"),
                "place_events": events,
            }
        return {
            "success": True,
            "error": "place_hover_xy_not_aligned",
            "opened": False,
            "handoff_to_vla": True,
            "bowl_xy_to_opening": bowl_err,
            "surface_label": surface_label,
            "surface_resolved": surface_name,
            "opening_source": None if release_opening is None else release_opening.get("source"),
            "release_guard_reason": geom.get("release_guard_reason"),
            "place_events": events,
        }

    yaw_result = _rotate_held_object_world_z_yaw(client, obj_name, close_value, remaining, label)
    remaining = max(0, remaining - int(yaw_result.get("env_steps") or 0))
    events.append({"event": "place_hover_yaw", **{k: v for k, v in yaw_result.items() if k != "waypoints"}})
    if client.done:
        return {"success": True, "error": "", "opened": False, "done": True, "place_events": events}

    align_result, remaining = _execute_place_held_object_xy_align(
        client,
        obj_name,
        surface_name,
        surface_label,
        release_opening,
        target_xy,
        close_value,
        remaining,
        label,
    )
    events.append({"event": "place_held_object_xy_align", **align_result})
    if book_caddy_release and not bool(align_result.get("success", True)):
        return {
            "success": False,
            "error": str(align_result.get("error") or "place_footprint_not_contained"),
            "opened": False,
            "abort_episode": True,
            "abort_reason": str(align_result.get("error") or "book_caddy_place_xy_alignment_failed"),
            "geometry": align_result,
            "place_events": events,
        }
    if client.done:
        return {"success": True, "error": "", "opened": False, "done": True, "place_events": events}
    bowl_err, ee_target_xy, grasp_offset, in_opening, geom = _object_xy_error()
    events.append(
        {
            "event": "place_after_yaw_align_xy",
            "bowl_xy_to_opening": bowl_err,
            "in_opening": in_opening,
            "grasp_offset_xy": grasp_offset.astype(float).tolist(),
            "surface_label": surface_label,
            "surface_resolved": surface_name,
            "opening_source": None if release_opening is None else release_opening.get("source"),
            "release_guard_reason": geom.get("release_guard_reason"),
            "object_xy": geom.get("object_xy"),
            "xy_dist": geom.get("xy_dist"),
        }
    )

    now = client.get_scene()
    obj_lower, _ = _aabb_lower_upper(now, obj_name)
    obj_bottom = float(obj_lower[2]) if obj_lower is not None else float(now.ee_pos[2] - hanging)
    hanging = max(0.01, float(now.ee_pos[2]) - obj_bottom)
    drop_z = min(float(now.ee_pos[2]), float(support_z) + 0.005 + hanging)
    high_drop_ee_z, high_drop_details = _high_drop_release_target_ee_z(now, obj_name, support_z, release_opening)
    if high_drop_ee_z is not None:
        drop_z = min(float(now.ee_pos[2]), max(drop_z, float(high_drop_ee_z)))
    drop_budget = min(int(cfg.place_drop_max_steps), remaining)
    drop_result: Dict[str, Any] = {"success": False, "error": "place_drop_no_budget"}
    if drop_budget > 0 and not client.done:
        caddy_closed_loop_drop = bool(
            cfg.place_drop_closed_loop_align
            and cfg.place_held_object_xy_align
            and _is_caddy_compartment_release(surface_name, surface_label, release_opening)
        )
        if caddy_closed_loop_drop:
            start_z = float(client.get_scene().ee_pos[2])
            slice_count = max(1, min(int(cfg.place_drop_align_slices), 6))
            if abs(start_z - float(drop_z)) <= 0.004:
                slice_count = 1
            z_targets = np.linspace(start_z, float(drop_z), slice_count + 1, dtype=np.float32)[1:]
            drop_slices: List[Dict[str, Any]] = []
            drop_env_steps = 0
            closed_loop_align_steps = 0
            remaining_drop_budget = drop_budget
            drop_success = True
            drop_error = ""
            for slice_index, z_goal in enumerate(z_targets):
                if client.done or remaining <= 0 or remaining_drop_budget <= 0:
                    break
                now_slice = client.get_scene()
                remaining_slices = max(1, len(z_targets) - slice_index)
                slice_budget = min(max(1, int(np.ceil(remaining_drop_budget / remaining_slices))), remaining)
                dz = abs(float(now_slice.ee_pos[2]) - float(z_goal))
                slice_reached = min(float(cfg.place_drop_reached_m), max(0.004, dz * 0.35))
                drop_goal = np.asarray(
                    [float(now_slice.ee_pos[0]), float(now_slice.ee_pos[1]), float(z_goal)],
                    dtype=np.float32,
                )
                move = _move_ee_xyz(
                    client,
                    drop_goal,
                    close_value,
                    slice_budget,
                    slice_reached,
                    f"{label}:drop_slice_{slice_index}",
                )
                used = int(move.get("env_steps") or 0)
                drop_env_steps += used
                remaining_drop_budget = max(0, remaining_drop_budget - used)
                remaining = max(0, remaining - used)
                drop_slices.append(
                    {
                        "slice": slice_index,
                        "target_z": float(z_goal),
                        "start_z": float(now_slice.ee_pos[2]),
                        "goal_xyz": drop_goal.astype(float).tolist(),
                        "reached_m": float(slice_reached),
                        "move": {k: v for k, v in move.items() if k != "waypoints"},
                    }
                )
                if not bool(move.get("success", False)) and move.get("error"):
                    drop_success = False
                    drop_error = str(move.get("error") or "place_drop_slice_failed")
                    break
                if client.done or remaining <= 0:
                    break
                align_slice_result, remaining = _execute_place_held_object_xy_align(
                    client,
                    obj_name,
                    surface_name,
                    surface_label,
                    release_opening,
                    target_xy,
                    close_value,
                    remaining,
                    f"{label}:drop_slice_{slice_index}",
                )
                closed_loop_align_steps += int(align_slice_result.get("env_steps") or 0)
                events.append(
                    {
                        "event": "place_drop_closed_loop_xy_align",
                        "drop_slice": slice_index,
                        **align_slice_result,
                    }
                )
            drop_result = {
                "success": drop_success,
                "error": drop_error,
                "closed_loop": True,
                "target_drop_z": float(drop_z),
                "start_z": float(start_z),
                "slices": drop_slices,
                "env_steps": drop_env_steps,
                "closed_loop_align_env_steps": closed_loop_align_steps,
            }
        else:
            drop = np.asarray([float(ee_target_xy[0]), float(ee_target_xy[1]), drop_z], dtype=np.float32)
            drop_result = _move_ee_xyz(client, drop, close_value, drop_budget, float(cfg.place_drop_reached_m), f"{label}:drop")
            remaining = max(0, remaining - int(drop_result.get("env_steps") or 0))
    events.append({"event": "place_drop", "high_drop_release": high_drop_details, **{k: v for k, v in drop_result.items() if k != "waypoints"}})
    if client.done:
        return {"success": True, "error": "", "opened": False, "done": True, "place_events": events}
    if book_caddy_release and (not bool(drop_result.get("success", False))):
        scene = client.get_scene()
        would_release, geom = _place_release_geometry(scene, obj_name, surface_name, cfg, opening_override=release_opening)
        geom = dict(geom)
        geom.update(
            {
                "release_guard_reason": "place_drop_not_reached",
                "would_release_without_drop_success": would_release,
                "drop_error": str(drop_result.get("error") or "place_drop_failed"),
            }
        )
        events.append(
            {
                "event": "place_release_check",
                "ok": False,
                "surface_label": surface_label,
                "surface_resolved": surface_name,
                "opening_source": None if release_opening is None else release_opening.get("source"),
                **geom,
            }
        )
        return {
            "success": False,
            "error": "place_drop_not_reached",
            "opened": False,
            "abort_episode": True,
            "abort_reason": "book_caddy_place_drop_not_reached",
            "geometry": geom,
            "place_events": events,
        }

    scene = client.get_scene()
    ok, geom = _place_release_geometry(scene, obj_name, surface_name, cfg, opening_override=release_opening)
    events.append(
        {
            "event": "place_release_check",
            "ok": ok,
            "surface_label": surface_label,
            "surface_resolved": surface_name,
            "opening_source": None if release_opening is None else release_opening.get("source"),
            **geom,
        }
    )
    if (not ok) and remaining > 8 and not client.done:
        bowl_err, ee_target_xy, _, in_opening, geom = _object_xy_error()
        retry = np.asarray(
            [float(ee_target_xy[0]), float(ee_target_xy[1]), float(client.get_scene().ee_pos[2])],
            dtype=np.float32,
        )
        retry_result = _move_ee_xyz(
            client,
            retry,
            close_value,
            min(int(cfg.place_xy_correct_max_steps), remaining),
            max(float(cfg.place_release_xy_min_m), 0.012),
            f"{label}:drop_xy_correct",
        )
        remaining = max(0, remaining - int(retry_result.get("env_steps") or 0))
        events.append({"event": "place_drop_xy_correct", **{k: v for k, v in retry_result.items() if k != "waypoints"}})
        scene = client.get_scene()
        ok, geom = _place_release_geometry(scene, obj_name, surface_name, cfg, opening_override=release_opening)
        events.append(
            {
                "event": "place_release_check_retry",
                "ok": ok,
                "surface_label": surface_label,
                "surface_resolved": surface_name,
                "opening_source": None if release_opening is None else release_opening.get("source"),
                **geom,
            }
        )
    if not ok:
        if book_caddy_release:
            return {
                "success": False,
                "error": "place_release_geometry_not_met",
                "opened": False,
                "abort_episode": True,
                "abort_reason": str(geom.get("release_guard_reason") or "book_caddy_place_release_geometry_not_met"),
                "geometry": geom,
                "place_events": events,
            }
        return {
            "success": True,
            "error": "place_release_geometry_not_met",
            "opened": False,
            "handoff_to_vla": True,
            "geometry": geom,
            "place_events": events,
        }

    open_result = client.open_gripper(label=f"{label}:open")
    dwell = min(max(0, int(cfg.place_open_dwell_steps)), remaining)
    if dwell > 0 and not client.done:
        client._gripper_action(open_value, steps=dwell, label=f"{label}:open_dwell")
        remaining = max(0, remaining - dwell)
    retreat_goal = client.get_scene().ee_pos[:3].astype(np.float32).copy()
    retreat_goal[2] = float(retreat_goal[2] + float(cfg.place_retreat_m))
    retreat_budget = min(int(cfg.place_retreat_max_steps), remaining)
    retreat_result: Dict[str, Any] = {}
    if retreat_budget > 0 and not client.done:
        retreat_result = _move_ee_xyz(client, retreat_goal, open_value, retreat_budget, 0.02, f"{label}:retreat")
    events.append({"event": "place_open", "open": {k: v for k, v in open_result.items() if k not in {"waypoints"}}, "dwell": dwell, "retreat": {k: v for k, v in retreat_result.items() if k != "waypoints"}})
    return {
        "success": bool(open_result.get("success") or client.done),
        "error": "" if (open_result.get("success") or client.done) else (open_result.get("error") or "place_open_failed"),
        "opened": True,
        "done": client.done,
        "geometry": geom,
        "place_events": events,
    }


def _split_pose_tail(
    poses: List[Dict[str, List[float]]],
    tail_m: float,
) -> Tuple[List[Dict[str, List[float]]], List[Dict[str, List[float]]]]:
    if not poses:
        return [], []
    if len(poses) == 1 or tail_m <= 0.0:
        return [], poses
    acc = 0.0
    cut = len(poses) - 1
    prev = np.asarray(poses[-1]["position"], dtype=np.float64)[:3]
    for idx in range(len(poses) - 2, -1, -1):
        point = np.asarray(poses[idx]["position"], dtype=np.float64)[:3]
        acc += float(np.linalg.norm(point - prev))
        if acc > float(tail_m):
            cut = idx + 1
            break
        prev = point
        cut = idx
    return poses[:cut], poses[cut:]


def _joint_interpolation_safe(q_start: Any, q_end: Any, cfg: LiberoRobotClientConfig) -> bool:
    start = np.asarray(q_start, dtype=np.float32).reshape(-1)[:7]
    end = np.asarray(q_end, dtype=np.float32).reshape(-1)[:7]
    if start.size != 7 or end.size != 7 or not np.all(np.isfinite(start)) or not np.all(np.isfinite(end)):
        return False
    delta = end - start
    return float(np.linalg.norm(delta)) <= float(cfg.joint_interp_max_l2_rad) and float(np.max(np.abs(delta))) <= float(
        cfg.joint_interp_max_abs_rad
    )


class LiberoRobotClient:
    """Small LIBERO adapter with the same shape as TiPToP's RobotClient.

    TiPToP executes cuTAMP plans as trajectory steps plus explicit gripper
    commands. LIBERO exposes delta end-effector actions instead of a real robot
    joint controller, so this adapter keeps the TiPToP interface while using
    bounded Cartesian delta tracking under the hood.
    """

    def __init__(
        self,
        env: Any,
        obs: Dict[str, Any],
        cfg: LiberoRobotClientConfig | None = None,
        step_callback: Callable[[Dict[str, Any], Dict[str, Any]], None] | None = None,
        holding_latch: Dict[str, Any] | None = None,
    ) -> None:
        self.env = env
        self.obs = obs
        self.cfg = cfg or LiberoRobotClientConfig()
        self.step_callback = step_callback
        self.holding_latch = holding_latch if isinstance(holding_latch, dict) else {}
        self.num_env_steps = 0
        self.done = False
        self.events: List[Dict[str, Any]] = []

    def get_obs(self) -> Dict[str, Any]:
        return self.obs

    def get_scene(self) -> SceneState:
        scene = read_scene(self.env, self.obs)
        _apply_confirmed_holding_latch(scene, self.holding_latch)
        return scene

    def confirmed_holding_object(self) -> Optional[str]:
        return _confirmed_holding_latch_object(self.holding_latch)

    def latch_confirmed_holding(self, obj_name: str, label: str, snapshot: Dict[str, Any] | None = None) -> None:
        record = _set_confirmed_holding_latch(
            self.holding_latch,
            obj_name,
            source="lift_probe",
            label=label,
            snapshot=snapshot,
        )
        if record:
            self.events.append({"type": "holding_latch", "action": "set", **record})

    def clear_confirmed_holding(self, reason: str) -> None:
        record = _clear_confirmed_holding_latch(self.holding_latch, reason)
        if record:
            self.events.append({"type": "holding_latch", "action": "clear", **record})

    def _step(self, action: np.ndarray, label: str = "", phase: str = "", step_type: str = "") -> Dict[str, Any]:
        action_arr = np.asarray(action, dtype=np.float32)
        self.obs, _, done, _ = self.env.step(action_arr.tolist())
        self.num_env_steps += 1
        self.done = bool(done)
        if self.step_callback is not None:
            self.step_callback(
                self.obs,
                {
                    "env_step": self.num_env_steps,
                    "label": label,
                    "phase": phase,
                    "type": step_type,
                    "done": self.done,
                    "action": action_arr.astype(float).tolist(),
                },
            )
        return self.obs

    def _gripper_action(self, value: float, steps: Optional[int] = None, label: str = "gripper") -> Dict[str, Any]:
        action = np.zeros(7, dtype=np.float32)
        action[6] = float(value)
        for _ in range(steps or self.cfg.gripper_steps):
            self._step(action, label=label, phase="gripper", step_type="gripper")
            if self.done:
                return {"success": True, "done": True}
        return {"success": True, "done": False}

    @staticmethod
    def _gripper_aperture(scene: SceneState) -> float:
        return float(np.mean(np.abs(scene.gripper_qpos)))

    def open_gripper(self, speed: float = 1.0, steps: Optional[int] = None, label: str = "open_gripper") -> Dict[str, Any]:
        before = self.get_scene()
        tried = [float(self.cfg.gripper_open_value)]
        result = self._gripper_action(tried[-1], steps=steps, label=label)
        after = self.get_scene()
        ok = bool(after.gripper_open or self._gripper_aperture(after) >= self.cfg.gripper_open_threshold)
        if (not ok) and (not self.done):
            tried.append(float(-self.cfg.gripper_open_value))
            result = self._gripper_action(tried[-1], steps=steps, label=label)
            after = self.get_scene()
            ok = bool(after.gripper_open or self._gripper_aperture(after) >= self.cfg.gripper_open_threshold)
        if ok:
            self.clear_confirmed_holding(f"open_gripper:{label}")
        self.events.append(
            {
                "type": "gripper",
                "action": "open",
                "success": ok,
                "tried_values": tried,
                "before_qpos": before.gripper_qpos.astype(float).tolist(),
                "after_qpos": after.gripper_qpos.astype(float).tolist(),
                "before_aperture": self._gripper_aperture(before),
                "after_aperture": self._gripper_aperture(after),
            }
        )
        return {"success": bool(result["success"] and ok), "error": "gripper_did_not_open" if not ok else ""}

    def close_gripper(self, speed: float = 1.0, steps: Optional[int] = None, label: str = "close_gripper") -> Dict[str, Any]:
        before = self.get_scene()
        tried = [float(self.cfg.gripper_close_value)]
        result = self._gripper_action(tried[-1], steps=steps, label=label)
        after = self.get_scene()
        dropped = float(self._gripper_aperture(before) - self._gripper_aperture(after))
        self.events.append(
            {
                "type": "gripper",
                "action": "close",
                "success": bool(result.get("success")),
                "tried_values": tried,
                "before_qpos": before.gripper_qpos.astype(float).tolist(),
                "after_qpos": after.gripper_qpos.astype(float).tolist(),
                "before_aperture": self._gripper_aperture(before),
                "after_aperture": self._gripper_aperture(after),
                "aperture_drop": dropped,
                "gripper_open": bool(after.gripper_open),
            }
        )
        return {
            "success": bool(result.get("success")),
            "error": "" if result.get("success") else (result.get("error") or "close_gripper_step_failed"),
            "aperture_drop": dropped,
            "after_aperture": self._gripper_aperture(after),
        }

    def execute_cartesian_waypoints(
        self,
        waypoints: Iterable[Iterable[float]],
        gripper: float,
        max_steps: int,
        label: str = "trajectory",
    ) -> Dict[str, Any]:
        original_waypoints = _valid_cartesian_waypoints(waypoints)
        tracking_waypoints = _compress_cartesian_waypoints(
            original_waypoints,
            min_spacing=float(self.cfg.trajectory_waypoint_spacing),
        )
        if not tracking_waypoints:
            return {"success": False, "error": "trajectory_has_no_valid_waypoints", "done": False}

        initial_scene = self.get_scene()
        initial_ee_pos = initial_scene.ee_pos[:3].astype(np.float32).copy()
        endpoint = tracking_waypoints[-1]
        initial_endpoint_dist = float(np.linalg.norm(endpoint - initial_ee_pos))
        effective_budget = min(
            max(0, int(max_steps)),
            len(tracking_waypoints) * max(1, int(self.cfg.trajectory_waypoint_max_steps)),
        )
        used = 0
        reached_all = True
        waypoint_events: List[Dict[str, Any]] = []
        failure_reason = ""
        for waypoint_idx, goal in enumerate(tracking_waypoints):
            start_scene = self.get_scene()
            start_pos_arr = start_scene.ee_pos[:3].astype(np.float32).copy()
            initial_dist = float(np.linalg.norm(goal - start_pos_arr))
            final_threshold = (
                float(self.cfg.trajectory_final_reached_threshold)
                if waypoint_idx == len(tracking_waypoints) - 1
                else float(self.cfg.trajectory_reached_threshold)
            )
            best_dist = initial_dist
            stall_count = 0
            waypoint_steps = 0
            distance_history = [initial_dist]
            while used < effective_budget and waypoint_steps < max(1, int(self.cfg.trajectory_waypoint_max_steps)):
                scene = self.get_scene()
                delta = goal - scene.ee_pos[:3]
                dist = float(np.linalg.norm(delta))
                if dist <= final_threshold:
                    break
                delta_norm = float(np.linalg.norm(delta))
                if delta_norm > float(self.cfg.trajectory_max_delta) > 0.0:
                    delta = delta * (float(self.cfg.trajectory_max_delta) / delta_norm)
                action = np.zeros(7, dtype=np.float32)
                cmd = self.cfg.trajectory_gain * delta / max(float(self.cfg.trajectory_action_scale), 1e-6)
                action[:3] = np.clip(cmd, -self.cfg.trajectory_max_cmd, self.cfg.trajectory_max_cmd)
                action[6] = float(gripper)
                self._step(action, label=label, phase="trajectory", step_type="trajectory")
                used += 1
                waypoint_steps += 1
                after_dist = float(np.linalg.norm(goal - self.get_scene().ee_pos[:3]))
                distance_history.append(after_dist)
                improvement = dist - after_dist
                best_dist = min(best_dist, after_dist)
                stall_count = stall_count + 1 if improvement < float(self.cfg.trajectory_min_step_progress) else 0
                if self.done:
                    break
                if stall_count >= max(1, int(self.cfg.trajectory_stall_window)):
                    failure_reason = "trajectory_tracking_stalled"
                    break
            end_scene = self.get_scene()
            final_dist = float(np.linalg.norm(goal - end_scene.ee_pos[:3]))
            reached = final_dist <= final_threshold
            reached_all = bool(reached_all and reached)
            waypoint_events.append(
                {
                    "waypoint_idx": waypoint_idx,
                    "goal": goal.astype(float).tolist(),
                    "start_ee_pos": start_pos_arr.astype(float).tolist(),
                    "end_ee_pos": end_scene.ee_pos[:3].astype(float).tolist(),
                    "initial_dist": initial_dist,
                    "best_dist": best_dist,
                    "final_dist": final_dist,
                    "progress": initial_dist - final_dist,
                    "env_steps": waypoint_steps,
                    "distance_history": distance_history,
                    "reached": bool(reached),
                    "threshold": final_threshold,
                    "stalled": bool(stall_count >= max(1, int(self.cfg.trajectory_stall_window))),
                }
            )
            if not reached:
                near_this = _near_planned_position(final_dist, self.cfg)
                if waypoint_idx < len(tracking_waypoints) - 1 and near_this:
                    waypoint_events[-1]["continued_near_miss"] = True
                    failure_reason = ""
                    if self.done:
                        break
                    continue
                if not failure_reason:
                    failure_reason = (
                        "trajectory_tracking_budget_exhausted"
                        if used >= effective_budget
                        else "trajectory_waypoint_not_reached"
                    )
                if waypoint_idx == len(tracking_waypoints) - 1 and near_this:
                    waypoint_events[-1]["near_goal_handoff"] = True
                break
            if self.done:
                break

        final_scene = self.get_scene()
        final_ee_pos = final_scene.ee_pos[:3].astype(np.float32).copy()
        endpoint_error = float(np.linalg.norm(endpoint - final_ee_pos))
        actual_motion = float(np.linalg.norm(final_ee_pos - initial_ee_pos))
        endpoint_progress = initial_endpoint_dist - endpoint_error
        progress_ratio = endpoint_progress / max(initial_endpoint_dist, 1e-6)
        no_motion = bool(
            initial_endpoint_dist > float(self.cfg.trajectory_final_reached_threshold)
            and actual_motion < float(self.cfg.trajectory_min_motion)
        )
        endpoint_reached = endpoint_error <= float(self.cfg.trajectory_final_reached_threshold)
        near_goal_handoff = _near_planned_position(endpoint_error, self.cfg)
        covered = len(waypoint_events) == len(tracking_waypoints)
        accepted = [
            bool(item.get("reached") or item.get("continued_near_miss") or item.get("near_goal_handoff"))
            for item in waypoint_events
        ]
        strict_success = bool((not self.done) and reached_all and endpoint_reached and not no_motion)
        near_miss_complete = bool((not self.done) and covered and accepted and all(accepted) and not no_motion)
        success = bool(not self.done and (strict_success or near_goal_handoff or near_miss_complete) and not no_motion)
        if success and not strict_success:
            failure_reason = "near_goal_handoff" if near_goal_handoff else "near_miss_continue"
        elif not success and not failure_reason:
            if no_motion:
                failure_reason = "trajectory_tracking_no_motion"
            elif not endpoint_reached:
                failure_reason = "trajectory_endpoint_not_reached"
            else:
                failure_reason = "trajectory_waypoint_not_reached"
        tracking_summary = {
            "original_waypoint_count": len(original_waypoints),
            "tracking_waypoint_count": len(tracking_waypoints),
            "effective_step_budget": effective_budget,
            "env_steps": used,
            "initial_ee_pos": initial_ee_pos.astype(float).tolist(),
            "final_ee_pos": final_ee_pos.astype(float).tolist(),
            "planned_endpoint": endpoint.astype(float).tolist(),
            "initial_endpoint_dist": initial_endpoint_dist,
            "endpoint_error": endpoint_error,
            "endpoint_progress": endpoint_progress,
            "progress_ratio": progress_ratio,
            "actual_motion": actual_motion,
            "endpoint_reached": endpoint_reached,
            "near_goal_handoff": bool(near_goal_handoff and not strict_success),
            "no_motion": no_motion,
            "position_tracking_only": True,
            "orientation_tracking_note": "Serialized joint paths are currently validated in Cartesian position only.",
        }
        self.events.append(
            {
                "type": "trajectory",
                "label": label,
                "success": success,
                "failure_reason": failure_reason,
                "env_steps": used,
                "waypoints": waypoint_events,
                "threshold": float(self.cfg.trajectory_reached_threshold),
                "final_threshold": float(self.cfg.trajectory_final_reached_threshold),
                "waypoint_spacing": float(self.cfg.trajectory_waypoint_spacing),
                "waypoint_max_steps": int(self.cfg.trajectory_waypoint_max_steps),
                "action_scale": float(self.cfg.trajectory_action_scale),
                "max_cmd": float(self.cfg.trajectory_max_cmd),
                "tracking_summary": tracking_summary,
            }
        )
        if self.done:
            return {
                "success": False,
                "error": "env_done_during_trajectory",
                "done": True,
                "env_steps": used,
                "waypoints": waypoint_events,
                "tracking_summary": tracking_summary,
            }
        if not success:
            return {
                "success": False,
                "error": failure_reason,
                "done": False,
                "env_steps": used,
                "waypoints": waypoint_events,
                "tracking_summary": tracking_summary,
            }
        return {
            "success": True,
            "error": "",
            "done": False,
            "env_steps": used,
            "waypoints": waypoint_events,
            "tracking_summary": tracking_summary,
        }

    def execute_cartesian_pose_waypoints(
        self,
        waypoints: Iterable[Dict[str, Any]],
        gripper: float,
        max_steps: int,
        label: str = "optimized_cutamp_motion",
    ) -> Dict[str, Any]:
        valid: List[Dict[str, np.ndarray]] = []
        for waypoint in waypoints:
            position = np.asarray(waypoint.get("position", []), dtype=np.float32).reshape(-1)[:3]
            quat = np.asarray(waypoint.get("quat_xyzw", []), dtype=np.float32).reshape(-1)[:4]
            if position.size == 3 and quat.size == 4 and np.all(np.isfinite(position)) and np.all(np.isfinite(quat)):
                quat = quat / max(float(np.linalg.norm(quat)), 1e-12)
                valid.append({"position": position.copy(), "quat_xyzw": quat.copy()})
        tracking = _compress_pose_waypoints(
            valid,
            position_spacing=float(self.cfg.trajectory_waypoint_spacing),
            orientation_spacing=float(self.cfg.orientation_waypoint_spacing),
        )
        if not tracking:
            return {"success": False, "error": "optimized_motion_has_no_valid_pose_waypoints", "done": False}

        effective_budget = min(
            max(0, int(max_steps)),
            len(tracking) * max(1, int(self.cfg.trajectory_waypoint_max_steps)),
        )
        used = 0
        failure_reason = ""
        waypoint_events: List[Dict[str, Any]] = []
        for waypoint_idx, target in enumerate(tracking):
            final = waypoint_idx == len(tracking) - 1
            pos_threshold = float(
                self.cfg.trajectory_final_reached_threshold if final else self.cfg.trajectory_reached_threshold
            )
            rot_threshold = float(
                self.cfg.orientation_final_reached_threshold if final else self.cfg.orientation_reached_threshold
            )
            start_scene = self.get_scene()
            initial_pos_error = float(np.linalg.norm(target["position"] - start_scene.ee_pos[:3]))
            initial_rot_error = float(np.linalg.norm(_orientation_error(target["quat_xyzw"], start_scene.ee_quat)))
            best_pos_error = initial_pos_error
            best_rot_error = initial_rot_error
            stall_count = 0
            steps = 0
            history: List[Dict[str, float]] = []
            while used < effective_budget and steps < max(1, int(self.cfg.trajectory_waypoint_max_steps)):
                scene = self.get_scene()
                pos_delta = target["position"] - scene.ee_pos[:3]
                rot_delta = _orientation_error(target["quat_xyzw"], scene.ee_quat)
                pos_error = float(np.linalg.norm(pos_delta))
                rot_error = float(np.linalg.norm(rot_delta))
                history.append({"position_error": pos_error, "orientation_error_rad": rot_error})
                if pos_error <= pos_threshold and rot_error <= rot_threshold:
                    break
                pos_norm = float(np.linalg.norm(pos_delta))
                if pos_norm > float(self.cfg.trajectory_max_delta) > 0.0:
                    pos_delta = pos_delta * (float(self.cfg.trajectory_max_delta) / pos_norm)
                action = np.zeros(7, dtype=np.float32)
                action[:3] = np.clip(
                    self.cfg.trajectory_gain * pos_delta / max(float(self.cfg.trajectory_action_scale), 1e-6),
                    -self.cfg.trajectory_max_cmd,
                    self.cfg.trajectory_max_cmd,
                )
                action[3:6] = np.clip(
                    rot_delta / max(float(self.cfg.orientation_action_scale), 1e-6),
                    -self.cfg.orientation_max_cmd,
                    self.cfg.orientation_max_cmd,
                )
                action[6] = float(gripper)
                self._step(action, label=label, phase="optimized_cutamp_motion", step_type="trajectory")
                used += 1
                steps += 1
                after = self.get_scene()
                after_pos = float(np.linalg.norm(target["position"] - after.ee_pos[:3]))
                after_rot = float(np.linalg.norm(_orientation_error(target["quat_xyzw"], after.ee_quat)))
                pos_improvement = pos_error - after_pos
                rot_improvement = rot_error - after_rot
                best_pos_error = min(best_pos_error, after_pos)
                best_rot_error = min(best_rot_error, after_rot)
                stalled = (
                    pos_improvement < float(self.cfg.trajectory_min_step_progress)
                    and rot_improvement < 0.005
                )
                stall_count = stall_count + 1 if stalled else 0
                if self.done:
                    break
                if stall_count >= max(1, int(self.cfg.trajectory_stall_window)):
                    failure_reason = "optimized_motion_tracking_stalled"
                    break
            end_scene = self.get_scene()
            final_pos_error = float(np.linalg.norm(target["position"] - end_scene.ee_pos[:3]))
            final_rot_error = float(np.linalg.norm(_orientation_error(target["quat_xyzw"], end_scene.ee_quat)))
            reached = final_pos_error <= pos_threshold and final_rot_error <= rot_threshold
            waypoint_events.append(
                {
                    "waypoint_idx": waypoint_idx,
                    "target_position": target["position"].astype(float).tolist(),
                    "target_quat_xyzw": target["quat_xyzw"].astype(float).tolist(),
                    "initial_position_error": initial_pos_error,
                    "initial_orientation_error_rad": initial_rot_error,
                    "best_position_error": best_pos_error,
                    "best_orientation_error_rad": best_rot_error,
                    "final_position_error": final_pos_error,
                    "final_orientation_error_rad": final_rot_error,
                    "position_threshold": pos_threshold,
                    "orientation_threshold_rad": rot_threshold,
                    "env_steps": steps,
                    "reached": reached,
                    "history": history,
                }
            )
            end_now = self.get_scene()
            end_pos_error = float(np.linalg.norm(tracking[-1]["position"] - end_now.ee_pos[:3]))
            end_rot_error = float(np.linalg.norm(_orientation_error(tracking[-1]["quat_xyzw"], end_now.ee_quat)))
            waypoint_events[-1]["segment_end_position_error"] = end_pos_error
            waypoint_events[-1]["segment_end_orientation_error_rad"] = end_rot_error
            if not reached:
                near_this = _near_planned_goal(final_pos_error, final_rot_error, self.cfg)
                near_end = _near_planned_goal(end_pos_error, end_rot_error, self.cfg)
                if not final and near_this:
                    waypoint_events[-1]["continued_near_miss"] = True
                    failure_reason = ""
                    if self.done:
                        break
                    continue
                if not failure_reason:
                    failure_reason = (
                        "optimized_motion_budget_exhausted"
                        if used >= effective_budget
                        else "optimized_motion_pose_not_reached"
                    )
                if near_end:
                    waypoint_events[-1]["near_goal_handoff"] = True
                break
            if self.done:
                break

        end_scene = self.get_scene()
        end_pos_error = float(np.linalg.norm(tracking[-1]["position"] - end_scene.ee_pos[:3]))
        end_rot_error = float(np.linalg.norm(_orientation_error(tracking[-1]["quat_xyzw"], end_scene.ee_quat)))
        near_goal_handoff = _near_planned_goal(end_pos_error, end_rot_error, self.cfg)
        covered = len(waypoint_events) == len(tracking)
        accepted = [
            bool(item.get("reached") or item.get("continued_near_miss") or item.get("near_goal_handoff"))
            for item in waypoint_events
        ]
        strict_success = bool(not self.done and covered and waypoint_events and all(item.get("reached") for item in waypoint_events))
        near_miss_complete = bool(not self.done and covered and accepted and all(accepted))
        success = bool(not self.done and (strict_success or near_goal_handoff or near_miss_complete))
        if success and not strict_success:
            failure_reason = "near_goal_handoff" if near_goal_handoff else "near_miss_continue"
        event = {
            "type": "optimized_cutamp_trajectory",
            "label": label,
            "success": success,
            "failure_reason": "" if success else failure_reason,
            "near_goal_handoff": bool(near_goal_handoff and not strict_success),
            "segment_end_position_error": end_pos_error,
            "segment_end_orientation_error_rad": end_rot_error,
            "original_waypoint_count": len(valid),
            "tracking_waypoint_count": len(tracking),
            "env_steps": used,
            "waypoints": waypoint_events,
            "position_and_orientation_tracking": True,
        }
        self.events.append(event)
        return {
            "success": success,
            "error": "" if success else (failure_reason or "optimized_motion_pose_not_reached"),
            "done": self.done,
            "waypoints": waypoint_events,
            "env_steps": used,
            "near_goal_handoff": bool(near_goal_handoff and not strict_success),
            "segment_end_position_error": end_pos_error,
            "segment_end_orientation_error_rad": end_rot_error,
            "planned_end_position": tracking[-1]["position"].astype(float).tolist(),
            "planned_end_quat_xyzw": tracking[-1]["quat_xyzw"].astype(float).tolist(),
        }

    def execute_planned_pick(self, target_q: Any, max_steps: int, label: str = "Pick") -> Dict[str, Any]:
        """Approach the planned grasp configuration, then close the gripper.

        The target is FK(q1) from cuTAMP, not a nearby object heuristic.
        """
        scene = self.get_scene()
        approach: Dict[str, Any] = {"success": True, "skipped": True, "error": ""}
        q = np.asarray(target_q, dtype=np.float32).reshape(-1) if target_q is not None else np.zeros(0)
        if q.size == 7 and np.all(np.isfinite(q)):
            q_now = np.asarray(scene.robot_qpos, dtype=np.float32).reshape(-1)[:7]
            if q_now.size == 7 and np.all(np.isfinite(q_now)):
                if not _joint_interpolation_safe(q_now, q, self.cfg):
                    event = {
                        "type": "planned_pick",
                        "label": label,
                        "success": False,
                        "close_error": "skipped_close_because_q1_too_far_for_joint_interpolation",
                        "q_now": q_now.astype(float).tolist(),
                        "q1": q.astype(float).tolist(),
                        "joint_delta_l2": float(np.linalg.norm(q - q_now)),
                    }
                    self.events.append(event)
                    return {
                        "success": False,
                        "error": "planned_pick_q1_too_far_for_joint_interpolation",
                        "done": self.done,
                    }
                joint_path = np.vstack([q_now, q])
            else:
                joint_path = q.reshape(1, 7)
            poses = _joint_path_to_ee_pose_waypoints(self.env, joint_path, scene.ee_quat)
            if poses:
                approach_gripper = (
                    float(self.cfg.gripper_close_value)
                    if self.confirmed_holding_object()
                    else float(self.cfg.gripper_open_value)
                )
                approach = self.execute_cartesian_pose_waypoints(
                    poses,
                    gripper=approach_gripper,
                    max_steps=max(0, min(int(max_steps), int(self.cfg.grasp_approach_max_steps))),
                    label=f"{label}:approach_q1",
                )
        if not bool(approach.get("skipped")) and not bool(approach.get("success")):
            event = {
                "type": "planned_pick",
                "label": label,
                "success": False,
                "approach": {k: v for k, v in approach.items() if k != "waypoints"},
                "close_error": "skipped_close_because_approach_missed_planned_q1",
            }
            self.events.append(event)
            return {
                "success": False,
                "error": str(approach.get("error") or "planned_pick_approach_missed_q1"),
                "done": self.done,
                "approach": approach,
            }
        remaining = max(0, int(max_steps) - int(approach.get("env_steps") or 0))
        close_steps = min(int(self.cfg.grasp_close_steps), remaining) if remaining else int(self.cfg.grasp_close_steps)
        close = self.close_gripper(steps=close_steps, label=label)
        success = bool(close.get("success"))
        if approach.get("done") or self.done:
            success = True
        event = {
            "type": "planned_pick",
            "label": label,
            "success": success,
            "approach": {k: v for k, v in approach.items() if k != "waypoints"},
            "close_error": close.get("error", ""),
        }
        self.events.append(event)
        return {
            "success": success,
            "error": "" if success else (close.get("error") or approach.get("error") or "planned_pick_failed"),
            "done": self.done,
            "approach": approach,
            "close": close,
        }

    def execute_held_transfer_keep_z_path(
        self,
        pose_waypoints: Iterable[Mapping[str, Any]],
        gripper: float,
        max_steps: int,
        label: str = "held_transfer_keep_z",
    ) -> Dict[str, Any]:
        valid: List[np.ndarray] = []
        for waypoint in pose_waypoints:
            position = np.asarray(waypoint.get("position", []), dtype=np.float32).reshape(-1)[:3]
            if position.size == 3 and np.all(np.isfinite(position)):
                valid.append(position.copy())
        if not valid:
            return {"success": False, "error": "held_transfer_has_no_valid_waypoints", "done": False}
        budget = max(0, int(max_steps))
        if int(self.cfg.held_transfer_max_steps) > 0:
            budget = min(budget, int(self.cfg.held_transfer_max_steps))
        if budget <= 0:
            return {"success": False, "error": "held_transfer_no_budget", "done": self.done, "env_steps": 0}

        start_scene = self.get_scene()
        start = start_scene.ee_pos[:3].astype(np.float32).copy()
        endpoint = valid[-1].astype(np.float32)
        protected_z = _held_transfer_protected_z(float(start[2]), float(endpoint[2]), self.cfg)
        horizontal = np.asarray([float(endpoint[0]), float(endpoint[1]), protected_z], dtype=np.float32)
        protected_waypoints: List[np.ndarray] = []
        if protected_z > float(start[2]) + float(self.cfg.held_transfer_reached_m):
            protected_waypoints.append(np.asarray([float(start[0]), float(start[1]), protected_z], dtype=np.float32))
        protected_waypoints.append(horizontal)

        old = (
            self.cfg.near_goal_position_m,
            self.cfg.trajectory_final_reached_threshold,
            self.cfg.trajectory_reached_threshold,
            self.cfg.trajectory_waypoint_max_steps,
        )
        try:
            reached = max(0.001, float(self.cfg.held_transfer_reached_m))
            self.cfg.near_goal_position_m = reached
            self.cfg.trajectory_final_reached_threshold = reached
            self.cfg.trajectory_reached_threshold = min(float(self.cfg.trajectory_reached_threshold), reached)
            self.cfg.trajectory_waypoint_max_steps = max(1, budget)
            result = self.execute_cartesian_waypoints(
                protected_waypoints,
                gripper=float(gripper),
                max_steps=budget,
                label=label,
            )
        finally:
            (
                self.cfg.near_goal_position_m,
                self.cfg.trajectory_final_reached_threshold,
                self.cfg.trajectory_reached_threshold,
                self.cfg.trajectory_waypoint_max_steps,
            ) = old

        end_scene = self.get_scene()
        event = {
            "event": "held_transfer_keep_z",
            "phase": "trajectory",
            "start_z": float(start[2]),
            "planned_endpoint_z": float(endpoint[2]),
            "protected_z": float(protected_z),
            "planned_endpoint": endpoint.astype(float).tolist(),
            "protected_endpoint": horizontal.astype(float).tolist(),
            "final_ee_z": float(end_scene.ee_pos[2]),
            "max_descent_m": float(self.cfg.held_transfer_max_descent_m),
            "z_margin_m": float(self.cfg.held_transfer_z_margin_m),
            "env_steps": int(result.get("env_steps") or 0),
            "success": bool(result.get("success", False)),
            "error": str(result.get("error") or ""),
        }
        self.events.append(event)
        result["held_transfer_keep_z"] = event
        return result

    def execute_joint_impedance_path(
        self,
        joint_confs: Any,
        joint_vels: Any = None,
        durations: Any = None,
        max_steps: Optional[int] = None,
        gripper: Optional[float] = None,
        label: str = "cutamp_joint_path_as_ee_waypoints",
        track_pose_tail: bool = False,
        track_full_pose: bool = False,
        keep_z_during_transfer: bool = False,
    ) -> Dict[str, Any]:
        hold = float(self.cfg.gripper_open_value if gripper is None else gripper)
        poses = _joint_path_to_ee_pose_waypoints(self.env, joint_confs, self.get_scene().ee_quat)
        n_joints = int(len(joint_confs)) if hasattr(joint_confs, "__len__") else 24
        budget = max(
            1,
            int(max_steps if max_steps is not None else n_joints * self.cfg.trajectory_waypoint_max_steps),
        )
        if poses:
            if track_full_pose:
                old_near = float(self.cfg.near_goal_position_m)
                try:
                    if "pick(" in str(label or "").lower():
                        self.cfg.near_goal_position_m = min(old_near, float(self.cfg.pick_reach_position_m))
                    return self.execute_cartesian_pose_waypoints(poses, gripper=hold, max_steps=budget, label=label)
                finally:
                    self.cfg.near_goal_position_m = old_near
            if keep_z_during_transfer and bool(self.cfg.held_transfer_keep_z):
                return self.execute_held_transfer_keep_z_path(
                    poses,
                    gripper=hold,
                    max_steps=budget,
                    label=label,
                )
            xyz_part = poses
            pose_tail: List[Dict[str, List[float]]] = []
            if track_pose_tail:
                xyz_part, pose_tail = _split_pose_tail(poses, float(self.cfg.pose_tracking_tail_m))
            if xyz_part:
                result = self.execute_cartesian_waypoints(
                    [item["position"] for item in xyz_part],
                    gripper=hold,
                    max_steps=budget,
                    label=label,
                )
                if not result.get("success", False) or not pose_tail:
                    return result
                used = int(result.get("env_steps") or result.get("tracking_summary", {}).get("env_steps") or 0)
                budget = max(1, budget - used)
                tail = self.execute_cartesian_pose_waypoints(
                    pose_tail,
                    gripper=hold,
                    max_steps=budget,
                    label=f"{label}:pose_tail",
                )
                tail["prefix_result"] = {k: v for k, v in result.items() if k != "waypoints"}
                return tail
            return self.execute_cartesian_pose_waypoints(pose_tail or poses, gripper=hold, max_steps=budget, label=label)
        ee_waypoints = _joint_path_to_ee_waypoints(self.env, joint_confs)
        if ee_waypoints is not None and len(ee_waypoints) > 0:
            return self.execute_cartesian_waypoints(
                ee_waypoints,
                gripper=hold,
                max_steps=max(1, int(max_steps if max_steps is not None else len(ee_waypoints) * self.cfg.trajectory_waypoint_max_steps)),
                label=label,
            )
        self.events.append(
            {
                "type": "trajectory",
                "label": "joint_impedance_path_unsupported_in_libero_delta_env",
                "success": False,
                "num_waypoints": int(len(joint_confs)) if hasattr(joint_confs, "__len__") else 0,
            }
        )
        return {"success": False, "error": "LIBERO delta-action env cannot execute joint waypoint paths directly"}


def _sim_handles(env: Any) -> Tuple[Any, Any, Any]:
    sim = getattr(env, "sim", None)
    if sim is None and hasattr(env, "env"):
        sim = getattr(env.env, "sim", None)
    return sim, getattr(sim, "model", None), getattr(sim, "data", None)


def _eef_site_id(model: Any) -> Optional[int]:
    if model is None:
        return None
    names = model_names(model, "site")
    for name in ("gripper0_grip_site", "robot0_grip_site", "eef_site", "grip_site"):
        if name in names:
            try:
                site_id = model_name_to_id(model, "site", name)
                if site_id is not None:
                    return int(site_id)
            except Exception:
                pass
    for idx, name in enumerate(names):
        low = str(name).lower()
        if "grip" in low or "eef" in low or "ee" in low:
            return idx
    return None


def _robot_joint_qpos_addresses(model: Any, expected_dim: int) -> List[int]:
    if model is None:
        return []
    names = model_names(model, "joint")
    addrs: List[int] = []
    for name in names:
        low = str(name).lower()
        if "finger" in low or "gripper" in low:
            continue
        if not (low.startswith("robot0") or "joint" in low or "panda" in low):
            continue
        try:
            joint_id = model_name_to_id(model, "joint", name)
            if joint_id is None:
                continue
            jid = int(joint_id)
            addr = int(model.jnt_qposadr[jid])
        except Exception:
            continue
        addrs.append(addr)
        if len(addrs) >= expected_dim:
            break
    return addrs


def _joint_path_to_ee_waypoints(env: Any, joint_confs: Any) -> Optional[List[Tuple[float, float, float]]]:
    """Convert serialized cuRobo joint waypoints into EE waypoints for LIBERO."""
    q_path = np.asarray(joint_confs, dtype=np.float32)
    if q_path.ndim != 2 or q_path.shape[0] == 0:
        return None
    sim, model, data = _sim_handles(env)
    if sim is None or model is None or data is None:
        return None
    site_id = _eef_site_id(model)
    if site_id is None:
        return None
    addrs = _robot_joint_qpos_addresses(model, int(q_path.shape[1]))
    if len(addrs) < int(q_path.shape[1]):
        return None
    qpos_backup = np.asarray(data.qpos).copy()
    qvel_backup = np.asarray(data.qvel).copy() if hasattr(data, "qvel") else None
    waypoints: List[Tuple[float, float, float]] = []
    try:
        stride = max(1, int(np.ceil(q_path.shape[0] / 24)))
        sample = q_path[::stride]
        if not np.allclose(sample[-1], q_path[-1]):
            sample = np.concatenate([sample, q_path[-1:]], axis=0)
        for q in sample:
            for idx, addr in enumerate(addrs[: q_path.shape[1]]):
                data.qpos[addr] = float(q[idx])
            try:
                sim.forward()
            except Exception:
                pass
            pos = np.asarray(data.site_xpos[site_id], dtype=np.float32).reshape(-1)[:3]
            if np.all(np.isfinite(pos)):
                waypoints.append(tuple(float(x) for x in pos))
    finally:
        data.qpos[:] = qpos_backup
        if qvel_backup is not None:
            data.qvel[:] = qvel_backup
        try:
            sim.forward()
        except Exception:
            pass
    return waypoints or None


def _joint_path_to_ee_pose_waypoints(
    env: Any,
    joint_confs: Any,
    reference_quat_xyzw: Any | None = None,
) -> Optional[List[Dict[str, List[float]]]]:
    q_path = np.asarray(joint_confs, dtype=np.float32)
    if q_path.ndim != 2 or q_path.shape[0] == 0:
        return None
    sim, model, data = _sim_handles(env)
    if sim is None or model is None or data is None:
        return None
    site_id = _eef_site_id(model)
    if site_id is None:
        return None
    addrs = _robot_joint_qpos_addresses(model, int(q_path.shape[1]))
    if len(addrs) < int(q_path.shape[1]):
        return None
    qpos_backup = np.asarray(data.qpos).copy()
    qvel_backup = np.asarray(data.qvel).copy() if hasattr(data, "qvel") else None
    raw_waypoints: List[Tuple[np.ndarray, np.ndarray]] = []
    try:
        for q in q_path:
            for idx, addr in enumerate(addrs[: q_path.shape[1]]):
                data.qpos[addr] = float(q[idx])
            try:
                sim.forward()
            except Exception:
                pass
            position = np.asarray(data.site_xpos[site_id], dtype=np.float64).reshape(-1)[:3]
            rotation = np.asarray(data.site_xmat[site_id], dtype=np.float64).reshape(3, 3)
            quat = _matrix_to_quat_xyzw(rotation)
            if np.all(np.isfinite(position)) and np.all(np.isfinite(quat)):
                raw_waypoints.append((position.copy(), rotation.copy()))
    finally:
        data.qpos[:] = qpos_backup
        if qvel_backup is not None:
            data.qvel[:] = qvel_backup
        try:
            sim.forward()
        except Exception:
            pass
    if not raw_waypoints:
        return None
    frame_rotation = np.eye(3, dtype=np.float64)
    if reference_quat_xyzw is not None:
        reference = np.asarray(reference_quat_xyzw, dtype=np.float64).reshape(-1)[:4]
        if reference.size == 4 and np.all(np.isfinite(reference)):
            # LIBERO's controller EEF frame and MuJoCo's grip-site frame differ
            # by a fixed rotation. Calibrate it at optimized q_start, then keep
            # cuTAMP's relative orientation changes along the whole segment.
            frame_rotation = _quat_xyzw_to_matrix(reference) @ raw_waypoints[0][1].T
    return [
        {
            "position": position.astype(float).tolist(),
            "quat_xyzw": _matrix_to_quat_xyzw(frame_rotation @ rotation).astype(float).tolist(),
        }
        for position, rotation in raw_waypoints
    ]


def _interpolate_joint_segment(q_start: Any, q_end: Any, max_joint_step: float = 0.08) -> Optional[np.ndarray]:
    start = np.asarray(q_start, dtype=np.float32).reshape(-1)
    end = np.asarray(q_end, dtype=np.float32).reshape(-1)
    if start.size != 7 or end.size != 7 or not np.all(np.isfinite(start)) or not np.all(np.isfinite(end)):
        return None
    steps = max(2, int(np.ceil(float(np.max(np.abs(end - start))) / max(max_joint_step, 1e-4))) + 1)
    return np.linspace(start, end, min(steps, 48), dtype=np.float32)


def _operator_argument_map(operator: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(argument.get("parameter", "")): dict(argument)
        for argument in operator.get("arguments", [])
        if isinstance(argument, dict)
    }


def execute_optimized_cutamp_plan(
    env: Any,
    obs: Dict[str, Any],
    optimized_plan: Dict[str, Any],
    max_env_steps: int = 120,
    goal_atoms: Iterable[Any] | None = None,
    stop_on_goal_satisfied: bool = True,
    client_cfg: LiberoRobotClientConfig | None = None,
    step_callback: Callable[[Dict[str, Any], Dict[str, Any]], None] | None = None,
    hook_bridge: Any = None,
    holding_latch: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], TipTopExecutionTrace]:
    operators = [dict(item) for item in optimized_plan.get("operators", []) if isinstance(item, dict)]
    bindings = dict(optimized_plan.get("bindings", {}))
    labels = [str(op.get("label") or op.get("name") or f"operator_{idx}") for idx, op in enumerate(operators)]
    trace = TipTopExecutionTrace(plan_reason="cutamp_optimized_solution_to_libero_delta_eef", plan_steps=labels)
    client = LiberoRobotClient(env, obs, cfg=client_cfg, step_callback=step_callback, holding_latch=holding_latch)
    trace.events.append(
        {
            "event": "optimized_cutamp_plan_received",
            "source": optimized_plan.get("source", ""),
            "plan_idx": optimized_plan.get("plan_idx"),
            "operators": operators,
            "binding_names": sorted(bindings),
        }
    )
    if not operators:
        trace.events.append({"event": "execution_failed_stop", "reason": "optimized_cutamp_plan_has_no_operators"})
        return client.get_obs(), trace

    for operator_idx, operator in enumerate(operators):
        if client.num_env_steps >= max_env_steps:
            trace.events.append({"event": "max_env_steps", "operator_idx": operator_idx})
            break
        name = str(operator.get("name", ""))
        label = str(operator.get("label") or name or f"operator_{operator_idx}")
        args = _operator_argument_map(operator)
        before_steps = client.num_env_steps
        trace.executed_steps.append(label)
        if name in {"MoveFree", "MoveHolding"}:
            start_symbol = str(args.get("q_start", {}).get("symbol", ""))
            end_symbol = str(args.get("q_end", {}).get("symbol", ""))
            q_path = None
            if _joint_interpolation_safe(bindings.get(start_symbol), bindings.get(end_symbol), client.cfg):
                q_path = _interpolate_joint_segment(bindings.get(start_symbol), bindings.get(end_symbol))
            reference_quat = client.get_scene().ee_quat.copy()
            pose_waypoints = (
                None
                if q_path is None
                else _joint_path_to_ee_pose_waypoints(env, q_path, reference_quat_xyzw=reference_quat)
            )
            if pose_waypoints is None:
                result = {
                    "success": False,
                    "error": (
                        "optimized_joint_interpolation_too_large"
                        if q_path is None and bindings.get(start_symbol) is not None and bindings.get(end_symbol) is not None
                        else f"optimized_joint_binding_missing_or_invalid:{start_symbol}->{end_symbol}"
                    ),
                }
            else:
                default_hold = (
                    float(client.cfg.gripper_close_value)
                    if name == "MoveHolding" or client.confirmed_holding_object()
                    else float(client.cfg.gripper_open_value)
                )
                skip, hold, hook_meta = _apply_trajectory_hook(
                    hook_bridge,
                    {
                        "label": label,
                        "stype": "trajectory",
                        "gripper_hold_value": default_hold,
                        "gripper_close_value": client.cfg.gripper_close_value,
                        "gripper_open_value": client.cfg.gripper_open_value,
                        "holding_latch_object": client.confirmed_holding_object(),
                    },
                    default_hold,
                )
                if skip:
                    result = {"success": True, "error": "", "skipped": "skill_skip", "gripper_hold_value": hold, **hook_meta}
                else:
                    result = client.execute_cartesian_pose_waypoints(
                        pose_waypoints,
                        gripper=hold,
                        max_steps=max(0, int(max_env_steps) - client.num_env_steps),
                        label=label,
                    )
                    result["gripper_hold_value"] = hold
                    result.update(hook_meta)
        elif name == "Pick":
            q_symbol = str(args.get("q", {}).get("symbol", ""))
            result = client.execute_planned_pick(
                bindings.get(q_symbol),
                max_steps=max(0, int(max_env_steps) - client.num_env_steps),
                label=label,
            )
        elif name == "Place":
            result = client.open_gripper(label=label)
        else:
            result = {"success": False, "error": f"unsupported_optimized_cutamp_operator:{name}"}

        trace.num_env_steps = client.num_env_steps
        trace.done = client.done
        trace.events.append(
            {
                "event": "execute_optimized_operator",
                "operator_idx": operator_idx,
                "operator": operator,
                "result": result,
                "env_steps": client.num_env_steps - before_steps,
            }
        )
        trace.events.extend(client.events)
        client.events.clear()
        if result.get("abort_episode"):
            trace.abort_episode = True
            trace.abort_reason = str(result.get("abort_reason") or result.get("error") or "recovery_abort_episode")
            trace.events.append({"event": "recovery_abort_episode", "step": label, "reason": trace.abort_reason})
            return client.get_obs(), trace
        if not bool(result.get("success", False)):
            trace.events.append({"event": "execution_failed_stop", "step": label, "reason": result.get("error", "")})
            return client.get_obs(), trace
        if client.done:
            trace.success = True
            return client.get_obs(), trace
        if stop_on_goal_satisfied and goal_atoms:
            goal = goal_satisfied(client.get_scene(), goal_atoms)
            trace.events.append(
                {
                    "event": "goal_check",
                    "step": label,
                    "ok": goal.ok,
                    "reason": goal.reason,
                    "details": goal.details,
                }
            )
            if goal.ok:
                trace.goal_satisfied = True
                trace.handoff_to_vla = True
                trace.success = True
                return client.get_obs(), trace
    return client.get_obs(), trace


def execute_real_cutamp_executable_plan(
    env: Any,
    obs: Dict[str, Any],
    parsed_task: ParsedTask,
    executable_plan: List[Dict[str, Any]],
    max_env_steps: int = 120,
    goal_atoms: Iterable[Any] | None = None,
    stop_on_goal_satisfied: bool = True,
    client_cfg: LiberoRobotClientConfig | None = None,
    step_callback: Callable[[Dict[str, Any], Dict[str, Any]], None] | None = None,
    hook_bridge: Any = None,
    holding_latch: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], TipTopExecutionTrace]:
    client = LiberoRobotClient(env, obs, cfg=client_cfg, step_callback=step_callback, holding_latch=holding_latch)
    labels = [str(step.get("label") or step.get("type") or f"step_{idx}") for idx, step in enumerate(executable_plan)]
    trace = TipTopExecutionTrace(plan_reason="real_cutamp_executable_plan", plan_steps=labels)
    trace.events.append(
        {
            "event": "executable_plan_received",
            "num_steps": len(executable_plan),
            "steps": [
                {
                    "idx": idx,
                    "type": step.get("type"),
                    "label": step.get("label", ""),
                    "action": step.get("action", ""),
                    "num_waypoints": step.get("num_waypoints", len(step.get("positions", []) or [])),
                    "has_positions": bool(step.get("positions")),
                    "has_velocities": bool(step.get("velocities")),
                    "dt": step.get("dt", 0.0),
                }
                for idx, step in enumerate(executable_plan)
            ],
        }
    )

    articulated_plan = any(step.get("type") == "articulation" for step in executable_plan)
    if stop_on_goal_satisfied and goal_atoms and not articulated_plan:
        initial_goal = goal_satisfied(client.get_scene(), goal_atoms)
        trace.events.append({"step": "__start__", "event": "goal_check", "ok": initial_goal.ok, "reason": initial_goal.reason, "details": initial_goal.details})
        if initial_goal.ok:
            trace.goal_satisfied = True
            trace.handoff_to_vla = True
            trace.success = True
            return client.get_obs(), trace

    gripper_closed = bool(client.confirmed_holding_object())
    placed = False
    opened_by_place = False
    reserve_place = _plan_has_place(executable_plan)
    for idx, step in enumerate(executable_plan):
        if client.num_env_steps >= max_env_steps:
            trace.events.append({"step": step.get("label", idx), "event": "max_env_steps"})
            break
        label = str(step.get("label") or step.get("type") or f"step_{idx}")
        stype = str(step.get("type", ""))
        before_steps = client.num_env_steps
        trace.executed_steps.append(label)
        low = label.lower()
        if stype == "articulation":
            from .articulation_executor import execute_articulated_plan
            result = execute_articulated_plan(client, step["plan"], max_env_steps - client.num_env_steps)
            if result.get("success"):
                trace.goal_satisfied = True
                trace.success = True
                trace.handoff_to_vla = True
        elif stype == "gripper":
            action = str(step.get("action", ""))
            if action == "open":
                if opened_by_place:
                    result = {"success": True, "error": "", "skipped": "already_opened_after_place"}
                    gripper_closed = False
                else:
                    result = client.open_gripper(label=label)
                    if result.get("success"):
                        gripper_closed = False
                result["gripper_hold_value"] = float(client.cfg.gripper_open_value)
                result["action"] = "open"
            elif action == "close":
                remaining_steps = _front_budget(client, max_env_steps, reserve_place and not placed)
                close_steps = (
                    min(int(client.cfg.grasp_close_steps), remaining_steps)
                    if remaining_steps
                    else int(client.cfg.grasp_close_steps)
                )
                target = _plan_target_object(executable_plan, idx)
                if target:
                    pre_close_scene = client.get_scene()
                    near, near_details = _ee_near_grasp_target(pre_close_scene, target, client.cfg)
                    planned_close = _planned_close_pose_from_executable(
                        client.env,
                        executable_plan,
                        idx,
                        label,
                        pre_close_scene.ee_quat,
                    )
                    precheck_event = {
                        "step": label,
                        "event": "grasp_close_precheck",
                        **_scene_grasp_debug_snapshot(pre_close_scene, target),
                        **near_details,
                        **planned_close,
                    }
                    planned_xyz = planned_close.get("planned_close_xyz")
                    planned_quat = planned_close.get("planned_close_quat_xyzw")
                    if planned_xyz is not None:
                        planned_xyz_arr = np.asarray(planned_xyz, dtype=np.float32).reshape(-1)[:3]
                        precheck_event["planned_close_pos_error_m"] = float(
                            np.linalg.norm(pre_close_scene.ee_pos[:3] - planned_xyz_arr)
                        )
                    if planned_quat is not None:
                        planned_quat_arr = np.asarray(planned_quat, dtype=np.float32).reshape(-1)[:4]
                        if planned_quat_arr.size == 4:
                            precheck_event["planned_close_orientation_error_rad"] = float(
                                np.linalg.norm(_orientation_error(planned_quat_arr, pre_close_scene.ee_quat))
                            )
                    trace.events.append(precheck_event)
                    if not near:
                        result = {
                            "success": False,
                            "error": "grasp_target_not_near",
                            "object": target,
                            "action": "close",
                            **near_details,
                        }
                        trace.events.append(
                            {
                                "step": label,
                                "event": "grasp_skip_not_near",
                                "reason": "grasp_target_not_near",
                                **near_details,
                            }
                        )
                        trace.events.append(
                            {
                                "step": label,
                                "event": "skip_place_not_holding",
                                "object": target,
                                "reason": "grasp_target_not_near",
                            }
                        )
                    else:
                        result = client.close_gripper(steps=close_steps, label=label)
                        result["gripper_hold_value"] = float(client.cfg.gripper_close_value)
                        result["action"] = "close"
                        leftover = max(0, int(max_env_steps) - int(client.num_env_steps))
                        confirmed, settle_events = _settle_and_confirm_holding(client, target, label, leftover)
                        for event in settle_events:
                            event.setdefault("gripper_hold_value", float(client.cfg.gripper_close_value))
                        trace.events.extend(settle_events)
                        probe = next((event for event in reversed(settle_events) if event.get("event") == "grasp_lift_probe"), None)
                        dwell = next((event for event in reversed(settle_events) if event.get("event") == "grasp_close_dwell"), None)
                        snapshot = probe or dwell or {}
                        evidence = dict(snapshot.get("holding_evidence") or {})
                        _call_hook(
                            hook_bridge,
                            "after_gripper_close",
                            {
                                "label": label,
                                "object_followed": None if probe is None else probe.get("object_followed"),
                                "object_lift_m": None if probe is None else probe.get("object_lift_m"),
                                "confirmed": confirmed,
                                "aperture": snapshot.get("aperture"),
                                "bilateral": snapshot.get("bilateral_contact"),
                                "holding_status": evidence.get("status"),
                                "holding_object": evidence.get("object_name"),
                                "gripper_close_value": float(client.cfg.gripper_close_value),
                                "gripper_open_value": float(client.cfg.gripper_open_value),
                            },
                        )
                        if confirmed:
                            gripper_closed = True
                            client.latch_confirmed_holding(target, label, snapshot=snapshot)
                            result = {
                                **result,
                                "success": True,
                                "error": "",
                                "confirmed_holding": True,
                                "confirmed_holding_object": target,
                                "holding_latch_source": "lift_probe",
                            }
                        else:
                            leftover = max(0, int(max_env_steps) - int(client.num_env_steps))
                            if leftover > 0 and not client.done:
                                client.open_gripper(label=f"{label}:open_unconfirmed")
                            gripper_closed = False
                            result = {
                                "success": False,
                                "error": "gripper_closed_but_not_holding",
                                "object": target,
                                "aperture_drop": result.get("aperture_drop"),
                                "after_aperture": result.get("after_aperture"),
                                "close_error": result.get("error", ""),
                                "gripper_hold_value": float(client.cfg.gripper_open_value),
                                "action": "close",
                            }
                            trace.events.append(
                                {
                                    "step": label,
                                    "event": "skip_place_not_holding",
                                    "object": target,
                                    "reason": "lift_probe_unconfirmed",
                                    "holding_evidence": dict(getattr(client.get_scene(), "holding_evidence", None) or {}),
                                }
                            )
                else:
                    result = client.close_gripper(steps=close_steps, label=label)
                    result["gripper_hold_value"] = float(client.cfg.gripper_close_value)
                    result["action"] = "close"
                    if result.get("success"):
                        gripper_closed = True
                        _call_hook(
                            hook_bridge,
                            "after_gripper_close",
                            {
                                "label": label,
                                "object_followed": None,
                                "confirmed": False,
                                "aperture": result.get("after_aperture"),
                                "gripper_close_value": float(client.cfg.gripper_close_value),
                                "gripper_open_value": float(client.cfg.gripper_open_value),
                            },
                        )
            else:
                result = {"success": False, "error": f"unknown_gripper_action:{action}"}
        elif stype == "trajectory":
            if "place(" in low:
                if not gripper_closed:
                    result = {
                        "success": False,
                        "error": "skip_place_not_holding",
                        "skipped": "not_holding",
                    }
                    trace.events.append({"step": label, "event": "skip_place_not_holding", "reason": "gripper_not_confirmed"})
                elif placed:
                    result = {"success": True, "error": "", "skipped": "duplicate_place_segment"}
                else:
                    leftover = max(0, int(max_env_steps) - client.num_env_steps)
                    default_hold = _gripper_hold_value(
                        label,
                        gripper_closed,
                        client.cfg,
                        preserve_closed=bool(client.confirmed_holding_object()),
                    )
                    skip, hold, hook_meta = _apply_trajectory_hook(
                        hook_bridge,
                        {
                            "label": label,
                            "stype": stype,
                            "gripper_closed": gripper_closed,
                            "gripper_hold_value": default_hold,
                            "gripper_close_value": float(client.cfg.gripper_close_value),
                            "gripper_open_value": float(client.cfg.gripper_open_value),
                            "holding_latch_object": client.confirmed_holding_object(),
                        },
                        default_hold,
                    )
                    if skip:
                        result = {"success": True, "error": "", "skipped": "skill_skip", "gripper_hold_value": hold, **hook_meta}
                    else:
                        result = _execute_place_hover_and_drop(client, executable_plan, idx, leftover, label)
                        result["gripper_hold_value"] = result.get("gripper_hold_value", hold)
                        result.update(hook_meta)
                    placed = True
                    if result.get("place_events"):
                        trace.events.extend(result["place_events"])
                    if result.get("opened"):
                        gripper_closed = False
                        opened_by_place = True
            else:
                positions = step.get("positions") or []
                if not positions:
                    result = {"success": False, "error": "trajectory_missing_serialized_positions"}
                else:
                    pos = np.asarray(positions, dtype=np.float32)
                    vel = np.asarray(step.get("velocities") or np.zeros_like(pos), dtype=np.float32)
                    remaining_steps = _front_budget(client, max_env_steps, reserve_place and not placed)
                    default_hold = _gripper_hold_value(
                        label,
                        gripper_closed,
                        client.cfg,
                        preserve_closed=bool(client.confirmed_holding_object()),
                    )
                    skip, hold, hook_meta = _apply_trajectory_hook(
                        hook_bridge,
                        {
                            "label": label,
                            "stype": stype,
                            "gripper_closed": gripper_closed,
                            "gripper_hold_value": default_hold,
                            "gripper_close_value": float(client.cfg.gripper_close_value),
                            "gripper_open_value": float(client.cfg.gripper_open_value),
                            "holding_latch_object": client.confirmed_holding_object(),
                        },
                        default_hold,
                    )
                    if skip:
                        result = {"success": True, "error": "", "skipped": "skill_skip", "gripper_hold_value": hold, **hook_meta}
                    else:
                        result = client.execute_joint_impedance_path(
                            pos,
                            vel,
                            [float(step.get("dt", 0.0) or 0.0)] * len(pos),
                            max_steps=remaining_steps,
                            gripper=hold,
                            label=label,
                            track_full_pose=("pick(" in low),
                            track_pose_tail=False,
                            keep_z_during_transfer=bool(
                                client.cfg.held_transfer_keep_z
                                and gripper_closed
                                and client.confirmed_holding_object()
                                and _plan_has_place(executable_plan[idx + 1 :])
                            ),
                        )
                        result["gripper_hold_value"] = hold
                        result.update(hook_meta)
        else:
            result = {"success": False, "error": f"unknown_executable_step_type:{stype}"}

        trace.num_env_steps = client.num_env_steps
        trace.done = client.done
        trace.events.append({"step": label, "event": "execute", "type": stype, "result": result, "env_steps": client.num_env_steps - before_steps})
        trace.events.extend(client.events)
        client.events.clear()
        _call_hook(
            hook_bridge,
            "after_recovery_attempt",
            {
                "label": label,
                "stype": stype,
                "success": bool(result.get("success", False)),
                "error": result.get("error", ""),
                "skill_id": result.get("skill_id") or "",
            },
        )
        if result.get("abort_episode"):
            trace.abort_episode = True
            trace.abort_reason = str(result.get("abort_reason") or result.get("error") or "recovery_abort_episode")
            trace.events.append({"step": label, "event": "recovery_abort_episode", "reason": trace.abort_reason})
            return client.get_obs(), trace
        if result.get("handoff_to_vla"):
            trace.handoff_to_vla = True
            return client.get_obs(), trace
        if not result.get("success", False):
            trace.events.append({"step": label, "event": "execution_failed_stop", "reason": result.get("error", "")})
            return client.get_obs(), trace
        if client.done:
            trace.success = True
            return client.get_obs(), trace
        if stop_on_goal_satisfied and goal_atoms and not articulated_plan:
            goal = goal_satisfied(client.get_scene(), goal_atoms)
            trace.events.append({"step": label, "event": "goal_check", "ok": goal.ok, "reason": goal.reason, "details": goal.details})
            if goal.ok:
                trace.goal_satisfied = True
                trace.handoff_to_vla = True
                trace.success = True
                trace.events.append({"step": label, "event": "goal_satisfied_after_step"})
                return client.get_obs(), trace
    return client.get_obs(), trace
