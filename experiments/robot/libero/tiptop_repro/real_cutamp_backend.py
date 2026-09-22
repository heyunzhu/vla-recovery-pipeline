from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import time
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional, Tuple
import math

import numpy as np

from .cutamp_domain import ActionSchema
from .cutamp_fluents import map_atom_to_cutamp
from .affordances import is_hollow_vessel, is_top_support_surface, is_virtual_support_surface
from .geometry import infer_shallow_receptacle_inner_bounds, is_shallow_receptacle, is_support_floor_collision_part
from .grasp_profiles import (
    DEFAULT_GRASP_SAMPLER_PROFILE,
    GRASP_PROFILE_ADAPTER_PARAM_KEY,
    GraspProfileRegistry,
    NATIVE_GRASP_SAMPLER_PROFILES,
    matrix_to_xyz_rpy,
    normalize_grasp_sampler_profile,
    pose7_rotation_matrix,
    registry_from_adapter_paths,
    rot_z,
    sample_grasp_profile_xyzrpy,
    wrap_yaw_rad,
)
from .libero_panda_frames import matrix_to_quat_wxyz, quat_wxyz_to_matrix, xyzw_to_wxyz
from .tamp_scene import GraspCandidate, GroundedAtom, TAMPObject, TAMPProblem


@dataclass
class RealCuTAMPBackendConfig:
    robot: str = "panda"
    grasp_dof: int = 4
    grasp_sampler_profile: str = DEFAULT_GRASP_SAMPLER_PROFILE
    grasp_profile_adapter_path: str = ""
    num_particles: int = 128
    num_opt_steps: int = 60
    max_loop_dur: float = 30.0
    curobo_plan: bool = False
    object_min_dim: float = 0.035
    surface_min_dim: float = 0.08
    table_xy: Tuple[float, float] = (1.30, 0.85)
    table_x_min_clip: Optional[float] = None
    table_height_override: Optional[float] = None
    table_z_offset: float = 0.0
    table_as_collision_obstacle: bool = True
    table_cutout_xy: Optional[List[float]] = None
    dummy_obstacle_if_empty: bool = True
    static_context_collision_mode: str = "all"
    runner_python: str = ""
    runner_timeout_sec: float = 420.0
    debug_dir: str = ""
    serialize_trajectories: bool = False
    apply_simulator_truth_initial_state: bool = True
    initial_state_min_confidence: float = 0.60
    fail_on_unsupported_holding: bool = True
    enable_initial_holding_prebinding: bool = True
    current_grasp_max_projection_error_deg: float = 10.0
    current_grasp_max_closure_position_error_m: float = 1e-4
    current_grasp_max_closure_rotation_error_deg: float = 0.1
    project_motiongen_start_joint_limits: bool = True
    motiongen_start_limit_slack_rad: float = 0.01
    accept_optimized_plan_if_motiongen_fails: bool = True
    diagnostic_constraint_mult_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)
    diagnostic_constraint_tol_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)
    articulation_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RealCuTAMPBackendResult:
    available: bool
    feasible: bool = False
    num_satisfying: int = 0
    failure_reason: str | None = None
    elapsed_sec: float = 0.0
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    executable_plan: List[Dict[str, Any]] = field(default_factory=list)
    optimized_plan: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "feasible": self.feasible,
            "num_satisfying": self.num_satisfying,
            "failure_reason": self.failure_reason,
            "elapsed_sec": self.elapsed_sec,
            "diagnostics": self.diagnostics,
            "executable_plan": self.executable_plan,
            "optimized_plan": self.optimized_plan,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RealCuTAMPBackendResult":
        return cls(
            available=bool(data.get("available", False)),
            feasible=bool(data.get("feasible", False)),
            num_satisfying=int(data.get("num_satisfying", 0)),
            failure_reason=data.get("failure_reason"),
            elapsed_sec=float(data.get("elapsed_sec", 0.0)),
            diagnostics=dict(data.get("diagnostics", {})),
            executable_plan=list(data.get("executable_plan", [])),
            optimized_plan=dict(data.get("optimized_plan", {})),
        )


def _quat_identity() -> List[float]:
    return [1.0, 0.0, 0.0, 0.0]


def _apply_constraint_overrides(
    target: Dict[str, Dict[str, float]],
    overrides: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, float]]:
    applied: Dict[str, Dict[str, float]] = {}
    if not isinstance(overrides, Mapping):
        return applied
    for constraint_type, values in overrides.items():
        if not isinstance(values, Mapping):
            continue
        dst = target.setdefault(str(constraint_type), {})
        out = applied.setdefault(str(constraint_type), {})
        for name, value in values.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            dst[str(name)] = numeric
            out[str(name)] = numeric
    return applied


_SURFACE_PAD_HEIGHT = 0.01


def _half_extents_xyz(obj: TAMPObject) -> np.ndarray:
    he = np.asarray(getattr(obj, "half_extents", []), dtype=np.float64).reshape(-1)
    out = np.array(
        [
            max(float(obj.radius) if obj.radius else 0.04, 1e-4),
            max(float(obj.radius) if obj.radius else 0.04, 1e-4),
            max(0.5 * float(obj.height or 0.025), 1e-4),
        ],
        dtype=np.float64,
    )
    n = min(3, int(he.size))
    if n:
        out[:n] = np.maximum(he[:n], 1e-4)
    return out


def _geom_center_xyz(obj: TAMPObject) -> np.ndarray:
    geom = obj.geometry if isinstance(obj.geometry, dict) else {}
    center = geom.get("center") if isinstance(geom, dict) else None
    if isinstance(center, (list, tuple)) and len(center) >= 3:
        return np.asarray(center[:3], dtype=np.float64)
    pos = np.asarray(obj.pos, dtype=np.float64).reshape(-1)
    xyz = np.zeros(3, dtype=np.float64)
    xyz[: min(3, pos.size)] = pos[: min(3, pos.size)]
    return xyz


def _inner_bounds(obj: TAMPObject) -> Dict[str, Any]:
    metadata = dict(obj.geometry.get("metadata", {}) if isinstance(obj.geometry, dict) else {})
    inner = metadata.get("inner_bounds", {})
    if isinstance(inner, dict) and inner:
        return dict(inner)
    if obj.role == "surface" and is_shallow_receptacle(obj.name):
        return infer_shallow_receptacle_inner_bounds(
            _geom_center_xyz(obj),
            _half_extents_xyz(obj),
            _collision_parts(obj),
        )
    return {}


def _is_container_surface(obj: TAMPObject) -> bool:
    if obj.role != "surface":
        return False
    if _inner_bounds(obj):
        return True
    metadata = dict(obj.geometry.get("metadata", {}) if isinstance(obj.geometry, dict) else {})
    affordances = metadata.get("affordances", [])
    return "container" in affordances


def _is_support_floor_part(obj: TAMPObject, part: Dict[str, Any]) -> bool:
    return is_support_floor_collision_part(
        obj.name,
        _geom_center_xyz(obj),
        _half_extents_xyz(obj),
        part,
    )


def _table_proxy_bounds(obj: TAMPObject, cfg: RealCuTAMPBackendConfig) -> Dict[str, float]:
    bounds = dict(obj.geometry.get("bounds", {}) if isinstance(obj.geometry, dict) else {})
    pos = np.asarray(obj.pos, dtype=np.float32).reshape(-1)
    center_x = float(pos[0]) if pos.size > 0 else 0.0
    center_y = float(pos[1]) if pos.size > 1 else 0.0
    top_z = float(bounds.get("z", float(pos[2]) if pos.size > 2 else 0.0))
    x_min = float(bounds.get("x_min", center_x - 0.5 * float(cfg.table_xy[0])))
    x_max = float(bounds.get("x_max", center_x + 0.5 * float(cfg.table_xy[0])))
    y_min = float(bounds.get("y_min", center_y - 0.5 * float(cfg.table_xy[1])))
    y_max = float(bounds.get("y_max", center_y + 0.5 * float(cfg.table_xy[1])))
    if cfg.table_x_min_clip is not None:
        x_min = max(x_min, float(cfg.table_x_min_clip))
    if x_max <= x_min:
        x_max = x_min + max(0.05, float(cfg.surface_min_dim))
    height = float(cfg.table_height_override) if cfg.table_height_override is not None else max(0.02, float(obj.height))
    height = max(0.001, height)
    top_z = top_z + float(cfg.table_z_offset)
    return {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "top_z": top_z, "height": height}


def _table_proxy_debug(obj: TAMPObject, cfg: RealCuTAMPBackendConfig) -> Dict[str, Any]:
    bounds = _table_proxy_bounds(obj, cfg)
    return {
        "name": obj.name,
        "input_pos": list(obj.pos),
        "input_half_extents": list(obj.half_extents),
        "input_geometry_bounds": dict(obj.geometry.get("bounds", {}) if isinstance(obj.geometry, dict) else {}),
        "effective_bounds": bounds,
        "dims": [bounds["x_max"] - bounds["x_min"], bounds["y_max"] - bounds["y_min"], bounds["height"]],
        "pose": [(bounds["x_min"] + bounds["x_max"]) * 0.5, (bounds["y_min"] + bounds["y_max"]) * 0.5, bounds["top_z"] - 0.5 * bounds["height"], *_quat_identity()],
        "table_x_min_clip": cfg.table_x_min_clip,
        "table_height_override": cfg.table_height_override,
        "table_z_offset": cfg.table_z_offset,
        "table_as_collision_obstacle": cfg.table_as_collision_obstacle,
        "table_cutout_xy": _normalized_table_cutout_xy(cfg),
        "dummy_obstacle_if_empty": cfg.dummy_obstacle_if_empty,
        "static_context_collision_mode": cfg.static_context_collision_mode,
    }


def _normalized_table_cutout_xy(cfg: RealCuTAMPBackendConfig) -> Optional[Tuple[float, float, float, float]]:
    raw = cfg.table_cutout_xy
    if raw is None:
        return None
    try:
        values = [float(item) for item in list(raw)[:4]]
    except (TypeError, ValueError):
        return None
    if len(values) < 4:
        return None
    x_min, x_max = (values[0], values[1]) if values[0] <= values[1] else (values[1], values[0])
    y_min, y_max = (values[2], values[3]) if values[2] <= values[3] else (values[3], values[2])
    if x_max - x_min < 1e-4 or y_max - y_min < 1e-4:
        return None
    return (x_min, x_max, y_min, y_max)


def _table_cutout_slab_specs(
    bounds: Mapping[str, float],
    cutout_xy: Tuple[float, float, float, float],
    *,
    min_span_m: float = 0.005,
) -> List[Dict[str, Any]]:
    """Replace one table cuboid with up to four slabs around an XY hole."""
    table_x_min = float(bounds["x_min"])
    table_x_max = float(bounds["x_max"])
    table_y_min = float(bounds["y_min"])
    table_y_max = float(bounds["y_max"])
    hole_x_min = max(table_x_min, float(cutout_xy[0]))
    hole_x_max = min(table_x_max, float(cutout_xy[1]))
    hole_y_min = max(table_y_min, float(cutout_xy[2]))
    hole_y_max = min(table_y_max, float(cutout_xy[3]))
    if hole_x_max - hole_x_min < min_span_m or hole_y_max - hole_y_min < min_span_m:
        return []
    height = float(bounds["height"])
    z = float(bounds["top_z"]) - 0.5 * height
    slabs: List[Dict[str, Any]] = []

    def add_slab(name: str, x_min: float, x_max: float, y_min: float, y_max: float) -> None:
        width = x_max - x_min
        depth = y_max - y_min
        if width < min_span_m or depth < min_span_m:
            return
        slabs.append(
            {
                "name": name,
                "dims": [width, depth, height],
                "pose": [0.5 * (x_min + x_max), 0.5 * (y_min + y_max), z, *_quat_identity()],
                "xy": [x_min, x_max, y_min, y_max],
            }
        )

    add_slab("west", table_x_min, hole_x_min, table_y_min, table_y_max)
    add_slab("east", hole_x_max, table_x_max, table_y_min, table_y_max)
    add_slab("south", hole_x_min, hole_x_max, table_y_min, hole_y_min)
    add_slab("north", hole_x_min, hole_x_max, hole_y_max, table_y_max)
    return slabs


def _cuboid_dims(obj: TAMPObject, cfg: RealCuTAMPBackendConfig) -> List[float]:
    if obj.role == "surface":
        if obj.name == "table":
            bounds = _table_proxy_bounds(obj, cfg)
            return [bounds["x_max"] - bounds["x_min"], bounds["y_max"] - bounds["y_min"], bounds["height"]]
        if _is_container_surface(obj):
            inner = _inner_bounds(obj)
            if inner:
                width = max(cfg.surface_min_dim, float(inner["x_max"]) - float(inner["x_min"]))
                depth = max(cfg.surface_min_dim, float(inner["y_max"]) - float(inner["y_min"]))
                return [width, depth, _SURFACE_PAD_HEIGHT]
        he = _half_extents_xyz(obj)
        return [
            max(cfg.surface_min_dim, 2.0 * float(he[0])),
            max(cfg.surface_min_dim, 2.0 * float(he[1])),
            _SURFACE_PAD_HEIGHT,
        ]
    he = _half_extents_xyz(obj)
    return [
        max(cfg.object_min_dim, 2.0 * float(he[0])),
        max(cfg.object_min_dim, 2.0 * float(he[1])),
        max(cfg.object_min_dim, 2.0 * float(he[2])),
    ]


def _cuboid_pose(obj: TAMPObject, cfg: RealCuTAMPBackendConfig) -> List[float]:
    dims = _cuboid_dims(obj, cfg)
    if obj.role == "surface":
        metadata = dict(obj.geometry.get("metadata", {}) if isinstance(obj.geometry, dict) else {})
        if obj.name == "table":
            bounds = _table_proxy_bounds(obj, cfg)
            return [
                (bounds["x_min"] + bounds["x_max"]) * 0.5,
                (bounds["y_min"] + bounds["y_max"]) * 0.5,
                bounds["top_z"] - 0.5 * bounds["height"],
                *_quat_identity(),
            ]
        if _is_container_surface(obj):
            inner = _inner_bounds(obj)
            if inner:
                support_z = float(inner.get("support_z", inner.get("z_min", 0.0)))
                try:
                    support_z = float(metadata.get("planner_support_z_m", support_z))
                except (TypeError, ValueError):
                    pass
                return [
                    0.5 * (float(inner["x_min"]) + float(inner["x_max"])),
                    0.5 * (float(inner["y_min"]) + float(inner["y_max"])),
                    support_z - 0.5 * float(dims[2]),
                    *_quat_identity(),
                ]
        center = _geom_center_xyz(obj)
        he = _half_extents_xyz(obj)
        support_z = float(center[2] + he[2])
        return [float(center[0]), float(center[1]), support_z - 0.5 * float(dims[2]), *_quat_identity()]
    center = _geom_center_xyz(obj)
    return [float(center[0]), float(center[1]), float(center[2]), *_quat_identity()]


def _pose7(pos: Any, quat: Any) -> List[float]:
    xyz = np.zeros(3, dtype=np.float64)
    pos_arr = np.asarray(pos if pos is not None else [0.0, 0.0, 0.0], dtype=np.float64).reshape(-1)
    xyz[: min(3, pos_arr.size)] = pos_arr[: min(3, pos_arr.size)]
    quat_arr = np.asarray(quat if quat is not None else _quat_identity(), dtype=np.float64).reshape(-1)
    quat_out = quat_arr[:4].astype(float).tolist() if quat_arr.size >= 4 else _quat_identity()
    return [float(xyz[0]), float(xyz[1]), float(xyz[2]), *quat_out]


def _compose_pose7(parent: List[float], local: List[float]) -> List[float]:
    parent_m = np.eye(4, dtype=np.float64)
    parent_m[:3, :3] = quat_wxyz_to_matrix(parent[3:7])
    parent_m[:3, 3] = parent[:3]
    local_m = np.eye(4, dtype=np.float64)
    local_m[:3, :3] = quat_wxyz_to_matrix(local[3:7])
    local_m[:3, 3] = local[:3]
    out = parent_m @ local_m
    return [*out[:3, 3].astype(float).tolist(), *matrix_to_quat_wxyz(out[:3, :3]).astype(float).tolist()]


def _part_shapes(parts: List[Dict[str, Any]]) -> List[str]:
    return [str(part.get("shape", "unknown")).lower() for part in parts]


def _single_box_part(parts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(parts) != 1:
        return None
    part = parts[0]
    if str(part.get("shape", "")).lower() != "box":
        return None
    size = np.asarray(part.get("size", []), dtype=np.float64).reshape(-1)
    if size.size < 3:
        return None
    return part


def _cuboid_from_single_box_part(obj: TAMPObject, part: Dict[str, Any]) -> Tuple[List[float], List[float]]:
    """Use the MuJoCo box geom itself so 6-DOF grasp sampling sees a Cuboid."""
    size = np.asarray(part.get("size", []), dtype=np.float64).reshape(-1)
    dims = (2.0 * np.maximum(size[:3], 1e-5)).astype(float).tolist()
    parent = _pose7(obj.pos, getattr(obj, "quat", _quat_identity()))
    local = _pose7(part.get("local_pos", [0.0, 0.0, 0.0]), part.get("local_quat", _quat_identity()))
    return dims, _compose_pose7(parent, local)


def _sanitize_name(name: str) -> str:
    out = []
    for ch in str(name):
        out.append(ch if ch.isalnum() or ch == "_" else "_")
    clean = "".join(out).strip("_")
    return clean or "obj"


def _surface_has_affordance(obj: TAMPObject, affordance: str) -> bool:
    metadata = dict(obj.geometry.get("metadata", {}) if isinstance(obj.geometry, dict) else {})
    values = metadata.get("affordances", [])
    return affordance in values


def _goal_on_target_support_surface_names(problem: TAMPProblem) -> set[str]:
    names_by_relation: Dict[str, set[str]] = {}

    def add_name(name: str, relation: str) -> None:
        if not name:
            return
        names_by_relation.setdefault(str(name), set()).add(str(relation).lower())

    atoms = list(problem.goal_atoms)
    mapped_goal = problem.fluent_mapping.get("goal", {}).get("fluents", []) if problem.fluent_mapping else []
    for item in mapped_goal:
        if not isinstance(item, dict):
            continue
        pred = str(item.get("source_predicate") or item.get("predicate", "")).lower()
        args = tuple(str(arg) for arg in item.get("args", []))
        if pred == "on" and len(args) >= 2:
            add_name(args[1], "on")
        elif pred in {"inside", "in"} and len(args) >= 2:
            add_name(args[1], "inside")
    for atom in atoms:
        pred = atom.predicate.lower()
        if pred == "on" and len(atom.args) >= 2:
            add_name(str(atom.args[1]), "on")
        elif pred in {"inside", "in"} and len(atom.args) >= 2:
            add_name(str(atom.args[1]), "inside")
    problem_surfaces = {obj.name: obj for obj in problem.surfaces}
    problem_objects = {obj.name: obj for obj in [*problem.surfaces, *problem.statics]}
    selected: set[str] = set()
    for name, relations in names_by_relation.items():
        surface = problem_surfaces.get(name)
        if surface is None:
            continue
        is_placement_region = _surface_has_affordance(surface, "placement_region")
        if "on" in relations and (
            is_top_support_surface(name)
            or is_hollow_vessel(name)
            or is_virtual_support_surface(name)
            or is_placement_region
        ):
            selected.add(name)
        if relations & {"inside", "in"} and (
            _is_container_surface(surface)
            or is_hollow_vessel(name)
            or is_virtual_support_surface(name)
            or is_placement_region
        ):
            selected.add(name)

        metadata = dict(surface.geometry.get("metadata", {}) if isinstance(surface.geometry, dict) else {})
        source_object = str(metadata.get("source_object") or "")
        if name in selected and is_placement_region and source_object in problem_objects:
            source_surface = problem_objects[source_object]
            if (
                bool(metadata.get("exclude_source_collision", False))
                or _is_container_surface(source_surface)
                or is_hollow_vessel(source_object)
            ):
                selected.add(source_object)
        if name in selected and bool(metadata.get("exclude_table_collision", False)):
            selected.add("table")
    return selected


def _exclude_target_support_surface_collision(obj: TAMPObject, target_support_surfaces: set[str]) -> bool:
    return obj.role in {"surface", "static_context"} and obj.name in target_support_surfaces


_LIBERO_OBJECT_ROOT_RE = re.compile(r"^(.+?_\d+)(?:_|$)")
_LIBERO_GEOM_PART_RE = re.compile(r"^(.+?_\d+)_g\d+$")


def _libero_object_root(name: str) -> str:
    match = _LIBERO_OBJECT_ROOT_RE.match(str(name or ""))
    return str(match.group(1)) if match else ""


def _libero_geom_part_root(name: str) -> str:
    match = _LIBERO_GEOM_PART_RE.match(str(name or ""))
    return str(match.group(1)) if match else ""


def _collision_parts_with_filter_debug(obj: TAMPObject) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(obj.geometry, dict):
        return [], {}
    metadata = obj.geometry.get("metadata", {})
    if not isinstance(metadata, dict):
        return [], {}
    raw_parts = [dict(part) for part in metadata.get("collision_parts", []) if isinstance(part, dict)]
    object_root = _libero_object_root(obj.name)
    if not object_root:
        return raw_parts, {}

    filtered: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    kept_by_body: List[Dict[str, Any]] = []
    for part in raw_parts:
        part_name = str(part.get("name") or "")
        part_root = _libero_geom_part_root(part_name)
        body_name = str(part.get("body_name") or "")
        body_root = _libero_object_root(body_name)

        if body_root:
            if body_root != object_root:
                dropped.append(
                    {
                        "geom_id": int(part.get("geom_id", -1)),
                        "name": part_name,
                        "body_name": body_name,
                        "expected_object_root": object_root,
                        "actual_part_root": part_root,
                        "actual_body_root": body_root,
                        "reason": "mismatched_libero_body_name",
                    }
                )
                continue
            if part_root and part_root != object_root:
                kept_by_body.append(
                    {
                        "geom_id": int(part.get("geom_id", -1)),
                        "name": part_name,
                        "body_name": body_name,
                        "expected_object_root": object_root,
                        "actual_part_root": part_root,
                        "actual_body_root": body_root,
                        "reason": "matching_body_name_overrides_geom_name",
                    }
                )
            filtered.append(part)
            continue

        if part_root and part_root != object_root:
            dropped.append(
                {
                    "geom_id": int(part.get("geom_id", -1)),
                    "name": part_name,
                    "body_name": body_name,
                    "expected_object_root": object_root,
                    "actual_part_root": part_root,
                    "actual_body_root": body_root,
                    "reason": "mismatched_libero_geom_name",
                }
            )
            continue
        filtered.append(part)

    if not dropped and not kept_by_body:
        return filtered, {}
    debug = {
        "raw_collision_part_count": len(raw_parts),
        "filtered_collision_part_count": len(filtered),
        "dropped_collision_part_count": len(dropped),
    }
    if dropped:
        debug["dropped_collision_parts"] = dropped
    if kept_by_body:
        debug["kept_collision_part_count"] = len(kept_by_body)
        debug["kept_collision_parts"] = kept_by_body
    return filtered, debug


def _collision_parts(obj: TAMPObject) -> List[Dict[str, Any]]:
    parts, _debug = _collision_parts_with_filter_debug(obj)
    return parts


def _part_trimesh(part: Dict[str, Any], *, local: bool):
    import trimesh

    shape = str(part.get("shape", "unknown")).lower()
    size = np.asarray(part.get("size", []), dtype=np.float64).reshape(-1)
    if size.size == 0:
        return None
    if shape == "box" and size.size >= 3:
        mesh = trimesh.creation.box(extents=2.0 * np.maximum(size[:3], 1e-5))
    elif shape == "sphere":
        mesh = trimesh.creation.icosphere(subdivisions=2, radius=max(float(size[0]), 1e-5))
    elif shape == "cylinder" and size.size >= 2:
        mesh = trimesh.creation.cylinder(radius=max(float(size[0]), 1e-5), height=max(2.0 * float(size[1]), 1e-5), sections=24)
    elif shape == "capsule" and size.size >= 2:
        mesh = trimesh.creation.capsule(radius=max(float(size[0]), 1e-5), height=max(2.0 * float(size[1]), 1e-5), count=[12, 12])
    elif shape == "ellipsoid" and size.size >= 3:
        mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        mesh.apply_scale(np.maximum(size[:3], 1e-5))
    elif shape == "mesh" and part.get("mesh_vertices") and part.get("mesh_faces"):
        vertices = np.asarray(part["mesh_vertices"], dtype=np.float64).reshape(-1, 3)
        scale = np.asarray(part.get("mesh_scale") or [1.0, 1.0, 1.0], dtype=np.float64).reshape(-1)[:3]
        mesh = trimesh.Trimesh(vertices=vertices * scale, faces=np.asarray(part["mesh_faces"], dtype=np.int64), process=False)
    else:
        return None

    pos_key = "local_pos" if local else "pos"
    quat_key = "local_quat" if local else "quat"
    pos = np.asarray(part.get(pos_key, [0.0, 0.0, 0.0]), dtype=np.float64).reshape(-1)[:3]
    quat = np.asarray(part.get(quat_key, _quat_identity()), dtype=np.float64).reshape(-1)[:4]
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = quat_wxyz_to_matrix(quat)
    transform[:3, 3] = pos
    mesh.apply_transform(transform)
    return mesh


def _mesh_obstacle(name: str, meshes: List[Any], pose: Optional[List[float]] = None, center_on_aabb: bool = False):
    import trimesh
    from curobo.geom.types import Mesh

    if not meshes:
        return None
    compound = trimesh.util.concatenate(meshes)
    pose7 = list(pose or [0.0, 0.0, 0.0, *_quat_identity()])
    if center_on_aabb and getattr(compound, "vertices", None) is not None and len(compound.vertices) > 0:
        verts = np.asarray(compound.vertices, dtype=np.float64)
        aabb_center = 0.5 * (verts.min(axis=0) + verts.max(axis=0))
        compound.apply_translation((-aabb_center).tolist())
        pose7 = _compose_pose7(pose7, [*aabb_center.astype(float).tolist(), *_quat_identity()])
    return Mesh(
        name=name,
        pose=pose7,
        vertices=np.asarray(compound.vertices, dtype=np.float32),
        faces=np.asarray(compound.faces, dtype=np.int32),
        color=[180, 180, 180, 255],
    )


def _obstacle_local_aabb_dims(obj: Any) -> List[float]:
    verts = getattr(obj, "vertices", None)
    if verts is None:
        get_mesh = getattr(obj, "get_trimesh_mesh", None)
        if callable(get_mesh):
            mesh = get_mesh()
            verts = getattr(mesh, "vertices", None)
    arr = np.asarray(verts if verts is not None else [], dtype=np.float64).reshape(-1, 3)
    if arr.size == 0:
        return [0.10, 0.10, 0.05]
    span = np.maximum(arr.max(axis=0) - arr.min(axis=0), 1e-3)
    return [float(span[0]), float(span[1]), float(span[2])]


def _cuboid_proxy_for_6dof_grasp(obj: Any):
    """6-DOF sampler only reads Cuboid.dims in the object frame; collision stays on `obj`."""
    from curobo.geom.types import Cuboid

    dims = _obstacle_local_aabb_dims(obj)
    proxy = Cuboid(
        name=f"{getattr(obj, 'name', 'obj')}_grasp_aabb",
        dims=dims,
        pose=[0.0, 0.0, 0.0, *_quat_identity()],
        color=[180, 180, 180],
    )
    tensor_args = getattr(obj, "tensor_args", None)
    if tensor_args is not None:
        proxy.tensor_args = tensor_args
    return proxy


def _use_rim_6dof_grasp(obj: Any) -> bool:
    """Hollow vessels are emitted as Mesh; solid cans stay Cuboid."""
    name = str(getattr(obj, "name", "") or "")
    if is_hollow_vessel(name):
        return True
    return getattr(obj, "vertices", None) is not None


def _normalize_grasp_sampler_profile(value: Any, *, registry: GraspProfileRegistry | None = None) -> str:
    return normalize_grasp_sampler_profile(value, registry=registry)


def _grasp_profile_adapter_path_from_hints(recovery_hints: Mapping[str, Any] | None) -> str:
    if not isinstance(recovery_hints, Mapping):
        return ""
    params = recovery_hints.get("params")
    if not isinstance(params, Mapping):
        return ""
    raw = params.get(GRASP_PROFILE_ADAPTER_PARAM_KEY) or params.get("grasp_profile_adapter")
    if raw in (None, ""):
        return ""
    if isinstance(raw, (list, tuple)):
        return str(raw[0]) if raw else ""
    return str(raw)


def _grasp_registry_from_adapter_path(adapter_path: str | Path | None) -> GraspProfileRegistry:
    if adapter_path in (None, ""):
        return registry_from_adapter_paths([])
    return registry_from_adapter_paths([adapter_path])


def _grasp_sampler_profile_from_hints(
    recovery_hints: Mapping[str, Any] | None,
    *,
    registry: GraspProfileRegistry | None = None,
) -> str | None:
    if not recovery_hints:
        return None
    if not isinstance(recovery_hints, Mapping):
        raise ValueError("recovery_hints must be a mapping")
    raw = recovery_hints.get("grasp_profile") or recovery_hints.get("grasp_sampler_profile")
    if raw in (None, ""):
        return None
    return _normalize_grasp_sampler_profile(raw, registry=registry)


def _config_with_recovery_hints(
    cfg: RealCuTAMPBackendConfig,
    recovery_hints: Mapping[str, Any] | None,
) -> RealCuTAMPBackendConfig:
    adapter_path = _grasp_profile_adapter_path_from_hints(recovery_hints) or cfg.grasp_profile_adapter_path
    registry = _grasp_registry_from_adapter_path(adapter_path)
    current_profile = _normalize_grasp_sampler_profile(cfg.grasp_sampler_profile, registry=registry)
    hint_profile = _grasp_sampler_profile_from_hints(recovery_hints, registry=registry)
    effective_profile = hint_profile or current_profile
    if effective_profile == cfg.grasp_sampler_profile and str(adapter_path or "") == str(cfg.grasp_profile_adapter_path or ""):
        return cfg
    return replace(cfg, grasp_sampler_profile=effective_profile, grasp_profile_adapter_path=str(adapter_path or ""))


def _grasp_6dof_xyzrpy_for_profile(
    profile: str,
    dims: List[float],
    *,
    rim: bool,
    pose: Optional[List[float]] = None,
    registry: GraspProfileRegistry | None = None,
) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy(profile, dims, rim=rim, pose=pose, registry=registry)


def _wrap_yaw_rad(value: float) -> float:
    return wrap_yaw_rad(value)


def _rot_z(yaw: float) -> np.ndarray:
    return rot_z(yaw)


def _matrix_to_xyz_rpy(matrix: Any) -> List[float]:
    return matrix_to_xyz_rpy(matrix)


def _ellipse_point(half_x: float, half_y: float, direction: Tuple[float, float], frac: float) -> Tuple[float, float]:
    dx, dy = direction
    return float(frac * half_x * dx), float(frac * half_y * dy)


def _bowl_rim_6dof_xyzrpy(profile: str, dims: List[float]) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy(profile, dims, rim=True)


def _mug_body_side_avoid_handle_6dof_xyzrpy(dims: List[float]) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy("mug_body_side_avoid_handle_v1", dims, rim=True)


def _can_body_lower_side_6dof_xyzrpy(dims: List[float], *, pose: Optional[List[float]] = None) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy("can_body_lower_side_v1", dims, rim=False, pose=pose)


def _small_shallow_bowl_rim_6dof_xyzrpy(dims: List[float]) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy("bowl_rim_small_shallow_diagonal_topdown_v1", dims, rim=True)


def _pose7_rotation_matrix(pose: Optional[List[float]]) -> np.ndarray:
    return pose7_rotation_matrix(pose)


def _flat_box_topdown_short_side_6dof_xyzrpy(dims: List[float], *, pose: Optional[List[float]] = None) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy("flat_box_topdown_short_side_v1", dims, rim=False, pose=pose)


def _topdown_6dof_xyzrpy(dims: List[float], *, rim: bool) -> List[List[float]]:
    return sample_grasp_profile_xyzrpy("libero_topdown", dims, rim=rim)


@contextmanager
def _allow_mesh_6dof_grasp_sampling(
    profile: str = DEFAULT_GRASP_SAMPLER_PROFILE,
    *,
    adapter_path: str | Path | None = None,
):
    """Replace cuTAMP's bookshelf side-grasp 6-DOF sampler with top-down yaw samples.

    The default sampler uses large roll (±45° to ±90°) written for the bookshelf
    domain. LIBERO tabletop bowls need fingers-down grasps, which in cuTAMP's
    object_from_grasp convention is roll=0, pitch=0, yaw varied — the same
    family as the 4-DOF sampler. Top-down profiles currently share this existing
    sampler. Native profiles skip the monkeypatch and leave cuTAMP's sampler
    untouched.
    """
    registry = _grasp_registry_from_adapter_path(adapter_path)
    normalized = _normalize_grasp_sampler_profile(profile, registry=registry)
    if normalized in NATIVE_GRASP_SAMPLER_PROFILES:
        yield
        return

    import cutamp.particle_initialization as particle_init
    import cutamp.samplers as samplers
    from curobo.geom.types import Cuboid

    original = samplers.grasp_6dof_sampler

    def _target_pose7(target) -> Optional[List[float]]:
        try:
            raw = _tensor_json(getattr(target, "pose", None))
        except Exception:
            raw = getattr(target, "pose", None)
        try:
            arr = np.asarray(raw if raw is not None else [], dtype=np.float64).reshape(-1)
        except Exception:
            return None
        if arr.size >= 7:
            return arr[:7].astype(float).tolist()
        return None

    def _topdown_6dof(num_samples: int, obj, num_faces=None):
        rim = _use_rim_6dof_grasp(obj)
        target = obj if isinstance(obj, Cuboid) else _cuboid_proxy_for_6dof_grasp(obj)
        dims = [float(value) for value in (getattr(target, "dims", None) or [0.06, 0.06, 0.04])]
        period = _grasp_6dof_xyzrpy_for_profile(
            normalized,
            dims,
            rim=rim,
            pose=_target_pose7(target),
            registry=registry,
        )
        if not period:
            period = [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]]
        n = max(1, int(num_samples))
        samples = [period[i % len(period)] for i in range(n)]
        return target.tensor_args.to_device(samples)

    samplers.grasp_6dof_sampler = _topdown_6dof
    particle_init.grasp_6dof_sampler = _topdown_6dof
    try:
        yield
    finally:
        samplers.grasp_6dof_sampler = original
        particle_init.grasp_6dof_sampler = original


def _require_native_grasp_sampler(profile: str) -> None:
    """Refuse a non-native grasp profile on the branch that cannot install it.

    ``_allow_mesh_6dof_grasp_sampling`` replaces cuTAMP's sampler with the profile-driven
    one, but only the ``grasp_dof == 6`` branch enters it. On the 4-DOF branch cuTAMP's
    native 4-DOF sampler produces every particle, so a requested profile keeps appearing
    in the config, in the capability registry and in the serialized grasp candidates
    while never influencing a single particle. Measured cost of that silence: a whole
    task pack reported ``0/64 robot_to_movables`` for every profile, which reads like a
    geometry failure instead of a wiring failure. Fail loudly instead.
    """

    if str(profile) in NATIVE_GRASP_SAMPLER_PROFILES:
        return
    raise ValueError(
        f"grasp sampler profile {profile!r} needs the profile-driven sampler, which is only "
        "installed when --real_cutamp_grasp_dof 6. Re-run with 6, or select the native profile "
        "('native' / 'cutamp_native') if a cuTAMP-native sample is what you actually want."
    )



def _plan_summary(plan: Any) -> List[Dict[str, Any]]:
    if not plan:
        return []
    out: List[Dict[str, Any]] = []
    for idx, step in enumerate(plan):
        if not isinstance(step, dict):
            out.append({"idx": idx, "type": type(step).__name__})
            continue
        item = {"idx": idx, "type": str(step.get("type", "unknown")), "label": str(step.get("label", ""))}
        if "action" in step:
            item["action"] = str(step.get("action"))
        out.append(item)
    return out



def _tensor_to_list(value: Any) -> List[Any]:
    try:
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        elif hasattr(value, "cpu"):
            value = value.cpu().numpy()
        return np.asarray(value).astype(float).tolist()
    except Exception:
        return []


def _surface_name_from_place_label(label: str) -> Optional[str]:
    text = str(label or "")
    if "(" not in text:
        return None
    inside = text.split("(", 1)[1].rsplit(")", 1)[0]
    parts = [part.strip() for part in inside.split(",") if part.strip()]
    for part in parts[1:]:
        low = part.lower()
        if low.startswith(("pose", "q", "grasp", "traj")):
            continue
        return part
    return None


def _serialized_surface_openings(problem: TAMPProblem) -> Dict[str, Dict[str, Any]]:
    openings: Dict[str, Dict[str, Any]] = {}
    frame_debug = problem.q_init_debug.get("world_to_planner_frame") if isinstance(problem.q_init_debug, Mapping) else {}
    frame_metadata: Dict[str, Any] = {}
    if isinstance(frame_debug, Mapping):
        origin = frame_debug.get("origin_world")
        quat = frame_debug.get("quat_world_wxyz")
        try:
            origin_values = [float(value) for value in np.asarray(origin, dtype=np.float64).reshape(-1)[:3]]
            quat_values = [float(value) for value in np.asarray(quat, dtype=np.float64).reshape(-1)[:4]]
        except (TypeError, ValueError):
            origin_values = []
            quat_values = []
        if len(origin_values) == 3 and len(quat_values) == 4:
            frame_metadata = {
                "planner_frame": str(frame_debug.get("base_source") or "robot0_base"),
                "planner_frame_method": str(frame_debug.get("method") or ""),
                "planner_frame_origin_world": origin_values,
                "planner_frame_quat_world_wxyz": quat_values,
            }
    for surface in list(problem.surfaces or []):
        geometry = surface.geometry if isinstance(surface.geometry, dict) else {}
        metadata = geometry.get("metadata", {}) if isinstance(geometry, dict) else {}
        inner = metadata.get("inner_bounds", {}) if isinstance(metadata, dict) else {}
        if not isinstance(inner, Mapping):
            continue
        if not all(key in inner for key in ("x_min", "x_max", "y_min", "y_max")):
            continue
        support_z = inner.get("support_z", inner.get("z_min", surface.pos[2] if surface.pos else 0.0))
        bounds_frame = str(
            metadata.get("inner_bounds_coordinate_frame")
            or metadata.get("coordinate_frame")
            or ("planner_frame" if frame_metadata else "world")
        ).strip().lower()
        if bounds_frame in {"robot_base", "robot0_base"}:
            bounds_frame = "planner_frame"
        elif bounds_frame not in {"planner_frame", "world", "world_frame"}:
            bounds_frame = "planner_frame" if frame_metadata else "world"
        try:
            opening = {
                "x_min": float(inner["x_min"]),
                "x_max": float(inner["x_max"]),
                "y_min": float(inner["y_min"]),
                "y_max": float(inner["y_max"]),
                "support_z": float(support_z),
                "surface_label": surface.name,
                "source": "serialized_surface_inner_bounds",
                "coordinate_frame": "world" if bounds_frame == "world_frame" else bounds_frame,
            }
            if bounds_frame == "planner_frame" and frame_metadata:
                opening.update(frame_metadata)
        except (TypeError, ValueError):
            continue
        for key in (
            "support_surface",
            "source_bddl_region",
            "source_bddl_qualified_region",
            "inner_bounds_coordinate_frame",
            "release_mode",
            "release_z_offset_m",
            "release_z_tolerance_m",
            "release_xy_margin_m",
            "planner_support_z_m",
            "exclude_table_collision",
            "inner_bounds_source",
            "source_site_name",
            "site_margin_m",
            "floor_clearance_m",
            "geometry_profile",
            "geometry_profile_adapter_path",
            "geometry_profile_adapter_warning",
            "inner_bounds_adapter",
            "inner_bounds_adapter_path",
            "inner_bounds_profile",
        ):
            if key in metadata:
                opening[key] = metadata[key]
        openings[surface.name] = opening
    return openings


def _serialize_cutamp_plan(
    plan: Any,
    include_trajectories: bool = False,
    surface_openings: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if not plan:
        return []
    surface_openings = dict(surface_openings or {})
    out: List[Dict[str, Any]] = []
    for idx, step in enumerate(plan):
        if not isinstance(step, dict):
            out.append({"idx": idx, "type": type(step).__name__})
            continue
        item: Dict[str, Any] = {
            "idx": idx,
            "type": str(step.get("type", "unknown")),
            "label": str(step.get("label", "")),
        }
        if "action" in step:
            item["action"] = str(step.get("action"))
        surface_name = _surface_name_from_place_label(str(step.get("label", "")))
        if surface_name:
            item["surface_label"] = surface_name
            opening = surface_openings.get(surface_name)
            if opening:
                item["surface_opening"] = dict(opening)
        traj = step.get("plan")
        if traj is not None:
            position = getattr(traj, "position", None)
            velocity = getattr(traj, "velocity", None)
            try:
                item["num_waypoints"] = int(len(position)) if position is not None else 0
            except Exception:
                item["num_waypoints"] = 0
            if include_trajectories:
                item["positions"] = _tensor_to_list(position)
                item["velocities"] = _tensor_to_list(velocity)
                item["dt"] = float(step.get("dt", 0.0) or 0.0)
        out.append(item)
    return out


def _serialize_optimized_cutamp_solution(plan_info: Dict[str, Any], best_particle: Dict[str, Any]) -> Dict[str, Any]:
    bindings = {str(name): _tensor_to_list(value) for name, value in best_particle.items()}
    operators: List[Dict[str, Any]] = []
    for idx, ground_op in enumerate(plan_info.get("plan_skeleton", []) or []):
        operator = getattr(ground_op, "operator", None)
        params = list(getattr(operator, "parameters", []) or [])
        values = [str(value) for value in (getattr(ground_op, "values", []) or [])]
        arguments: List[Dict[str, Any]] = []
        for param_idx, value in enumerate(values):
            param = params[param_idx] if param_idx < len(params) else None
            arguments.append(
                {
                    "parameter": str(getattr(param, "name", f"arg{param_idx}")),
                    "parameter_type": str(getattr(param, "type", "unknown")),
                    "symbol": value,
                    "binding": bindings.get(value),
                }
            )
        operators.append(
            {
                "idx": idx,
                "name": str(getattr(operator, "name", type(ground_op).__name__)),
                "label": str(getattr(ground_op, "name", ground_op)),
                "values": values,
                "arguments": arguments,
            }
        )
    return {
        "source": "cutamp_best_satisfying_particle_after_continuous_optimization",
        "plan_idx": int(plan_info.get("idx", -1)),
        "operators": operators,
        "bindings": bindings,
        "binding_shapes": {
            name: list(np.asarray(value).shape) for name, value in bindings.items()
        },
    }


@contextmanager
def _capture_optimized_cutamp_solution(capture: Dict[str, Any]):
    """Capture cuTAMP's selected skeleton and best satisfying particle without patching cuTAMP source."""
    import cutamp.algorithm as algorithm_module

    original = algorithm_module.get_best_particle

    def wrapped(plan_info, config, constraint_checker, cost_reducer):
        best_particle = original(plan_info, config, constraint_checker, cost_reducer)
        capture.clear()
        capture.update(_serialize_optimized_cutamp_solution(plan_info, best_particle))
        return best_particle

    algorithm_module.get_best_particle = wrapped
    try:
        yield
    finally:
        algorithm_module.get_best_particle = original


def _motiongen_failed(failure_reason: Any) -> bool:
    text = str(failure_reason or "")
    return "Motion planning failed" in text


def _joint_limit_bounds(world: Any) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    candidates = [
        getattr(getattr(world, "robot_container", None), "joint_limits", None),
        getattr(getattr(world, "kin_model", None), "joint_limits", None),
    ]
    motion_gen = getattr(world, "motion_gen", None)
    if motion_gen is not None:
        kin = getattr(motion_gen, "kinematics", None)
        kin_cfg = getattr(kin, "kinematics_config", None)
        cspace = getattr(kin_cfg, "cspace", None)
        candidates.extend(
            [
                getattr(cspace, "joint_limits", None),
                getattr(kin_cfg, "joint_limits", None),
            ]
        )
    for raw in candidates:
        if raw is None:
            continue
        value = raw
        try:
            value = value.detach().cpu().numpy()
        except Exception:
            pass
        arr = np.asarray(value, dtype=np.float64)
        if arr.ndim == 2 and arr.shape[0] == 2 and arr.shape[1] >= 7:
            return arr[0, :7], arr[1, :7]
        if arr.ndim == 2 and arr.shape[1] == 2 and arr.shape[0] >= 7:
            return arr[:7, 0], arr[:7, 1]
    return None


def _q_to_list7(q_value: Any) -> List[float]:
    value = q_value
    try:
        value = value.detach().cpu().numpy()
    except Exception:
        pass
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    return [float(x) for x in arr[:7]]


def _project_q_into_joint_limits(q_value: Any, lower: np.ndarray, upper: np.ndarray, slack_rad: float) -> Tuple[Any, List[Dict[str, Any]]]:
    import torch

    if not isinstance(q_value, torch.Tensor):
        return q_value, []
    flat = q_value.reshape(-1, q_value.shape[-1])
    dof = min(7, int(flat.shape[-1]), int(lower.size), int(upper.size))
    projected = q_value.clone()
    proj_flat = projected.reshape(-1, projected.shape[-1])
    events: List[Dict[str, Any]] = []
    interior = 1e-4
    for idx in range(dof):
        lo = float(lower[idx])
        hi = float(upper[idx])
        lo_in = lo + interior if (hi - lo) > 2.0 * interior else lo
        hi_in = hi - interior if (hi - lo) > 2.0 * interior else hi
        col = proj_flat[:, idx]
        below = col < lo
        above = col > hi
        if bool(below.any()):
            worst = float((lo - col[below]).max().item())
            if worst <= float(slack_rad):
                col = torch.where(below, col.new_tensor(lo_in), col)
                events.append({"index": idx, "side": "lower", "limit": lo, "target": lo_in, "worst_violation_rad": worst, "projected": True})
            else:
                events.append({"index": idx, "side": "lower", "limit": lo, "worst_violation_rad": worst, "projected": False})
        if bool(above.any()):
            worst = float((col[above] - hi).max().item())
            if worst <= float(slack_rad):
                col = torch.where(above, col.new_tensor(hi_in), col)
                events.append({"index": idx, "side": "upper", "limit": hi, "target": hi_in, "worst_violation_rad": worst, "projected": True})
            else:
                events.append({"index": idx, "side": "upper", "limit": hi, "worst_violation_rad": worst, "projected": False})
        proj_flat[:, idx] = col
    return projected, events


@contextmanager
def _project_motiongen_start_joint_limits(debug: Dict[str, Any], slack_rad: float):
    """Project MotionGen start q0 into robot limits without changing the LIBERO q_init seen by rollout."""
    import cutamp.algorithm as algorithm_module
    import cutamp.motion_solver as motion_solver

    original_ms = motion_solver.solve_curobo
    original_algo = algorithm_module.solve_curobo
    debug.update({"enabled": True, "applied": False, "bounds_found": False, "events": [], "calls": [], "slack_rad": float(slack_rad)})

    def wrapped(plan_info, best_particle, world, config, *args, **kwargs):
        bounds = _joint_limit_bounds(world)
        particle = best_particle
        call: Dict[str, Any] = {"bounds_found": bounds is not None}
        if bounds is not None and isinstance(best_particle, dict) and best_particle.get("q0") is not None:
            lower, upper = bounds
            debug["bounds_found"] = True
            call["q0_before"] = _q_to_list7(best_particle["q0"])
            projected_q0, events = _project_q_into_joint_limits(best_particle["q0"], lower, upper, slack_rad)
            call["events"] = events
            call["q0_after"] = _q_to_list7(projected_q0)
            debug["events"] = events
            debug["lower"] = lower.tolist()
            debug["upper"] = upper.tolist()
            if any(event.get("projected") for event in events):
                particle = dict(best_particle)
                particle["q0"] = projected_q0
                debug["applied"] = True
                call["applied"] = True
        debug["calls"].append(call)
        return original_ms(plan_info, particle, world, config, *args, **kwargs)

    motion_solver.solve_curobo = wrapped
    algorithm_module.solve_curobo = wrapped
    try:
        yield
    finally:
        motion_solver.solve_curobo = original_ms
        algorithm_module.solve_curobo = original_algo


def _object_to_dict(obj: TAMPObject) -> Dict[str, Any]:
    return obj.to_dict()


def _object_from_dict(data: Dict[str, Any]) -> TAMPObject:
    return TAMPObject(
        name=str(data["name"]),
        pos=[float(x) for x in data["pos"]],
        radius=float(data["radius"]),
        height=float(data["height"]),
        role=str(data["role"]),
        quat=[float(x) for x in data.get("quat", [1.0, 0.0, 0.0, 0.0])],
        half_extents=[float(x) for x in data.get("half_extents", [])],
        mesh_path=data.get("mesh_path"),
        geometry=dict(data.get("geometry", {})),
    )


def _problem_to_dict(problem: TAMPProblem) -> Dict[str, Any]:
    return {
        "movables": [_object_to_dict(obj) for obj in problem.movables],
        "surfaces": [_object_to_dict(obj) for obj in problem.surfaces],
        "statics": [_object_to_dict(obj) for obj in problem.statics],
        "goal_atoms": [{"predicate": atom.predicate, "args": list(atom.args)} for atom in problem.goal_atoms],
        "grasps": {name: [candidate.to_dict() for candidate in candidates] for name, candidates in problem.grasps.items()},
        "place_candidates": {name: np.asarray(candidates, dtype=np.float32).astype(float).tolist() for name, candidates in problem.place_candidates.items()},
        "init_atoms": list(problem.init_atoms),
        "required_final_atoms": list(problem.required_final_atoms),
        "fluent_mapping": dict(problem.fluent_mapping),
        "action_schemas": [schema.to_dict() for schema in problem.action_schemas],
        "table_z": float(problem.table_z),
        "table_geometry": dict(problem.table_geometry),
        "q_init": list(problem.q_init) if problem.q_init is not None else None,
        "q_init_debug": dict(problem.q_init_debug),
        "current_grasp": _to_jsonable(problem.current_grasp),
        "articulations": _to_jsonable(problem.articulations),
        "articulation_options": _to_jsonable(problem.articulation_options),
    }


def _problem_from_dict(data: Dict[str, Any]) -> TAMPProblem:
    return TAMPProblem(
        movables=[_object_from_dict(obj) for obj in data.get("movables", [])],
        surfaces=[_object_from_dict(obj) for obj in data.get("surfaces", [])],
        statics=[_object_from_dict(obj) for obj in data.get("statics", [])],
        goal_atoms=[GroundedAtom(str(atom["predicate"]), tuple(atom.get("args", []))) for atom in data.get("goal_atoms", [])],
        grasps={
            str(name): [
                GraspCandidate(
                    pos=[float(x) for x in candidate.get("pos", [0.0, 0.0, 0.0])],
                    quat=[float(x) for x in candidate.get("quat", [1.0, 0.0, 0.0, 0.0])],
                    approach=[float(x) for x in candidate.get("approach", [0.0, 0.0, -1.0])],
                    width=float(candidate.get("width", 0.04)),
                    score=float(candidate.get("score", 0.0)),
                    source=str(candidate.get("source", "serialized")),
                    object_name=candidate.get("object_name"),
                    metadata=dict(candidate.get("metadata", {})),
                )
                for candidate in candidates
            ]
            for name, candidates in data.get("grasps", {}).items()
        },
        place_candidates={
            str(name): np.asarray(candidates, dtype=np.float32)
            for name, candidates in data.get("place_candidates", {}).items()
        },
        init_atoms=list(data.get("init_atoms", [])),
        required_final_atoms=list(data.get("required_final_atoms", [])),
        fluent_mapping=dict(data.get("fluent_mapping", {})),
        action_schemas=[
            ActionSchema(
                name=str(schema.get("name", "unknown")),
                parameters=[str(x) for x in schema.get("parameters", [])],
                preconditions=[str(x) for x in schema.get("preconditions", [])],
                effects=[str(x) for x in schema.get("effects", [])],
                continuous_parameters=[str(x) for x in schema.get("continuous_parameters", [])],
                supported_by_executor=bool(schema.get("supported_by_executor", False)),
                diagnostics=dict(schema.get("diagnostics", {})),
            )
            for schema in data.get("action_schemas", [])
        ],
        table_z=float(data.get("table_z", 0.78)),
        table_geometry=dict(data.get("table_geometry", {})),
        q_init=[float(x) for x in data.get("q_init", [])] if data.get("q_init") is not None else None,
        q_init_debug=dict(data.get("q_init_debug", {})),
        current_grasp=dict(data.get("current_grasp", {})) if data.get("current_grasp") else None,
        articulations=dict(data.get("articulations", {})),
        articulation_options=dict(data.get("articulation_options", {})),
    )


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    return value


def _maybe_attr(obj: Any, names: List[str]) -> Any:
    for name in names:
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _extract_cutamp_robot_debug(env: Any, q_init: Optional[List[float]]) -> Dict[str, Any]:
    debug: Dict[str, Any] = {"q_init": list(q_init) if q_init is not None else None}
    seen: set[int] = set()
    queue: List[Tuple[str, Any]] = [("env", env)]
    candidates: List[Dict[str, Any]] = []
    while queue and len(seen) < 64:
        path, obj = queue.pop(0)
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        joint_names = _maybe_attr(obj, ["joint_names", "joint_names_order", "cspace_joint_names", "controlled_joint_names"])
        lower = _maybe_attr(obj, ["lower_limits", "joint_lower_limits", "retract_config_lower", "cspace_lower_limits"])
        upper = _maybe_attr(obj, ["upper_limits", "joint_upper_limits", "retract_config_upper", "cspace_upper_limits"])
        limits = _maybe_attr(obj, ["joint_limits", "limits", "cspace_limits"])
        if joint_names is not None or lower is not None or upper is not None or limits is not None:
            candidates.append(
                {
                    "path": path,
                    "type": type(obj).__name__,
                    "joint_names": _to_jsonable(joint_names),
                    "lower": _to_jsonable(lower),
                    "upper": _to_jsonable(upper),
                    "limits": _to_jsonable(limits),
                }
            )
        for child_name in [
            "robot",
            "robot_model",
            "robot_cfg",
            "kinematics",
            "kinematics_config",
            "cspace",
            "motion_gen",
            "world_model",
        ]:
            try:
                child = getattr(obj, child_name)
            except Exception:
                continue
            if child is not None:
                queue.append((f"{path}.{child_name}", child))
    debug["cutamp_robot_candidates"] = candidates
    return debug


def _tensor_json(value: Any) -> Any:
    if value is None:
        return None
    try:
        value = value.detach().cpu().numpy()
    except Exception:
        pass
    return _to_jsonable(value)


def _runtime_robot_alignment_debug(
    robot: str,
    q_init: Optional[List[float]],
    problem_debug: Dict[str, Any],
) -> Dict[str, Any]:
    debug: Dict[str, Any] = {"requested_robot": robot, "q_init": q_init}
    try:
        import cutamp
        import curobo
        from curobo.types.base import TensorDeviceType
        from cutamp.robots import load_robot_container

        debug["runtime_modules"] = {
            "cutamp": str(getattr(cutamp, "__file__", "")),
            "curobo": str(getattr(curobo, "__file__", "")),
        }
        tensor_args = TensorDeviceType()
        container = load_robot_container(robot, tensor_args)
        debug["container_name"] = str(getattr(container, "name", ""))
        debug["joint_limits"] = _tensor_json(getattr(container, "joint_limits", None))
        debug["tool_from_ee"] = _tensor_json(getattr(container, "tool_from_ee", None))
        kin_model = getattr(container, "kin_model", None)
        kin_cfg = getattr(kin_model, "kinematics_config", None)
        cspace = getattr(kin_cfg, "cspace", None)
        debug["joint_names"] = list(getattr(cspace, "joint_names", []) or [])
        debug["retract_config"] = _tensor_json(getattr(cspace, "retract_config", None))
        debug["ee_link"] = str(getattr(kin_cfg, "ee_link", ""))

        if q_init is not None and kin_model is not None:
            q = tensor_args.to_device(q_init)
            if getattr(q, "ndim", 0) == 1:
                q = q.unsqueeze(0)
            state = kin_model.get_state(q)
            fk_pos = _maybe_attr(state, ["ee_position", "end_effector_position"])
            fk_quat = _maybe_attr(state, ["ee_quaternion", "end_effector_quaternion"])
            debug["fk"] = {
                "position": _tensor_json(fk_pos),
                "quaternion": _tensor_json(fk_quat),
            }
            planner_eef = dict(problem_debug.get("planner_input_eef", {}) or {})
            expected = np.asarray(planner_eef.get("pos", []), dtype=np.float64).reshape(-1)[:3]
            actual = np.asarray(_tensor_json(fk_pos), dtype=np.float64).reshape(-1)[:3]
            if planner_eef and fk_pos is not None:
                if expected.size == 3 and actual.size == 3:
                    debug["fk_position_error_m"] = float(np.linalg.norm(actual - expected))
            tool_from_ee = np.asarray(debug.get("tool_from_ee", []), dtype=np.float64)
            actual_quat = np.asarray(_tensor_json(fk_quat), dtype=np.float64).reshape(-1)[:4]
            expected_quat_xyzw = np.asarray(planner_eef.get("quat_xyzw", []), dtype=np.float64).reshape(-1)[:4]
            if actual_quat.size == 4 and expected_quat_xyzw.size == 4:
                expected_rotation = quat_wxyz_to_matrix(xyzw_to_wxyz(expected_quat_xyzw))
                relative = quat_wxyz_to_matrix(actual_quat) @ expected_rotation.T
                cosine = np.clip((float(np.trace(relative)) - 1.0) * 0.5, -1.0, 1.0)
                debug["fk_hand_orientation_error_deg"] = float(np.degrees(np.arccos(cosine)))
            if (
                tool_from_ee.shape == (4, 4)
                and actual.size == 3
                and actual_quat.size == 4
                and expected.size == 3
                and expected_quat_xyzw.size == 4
            ):
                base_from_ee = np.eye(4, dtype=np.float64)
                base_from_ee[:3, :3] = quat_wxyz_to_matrix(actual_quat)
                base_from_ee[:3, 3] = actual
                base_from_tool = base_from_ee @ tool_from_ee
                debug["fk_tool_position"] = base_from_tool[:3, 3].astype(float).tolist()
                debug["fk_tool_position_error_m"] = float(
                    np.linalg.norm(base_from_tool[:3, 3] - expected)
                )
                debug["fk_tool_position_note"] = (
                    "position uses cuTAMP tool offset; LIBERO EEF orientation follows panda_hand, "
                    "so orientation is reported by fk_hand_orientation_error_deg"
                )

        limits = np.asarray(debug.get("joint_limits", []), dtype=np.float64)
        q_arr = np.asarray(q_init or [], dtype=np.float64)
        if limits.shape[0] == 2 and limits.shape[1] >= q_arr.size and q_arr.size:
            violations = []
            for idx, value in enumerate(q_arr):
                lo, hi = float(limits[0, idx]), float(limits[1, idx])
                if value < lo or value > hi:
                    violations.append({"index": idx, "value": float(value), "lower": lo, "upper": hi})
            debug["joint_limit_violations"] = violations
    except Exception as exc:
        debug["error"] = f"{type(exc).__name__}: {exc}"
    return debug


def _rotation_error_deg(actual: np.ndarray, expected: np.ndarray) -> float:
    relative = np.asarray(actual, dtype=np.float64) @ np.asarray(expected, dtype=np.float64).T
    cosine = np.clip((float(np.trace(relative)) - 1.0) * 0.5, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def _reconstruct_runtime_current_grasp(
    robot: str,
    q_init: Optional[List[float]],
    problem: TAMPProblem,
    name_map: Dict[str, str],
    cfg: RealCuTAMPBackendConfig,
) -> Dict[str, Any]:
    """Reconstruct object_from_grasp using the exact cuTAMP runtime frame chain."""
    observation_grasp = dict(problem.current_grasp or {})
    debug: Dict[str, Any] = {
        "status": "not_holding",
        "requested_grasp_dof": int(cfg.grasp_dof),
        "observation_current_grasp": _to_jsonable(observation_grasp),
    }
    if not observation_grasp:
        return debug

    object_name = str(observation_grasp.get("object_name", ""))
    debug.update(
        {
            "status": "incomplete",
            "object_name": object_name,
            "mapped_object_name": name_map.get(object_name, _sanitize_name(object_name)),
            "symbol": str(observation_grasp.get("symbol", "grasp0")),
            "confidence": float(observation_grasp.get("confidence", 0.0)),
        }
    )
    if q_init is None or len(q_init) != 7:
        debug["failure_reason"] = "q_init_missing_or_not_7dof"
        return debug

    base_from_object = np.asarray(
        observation_grasp.get("base_from_object_matrix", []), dtype=np.float64
    )
    if base_from_object.shape != (4, 4) or not np.isfinite(base_from_object).all():
        debug["failure_reason"] = "base_from_object_matrix_missing_or_invalid"
        return debug

    try:
        import roma
        from curobo.types.base import TensorDeviceType
        from cutamp.robots import load_robot_container

        tensor_args = TensorDeviceType()
        container = load_robot_container(robot, tensor_args)
        q = tensor_args.to_device(q_init)
        if getattr(q, "ndim", 0) == 1:
            q = q.unsqueeze(0)
        state = container.kin_model.get_state(q)
        fk_pos = np.asarray(
            _tensor_json(_maybe_attr(state, ["ee_position", "end_effector_position"])),
            dtype=np.float64,
        ).reshape(-1)[:3]
        fk_quat = np.asarray(
            _tensor_json(_maybe_attr(state, ["ee_quaternion", "end_effector_quaternion"])),
            dtype=np.float64,
        ).reshape(-1)[:4]
        tool_from_ee = np.asarray(_tensor_json(container.tool_from_ee), dtype=np.float64)
        if fk_pos.size != 3 or fk_quat.size != 4 or tool_from_ee.shape != (4, 4):
            debug["failure_reason"] = "runtime_fk_or_tool_transform_invalid"
            return debug

        base_from_ee = np.eye(4, dtype=np.float64)
        base_from_ee[:3, :3] = quat_wxyz_to_matrix(fk_quat)
        base_from_ee[:3, 3] = fk_pos

        # cuTAMP uses: base_from_ee = base_from_object @ object_from_grasp @ tool_from_ee.
        base_from_grasp = base_from_ee @ np.linalg.inv(tool_from_ee)
        object_from_grasp = np.linalg.inv(base_from_object) @ base_from_grasp

        yaw = float(np.arctan2(object_from_grasp[1, 0], object_from_grasp[0, 0]))
        grasp_4dof = [*object_from_grasp[:3, 3].astype(float).tolist(), yaw]
        projected_4dof = np.eye(4, dtype=np.float64)
        projected_4dof[:3, :3] = np.asarray(
            [
                [np.cos(yaw), -np.sin(yaw), 0.0],
                [np.sin(yaw), np.cos(yaw), 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        projected_4dof[:3, 3] = object_from_grasp[:3, 3]
        projection_error = _rotation_error_deg(
            object_from_grasp[:3, :3], projected_4dof[:3, :3]
        )

        rotation_tensor = tensor_args.to_device(object_from_grasp[:3, :3].tolist())
        rpy = np.asarray(
            _tensor_json(roma.rotmat_to_euler("XYZ", rotation_tensor)), dtype=np.float64
        ).reshape(-1)[:3]
        grasp_6dof = [*object_from_grasp[:3, 3].astype(float).tolist(), *rpy.astype(float).tolist()]
        reconstructed_rotation_6dof = np.asarray(
            _tensor_json(roma.euler_to_rotmat("XYZ", tensor_args.to_device(rpy.tolist()))),
            dtype=np.float64,
        ).reshape(3, 3)
        projection_6dof_error = _rotation_error_deg(
            object_from_grasp[:3, :3], reconstructed_rotation_6dof
        )

        closure = base_from_object @ object_from_grasp @ tool_from_ee
        closure_position_error = float(np.linalg.norm(closure[:3, 3] - base_from_ee[:3, 3]))
        closure_rotation_error = _rotation_error_deg(closure[:3, :3], base_from_ee[:3, :3])
        selected_projection_error = projection_error if int(cfg.grasp_dof) == 4 else projection_6dof_error
        selected_value = grasp_4dof if int(cfg.grasp_dof) == 4 else grasp_6dof
        valid = (
            int(cfg.grasp_dof) in {4, 6}
            and selected_projection_error <= float(cfg.current_grasp_max_projection_error_deg)
            and closure_position_error <= float(cfg.current_grasp_max_closure_position_error_m)
            and closure_rotation_error <= float(cfg.current_grasp_max_closure_rotation_error_deg)
        )
        debug.update(
            {
                "status": "ready" if valid else "invalid",
                "source": "cutamp_runtime_q_init_fk",
                "base_from_object_matrix": base_from_object.astype(float).tolist(),
                "base_from_ee_matrix": base_from_ee.astype(float).tolist(),
                "tool_from_ee_matrix": tool_from_ee.astype(float).tolist(),
                "base_from_grasp_matrix": base_from_grasp.astype(float).tolist(),
                "object_from_grasp_matrix": object_from_grasp.astype(float).tolist(),
                "cutamp_grasp_4dof": grasp_4dof,
                "cutamp_grasp_6dof": grasp_6dof,
                "projection_4dof_rotation_error_deg": projection_error,
                "projection_6dof_rotation_error_deg": projection_6dof_error,
                "closure_position_error_m": closure_position_error,
                "closure_rotation_error_deg": closure_rotation_error,
                "selected_grasp_dof": int(cfg.grasp_dof),
                "selected_grasp_value": selected_value,
                "selected_projection_error_deg": selected_projection_error,
                "valid": bool(valid),
                "equation": "base_from_ee = base_from_object @ object_from_grasp @ tool_from_ee",
            }
        )
        if not valid:
            debug["failure_reason"] = "runtime_grasp_failed_closure_or_dof_projection_check"
    except Exception as exc:
        debug["status"] = "error"
        debug["failure_reason"] = f"{type(exc).__name__}: {exc}"
    return debug


def _state_strings(state: Any) -> List[str]:
    return sorted(str(atom) for atom in state)


def _build_simulator_truth_initial_state(
    env: Any,
    problem: TAMPProblem,
    name_map: Dict[str, str],
    cfg: RealCuTAMPBackendConfig,
    runtime_current_grasp: Optional[Dict[str, Any]] = None,
) -> Tuple[frozenset, Dict[str, Any], Optional[str]]:
    from cutamp.tamp_domain import get_initial_state, all_tamp_fluents

    types = dict(getattr(env, "type_to_objects", {}) or {})

    def names(key: str) -> List[str]:
        return [str(getattr(obj, "name", obj)) for obj in types.get(key, [])]

    movable_names = set(names("Movable"))
    surface_names = set(names("Surface"))
    button_names = set(names("Button"))
    stick_names = set(names("Stick"))
    known_names = movable_names | surface_names | button_names | stick_names
    default_state = get_initial_state(
        movables=sorted(movable_names),
        surfaces=sorted(surface_names),
        sticks=sorted(stick_names),
        buttons=sorted(button_names),
    )
    debug: Dict[str, Any] = {
        "problem_init_atoms": list(problem.init_atoms),
        "mapped_init_fluents": list(problem.fluent_mapping.get("init", {}).get("fluents", [])) if problem.fluent_mapping else [],
        "adapter_applies_problem_init_atoms": bool(cfg.apply_simulator_truth_initial_state),
        "initial_state_source": "cutamp_default" if not cfg.apply_simulator_truth_initial_state else "cutamp_default_plus_simulator_truth",
        "initial_state_min_confidence": float(cfg.initial_state_min_confidence),
        "default_initial_state": _state_strings(default_state),
        "applied_fluents": [],
        "dropped_fluents": [],
        "conflicting_fluents": [],
        "unsupported_fluents": [],
        "current_grasp": _to_jsonable(runtime_current_grasp or problem.current_grasp),
    }
    if not cfg.apply_simulator_truth_initial_state:
        debug["applied_initial_state"] = _state_strings(default_state)
        return default_state, debug, None

    name_to_fluent = {fluent.name.lower(): fluent for fluent in all_tamp_fluents}
    candidates: List[Dict[str, Any]] = []
    for atom in problem.init_atoms:
        source = str(atom.get("source", "unknown")) if isinstance(atom, dict) else "unknown"
        confidence = float(atom.get("confidence", 1.0)) if isinstance(atom, dict) else 1.0
        mapped = map_atom_to_cutamp(atom, allow_approximations=True)
        for item in mapped.fluents:
            args = tuple(name_map.get(str(arg), _sanitize_name(str(arg))) for arg in item.args)
            candidates.append(
                {
                    "predicate": item.predicate.lower(),
                    "args": args,
                    "source_predicate": item.source_predicate,
                    "source": source,
                    "confidence": confidence,
                    "approximated": bool(item.approximated),
                    "note": item.note,
                }
            )

    holding_candidates = [item for item in candidates if item["predicate"] in {"holding", "holdingwithgrasp"}]
    handempty_candidates = [item for item in candidates if item["predicate"] == "handempty"]
    blocker: Optional[str] = None
    if holding_candidates:
        if handempty_candidates:
            debug["conflicting_fluents"].append(
                {
                    "reason": "HandEmpty and Holding are both present in simulator-derived atoms",
                    "handempty": handempty_candidates,
                    "holding": holding_candidates,
                }
            )
        reconstructed = dict(runtime_current_grasp or {})
        holding_names = {item["args"][0] for item in holding_candidates if item.get("args")}
        expected_name = name_map.get(str(reconstructed.get("object_name", "")), _sanitize_name(str(reconstructed.get("object_name", ""))))
        grasp_value = reconstructed.get("selected_grasp_value")
        projection_error = float(reconstructed.get("selected_projection_error_deg", float("inf")))
        grasp_ready = (
            bool(reconstructed.get("valid", False))
            and expected_name in holding_names
            and isinstance(grasp_value, list)
            and len(grasp_value) == int(cfg.grasp_dof)
            and all(np.isfinite(float(value)) for value in grasp_value)
        )
        debug["current_grasp_validation"] = {
            "grasp_ready": grasp_ready,
            "expected_object": expected_name,
            "holding_objects": sorted(holding_names),
            "projection_rotation_error_deg": projection_error,
            "selected_grasp_dof": int(cfg.grasp_dof),
            "closure_position_error_m": reconstructed.get("closure_position_error_m"),
            "closure_rotation_error_deg": reconstructed.get("closure_rotation_error_deg"),
            "continuous_particle_binding_supported": bool(cfg.enable_initial_holding_prebinding),
        }
        if not grasp_ready:
            debug["unsupported_fluents"].extend(holding_candidates)
            if cfg.fail_on_unsupported_holding:
                blocker = "unsupported_simulator_holding_state: current grasp reconstruction is incomplete"
        elif not cfg.enable_initial_holding_prebinding and cfg.fail_on_unsupported_holding:
            blocker = "unsupported_initial_holding_binding: cuTAMP particles require current grasp prebinding"

    low_confidence_handempty = [
        item for item in handempty_candidates if float(item["confidence"]) < float(cfg.initial_state_min_confidence)
    ]
    assume_closed_handempty = bool(not holding_candidates and low_confidence_handempty)
    debug["assumed_handempty_from_unconfirmed_closed_gripper"] = assume_closed_handempty
    if assume_closed_handempty:
        debug["assumed_handempty_sources"] = list(low_confidence_handempty)

    state = set(default_state)
    dynamic_predicates = {
        "handempty",
        "holding",
        "holdingwithgrasp",
        "on",
        "buttonpushed",
        "canpush",
        "pushedwithstick",
    }
    best_on_by_object: Dict[str, Dict[str, Any]] = {}
    accepted: List[Dict[str, Any]] = []
    for item in candidates:
        pred = item["predicate"]
        args = item["args"]
        if pred not in dynamic_predicates:
            continue
        if item["confidence"] < float(cfg.initial_state_min_confidence):
            if assume_closed_handempty and pred == "handempty":
                continue
            debug["dropped_fluents"].append({**item, "reason": "below_min_confidence"})
            continue
        if pred == "on":
            if len(args) != 2 or args[0] not in movable_names or args[1] not in surface_names:
                debug["dropped_fluents"].append({**item, "reason": "On requires a known Movable and Surface"})
                continue
            previous = best_on_by_object.get(args[0])
            if previous is None or float(item["confidence"]) > float(previous["confidence"]):
                if previous is not None:
                    debug["dropped_fluents"].append({**previous, "reason": "lower_confidence_On_for_same_object"})
                best_on_by_object[args[0]] = item
            else:
                debug["dropped_fluents"].append({**item, "reason": "lower_confidence_On_for_same_object"})
            continue
        if pred == "holding" and (len(args) != 1 or args[0] not in movable_names):
            debug["dropped_fluents"].append({**item, "reason": "Holding requires a known Movable"})
            continue
        if pred == "holdingwithgrasp" and (
            len(args) != 2
            or args[0] not in movable_names
            or str(args[1]) != str(reconstructed.get("symbol", "grasp0"))
        ):
            debug["dropped_fluents"].append(
                {**item, "reason": "HoldingWithGrasp requires a known Movable and the reconstructed grasp symbol"}
            )
            continue
        if pred == "buttonpushed" and (len(args) != 1 or args[0] not in button_names):
            debug["dropped_fluents"].append({**item, "reason": "ButtonPushed requires a known Button"})
            continue
        if pred == "canpush" and (len(args) != 1 or args[0] not in button_names):
            debug["dropped_fluents"].append({**item, "reason": "CanPush requires a known Button"})
            continue
        if pred == "pushedwithstick" and (
            len(args) != 2 or args[0] not in button_names or args[1] not in stick_names
        ):
            debug["dropped_fluents"].append({**item, "reason": "PushedWithStick requires known Button and Stick objects"})
            continue
        accepted.append(item)
    accepted.extend(best_on_by_object.values())

    if holding_candidates:
        handempty = name_to_fluent.get("handempty")
        if handempty is not None:
            state.discard(handempty.ground())
        has_not_picked_up = name_to_fluent.get("hasnotpickedup")
        if has_not_picked_up is not None:
            for item in holding_candidates:
                if item["predicate"] != "holding" or not item.get("args"):
                    continue
                try:
                    state.discard(has_not_picked_up.ground(item["args"][0]))
                except Exception:
                    pass
    elif handempty_candidates:
        accepted_handempty = max(handempty_candidates, key=lambda item: float(item["confidence"]))
        if accepted_handempty["confidence"] >= float(cfg.initial_state_min_confidence):
            accepted.append(accepted_handempty)
        elif assume_closed_handempty:
            accepted.append(
                {
                    **accepted_handempty,
                    "confidence": float(cfg.initial_state_min_confidence),
                    "assumed": True,
                    "note": "assumed_handempty_from_unconfirmed_closed_gripper",
                }
            )

    seen_grounded = set()
    for item in accepted:
        pred = item["predicate"]
        args = item["args"]
        fluent = name_to_fluent.get(pred)
        if fluent is None:
            debug["dropped_fluents"].append({**item, "reason": "cuTAMP fluent not found"})
            continue
        try:
            grounded = fluent.ground(*args)
        except Exception as exc:
            debug["dropped_fluents"].append({**item, "reason": f"grounding_failed:{type(exc).__name__}:{exc}"})
            continue
        key = str(grounded)
        if key in seen_grounded:
            continue
        seen_grounded.add(key)
        state.add(grounded)
        debug["applied_fluents"].append({**item, "grounded": key})

    debug["known_object_types"] = {
        "Movable": sorted(movable_names),
        "Surface": sorted(surface_names),
        "Button": sorted(button_names),
        "Stick": sorted(stick_names),
    }
    debug["known_object_names"] = sorted(known_names)
    applied_state = frozenset(state)
    debug["applied_initial_state"] = _state_strings(applied_state)
    debug["blocker"] = blocker
    return applied_state, debug, blocker


@contextmanager
def _override_cutamp_initial_state(initial_state: frozenset):
    import cutamp.tamp_world as tamp_world_module

    original = tamp_world_module.get_initial_state
    tamp_world_module.get_initial_state = lambda *args, **kwargs: initial_state
    try:
        yield
    finally:
        tamp_world_module.get_initial_state = original


def _thin_horizontal_world_x_yaws(obj: Any) -> list[float]:
    """World z-yaws that align the cuboid's thin horizontal edge with world +x."""
    dims = [float(item) for item in (getattr(obj, "dims", None) or [0.03, 0.11, 0.13])]
    while len(dims) < 2:
        dims.append(0.05)
    if float(dims[0]) <= float(dims[1]):
        return [0.0, math.pi]
    return [0.5 * math.pi, -0.5 * math.pi]


def _place_yaw_policies_by_surface(problem: TAMPProblem, name_map: Mapping[str, str]) -> Dict[str, str]:
    policies: Dict[str, str] = {}
    for surface in problem.surfaces:
        geometry = surface.geometry if isinstance(surface.geometry, Mapping) else {}
        metadata = geometry.get("metadata") if isinstance(geometry.get("metadata"), Mapping) else {}
        policy = str((metadata or {}).get("place_yaw_policy") or "").strip()
        if policy != "thin_horizontal_along_world_x":
            continue
        safe = str(name_map.get(surface.name) or _sanitize_name(surface.name))
        policies[str(surface.name)] = policy
        policies[safe] = policy
    return policies


@contextmanager
def _override_place_yaw_sampler(
    problem: TAMPProblem,
    name_map: Mapping[str, str],
    debug: Dict[str, Any],
):
    """Pin Place yaw without modifying third_party cuTAMP source."""
    policies = _place_yaw_policies_by_surface(problem, name_map)
    debug.update({"enabled": bool(policies), "policies": dict(policies), "applied": False})
    if not policies:
        yield
        return

    import cutamp.particle_initialization as init_mod
    import cutamp.samplers as samplers_mod

    original = samplers_mod.place_4dof_sampler
    original_init = init_mod.place_4dof_sampler

    def wrapped(num_samples, obj, obj_spheres, surface, *args, **kwargs):
        sampled = original(num_samples, obj, obj_spheres, surface, *args, **kwargs)
        policy = policies.get(str(getattr(surface, "name", "") or ""), "")
        if policy != "thin_horizontal_along_world_x":
            return sampled
        import torch

        if not torch.is_tensor(sampled) or sampled.ndim < 2 or sampled.shape[0] == 0 or sampled.shape[-1] < 4:
            return sampled
        yaws = _thin_horizontal_world_x_yaws(obj)
        yaw_t = torch.tensor(yaws, device=sampled.device, dtype=sampled.dtype)
        idx = torch.randint(0, int(yaw_t.numel()), (int(sampled.shape[0]),), device=sampled.device)
        out = sampled.clone()
        out[:, 3] = yaw_t[idx]
        debug["applied"] = True
        debug["surface"] = str(getattr(surface, "name", "") or "")
        debug["object"] = str(getattr(obj, "name", "") or "")
        debug["yaws"] = list(yaws)
        return out

    samplers_mod.place_4dof_sampler = wrapped
    init_mod.place_4dof_sampler = wrapped
    try:
        yield
    finally:
        samplers_mod.place_4dof_sampler = original
        init_mod.place_4dof_sampler = original_init


@contextmanager
def _override_cutamp_particle_initializer(
    runtime_current_grasp: Optional[Dict[str, Any]],
    q_init: Optional[List[float]],
    debug: Dict[str, Any],
):
    """Prebind an episode-start holding grasp without modifying external cuTAMP source."""
    binding = dict(runtime_current_grasp or {})
    if not binding.get("valid", False):
        debug.update({"enabled": False, "reason": "no_valid_runtime_current_grasp"})
        yield
        return

    import cutamp.algorithm as algorithm_module
    from cutamp.tamp_domain import MoveFree, Pick

    original_initializer = algorithm_module.ParticleInitializer
    grasp_symbol = str(binding.get("symbol", "grasp0"))
    object_name = str(binding.get("mapped_object_name", binding.get("object_name", "")))
    grasp_value = [float(value) for value in binding.get("selected_grasp_value", [])]
    q_value = [float(value) for value in (q_init or [])]
    alias = f"__initial_holding_prebind_{object_name}"
    q_prebind = "q_initial_holding_prebind"
    traj_prebind = "traj_initial_holding_prebind"

    debug.update(
        {
            "enabled": True,
            "applied": False,
            "object_name": object_name,
            "grasp_symbol": grasp_symbol,
            "grasp_dof": len(grasp_value),
            "q_len": len(q_value),
            "strategy": "scoped_initializer_prefix_movefree_pick",
            "external_source_modified": False,
        }
    )

    class InitialHoldingParticleInitializer(original_initializer):
        def __call__(self, plan_skeleton, verbose: bool = True):
            if not plan_skeleton:
                debug["reason"] = "empty_plan_skeleton_no_particles_needed"
                return super().__call__(plan_skeleton, verbose=verbose)

            grasp_tensor = self.world.tensor_args.to_device(grasp_value)
            grasp_tensor = grasp_tensor.reshape(1, -1).repeat(self.config.num_particles, 1)
            q_tensor = self.world.tensor_args.to_device(q_value)
            q_tensor = q_tensor.reshape(1, -1).repeat(self.config.num_particles, 1)
            fake_ik_result = SimpleNamespace(
                solution=q_tensor[:, None, :],
                success=self.world.tensor_args.to_device(
                    [[True]] * self.config.num_particles
                ),
            )
            self.pick_cache[alias] = {
                "sampled_grasps": grasp_tensor,
                "ik_result": fake_ik_result,
                "confidences": self.world.tensor_args.to_device(
                    [float(binding.get("confidence", 1.0))] * self.config.num_particles
                ),
            }

            original_has_object = self.world.has_object
            self.world.has_object = lambda name: name == alias or original_has_object(name)
            prefix = [
                MoveFree.ground(
                    {"q_start": "q0", "traj": traj_prebind, "q_end": q_prebind}
                ),
                Pick.ground({"obj": alias, "grasp": grasp_symbol, "q": q_prebind}),
            ]
            try:
                particles = super().__call__(prefix + list(plan_skeleton), verbose=verbose)
            finally:
                self.world.has_object = original_has_object
                self.pick_cache.pop(alias, None)

            if particles is not None:
                particles.pop(q_prebind, None)
                debug.update(
                    {
                        "applied": grasp_symbol in particles,
                        "particle_keys": sorted(str(key) for key in particles),
                        "num_particles": int(self.config.num_particles),
                    }
                )
                if grasp_symbol in particles:
                    debug["bound_grasp_shape"] = list(particles[grasp_symbol].shape)
                    debug["bound_q0_shape"] = list(particles["q0"].shape)
            return particles

    algorithm_module.ParticleInitializer = InitialHoldingParticleInitializer
    try:
        yield
    finally:
        algorithm_module.ParticleInitializer = original_initializer


def _q_init_debug(problem: TAMPProblem, q_init: Optional[List[float]], env: Any | None = None) -> Dict[str, Any]:
    debug: Dict[str, Any] = dict(problem.q_init_debug)
    debug["q_init_passed_to_cutamp"] = list(q_init) if q_init is not None else None
    debug["q_init_len"] = len(q_init) if q_init is not None else 0
    if env is not None:
        debug.update(_extract_cutamp_robot_debug(env, q_init))
    return debug


class RealCuTAMPBackend:
    """Adapter from our LIBERO TAMPProblem to NVIDIA/cuTAMP's TAMPEnvironment.

    The backend can run in-process when cuTAMP/cuRobo are installed in the eval
    environment. If OpenVLA and cuTAMP live in separate envs, set
    ``runner_python`` to the cuTAMP env's Python and this class will solve in a
    short subprocess, returning the same JSON-compatible result.
    """

    def __init__(self, cfg: RealCuTAMPBackendConfig | None = None) -> None:
        self.cfg = cfg or RealCuTAMPBackendConfig()

    def solve(
        self,
        problem: TAMPProblem,
        recovery_hints: Mapping[str, Any] | None = None,
    ) -> RealCuTAMPBackendResult:
        try:
            cfg = _config_with_recovery_hints(self.cfg, recovery_hints)
        except Exception as exc:
            return RealCuTAMPBackendResult(
                available=True,
                feasible=False,
                failure_reason=f"invalid_recovery_hints:{type(exc).__name__}: {exc}",
                diagnostics={
                    "backend": "cutamp",
                    "recovery_hints": _to_jsonable(recovery_hints),
                },
            )
        backend = self if cfg is self.cfg else RealCuTAMPBackend(cfg)
        if cfg.runner_python and os.environ.get("REAL_CUTAMP_BACKEND_CHILD") != "1":
            return backend._solve_with_runner(problem)
        return backend._solve_in_process(problem)

    def _solve_with_runner(self, problem: TAMPProblem) -> RealCuTAMPBackendResult:
        start = time.time()
        repo_root = Path(__file__).resolve().parents[4]
        grasp_registry = _grasp_registry_from_adapter_path(self.cfg.grasp_profile_adapter_path)
        payload = {
            "problem": _problem_to_dict(problem),
            "config": {**asdict(self.cfg), "runner_python": ""},
        }
        with tempfile.TemporaryDirectory(prefix="real_cutamp_") as tmpdir:
            in_path = Path(tmpdir) / "problem.json"
            out_path = Path(tmpdir) / "result.json"
            in_path.write_text(json.dumps(payload), encoding="utf-8")
            debug_base = Path(self.cfg.debug_dir or os.environ.get("REAL_CUTAMP_DEBUG_DIR", ""))
            debug_prefix = None
            if str(debug_base):
                debug_base.mkdir(parents=True, exist_ok=True)
                debug_prefix = debug_base / f"solve_{int(start * 1000)}_{os.getpid()}"
                shutil.copy2(in_path, debug_prefix.with_suffix(".problem.json"))
            env = os.environ.copy()
            env["REAL_CUTAMP_BACKEND_CHILD"] = "1"
            env.setdefault("CUTAMP_CONTACT_MODE_TARGET", "1")
            env.setdefault("CUTAMP_ALLOW_START_COLLISION_ESCAPE", "1")
            env.setdefault("CUTAMP_START_ESCAPE_Z", "0.08")
            env["PYTHONPATH"] = f"{repo_root}{os.pathsep}" + env.get("PYTHONPATH", "")
            cmd = [
                self.cfg.runner_python,
                "-m",
                "experiments.robot.libero.tiptop_repro.real_cutamp_backend",
                "--solve-json",
                str(in_path),
                "--result-json",
                str(out_path),
            ]
            try:
                timeout_sec = float(self.cfg.runner_timeout_sec) if float(self.cfg.runner_timeout_sec) > 0 else max(float(self.cfg.max_loop_dur) + 240.0, 240.0)
                proc = subprocess.run(cmd, cwd=str(repo_root), env=env, text=True, capture_output=True, timeout=timeout_sec)
                if debug_prefix is not None:
                    debug_prefix.with_suffix(".stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
                    debug_prefix.with_suffix(".stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
                    if out_path.exists():
                        shutil.copy2(out_path, debug_prefix.with_suffix(".result.json"))
            except subprocess.TimeoutExpired as exc:
                if debug_prefix is not None:
                    stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                    stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                    debug_prefix.with_suffix(".timeout.stdout.txt").write_text(stdout, encoding="utf-8")
                    debug_prefix.with_suffix(".timeout.stderr.txt").write_text(stderr, encoding="utf-8")
                return RealCuTAMPBackendResult(
                    available=True,
                    feasible=False,
                    failure_reason=f"runner_timeout:{exc.timeout:.1f}s",
                    elapsed_sec=time.time() - start,
                    diagnostics={
                        "stdout_tail": (exc.stdout or "")[-800:] if isinstance(exc.stdout, str) else "",
                        "stderr_tail": (exc.stderr or "")[-800:] if isinstance(exc.stderr, str) else "",
                        "runner_python": self.cfg.runner_python,
                        "grasp_sampler_profile": _normalize_grasp_sampler_profile(
                            self.cfg.grasp_sampler_profile,
                            registry=grasp_registry,
                        ),
                    },
                )
            if proc.returncode != 0:
                return RealCuTAMPBackendResult(
                    available=False,
                    failure_reason=f"runner_failed:{proc.returncode}: {proc.stderr[-800:]}",
                    elapsed_sec=time.time() - start,
                    diagnostics={
                        "stdout_tail": proc.stdout[-800:],
                        "debug_prefix": str(debug_prefix) if debug_prefix is not None else "",
                        "grasp_sampler_profile": _normalize_grasp_sampler_profile(
                            self.cfg.grasp_sampler_profile,
                            registry=grasp_registry,
                        ),
                    },
                )
            if not out_path.exists():
                return RealCuTAMPBackendResult(
                    available=True,
                    feasible=False,
                    failure_reason="runner_missing_result_json",
                    elapsed_sec=time.time() - start,
                    diagnostics={
                        "stdout_tail": proc.stdout[-800:],
                        "stderr_tail": proc.stderr[-800:],
                        "debug_prefix": str(debug_prefix) if debug_prefix is not None else "",
                        "grasp_sampler_profile": _normalize_grasp_sampler_profile(
                            self.cfg.grasp_sampler_profile,
                            registry=grasp_registry,
                        ),
                    },
                )
            result = RealCuTAMPBackendResult.from_dict(json.loads(out_path.read_text(encoding="utf-8")))
            result.diagnostics.setdefault("runner_python", self.cfg.runner_python)
            result.diagnostics.setdefault("debug_prefix", str(debug_prefix) if debug_prefix is not None else "")
            result.diagnostics.setdefault("runner_elapsed_sec", time.time() - start)
            result.diagnostics.setdefault(
                "grasp_sampler_profile",
                _normalize_grasp_sampler_profile(self.cfg.grasp_sampler_profile, registry=grasp_registry),
            )
            return result

    def _solve_in_process(self, problem: TAMPProblem) -> RealCuTAMPBackendResult:
        start = time.time()
        if any(atom.predicate.lower() in {"open", "closed"} for atom in problem.goal_atoms):
            from .cutamp_articulation import solve_backend_problem
            return solve_backend_problem(problem, self.cfg)
        try:
            grasp_registry = _grasp_registry_from_adapter_path(self.cfg.grasp_profile_adapter_path)
            grasp_sampler_profile = _normalize_grasp_sampler_profile(
                self.cfg.grasp_sampler_profile,
                registry=grasp_registry,
            )
            env, name_map, goal_notes, geometry_debug = self._build_env(problem)
            from cutamp.algorithm import run_cutamp
            from cutamp.config import TAMPConfiguration
            from cutamp.constraint_checker import ConstraintChecker
            from cutamp.cost_reduction import CostReducer
            from cutamp.scripts.utils import default_constraint_to_mult, default_constraint_to_tol
        except Exception as exc:
            return RealCuTAMPBackendResult(
                available=False,
                failure_reason=f"{type(exc).__name__}: {exc}",
                elapsed_sec=time.time() - start,
                diagnostics={
                    "backend": "cutamp",
                    "grasp_sampler_profile": str(getattr(self.cfg, "grasp_sampler_profile", "")),
                },
            )

        try:
            config = TAMPConfiguration(
                num_particles=self.cfg.num_particles,
                robot=self.cfg.robot,
                grasp_dof=self.cfg.grasp_dof,
                num_opt_steps=self.cfg.num_opt_steps,
                max_loop_dur=self.cfg.max_loop_dur,
                enable_visualizer=False,
                rr_spawn=False,
                enable_experiment_logging=False,
                curobo_plan=self.cfg.curobo_plan,
            )
            constraint_to_mult = {key: dict(value) for key, value in default_constraint_to_mult.items()}
            constraint_to_tol = {key: dict(value) for key, value in default_constraint_to_tol.items()}
            stable_key = "StablePlacement"
            constraint_to_mult.setdefault(stable_key, {})["default"] = 2.0
            constraint_to_tol.setdefault(stable_key, {})["default"] = 1e-2
            applied_constraint_overrides = {
                "mult": _apply_constraint_overrides(
                    constraint_to_mult,
                    self.cfg.diagnostic_constraint_mult_overrides,
                ),
                "tol": _apply_constraint_overrides(
                    constraint_to_tol,
                    self.cfg.diagnostic_constraint_tol_overrides,
                ),
            }
            cost_reducer = CostReducer(constraint_to_mult)
            constraint_checker = ConstraintChecker(constraint_to_tol)
            q_init = problem.q_init
            if q_init is not None and len(q_init) == 0:
                q_init = None
            q_debug = _q_init_debug(problem, q_init, env)
            alignment_debug = _runtime_robot_alignment_debug(self.cfg.robot, q_init, problem.q_init_debug)
            runtime_current_grasp = _reconstruct_runtime_current_grasp(
                self.cfg.robot, q_init, problem, name_map, self.cfg
            )
            initial_state, symbolic_debug, initial_state_blocker = _build_simulator_truth_initial_state(
                env, problem, name_map, self.cfg, runtime_current_grasp
            )
            if initial_state_blocker is not None:
                return RealCuTAMPBackendResult(
                    available=True,
                    feasible=False,
                    failure_reason=initial_state_blocker,
                    elapsed_sec=time.time() - start,
                    diagnostics={
                        "backend": "cutamp",
                        "robot": self.cfg.robot,
                        "grasp_sampler_profile": grasp_sampler_profile,
                        "name_map": name_map,
                        "goal_notes": goal_notes,
                        "fluent_mapping": problem.fluent_mapping,
                        "q_init_debug": q_debug,
                        "robot_alignment_debug": alignment_debug,
                        "runtime_current_grasp_debug": runtime_current_grasp,
                        "symbolic_initial_state_debug": symbolic_debug,
                        "geometry_debug": geometry_debug,
                    },
                )
            prebinding_debug: Dict[str, Any] = {}
            place_yaw_debug: Dict[str, Any] = {}
            optimized_plan: Dict[str, Any] = {}
            motiongen_start_debug: Dict[str, Any] = {"enabled": False}
            start_limit_cm = (
                _project_motiongen_start_joint_limits(motiongen_start_debug, self.cfg.motiongen_start_limit_slack_rad)
                if self.cfg.project_motiongen_start_joint_limits
                else nullcontext()
            )
            if int(self.cfg.grasp_dof) == 6:
                grasp_mesh_cm = _allow_mesh_6dof_grasp_sampling(
                    grasp_sampler_profile,
                    adapter_path=self.cfg.grasp_profile_adapter_path,
                )
            else:
                # 4-DOF samples every particle with cuTAMP's native sampler, so a profile that
                # needs the profile-driven sampler would silently never take effect.
                _require_native_grasp_sampler(grasp_sampler_profile)
                grasp_mesh_cm = nullcontext()
            with _override_place_yaw_sampler(problem, name_map, place_yaw_debug):
                with _override_cutamp_initial_state(initial_state):
                    with _override_cutamp_particle_initializer(
                        runtime_current_grasp, q_init, prebinding_debug
                    ):
                        with _capture_optimized_cutamp_solution(optimized_plan):
                            with start_limit_cm:
                                with grasp_mesh_cm:
                                    plan, num_satisfying, failure_reason = run_cutamp(
                                        env, config, cost_reducer, constraint_checker, q_init=q_init
                                    )
            feasible = failure_reason is None and int(num_satisfying) > 0
            if (
                not feasible
                and self.cfg.accept_optimized_plan_if_motiongen_fails
                and int(num_satisfying) > 0
                and optimized_plan
                and _motiongen_failed(failure_reason)
            ):
                feasible = True
            if feasible and not optimized_plan:
                feasible = False
                failure_reason = "optimized_solution_missing_after_continuous_optimization"
            return RealCuTAMPBackendResult(
                available=True,
                feasible=feasible,
                num_satisfying=int(num_satisfying),
                failure_reason=None if failure_reason is None else str(failure_reason),
                elapsed_sec=time.time() - start,
                executable_plan=_serialize_cutamp_plan(
                    plan,
                    include_trajectories=self.cfg.serialize_trajectories,
                    surface_openings=_serialized_surface_openings(problem),
                ),
                optimized_plan=optimized_plan,
                diagnostics={
                    "backend": "cutamp",
                    "robot": self.cfg.robot,
                    "grasp_sampler_profile": grasp_sampler_profile,
                    "num_particles": self.cfg.num_particles,
                    "num_opt_steps": self.cfg.num_opt_steps,
                    "curobo_plan": self.cfg.curobo_plan,
                    "motiongen_start_limit_debug": motiongen_start_debug,
                    "accepted_optimized_plan_after_motiongen_fail": bool(
                        feasible and _motiongen_failed(failure_reason)
                    ),
                    "plan_type": type(plan).__name__,
                    "plan_summary": _plan_summary(plan),
                    "optimized_plan_present": bool(optimized_plan),
                    "optimized_operator_count": len(optimized_plan.get("operators", [])),
                    "optimized_binding_names": sorted(optimized_plan.get("bindings", {})),
                    "diagnostic_constraint_overrides": applied_constraint_overrides,
                    "name_map": name_map,
                    "goal_notes": goal_notes,
                    "fluent_mapping": problem.fluent_mapping,
                    "action_schemas": [schema.to_dict() for schema in problem.action_schemas],
                    "q_init_present": q_init is not None,
                    "q_init_len": len(q_init) if q_init is not None else 0,
                    "q_init_debug": q_debug,
                    "robot_alignment_debug": alignment_debug,
                    "runtime_current_grasp_debug": runtime_current_grasp,
                    "initial_holding_prebinding_debug": prebinding_debug,
                    "place_yaw_sampler_debug": place_yaw_debug,
                    "symbolic_initial_state_debug": symbolic_debug,
                    "grasp_counts": {name: len(candidates) for name, candidates in problem.grasps.items()},
                    "geometry_debug": geometry_debug,
                },
            )
        except Exception as exc:
            return RealCuTAMPBackendResult(
                available=True,
                feasible=False,
                failure_reason=f"{type(exc).__name__}: {exc}",
                elapsed_sec=time.time() - start,
                diagnostics={
                    "backend": "cutamp",
                    "grasp_sampler_profile": locals().get("grasp_sampler_profile", self.cfg.grasp_sampler_profile),
                    "name_map": name_map,
                    "goal_notes": goal_notes,
                    "fluent_mapping": problem.fluent_mapping,
                    "action_schemas": [schema.to_dict() for schema in problem.action_schemas],
                    "geometry_debug": geometry_debug,
                    "q_init_debug": _q_init_debug(problem, problem.q_init, None),
                    "initial_holding_prebinding_debug": locals().get("prebinding_debug", {}),
                    "place_yaw_sampler_debug": locals().get("place_yaw_debug", {}),
                },
            )

    def _build_env(self, problem: TAMPProblem):
        from curobo.geom.types import Cuboid
        from cutamp.envs import TAMPEnvironment
        from cutamp.tamp_domain import all_tamp_fluents

        name_to_fluent = {fluent.name.lower(): fluent for fluent in all_tamp_fluents}
        name_map: Dict[str, str] = {}
        movables = []
        statics = []
        surfaces = []
        geometry_debug: Dict[str, Any] = {"table_proxy": [], "objects": []}
        emitted_static_geom_ids: set[int] = set()
        target_support_surfaces = _goal_on_target_support_surface_names(problem)
        geometry_debug["target_support_surfaces"] = sorted(target_support_surfaces)

        def add_obj(obj: TAMPObject, movable: bool) -> None:
            safe = _sanitize_name(obj.name)
            name_map[obj.name] = safe
            dims = _cuboid_dims(obj, self.cfg)
            pose = _cuboid_pose(obj, self.cfg)
            parts, collision_filter_debug = _collision_parts_with_filter_debug(obj)
            object_debug: Dict[str, Any] = {
                "name": obj.name,
                "safe_name": safe,
                "role": obj.role,
                "object_pose": [*list(obj.pos)[:3], *list(obj.quat)[:4]],
                "collision_part_count": len(parts),
                "collision_parts": [
                    {
                        "geom_id": int(part.get("geom_id", -1)),
                        "name": part.get("name"),
                        "body_name": part.get("body_name"),
                        "shape": part.get("shape"),
                        "size": part.get("size"),
                        "pos": part.get("pos"),
                        "quat": part.get("quat"),
                        "local_pos": part.get("local_pos"),
                        "local_quat": part.get("local_quat"),
                    }
                    for part in parts
                ],
            }
            if collision_filter_debug:
                object_debug["collision_part_filter"] = collision_filter_debug
            if obj.name == "table":
                geometry_debug.setdefault("table_proxy", []).append(_table_proxy_debug(obj, self.cfg))

            proxy = Cuboid(
                name=safe,
                dims=dims,
                pose=pose,
                color=[180, 180, 180],
            )
            if movable:
                box_part = _single_box_part(parts)
                if box_part is not None:
                    # 6-DOF grasp sampling only accepts Cuboid. A single MuJoCo box
                    # should stay a Cuboid instead of being tessellated into a Mesh.
                    box_dims, box_pose = _cuboid_from_single_box_part(obj, box_part)
                    obstacle = Cuboid(
                        name=safe,
                        dims=box_dims,
                        pose=box_pose,
                        color=[180, 180, 180],
                    )
                    object_debug["collision_representation"] = "mujoco_single_box_cuboid"
                    object_debug["cuboid_dims"] = box_dims
                    object_debug["cuboid_pose"] = box_pose
                elif int(self.cfg.grasp_dof) == 6 and not is_hollow_vessel(obj.name):
                    # Compound non-vessel meshes still cannot be 6-DOF sampled.
                    # Keep a Cuboid proxy so the sampler can run; collision is coarser.
                    obstacle = proxy
                    object_debug["collision_representation"] = "grasp_dof6_cuboid_proxy"
                    object_debug["part_shapes"] = _part_shapes(parts)
                    object_debug["fallback_reason"] = (
                        "6-DOF grasp sampler only accepts Cuboid; non-single-box MuJoCo "
                        "geometry is represented by the cuboid proxy instead of a mesh"
                    )
                else:
                    meshes = [mesh for mesh in (_part_trimesh(part, local=True) for part in parts) if mesh is not None]
                    obstacle = _mesh_obstacle(
                        safe,
                        meshes,
                        pose=[*list(obj.pos)[:3], *list(obj.quat)[:4]],
                        center_on_aabb=is_hollow_vessel(obj.name),
                    )
                    if obstacle is None:
                        obstacle = proxy
                        object_debug["collision_representation"] = "fallback_cuboid"
                        object_debug["fallback_reason"] = "no_supported_active_mujoco_geom"
                    else:
                        object_debug["collision_representation"] = (
                            "hollow_vessel_mesh" if is_hollow_vessel(obj.name) else "compound_mujoco_mesh"
                        )
                        object_debug["mesh_part_count"] = len(meshes)
                        if int(self.cfg.grasp_dof) == 6:
                            object_debug["grasp_sampling"] = "6dof_on_mesh_rim"
                movables.append(obstacle)
            else:
                is_surface = obj.role == "surface"
                is_table_surface = is_surface and obj.name == "table"
                is_static_context = obj.role == "static_context"
                is_target_support_surface = _exclude_target_support_surface_collision(obj, target_support_surfaces)
                if is_surface:
                    # Surface semantics require one named support object, independent
                    # of the potentially multi-part collision representation.
                    surfaces.append(proxy)
                include_collision = True
                if is_table_surface and not self.cfg.table_as_collision_obstacle:
                    include_collision = False
                if is_target_support_surface:
                    include_collision = False
                if is_static_context and self.cfg.static_context_collision_mode == "none":
                    include_collision = False
                if include_collision:
                    cutout_xy = _normalized_table_cutout_xy(self.cfg) if is_table_surface else None
                    cutout_slabs = (
                        _table_cutout_slab_specs(_table_proxy_bounds(obj, self.cfg), cutout_xy)
                        if cutout_xy is not None
                        else []
                    )
                    if cutout_slabs:
                        for slab in cutout_slabs:
                            statics.append(
                                Cuboid(
                                    name=f"{safe}__cutout_{slab['name']}",
                                    dims=slab["dims"],
                                    pose=slab["pose"],
                                    color=[180, 180, 180],
                                )
                            )
                        object_debug["collision_representation"] = "table_cutout_cuboids"
                        object_debug["table_cutout_xy"] = list(cutout_xy)
                        object_debug["emitted_collision_parts"] = len(cutout_slabs)
                        if geometry_debug.get("table_proxy"):
                            geometry_debug["table_proxy"][-1]["cutout_slabs"] = cutout_slabs
                    else:
                        emitted = 0
                        duplicate_parts = 0
                        skipped_floor_parts = 0
                        for part in parts:
                            geom_id = int(part.get("geom_id", -1))
                            if geom_id >= 0 and geom_id in emitted_static_geom_ids:
                                duplicate_parts += 1
                                continue
                            if _is_support_floor_part(obj, part):
                                skipped_floor_parts += 1
                                continue
                            mesh = _part_trimesh(part, local=False)
                            if mesh is None:
                                continue
                            part_name = f"{safe}__mj_geom_{geom_id if geom_id >= 0 else emitted}"
                            obstacle = _mesh_obstacle(part_name, [mesh])
                            if obstacle is not None:
                                statics.append(obstacle)
                                emitted += 1
                                if geom_id >= 0:
                                    emitted_static_geom_ids.add(geom_id)
                        if skipped_floor_parts:
                            object_debug["skipped_support_floor_parts"] = skipped_floor_parts
                        if emitted:
                            object_debug["collision_representation"] = "mujoco_part_meshes"
                            object_debug["emitted_collision_parts"] = emitted
                            object_debug["duplicate_parts_suppressed"] = duplicate_parts
                        elif skipped_floor_parts:
                            object_debug["collision_representation"] = "rims_only_floor_excluded"
                            object_debug["emitted_collision_parts"] = 0
                        elif parts and duplicate_parts == len(parts):
                            object_debug["collision_representation"] = "duplicate_parts_suppressed"
                            object_debug["duplicate_parts_suppressed"] = duplicate_parts
                        else:
                            statics.append(proxy)
                            object_debug["collision_representation"] = "fallback_cuboid"
                            object_debug["fallback_reason"] = "no_supported_unique_active_mujoco_geom"
                else:
                    object_debug["collision_representation"] = "excluded"
                    if is_target_support_surface:
                        object_debug["collision_representation"] = "excluded_target_support_surface"
                    geometry_debug.setdefault("excluded_collision_objects", []).append({
                        "name": obj.name,
                        "role": obj.role,
                        "reason": (
                            "target_support_surface"
                            if is_target_support_surface
                            else "table_surface_only" if is_table_surface else "static_context_filtered"
                        ),
                    })
                    if obj.name == "table" and geometry_debug.get("table_proxy"):
                        geometry_debug.setdefault("table_proxy", [])[-1]["collision_obstacle"] = False
            geometry_debug["objects"].append(object_debug)

        for obj in problem.movables:
            add_obj(obj, movable=True)
        for obj in problem.surfaces:
            add_obj(obj, movable=False)
        for obj in problem.statics:
            add_obj(obj, movable=False)

        goal_notes: List[str] = []
        mapped_goal = problem.fluent_mapping.get("goal", {}).get("fluents", []) if problem.fluent_mapping else []
        if mapped_goal:
            requested = [
                (str(item.get("predicate", "")).lower(), tuple(name_map.get(str(x), _sanitize_name(str(x))) for x in item.get("args", [])))
                for item in mapped_goal
            ]
            goal_notes.extend(problem.fluent_mapping.get("goal", {}).get("diagnostics", []))
        else:
            requested = [(atom.predicate.lower(), tuple(name_map.get(x, _sanitize_name(x)) for x in atom.args)) for atom in problem.goal_atoms]
        has_holding = any(pred == "holding" for pred, _ in requested)
        goal_state = set()
        for pred, args in requested:
            if pred == "handempty" and has_holding:
                goal_notes.append("dropped HandEmpty because Holding is also requested")
                continue
            fluent_name = {"holding": "holding", "on": "on", "handempty": "handempty", "inside": "in"}.get(pred, pred)
            fluent = name_to_fluent.get(fluent_name)
            if fluent is None:
                goal_notes.append(f"unknown fluent: {pred}")
                continue
            try:
                goal_state.add(fluent.ground(*args))
            except Exception as exc:
                goal_notes.append(f"failed to ground {pred}{args}: {type(exc).__name__}: {exc}")

        if not statics and self.cfg.dummy_obstacle_if_empty:
            dummy = Cuboid(
                name="dummy_far_obstacle",
                dims=[0.01, 0.01, 0.01],
                pose=[10.0, 10.0, 10.0, *_quat_identity()],
                color=[60, 60, 60],
            )
            statics.append(dummy)
            geometry_debug.setdefault("dummy_obstacles", []).append({
                "name": "dummy_far_obstacle",
                "reason": "empty_collision_world",
                "pose": [10.0, 10.0, 10.0, *_quat_identity()],
                "dims": [0.01, 0.01, 0.01],
            })

        env = TAMPEnvironment(
            name="libero_cutamp_adapter",
            movables=movables,
            statics=statics,
            type_to_objects={
                "Movable": movables,
                "Surface": surfaces,
            },
            goal_state=frozenset(goal_state),
        )
        return env, name_map, goal_notes, geometry_debug


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.solve_json).read_text(encoding="utf-8"))
    cfg = RealCuTAMPBackendConfig(**payload.get("config", {}))
    problem = _problem_from_dict(payload["problem"])
    result = RealCuTAMPBackend(cfg)._solve_in_process(problem)
    Path(args.result_json).write_text(json.dumps(result.to_dict()), encoding="utf-8")


if __name__ == "__main__":
    _main()
