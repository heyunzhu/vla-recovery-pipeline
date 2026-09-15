"""Shadow diagnostic for target-approach repair timing.

This signal is intentionally not a trigger. It records whether existing qstate
evidence resembles a safe pre-grasp handoff window.
"""

from __future__ import annotations

from typing import Any, Mapping


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute(state: Mapping[str, Any], history: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    del history
    aperture = _as_float(state.get("gripper_aperture", state.get("aperture")))
    target_ee = _as_float(state.get("target_ee_distance_m"))
    target_future = _as_float(state.get("target_future_min_xy_distance_m"))
    holding = str(state.get("holding_status") or "")
    nearest_is_target = state.get("nearest_pickable_is_target")
    intent_is_target = state.get("intent_object_is_target")

    open_empty = bool(aperture is not None and aperture > 0.025 and holding == "handempty_or_unconfirmed")
    near_target = bool(target_ee is not None and target_ee <= 0.16)
    has_target_evidence = bool(
        nearest_is_target is True
        or intent_is_target is True
        or (target_future is not None and target_future <= 0.09)
    )
    active = bool(open_empty and near_target and has_target_evidence)
    score = 0.0
    if open_empty:
        score += 0.35
    if near_target and target_ee is not None:
        score += max(0.0, min(0.35, (0.16 - target_ee) / 0.16 * 0.35))
    if has_target_evidence:
        score += 0.30
    return {
        "diag_target_approach_window_v1": active,
        "diag_target_approach_window_v1_score": round(float(score), 4),
    }
