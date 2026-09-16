"""LIBERO-Pro goal-task grounding profiles for the scratch mining pack."""

from __future__ import annotations

import copy
import re
from fnmatch import fnmatchcase
from typing import Any, Mapping


ADAPTER_NAME = "libero_goal_task_grounding_profiles"

PROFILE_PRIMITIVES = {
    "plate_stove_cook_region_v1": "table_region_surface",
    "wine_bottle_bowl_inner_floor_v1": "container_region_surface",
    "wine_rack_top_region_v1": "table_region_surface",
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
    return None, ""


def normalize_grounding_profile_params(profile: str, params: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        raise ValueError(f"unknown LIBERO goal-task grounding profile: {profile_id}")
    out = copy.deepcopy(dict(params))
    slot, key = _hint_slot(out)
    if slot is not None:
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
    low = str(name or "").lower()
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


def _language(parsed: Any) -> str:
    return str(getattr(parsed, "language", "") or "").lower()


def _bddl_goal_surfaces(parsed: Any) -> list[str]:
    diagnostics = dict(getattr(parsed, "diagnostics", {}) or {})
    out: list[str] = []
    raw = diagnostics.get("goal_surfaces") or diagnostics.get("bddl_goal_surfaces") or []
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        out.extend(str(item) for item in raw if str(item or ""))
    for atom in diagnostics.get("goal_atoms") or diagnostics.get("bddl_goal_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred in {"on", "inside"} and len(args) >= 2:
            out.append(str(args[1]))
    return list(dict.fromkeys(out))


def _region_name(parsed: Any, hint: Mapping[str, Any]) -> str:
    fixed = str(hint.get("region_name") or "").strip()
    if fixed:
        return fixed
    patterns = hint.get("bddl_goal_surface_matches") or hint.get("region_name_matches")
    for surface in _bddl_goal_surfaces(parsed):
        if patterns and not (_matches_any(surface, patterns) or _regex_matches_any(surface, patterns)):
            continue
        if "stove" in surface.lower() and "cook_region" in surface.lower():
            return surface
        if ("wine_rack" in surface.lower() or "rack" in surface.lower()) and "top_region" in surface.lower():
            return surface
    return ""


def _proxy_name(surface: str, hint: Mapping[str, Any]) -> str:
    suffix = str(hint.get("proxy_suffix") or "inner_floor").strip("_") or "inner_floor"
    if str(surface or "").endswith(f"_{suffix}"):
        return str(surface)
    return f"{surface}_{suffix}"


def _is_wine_bottle_bowl_profile(profile_id: str) -> bool:
    return str(profile_id or "").strip() == "wine_bottle_bowl_inner_floor_v1"


def _surface_matches_container(surface: str, hint: Mapping[str, Any]) -> bool:
    patterns = hint.get("container_name_matches") or hint.get("rewrite_misgrounded_goals") or []
    if patterns and _matches_any(surface, patterns):
        return True
    low = str(surface or "").lower()
    return "bowl" in low or "akita_black_bowl" in low


def _task_matches(profile_id: str, parsed: Any, target: str | None, obj: str, hint: Mapping[str, Any]) -> bool:
    language = _language(parsed)
    language_patterns = hint.get("task_language_matches")
    if language_patterns and not _regex_matches_any(language, language_patterns):
        return False
    target_patterns = hint.get("target_name_matches") or hint.get("object_name_matches")
    if target_patterns and not (_matches_any(obj, target_patterns) or _matches_any(str(target or ""), target_patterns)):
        return False
    if target is not None and obj != target:
        return False
    if profile_id == "plate_stove_cook_region_v1":
        return "plate" in obj.lower() or "plate" in str(target or "").lower() or "plate" in language
    if _is_wine_bottle_bowl_profile(profile_id):
        surfaces = " ".join(_bddl_goal_surfaces(parsed)).lower()
        return (
            "wine_bottle" in obj.lower()
            and ("bowl" in language or "bowl" in surfaces)
            and (" in " in f" {language} " or "inside" in language)
        )
    if profile_id == "wine_rack_top_region_v1":
        surfaces = " ".join(_bddl_goal_surfaces(parsed)).lower()
        hint_region = str(hint.get("region_name") or "").lower()
        return "rack" in language or "rack" in surfaces or "rack" in hint_region
    return False


def rewrite_placement_atom(
    profile: str,
    *,
    atom: Any,
    scene: Any,
    parsed: Any,
    target: str | None,
    hint_key: str,
    hint: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    del scene, hint_key
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        return None
    args = tuple(getattr(atom, "args", ()) or ())
    predicate = str(getattr(atom, "predicate", "")).lower()
    if predicate not in {"on", "inside"} or len(args) != 2:
        return None
    obj, surface = str(args[0]), str(args[1])
    if not _task_matches(profile_id, parsed, target, obj, hint):
        return None
    if _is_wine_bottle_bowl_profile(profile_id):
        if not _surface_matches_container(surface, hint):
            return None
        proxy = _proxy_name(surface, hint)
        return {
            "predicate": "on",
            "object": obj,
            "surface": proxy,
            "grounding": {
                "source": "libero_goal_task_grounding_profile",
                "grounding_profile": profile_id,
                "intent": str(hint.get("intent") or "container_inside"),
                "relation": "inside",
                "from": surface,
                "to": proxy,
                "semantic_predicate": predicate,
                "compiled_predicate": "on",
            },
        }
    if predicate != "on":
        return None
    region = _region_name(parsed, hint)
    if not region:
        return None
    rewrite_patterns = hint.get("rewrite_misgrounded_goals") or []
    if surface != region and not _matches_any(surface, rewrite_patterns):
        return None
    return {
        "predicate": "on",
        "object": obj,
        "surface": region,
        "grounding": {
            "source": "libero_goal_task_grounding_profile",
            "grounding_profile": profile_id,
            "intent": str(hint.get("intent") or "fixed_table_region"),
            "relation": "on",
            "from": surface,
            "to": region,
            "semantic_predicate": str(getattr(atom, "predicate", "")),
            "compiled_predicate": "on",
        },
    }


def is_known_or_virtual_surface(
    profile: str,
    *,
    surface: str,
    scene: Any,
    parsed: Any,
    hint_key: str,
    hint: Mapping[str, Any],
) -> bool | None:
    del scene, hint_key
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        return None
    if _is_wine_bottle_bowl_profile(profile_id):
        for source in _bddl_goal_surfaces(parsed):
            if _surface_matches_container(source, hint) and str(surface or "") == _proxy_name(source, hint):
                return True
        return False
    return str(surface or "") == _region_name(parsed, hint)
