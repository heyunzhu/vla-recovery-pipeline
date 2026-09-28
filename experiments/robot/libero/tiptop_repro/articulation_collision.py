"""Conservative oriented-box collision proxies for articulated scene parts."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .articulation import ArticulationError, transform, vector


@dataclass
class CollisionBox:
    name: str
    geom_id: int | None
    pose: np.ndarray
    half_extents: np.ndarray

    def __post_init__(self):
        self.pose = transform(self.pose)
        self.half_extents = vector(self.half_extents, 3)
        if np.any(self.half_extents <= 0):
            raise ArticulationError("collision proxy has nonpositive dimensions")

    def moved(self, displacement):
        return CollisionBox(self.name, self.geom_id, displacement @ self.pose, self.half_extents)


def sphere_clearance(spheres, box: CollisionBox):
    spheres = np.asarray(spheres, dtype=float)
    local = (spheres[:, :3] - box.pose[:3, 3]) @ box.pose[:3, :3]
    distance = np.abs(local) - box.half_extents
    signed = np.linalg.norm(np.maximum(distance, 0), axis=1) + np.minimum(np.max(distance, axis=1), 0)
    return signed - spheres[:, 3]


def boxes_overlap(a: CollisionBox, b: CollisionBox, tolerance: float = 1e-7) -> bool:
    """15-axis separating-axis test; touching faces are not penetration."""
    ra, rb = a.pose[:3, :3], b.pose[:3, :3]
    delta = b.pose[:3, 3] - a.pose[:3, 3]
    axes = [*ra.T, *rb.T, *(np.cross(x, y) for x in ra.T for y in rb.T)]
    for axis in axes:
        length = np.linalg.norm(axis)
        if length < 1e-9:
            continue
        axis = axis / length
        radius = np.sum(a.half_extents * np.abs(ra.T @ axis)) + np.sum(b.half_extents * np.abs(rb.T @ axis))
        if abs(delta @ axis) >= radius - tolerance:
            return False
    return True


def boxes_from_problem(problem) -> list[CollisionBox]:
    from .libero_panda_frames import quat_wxyz_to_matrix
    from .real_cutamp_backend import _cuboid_dims, _cuboid_pose, RealCuTAMPBackendConfig

    result, seen = [], set()
    # Ported from the articulated-manipulation branch's runtime snapshot (their mechanism, not a new
    # invention): objects named in `ignore_collision_object_names` (exact name or `<name>_...`) are
    # dropped from the collision world, and `experiment_scene_table` substitutes a scene-accurate
    # table for this planner's coarse table proxy. Both are opt-in through articulation_options, so
    # the default behaviour is unchanged.
    options = getattr(problem, "articulation_options", {}) or {}
    ignored = {str(name) for name in options.get("ignore_collision_object_names", [])}
    scene_table = options.get("experiment_scene_table")
    for obj in [*problem.statics, *problem.movables, *problem.surfaces]:
        if any(obj.name == item or obj.name.startswith(item + "_") for item in ignored):
            continue
        geoms = obj.geometry.get("articulation_geoms", obj.geometry.get("geoms", []))
        if "articulation_geoms" in obj.geometry and not geoms:
            continue
        if not geoms:
            if obj.name == "table" and isinstance(scene_table, dict):
                pose = np.eye(4)
                pose[:3, :3] = quat_wxyz_to_matrix(scene_table["pose"][3:])
                pose[:3, 3] = scene_table["pose"][:3]
                result.append(CollisionBox("scene_table", None, pose,
                                           np.asarray(scene_table["dims"], dtype=float) / 2))
                continue
            # Match the existing planner's conservative fallback for e.g. table.
            pose7 = _cuboid_pose(obj, RealCuTAMPBackendConfig())
            pose = np.eye(4)
            pose[:3, :3] = quat_wxyz_to_matrix(pose7[3:])
            pose[:3, 3] = pose7[:3]
            result.append(CollisionBox(f"fallback_{len(result)}", None, pose,
                                       np.asarray(_cuboid_dims(obj, RealCuTAMPBackendConfig())) / 2))
            continue
        for geom in geoms:
            if not geom.get("collision_active", True):
                continue
            gid = int(geom["geom_id"])
            if gid in seen:
                continue
            seen.add(gid)
            pose = np.eye(4)
            pose[:3, :3] = quat_wxyz_to_matrix(geom["quat"])
            pose[:3, 3] = geom["pos"]
            size, shape = np.asarray(geom["size"], dtype=float), geom["shape"]
            if shape in {"box", "ellipsoid"}:
                half = size[:3]
            elif shape == "sphere":
                half = np.repeat(size[0], 3)
            elif shape in {"cylinder", "capsule"}:
                half = np.array([size[0], size[0], size[1] + (size[0] if shape == "capsule" else 0)])
            elif shape == "mesh":
                vertices = np.asarray(geom.get("mesh_vertices", []), dtype=float)
                if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
                    raise ArticulationError(f"collision_mesh_vertices_missing:{gid}")
                lo, hi = vertices.min(axis=0), vertices.max(axis=0)
                pose[:3, 3] += pose[:3, :3] @ ((lo + hi) / 2)
                half = (hi - lo) / 2
            else:
                raise ArticulationError(f"unsupported_collision_geometry:{gid}:{shape}")
            result.append(CollisionBox(f"geom_{gid}", gid, pose, half))
    if not result:
        raise ArticulationError("empty_articulation_collision_scene")
    return result
