from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .affordances import is_shallow_receptacle, object_affordances, object_category
from .libero_panda_frames import matrix_to_quat_wxyz, quat_wxyz_to_matrix
from .scene_reader import ObjectState, SceneState


@dataclass(frozen=True)
class GeometryProxy:
    kind: str
    center: List[float]
    radius: float
    height: float
    half_extents: List[float]
    mesh_path: Optional[str] = None
    source: str = "sim_truth_proxy"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "center": list(self.center),
            "radius": float(self.radius),
            "height": float(self.height),
            "half_extents": list(self.half_extents),
            "mesh_path": self.mesh_path,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


def _object_bottom_z(obj: ObjectState) -> float:
    raw = dict(getattr(obj, "geometry", {}) or {})
    geoms = list(raw.get("geoms", []) or [])
    bottoms = []
    for geom in geoms:
        pos = np.asarray(geom.get("pos", obj.pos[:3]), dtype=np.float32).reshape(-1)
        size = np.asarray(geom.get("size", [0.0, 0.0, 0.0]), dtype=np.float32).reshape(-1)
        if pos.size >= 3 and size.size >= 3:
            bottoms.append(float(pos[2] - max(float(size[2]), 0.0)))
    if bottoms:
        return float(np.percentile(np.asarray(bottoms, dtype=np.float32), 10))
    return float(obj.pos[2])


def estimate_table_z(scene: SceneState) -> float:
    if not scene.objects:
        return 0.0
    bottoms = np.array([_object_bottom_z(obj) for obj in scene.objects.values()], dtype=np.float32)
    support_z = float(np.percentile(bottoms, 10))
    # cuTAMP's native examples use a table top near z=0, while LIBERO scenes often
    # have table/object heights around z=0.4. Estimate from object bottoms instead
    # of clamping to a fixed simulator-specific height.
    return float(np.clip(support_z, -0.05, 0.90))

def _part_world_center_and_extents(part: Dict[str, Any]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    pos = np.asarray(part.get("pos", []), dtype=np.float64).reshape(-1)
    if pos.size < 3:
        return None
    quat = np.asarray(part.get("quat", [1.0, 0.0, 0.0, 0.0]), dtype=np.float64).reshape(-1)
    if quat.size < 4:
        quat = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    size = np.asarray(part.get("size", []), dtype=np.float64).reshape(-1)
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
    world_ext = np.abs(quat_wxyz_to_matrix(quat[:4])) @ np.maximum(local_ext, 1e-4)
    return pos[:3].astype(np.float64), world_ext


def _site_world_bounds(site: Dict[str, Any]) -> Optional[Dict[str, float]]:
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


def _shrink_xy_bounds(bounds: Dict[str, float], margin_m: float) -> Dict[str, float]:
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


def _geometry_sites(raw_geometry: Mapping[str, Any]) -> List[Dict[str, Any]]:
    sites = list(raw_geometry.get("sites", []) or [])
    metadata = raw_geometry.get("metadata", {}) if isinstance(raw_geometry.get("metadata"), Mapping) else {}
    if isinstance(metadata, Mapping):
        sites.extend(list(metadata.get("sites", []) or []))
        sites.extend(list(metadata.get("containment_sites", []) or []))
    out: List[Dict[str, Any]] = []
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


def receptacle_rim_band(half_extents: Sequence[float]) -> float:
    he = np.asarray(half_extents, dtype=np.float64).reshape(-1)
    span = 2.0 * he[: min(2, he.size)] if he.size else np.asarray([0.2, 0.2], dtype=np.float64)
    if span.size < 2:
        span = np.array([0.2, 0.2], dtype=np.float64)
    return float(min(0.025, 0.18 * max(float(np.min(span)), 1e-3)))


def is_interior_xy_part(
    part: Dict[str, Any],
    aabb_lower: np.ndarray,
    aabb_upper: np.ndarray,
    rim_band: float,
) -> bool:
    info = _part_world_center_and_extents(part)
    if info is None:
        return False
    pos, _ = info
    dist_to_edge = min(
        float(pos[0] - aabb_lower[0]),
        float(aabb_upper[0] - pos[0]),
        float(pos[1] - aabb_lower[1]),
        float(aabb_upper[1] - pos[1]),
    )
    return dist_to_edge > float(rim_band)


def is_support_floor_collision_part(
    object_name: str,
    center: Sequence[float],
    half_extents: Sequence[float],
    part: Dict[str, Any],
) -> bool:
    if not is_shallow_receptacle(object_name):
        return False
    center_arr = np.asarray(center, dtype=np.float64).reshape(-1)
    he = np.asarray(half_extents, dtype=np.float64).reshape(-1)
    if center_arr.size < 3 or he.size < 2:
        return False
    he3 = np.array([0.05, 0.05, 0.02], dtype=np.float64)
    he3[: min(3, he.size)] = he[: min(3, he.size)]
    lower = center_arr[:3] - he3
    upper = center_arr[:3] + he3
    return is_interior_xy_part(part, lower, upper, receptacle_rim_band(he3))


def infer_shallow_receptacle_inner_bounds(
    center: Sequence[float],
    half_extents: Sequence[float],
    collision_parts: Sequence[Dict[str, Any]],
) -> Dict[str, float]:
    center_arr = np.asarray(center, dtype=np.float64).reshape(-1)[:3]
    he = np.asarray(half_extents, dtype=np.float64).reshape(-1)
    he3 = np.array([0.05, 0.05, 0.02], dtype=np.float64)
    he3[: min(3, he.size)] = np.maximum(he[: min(3, he.size)], 1e-4)
    lower = center_arr - he3
    upper = center_arr + he3
    rim = receptacle_rim_band(he3)
    floor_mins: List[np.ndarray] = []
    floor_maxs: List[np.ndarray] = []
    for part in collision_parts:
        if not is_interior_xy_part(part, lower, upper, rim):
            continue
        info = _part_world_center_and_extents(part)
        if info is None:
            continue
        pos, world_ext = info
        floor_mins.append(pos - world_ext)
        floor_maxs.append(pos + world_ext)
    if floor_mins:
        fl = np.min(np.stack(floor_mins, axis=0), axis=0)
        fu = np.max(np.stack(floor_maxs, axis=0), axis=0)
        outer_xy = upper[:2] - lower[:2]
        inner_xy = fu[:2] - fl[:2]
        if bool(np.all(inner_xy >= 0.4 * np.maximum(outer_xy, 1e-4))):
            return {
                "x_min": float(fl[0]),
                "x_max": float(fu[0]),
                "y_min": float(fl[1]),
                "y_max": float(fu[1]),
                "z_min": float(fl[2]),
                "z_max": float(fu[2]),
                "support_z": float(fu[2]),
            }
    return {
        "x_min": float(lower[0] + rim),
        "x_max": float(upper[0] - rim),
        "y_min": float(lower[1] + rim),
        "y_max": float(upper[1] - rim),
        "z_min": float(lower[2]),
        "z_max": float(upper[2]),
        "support_z": float(lower[2] + 0.45 * max(float(upper[2] - lower[2]), 1e-3)),
    }


def _container_inner_bounds(center_arr: np.ndarray, ext_arr: np.ndarray) -> Dict[str, float]:
    return {
        "x_min": float(center_arr[0] - max(ext_arr[0] * 0.75, 0.04)),
        "x_max": float(center_arr[0] + max(ext_arr[0] * 0.75, 0.04)),
        "y_min": float(center_arr[1] - max(ext_arr[1] * 0.75, 0.04)),
        "y_max": float(center_arr[1] + max(ext_arr[1] * 0.75, 0.04)),
        "z_min": float(center_arr[2] - max(ext_arr[2] * 0.35, 0.01)),
        "z_max": float(center_arr[2] + max(ext_arr[2] * 0.75, 0.06)),
        "support_z": float(center_arr[2] - max(ext_arr[2] * 0.35, 0.01)),
    }


def estimate_object_radius(obj: ObjectState, scene: SceneState) -> float:
    other_dists = [
        float(np.linalg.norm(obj.pos[:2] - other.pos[:2]))
        for other in scene.objects.values()
        if other.name != obj.name
    ]
    if not other_dists:
        return 0.045
    return float(np.clip(0.22 * min(other_dists), 0.035, 0.075))


def estimate_table_geometry(scene: SceneState) -> Dict[str, Any]:
    table_z = estimate_table_z(scene)
    if scene.objects:
        xy = np.asarray([obj.pos[:2] for obj in scene.objects.values()], dtype=np.float32)
        x_min = float(np.clip(np.min(xy[:, 0]) - 0.22, -0.75, 0.10))
        x_max = float(np.clip(np.max(xy[:, 0]) + 0.22, 0.10, 0.75))
        y_min = float(np.clip(np.min(xy[:, 1]) - 0.22, -0.60, 0.0))
        y_max = float(np.clip(np.max(xy[:, 1]) + 0.22, 0.0, 0.60))
    else:
        x_min, x_max, y_min, y_max = -0.65, 0.65, -0.45, 0.45
    return {
        "kind": "table_plane",
        "center": [(x_min + x_max) * 0.5, (y_min + y_max) * 0.5, table_z],
        "bounds": {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "z": table_z},
        "half_extents": [(x_max - x_min) * 0.5, (y_max - y_min) * 0.5, 0.02],
        "mesh_path": None,
        "source": "sim_truth_proxy",
    }


def _geometry_from_mujoco(obj: ObjectState) -> Optional[GeometryProxy]:
    raw = dict(getattr(obj, "geometry", {}) or {})
    all_geoms = list(raw.get("geoms", []) or [])
    geoms = [geom for geom in all_geoms if bool(geom.get("collision_active", True))]
    if not geoms:
        return None
    object_pos = np.asarray(obj.pos[:3], dtype=np.float64)
    object_quat = np.asarray(obj.quat if obj.quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    base_from_object = np.eye(4, dtype=np.float64)
    base_from_object[:3, :3] = quat_wxyz_to_matrix(object_quat)
    base_from_object[:3, 3] = object_pos
    object_from_base = np.linalg.inv(base_from_object)

    bounds_min: List[np.ndarray] = []
    bounds_max: List[np.ndarray] = []
    collision_parts: List[Dict[str, Any]] = []
    mesh_path = None
    for geom in geoms:
        pos = np.asarray(geom.get("pos", obj.pos[:3]), dtype=np.float64).reshape(-1)[:3]
        quat = np.asarray(geom.get("quat", [1.0, 0.0, 0.0, 0.0]), dtype=np.float64).reshape(-1)[:4]
        size = np.asarray(geom.get("size", [0.035, 0.035, 0.035]), dtype=np.float64).reshape(-1)
        if size.size == 0:
            size = np.asarray([0.035, 0.035, 0.035], dtype=np.float64)
        base_from_geom = np.eye(4, dtype=np.float64)
        base_from_geom[:3, :3] = quat_wxyz_to_matrix(quat)
        base_from_geom[:3, 3] = pos
        object_from_geom = object_from_base @ base_from_geom

        shape = str(geom.get("shape", "unknown"))
        local_ext = np.zeros(3, dtype=np.float64)
        if shape == "sphere":
            local_ext[:] = float(size[0])
        elif shape in {"capsule", "cylinder"}:
            local_ext[:] = [float(size[0]), float(size[0]), float(size[1] if size.size > 1 else size[0])]
        elif shape in {"box", "ellipsoid"}:
            local_ext[: min(3, size.size)] = size[: min(3, size.size)]
        elif shape == "mesh" and geom.get("mesh_vertices"):
            vertices = np.asarray(geom["mesh_vertices"], dtype=np.float64).reshape(-1, 3)
            mesh_scale = np.asarray(geom.get("mesh_scale") or [1.0, 1.0, 1.0], dtype=np.float64).reshape(-1)[:3]
            vertices = vertices * mesh_scale
            world_vertices = vertices @ base_from_geom[:3, :3].T + pos
            bounds_min.append(world_vertices.min(axis=0))
            bounds_max.append(world_vertices.max(axis=0))
        else:
            local_ext[: min(3, size.size)] = size[: min(3, size.size)]
        if np.any(local_ext > 0.0):
            world_ext = np.abs(base_from_geom[:3, :3]) @ np.maximum(local_ext, 1e-4)
            bounds_min.append(pos - world_ext)
            bounds_max.append(pos + world_ext)

        part = dict(geom)
        part["local_pos"] = object_from_geom[:3, 3].astype(float).tolist()
        part["local_quat"] = matrix_to_quat_wxyz(object_from_geom[:3, :3]).astype(float).tolist()
        collision_parts.append(part)
        mesh_path = mesh_path or geom.get("mesh_path")
    if not bounds_min:
        return None
    lower = np.min(np.stack(bounds_min, axis=0), axis=0)
    upper = np.max(np.stack(bounds_max, axis=0), axis=0)
    center_arr = 0.5 * (lower + upper)
    ext_arr = np.maximum(0.5 * (upper - lower), 1e-4)
    radius = float(np.linalg.norm(ext_arr[:2]))
    height = float(max(0.025, 2.0 * ext_arr[2]))
    category = object_category(obj.name)
    affordances = object_affordances(obj.name)
    kind = (
        "mujoco_mesh"
        if any(geom.get("mesh_id") is not None and int(geom["mesh_id"]) >= 0 for geom in geoms)
        else "mujoco_geom"
    )
    metadata: Dict[str, Any] = {
        "category": category,
        "affordances": affordances,
        "collision_parts": collision_parts,
        "collision_geom_count": len(collision_parts),
        "visual_only_geom_count": len(all_geoms) - len(collision_parts),
        "all_geom_ids": [int(geom.get("geom_id", -1)) for geom in all_geoms],
    }
    sites = _geometry_sites(raw)
    if sites:
        metadata["sites"] = sites
        metadata["site_count"] = len(sites)
        metadata["containment_sites"] = [
            site for site in sites if "contain_region" in str(site.get("name") or "").lower()
        ]
    if "container" in affordances:
        metadata["inner_bounds"] = _container_inner_bounds(center_arr, ext_arr)
    elif is_shallow_receptacle(obj.name):
        metadata["inner_bounds"] = infer_shallow_receptacle_inner_bounds(
            center_arr, ext_arr, collision_parts
        )
    return GeometryProxy(
        kind=kind,
        center=center_arr.astype(float).tolist(),
        radius=radius,
        height=height,
        half_extents=ext_arr.astype(float).tolist(),
        mesh_path=mesh_path,
        source=str(raw.get("source", "mujoco_geom")),
        metadata=metadata,
    )


def estimate_object_geometry(obj: ObjectState, scene: SceneState) -> GeometryProxy:
    mujoco = _geometry_from_mujoco(obj)
    if mujoco is not None:
        return mujoco
    category = object_category(obj.name)
    affordances = object_affordances(obj.name)
    table_z = estimate_table_z(scene)
    radius = estimate_object_radius(obj, scene)
    height = float(np.clip(float(obj.pos[2]) - table_z, 0.025, 0.18))
    kind = "cylinder_proxy"
    half_extents = [radius, radius, max(height * 0.5, 0.015)]
    metadata: Dict[str, Any] = {"category": category, "affordances": affordances}

    if "container" in affordances:
        kind = "container_box_proxy"
        radius = max(radius, 0.075)
        height = max(height, 0.08)
        half_extents = [radius * 1.25, radius * 1.25, height * 0.5]
        metadata["inner_bounds"] = {
            "x_min": float(obj.pos[0] - radius * 0.85),
            "x_max": float(obj.pos[0] + radius * 0.85),
            "y_min": float(obj.pos[1] - radius * 0.85),
            "y_max": float(obj.pos[1] + radius * 0.85),
            "z_min": float(max(table_z + 0.03, obj.pos[2] - 0.01)),
            "z_max": float(obj.pos[2] + max(height, 0.08)),
            "support_z": float(max(table_z + 0.03, obj.pos[2] - 0.01)),
        }
    elif is_shallow_receptacle(obj.name):
        kind = "surface_box_proxy"
        radius = max(radius, 0.08)
        half_extents = [radius * 1.4, radius * 1.4, 0.025]
        metadata["inner_bounds"] = infer_shallow_receptacle_inner_bounds(
            obj.pos[:3], half_extents, []
        )
    elif "surface" in affordances:
        kind = "surface_box_proxy"
        radius = max(radius, 0.08)
        half_extents = [radius * 1.4, radius * 1.4, 0.025]
    elif "door_link" in affordances:
        kind = "articulated_link_proxy"
        half_extents = [max(radius * 0.5, 0.025), max(radius * 1.5, 0.06), max(height * 0.5, 0.02)]
    elif category == "movable":
        kind = "movable_cylinder_proxy"

    center = obj.pos[:3].astype(float).copy()
    if "surface" not in affordances:
        half_z = float(half_extents[2]) if len(half_extents) >= 3 else max(height * 0.5, 0.015)
        center[2] = max(float(center[2]), float(table_z) + half_z)

    return GeometryProxy(
        kind=kind,
        center=center.tolist(),
        radius=radius,
        height=height,
        half_extents=[float(x) for x in half_extents],
        mesh_path=None,
        metadata=metadata,
    )


def point_inside_table_bounds(point: np.ndarray, table_geometry: Dict[str, Any], margin: float = 0.0) -> bool:
    bounds = table_geometry.get("bounds", {})
    x, y = float(point[0]), float(point[1])
    return (
        x >= float(bounds.get("x_min", -0.65)) + margin
        and x <= float(bounds.get("x_max", 0.65)) - margin
        and y >= float(bounds.get("y_min", -0.45)) + margin
        and y <= float(bounds.get("y_max", 0.45)) - margin
    )
