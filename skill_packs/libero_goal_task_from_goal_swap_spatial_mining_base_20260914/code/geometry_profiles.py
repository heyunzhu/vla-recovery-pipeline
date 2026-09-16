"""LIBERO-Pro goal-task geometry profiles for the scratch mining pack."""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping


ADAPTER_NAME = "libero_goal_task_geometry_profiles"

PROFILE_PRIMITIVES = {
    "stove_cook_region_surface_v1": "fixed_table_rect",
    "wine_bottle_bowl_inner_floor_v1": "inner_floor",
    "wine_rack_top_region_surface_v1": "fixed_table_rect",
}
PROFILE_IDS = frozenset(PROFILE_PRIMITIVES)


def _hint_slot(params: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    hints = params.get("geometry_hints")
    if not isinstance(hints, Mapping):
        return None, ""
    hints = copy.deepcopy(dict(hints))
    params["geometry_hints"] = hints
    placement = hints.get("placement_region")
    if isinstance(placement, Mapping):
        placement = copy.deepcopy(dict(placement))
        hints["placement_region"] = placement
        return placement, "placement_region"
    return None, ""


def normalize_geometry_profile_params(profile: str, params: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        raise ValueError(f"unknown LIBERO goal-task geometry profile: {profile_id}")
    out = copy.deepcopy(dict(params))
    slot, key = _hint_slot(out)
    if slot is not None:
        slot.setdefault("planner_primitive", PROFILE_PRIMITIVES[profile_id])
        slot.setdefault("geometry_profile", profile_id)
        slot.setdefault("geometry_profile_adapter", ADAPTER_NAME)
        slot.setdefault("geometry_hint_key", key)
    return out


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _seq(value: Any, default: Iterable[float], length: int = 3) -> list[float]:
    out: list[float] = []
    if isinstance(value, (list, tuple)):
        for item in value[:length]:
            out.append(_float(item, 0.0))
    defaults = list(default)
    while len(out) < length:
        out.append(float(defaults[len(out)] if len(defaults) > len(out) else 0.0))
    return out[:length]


def _geometry(obj: Any) -> Mapping[str, Any]:
    raw = getattr(obj, "geometry", {}) or {}
    return raw if isinstance(raw, Mapping) else {}


def _metadata(obj: Any) -> Mapping[str, Any]:
    raw = _geometry(obj).get("metadata") or {}
    return raw if isinstance(raw, Mapping) else {}


def _sites(obj: Any) -> list[Mapping[str, Any]]:
    meta = _metadata(obj)
    out: list[Mapping[str, Any]] = []
    for key in ("sites", "containment_sites"):
        values = meta.get(key) or []
        if isinstance(values, list):
            out.extend(item for item in values if isinstance(item, Mapping))
    return out


def _site_by_name(obj: Any, name: str) -> Mapping[str, Any] | None:
    wanted = str(name or "").lower()
    for site in _sites(obj):
        if str(site.get("name") or "").lower() == wanted:
            return site
    return None


def _find_source(scene: Any, hint: Mapping[str, Any], surface_name: str) -> Any | None:
    objects = getattr(scene, "objects", {}) or {}
    surface_low = str(surface_name or "").lower()
    preferred = [
        str(hint.get("source_object") or "").strip(),
    ]
    if "stove" in surface_low:
        preferred.extend(["flat_stove_1_main", "flat_stove_1_burner"])
    if "wine_rack" in surface_low or "rack" in surface_low:
        preferred.append("wine_rack_1_main")
    for name in preferred:
        if name and name in objects:
            return objects[name]
    for obj in objects.values():
        if _site_by_name(obj, surface_name) is not None:
            return obj
    for name, obj in objects.items():
        if "flat_stove" in str(name).lower():
            return obj
        if "wine_rack" in str(name).lower():
            return obj
    return None


def _source_top_z(obj: Any) -> float:
    geom = _geometry(obj)
    center = _seq(geom.get("center", getattr(obj, "pos", [0.0, 0.0, 0.0])), [0.0, 0.0, 0.0])
    half = _seq(geom.get("half_extents"), [0.095, 0.095, 0.023])
    top_z = center[2] + abs(half[2])
    for part in _metadata(obj).get("collision_parts") or []:
        if not isinstance(part, Mapping):
            continue
        pos = _seq(part.get("pos"), center)
        size = _seq(part.get("size"), [0.0, 0.0, 0.0])
        name = str(part.get("name") or "").lower()
        if "burner" in name or "stove" in name:
            top_z = max(top_z, pos[2] + abs(size[2]))
    return float(top_z)


def _surface_name(task: Any, hint: Mapping[str, Any]) -> str:
    fixed = str(hint.get("surface_name") or hint.get("region_name") or "").strip()
    if fixed:
        return fixed
    diagnostics = dict(getattr(task, "diagnostics", {}) or {})
    candidates: list[str] = []
    raw = diagnostics.get("goal_surfaces") or diagnostics.get("bddl_goal_surfaces") or []
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        candidates.extend(str(item) for item in raw if str(item or ""))
    for atom in diagnostics.get("goal_atoms") or diagnostics.get("bddl_goal_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        args = list(atom.get("args") or [])
        if len(args) >= 2:
            candidates.append(str(args[1]))
    for candidate in candidates:
        low = candidate.lower()
        if "stove" in low and "cook_region" in low:
            return candidate
        if ("wine_rack" in low or "rack" in low) and "top_region" in low:
            return candidate
    return ""


def resolve_surface_descriptor(
    profile: str,
    *,
    surface_name: str,
    scene: Any,
    task: Any,
    table_geometry: Mapping[str, Any],
    hint: Mapping[str, Any],
    hint_key: str,
) -> Mapping[str, Any] | None:
    del table_geometry, hint_key
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        return None
    expected = _surface_name(task, hint)
    if str(surface_name or "") != expected:
        return None
    source = _find_source(scene, hint, expected)
    if source is None:
        return None
    site = _site_by_name(source, str(hint.get("source_site_name") or expected))
    if site is None:
        site = _site_by_name(source, expected)
    default_size = [0.075, 0.075, 0.0025]
    if profile_id == "wine_rack_top_region_surface_v1":
        default_size = [0.100, 0.022, 0.0025]
    center = _seq(site.get("pos") if site is not None else None, getattr(source, "pos", [0.0, 0.0, 0.0]))
    size = _seq(site.get("size") if site is not None else None, default_size)
    margin = max(_float(hint.get("site_margin_m"), 0.006), 0.0)
    default_min_half = 0.024 if profile_id == "wine_rack_top_region_surface_v1" else 0.040
    half_x = max(abs(size[0]) - margin, _float(hint.get("min_half_extent_m"), default_min_half))
    half_y = max(abs(size[1]) - margin, _float(hint.get("min_half_extent_m"), default_min_half))
    thickness = max(_float(hint.get("thickness_m"), 0.010), 0.004)
    if profile_id == "wine_rack_top_region_surface_v1":
        support_z = float(center[2] + abs(size[2]) + _float(hint.get("top_clearance_m"), 0.003))
        kind = "virtual_wine_rack_top_region"
        source_tag = "libero_goal_task_wine_rack_top_region_site"
        default_place_z_offset = 0.095
    else:
        support_z = _source_top_z(source) + _float(hint.get("top_clearance_m"), 0.002)
        kind = "virtual_stove_cook_region"
        source_tag = "libero_goal_task_stove_cook_region_site"
        default_place_z_offset = 0.160
    proxy_center = [float(center[0]), float(center[1]), float(support_z - 0.5 * thickness)]
    bounds = {
        "x_min": float(center[0] - half_x),
        "x_max": float(center[0] + half_x),
        "y_min": float(center[1] - half_y),
        "y_max": float(center[1] + half_y),
        "z_min": float(support_z),
        "z_max": float(support_z + thickness),
        "support_z": float(support_z),
    }
    return {
        "shape": "box",
        "kind": kind,
        "center": proxy_center,
        "quat": list(site.get("quat") if site is not None and isinstance(site.get("quat"), list) else [1.0, 0.0, 0.0, 0.0]),
        "half_extents": [float(half_x), float(half_y), float(0.5 * thickness)],
        "height": float(thickness),
        "source": source_tag,
        "planner_primitive": "fixed_table_rect",
        "coordinate_frame": "planner_frame",
        "inner_bounds": bounds,
        "inner_bounds_coordinate_frame": "planner_frame",
        "metadata": {
            "category": "surface",
            "affordances": ["surface", "placement_region", "fixed_table_region"],
            "geometry_profile": profile_id,
            "geometry_profile_adapter": ADAPTER_NAME,
            "source_object": str(getattr(source, "name", "") or hint.get("source_object") or ""),
            "source_site_name": str(site.get("name") if site is not None else expected),
            "site_margin_m": float(margin),
            "exclude_source_collision": bool(hint.get("exclude_source_collision", False)),
            "place_z_offset_m": _float(hint.get("place_z_offset_m"), default_place_z_offset),
            "inner_bounds": bounds,
        },
    }
