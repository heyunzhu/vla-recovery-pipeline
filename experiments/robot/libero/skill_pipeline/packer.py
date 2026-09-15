"""Pack success/fail pairs or fail-only sets for the offline actor."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .trace_schema import read_jsonl

KEYFRAME_SLOTS = ("approach", "close", "lift", "release", "place")
FAIL_ONLY_SLOTS = ("approach", "mid", "stall", "end")


def _aperture(row: Mapping[str, Any]) -> float | None:
    value = row.get("gripper_aperture")
    return None if value is None else float(value)


def _ee_z(row: Mapping[str, Any]) -> float | None:
    xyz = row.get("ee_xyz")
    if isinstance(xyz, (list, tuple)) and len(xyz) >= 3:
        return float(xyz[2])
    return None


def _ee_xyz(row: Mapping[str, Any]) -> list[float] | None:
    xyz = row.get("ee_xyz")
    if isinstance(xyz, (list, tuple)) and len(xyz) >= 3:
        return [float(xyz[0]), float(xyz[1]), float(xyz[2])]
    return None


def _cmd(row: Mapping[str, Any]) -> float | None:
    value = row.get("gripper_cmd")
    return None if value is None else float(value)


def _summarize_queries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "query_idx",
        "env_step",
        "mode",
        "ee_xyz",
        "gripper_aperture",
        "gripper_cmd",
        "target_name",
        "target_orientation",
        "target_upright_axis_alignment",
        "target_ee_distance_m",
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
        "nearest_articulated_blocker_name",
        "nearest_articulated_blocker_distance_m",
        "path_articulated_blocker_name",
        "path_articulated_blocker_min_xy_distance_m",
        "blocker_target_future_min_xy_distance_m",
        "articulated_blocker_joint_state_known",
        "articulated_blocker_open_joint_names",
        "vla_articulated_blocker_status",
        "holding_status",
        "holding_object",
        "bilateral",
        "object_followed",
        "hook_fired",
        "skill_id",
        "logvar_gripper_first",
        "residual_score",
    )
    return [{key: row.get(key) for key in keep} for row in rows]


def _disp(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))


def _pick_slot(rows: Sequence[Mapping[str, Any]], slot: str) -> Mapping[str, Any] | None:
    if not rows:
        return None
    if slot == "approach":
        open_rows = [row for row in rows if (_aperture(row) or 0.0) > 0.02]
        return open_rows[min(3, len(open_rows) - 1)] if open_rows else rows[0]
    if slot == "close":
        best = None
        best_drop = -1.0
        prev = None
        for row in rows:
            if prev is not None and _aperture(row) is not None and _aperture(prev) is not None:
                drop = float(_aperture(prev)) - float(_aperture(row))
                if drop > best_drop:
                    best_drop = drop
                    best = row
            prev = row
        return best if best_drop > 0.005 else None
    if slot == "lift":
        prev_z = None
        for row in rows:
            z_now = _ee_z(row)
            if prev_z is not None and z_now is not None and z_now - prev_z >= 0.01:
                if (_aperture(row) or 1.0) < 0.03:
                    return row
            prev_z = z_now
        return None
    if slot == "release":
        prev = None
        for row in rows:
            if prev is not None and _cmd(row) is not None and _cmd(prev) is not None:
                if float(_cmd(prev)) > 0.0 and float(_cmd(row)) < 0.0:
                    return row
            prev = row
        return None
    if slot == "place":
        return rows[min(len(rows) - 1, max(0, len(rows) - 3))]
    if slot == "mid":
        return rows[len(rows) // 2]
    if slot == "end":
        return rows[-1]
    if slot == "stall":
        window = min(6, len(rows))
        best = rows[-1]
        best_disp = float("inf")
        for end in range(window - 1, len(rows)):
            start = rows[end - window + 1]
            last = rows[end]
            a = _ee_xyz(start)
            b = _ee_xyz(last)
            if a is None or b is None:
                continue
            dist = _disp(a, b)
            if dist < best_disp:
                best_disp = dist
                best = last
        return best
    return None


def _frame_rel(episode_dir: Path, query_idx: Any) -> str | None:
    if query_idx is None:
        return None
    path = episode_dir / "frames" / f"q{int(query_idx):04d}_agentview.jpg"
    if path.exists():
        return str(path)
    return None


def _recovery_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(item.get("recovery") or [])
    return {
        "recovery_trace_path": item["recovery_path"],
        "recovery_event_count": len(rows),
        "recovery_available": bool(rows),
    }


def _failure_entry(item: Mapping[str, Any]) -> dict[str, Any]:
    rec = _recovery_summary(item)
    return {
        "episode_dir": item["dir"],
        "episode_idx": item["meta"].get("episode_idx"),
        "seed": item["meta"].get("seed"),
        "success": bool(item["meta"].get("success")),
        "queries": _summarize_queries(item["queries"]),
        **rec,
    }


def load_episode(episode_dir: str | Path) -> dict[str, Any]:
    path = Path(episode_dir)
    meta = json.loads((path / "episode.json").read_text(encoding="utf-8"))
    recovery_path = path / "recovery_trace.jsonl"
    return {
        "dir": str(path),
        "meta": meta,
        "queries": read_jsonl(path / "query_trace.jsonl"),
        "recovery_path": str(recovery_path),
        "recovery": read_jsonl(recovery_path),
    }


def _aligned_frames(
    slots: Sequence[str],
    success_rows: Sequence[Mapping[str, Any]] | None,
    fail_item: Mapping[str, Any] | None,
    success_dir: Path | None,
) -> list[dict[str, Any]]:
    aligned = []
    fail_rows = fail_item["queries"] if fail_item else []
    for slot in slots:
        s_row = _pick_slot(success_rows or [], slot) if success_rows is not None else None
        f_row = _pick_slot(fail_rows, slot)
        if s_row is None and f_row is None:
            continue
        aligned.append(
            {
                "slot": slot,
                "query_idx": (s_row or f_row).get("query_idx"),
                "success_frame": _frame_rel(success_dir, (s_row or {}).get("query_idx")) if success_dir else None,
                "fail_frame": _frame_rel(Path(fail_item["dir"]), (f_row or {}).get("query_idx")) if fail_item else None,
            }
        )
    return aligned


def _write_payload(payload: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def pack_pair(
    success_dir: str | Path,
    fail_dirs: Sequence[str | Path],
    out_path: str | Path,
    task: str = "",
) -> dict[str, Any]:
    success = load_episode(success_dir)
    failures = [load_episode(path) for path in fail_dirs]
    success_rows = success["queries"]
    payload = {
        "track": "pair",
        "pack_kind": "pair",
        "task": task or success["meta"].get("task_description", ""),
        "recovery_required": False,
        "success": {
            "episode_dir": success["dir"],
            "episode_idx": success["meta"].get("episode_idx"),
            "seed": success["meta"].get("seed"),
            "success": True,
            "queries": _summarize_queries(success_rows),
            **_recovery_summary(success),
        },
        "failures": [_failure_entry(item) for item in failures],
        "aligned_frames": _aligned_frames(KEYFRAME_SLOTS, success_rows, failures[0] if failures else None, Path(success["dir"])),
        "recovery_trace_paths": [item["recovery_path"] for item in failures],
        "note": (
            "Do not inline recovery_trace.jsonl. Open the path only if recovery_available is true. "
            "Empty recovery traces are valid for VLA-only writing rollouts."
        ),
    }
    return _write_payload(payload, out_path)


def pack_fail_set(
    fail_dirs: Sequence[str | Path],
    out_path: str | Path,
    task: str = "",
) -> dict[str, Any]:
    if not fail_dirs:
        raise ValueError("pack_fail_set requires at least one failure episode")
    failures = [load_episode(path) for path in fail_dirs]
    payload = {
        "track": "fail_only",
        "pack_kind": "fail_set",
        "task": task or failures[0]["meta"].get("task_description", ""),
        "recovery_required": False,
        "success": None,
        "failures": [_failure_entry(item) for item in failures],
        "aligned_frames": _aligned_frames(FAIL_ONLY_SLOTS, None, failures[0], None),
        "recovery_trace_paths": [item["recovery_path"] for item in failures],
        "note": (
            "Fail-only pack: no success contrast. recovery_trace.jsonl may be empty. "
            "Write a VLA-stall trigger that enters cutamp_recover; do not invent a new backend. "
            "Do not require close/lift_probe/Pick labels if recovery_available is false."
        ),
    }
    return _write_payload(payload, out_path)
