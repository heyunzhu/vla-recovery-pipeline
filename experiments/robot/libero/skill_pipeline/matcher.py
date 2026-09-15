"""Evaluate declared skill predicates. Skills cannot contain Python."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Mapping, Sequence

from .predicate_registry import (
    PredicateRegistry,
    compare_values,
    diagnostic_signal_expected_value,
    diagnostic_signal_name,
    diagnostic_signal_value,
)
from .schema import SkillSpec, normalize_predicates

DEFAULT_STALL_WINDOW = 4
DEFAULT_STALL_MAX_DISP_M = 0.015


@dataclass(frozen=True)
class Match:
    skill: SkillSpec
    hook: str


def _as_xyz(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [float(value[0]), float(value[1]), float(value[2])]
    return None


def _predicate_registry_or_default(predicate_registry: PredicateRegistry | None) -> PredicateRegistry:
    return predicate_registry or PredicateRegistry.builtins()


def _diagnostic_signal_predicate(name: str, expected: Any, state: Mapping[str, Any]) -> bool:
    signal = diagnostic_signal_name(expected)
    if not signal:
        return False
    actual = diagnostic_signal_value(state, signal)
    if name == "diagnostic_signal_present":
        return actual is not None
    expected_value = diagnostic_signal_expected_value(expected)
    if name == "diagnostic_signal_is":
        return compare_values(actual, expected_value, "is")
    if name == "diagnostic_signal_gt":
        return compare_values(actual, expected_value, "gt")
    if name == "diagnostic_signal_gte":
        return compare_values(actual, expected_value, "gte")
    if name == "diagnostic_signal_lt":
        return compare_values(actual, expected_value, "lt")
    if name == "diagnostic_signal_lte":
        return compare_values(actual, expected_value, "lte")
    return False


def eval_predicate(
    name: str,
    expected: Any,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> bool:
    if str(name).startswith("diagnostic_signal_"):
        return _diagnostic_signal_predicate(name, expected, state)
    if name == "object_followed_lift":
        followed = state.get("object_followed")
        if followed is None:
            return False
        return bool(followed) is bool(expected)
    if name == "label_matches":
        return bool(re.search(str(expected), str(state.get("label") or ""), flags=re.I))
    if name == "aperture_gt":
        aperture = state.get("aperture")
        return aperture is not None and float(aperture) > float(expected)
    if name == "aperture_lt":
        aperture = state.get("aperture")
        return aperture is not None and float(aperture) < float(expected)
    if name == "gripper_cmd_gt":
        value = state.get("gripper_cmd")
        return value is not None and float(value) > float(expected)
    if name == "holding_status_is":
        return str(state.get("holding_status") or "") == str(expected)
    if name == "target_ee_distance_gt":
        value = state.get("target_ee_distance_m")
        return value is not None and float(value) > float(expected)
    if name == "target_ee_distance_lt":
        value = state.get("target_ee_distance_m")
        return value is not None and float(value) < float(expected)
    if name == "target_future_min_xy_distance_gt":
        value = state.get("target_future_min_xy_distance_m")
        return value is not None and float(value) > float(expected)
    if name == "target_future_min_xy_distance_lt":
        value = state.get("target_future_min_xy_distance_m")
        return value is not None and float(value) < float(expected)
    if name == "nearest_pickable_distance_lt":
        value = state.get("nearest_pickable_distance_m")
        return value is not None and float(value) < float(expected)
    if name == "nearest_pickable_distance_gt":
        value = state.get("nearest_pickable_distance_m")
        return value is not None and float(value) > float(expected)
    if name == "nearest_pickable_is_target":
        value = state.get("nearest_pickable_is_target")
        if value is None:
            return False
        return bool(value) is bool(expected)
    if name == "intent_object_is_target":
        value = state.get("intent_object_is_target")
        if value is None:
            return False
        return bool(value) is bool(expected)
    if name == "intent_min_xy_distance_lt":
        value = state.get("intent_min_xy_distance_m")
        return value is not None and float(value) < float(expected)
    if name == "wrong_object_intent_margin_gt":
        value = state.get("wrong_object_intent_margin_m")
        return value is not None and float(value) > float(expected)
    if name == "wrong_object_intent_persist_queries_gte":
        value = state.get("wrong_object_intent_persist_queries")
        return value is not None and int(value) >= int(expected)
    if name == "wrong_progress_object_total_motion_gt":
        value = state.get("wrong_progress_object_total_motion_m")
        return value is not None and float(value) > float(expected)
    if name == "wrong_progress_object_goal_xy_distance_lt":
        value = state.get("wrong_progress_object_goal_xy_distance_m")
        return value is not None and float(value) < float(expected)
    if name == "wrong_progress_object_is_intent":
        value = state.get("wrong_progress_object_is_intent")
        if value is None:
            return False
        return bool(value) is bool(expected)
    if name == "wrong_progress_object_is_held":
        value = state.get("wrong_progress_object_is_held")
        if value is None:
            return False
        return bool(value) is bool(expected)
    if name == "wrong_progress_target_static":
        value = state.get("wrong_progress_target_static")
        if value is None:
            return False
        return bool(value) is bool(expected)
    if name == "vla_wrong_object_progress_status_is":
        return str(state.get("vla_wrong_object_progress_status") or "") == str(expected)
    if name == "vla_pick_target_status_is":
        return str(state.get("vla_pick_target_status") or "") == str(expected)
    if name == "vla_articulated_blocker_status_is":
        return str(state.get("vla_articulated_blocker_status") or "") == str(expected)
    if name == "ee_stalled":
        window = DEFAULT_STALL_WINDOW
        max_disp = DEFAULT_STALL_MAX_DISP_M
        if isinstance(expected, Mapping):
            window = int(expected.get("window", window))
            max_disp = float(expected.get("max_disp_m", expected.get("max_disp", max_disp)))
        elif expected not in (True, None):
            max_disp = float(expected)
        history = [_as_xyz(item) for item in (state.get("ee_history") or [])]
        history = [item for item in history if item is not None]
        if len(history) < window:
            return False
        first = history[-window]
        last = history[-1]
        disp = math.sqrt(sum((last[i] - first[i]) ** 2 for i in range(3)))
        return disp <= max_disp
    registry = _predicate_registry_or_default(predicate_registry)
    if registry.is_trigger_predicate_allowed(name):
        return registry.evaluate_predicate(name, expected, state)
    raise KeyError(f"unknown predicate: {name}")


def _matches_text(value: Any, pattern: Any) -> bool:
    if isinstance(pattern, (list, tuple, set)):
        return any(_matches_text(value, item) for item in pattern)
    if isinstance(value, (list, tuple, set)):
        return any(_matches_text(item, pattern) for item in value)
    text = str(value or "")
    raw_pattern = str(pattern)
    try:
        if re.search(raw_pattern, text, flags=re.I):
            return True
    except re.error:
        pass
    return fnmatchcase(text.lower(), raw_pattern.lower())


def eval_applies_predicate(
    name: str,
    expected: Any,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> bool:
    if name == "task_language_matches":
        return _matches_text(state.get("task_description") or state.get("language"), expected)
    if name == "target_name_matches":
        return _matches_text(state.get("target_name") or state.get("target"), expected)
    if name == "target_name_excludes":
        return not _matches_text(state.get("target_name") or state.get("target"), expected)
    if name == "target_orientation_is":
        return str(state.get("target_orientation") or "") == str(expected)
    if name == "goal_name_matches":
        return _matches_text(state.get("goal_name") or state.get("goal"), expected)
    if name == "surface_name_matches":
        return _matches_text(state.get("surface_name") or state.get("surface"), expected)
    if name == "bddl_goal_surface_matches":
        return _matches_text(state.get("bddl_goal_surfaces") or state.get("bddl_goal_surface"), expected)
    registry = _predicate_registry_or_default(predicate_registry)
    if registry.is_applies_predicate_allowed(name):
        return registry.evaluate_applies_predicate(name, expected, state)
    raise KeyError(f"unknown applies_to predicate: {name}")


def _actual_value_for_predicate(name: str, state: Mapping[str, Any]) -> Any:
    mapping = {
        "object_followed_lift": "object_followed",
        "label_matches": "label",
        "aperture_gt": "aperture",
        "aperture_lt": "aperture",
        "gripper_cmd_gt": "gripper_cmd",
        "holding_status_is": "holding_status",
        "target_ee_distance_gt": "target_ee_distance_m",
        "target_ee_distance_lt": "target_ee_distance_m",
        "target_future_min_xy_distance_gt": "target_future_min_xy_distance_m",
        "target_future_min_xy_distance_lt": "target_future_min_xy_distance_m",
        "nearest_pickable_distance_lt": "nearest_pickable_distance_m",
        "nearest_pickable_distance_gt": "nearest_pickable_distance_m",
        "nearest_pickable_is_target": "nearest_pickable_is_target",
        "intent_object_is_target": "intent_object_is_target",
        "intent_min_xy_distance_lt": "intent_min_xy_distance_m",
        "wrong_object_intent_margin_gt": "wrong_object_intent_margin_m",
        "wrong_object_intent_persist_queries_gte": "wrong_object_intent_persist_queries",
        "wrong_progress_object_total_motion_gt": "wrong_progress_object_total_motion_m",
        "wrong_progress_object_goal_xy_distance_lt": "wrong_progress_object_goal_xy_distance_m",
        "wrong_progress_object_is_intent": "wrong_progress_object_is_intent",
        "wrong_progress_object_is_held": "wrong_progress_object_is_held",
        "wrong_progress_target_static": "wrong_progress_target_static",
        "vla_wrong_object_progress_status_is": "vla_wrong_object_progress_status",
        "vla_pick_target_status_is": "vla_pick_target_status",
        "vla_articulated_blocker_status_is": "vla_articulated_blocker_status",
    }
    if name == "ee_stalled":
        history = [_as_xyz(item) for item in (state.get("ee_history") or [])]
        history = [item for item in history if item is not None]
        if not history:
            return {"history_len": 0}
        window = DEFAULT_STALL_WINDOW
        if isinstance(state.get("ee_stalled"), Mapping):
            window = int(state["ee_stalled"].get("window", window))
        return {"history_len": len(history), "latest_xyz": history[-1]}
    if str(name).startswith("diagnostic_signal_"):
        signal = diagnostic_signal_name(state.get(name))
        if not signal:
            return {"signals": dict(state.get("diagnostic_signals", {}).get("values", {}))} if isinstance(state.get("diagnostic_signals"), Mapping) else {}
        return {"signal": signal, "value": diagnostic_signal_value(state, signal)}
    key = mapping.get(name)
    return state.get(key) if key else None


def _actual_value_for_applies_predicate(name: str, state: Mapping[str, Any]) -> Any:
    mapping = {
        "task_language_matches": "task_description",
        "target_name_matches": "target_name",
        "target_name_excludes": "target_name",
        "target_orientation_is": "target_orientation",
        "goal_name_matches": "goal_name",
        "surface_name_matches": "surface_name",
        "bddl_goal_surface_matches": "bddl_goal_surfaces",
    }
    key = mapping.get(name)
    if key == "task_description" and state.get("task_description") is None:
        return state.get("language")
    if key == "target_name" and state.get("target_name") is None:
        return state.get("target")
    if key == "goal_name" and state.get("goal_name") is None:
        return state.get("goal")
    if key == "surface_name" and state.get("surface_name") is None:
        return state.get("surface")
    if key == "bddl_goal_surfaces" and state.get("bddl_goal_surfaces") is None:
        return state.get("bddl_goal_surface")
    return state.get(key) if key else None


def _predicate_diagnostics(
    predicates: Sequence[tuple[str, Any]],
    state: Mapping[str, Any],
    *,
    applies_to: bool = False,
    predicate_registry: PredicateRegistry | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, expected in predicates:
        error = ""
        try:
            if applies_to:
                passed = bool(eval_applies_predicate(name, expected, state, predicate_registry=predicate_registry))
            else:
                passed = bool(eval_predicate(name, expected, state, predicate_registry=predicate_registry))
        except Exception as exc:  # pragma: no cover - schema validation normally prevents this.
            passed = False
            error = f"{type(exc).__name__}: {exc}"
        actual = None
        if applies_to:
            actual = _actual_value_for_applies_predicate(name, state)
            if actual is None and predicate_registry is not None:
                actual = predicate_registry.actual_value_for_applies_predicate(name, state)
        else:
            actual = _actual_value_for_predicate(name, {**dict(state), name: expected})
            if actual is None and predicate_registry is not None:
                actual = predicate_registry.actual_value_for_predicate(name, state)
        rows.append(
            {
                "predicate": name,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "error": error,
            }
        )
    return rows


def explain_trigger(
    trigger: Mapping[str, Any] | None,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> dict[str, Any]:
    trigger = dict(trigger or {})
    all_rows = _predicate_diagnostics(
        normalize_predicates(trigger.get("all")),
        state,
        predicate_registry=predicate_registry,
    )
    any_rows = _predicate_diagnostics(
        normalize_predicates(trigger.get("any")),
        state,
        predicate_registry=predicate_registry,
    )
    has_any = bool(all_rows or any_rows)
    all_passed = all(row["passed"] for row in all_rows)
    any_passed = True if not any_rows else any(row["passed"] for row in any_rows)
    return {
        "passed": bool(has_any and all_passed and any_passed),
        "all": all_rows,
        "any": any_rows,
        "failed_all": [row["predicate"] for row in all_rows if not row["passed"]],
        "failed_any": [] if any_passed else [row["predicate"] for row in any_rows],
    }


def explain_applies_to(
    applies_to: Mapping[str, Any] | None,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> dict[str, Any]:
    applies_to = dict(applies_to or {})
    all_rows = _predicate_diagnostics(
        normalize_predicates(applies_to.get("all")),
        state,
        applies_to=True,
        predicate_registry=predicate_registry,
    )
    any_rows = _predicate_diagnostics(
        normalize_predicates(applies_to.get("any")),
        state,
        applies_to=True,
        predicate_registry=predicate_registry,
    )
    has_any = bool(all_rows or any_rows)
    all_passed = all(row["passed"] for row in all_rows)
    any_passed = True if not any_rows else any(row["passed"] for row in any_rows)
    return {
        "passed": bool(has_any and all_passed and any_passed),
        "all": all_rows,
        "any": any_rows,
        "failed_all": [row["predicate"] for row in all_rows if not row["passed"]],
        "failed_any": [] if any_passed else [row["predicate"] for row in any_rows],
    }


def eval_trigger(
    trigger: Mapping[str, Any] | None,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> bool:
    trigger = dict(trigger or {})
    all_preds = normalize_predicates(trigger.get("all"))
    any_preds = normalize_predicates(trigger.get("any"))
    if not all_preds and not any_preds:
        return False
    if all_preds and not all(
        eval_predicate(name, value, state, predicate_registry=predicate_registry) for name, value in all_preds
    ):
        return False
    if any_preds and not any(
        eval_predicate(name, value, state, predicate_registry=predicate_registry) for name, value in any_preds
    ):
        return False
    return True


def eval_applies_to(
    applies_to: Mapping[str, Any] | None,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> bool:
    applies_to = dict(applies_to or {})
    all_preds = normalize_predicates(applies_to.get("all"))
    any_preds = normalize_predicates(applies_to.get("any"))
    if not all_preds and not any_preds:
        return False
    if all_preds and not all(
        eval_applies_predicate(name, value, state, predicate_registry=predicate_registry) for name, value in all_preds
    ):
        return False
    if any_preds and not any(
        eval_applies_predicate(name, value, state, predicate_registry=predicate_registry) for name, value in any_preds
    ):
        return False
    return True


def match_skills(
    skills: Sequence[SkillSpec],
    hook: str,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> Match | None:
    ranked = sorted(
        [skill for skill in skills if skill.kind not in {"diagnostics", "recovery_hint"} and skill.hook == hook],
        key=lambda skill: (-int(skill.priority), skill.id),
    )
    for skill in ranked:
        registry = predicate_registry or getattr(skill, "predicate_registry", None)
        if skill.applies_to and not eval_applies_to(skill.applies_to, state, predicate_registry=registry):
            continue
        if eval_trigger(skill.trigger, state, predicate_registry=registry):
            return Match(skill=skill, hook=hook)
    return None


def diagnose_skills(
    skills: Sequence[SkillSpec],
    hook: str,
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> list[dict[str, Any]]:
    ranked = sorted(
        [skill for skill in skills if skill.kind not in {"diagnostics", "recovery_hint"} and skill.hook == hook],
        key=lambda skill: (-int(skill.priority), skill.id),
    )
    rows: list[dict[str, Any]] = []
    for skill in ranked:
        registry = predicate_registry or getattr(skill, "predicate_registry", None)
        applies = (
            explain_applies_to(skill.applies_to, state, predicate_registry=registry)
            if skill.applies_to
            else {"passed": True}
        )
        trigger = explain_trigger(skill.trigger, state, predicate_registry=registry)
        rows.append(
            {
                "skill_id": skill.id,
                "priority": int(skill.priority),
                "applies_to": applies,
                "trigger": trigger,
                "would_fire": bool(applies.get("passed") and trigger.get("passed")),
            }
        )
    return rows


def match_recovery_hints(
    skills: Sequence[SkillSpec],
    state: Mapping[str, Any],
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> list[Match]:
    ranked = sorted(
        [skill for skill in skills if skill.kind == "recovery_hint"],
        key=lambda skill: (int(skill.priority), skill.id),
    )
    return [
        Match(skill=skill, hook="recovery_hint")
        for skill in ranked
        if eval_applies_to(
            skill.applies_to,
            state,
            predicate_registry=predicate_registry or getattr(skill, "predicate_registry", None),
        )
    ]
