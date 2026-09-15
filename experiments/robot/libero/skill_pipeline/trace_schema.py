"""Compact episode traces. Do not dump full contact tables."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

QUERY_TRACE_FIELDS = (
    "task_id_1based",
    "episode_idx",
    "seed",
    "query_idx",
    "env_step",
    "mode",
    "ee_xyz",
    "ee_quat",
    "gripper_qpos",
    "gripper_aperture",
    "gripper_cmd",
    "target_name",
    "target_xyz",
    "target_quat",
    "target_orientation",
    "target_upright_axis_alignment",
    "target_ee_distance_m",
    "goal_name",
    "goal_xyz",
    "bddl_goal_surfaces",
    "bddl_goal_atoms",
    "bddl_regions",
    "nearest_pickable_name",
    "nearest_pickable_distance_m",
    "nearest_pickable_is_target",
    "vla_pick_target_status",
    "intent_object_name",
    "intent_object_is_target",
    "intent_min_xy_distance_m",
    "target_future_min_xy_distance_m",
    "wrong_object_intent_margin_m",
    "wrong_object_intent_persist_queries",
    "intent_object_motion_m",
    "intent_object_total_motion_m",
    "target_motion_m",
    "target_total_motion_m",
    "wrong_progress_object_name",
    "wrong_progress_object_total_motion_m",
    "wrong_progress_object_step_motion_m",
    "wrong_progress_object_goal_xy_distance_m",
    "wrong_progress_object_ee_distance_m",
    "wrong_progress_object_is_intent",
    "wrong_progress_object_is_held",
    "wrong_progress_target_static",
    "vla_wrong_object_progress_status",
    "nearest_articulated_blocker_name",
    "nearest_articulated_blocker_distance_m",
    "path_articulated_blocker_name",
    "path_articulated_blocker_min_xy_distance_m",
    "blocker_target_future_min_xy_distance_m",
    "articulated_blocker_joint_state_known",
    "articulated_blocker_open_joint_names",
    "articulated_blocker_contact",
    "articulated_blocker_contact_name",
    "articulated_blocker_contact_robot_name",
    "articulated_blocker_contact_count",
    "articulated_blocker_contact_min_distance_m",
    "articulated_blocker_contact_persist_queries",
    "vla_articulated_blocker_status",
    "holding_status",
    "holding_object",
    "bilateral",
    "object_followed",
    "logvar_gripper_first",
    "residual_score",
    "diagnostic_signals",
    "hook_fired",
    "skill_id",
    "recovery_hints",
    "skill_match_diagnostics",
)

RECOVERY_KINDS = ("rule", "close", "lift_probe", "trajectory", "place", "open", "plan", "execution_bridge")


class TraceSchemaError(ValueError):
    """Trace record is missing required fields or uses a forbidden encoding."""


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def compact_holding(scene: Any, target_name: str | None = None) -> dict[str, Any]:
    evidence = dict(getattr(scene, "holding_evidence", None) or {})
    holding_object = evidence.get("object_name")
    bilateral = None
    for cand in evidence.get("candidates") or []:
        name = cand.get("object_name")
        if holding_object and name == holding_object:
            bilateral = bool(cand.get("bilateral_contact"))
            break
        if target_name and name == target_name and bilateral is None:
            bilateral = bool(cand.get("bilateral_contact"))
    return {
        "holding_status": evidence.get("status"),
        "holding_object": holding_object,
        "bilateral": bilateral,
    }


def make_query_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = {key: _jsonable(payload.get(key)) for key in QUERY_TRACE_FIELDS}
    if record.get("mode") not in ("vla", "recovery"):
        raise TraceSchemaError("mode must be 'vla' or 'recovery'")
    followed = record.get("object_followed")
    if followed is not True and followed is not False and followed is not None:
        raise TraceSchemaError("object_followed must be true, false, or null (not 0/1)")
    nearest_is_target = record.get("nearest_pickable_is_target")
    if nearest_is_target is not True and nearest_is_target is not False and nearest_is_target is not None:
        raise TraceSchemaError("nearest_pickable_is_target must be true, false, or null (not 0/1)")
    intent_is_target = record.get("intent_object_is_target")
    if intent_is_target is not True and intent_is_target is not False and intent_is_target is not None:
        raise TraceSchemaError("intent_object_is_target must be true, false, or null (not 0/1)")
    for key in ("wrong_progress_object_is_intent", "wrong_progress_object_is_held", "wrong_progress_target_static"):
        value = record.get(key)
        if value is not True and value is not False and value is not None:
            raise TraceSchemaError(f"{key} must be true, false, or null (not 0/1)")
    diagnostics = record.get("diagnostic_signals")
    if diagnostics is None:
        record["diagnostic_signals"] = {}
    elif not isinstance(diagnostics, dict):
        raise TraceSchemaError("diagnostic_signals must be a mapping")
    return record


def validate_query_record(record: Mapping[str, Any]) -> None:
    optional_fields = {"diagnostic_signals"}
    missing = [key for key in QUERY_TRACE_FIELDS if key not in record and key not in optional_fields]
    if missing:
        raise TraceSchemaError(f"query_trace missing fields: {missing}")
    make_query_record(record)


def _kind_from_execute(label: str, stype: str, result: Mapping[str, Any]) -> str:
    low = str(label or "").lower()
    if stype == "gripper":
        action = str(result.get("action") or "")
        if "open" in low or action == "open":
            return "open"
        return "close"
    if "place" in low or str(result.get("kind") or "").startswith("place"):
        return "place"
    return "trajectory"


def _pick_fields(source: Mapping[str, Any], names: Iterable[str]) -> dict[str, Any]:
    return {name: _jsonable(source.get(name)) for name in names if name in source}


def _compact_holding_evidence(value: Any) -> dict[str, Any]:
    evidence = dict(value or {})
    candidates = list(evidence.get("candidates") or [])
    return {
        "status": evidence.get("status"),
        "object_name": evidence.get("object_name"),
        "num_candidates": len(candidates),
        "candidates": [
            {
                key: _jsonable(cand.get(key))
                for key in (
                    "object_name",
                    "bilateral_contact",
                    "left_contact",
                    "right_contact",
                    "distance",
                    "aperture",
                )
                if key in cand
            }
            for cand in candidates[:4]
            if isinstance(cand, Mapping)
        ],
    }


def recovery_events_from_trace(
    events: Iterable[Mapping[str, Any]],
    *,
    query_idx: int | None = None,
    skill_id: str = "",
) -> list[dict[str, Any]]:
    """Flatten executor events into compact recovery_trace rows."""
    rows: list[dict[str, Any]] = []
    for event in events:
        name = str(event.get("event") or "")
        etype = str(event.get("type") or "")
        label = str(event.get("step") or event.get("label") or "")
        if name == "grasp_close_dwell":
            row = {
                "kind": "close",
                "event": name,
                "label": label,
                "query_idx": query_idx,
                "gripper_hold_value": event.get("gripper_hold_value"),
                "success": True,
                "error": "",
                "aperture": event.get("aperture"),
                "object_followed": None,
                "object_lift_m": None,
                "confirmed": None,
                "hook_fired": False,
                "skill_id": skill_id,
            }
            row.update(_pick_fields(event, ("holding", "bilateral_contact", "object_z", "gripper_open")))
            row["holding_evidence"] = _compact_holding_evidence(event.get("holding_evidence"))
            rows.append(row)
        elif name == "grasp_close_precheck":
            row = {
                "kind": "close",
                "event": name,
                "label": label,
                "query_idx": query_idx,
                "success": bool(event.get("near")),
                "error": "" if event.get("near") else "grasp_target_not_near_precheck",
                "hook_fired": False,
                "skill_id": skill_id,
            }
            row.update(
                _pick_fields(
                    event,
                    (
                        "object",
                        "ee_xyz",
                        "ee_quat",
                        "gripper_qpos",
                        "aperture",
                        "object_xyz",
                        "holding",
                        "xy_m",
                        "z_delta_m",
                        "max_xy_m",
                        "max_above_m",
                        "near",
                        "planned_close_step_idx",
                        "planned_close_num_waypoints",
                        "planned_close_q",
                        "planned_close_xyz",
                        "planned_close_quat_xyzw",
                        "planned_close_pos_error_m",
                        "planned_close_orientation_error_rad",
                    ),
                )
            )
            row["holding_evidence"] = _compact_holding_evidence(event.get("holding_evidence"))
            rows.append(row)
        elif name == "grasp_lift_probe":
            row = {
                "kind": "lift_probe",
                "event": name,
                "label": label,
                "query_idx": query_idx,
                "gripper_hold_value": event.get("gripper_hold_value"),
                "success": True,
                "error": "",
                "aperture": event.get("aperture"),
                "object_followed": event.get("object_followed"),
                "object_lift_m": event.get("object_lift_m"),
                "confirmed": event.get("confirmed"),
                "hook_fired": False,
                "skill_id": skill_id,
            }
            row.update(
                _pick_fields(
                    event,
                    ("lift_m", "bilateral_contact", "holding", "object_z", "gripper_open"),
                )
            )
            row["lift_result"] = _jsonable(event.get("lift_result"))
            row["holding_evidence"] = _compact_holding_evidence(event.get("holding_evidence"))
            rows.append(row)
        elif name in {"execute", "execute_optimized_operator"}:
            result = dict(event.get("result") or {})
            stype = str(event.get("type") or event.get("operator") or "")
            error = str(result.get("error") or event.get("error") or "")
            row = {
                "kind": _kind_from_execute(label, stype, result),
                "event": name,
                "label": label,
                "query_idx": query_idx,
                "gripper_hold_value": result.get("gripper_hold_value"),
                "success": bool(result.get("success", False)),
                "error": error,
                "aperture": result.get("after_aperture", result.get("aperture")),
                "object_followed": result.get("object_followed"),
                "object_lift_m": result.get("object_lift_m"),
                "confirmed": result.get("confirmed_holding"),
                "skipped": result.get("skipped"),
                "hook_fired": bool(result.get("hook_fired")),
                "skill_id": result.get("skill_id") or skill_id,
                "backend": result.get("backend") or "",
                "handoff_to_vla": bool(result.get("handoff_to_vla")),
                "abort_episode": bool(result.get("abort_episode")),
                "abort_reason": str(result.get("abort_reason") or ""),
                "env_steps": event.get("env_steps", result.get("env_steps")),
            }
            row.update(
                _pick_fields(
                    result,
                    (
                        "action",
                        "object",
                        "opened",
                        "done",
                        "near_goal_handoff",
                        "segment_end_position_error",
                        "segment_end_orientation_error_rad",
                        "planned_end_position",
                        "planned_end_quat_xyzw",
                        "bowl_xy_to_opening",
                        "bowl_clearance_m",
                        "geometry",
                    ),
                )
            )
            rows.append(row)
        elif name in {
            "place_targets",
            "place_lift",
            "place_lift_clearance",
            "held_transfer_keep_z",
            "place_hover",
            "place_hover_xy",
            "place_hover_xy_correct",
            "place_hover_xy_after_correct",
            "place_hover_yaw",
            "place_held_object_xy_align",
            "place_after_yaw_align_xy",
            "place_drop",
            "place_drop_closed_loop_xy_align",
            "place_drop_xy_correct",
            "place_release_check",
            "place_release_check_retry",
            "place_open",
        }:
            row = {
                "kind": "place",
                "event": name,
                "label": label,
                "query_idx": query_idx,
                "success": bool(event.get("success", event.get("ok", True))),
                "error": str(event.get("error") or ""),
                "hook_fired": False,
                "skill_id": skill_id,
            }
            row.update(
                _pick_fields(
                    event,
                    (
                        "object",
                        "surface",
                        "surface_label",
                        "surface_resolved",
                        "opening_source",
                        "opening_frame",
                        "opening_frame_conversion_applied",
                        "opening_frame_conversion_reason",
                        "opening_center_xy",
                        "opening_center_xy_planner",
                        "opening_center_xy_world",
                        "support_z_planner",
                        "support_z_world",
                        "object_aabb_bottom",
                        "surface_aabb_top",
                        "hanging_m",
                        "lift_z",
                        "ee_z",
                        "surf_top",
                        "bowl_clearance_m",
                        "min_clearance_m",
                        "drop_z",
                        "planned_end",
                        "planned_endpoint",
                        "planned_endpoint_z",
                        "protected_endpoint",
                        "protected_z",
                        "final_ee_z",
                        "max_descent_m",
                        "z_margin_m",
                        "phase",
                        "grasp_offset_xy",
                        "bowl_xy",
                        "object_hx_m",
                        "object_hy_m",
                        "allowed_xy_m",
                        "ee_xy_to_opening",
                        "bowl_xy_to_opening",
                        "in_opening",
                        "in_shrunk",
                        "xy_dist",
                        "z_delta",
                        "object_xy",
                        "object_z",
                        "support_z",
                        "z_ok",
                        "release_guard_reason",
                        "env_steps",
                        "skipped",
                        "ok",
                        "opened",
                        "current_yaw_rad",
                        "target_yaw_rad",
                        "delta_yaw_rad",
                        "final_yaw_rad",
                        "initial_object_hx_m",
                        "initial_object_hy_m",
                        "executed",
                        "alignment_mode",
                        "closed_loop",
                        "closed_loop_align_env_steps",
                        "target_drop_z",
                        "start_z",
                        "drop_slice",
                        "slices",
                        "iterations",
                        "object_footprint_xy",
                        "safe_opening_xy",
                        "footprint_delta_xy",
                        "containment_delta_xy",
                        "footprint_violation_m",
                        "final_footprint_violation_m",
                        "footprint_center_xy",
                        "safe_center_xy",
                        "footprint_center_delta_xy",
                        "footprint_center_xy_dist",
                        "final_footprint_center_xy_dist",
                        "center_tolerance_m",
                        "footprint_centered",
                        "final_alignment_error_m",
                        "residual_after_delta_m",
                        "footprint_contained",
                        "footprint_fits",
                        "oversize_axes",
                        "final_xy_dist",
                        "final_in_opening",
                        "initial_orientation_error_rad",
                        "final_orientation_error_rad",
                    ),
                )
            )
            if "opening" in event:
                row["opening"] = _jsonable(event.get("opening"))
            if "shrunk_opening" in event:
                row["shrunk_opening"] = _jsonable(event.get("shrunk_opening"))
            rows.append(row)
        elif etype == "optimized_cutamp_trajectory":
            row = {
                "kind": "trajectory",
                "event": etype,
                "label": label,
                "query_idx": query_idx,
                "success": bool(event.get("success", False)),
                "error": str(event.get("failure_reason") or ""),
                "hook_fired": False,
                "skill_id": skill_id,
            }
            row.update(
                _pick_fields(
                    event,
                    (
                        "env_steps",
                        "near_goal_handoff",
                        "segment_end_position_error",
                        "segment_end_orientation_error_rad",
                        "original_waypoint_count",
                        "tracking_waypoint_count",
                        "position_and_orientation_tracking",
                    ),
                )
            )
            rows.append(row)
        elif name == "execution_failed_stop":
            rows.append(
                {
                    "kind": "trajectory",
                    "event": name,
                    "label": label,
                    "query_idx": query_idx,
                    "success": False,
                    "error": str(event.get("reason") or ""),
                    "hook_fired": False,
                    "skill_id": skill_id,
                }
            )
        elif name in {"skip_place_not_holding", "grasp_skip_not_near"}:
            rows.append(
                {
                    "kind": "place" if name == "skip_place_not_holding" else "close",
                    "event": name,
                    "label": label,
                    "query_idx": query_idx,
                    "success": False,
                    "error": str(event.get("reason") or name),
                    "skipped": name,
                    "hook_fired": False,
                    "skill_id": skill_id,
                    "holding_evidence": _compact_holding_evidence(event.get("holding_evidence")),
                }
            )
        elif name in {"goal_check", "goal_satisfied_after_step", "max_env_steps"}:
            row = {
                "kind": "plan",
                "event": name,
                "label": label,
                "query_idx": query_idx,
                "success": bool(event.get("ok", name == "goal_satisfied_after_step")),
                "error": "" if event.get("ok", name == "goal_satisfied_after_step") else str(event.get("reason") or name),
                "hook_fired": False,
                "skill_id": skill_id,
            }
            row.update(_pick_fields(event, ("details", "operator_idx", "step")))
            rows.append(row)
    return rows


def recover_without_execution_event(
    attempt: Mapping[str, Any] | Any,
    *,
    query_idx: int | None = None,
    skill_id: str = "",
) -> dict[str, Any]:
    """Compact row when recover() ran but produced no executor events."""
    backend = {}
    plan_reason = ""
    if isinstance(attempt, Mapping):
        backend = dict(attempt.get("planner_backend") or {})
        plan_reason = str(attempt.get("plan_reason") or "")
    else:
        backend = dict(getattr(attempt, "planner_backend", None) or {})
        plan_reason = str(getattr(attempt, "plan_reason", "") or "")
    execution_source = str(backend.get("execution_source") or "")
    real = dict(backend.get("real_cutamp") or {})
    selected = dict(real.get("selected_result") or {})
    if not selected.get("failure_reason"):
        attempts = list(real.get("attempts") or [])
        if attempts:
            selected = dict((attempts[-1] or {}).get("result") or selected)
    failure_reason = str(
        selected.get("failure_reason") or plan_reason or execution_source or "recover_without_execution"
    )
    return {
        "kind": "plan",
        "label": plan_reason or execution_source or "recover",
        "query_idx": query_idx,
        "success": False,
        "error": failure_reason,
        "execution_source": execution_source,
        "num_satisfying": selected.get("num_satisfying"),
        "hook_fired": bool(skill_id),
        "skill_id": skill_id,
    }


@dataclass
class EpisodeWriter:
    episode_dir: Path
    query_path: Path = field(init=False)
    recovery_path: Path = field(init=False)
    frames_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.episode_dir = Path(self.episode_dir)
        self.episode_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir = self.episode_dir / "frames"
        self.frames_dir.mkdir(exist_ok=True)
        self.query_path = self.episode_dir / "query_trace.jsonl"
        self.recovery_path = self.episode_dir / "recovery_trace.jsonl"
        self.query_path.write_text("", encoding="utf-8")
        self.recovery_path.write_text("", encoding="utf-8")

    def append_query(self, record: Mapping[str, Any]) -> None:
        validate_query_record(record)
        with self.query_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(make_query_record(record), ensure_ascii=False) + "\n")

    def append_recovery(self, record: Mapping[str, Any]) -> None:
        with self.recovery_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_jsonable(dict(record)), ensure_ascii=False) + "\n")

    def append_recovery_from_trace(self, events: Iterable[Mapping[str, Any]], **kwargs: Any) -> None:
        for row in recovery_events_from_trace(events, **kwargs):
            self.append_recovery(row)

    def save_query_frame(self, query_idx: int, image: Any, suffix: str = "agentview") -> str:
        path = self.frames_dir / f"q{int(query_idx):04d}_{suffix}.jpg"
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            return ""
        arr = np.asarray(image)
        Image.fromarray(arr).save(path, quality=90)
        return str(path.relative_to(self.episode_dir))

    def write_episode_json(self, payload: Mapping[str, Any]) -> None:
        path = self.episode_dir / "episode.json"
        path.write_text(json.dumps(_jsonable(dict(payload)), ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    file_path = Path(path)
    if not file_path.exists():
        return rows
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
