"""Held-out trigger stats and same-init skill on/off comparison.

Thresholds are constants. Changing them requires updating tests; do not
relax them inside a skill file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .matcher import eval_trigger
from .schema import SkillSpec

# 2026-09-16: the "failed-episode recall" floor is DISABLED (set to 0.0) by the project owner.
# Recall is still computed and reported (admission/validation reports print it), but it no longer
# blocks a write: it is a prediction of usefulness computed offline, not a property of the skill.
# Set to e.g. 0.60 to re-enable the old gate behavior.
FAIL_RECALL_MIN = 0.0
SUCCESS_EPISODE_FIRE_MAX = 0.10
SUCCESS_MAX_FIRE_QUERIES = 2
SUCCESS_REGRESSION_RATE_MAX = 0.0


@dataclass
class TriggerMetrics:
    n_fail: int = 0
    n_fail_hit: int = 0
    n_success: int = 0
    n_success_fire: int = 0
    late_irreversible: int = 0
    fail_hits: list[str] = field(default_factory=list)
    success_fires: list[str] = field(default_factory=list)

    @property
    def fail_recall(self) -> float:
        return 0.0 if self.n_fail == 0 else self.n_fail_hit / self.n_fail

    @property
    def success_fire_rate(self) -> float:
        return 0.0 if self.n_success == 0 else self.n_success_fire / self.n_success


@dataclass
class SameInitMetrics:
    n_pairs: int = 0
    n_improved: int = 0
    n_regressed: int = 0
    off_success: int = 0
    on_success: int = 0


def _label_is_irreversible_open(label: str, gripper_hold_value: Any) -> bool:
    low = str(label or "").lower()
    if "pick(" not in low and "movefree" not in low:
        return False
    if gripper_hold_value is None:
        return True
    return float(gripper_hold_value) < 0.0


def episode_id(episode: Mapping[str, Any]) -> str:
    meta = episode.get("meta") or episode
    return f"task{meta.get('task_id_1based')}_ep{meta.get('episode_idx')}_seed{meta.get('seed')}"


def _episode_id(episode: Mapping[str, Any]) -> str:
    return episode_id(episode)


def _state_from_recovery(row: Mapping[str, Any], followed: Any, history: list[Any]) -> dict[str, Any]:
    return {
        "label": row.get("label"),
        "task_description": row.get("task_description") or row.get("language"),
        "language": row.get("language") or row.get("task_description"),
        "target_name": row.get("target_name") or row.get("target"),
        "target": row.get("target") or row.get("target_name"),
        "goal_name": row.get("goal_name") or row.get("goal"),
        "goal": row.get("goal") or row.get("goal_name"),
        "surface_name": row.get("surface_name") or row.get("surface"),
        "surface": row.get("surface") or row.get("surface_name"),
        "bddl_goal_surface": row.get("bddl_goal_surface"),
        "bddl_goal_surfaces": row.get("bddl_goal_surfaces"),
        "aperture": row.get("aperture"),
        "gripper_cmd": row.get("gripper_cmd"),
        "object_followed": followed if followed is not None else row.get("object_followed"),
        "holding_status": row.get("holding_status"),
        "target_orientation": row.get("target_orientation"),
        "target_upright_axis_alignment": row.get("target_upright_axis_alignment"),
        "target_ee_distance_m": row.get("target_ee_distance_m"),
        "nearest_pickable_name": row.get("nearest_pickable_name"),
        "nearest_pickable_distance_m": row.get("nearest_pickable_distance_m"),
        "nearest_pickable_is_target": row.get("nearest_pickable_is_target"),
        "vla_pick_target_status": row.get("vla_pick_target_status"),
        "intent_object_name": row.get("intent_object_name"),
        "intent_object_is_target": row.get("intent_object_is_target"),
        "intent_min_xy_distance_m": row.get("intent_min_xy_distance_m"),
        "target_future_min_xy_distance_m": row.get("target_future_min_xy_distance_m"),
        "wrong_object_intent_margin_m": row.get("wrong_object_intent_margin_m"),
        "wrong_object_intent_persist_queries": row.get("wrong_object_intent_persist_queries"),
        "intent_object_motion_m": row.get("intent_object_motion_m"),
        "intent_object_total_motion_m": row.get("intent_object_total_motion_m"),
        "target_motion_m": row.get("target_motion_m"),
        "target_total_motion_m": row.get("target_total_motion_m"),
        "nearest_articulated_blocker_name": row.get("nearest_articulated_blocker_name"),
        "nearest_articulated_blocker_distance_m": row.get("nearest_articulated_blocker_distance_m"),
        "path_articulated_blocker_name": row.get("path_articulated_blocker_name"),
        "path_articulated_blocker_min_xy_distance_m": row.get("path_articulated_blocker_min_xy_distance_m"),
        "blocker_target_future_min_xy_distance_m": row.get("blocker_target_future_min_xy_distance_m"),
        "articulated_blocker_joint_state_known": row.get("articulated_blocker_joint_state_known"),
        "articulated_blocker_open_joint_names": row.get("articulated_blocker_open_joint_names"),
        "vla_articulated_blocker_status": row.get("vla_articulated_blocker_status"),
        "wrong_progress_object_total_motion_m": row.get("wrong_progress_object_total_motion_m"),
        "wrong_progress_object_goal_xy_distance_m": row.get("wrong_progress_object_goal_xy_distance_m"),
        "wrong_progress_object_is_intent": row.get("wrong_progress_object_is_intent"),
        "wrong_progress_object_is_held": row.get("wrong_progress_object_is_held"),
        "wrong_progress_target_static": row.get("wrong_progress_target_static"),
        "vla_wrong_object_progress_status": row.get("vla_wrong_object_progress_status"),
        "ee_history": list(history),
        "ee_xyz": row.get("ee_xyz"),
        "gripper_aperture": row.get("aperture"),
    }


def _state_from_query(row: Mapping[str, Any], history: list[Any]) -> dict[str, Any]:
    return {
        "label": row.get("label") or "",
        "task_description": row.get("task_description") or row.get("language"),
        "language": row.get("language") or row.get("task_description"),
        "target_name": row.get("target_name") or row.get("target"),
        "target": row.get("target") or row.get("target_name"),
        "goal_name": row.get("goal_name") or row.get("goal"),
        "goal": row.get("goal") or row.get("goal_name"),
        "surface_name": row.get("surface_name") or row.get("surface"),
        "surface": row.get("surface") or row.get("surface_name"),
        "bddl_goal_surface": row.get("bddl_goal_surface"),
        "bddl_goal_surfaces": row.get("bddl_goal_surfaces"),
        "aperture": row.get("gripper_aperture"),
        "gripper_cmd": row.get("gripper_cmd"),
        "object_followed": row.get("object_followed"),
        "holding_status": row.get("holding_status"),
        "target_orientation": row.get("target_orientation"),
        "target_upright_axis_alignment": row.get("target_upright_axis_alignment"),
        "target_ee_distance_m": row.get("target_ee_distance_m"),
        "nearest_pickable_name": row.get("nearest_pickable_name"),
        "nearest_pickable_distance_m": row.get("nearest_pickable_distance_m"),
        "nearest_pickable_is_target": row.get("nearest_pickable_is_target"),
        "vla_pick_target_status": row.get("vla_pick_target_status"),
        "intent_object_name": row.get("intent_object_name"),
        "intent_object_is_target": row.get("intent_object_is_target"),
        "intent_min_xy_distance_m": row.get("intent_min_xy_distance_m"),
        "target_future_min_xy_distance_m": row.get("target_future_min_xy_distance_m"),
        "wrong_object_intent_margin_m": row.get("wrong_object_intent_margin_m"),
        "wrong_object_intent_persist_queries": row.get("wrong_object_intent_persist_queries"),
        "intent_object_motion_m": row.get("intent_object_motion_m"),
        "intent_object_total_motion_m": row.get("intent_object_total_motion_m"),
        "target_motion_m": row.get("target_motion_m"),
        "target_total_motion_m": row.get("target_total_motion_m"),
        "nearest_articulated_blocker_name": row.get("nearest_articulated_blocker_name"),
        "nearest_articulated_blocker_distance_m": row.get("nearest_articulated_blocker_distance_m"),
        "path_articulated_blocker_name": row.get("path_articulated_blocker_name"),
        "path_articulated_blocker_min_xy_distance_m": row.get("path_articulated_blocker_min_xy_distance_m"),
        "blocker_target_future_min_xy_distance_m": row.get("blocker_target_future_min_xy_distance_m"),
        "articulated_blocker_joint_state_known": row.get("articulated_blocker_joint_state_known"),
        "articulated_blocker_open_joint_names": row.get("articulated_blocker_open_joint_names"),
        "vla_articulated_blocker_status": row.get("vla_articulated_blocker_status"),
        "wrong_progress_object_total_motion_m": row.get("wrong_progress_object_total_motion_m"),
        "wrong_progress_object_goal_xy_distance_m": row.get("wrong_progress_object_goal_xy_distance_m"),
        "wrong_progress_object_is_intent": row.get("wrong_progress_object_is_intent"),
        "wrong_progress_object_is_held": row.get("wrong_progress_object_is_held"),
        "wrong_progress_target_static": row.get("wrong_progress_target_static"),
        "vla_wrong_object_progress_status": row.get("vla_wrong_object_progress_status"),
        "ee_history": list(history),
        "ee_xyz": row.get("ee_xyz"),
        "gripper_aperture": row.get("gripper_aperture"),
    }


def iter_fire_indices(skill: SkillSpec, episode: Mapping[str, Any]) -> list[int]:
    fires: list[int] = []
    history: list[Any] = []
    followed = None
    if skill.hook == "after_pi0_query":
        for idx, row in enumerate(episode.get("queries") or []):
            xyz = row.get("ee_xyz")
            if isinstance(xyz, (list, tuple)):
                history.append(xyz)
            if eval_trigger(
                skill.trigger,
                _state_from_query(row, history),
                predicate_registry=getattr(skill, "predicate_registry", None),
            ):
                fires.append(idx)
        return fires
    for idx, row in enumerate(episode.get("recovery") or []):
        if row.get("object_followed") is not None:
            followed = row.get("object_followed")
        if eval_trigger(
            skill.trigger,
            _state_from_recovery(row, followed, history),
            predicate_registry=getattr(skill, "predicate_registry", None),
        ):
            fires.append(idx)
    return fires


def _hit_before_irreversible(skill: SkillSpec, episode: Mapping[str, Any], fire_indices: Sequence[int]) -> bool:
    events = list(episode.get("recovery") or [])
    if skill.hook == "after_pi0_query":
        return bool(fire_indices)
    irreversible = None
    for idx, row in enumerate(events):
        if str(row.get("kind") or "") == "trajectory" and _label_is_irreversible_open(
            str(row.get("label") or ""), row.get("gripper_hold_value")
        ):
            irreversible = idx
            break
    if not fire_indices:
        return False
    if irreversible is None:
        return True
    return min(fire_indices) <= irreversible


def evaluate_heldout_triggers(skill: SkillSpec, episodes: Sequence[Mapping[str, Any]]) -> TriggerMetrics:
    metrics = TriggerMetrics()
    for episode in episodes:
        success = bool((episode.get("meta") or episode).get("success"))
        fires = iter_fire_indices(skill, episode)
        ep_id = _episode_id(episode)
        if success:
            metrics.n_success += 1
            if fires and len(fires) > SUCCESS_MAX_FIRE_QUERIES:
                metrics.n_success_fire += 1
                metrics.success_fires.append(ep_id)
        else:
            metrics.n_fail += 1
            if fires and _hit_before_irreversible(skill, episode, fires):
                metrics.n_fail_hit += 1
                metrics.fail_hits.append(ep_id)
            elif fires:
                metrics.late_irreversible += 1
    return metrics


def compare_same_init(
    off_episodes: Sequence[Mapping[str, Any]],
    on_episodes: Sequence[Mapping[str, Any]],
) -> SameInitMetrics:
    def key(episode: Mapping[str, Any]) -> tuple[Any, Any, Any]:
        meta = episode.get("meta") or episode
        return meta.get("task_id_1based"), meta.get("episode_idx"), meta.get("seed")

    on_map = {key(item): item for item in on_episodes}
    metrics = SameInitMetrics()
    for off in off_episodes:
        matched = on_map.get(key(off))
        if matched is None:
            continue
        metrics.n_pairs += 1
        off_ok = bool((off.get("meta") or off).get("success"))
        on_ok = bool((matched.get("meta") or matched).get("success"))
        metrics.off_success += int(off_ok)
        metrics.on_success += int(on_ok)
        if on_ok and not off_ok:
            metrics.n_improved += 1
        if off_ok and not on_ok:
            metrics.n_regressed += 1
    return metrics


def trigger_thresholds_ok(metrics: TriggerMetrics) -> bool:
    if metrics.n_fail <= 0:
        return False
    if FAIL_RECALL_MIN > 0 and metrics.fail_recall < FAIL_RECALL_MIN:
        return False
    if metrics.success_fire_rate > SUCCESS_EPISODE_FIRE_MAX:
        return False
    return metrics.late_irreversible == 0


def admission_ok(
    heldout: TriggerMetrics | None,
    *,
    same_init_improved: bool,
    success_regressed: bool,
) -> bool:
    if heldout is None or not trigger_thresholds_ok(heldout):
        return False
    if success_regressed:
        return False
    return bool(same_init_improved)
