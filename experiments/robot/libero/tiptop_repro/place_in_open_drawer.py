"""Place into a drawer that is already open.

The cavity is the live region site on the drawer link. A MuJoCo box site
stores its half extents in the site's *own* frame, so they must be rotated by
the site quaternion before they can be compared with anything in the planner
frame: LIBERO's cabinet region sites are rotated a quarter turn, and reading
``site_size`` as an axis-aligned box swaps the x and z half extents, which
moves the cavity floor ~7 cm below the drawer and its ceiling ~7 cm above the
rim. Every derived box is therefore reported in the diagnostics next to the
axis-aligned box of the drawer link's own collision geometry, and a gross
disagreement refuses the skill instead of feeding the planner an impossible
region.

The release height is the top of the tallest vertical gap at the site center.
The gripper occupies some vertical space below the grasped object's centre, so
that top must also leave the gripper above the boards. A tie uses the lower
gap. If the top is not high enough, this skill refuses.
This skill does not open the drawer. A closed joint, or a joint whose travel
is unknown, is a refusal.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .engine_capabilities import CENTER_ONLY_PLACE_CANDIDATE_POLICY
from .libero_panda_frames import quat_wxyz_to_matrix

DRAWER_REGION_SUFFIXES = ("_top_region", "_middle_region", "_bottom_region")
PROXY_SUFFIX = "_inner_floor"
OPEN_PROGRESS_MIN = 0.70
XY_INSET_M = 0.01
COLLISION_CLEARANCE_M = 0.001
RETREAT_CLEARANCE_M = 0.04
MIN_CAVITY_HEIGHT_M = 0.03
# MuJoCo's site type enum value for a box: the only shape whose ``site_size``
# is a usable half-extent triple.
MUJOCO_SITE_TYPE_BOX = 6
# The skill may be told how far the gripper reaches below the grasped object's
# centre; otherwise it is derived from the object instead of a fixed constant.
HAND_BELOW_OBJECT_HINT_KEY = "open_drawer_hand_below_object_m"
# A region site must lie inside the drawer link's own collision geometry. The
# observed frame bug put the site 7 cm outside it, so 2 cm separates the two
# without flagging legitimate sites that poke slightly past the rim.
GEOMETRY_MISMATCH_TOLERANCE_M = 0.02
# Angular resolution of the rotated-footprint fit check.
FOOTPRINT_FIT_SAMPLES = 721


def is_drawer_region_name(name: str) -> bool:
    low = str(name or "").lower()
    return any(low.endswith(suffix) for suffix in DRAWER_REGION_SUFFIXES)


def language_asks_drawer_inside(language: str) -> bool:
    words = [word.strip(".,;:!?()[]") for word in str(language or "").lower().replace("_", " ").split()]
    return "drawer" in words and any(word in words for word in ("in", "into", "inside"))


def _atom_pred_args(atom: Any) -> tuple[str, list[str]]:
    if isinstance(atom, Mapping):
        pred = str(atom.get("predicate") or "").lower()
        args = [str(arg) for arg in (atom.get("args") or [])]
    else:
        pred = str(getattr(atom, "predicate", "") or "").lower()
        args = [str(arg) for arg in (getattr(atom, "args", ()) or ())]
    if pred == "in":
        pred = "inside"
    return pred, args


def select_drawer_inside_goal(language: str, goal_atoms: Any) -> Optional[tuple[str, str]]:
    """Return (object, region) for an inside-drawer BDDL goal, else None."""
    if not language_asks_drawer_inside(language):
        return None
    for atom in goal_atoms or []:
        pred, args = _atom_pred_args(atom)
        if pred != "inside" or len(args) < 2:
            continue
        if is_drawer_region_name(args[1]):
            return args[0], args[1]
    return None


def proxy_name_for_region(region_name: str) -> str:
    return f"{region_name}{PROXY_SUFFIX}"


def region_from_surface_name(surface_name: str) -> Optional[str]:
    name = str(surface_name or "")
    if is_drawer_region_name(name):
        return name
    if name.endswith(PROXY_SUFFIX):
        region = name[: -len(PROXY_SUFFIX)]
        if is_drawer_region_name(region):
            return region
    return None


def _level_token(region_name: str) -> str:
    low = region_name.lower()
    for suffix in DRAWER_REGION_SUFFIXES:
        if low.endswith(suffix):
            return suffix[1 : -len("_region")]
    return ""


def _link_names(region_name: str) -> list[str]:
    if region_name.lower().endswith("_region"):
        return [region_name[: -len("region")] + "level"]
    return []


def find_region_site(scene: Any, region_name: str) -> Optional[dict[str, Any]]:
    level = _level_token(region_name)
    alias = f"{level}_region" if level else ""
    links = {name.lower() for name in _link_names(region_name)}
    ranked: list[tuple[int, dict[str, Any]]] = []
    for obj in getattr(scene, "objects", {}).values():
        geometry = getattr(obj, "geometry", None) or {}
        if not isinstance(geometry, dict):
            continue
        for site in geometry.get("sites") or []:
            if not isinstance(site, dict):
                continue
            site_name = str(site.get("name") or "")
            if site_name != region_name and site_name.lower() != alias:
                continue
            body = str(site.get("body_name") or getattr(obj, "name", "")).lower()
            if body in links or str(getattr(obj, "name", "")).lower() in links:
                rank = 2
            elif level and level in body:
                rank = 1
            else:
                rank = 0
            ranked.append((rank, site))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked[0][0] == 0 and len(ranked) > 1:
        return None
    return ranked[0][1]


def find_drawer_joint(scene: Any, region_name: str) -> Optional[dict[str, Any]]:
    links = {name.lower() for name in _link_names(region_name)}
    level = _level_token(region_name)
    structure = getattr(scene, "articulation_structure", {}) or {}
    joints = getattr(scene, "joints", {}) or {}
    chosen = None
    for entry in structure.values():
        if not isinstance(entry, dict):
            continue
        body = str(entry.get("body_name") or "").lower()
        joint_name = str(entry.get("joint_name") or "")
        if body in links or joint_name.lower() in links:
            chosen = entry
            break
        if level and level in body and ("cabinet" in body or "drawer" in body):
            chosen = entry
            break
    if chosen is None:
        for joint_name, joint in joints.items():
            low = str(joint_name).lower()
            if low in links or (level and level in low and ("cabinet" in low or "drawer" in low)):
                joint_range = getattr(joint, "joint_range", None)
                return {
                    "joint_name": str(joint_name),
                    "qpos": float(joint.qpos),
                    "joint_range": list(joint_range) if joint_range else None,
                    "body_name": "",
                }
        return None
    joint_name = str(chosen.get("joint_name") or "")
    joint = joints.get(joint_name)
    qpos = float(joint.qpos) if joint is not None else float(chosen.get("reference_position"))
    joint_range = chosen.get("joint_range")
    return {
        "joint_name": joint_name,
        "qpos": qpos,
        "joint_range": list(joint_range) if joint_range else None,
        "body_name": str(chosen.get("body_name") or ""),
    }


def drawer_open_progress(qpos: float, joint_range: Any) -> Optional[float]:
    """0 is the closed end of the travel, 1 is the open end. None if unknown."""
    if not joint_range or len(joint_range) < 2:
        return None
    lo = float(joint_range[0])
    hi = float(joint_range[1])
    q = float(qpos)
    if not np.isfinite([lo, hi, q]).all() or hi <= lo or q < lo - 1e-4 or q > hi + 1e-4:
        return None
    if lo <= 0.0 <= hi:
        closed = 0.0
        open_end = hi if abs(hi) >= abs(lo) else lo
    else:
        closed = lo if abs(lo) <= abs(hi) else hi
        open_end = hi if closed == lo else lo
    travel = open_end - closed
    if abs(travel) < 1e-6:
        return None
    return float((q - closed) / travel)


def _aabb_half_extents(size: Any, quat: Any) -> Optional[np.ndarray]:
    half = np.asarray(size if size is not None else [], dtype=float).reshape(-1)
    if half.size < 3 or not np.isfinite(half[:3]).all() or np.any(half[:3] <= 0.0):
        return None
    local = np.abs(half[:3])
    raw = np.asarray(quat if quat is not None else [], dtype=float).reshape(-1)
    if raw.size < 4 or not np.isfinite(raw[:4]).all() or float(np.linalg.norm(raw[:4])) < 1e-8:
        return local
    return np.abs(quat_wxyz_to_matrix(raw[:4])) @ local


def _site_local_half_extents(site: Mapping[str, Any]) -> Optional[np.ndarray]:
    """The site's half extents exactly as MuJoCo stores them (site frame)."""
    size = np.asarray(site.get("size") if site.get("size") is not None else [], dtype=float).reshape(-1)
    if size.size < 3 or not np.isfinite(size[:3]).all() or np.any(size[:3] <= 1e-4):
        return None
    return size[:3].astype(float)


def site_is_axis_aligned_box(site: Mapping[str, Any]) -> bool:
    """Whether the site's ``size`` is a usable half-extent triple.

    ``scene_reader`` always records the MuJoCo type and shape, so a real asset
    is judged strictly. A hand-built scene carries no type metadata, and
    "unknown" is not the same as "not a box", so it is accepted.
    """
    site_type = site.get("type")
    shape = str(site.get("shape") or "").strip().lower()
    if site_type is None and not shape:
        return _site_local_half_extents(site) is not None
    if site_type is not None:
        try:
            return int(site_type) == MUJOCO_SITE_TYPE_BOX
        except (TypeError, ValueError):
            return False
    return shape == "box"


def site_axis_aligned_half_extents(site: Mapping[str, Any]) -> Optional[np.ndarray]:
    """Half extents of the site's world-axis-aligned bounding box.

    ``site_size`` lives in the site's own frame, so the site quaternion has to
    be applied before the extents mean anything in the planner frame. Skipping
    that rotation swaps the x and z half extents for LIBERO's cabinet region
    sites, which is exactly the bug this function exists to prevent.
    """
    local = _site_local_half_extents(site)
    if local is None:
        return None
    return _aabb_half_extents(local, site.get("quat"))


def _aabb_of(points: Sequence[Any]) -> Optional[tuple[np.ndarray, np.ndarray]]:
    if not points:
        return None
    stack = np.stack([np.asarray(point, dtype=float).reshape(-1)[:3] for point in points], axis=0)
    if not np.isfinite(stack).all():
        return None
    return stack.min(axis=0), stack.max(axis=0)


def _box_from_center_half(center: np.ndarray, half: Optional[np.ndarray]) -> Optional[dict[str, Any]]:
    if half is None or center.size < 3:
        return None
    lo = center[:3] - half
    hi = center[:3] + half
    return {"lo": lo.astype(float).tolist(), "hi": hi.astype(float).tolist()}


def drawer_geometry_aabb(scene: Any, region_name: str, site: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Axis-aligned box of the drawer link's own collision geometry.

    This is the independent measurement the region-site box is cross-checked
    against: a drawer region site describes the drawer's interior, so it must
    lie inside the geometry of the drawer link that owns it.
    """
    boxes = _drawer_collision_boxes(scene, region_name, site)
    corners: list[np.ndarray] = []
    for pos, half in boxes:
        corners.append(np.asarray(pos, dtype=float)[:3] - half)
        corners.append(np.asarray(pos, dtype=float)[:3] + half)
    bounds = _aabb_of(corners)
    if bounds is None:
        return None
    lo, hi = bounds
    return {"lo": lo.astype(float).tolist(), "hi": hi.astype(float).tolist(), "box_count": len(boxes)}


def _geometry_mismatch(site: Mapping[str, Any], geometry_aabb: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Report a gross disagreement between the site box and the drawer geometry."""
    if not geometry_aabb:
        return None
    pos = np.asarray(site.get("pos"), dtype=float).reshape(-1)
    half = site_axis_aligned_half_extents(site)
    if pos.size < 3 or half is None:
        return None
    lo = pos[:3] - half
    hi = pos[:3] + half
    g_lo = np.asarray(geometry_aabb.get("lo"), dtype=float).reshape(-1)[:3]
    g_hi = np.asarray(geometry_aabb.get("hi"), dtype=float).reshape(-1)[:3]
    if not np.isfinite(np.concatenate([g_lo, g_hi])).all():
        return None
    excess = float(np.max(np.maximum(g_lo - lo, hi - g_hi)))
    if excess <= GEOMETRY_MISMATCH_TOLERANCE_M:
        return None
    return (
        f"drawer region site box exceeds the drawer link collision geometry by {excess:.4f} m "
        f"(tolerance {GEOMETRY_MISMATCH_TOLERANCE_M:.3f} m); the site half extents are probably "
        "being read in the wrong frame"
    )


def _footprint_fits(width: float, depth: float, span_x: float, span_y: float) -> bool:
    """Whether a width x depth rectangle fits a span_x x span_y rectangle at any yaw."""
    if width <= span_x and depth <= span_y:
        return True
    if depth <= span_x and width <= span_y:
        return True
    angles = np.linspace(0.0, 0.5 * np.pi, FOOTPRINT_FIT_SAMPLES)
    cos = np.abs(np.cos(angles))
    sin = np.abs(np.sin(angles))
    box_x = width * cos + depth * sin
    box_y = width * sin + depth * cos
    return bool(np.any((box_x <= span_x + 1e-9) & (box_y <= span_y + 1e-9)))


def _object_fits_inner_bounds(site: Mapping[str, Any], object_half: Optional[np.ndarray]) -> tuple[bool, str]:
    if object_half is None:
        return True, ""
    half = site_axis_aligned_half_extents(site)
    if half is None:
        return True, ""
    inner_x = 2.0 * float(half[0]) - 2.0 * XY_INSET_M
    inner_y = 2.0 * float(half[1]) - 2.0 * XY_INSET_M
    if inner_x <= 0.0 or inner_y <= 0.0:
        return False, "cavity inner footprint is empty"
    extent_x = 2.0 * abs(float(object_half[0]))
    extent_y = 2.0 * abs(float(object_half[1]))
    if _footprint_fits(extent_x, extent_y, inner_x, inner_y):
        return True, ""
    return False, (
        f"object footprint {extent_x:.4f}x{extent_y:.4f} m does not fit the cavity inner footprint "
        f"{inner_x:.4f}x{inner_y:.4f} m at any yaw"
    )


def resolve_hand_below_object(hint: Any, object_half: Optional[np.ndarray]) -> tuple[float, str]:
    """Vertical reach of the gripper below the grasped object's centre.

    A top-down grasp puts the fingers alongside the object, so they stop near
    its underside. The old fixed 9 cm made the release point clear a drawer
    rim it never had to clear; the value is now explicit and recorded.
    """
    if hint is not None:
        try:
            value = float(hint)
        except (TypeError, ValueError):
            value = float("nan")
        if np.isfinite(value) and value >= 0.0:
            return value, "skill_hint"
    if object_half is not None:
        return float(abs(object_half[2])), "object_half_height"
    return 0.0, "unknown_default_zero"


def hand_below_object_hint(hints: Any) -> Any:
    """Read the gripper reach override out of a recovery-hints mapping."""
    if isinstance(hints, Mapping):
        return hints.get(HAND_BELOW_OBJECT_HINT_KEY)
    return None


def open_drawer_geometry_diagnostics(
    scene: Any,
    region_name: str,
    site: Mapping[str, Any],
    object_half: Optional[np.ndarray],
    hand_below_object_m: float,
    hand_below_object_source: str,
) -> dict[str, Any]:
    """Every box this decision rests on, so a wrong one is visible in the trace."""
    pos = np.asarray(site.get("pos"), dtype=float).reshape(-1)
    local = _site_local_half_extents(site)
    world = site_axis_aligned_half_extents(site)
    return {
        "site_name": str(site.get("name") or ""),
        "site_type": site.get("type"),
        "site_shape": site.get("shape"),
        "site_local_half_extents": None if local is None else local.tolist(),
        "site_world_half_extents": None if world is None else world.tolist(),
        "site_local_aabb": _box_from_center_half(pos, local),
        "site_world_aabb": _box_from_center_half(pos, world),
        "drawer_geometry_aabb": drawer_geometry_aabb(scene, region_name, site),
        "placed_object_half_extents": (
            None if object_half is None else np.asarray(object_half, dtype=float).reshape(-1)[:3].tolist()
        ),
        "hand_below_object_m": float(hand_below_object_m),
        "hand_below_object_source": hand_below_object_source,
    }


def _drawer_name_matches(name: str, names: set[str], level: str) -> bool:
    low = str(name or "").lower()
    if low in names:
        return True
    return bool(level and level in low and ("cabinet" in low or "drawer" in low))


def _drawer_collision_boxes(
    scene: Any,
    region_name: str,
    site: Mapping[str, Any],
) -> list[tuple[np.ndarray, np.ndarray]]:
    level = _level_token(region_name)
    names = {name.lower() for name in _link_names(region_name)}
    body = str(site.get("body_name") or "").lower()
    if body:
        names.add(body)
    boxes: list[tuple[np.ndarray, np.ndarray]] = []
    seen: set[tuple[Any, ...]] = set()
    for obj in getattr(scene, "objects", {}).values():
        geometry = getattr(obj, "geometry", None) or {}
        if not isinstance(geometry, dict):
            continue
        obj_name = str(getattr(obj, "name", ""))
        obj_matches = _drawer_name_matches(obj_name, names, level)
        for geom in geometry.get("geoms") or []:
            if not isinstance(geom, dict) or geom.get("collision_active") is False:
                continue
            if str(geom.get("shape") or "") != "box":
                continue
            geom_body = str(geom.get("body_name") or obj_name)
            if not obj_matches and not _drawer_name_matches(geom_body, names, level):
                continue
            pos = np.asarray(geom.get("pos"), dtype=float).reshape(-1)
            half = _aabb_half_extents(geom.get("size"), geom.get("quat"))
            if pos.size < 3 or half is None or not np.isfinite(pos[:3]).all():
                continue
            key = (str(geom.get("name") or ""), *(round(float(value), 6) for value in pos[:3]))
            if key in seen:
                continue
            seen.add(key)
            boxes.append((pos[:3].astype(float), half))
    return boxes


def _placed_object_half_extents(scene: Any, object_name: str) -> Optional[np.ndarray]:
    objects = getattr(scene, "objects", {})
    obj = objects.get(object_name) if object_name else None
    if obj is None:
        return None
    center = np.asarray(getattr(obj, "pos", []), dtype=float).reshape(-1)
    if center.size < 3 or not np.isfinite(center[:3]).all():
        return None
    geometry = getattr(obj, "geometry", None) or {}
    extents: list[np.ndarray] = []
    for geom in (geometry.get("geoms") or []) if isinstance(geometry, dict) else []:
        if not isinstance(geom, dict) or geom.get("collision_active") is False:
            continue
        if str(geom.get("shape") or "") != "box":
            continue
        pos = np.asarray(geom.get("pos"), dtype=float).reshape(-1)
        half = _aabb_half_extents(geom.get("size"), geom.get("quat"))
        if pos.size < 3 or half is None or not np.isfinite(pos[:3]).all():
            continue
        low = pos[:3] - half
        high = pos[:3] + half
        extents.append(np.maximum(np.abs(low - center[:3]), np.abs(high - center[:3])))
    if not extents:
        return None
    return np.max(np.stack(extents, axis=0), axis=0)


def _subtract_intervals(
    span: tuple[float, float],
    blocks: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    free = [span]
    for block_lo, block_hi in blocks:
        nxt: list[tuple[float, float]] = []
        for lo, hi in free:
            if block_hi <= lo or block_lo >= hi:
                nxt.append((lo, hi))
                continue
            if block_lo > lo:
                nxt.append((lo, min(block_lo, hi)))
            if block_hi < hi:
                nxt.append((max(block_hi, lo), hi))
        free = [(lo, hi) for lo, hi in nxt if hi - lo > 1e-6]
    return free


def _release_height(
    floor_z: float,
    ceiling_z: float,
    center_xy: np.ndarray,
    object_half: Optional[np.ndarray],
    boxes: list[tuple[np.ndarray, np.ndarray]],
    hand_below_object_m: float,
) -> tuple[Optional[tuple[float, list[float]]], str]:
    if object_half is None:
        hx = hy = hz = 0.0
        pad = 0.0
    else:
        hx, hy, hz = (float(value) for value in object_half[:3])
        pad = COLLISION_CLEARANCE_M
    z_lo = floor_z + hz + pad
    z_hi = ceiling_z - hz - pad
    if z_hi <= z_lo:
        return None, "cavity_too_short_for_object"
    blocks: list[tuple[float, float]] = []
    for pos, half in boxes:
        if abs(float(center_xy[0]) - float(pos[0])) >= hx + float(half[0]) + pad:
            continue
        if abs(float(center_xy[1]) - float(pos[1])) >= hy + float(half[1]) + pad:
            continue
        blocks.append((float(pos[2]) - float(half[2]) - hz - pad, float(pos[2]) + float(half[2]) + hz + pad))
    free = _subtract_intervals((z_lo, z_hi), blocks)
    if not free:
        return None, "no_vertical_gap_at_site_center"
    free.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    gap_lo, gap_hi = free[0]
    release_z = gap_hi
    if boxes and not _hand_clears_boxes(release_z, center_xy, object_half, boxes, pad, hand_below_object_m):
        return None, "hand_clearance_infeasible"
    return (release_z, [gap_lo, gap_hi]), ""


def _hand_clears_boxes(
    release_z: float,
    center_xy: np.ndarray,
    object_half: Optional[np.ndarray],
    boxes: list[tuple[np.ndarray, np.ndarray]],
    pad: float,
    hand_below_object_m: float,
) -> bool:
    """The gripper's lowest point must clear the boards it reaches past.

    Only boards at or below the release height can be hit from below; a board
    above it is reached by the opening/insertion path, which this skill does
    not plan yet. The free-interval search already guarantees the object itself
    clears every board at the release height, so with a gripper that stops at
    the object's underside this check can only fail when the caller declares a
    deeper reach.
    """
    if object_half is None:
        hx = hy = 0.0
    else:
        hx, hy = float(object_half[0]), float(object_half[1])
    hand_bottom = release_z - float(hand_below_object_m)
    for pos, half in boxes:
        if float(pos[2]) + float(half[2]) > release_z + pad:
            continue
        if abs(float(center_xy[0]) - float(pos[0])) >= hx + float(half[0]) + pad:
            continue
        if abs(float(center_xy[1]) - float(pos[1])) >= hy + float(half[1]) + pad:
            continue
        if hand_bottom < float(pos[2]) + float(half[2]) + pad:
            return False
    return True


def cavity_from_site(
    site: Mapping[str, Any],
    *,
    object_half: Optional[np.ndarray] = None,
    collision_boxes: Optional[list[tuple[np.ndarray, np.ndarray]]] = None,
    hand_below_object_m: float = 0.0,
) -> tuple[Optional[dict[str, Any]], str]:
    """Derive the cavity box from a box site, in the planner frame.

    Returns ``(cavity, reason)``; ``cavity`` is None when the skill must refuse
    and ``reason`` then names the concrete cause.
    """
    if not site_is_axis_aligned_box(site):
        return None, "unsupported_site_type"
    pos = np.asarray(site.get("pos"), dtype=float).reshape(-1)
    if pos.size < 3 or not np.isfinite(pos[:3]).all():
        return None, "site_position_unknown"
    # ``site_size`` is in the site frame; rotating it is what keeps the cavity
    # floor on the drawer floor instead of ~7 cm below it.
    half = site_axis_aligned_half_extents(site)
    if half is None:
        return None, "site_size_unknown"
    floor_z = float(pos[2] - half[2])
    ceiling_z = float(pos[2] + half[2])
    height = ceiling_z - floor_z
    if height < MIN_CAVITY_HEIGHT_M:
        return None, "cavity_too_short"
    boxes = list(collision_boxes or [])
    if boxes and object_half is None:
        return None, "placed_object_size_unknown"
    release, release_reason = _release_height(
        floor_z, ceiling_z, pos[:2], object_half, boxes, hand_below_object_m
    )
    if release is None:
        return None, release_reason
    release_z, release_gap = release
    if not floor_z < release_z < ceiling_z:
        return None, "release_outside_cavity"
    x_min = float(pos[0] - half[0] + XY_INSET_M)
    x_max = float(pos[0] + half[0] - XY_INSET_M)
    y_min = float(pos[1] - half[1] + XY_INSET_M)
    y_max = float(pos[1] + half[1] - XY_INSET_M)
    if x_max <= x_min or y_max <= y_min:
        return None, "cavity_inner_footprint_empty"
    release = [float(pos[0]), float(pos[1]), release_z]
    above = [float(pos[0]), float(pos[1]), ceiling_z + RETREAT_CLEARANCE_M]
    return {
        "release_pos": release,
        "approach_pos": list(above),
        "retreat_pos": list(above),
        "floor_z": floor_z,
        "ceiling_z": ceiling_z,
        "inner_bounds": {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "z_min": floor_z,
            "z_max": ceiling_z,
            "support_z": floor_z,
        },
        "place_z_offset_m": release_z - floor_z,
        "release_gap": release_gap,
        "site_name": str(site.get("name") or ""),
        "site_pos": pos[:3].astype(float).tolist(),
        "site_size": half.astype(float).tolist(),
        "site_half_extents_world": half.astype(float).tolist(),
        "hand_below_object_m": float(hand_below_object_m),
    }, ""


def place_waypoints(cavity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Above the opening, release inside the cavity, then leave with the hand open."""
    return [
        {"name": "above_opening", "pos": list(cavity["approach_pos"]), "gripper": "closed"},
        {"name": "release", "pos": list(cavity["release_pos"]), "gripper": "open"},
        {"name": "retreat", "pos": list(cavity["retreat_pos"]), "gripper": "open"},
    ]


def evaluate_open_drawer_place(
    scene: Any,
    surface_name: str,
    object_name: str = "",
    hand_below_object_m: Any = None,
) -> Optional[dict[str, Any]]:
    """Decide whether an object can be released into an already-open drawer.

    Every refusal names a concrete cause, and every box the decision rests on
    is returned so a wrong frame shows up in the trace instead of silently
    becoming an infeasible planning goal.
    """
    region = region_from_surface_name(surface_name)
    if region is None:
        return None
    site = find_region_site(scene, region)
    joint = find_drawer_joint(scene, region)
    if site is None:
        return {"status": "no_site", "region": region, "reason": "drawer region site is not in the live scene"}
    if joint is None or not joint.get("joint_range"):
        return {"status": "unknown", "region": region, "reason": "drawer joint range is unknown"}
    progress = drawer_open_progress(joint["qpos"], joint["joint_range"])
    if progress is None:
        return {"status": "unknown", "region": region, "reason": "drawer joint position is outside its range"}

    boxes = _drawer_collision_boxes(scene, region, site)
    object_half = _placed_object_half_extents(scene, object_name)
    hand_below, hand_below_source = resolve_hand_below_object(hand_below_object_m, object_half)
    geometry = open_drawer_geometry_diagnostics(
        scene, region, site, object_half, hand_below, hand_below_source
    ) if progress >= OPEN_PROGRESS_MIN else {}

    if progress < OPEN_PROGRESS_MIN:
        return {
            "status": "closed",
            "region": region,
            "progress": progress,
            "reason": "drawer is not open; this skill does not open it",
        }
    if not site_is_axis_aligned_box(site):
        return {
            **geometry,
            "status": "unsupported_site_type",
            "region": region,
            "progress": progress,
            "reason": "drawer region site is not a box, so its size is not a cavity half-extent triple",
        }
    if boxes and object_half is None:
        return {
            **geometry,
            "status": "no_cavity",
            "region": region,
            "progress": progress,
            "reason": "placed object size is unknown, so the cavity gap cannot be checked",
        }
    mismatch = _geometry_mismatch(site, geometry.get("drawer_geometry_aabb"))
    if mismatch is not None:
        return {
            **geometry,
            "status": "cavity_geometry_mismatch",
            "region": region,
            "progress": progress,
            "reason": mismatch,
        }
    fits, fit_detail = _object_fits_inner_bounds(site, object_half)
    if not fits:
        return {
            **geometry,
            "status": "object_does_not_fit",
            "region": region,
            "progress": progress,
            "reason": fit_detail,
        }
    cavity, cavity_reason = cavity_from_site(
        site,
        object_half=object_half,
        collision_boxes=boxes,
        hand_below_object_m=hand_below,
    )
    if cavity is None:
        return {
            **geometry,
            "status": "no_cavity",
            "region": region,
            "progress": progress,
            "reason": cavity_reason,
        }
    return {
        **geometry,
        **cavity,
        "status": "ready",
        "region": region,
        "proxy_name": proxy_name_for_region(region),
        "progress": progress,
        "joint_name": joint["joint_name"],
        "reason": "place into the open drawer cavity",
    }


def drawer_surface_is_known(surface: str, scene: Any, parsed: Any) -> bool:
    if parsed is None:
        return False
    selected = select_drawer_inside_goal(
        getattr(parsed, "language", ""),
        (getattr(parsed, "diagnostics", None) or {}).get("bddl_goal_atoms"),
    )
    if selected is None:
        return False
    region = selected[1]
    if surface not in {region, proxy_name_for_region(region)}:
        return False
    return find_region_site(scene, region) is not None or find_drawer_joint(scene, region) is not None


DIAGNOSTIC_KEYS = (
    "site_name",
    "site_type",
    "site_shape",
    "site_local_half_extents",
    "site_world_half_extents",
    "site_local_aabb",
    "site_world_aabb",
    "drawer_geometry_aabb",
    "placed_object_half_extents",
    "hand_below_object_m",
    "hand_below_object_source",
)


def open_drawer_place_diagnostics(decision: Mapping[str, Any]) -> dict[str, Any]:
    """The boxes behind one decision, for the recovery trace and the problem dump."""
    return {key: decision[key] for key in DIAGNOSTIC_KEYS if key in decision}


def rewrite_open_drawer_placement(
    atom: Any,
    scene: Any,
    parsed: Any,
    hand_below_object_m: Any = None,
) -> tuple[Any, dict[str, Any]]:
    pred, args = _atom_pred_args(atom)
    if pred != "inside" or len(args) < 2:
        return atom, {}
    selected = select_drawer_inside_goal(
        getattr(parsed, "language", ""),
        (getattr(parsed, "diagnostics", None) or {}).get("bddl_goal_atoms"),
    )
    if selected is None or (args[0], args[1]) != selected:
        return atom, {}
    decision = evaluate_open_drawer_place(scene, args[1], args[0], hand_below_object_m=hand_below_object_m)
    if not decision:
        return atom, {}
    diagnostics = open_drawer_place_diagnostics(decision)
    if decision["status"] != "ready":
        return atom, {
            "source": "open_drawer_region_site",
            "from": decision["region"],
            "open_drawer_place_status": decision["status"],
            "open_drawer_place_reason": decision["reason"],
            "open_drawer_geometry": diagnostics,
        }
    from .tamp_scene import GroundedAtom

    grounding = {
        "source": "open_drawer_region_site",
        "from": decision["region"],
        "to": decision["proxy_name"],
        "release_pos": list(decision["release_pos"]),
        "approach_pos": list(decision["approach_pos"]),
        "retreat_pos": list(decision["retreat_pos"]),
        "drawer_joint": decision["joint_name"],
        "drawer_open_progress": decision["progress"],
        "open_drawer_place_status": "ready",
        "release_gap": list(decision.get("release_gap") or []),
        "open_drawer_geometry": diagnostics,
    }
    return GroundedAtom("on", (args[0], decision["proxy_name"])), grounding


def surface_descriptor_for_open_drawer(decision: Mapping[str, Any], scene: Any) -> dict[str, Any]:
    inner = dict(decision["inner_bounds"])
    x_span = float(inner["x_max"]) - float(inner["x_min"])
    y_span = float(inner["y_max"]) - float(inner["y_min"])
    thickness = 0.01
    half = [0.5 * x_span, 0.5 * y_span, 0.5 * thickness]
    center = [
        0.5 * (float(inner["x_min"]) + float(inner["x_max"])),
        0.5 * (float(inner["y_min"]) + float(inner["y_max"])),
        float(inner["support_z"]) - half[2],
    ]
    debug = getattr(scene, "robot_joint_debug", {}) or {}
    frame = "planner_frame" if isinstance(debug.get("world_to_planner_frame"), dict) else "world"
    return {
        "shape": "box",
        "kind": "virtual_open_drawer_cavity",
        "center": center,
        # The descriptor is the axis-aligned bounding box of the rotated cavity
        # site, so identity is the correct orientation here: the site's own
        # quaternion has already been folded into ``inner_bounds``.
        "quat": [1.0, 0.0, 0.0, 0.0],
        "half_extents": half,
        "role": "surface",
        "source": "live_drawer_region_site",
        "inner_bounds": inner,
        "inner_bounds_coordinate_frame": frame,
        "metadata": {
            "affordances": ["surface", "placement_region", "inner_floor"],
            "planner_primitive": "inner_floor",
            "place_z_offset_m": float(decision["place_z_offset_m"]),
            "place_candidate_policy": CENTER_ONLY_PLACE_CANDIDATE_POLICY,
            "source_region": decision["region"],
            "source_site_name": decision.get("site_name") or "",
            "open_drawer_release_pos": list(decision["release_pos"]),
            "open_drawer_release_gap": list(decision.get("release_gap") or []),
            "open_drawer_retreat_pos": list(decision["retreat_pos"]),
            "open_drawer_geometry": open_drawer_place_diagnostics(decision),
            "inner_bounds_coordinate_frame": frame,
        },
    }
