"""LIBERO-90 legacy geometry-profile adapter.

The core planner consumes a few generic geometry primitives. This adapter keeps
the LIBERO-90 profile catalog responsible for mapping benchmark-specific
profile names onto those primitives.
"""

from __future__ import annotations

import copy
import re
from fnmatch import fnmatchcase
from typing import Any, Mapping, Optional, Sequence

import numpy as np


ADAPTER_NAME = "libero90_legacy_geometry_profiles"

PROFILE_PRIMITIVES = {
    "plate_side_region_geometry_v1": "fixed_table_rect",
    "desk_caddy_side_region_geometry_v1": "fixed_table_rect",
    "task35_mug_front_region_geometry_v1": "fixed_table_rect",
    "task38_plate_right_region_geometry_v1": "fixed_table_rect",
    "desk_caddy_compartment_inner_floor_v1": "inner_floor",
    "top_drawer_inner_floor_geometry_v1": "inner_floor",
    "shelf_region_inner_floor_geometry_v1": "inner_floor",
    "container_inside_region_geometry_v1": "inner_floor",
    "bowl_stack_support_geometry_v1": "movable_support_surface",
}

PROFILE_IDS = frozenset(PROFILE_PRIMITIVES)


_DESK_CADDY_COMPARTMENT_SITE_SUFFIXES = {
    "front": "front_contain_region",
    "back": "back_contain_region",
    "left": "left_contain_region",
    "right": "right_contain_region",
}

_DESK_CADDY_COMPARTMENT_BOUNDS_FRACTION = {
    "front": {"x_min": 0.10, "x_max": 0.90, "y_min": 0.04, "y_max": 0.42},
    "back": {"x_min": 0.10, "x_max": 0.90, "y_min": 0.58, "y_max": 0.96},
    "left": {"x_min": 0.04, "x_max": 0.45, "y_min": 0.10, "y_max": 0.90},
    "right": {"x_min": 0.55, "x_max": 0.96, "y_min": 0.10, "y_max": 0.90},
}

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
    movable = hints.get("movable_support_surface")
    if isinstance(movable, Mapping):
        movable = copy.deepcopy(dict(movable))
        hints["movable_support_surface"] = movable
        return movable, "movable_support_surface"
    return None, ""


def normalize_geometry_profile_params(profile: str, params: Mapping[str, Any]) -> dict[str, Any]:
    profile_id = str(profile or "").strip()
    if profile_id not in PROFILE_PRIMITIVES:
        raise ValueError(f"unknown LIBERO-90 geometry profile: {profile_id}")
    out = copy.deepcopy(dict(params))
    slot, key = _hint_slot(out)
    if slot is None:
        return out
    slot.setdefault("planner_primitive", PROFILE_PRIMITIVES[profile_id])
    slot.setdefault("geometry_profile", profile_id)
    slot.setdefault("geometry_profile_adapter", ADAPTER_NAME)
    slot.setdefault("geometry_hint_key", key)
    return out


def _float_hint(mapping: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(mapping.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _clamped_float_hint(mapping: Mapping[str, Any], key: str, default: float, lo: float, hi: float) -> float:
    value = _float_hint(mapping, key, default)
    return float(max(lo, min(hi, value)))


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


def _bddl_regions(task: Any) -> dict[str, Any]:
    regions = (getattr(task, "diagnostics", {}) or {}).get("bddl_regions") or {}
    return dict(regions) if isinstance(regions, Mapping) else {}


def _bddl_region_entry(task: Any, region_name: str) -> dict[str, Any]:
    regions = _bddl_regions(task)
    entry = regions.get(region_name)
    if isinstance(entry, Mapping):
        return dict(entry)
    suffix = region_name.split("_", 1)[-1] if "_" in region_name else region_name
    entry = regions.get(suffix)
    return dict(entry) if isinstance(entry, Mapping) else {}


def _bddl_region_xy_bounds(entry: Mapping[str, Any]) -> dict[str, float]:
    values: list[float] = []
    for item in entry.get("ranges") or []:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            pass
    if len(values) < 4:
        return {}
    x1, y1, x2, y2 = values[:4]
    return {
        "x_min": float(min(x1, x2)),
        "x_max": float(max(x1, x2)),
        "y_min": float(min(y1, y2)),
        "y_max": float(max(y1, y2)),
    }


def _bddl_region_center_xy(entry: Mapping[str, Any]) -> Optional[np.ndarray]:
    bounds = _bddl_region_xy_bounds(entry)
    if not bounds:
        return None
    return np.asarray(
        [
            0.5 * (bounds["x_min"] + bounds["x_max"]),
            0.5 * (bounds["y_min"] + bounds["y_max"]),
        ],
        dtype=np.float64,
    )


def _bddl_region_xy_offset(scene: Any, task: Any, target_region_entry: Mapping[str, Any]) -> np.ndarray:
    objects = getattr(scene, "objects", {}) or {}
    target_hint = str(getattr(task, "target_hint", "") or "")
    target_surface = str(target_region_entry.get("target") or "")
    offsets: list[np.ndarray] = []
    for atom in (getattr(task, "diagnostics", {}) or {}).get("bddl_init_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred not in {"on", "inside"} or len(args) < 2:
            continue
        if target_hint and str(args[0]) == target_hint:
            continue
        obj = objects.get(str(args[0]))
        if obj is None or getattr(obj, "pos", None) is None:
            continue
        entry = _bddl_region_entry(task, str(args[1]))
        if not entry:
            continue
        if target_surface and str(entry.get("target") or "") != target_surface:
            continue
        center = _bddl_region_center_xy(entry)
        if center is None:
            continue
        offsets.append(np.asarray(obj.pos[:2], dtype=np.float64) - center)
    if not offsets:
        return np.zeros(2, dtype=np.float64)
    return np.median(np.stack(offsets, axis=0), axis=0)


def _bddl_goal_surface_names(task: Any) -> list[str]:
    diagnostics = dict(getattr(task, "diagnostics", {}) or {})
    surfaces: list[str] = []
    raw_surfaces = diagnostics.get("bddl_goal_surfaces") or []
    if isinstance(raw_surfaces, str):
        raw_surfaces = [raw_surfaces]
    if isinstance(raw_surfaces, list):
        surfaces.extend(str(surface) for surface in raw_surfaces if str(surface or ""))
    for atom in diagnostics.get("bddl_goal_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred in {"on", "inside"} and len(args) >= 2:
            surfaces.append(str(args[1]))
    return list(dict.fromkeys(surfaces))


def _fixed_table_region_candidate(region_name: str, task: Any, hint: Mapping[str, Any]) -> str:
    fixed = str(hint.get("region_name") or "").strip()
    if fixed:
        return fixed if region_name == fixed else ""
    if not (hint.get("region_name_from_bddl_goal") or hint.get("bounds_from_bddl_region")):
        return ""
    if region_name not in _bddl_goal_surface_names(task):
        return ""
    patterns = hint.get("bddl_goal_surface_matches") or hint.get("region_name_matches") or hint.get("source_region_matches")
    if patterns and not _matches_name_or_regex(region_name, patterns):
        return ""
    return region_name


def _bddl_table_rect_bounds(
    region_name: str,
    hint: Mapping[str, Any],
    scene: Any,
    task: Any,
) -> tuple[dict[str, float], dict[str, Any]]:
    if not hint.get("bounds_from_bddl_region"):
        return {}, {}
    entry = _bddl_region_entry(task, region_name)
    bounds = _bddl_region_xy_bounds(entry)
    if not bounds:
        return {}, {}
    if bool(hint.get("align_bddl_regions_to_scene", True)):
        offset = _bddl_region_xy_offset(scene, task, entry)
        bounds = {
            "x_min": float(bounds["x_min"] + offset[0]),
            "x_max": float(bounds["x_max"] + offset[0]),
            "y_min": float(bounds["y_min"] + offset[1]),
            "y_max": float(bounds["y_max"] + offset[1]),
        }
    else:
        offset = np.zeros(2, dtype=np.float64)
    return bounds, {
        "source_bddl_region": entry.get("name") or region_name,
        "source_bddl_qualified_region": entry.get("qualified_name") or region_name,
        "source_bddl_target": entry.get("target") or "",
        "source_bddl_ranges": list(entry.get("ranges") or []),
        "bddl_scene_xy_offset": offset.astype(float).tolist(),
    }


def _crop_bounds_away_from_reference(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    hint: Mapping[str, Any],
    scene: Any,
    *,
    min_span: float,
) -> tuple[float, float, float, float, dict[str, Any]]:
    policy = str(hint.get("region_crop_policy") or hint.get("bounds_crop_policy") or "").strip().lower()
    if policy not in {"away_from_reference", "farthest_from_reference", "outer_from_reference"}:
        return x_min, x_max, y_min, y_max, {}
    ref_name = str(
        hint.get("region_crop_reference_object")
        or hint.get("bounds_crop_reference_object")
        or hint.get("place_candidate_reference_object")
        or ""
    ).strip()
    metadata: dict[str, Any] = {
        "region_crop_policy": policy,
        "region_crop_reference_object": ref_name,
        "region_crop_applied": False,
    }
    objects = getattr(scene, "objects", {}) or {}
    if not ref_name or ref_name not in objects:
        metadata["region_crop_skip_reason"] = "missing_reference_object"
        return x_min, x_max, y_min, y_max, metadata
    ref_xy = np.asarray(objects[ref_name].pos[:2], dtype=np.float64)
    center_xy = np.asarray([0.5 * (x_min + x_max), 0.5 * (y_min + y_max)], dtype=np.float64)
    delta = center_xy - ref_xy
    if float(np.linalg.norm(delta)) < 1e-6:
        metadata["region_crop_skip_reason"] = "reference_at_region_center"
        return x_min, x_max, y_min, y_max, metadata
    axis = 1 if abs(float(delta[1])) > abs(float(delta[0])) else 0
    keep_high = bool(delta[axis] >= 0.0)
    keep_fraction = _clamped_float_hint(hint, "region_crop_keep_fraction", 0.65, 0.25, 1.0)
    edge_margin = max(_float_hint(hint, "region_crop_edge_margin_m", 0.0), 0.0)
    original = {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max}

    if axis == 0:
        span = max(float(x_max - x_min), 1e-6)
        keep_span = min(span, max(span * keep_fraction, min_span))
        if keep_high:
            x_min = float(x_max - keep_span)
        else:
            x_max = float(x_min + keep_span)
    else:
        span = max(float(y_max - y_min), 1e-6)
        keep_span = min(span, max(span * keep_fraction, min_span))
        if keep_high:
            y_min = float(y_max - keep_span)
        else:
            y_max = float(y_min + keep_span)

    if (x_max - x_min) > 2.0 * edge_margin:
        x_min += edge_margin
        x_max -= edge_margin
    if (y_max - y_min) > 2.0 * edge_margin:
        y_min += edge_margin
        y_max -= edge_margin

    metadata.update(
        {
            "region_crop_applied": True,
            "region_crop_axis": "y" if axis == 1 else "x",
            "region_crop_keep_high": keep_high,
            "region_crop_keep_fraction": keep_fraction,
            "region_crop_edge_margin_m": edge_margin,
            "region_crop_reference_pos": ref_xy.astype(float).tolist(),
            "region_crop_original_bounds": original,
        }
    )
    return x_min, x_max, y_min, y_max, metadata


def _place_candidate_metadata(hint: Mapping[str, Any], scene: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in (
        "place_candidate_policy",
        "place_candidate_reference_object",
        "place_candidate_edge_margin_m",
        "place_candidate_max_count",
    ):
        if key in hint:
            metadata[key] = hint[key]
    ref_name = str(metadata.get("place_candidate_reference_object") or "")
    objects = getattr(scene, "objects", {}) or {}
    if ref_name and ref_name in objects:
        metadata["place_candidate_reference_pos"] = (
            np.asarray(objects[ref_name].pos, dtype=np.float64).reshape(-1)[:3].astype(float).tolist()
        )
    return metadata


def resolve_table_rect(
    profile: str,
    *,
    region_name: str,
    table_geometry: Mapping[str, Any],
    scene: Any,
    task: Any,
    hint: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Resolve LIBERO-90 table-region rectangles before the core builds a proxy surface."""
    del table_geometry
    profile_id = str(profile or "").strip()
    if PROFILE_PRIMITIVES.get(profile_id) != "fixed_table_rect":
        return None
    region = _fixed_table_region_candidate(str(region_name or ""), task, hint)
    if not region:
        return None
    bounds = dict(hint.get("bounds_m") or {}) if isinstance(hint.get("bounds_m"), Mapping) else {}
    bddl_bounds, bddl_metadata = _bddl_table_rect_bounds(region, hint, scene, task)
    if bddl_bounds:
        bounds = bddl_bounds
    if not all(key in bounds for key in ("x_min", "x_max", "y_min", "y_max")):
        return None
    x_min = _float_hint(bounds, "x_min", 0.0)
    x_max = _float_hint(bounds, "x_max", 0.0)
    y_min = _float_hint(bounds, "y_min", 0.0)
    y_max = _float_hint(bounds, "y_max", 0.0)
    min_span = _float_hint(hint, "min_span_m", 0.045)
    x_min, x_max, y_min, y_max, crop_metadata = _crop_bounds_away_from_reference(
        x_min,
        x_max,
        y_min,
        y_max,
        hint,
        scene,
        min_span=min_span,
    )
    return {
        "bounds": {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max},
        "metadata": {
            "fixed_table_rect_source": "libero90_geometry_profile_adapter",
            "geometry_profile": profile_id,
            "geometry_profile_adapter": ADAPTER_NAME,
            **bddl_metadata,
            **crop_metadata,
            **_place_candidate_metadata(hint, scene),
        },
    }


def _part_world_center_and_extents(part: Mapping[str, Any]) -> Optional[tuple[np.ndarray, np.ndarray]]:
    try:
        pos = np.asarray(part.get("pos", []), dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if pos.size < 3:
        return None
    try:
        quat = np.asarray(part.get("quat", [1.0, 0.0, 0.0, 0.0]), dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        quat = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    if quat.size < 4:
        quat = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    try:
        size = np.asarray(part.get("size", []), dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if size.size == 0:
        return None
    local_ext = np.zeros(3, dtype=np.float64)
    shape = str(part.get("shape", "box")).lower()
    if shape == "sphere":
        local_ext[:] = float(size[0])
    elif shape in {"capsule", "cylinder"}:
        radius = float(size[0])
        half_h = float(size[1] if size.size > 1 else size[0])
        local_ext[:] = [radius, radius, half_h]
    else:
        local_ext[: min(3, size.size)] = size[: min(3, size.size)]
    rotation = _quat_wxyz_to_matrix(quat[:4])
    world_ext = np.abs(rotation) @ np.maximum(local_ext, 1e-4)
    return pos[:3].astype(np.float64), world_ext


def _quat_wxyz_to_matrix(quat: Sequence[float]) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64).reshape(-1)
    if q.size < 4:
        return np.eye(3, dtype=np.float64)
    w, x, y, z = q[:4]
    norm = float(np.linalg.norm([w, x, y, z]))
    if norm < 1e-8:
        return np.eye(3, dtype=np.float64)
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _site_world_bounds(site: Mapping[str, Any]) -> Optional[dict[str, float]]:
    info = _part_world_center_and_extents(site)
    if info is None:
        return None
    pos, world_ext = info
    lower = pos - world_ext
    upper = pos + world_ext
    return {
        "x_min": float(lower[0]),
        "x_max": float(upper[0]),
        "y_min": float(lower[1]),
        "y_max": float(upper[1]),
        "z_min": float(lower[2]),
        "z_max": float(upper[2]),
        "support_z": float(lower[2]),
    }


def _shrink_xy_bounds(bounds: Mapping[str, Any], margin_m: float) -> dict[str, Any]:
    margin = max(0.0, float(margin_m))
    out = dict(bounds)
    x_min = float(out["x_min"]) + margin
    x_max = float(out["x_max"]) - margin
    y_min = float(out["y_min"]) + margin
    y_max = float(out["y_max"]) - margin
    if x_min < x_max:
        out["x_min"] = x_min
        out["x_max"] = x_max
    if y_min < y_max:
        out["y_min"] = y_min
        out["y_max"] = y_max
    return out


def _geometry_sites(raw_geometry: Mapping[str, Any]) -> list[dict[str, Any]]:
    sites = list(raw_geometry.get("sites", []) or [])
    metadata = raw_geometry.get("metadata", {}) if isinstance(raw_geometry.get("metadata"), Mapping) else {}
    if isinstance(metadata, Mapping):
        sites.extend(list(metadata.get("sites", []) or []))
        sites.extend(list(metadata.get("containment_sites", []) or []))
    out: list[dict[str, Any]] = []
    seen = set()
    for site in sites:
        if not isinstance(site, Mapping):
            continue
        item = dict(site)
        try:
            site_id = int(item.get("site_id", -1))
        except (TypeError, ValueError):
            site_id = -1
        key = (str(item.get("name") or ""), site_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _desk_caddy_site_bounds(
    source: Any,
    compartment: str,
    *,
    margin_m: float = 0.0,
) -> Optional[dict[str, Any]]:
    source_name = str(getattr(source, "name", "") or "")
    if "desk_caddy" not in source_name.lower():
        return None
    token = _DESK_CADDY_COMPARTMENT_SITE_SUFFIXES.get(str(compartment or "").strip().lower())
    if not token:
        return None
    raw_geometry = getattr(source, "geometry", {}) or {}
    if not isinstance(raw_geometry, Mapping):
        return None
    for site in _geometry_sites(raw_geometry):
        name = str(site.get("name") or "").lower()
        if token not in name:
            continue
        bounds = _site_world_bounds(site)
        if bounds is None:
            continue
        bounds = _shrink_xy_bounds(bounds, margin_m)
        bounds.update(
            {
                "source": "libero90_desk_caddy_site_bounds",
                "source_site_name": str(site.get("name") or token),
                "compartment": str(compartment or ""),
                "site_margin_m": float(max(0.0, margin_m)),
                "geometry_profile_adapter": ADAPTER_NAME,
            }
        )
        return bounds
    return None


def _center_and_half_extents(source: Any, source_geometry: Mapping[str, Any] | None) -> tuple[np.ndarray, np.ndarray]:
    center_raw = (source_geometry or {}).get("center")
    if center_raw is None:
        center_raw = getattr(source, "pos", [0.0, 0.0, 0.0])
    try:
        center = np.asarray(center_raw, dtype=np.float64).reshape(-1)[:3]
    except (TypeError, ValueError):
        center = np.zeros(3, dtype=np.float64)
    if center.size < 3:
        center = np.pad(center, (0, 3 - center.size))
    he_raw = (source_geometry or {}).get("half_extents")
    try:
        he = np.asarray(he_raw, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        he = np.zeros(0, dtype=np.float64)
    he3 = np.asarray([0.06, 0.06, 0.03], dtype=np.float64)
    if he.size:
        he3[: min(3, he.size)] = np.maximum(he[: min(3, he.size)], 1e-4)
    return center.astype(np.float64), he3


def _apply_normalized_xy_crop(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    fraction: Mapping[str, Any],
) -> tuple[float, float, float, float]:
    span_x = max(float(x_max - x_min), 1e-6)
    span_y = max(float(y_max - y_min), 1e-6)
    fx_min = float(fraction.get("x_min", 0.0))
    fx_max = float(fraction.get("x_max", 1.0))
    fy_min = float(fraction.get("y_min", 0.0))
    fy_max = float(fraction.get("y_max", 1.0))
    fx_min, fx_max = sorted((max(0.0, min(1.0, fx_min)), max(0.0, min(1.0, fx_max))))
    fy_min, fy_max = sorted((max(0.0, min(1.0, fy_min)), max(0.0, min(1.0, fy_max))))
    return (
        float(x_min + span_x * fx_min),
        float(x_min + span_x * fx_max),
        float(y_min + span_y * fy_min),
        float(y_min + span_y * fy_max),
    )


def _desk_caddy_fallback_bounds(
    source: Any,
    source_geometry: Mapping[str, Any] | None,
    compartment: str,
    hint: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    source_name = str(getattr(source, "name", "") or "")
    if "desk_caddy" not in source_name.lower():
        return None
    fraction = hint.get("compartment_bounds_fraction") or hint.get("bounds_fraction")
    if not isinstance(fraction, Mapping):
        fraction = _DESK_CADDY_COMPARTMENT_BOUNDS_FRACTION.get(str(compartment or "").strip().lower())
    if not isinstance(fraction, Mapping):
        return None
    center, he3 = _center_and_half_extents(source, source_geometry)
    metadata = (source_geometry or {}).get("metadata", {}) if isinstance((source_geometry or {}).get("metadata"), Mapping) else {}
    inner = metadata.get("inner_bounds") if isinstance(metadata, Mapping) else None
    margin = _float_hint(hint, "margin_m", 0.025)
    if isinstance(inner, Mapping) and inner:
        x_min = float(inner.get("x_min", center[0] - he3[0])) + margin
        x_max = float(inner.get("x_max", center[0] + he3[0])) - margin
        y_min = float(inner.get("y_min", center[1] - he3[1])) + margin
        y_max = float(inner.get("y_max", center[1] + he3[1])) - margin
        support_z = float(inner.get("support_z", inner.get("z_min", center[2] - he3[2])))
    else:
        x_min = float(center[0] - he3[0] + margin)
        x_max = float(center[0] + he3[0] - margin)
        y_min = float(center[1] - he3[1] + margin)
        y_max = float(center[1] + he3[1] - margin)
        support_z = float(center[2] - he3[2])
    x_min, x_max, y_min, y_max = _apply_normalized_xy_crop(x_min, x_max, y_min, y_max, fraction)
    return {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "support_z": support_z,
        "source": "libero90_desk_caddy_aabb_crop",
        "compartment": str(compartment or ""),
        "bounds_fraction": dict(fraction),
        "margin_m": float(max(0.0, margin)),
        "geometry_profile_adapter": ADAPTER_NAME,
    }


def resolve_inner_floor_bounds(
    profile: str,
    *,
    source: Any,
    scene: Any,
    hint: Mapping[str, Any],
    proxy_name: str,
    compartment: str,
    source_geometry: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    del scene, proxy_name
    if str(profile or "").strip() != "desk_caddy_compartment_inner_floor_v1":
        return None
    source_name = str(getattr(source, "name", "") or "")
    if "desk_caddy" not in source_name.lower():
        return None
    compartment = str(compartment or "").strip().lower()
    if compartment not in _DESK_CADDY_COMPARTMENT_SITE_SUFFIXES:
        return None
    site_margin = _float_hint(hint, "site_margin_m", 0.0)
    site_bounds = _desk_caddy_site_bounds(source, compartment, margin_m=site_margin)
    if site_bounds is not None:
        site_bounds["geometry_profile"] = str(profile or "")
        return site_bounds
    fallback = _desk_caddy_fallback_bounds(source, source_geometry, compartment, hint)
    if fallback is not None:
        fallback["geometry_profile"] = str(profile or "")
    return fallback
