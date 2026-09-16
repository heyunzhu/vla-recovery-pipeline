"""LIBERO-90 legacy grounding-profile adapter.

The core goal compiler consumes a small set of generic grounding primitives.
This adapter keeps LIBERO-90 profile names responsible for mapping benchmark
specific target-binding policies onto those primitives.
"""

from __future__ import annotations

import copy
import re
from fnmatch import fnmatchcase
from typing import Any, Mapping


ADAPTER_NAME = "libero90_legacy_grounding_profiles"

PROFILE_PRIMITIVES = {
    "plate_side_table_region_v1": "table_region_surface",
    "desk_caddy_side_table_region_v1": "table_region_surface",
    "task35_mug_front_region_v1": "table_region_surface",
    "task38_plate_right_region_v1": "table_region_surface",
    "desk_caddy_compartment_v1": "container_region_surface",
    "shelf_support_v1": "preferred_support_surface",
    "top_drawer_container_v1": "preferred_container_surface",
    "cabinet_top_support_v1": "preferred_support_surface",
    "bowl_stack_support_v1": "movable_support_surface",
}

PROFILE_IDS = frozenset(PROFILE_PRIMITIVES)


def _hint_slot(params: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    hints = params.get("grounding_hints")
    if not isinstance(hints, Mapping):
        return None, ""
    hints = copy.deepcopy(dict(hints))
    params["grounding_hints"] = hints
    placement = hints.get("placement_surface")
    if isinstance(placement, Mapping):
        placement = copy.deepcopy(dict(placement))
        hints["placement_surface"] = placement
        return placement, "placement_surface"
    support = hints.get("support_object")
    if isinstance(support, Mapping):
        support = copy.deepcopy(dict(support))
        hints["support_object"] = support
        return support, "support_object"
    return None, ""


def normalize_grounding_profile_params(profile: str, params: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        raise ValueError(f"unknown LIBERO-90 grounding profile: {profile_id}")
    out = copy.deepcopy(dict(params))
    slot, key = _hint_slot(out)
    if slot is None:
        return out
    slot.setdefault("planner_primitive", PROFILE_PRIMITIVES[profile_id])
    slot.setdefault("grounding_profile", profile_id)
    slot.setdefault("grounding_profile_adapter", ADAPTER_NAME)
    slot.setdefault("grounding_hint_key", key)
    return out


def _matches_any(name: str, patterns: Any) -> bool:
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list):
        return False
    low = name.lower()
    return any(fnmatchcase(low, str(pattern).lower()) for pattern in patterns)


def _regex_matches_any(text: str, patterns: Any) -> bool:
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list):
        return False
    value = str(text or "")
    for pattern in patterns:
        try:
            if re.search(str(pattern), value, flags=re.I):
                return True
        except re.error:
            continue
    return False


def _matches_name_or_regex(name: str, patterns: Any) -> bool:
    return _matches_any(name, patterns) or _regex_matches_any(name, patterns)


def _language(parsed: Any) -> str:
    return str(getattr(parsed, "language", "") or "").lower()


def _scene_names(scene: Any) -> list[str]:
    objects = getattr(scene, "objects", {}) or {}
    return sorted(str(name) for name in objects)


def _bddl_goal_surface_names(parsed: Any) -> list[str]:
    diagnostics = dict(getattr(parsed, "diagnostics", {}) or {})
    surfaces: list[str] = []
    raw_surfaces = diagnostics.get("goal_surfaces") or diagnostics.get("bddl_goal_surfaces") or []
    if isinstance(raw_surfaces, str):
        raw_surfaces = [raw_surfaces]
    if isinstance(raw_surfaces, list):
        surfaces.extend(str(surface) for surface in raw_surfaces if str(surface or ""))
    for atom in diagnostics.get("goal_atoms") or diagnostics.get("bddl_goal_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred in {"on", "inside"} and len(args) >= 2:
            surfaces.append(str(args[1]))
    return list(dict.fromkeys(surfaces))


def _fixed_table_region_name(region_name: str, parsed: Any, hint: Mapping[str, Any]) -> str:
    fixed = str(hint.get("region_name") or "").strip()
    if fixed:
        return fixed
    if not (hint.get("region_name_from_bddl_goal") or hint.get("bounds_from_bddl_region")):
        return ""
    patterns = hint.get("bddl_goal_surface_matches") or hint.get("region_name_matches") or hint.get("source_region_matches")
    candidates = [str(region_name or ""), *_bddl_goal_surface_names(parsed)]
    for candidate in candidates:
        if not candidate:
            continue
        if patterns and not _matches_name_or_regex(candidate, patterns):
            continue
        return candidate
    return ""


def _compartment_from_region_name(region_name: str, hint: Mapping[str, Any] | None = None) -> str:
    if isinstance(hint, Mapping):
        raw = str(hint.get("compartment") or "").strip().lower()
        if raw:
            return raw
    low = str(region_name or "").lower()
    for token in ("front", "back", "left", "right", "middle", "center"):
        if f"_{token}_" in low or low.endswith(f"_{token}"):
            return token
    return ""


def resolve_goal_surface(
    profile: str,
    *,
    scene: Any,
    parsed: Any,
    target: str | None,
    goal: str | None,
    hint: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Resolve LIBERO-90 support/container aliases for named grounding profiles."""
    profile_id = str(profile or "").strip()
    primitive = PROFILE_PRIMITIVES.get(profile_id, "")
    if goal is None or goal not in getattr(scene, "objects", {}):
        return None
    if primitive not in {"preferred_support_surface", "preferred_container_surface", "container_region_surface"}:
        return None
    intent = str(hint.get("intent") or "").lower()
    object_class = str(hint.get("object_class") or "").lower()
    relation = str(hint.get("relation") or "").lower()
    language = _language(parsed)
    goal_low = goal.lower()
    if object_class and object_class not in goal_low and object_class not in language:
        return None
    if primitive == "preferred_support_surface" and intent == "top_support":
        if "top" not in language and "_top" not in goal_low and "top_side" not in goal_low:
            return None
    elif primitive == "preferred_support_surface" and intent == "shelf_support":
        if "shelf" not in language and "shelf" not in goal_low:
            return None
    else:
        if relation and relation != "inside":
            return None
        if "drawer" not in language and "inside" not in language and "in " not in language:
            return None
        drawer_level = str(hint.get("drawer_level") or "").lower()
        if drawer_level and drawer_level not in language and f"_{drawer_level}" not in goal_low:
            return None

    names = _scene_names(scene)
    avoid = {
        name
        for name in names
        if name != target and hint.get("avoid") and _matches_any(name, hint.get("avoid"))
    }
    for group in ("prefer", "fallback"):
        patterns = hint.get(group)
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, list):
            continue
        for pattern in patterns:
            matches = [
                name
                for name in names
                if name != target
                and name not in avoid
                and _matches_any(name, [pattern])
                and (not object_class or object_class in name.lower())
            ]
            if not matches:
                continue
            resolved = matches[0]
            if resolved == goal:
                return {"surface": goal, "grounding": {}}
            return {
                "surface": resolved,
                "grounding": {
                    "source": "skill_grounding_profile_adapter",
                    "grounding_profile": profile_id,
                    "intent": intent,
                    "object_class": object_class,
                    "relation": relation,
                    "from": goal,
                    "to": resolved,
                    "pattern": str(pattern),
                },
            }
    return None


def rewrite_fixed_table_region_atom(
    profile: str,
    *,
    atom: Any,
    parsed: Any,
    target: str | None,
    region_name: str,
    hint: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Rewrite LIBERO-90 side-region aliases to explicit virtual table regions."""
    profile_id = str(profile or "").strip()
    if PROFILE_PRIMITIVES.get(profile_id) != "table_region_surface":
        return None
    region = _fixed_table_region_name(region_name, parsed, hint)
    if not region:
        return None
    args = tuple(getattr(atom, "args", ()) or ())
    if len(args) != 2:
        return None
    obj, surface = str(args[0]), str(args[1])
    language_patterns = hint.get("task_language_matches")
    if language_patterns and not _regex_matches_any(getattr(parsed, "language", ""), language_patterns):
        return None
    target_patterns = hint.get("target_name_matches") or hint.get("object_name_matches")
    if target_patterns and not (_matches_any(obj, target_patterns) or _matches_any(str(target or ""), target_patterns)):
        return None
    if target is not None and obj != target:
        target_patterns = target_patterns or hint.get("allow_non_target_object_name_matches")
        if not target_patterns or not _matches_any(obj, target_patterns):
            return None
    rewrite_patterns = hint.get("rewrite_misgrounded_goals") or hint.get("source_surface_matches")
    surface_is_region = surface == region
    if not surface_is_region and rewrite_patterns and not _matches_any(surface, rewrite_patterns):
        return None
    if not surface_is_region and not rewrite_patterns:
        return None
    return {
        "predicate": "on",
        "object": obj,
        "surface": region,
        "grounding": {
            "source": "skill_grounding_profile_adapter",
            "grounding_profile": profile_id,
            "intent": str(hint.get("intent") or "fixed_table_region"),
            "relation": str(hint.get("relation") or "on"),
            "from": surface,
            "to": region,
            "semantic_predicate": str(getattr(atom, "predicate", "")),
            "compiled_predicate": "on",
        },
    }


def resolve_container_region_source(
    profile: str,
    *,
    region_name: str,
    scene: Any,
    hint: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Resolve LIBERO-90 virtual contain-region names to their live container body."""
    profile_id = str(profile or "").strip()
    if PROFILE_PRIMITIVES.get(profile_id) != "container_region_surface":
        return None
    region = str(region_name or "")
    patterns = hint.get("region_name_matches") or hint.get("source_region_matches")
    if patterns and not _matches_any(region, patterns):
        return None
    objects = getattr(scene, "objects", {}) or {}
    if region in objects:
        return {"source": region, "compartment": _compartment_from_region_name(region, hint)}
    compartment = _compartment_from_region_name(region, hint)
    for suffix in ("_contain_region", "_container_region", "_inside_region"):
        if not region.endswith(suffix):
            continue
        base = region[: -len(suffix)]
        candidates = [f"{base}_main", base]
        if compartment and base.endswith(f"_{compartment}"):
            container = base[: -(len(compartment) + 1)]
            candidates.extend([f"{container}_main", container])
        for candidate in candidates:
            if candidate in objects:
                return {
                    "source": candidate,
                    "compartment": compartment,
                    "from": region,
                    "grounding_profile": profile_id,
                }
    return None


def allow_movable_support_surface(
    profile: str,
    *,
    surface: str,
    atom: Any,
    scene: Any,
    parsed: Any,
    target: str | None,
    hint: Mapping[str, Any],
) -> bool | None:
    """Decide whether a movable object may be registered as a support surface."""
    del scene
    profile_id = str(profile or "").strip()
    if PROFILE_PRIMITIVES.get(profile_id) != "movable_support_surface":
        return None
    if surface == target or str(getattr(atom, "predicate", "")).lower() != "on":
        return False
    patterns = hint.get("support_name_matches") or hint.get("name_matches")
    if patterns and not _matches_any(surface, patterns):
        return False
    object_class = str(hint.get("object_class") or hint.get("support_object_class") or "").lower()
    language = _language(parsed)
    if object_class and object_class not in surface.lower() and object_class not in language:
        return False
    return True
