from __future__ import annotations

import copy
import importlib.util
import logging
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from .affordances import is_hollow_vessel, is_probably_movable, is_probably_surface
from .cutamp_domain import ActionSchema, build_action_schemas
from .cutamp_fluents import map_atoms_to_cutamp
from .engine_capabilities import (
    canonical_geometry_descriptor_shape,
    canonical_geometry_planner_primitive,
    canonical_place_candidate_policy,
    canonical_place_yaw_policy,
    canonical_release_mode,
)
from .geometry import (
    estimate_object_geometry,
    estimate_object_radius,
    estimate_table_geometry,
    estimate_table_z,
)
from .grasp_profiles import (
    GraspProfileRegistry,
    is_native_grasp_sampler_profile,
    normalize_grasp_sampler_profile,
    pose7_rotation_matrix,
    profile_gripper_width,
    registry_from_recovery_hints,
    sample_grasp_profile,
)
from .libero_panda_frames import (
    matrix_to_quat_wxyz,
    quat_wxyz_to_matrix,
    robot_base_pose,
    world_to_base_position,
    world_to_base_quat_wxyz,
    wxyz_to_xyzw,
    xyzw_to_wxyz,
)
from .predicates import SymbolicState
from .scene_reader import ObjectState, SceneState
from .task_parser import ParsedTask


logger = logging.getLogger(__name__)


def _topdown_ee_quat_xyzw(yaw: float) -> List[float]:
    """LIBERO grip-site quaternion for a downward grasp, yawed about world z."""
    cosine = float(np.cos(yaw))
    sine = float(np.sin(yaw))
    rot_z = np.asarray([[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    rot_x_pi = np.asarray([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]], dtype=np.float64)
    return wxyz_to_xyzw(matrix_to_quat_wxyz(rot_z @ rot_x_pi)).astype(float).tolist()


@dataclass(frozen=True)
class GroundedAtom:
    predicate: str
    args: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        return {"predicate": self.predicate, "args": list(self.args)}


@dataclass(frozen=True)
class GraspCandidate:
    pos: List[float]
    quat: List[float]
    approach: List[float]
    width: float
    score: float
    source: str = "sim_truth_proxy"
    object_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "pos": list(self.pos),
            "quat": list(self.quat),
            "approach": list(self.approach),
            "width": float(self.width),
            "score": float(self.score),
            "source": self.source,
            "object_name": self.object_name,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_point(
        cls,
        object_name: str,
        point: np.ndarray,
        width: float,
        score: float,
        source: str = "sim_truth_proxy_topdown",
        metadata: Optional[Dict[str, Any]] = None,
        quat: Optional[List[float]] = None,
        approach: Optional[List[float]] = None,
    ) -> "GraspCandidate":
        return cls(
            pos=np.asarray(point, dtype=np.float32)[:3].astype(float).tolist(),
            quat=list(quat) if quat is not None else _topdown_ee_quat_xyzw(0.0),
            approach=list(approach) if approach is not None else [0.0, 0.0, -1.0],
            width=float(width),
            score=float(score),
            source=source,
            object_name=object_name,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class PoseCandidate:
    pos: List[float]
    quat: List[float]
    score: float
    kind: str
    source: str = "sim_truth_proxy"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "pos": list(self.pos),
            "quat": list(self.quat),
            "score": float(self.score),
            "kind": self.kind,
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_point(
        cls,
        point: np.ndarray,
        score: float,
        kind: str,
        source: str = "sim_truth_proxy",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "PoseCandidate":
        return cls(
            pos=np.asarray(point, dtype=np.float32)[:3].astype(float).tolist(),
            quat=[1.0, 0.0, 0.0, 0.0],
            score=float(score),
            kind=kind,
            source=source,
            metadata=dict(metadata or {}),
        )

@dataclass
class TAMPObject:
    name: str
    pos: List[float]
    radius: float
    height: float
    role: str
    quat: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    half_extents: List[float] = field(default_factory=list)
    mesh_path: Optional[str] = None
    geometry: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "pos": self.pos,
            "quat": self.quat,
            "radius": self.radius,
            "height": self.height,
            "role": self.role,
            "half_extents": self.half_extents,
            "mesh_path": self.mesh_path,
            "geometry": self.geometry,
        }


def _float_list(value: Any, *, default: Iterable[float], length: int) -> List[float]:
    try:
        raw = list(value)
    except TypeError:
        raw = []
    out = [float(item) for item in list(default)[:length]]
    for idx, item in enumerate(raw[:length]):
        try:
            out[idx] = float(item)
        except (TypeError, ValueError):
            continue
    while len(out) < length:
        out.append(0.0)
    return out[:length]


def _float_value(value: Any, *, default: float, label: str) -> float:
    if value in (None, ""):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid geometry descriptor {label}: {value!r}") from exc


def _descriptor_half_extents(descriptor: Mapping[str, Any], shape: str) -> List[float]:
    if isinstance(descriptor.get("half_extents"), (list, tuple)):
        half_extents = _float_list(descriptor.get("half_extents"), default=[0.03, 0.03, 0.005], length=3)
    elif isinstance(descriptor.get("size"), (list, tuple)):
        size = _float_list(descriptor.get("size"), default=[0.06, 0.06, 0.010], length=3)
        half_extents = [0.5 * max(value, 1e-5) for value in size]
    elif shape == "sphere":
        radius = max(_float_value(descriptor.get("radius"), default=0.03, label="radius"), 1e-5)
        half_extents = [radius, radius, radius]
    elif shape == "cylinder":
        radius = max(_float_value(descriptor.get("radius"), default=0.03, label="radius"), 1e-5)
        height = max(_float_value(descriptor.get("height"), default=0.010, label="height"), 1e-5)
        half_extents = [radius, radius, 0.5 * height]
    else:
        half_extents = [0.03, 0.03, 0.005]
    return [max(float(value), 1e-5) for value in half_extents[:3]]


def _virtual_surface_from_descriptor(
    name: str,
    descriptor: Mapping[str, Any],
    *,
    default_kind: str = "virtual_surface_descriptor",
) -> TAMPObject:
    shape = canonical_geometry_descriptor_shape(descriptor.get("shape")) or "box"
    half_extents = _descriptor_half_extents(descriptor, shape)
    center = _float_list(
        descriptor.get("center", descriptor.get("pos")),
        default=[0.0, 0.0, half_extents[2]],
        length=3,
    )
    quat = _float_list(descriptor.get("quat"), default=[1.0, 0.0, 0.0, 0.0], length=4)
    radius = _float_value(
        descriptor.get("radius"),
        default=float(np.linalg.norm(np.asarray(half_extents[:2], dtype=np.float64))),
        label="radius",
    )
    height = _float_value(descriptor.get("height"), default=2.0 * half_extents[2], label="height")
    metadata = dict(descriptor.get("metadata") or {}) if isinstance(descriptor.get("metadata"), Mapping) else {}
    affordances = descriptor.get("affordances", metadata.get("affordances"))
    if isinstance(affordances, (list, tuple)):
        metadata["affordances"] = [str(item) for item in affordances if str(item)]
    else:
        metadata.setdefault("affordances", ["surface", "placement_region"])
    if "surface" not in metadata["affordances"]:
        metadata["affordances"].insert(0, "surface")
    metadata.setdefault("category", "surface")
    metadata.setdefault("geometry_descriptor_shape", shape)
    if descriptor.get("planner_primitive"):
        metadata.setdefault("planner_primitive", str(descriptor.get("planner_primitive")))
    if descriptor.get("coordinate_frame"):
        metadata.setdefault("coordinate_frame", str(descriptor.get("coordinate_frame")))
    inner_bounds = descriptor.get("inner_bounds")
    if isinstance(inner_bounds, Mapping):
        metadata["inner_bounds"] = dict(inner_bounds)
        if descriptor.get("inner_bounds_coordinate_frame"):
            metadata.setdefault("inner_bounds_coordinate_frame", str(descriptor.get("inner_bounds_coordinate_frame")))
    geometry = {
        "kind": str(descriptor.get("kind") or default_kind),
        "shape": shape,
        "center": center,
        "radius": radius,
        "height": height,
        "half_extents": half_extents,
        "mesh_path": descriptor.get("mesh_path"),
        "source": str(descriptor.get("source") or "skill_geometry_descriptor"),
        "metadata": metadata,
    }
    return TAMPObject(
        name=name,
        pos=center,
        radius=radius,
        height=height,
        role=str(descriptor.get("role") or "surface"),
        quat=quat,
        half_extents=half_extents,
        mesh_path=str(descriptor.get("mesh_path") or "") or None,
        geometry=geometry,
    )


@dataclass
class TAMPProblem:
    movables: List[TAMPObject]
    surfaces: List[TAMPObject]
    statics: List[TAMPObject]
    goal_atoms: List[GroundedAtom]
    init_atoms: List[Dict[str, Any]] = field(default_factory=list)
    required_final_atoms: List[Dict[str, Any]] = field(default_factory=list)
    fluent_mapping: Dict[str, Any] = field(default_factory=dict)
    action_schemas: List[ActionSchema] = field(default_factory=list)
    grasps: Dict[str, List[GraspCandidate]] = field(default_factory=dict)
    place_candidates: Dict[str, np.ndarray] = field(default_factory=dict)
    retreat_candidates: List[PoseCandidate] = field(default_factory=list)
    table_z: float = 0.78
    table_geometry: Dict[str, object] = field(default_factory=dict)
    q_init: Optional[List[float]] = None
    q_init_debug: Dict[str, Any] = field(default_factory=dict)
    current_grasp: Optional[Dict[str, Any]] = None

    def grasp_points(self, object_name: str) -> np.ndarray:
        candidates = self.grasps.get(object_name, [])
        if not candidates:
            return np.empty((0, 3), dtype=np.float32)
        candidates = sorted(candidates, key=lambda item: item.score, reverse=True)
        return np.asarray([candidate.pos[:3] for candidate in candidates], dtype=np.float32)

    def retreat_points(self) -> np.ndarray:
        if not self.retreat_candidates:
            return np.empty((0, 3), dtype=np.float32)
        candidates = sorted(self.retreat_candidates, key=lambda item: item.score, reverse=True)
        return np.asarray([candidate.pos[:3] for candidate in candidates], dtype=np.float32)

    def to_dict(self) -> Dict[str, object]:
        return {
            "movables": [obj.to_dict() for obj in self.movables],
            "surfaces": [obj.to_dict() for obj in self.surfaces],
            "statics": [obj.to_dict() for obj in self.statics],
            "goal_atoms": [atom.to_dict() for atom in self.goal_atoms],
            "init_atoms": list(self.init_atoms),
            "required_final_atoms": list(self.required_final_atoms),
            "fluent_mapping": dict(self.fluent_mapping),
            "action_schemas": [schema.to_dict() for schema in self.action_schemas],
            "grasp_counts": {k: int(len(v)) for k, v in self.grasps.items()},
            "grasp_candidates": {k: [candidate.to_dict() for candidate in sorted(v, key=lambda item: item.score, reverse=True)] for k, v in self.grasps.items()},
            "place_candidate_counts": {k: int(len(v)) for k, v in self.place_candidates.items()},
            "place_candidates": {k: np.asarray(v, dtype=np.float32).astype(float).tolist() for k, v in self.place_candidates.items()},
            "retreat_candidate_count": int(len(self.retreat_candidates)),
            "retreat_candidates": [candidate.to_dict() for candidate in sorted(self.retreat_candidates, key=lambda item: item.score, reverse=True)],
            "table_z": self.table_z,
            "table_geometry": self.table_geometry,
            "q_init": list(self.q_init) if self.q_init is not None else None,
            "q_init_debug": dict(self.q_init_debug),
            "current_grasp": copy.deepcopy(self.current_grasp),
        }


def _estimate_table_z(scene: SceneState) -> float:
    return estimate_table_z(scene)


def _estimate_radius(obj: ObjectState, scene: SceneState) -> float:
    return estimate_object_radius(obj, scene)


def _is_robot_mount_object(name: str) -> bool:
    low = str(name).lower()
    return low.startswith("mount0_") or low.startswith("robot0_") or "pedestal" in low


def _robot_base_origin(scene: SceneState) -> Optional[np.ndarray]:
    pose = robot_base_pose(scene)
    return None if pose is None else pose[0].astype(np.float32)


def _shift_geometry_to_robot_base(
    geometry: Dict[str, Any], base_position: np.ndarray, base_quat_wxyz: np.ndarray
) -> Dict[str, Any]:
    out = copy.deepcopy(dict(geometry or {}))

    def shift_pose_record(record: Dict[str, Any]) -> None:
        pos = np.asarray(record.get("pos"), dtype=np.float32).reshape(-1) if "pos" in record else np.zeros(0)
        if pos.size >= 3:
            record["pos"] = world_to_base_position(pos[:3], base_position, base_quat_wxyz).astype(float).tolist()
        quat = np.asarray(record.get("quat", []), dtype=np.float64).reshape(-1)
        if quat.size >= 4:
            record["quat"] = world_to_base_quat_wxyz(quat[:4], base_quat_wxyz).astype(float).tolist()

    seen: set[int] = set()

    def shift_pose_records(records: Any) -> None:
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict):
                continue
            record_id = id(record)
            if record_id in seen:
                continue
            seen.add(record_id)
            shift_pose_record(record)

    shift_pose_records(out.get("geoms"))
    shift_pose_records(out.get("sites"))
    metadata = out.get("metadata")
    if isinstance(metadata, dict):
        shift_pose_records(metadata.get("sites"))
        shift_pose_records(metadata.get("containment_sites"))
    return out


def _scene_in_robot_base_frame(scene: SceneState) -> SceneState:
    base_pose = robot_base_pose(scene)
    if base_pose is None:
        return scene
    base_position, base_quat_wxyz, base_source = base_pose
    objects: Dict[str, ObjectState] = {}
    for name, obj in scene.objects.items():
        if _is_robot_mount_object(name):
            continue
        objects[name] = ObjectState(
            name=obj.name,
            pos=world_to_base_position(obj.pos[:3], base_position, base_quat_wxyz).astype(np.float32),
            quat=(
                world_to_base_quat_wxyz(obj.quat, base_quat_wxyz).astype(np.float32)
                if obj.quat is not None and np.asarray(obj.quat).size >= 4
                else None
            ),
            geometry=_shift_geometry_to_robot_base(obj.geometry, base_position, base_quat_wxyz),
        )
    robot_joint_debug = copy.deepcopy(dict(scene.robot_joint_debug))
    robot_joint_debug["world_to_planner_frame"] = {
        "method": "full_se3_inverse_robot_base",
        "base_source": base_source,
        "origin_world": base_position.astype(float).tolist(),
        "quat_world_wxyz": base_quat_wxyz.astype(float).tolist(),
        "rotation_applied": True,
    }
    eef_quat_base_wxyz = world_to_base_quat_wxyz(xyzw_to_wxyz(scene.ee_quat), base_quat_wxyz)
    robot_joint_debug["planner_input_eef"] = {
        "pos": world_to_base_position(scene.ee_pos[:3], base_position, base_quat_wxyz).astype(float).tolist(),
        "quat_xyzw": wxyz_to_xyzw(eef_quat_base_wxyz).astype(float).tolist(),
        "source_frame": "libero_grip_site",
        "target_frame": "robot0_base",
    }
    return SceneState(
        ee_pos=world_to_base_position(scene.ee_pos[:3], base_position, base_quat_wxyz).astype(np.float32),
        ee_quat=wxyz_to_xyzw(eef_quat_base_wxyz).astype(np.float32),
        gripper_qpos=scene.gripper_qpos.copy(),
        robot_qpos=scene.robot_qpos.copy(),
        objects=objects,
        joints=scene.joints,
        robot_joint_debug=robot_joint_debug,
        contacts=copy.deepcopy(scene.contacts),
        holding_evidence=copy.deepcopy(scene.holding_evidence),
        raw_obs_keys=scene.raw_obs_keys,
    )


def _pose_matrix(pos: np.ndarray, quat_xyzw: np.ndarray) -> np.ndarray:
    out = np.eye(4, dtype=np.float64)
    out[:3, :3] = quat_wxyz_to_matrix(xyzw_to_wxyz(quat_xyzw))
    out[:3, 3] = np.asarray(pos, dtype=np.float64)[:3]
    return out


def _reconstruct_current_grasp(scene: SceneState) -> Optional[Dict[str, Any]]:
    evidence = dict(scene.holding_evidence or {})
    object_name = evidence.get("object_name")
    obj = scene.objects.get(str(object_name)) if object_name is not None else None
    if evidence.get("status") != "holding" or obj is None or obj.quat is None:
        return None
    object_quat = np.asarray(obj.quat, dtype=np.float64).reshape(-1)
    if object_quat.size < 4:
        return None
    base_from_object = _pose_matrix(obj.pos[:3], wxyz_to_xyzw(object_quat[:4]))
    return {
        "object_name": str(object_name),
        "symbol": "grasp0",
        "source": "sim_truth_holding_object_pose",
        "confidence": float(evidence.get("confidence", 0.0)),
        "base_from_object_matrix": base_from_object.astype(float).tolist(),
        "note": (
            "This layer only identifies the held object and records its simulator-truth pose. "
            "The cuTAMP object_from_grasp value must be reconstructed from q_init FK and "
            "the runtime tool_from_ee transform inside the planning backend."
        ),
    }


def _make_object(obj: ObjectState, scene: SceneState, role: str) -> TAMPObject:
    geometry = estimate_object_geometry(obj, scene)
    return TAMPObject(
        name=obj.name,
        pos=obj.pos[:3].astype(float).tolist(),
        radius=geometry.radius,
        height=geometry.height,
        role=role,
        quat=(
            np.asarray(obj.quat, dtype=np.float32).reshape(-1)[:4].astype(float).tolist()
            if obj.quat is not None and np.asarray(obj.quat).size >= 4
            else [1.0, 0.0, 0.0, 0.0]
        ),
        half_extents=list(geometry.half_extents),
        mesh_path=geometry.mesh_path,
        geometry=geometry.to_dict(),
    )


def _topdown_grasp_candidates(obj: ObjectState, scene: SceneState) -> List[GraspCandidate]:
    geometry = estimate_object_geometry(obj, scene)
    radius = max(float(geometry.radius), _estimate_radius(obj, scene))
    width = float(np.clip(2.2 * radius, 0.025, 0.085))
    offsets = np.array(
        [
            [0.0, 0.0, 0.035],
            [0.45 * radius, 0.0, 0.04],
            [-0.45 * radius, 0.0, 0.04],
            [0.0, 0.45 * radius, 0.04],
            [0.0, -0.45 * radius, 0.04],
            [0.32 * radius, 0.32 * radius, 0.045],
            [0.32 * radius, -0.32 * radius, 0.045],
            [-0.32 * radius, 0.32 * radius, 0.045],
            [-0.32 * radius, -0.32 * radius, 0.045],
        ],
        dtype=np.float32,
    )
    yaws = (0.0, 0.5 * np.pi, np.pi, -0.5 * np.pi)
    points = obj.pos[:3].astype(np.float32)[None, :] + offsets
    points[:, 2] = np.maximum(points[:, 2], _estimate_table_z(scene) + 0.035)
    center = obj.pos[:3].astype(np.float32)
    candidates: List[GraspCandidate] = []
    rank = 0
    for point in points:
        lateral = float(np.linalg.norm(point[:2] - center[:2]))
        height_penalty = abs(float(point[2] - center[2]) - 0.04)
        for yaw in yaws:
            score = float(np.clip(0.92 - 2.0 * lateral - 0.75 * height_penalty - 0.02 * abs(yaw), 0.15, 0.95))
            candidates.append(
                GraspCandidate.from_point(
                    obj.name,
                    point,
                    width=width,
                    score=score,
                    quat=_topdown_ee_quat_xyzw(float(yaw)),
                    metadata={
                        "rank": rank,
                        "yaw": float(yaw),
                        "geometry_kind": geometry.kind,
                        "radius": geometry.radius,
                        "height": geometry.height,
                        "sampler": "topdown_proxy",
                    },
                )
            )
            rank += 1
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def _grasp_dims_for_profile(obj: ObjectState, scene: SceneState, geometry: Any) -> List[float]:
    he = np.asarray(geometry.half_extents, dtype=np.float32).reshape(-1)
    if he.size >= 3:
        return (2.0 * np.maximum(he[:3], 1e-4)).astype(float).tolist()
    radius = max(float(geometry.radius), _estimate_radius(obj, scene))
    height = max(float(geometry.height), 0.04)
    return [2.0 * radius, 2.0 * radius, height]


def _object_pose7_wxyz(obj: ObjectState) -> List[float]:
    quat = np.asarray(obj.quat if obj.quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=np.float64).reshape(-1)
    if quat.size < 4:
        quat = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    return [*obj.pos[:3].astype(float).tolist(), *quat[:4].astype(float).tolist()]


def _shared_profile_grasp_candidates(
    obj: ObjectState,
    scene: SceneState,
    profile: str,
    registry: GraspProfileRegistry | None = None,
) -> List[GraspCandidate]:
    try:
        normalized = normalize_grasp_sampler_profile(profile, registry=registry)
        if is_native_grasp_sampler_profile(normalized, registry=registry):
            return _topdown_grasp_candidates(obj, scene)
    except ValueError:
        return _topdown_grasp_candidates(obj, scene)

    geometry = estimate_object_geometry(obj, scene)
    dims = _grasp_dims_for_profile(obj, scene, geometry)
    pose = _object_pose7_wxyz(obj)
    world_from_obj = pose7_rotation_matrix(pose)
    center = obj.pos[:3].astype(np.float64)
    rim = is_hollow_vessel(obj.name) or str(geometry.kind).lower() == "mesh"
    samples = sample_grasp_profile(normalized, dims, rim=rim, pose=pose, registry=registry)
    if not samples:
        return _topdown_grasp_candidates(obj, scene)

    width = profile_gripper_width(
        normalized,
        dims,
        rim=rim,
        radius=max(float(geometry.radius), _estimate_radius(obj, scene)),
        pose=pose,
        registry=registry,
    )
    table_min_z = _estimate_table_z(scene) + 0.035
    candidates: List[GraspCandidate] = []
    for rank, sample in enumerate(samples):
        local_xyz = np.asarray(sample.xyz, dtype=np.float64)
        point = center + world_from_obj @ local_xyz
        point[2] = max(float(point[2]), table_min_z)
        yaw = float(sample.metadata.get("world_yaw", sample.rpy[2]))
        metadata = {
            "rank": rank,
            "yaw": yaw,
            "geometry_kind": geometry.kind,
            "sampler": normalized,
            "local_xyz": local_xyz.astype(float).tolist(),
            "local_rpy": [float(value) for value in sample.rpy],
        }
        metadata.update(dict(sample.metadata))
        score = float(np.clip(0.93 - 0.006 * rank, 0.18, 0.94))
        candidates.append(
            GraspCandidate.from_point(
                obj.name,
                point.astype(np.float32),
                width=width,
                score=score,
                quat=_topdown_ee_quat_xyzw(yaw),
                metadata=metadata,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def _mug_body_side_grasp_candidates(obj: ObjectState, scene: SceneState) -> List[GraspCandidate]:
    return _shared_profile_grasp_candidates(obj, scene, "mug_body_side_avoid_handle_v1")


def _small_shallow_bowl_grasp_candidates(obj: ObjectState, scene: SceneState) -> List[GraspCandidate]:
    return _shared_profile_grasp_candidates(obj, scene, "bowl_rim_small_shallow_diagonal_topdown_v1")


def _flat_box_topdown_short_side_grasp_candidates(obj: ObjectState, scene: SceneState) -> List[GraspCandidate]:
    return _shared_profile_grasp_candidates(obj, scene, "flat_box_topdown_short_side_v1")


def _can_body_lower_side_grasp_candidates(obj: ObjectState, scene: SceneState) -> List[GraspCandidate]:
    return _shared_profile_grasp_candidates(obj, scene, "can_body_lower_side_v1")


def _grasp_profile_from_hints(recovery_hints: Mapping[str, Any] | None) -> str:
    if not isinstance(recovery_hints, Mapping):
        return ""
    return str(recovery_hints.get("grasp_profile") or recovery_hints.get("grasp_sampler_profile") or "")


def _grasp_candidates_for_profile(
    obj: ObjectState,
    scene: SceneState,
    profile: str,
    registry: GraspProfileRegistry | None = None,
) -> List[GraspCandidate]:
    if profile:
        return _shared_profile_grasp_candidates(obj, scene, profile, registry=registry)
    return _topdown_grasp_candidates(obj, scene)


def _placement_candidates(surface: ObjectState, scene: SceneState) -> np.ndarray:
    geometry = estimate_object_geometry(surface, scene).to_dict()
    inner = geometry.get("metadata", {}).get("inner_bounds") if isinstance(geometry.get("metadata"), dict) else None
    if inner:
        x_min, x_max = float(inner["x_min"]), float(inner["x_max"])
        y_min, y_max = float(inner["y_min"]), float(inner["y_max"])
        z = float(inner["z_min"]) + 0.12
        pts = np.array(
            [
                [(x_min + x_max) * 0.5, (y_min + y_max) * 0.5, z],
                [x_min * 0.65 + x_max * 0.35, (y_min + y_max) * 0.5, z],
                [x_min * 0.35 + x_max * 0.65, (y_min + y_max) * 0.5, z],
                [(x_min + x_max) * 0.5, y_min * 0.65 + y_max * 0.35, z],
                [(x_min + x_max) * 0.5, y_min * 0.35 + y_max * 0.65, z],
            ],
            dtype=np.float32,
        )
        return pts
    radius = max(float(geometry.get("radius", _estimate_radius(surface, scene))), 0.055)
    offsets = np.array(
        [
            [0.0, 0.0, 0.16],
            [0.45 * radius, 0.0, 0.16],
            [-0.45 * radius, 0.0, 0.16],
            [0.0, 0.45 * radius, 0.16],
            [0.0, -0.45 * radius, 0.16],
        ],
        dtype=np.float32,
    )
    out = surface.pos[:3].astype(np.float32)[None, :] + offsets
    out[:, 2] = np.maximum(out[:, 2], _estimate_table_z(scene) + 0.14)
    return out


def _retreat_candidates(scene: SceneState) -> List[PoseCandidate]:
    table_z = _estimate_table_z(scene)
    ee = scene.ee_pos[:3].astype(np.float32)
    offsets = np.array(
        [
            [0.0, 0.0, 0.16],
            [0.0, -0.12, 0.13],
            [0.0, 0.12, 0.13],
            [-0.12, 0.0, 0.13],
            [0.12, 0.0, 0.13],
            [0.0, -0.18, 0.18],
            [0.0, 0.18, 0.18],
        ],
        dtype=np.float32,
    )
    points = ee[None, :] + offsets
    points[:, 2] = np.maximum(points[:, 2], table_z + 0.20)
    candidates: List[PoseCandidate] = []
    for idx, point in enumerate(points):
        motion = float(np.linalg.norm(point - ee))
        score = float(np.clip(0.95 - 0.8 * motion - 0.03 * idx, 0.1, 0.95))
        candidates.append(
            PoseCandidate.from_point(
                point,
                score=score,
                kind="retreat_pose",
                metadata={"rank": idx, "motion_from_ee": motion, "sampler": "ee_lift_back_proxy"},
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def _hint_params(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(recovery_hints, Mapping):
        return {}
    params = recovery_hints.get("params")
    return dict(params) if isinstance(params, Mapping) else {}


def _placement_region_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    hints = _hint_params(recovery_hints).get("geometry_hints")
    if not isinstance(hints, Mapping):
        return {}
    region = hints.get("placement_region")
    return dict(region) if isinstance(region, Mapping) else {}


def _geometry_hint_mappings(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    hints = _hint_params(recovery_hints).get("geometry_hints")
    if not isinstance(hints, Mapping):
        return {}
    return {
        str(key): dict(value)
        for key, value in hints.items()
        if isinstance(value, Mapping)
    }


_GEOMETRY_RUNTIME_ADAPTER_CACHE: Dict[str, Any] = {}
_GEOMETRY_RUNTIME_ADAPTER_WARNED: set[Tuple[str, str, str]] = set()


def _load_geometry_runtime_adapter(path: str) -> Any:
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    cached = _GEOMETRY_RUNTIME_ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not resolved.exists():
        raise FileNotFoundError(f"geometry profile runtime adapter does not exist: {resolved}")
    module_name = f"_tiptop_geometry_runtime_adapter_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load geometry profile runtime adapter: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _GEOMETRY_RUNTIME_ADAPTER_CACHE[cache_key] = module
    return module


def _adapter_inner_floor_bounds(
    *,
    proxy_name: str,
    source: ObjectState,
    scene: SceneState,
    hint: Mapping[str, Any],
    compartment: str,
    source_geometry: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    path = str(hint.get("geometry_profile_adapter_path") or "").strip()
    profile = str(hint.get("geometry_profile") or "").strip()
    if not path or not profile:
        return None
    module = _load_geometry_runtime_adapter(path)
    resolver = getattr(module, "resolve_inner_floor_bounds", None)
    if not callable(resolver):
        return None
    result = resolver(
        profile,
        source=source,
        scene=scene,
        hint=copy.deepcopy(dict(hint)),
        proxy_name=proxy_name,
        compartment=compartment,
        source_geometry=copy.deepcopy(dict(source_geometry)),
    )
    if not isinstance(result, Mapping):
        return None
    required = ("x_min", "x_max", "y_min", "y_max", "support_z")
    if not all(key in result for key in required):
        return None
    out = dict(result)
    out.setdefault("geometry_profile", profile)
    out.setdefault("geometry_profile_adapter_path", path)
    return out


def _adapter_fixed_table_rect_bounds(
    *,
    region_name: str,
    table_geometry: Mapping[str, Any],
    scene: SceneState | None,
    task: ParsedTask | None,
    hint: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    path = str(hint.get("geometry_profile_adapter_path") or "").strip()
    profile = str(hint.get("geometry_profile") or "").strip()
    if not path or not profile:
        return None
    module = _load_geometry_runtime_adapter(path)
    resolver = getattr(module, "resolve_table_rect", None)
    if not callable(resolver):
        return None
    result = resolver(
        profile,
        region_name=region_name,
        table_geometry=copy.deepcopy(dict(table_geometry)),
        scene=scene,
        task=task,
        hint=copy.deepcopy(dict(hint)),
    )
    if not isinstance(result, Mapping):
        return None
    bounds = result.get("bounds")
    if not isinstance(bounds, Mapping):
        bounds = result
    required = ("x_min", "x_max", "y_min", "y_max")
    if not all(key in bounds for key in required):
        return None
    try:
        out = {
            "bounds": {key: float(bounds[key]) for key in required},
            "metadata": dict(result.get("metadata") or {}) if isinstance(result.get("metadata"), Mapping) else {},
        }
    except (TypeError, ValueError):
        return None
    out["metadata"].setdefault("geometry_profile", profile)
    out["metadata"].setdefault("geometry_profile_adapter_path", path)
    return out


def _surface_descriptor_applies(surface_name: str, hint_key: str, hint: Mapping[str, Any]) -> bool:
    for key in ("surface_name", "region_name", "proxy_name"):
        value = str(hint.get(key) or "").strip()
        if value and value == surface_name:
            return True
    patterns = hint.get("surface_name_matches") or hint.get("region_name_matches") or hint.get("proxy_name_matches")
    if patterns and _matches_name_or_regex(surface_name, patterns):
        return True
    return hint_key == surface_name


def _adapter_virtual_surface_descriptor(
    *,
    surface_name: str,
    scene: SceneState,
    task: ParsedTask,
    table_geometry: Mapping[str, Any],
    recovery_hints: Mapping[str, Any] | None,
) -> Optional[TAMPObject]:
    for hint_key, hint in _geometry_hint_mappings(recovery_hints).items():
        descriptor = hint.get("surface_descriptor")
        if isinstance(descriptor, Mapping) and _surface_descriptor_applies(surface_name, hint_key, hint):
            payload = dict(descriptor)
            payload.setdefault("name", surface_name)
            payload.setdefault("source", "skill_geometry_hint_surface_descriptor")
            metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {}
            metadata.setdefault("geometry_hint_key", hint_key)
            metadata.setdefault("geometry_profile", str(hint.get("geometry_profile") or ""))
            payload["metadata"] = metadata
            return _virtual_surface_from_descriptor(surface_name, payload)

        path = str(hint.get("geometry_profile_adapter_path") or "").strip()
        profile = str(hint.get("geometry_profile") or "").strip()
        if not path or not profile:
            continue
        module = _load_geometry_runtime_adapter(path)
        resolver = getattr(module, "resolve_surface_descriptor", None)
        if not callable(resolver):
            continue
        result = resolver(
            profile,
            surface_name=surface_name,
            scene=scene,
            task=task,
            table_geometry=copy.deepcopy(dict(table_geometry)),
            hint=copy.deepcopy(dict(hint)),
            hint_key=hint_key,
        )
        if not isinstance(result, Mapping):
            continue
        payload = dict(result)
        payload.setdefault("name", surface_name)
        payload.setdefault("source", "skill_geometry_adapter_surface_descriptor")
        metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {}
        metadata.setdefault("geometry_profile", profile)
        metadata.setdefault("geometry_profile_adapter_path", path)
        metadata.setdefault("geometry_hint_key", hint_key)
        payload["metadata"] = metadata
        return _virtual_surface_from_descriptor(surface_name, payload)
    return None


def _expects_inner_floor_runtime_adapter(source: ObjectState, hint: Mapping[str, Any], compartment: str) -> bool:
    source_name = str(getattr(source, "name", "") or "").strip().lower()
    profile = str(hint.get("geometry_profile") or "").strip().lower()
    intent = str(hint.get("intent") or "").strip().lower()
    primitive = _geometry_planner_primitive(hint)
    if "desk_caddy" not in source_name:
        return False
    if profile == "desk_caddy_compartment_inner_floor_v1":
        return True
    return bool(
        primitive == "inner_floor"
        and intent == "compartment_inner_floor"
        and compartment in {"front", "back", "left", "right"}
    )


def _warn_missing_inner_floor_adapter(proxy_name: str, source: ObjectState, hint: Mapping[str, Any]) -> None:
    profile = str(hint.get("geometry_profile") or "").strip()
    path = str(hint.get("geometry_profile_adapter_path") or "").strip()
    key = (str(getattr(source, "name", "") or ""), str(proxy_name), profile)
    if key in _GEOMETRY_RUNTIME_ADAPTER_WARNED:
        return
    _GEOMETRY_RUNTIME_ADAPTER_WARNED.add(key)
    logger.warning(
        "desk_caddy geometry hint is using generic inner-floor fallback without a runtime adapter: "
        "proxy=%s source=%s geometry_profile=%s adapter_path=%s",
        proxy_name,
        key[0],
        profile,
        path,
    )


def _geometry_planner_primitive(hint: Mapping[str, Any]) -> str:
    return canonical_geometry_planner_primitive(hint)


def _fixed_table_rect_region_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    hint = _placement_region_hint(recovery_hints)
    if _geometry_planner_primitive(hint) != "fixed_table_rect":
        return {}
    if not str(hint.get("region_name") or "").strip() and not (
        hint.get("region_name_from_bddl_goal") or hint.get("bounds_from_bddl_region")
    ):
        return {}
    return hint


def _fixed_table_rect_region_name(hint: Mapping[str, Any]) -> Optional[str]:
    name = str(hint.get("region_name") or "").strip()
    return name or None


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


def _bddl_goal_surface_names(task: ParsedTask | None) -> List[str]:
    if task is None:
        return []
    diagnostics = dict(task.diagnostics or {})
    surfaces: List[str] = []
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
    out: List[str] = []
    seen = set()
    for surface in surfaces:
        if surface in seen:
            continue
        seen.add(surface)
        out.append(surface)
    return out


def _fixed_table_rect_region_applies(
    region_name: str,
    hint: Mapping[str, Any],
    task: ParsedTask | None,
) -> bool:
    fixed_name = _fixed_table_rect_region_name(hint)
    if fixed_name:
        return region_name == fixed_name
    if not (hint.get("region_name_from_bddl_goal") or hint.get("bounds_from_bddl_region")):
        return False
    if region_name not in _bddl_goal_surface_names(task):
        return False
    patterns = (
        hint.get("bddl_goal_surface_matches")
        or hint.get("region_name_matches")
        or hint.get("source_region_matches")
    )
    return not patterns or _matches_name_or_regex(region_name, patterns)


_COMPARTMENT_TOKENS = ("front", "back", "left", "right", "middle", "center")


def _compartment_from_region_name(region_name: str, hint: Mapping[str, Any] | None = None) -> str:
    if isinstance(hint, Mapping):
        raw = str(hint.get("compartment") or "").strip().lower()
        if raw:
            return raw
    low = str(region_name or "").lower()
    for token in _COMPARTMENT_TOKENS:
        if f"_{token}_" in low or low.endswith(f"_{token}"):
            return token
    return ""


def _placement_region_source_name(region_name: str, hint: Mapping[str, Any]) -> Optional[str]:
    suffix = str(hint.get("proxy_suffix") or "inner_floor").strip("_") or "inner_floor"
    marker = f"_{suffix}"
    if not region_name.endswith(marker):
        return None
    source = region_name[: -len(marker)]
    compartment = _compartment_from_region_name(region_name, hint)
    if compartment and source.endswith(f"_{compartment}"):
        source = source[: -(len(compartment) + 1)]
    return source


def _apply_normalized_xy_crop(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    fraction: Mapping[str, Any],
) -> Tuple[float, float, float, float]:
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


def _clamped_float_hint(mapping: Mapping[str, Any], key: str, default: float, lo: float, hi: float) -> float:
    value = _float_hint(mapping, key, default)
    return float(max(lo, min(hi, value)))


def _place_candidate_policy(hint: Mapping[str, Any]) -> str:
    raw = str(hint.get("place_candidate_policy") or "").strip().lower()
    policy = canonical_place_candidate_policy(raw)
    if raw and not policy:
        raise ValueError(f"unsupported place_candidate_policy: {raw}")
    return policy


def _place_yaw_policy(hint: Mapping[str, Any]) -> str:
    raw = str(hint.get("place_yaw_policy") or "").strip().lower()
    policy = canonical_place_yaw_policy(raw)
    if raw and not policy:
        raise ValueError(f"unsupported place_yaw_policy: {raw}")
    if policy == "world_z_thin_x":
        return "thin_horizontal_along_world_x"
    return policy


def _high_drop_release_mode(hint: Mapping[str, Any]) -> str:
    mode = str(hint.get("release_mode") or "").strip().lower()
    normalized = canonical_release_mode(mode)
    if mode and not normalized:
        raise ValueError(f"unsupported release_mode: {mode}")
    return normalized


def _entry_xy_for_compartment(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    compartment: str,
    fraction: float,
) -> List[float]:
    fx = 0.5
    fy = 0.5
    frac = max(0.05, min(0.95, float(fraction)))
    if compartment == "front":
        fy = frac
    elif compartment == "back":
        fy = 1.0 - frac
    elif compartment == "left":
        fx = frac
    elif compartment == "right":
        fx = 1.0 - frac
    return [
        float(x_min + (x_max - x_min) * fx),
        float(y_min + (y_max - y_min) * fy),
    ]


def _candidate_ref_xy(metadata: Mapping[str, Any]) -> Optional[np.ndarray]:
    raw = metadata.get("place_candidate_reference_pos")
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return np.asarray([float(raw[0]), float(raw[1])], dtype=np.float64)
    except (TypeError, ValueError):
        return None


def _unique_xyz_points(points: Iterable[List[float]]) -> List[List[float]]:
    unique: List[List[float]] = []
    seen: set[tuple[float, float, float]] = set()
    for point in points:
        if len(point) < 3:
            continue
        normalized = [float(point[0]), float(point[1]), float(point[2])]
        key = tuple(round(value, 6) for value in normalized)
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _inner_floor_place_candidates(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z: float,
    metadata: Mapping[str, Any],
) -> np.ndarray:
    x_min = float(x_min)
    x_max = float(x_max)
    y_min = float(y_min)
    y_max = float(y_max)
    z = float(z)
    center = [0.5 * (x_min + x_max), 0.5 * (y_min + y_max), z]
    policy = str(metadata.get("place_candidate_policy") or "").strip().lower()
    if policy in {
        "farthest_from_reference_with_corners",
        "farthest_from_object_with_corners",
        "reference_clearance_with_corners",
    }:
        margin = max(_float_hint(metadata, "place_candidate_edge_margin_m", 0.0), 0.0)
        if (x_max - x_min) > 2.0 * margin:
            left = x_min + margin
            right = x_max - margin
        else:
            left = x_min
            right = x_max
        if (y_max - y_min) > 2.0 * margin:
            bottom = y_min + margin
            top = y_max - margin
        else:
            bottom = y_min
            top = y_max
        candidates = _unique_xyz_points(
            [
                center,
                [left, center[1], z],
                [right, center[1], z],
                [center[0], bottom, z],
                [center[0], top, z],
                [left, bottom, z],
                [left, top, z],
                [right, bottom, z],
                [right, top, z],
            ]
        )
        ref_xy = _candidate_ref_xy(metadata)
        if ref_xy is not None:
            candidates.sort(
                key=lambda point: (
                    -float(np.linalg.norm(np.asarray(point[:2], dtype=np.float64) - ref_xy)),
                    float(point[0]),
                    float(point[1]),
                )
            )
        max_count = int(max(_float_hint(metadata, "place_candidate_max_count", len(candidates)), 1.0))
        return np.asarray(candidates[:max_count], dtype=np.float32)
    if policy != "center_and_entry_high_drop":
        return np.asarray(
            [
                center,
                [x_min, center[1], z],
                [x_max, center[1], z],
                [center[0], y_min, z],
                [center[0], y_max, z],
            ],
            dtype=np.float32,
        )
    entry_xy = _entry_xy_for_compartment(
        x_min,
        x_max,
        y_min,
        y_max,
        str(metadata.get("compartment") or ""),
        float(metadata.get("place_candidate_entry_fraction", 0.30)),
    )
    candidates = [center]
    entry = [entry_xy[0], entry_xy[1], z]
    if float(np.linalg.norm(np.asarray(entry[:2], dtype=np.float64) - np.asarray(center[:2], dtype=np.float64))) > 1e-4:
        candidates.append(entry)
    return np.asarray(candidates, dtype=np.float32)


def _virtual_inner_floor_surface(
    proxy_name: str,
    source: ObjectState,
    scene: SceneState,
    hint: Mapping[str, Any],
) -> TAMPObject:
    geometry = estimate_object_geometry(source, scene)
    geometry_dict = geometry.to_dict()
    inner = geometry_dict.get("metadata", {}).get("inner_bounds") if isinstance(geometry_dict.get("metadata"), dict) else None
    center = np.asarray(geometry.center, dtype=np.float64).reshape(-1)[:3]
    he = np.asarray(geometry.half_extents, dtype=np.float64).reshape(-1)
    he3 = np.asarray([0.06, 0.06, 0.03], dtype=np.float64)
    he3[: min(3, he.size)] = np.maximum(he[: min(3, he.size)], 1e-4)
    margin = float(hint.get("margin_m", 0.025))
    min_span = float(hint.get("min_span_m", 0.045))
    compartment = _compartment_from_region_name(proxy_name, hint)
    adapter_inner = _adapter_inner_floor_bounds(
        proxy_name=proxy_name,
        source=source,
        scene=scene,
        hint=hint,
        compartment=compartment,
        source_geometry=geometry_dict,
    )
    using_adapter_inner = adapter_inner is not None
    adapter_warning = ""
    if not using_adapter_inner and _expects_inner_floor_runtime_adapter(source, hint, compartment):
        adapter_warning = "desk_caddy_compartment_geometry_adapter_missing"
        _warn_missing_inner_floor_adapter(proxy_name, source, hint)
    if using_adapter_inner:
        inner = adapter_inner
    applied_margin = 0.0 if using_adapter_inner else margin
    if using_adapter_inner:
        x_min = float(adapter_inner.get("x_min", center[0] - he3[0]))
        x_max = float(adapter_inner.get("x_max", center[0] + he3[0]))
        y_min = float(adapter_inner.get("y_min", center[1] - he3[1]))
        y_max = float(adapter_inner.get("y_max", center[1] + he3[1]))
    elif isinstance(inner, Mapping) and inner:
        x_min = float(inner.get("x_min", center[0] - he3[0])) + applied_margin
        x_max = float(inner.get("x_max", center[0] + he3[0])) - applied_margin
        y_min = float(inner.get("y_min", center[1] - he3[1])) + applied_margin
        y_max = float(inner.get("y_max", center[1] + he3[1])) - applied_margin
    else:
        x_min = float(center[0] - he3[0] + margin)
        x_max = float(center[0] + he3[0] - margin)
        y_min = float(center[1] - he3[1] + margin)
        y_max = float(center[1] + he3[1] - margin)
    bounds_fraction = hint.get("compartment_bounds_fraction") or hint.get("bounds_fraction")
    if not using_adapter_inner and isinstance(bounds_fraction, Mapping) and bounds_fraction:
        x_min, x_max, y_min, y_max = _apply_normalized_xy_crop(x_min, x_max, y_min, y_max, bounds_fraction)
    if x_max <= x_min:
        x_min, x_max = float(center[0] - 0.5 * min_span), float(center[0] + 0.5 * min_span)
    if y_max <= y_min:
        y_min, y_max = float(center[1] - 0.5 * min_span), float(center[1] + 0.5 * min_span)
    floor_clearance = float(hint.get("floor_clearance_m", 0.006))
    if isinstance(inner, Mapping) and inner:
        support_z = float(inner.get("support_z", inner.get("z_min", center[2] - he3[2]))) + floor_clearance
    else:
        support_z = float(center[2] - he3[2] + floor_clearance)
    thickness = float(hint.get("thickness_m", 0.010))
    half_extents = [
        max(0.5 * (x_max - x_min), 0.5 * min_span),
        max(0.5 * (y_max - y_min), 0.5 * min_span),
        max(0.5 * thickness, 0.002),
    ]
    proxy_center = [0.5 * (x_min + x_max), 0.5 * (y_min + y_max), support_z - half_extents[2]]
    proxy_geometry = {
        "kind": "virtual_inner_floor",
        "center": proxy_center,
        "radius": float(np.linalg.norm(np.asarray(half_extents[:2], dtype=np.float64))),
        "height": float(2.0 * half_extents[2]),
        "half_extents": half_extents,
        "mesh_path": None,
        "source": "skill_geometry_hint",
        "metadata": {
            "category": "surface",
            "affordances": ["surface", "placement_region", "inner_floor"],
            "planner_primitive": _geometry_planner_primitive(hint) or "inner_floor",
            "source_object": source.name,
            "source_geometry_kind": geometry.kind,
            "compartment": compartment,
            "inner_bounds_source": (
                str(adapter_inner.get("source") or "skill_pack_adapter_inner_floor_bounds")
                if using_adapter_inner
                else "geometry_inner_bounds_or_aabb_crop"
            ),
            "inner_bounds_coordinate_frame": (
                "planner_frame"
                if isinstance(scene.robot_joint_debug.get("world_to_planner_frame"), Mapping)
                else "world"
            ),
            "source_site_name": "" if not using_adapter_inner else str(adapter_inner.get("source_site_name", "")),
            "site_margin_m": (
                _float_hint(adapter_inner, "site_margin_m", 0.0) if using_adapter_inner else applied_margin
            ),
            "floor_clearance_m": floor_clearance,
            "exclude_source_collision": bool(hint.get("exclude_source_collision", False)),
            "exclude_table_collision": bool(hint.get("exclude_table_collision", False)),
            "place_yaw_policy": _place_yaw_policy(hint),
            "place_z_offset_m": _float_hint(hint, "place_z_offset_m", 0.12),
            "place_candidate_policy": _place_candidate_policy(hint),
            "place_candidate_entry_fraction": _clamped_float_hint(hint, "place_candidate_entry_fraction", 0.30, 0.05, 0.95),
            "inner_bounds": {
                "x_min": x_min,
                "x_max": x_max,
                "y_min": y_min,
                "y_max": y_max,
                "z_min": support_z,
                "z_max": support_z + thickness,
                "support_z": support_z,
            },
        },
    }
    if using_adapter_inner:
        metadata = proxy_geometry["metadata"]
        metadata["inner_bounds_adapter"] = str(adapter_inner.get("geometry_profile_adapter") or "")
        metadata["inner_bounds_adapter_path"] = str(adapter_inner.get("geometry_profile_adapter_path") or "")
        metadata["inner_bounds_profile"] = str(adapter_inner.get("geometry_profile") or "")
        if "bounds_fraction" in adapter_inner:
            metadata["bounds_fraction"] = copy.deepcopy(adapter_inner["bounds_fraction"])
    if adapter_warning:
        metadata = proxy_geometry["metadata"]
        metadata["geometry_profile_adapter_warning"] = adapter_warning
        metadata["geometry_profile"] = str(hint.get("geometry_profile") or "")
        metadata["geometry_profile_adapter_path"] = str(hint.get("geometry_profile_adapter_path") or "")
    release_mode = _high_drop_release_mode(hint)
    if release_mode:
        metadata = proxy_geometry["metadata"]
        release_z_offset = _clamped_float_hint(hint, "release_z_offset_m", metadata["place_z_offset_m"], 0.0, 0.20)
        metadata["release_mode"] = release_mode
        metadata["release_z_offset_m"] = release_z_offset
        metadata["release_z_tolerance_m"] = _clamped_float_hint(hint, "release_z_tolerance_m", 0.04, 0.0, 0.10)
        metadata["release_xy_margin_m"] = _clamped_float_hint(hint, "release_xy_margin_m", 0.0, 0.0, 0.05)
        metadata["planner_support_z_m"] = support_z + _clamped_float_hint(
            hint,
            "planner_support_z_offset_m",
            release_z_offset,
            0.0,
            0.20,
        )
        affordances = metadata["affordances"]
        if "high_drop_release" not in affordances:
            affordances.append("high_drop_release")
    return _virtual_surface_from_descriptor(
        proxy_name,
        {
            "shape": "box",
            "kind": proxy_geometry["kind"],
            "center": proxy_center,
            "quat": [1.0, 0.0, 0.0, 0.0],
            "half_extents": half_extents,
            "radius": proxy_geometry["radius"],
            "height": proxy_geometry["height"],
            "source": proxy_geometry["source"],
            "metadata": proxy_geometry["metadata"],
        },
        default_kind="virtual_inner_floor",
    )


def _float_hint(mapping: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(mapping.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _bddl_regions(task: ParsedTask | None) -> Dict[str, Any]:
    if task is None:
        return {}
    diagnostics = task.diagnostics or {}
    regions = diagnostics.get("goal_regions") or diagnostics.get("bddl_regions") or {}
    return dict(regions) if isinstance(regions, Mapping) else {}


def _bddl_region_entry(task: ParsedTask | None, region_name: str) -> Dict[str, Any]:
    regions = _bddl_regions(task)
    entry = regions.get(region_name)
    if isinstance(entry, Mapping):
        return dict(entry)
    suffix = region_name.split("_", 1)[-1] if "_" in region_name else region_name
    entry = regions.get(suffix)
    return dict(entry) if isinstance(entry, Mapping) else {}


def _language_relative_table_region_surface(
    region_name: str,
    table_geometry: Mapping[str, Any],
    scene: SceneState,
    task: ParsedTask | None,
) -> Optional[TAMPObject]:
    entry = _bddl_region_entry(task, region_name)
    if str(entry.get("kind") or "") != "language_relative_table_region":
        return None
    if str(entry.get("relation") or "") != "front":
        return None

    reference_name = str(entry.get("reference_object") or "")
    anchor_name = str(entry.get("front_anchor_object") or "")
    rear_site_name = str(entry.get("rear_anchor_site") or "")
    reference = scene.objects.get(reference_name)
    anchor = scene.objects.get(anchor_name)
    if reference is None or anchor is None or not rear_site_name:
        return None
    rear_sites = [
        site
        for site in (reference.geometry or {}).get("sites") or []
        if isinstance(site, Mapping) and str(site.get("name") or "") == rear_site_name
    ]
    if len(rear_sites) != 1 or rear_sites[0].get("pos") is None:
        return None

    rear_pos = np.asarray(rear_sites[0]["pos"], dtype=np.float64).reshape(-1)[:3]
    anchor_pos = np.asarray(anchor.pos, dtype=np.float64).reshape(-1)[:3]
    front = anchor_pos[:2] - rear_pos[:2]
    norm = float(np.linalg.norm(front))
    if norm <= 1e-6:
        return None
    front /= norm

    site_size = np.asarray(rear_sites[0].get("size") or [0.075, 0.075], dtype=np.float64).reshape(-1)
    positive_xy = [float(value) for value in site_size[:2] if float(value) > 1e-6]
    source_half_extent = min(positive_xy) if positive_xy else 0.075
    half_extent = float(np.clip(0.5 * source_half_extent, 0.03, 0.055))
    clearance = max(0.01, 0.25 * half_extent)
    center_xy = anchor_pos[:2] + front * (half_extent + clearance)

    table_bounds = dict(table_geometry.get("bounds") or {})
    center_xy[0] = float(
        np.clip(
            center_xy[0],
            float(table_bounds.get("x_min", center_xy[0] - half_extent)) + half_extent,
            float(table_bounds.get("x_max", center_xy[0] + half_extent)) - half_extent,
        )
    )
    center_xy[1] = float(
        np.clip(
            center_xy[1],
            float(table_bounds.get("y_min", center_xy[1] - half_extent)) + half_extent,
            float(table_bounds.get("y_max", center_xy[1] + half_extent)) - half_extent,
        )
    )
    support_z = float(table_bounds.get("z", table_geometry.get("center", [0.0, 0.0, 0.0])[2]))
    thickness = 0.010
    bounds = {
        "x_min": float(center_xy[0] - half_extent),
        "x_max": float(center_xy[0] + half_extent),
        "y_min": float(center_xy[1] - half_extent),
        "y_max": float(center_xy[1] + half_extent),
        "z_min": support_z,
        "z_max": support_z + thickness,
        "support_z": support_z,
    }
    return _virtual_surface_from_descriptor(
        region_name,
        {
            "shape": "box",
            "kind": "virtual_language_relative_table_region",
            "center": [float(center_xy[0]), float(center_xy[1]), support_z - 0.5 * thickness],
            "half_extents": [half_extent, half_extent, 0.5 * thickness],
            "planner_primitive": "fixed_table_rect",
            "inner_bounds": bounds,
            "inner_bounds_coordinate_frame": "planner_frame",
            "metadata": {
                "category": "surface",
                "affordances": ["surface", "placement_region", "language_relative_region"],
                "reference_object": reference_name,
                "front_anchor_object": anchor_name,
                "rear_anchor_site": rear_site_name,
                "front_direction_xy": front.astype(float).tolist(),
                "place_z_offset_m": 0.160,
            },
        },
        default_kind="virtual_language_relative_table_region",
    )


def _bddl_region_xy_bounds(entry: Mapping[str, Any]) -> Dict[str, float]:
    values = []
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


def _bddl_region_xy_offset(
    scene: SceneState | None,
    task: ParsedTask | None,
    target_region_entry: Mapping[str, Any],
) -> np.ndarray:
    if scene is None or task is None:
        return np.zeros(2, dtype=np.float64)
    target_surface = str(target_region_entry.get("target") or "")
    offsets: List[np.ndarray] = []
    diagnostics = task.diagnostics or {}
    for atom in diagnostics.get("init_atoms") or diagnostics.get("bddl_init_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred not in {"on", "inside"} or len(args) < 2:
            continue
        if task.target_hint and str(args[0]) == str(task.target_hint):
            continue
        obj = scene.objects.get(str(args[0]))
        if obj is None or obj.pos is None:
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


def _bddl_table_rect_bounds(
    region_name: str,
    hint: Mapping[str, Any],
    scene: SceneState | None,
    task: ParsedTask | None,
) -> tuple[Dict[str, float], Dict[str, Any]]:
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
    scene: SceneState | None,
    *,
    min_span: float,
) -> tuple[float, float, float, float, Dict[str, Any]]:
    policy = str(hint.get("region_crop_policy") or hint.get("bounds_crop_policy") or "").strip().lower()
    if policy not in {"away_from_reference", "farthest_from_reference", "outer_from_reference"}:
        return x_min, x_max, y_min, y_max, {}
    ref_name = str(
        hint.get("region_crop_reference_object")
        or hint.get("bounds_crop_reference_object")
        or hint.get("place_candidate_reference_object")
        or ""
    ).strip()
    metadata: Dict[str, Any] = {
        "region_crop_policy": policy,
        "region_crop_reference_object": ref_name,
        "region_crop_applied": False,
    }
    if scene is None or not ref_name or ref_name not in scene.objects:
        metadata["region_crop_skip_reason"] = "missing_reference_object"
        return x_min, x_max, y_min, y_max, metadata
    ref_xy = np.asarray(scene.objects[ref_name].pos[:2], dtype=np.float64)
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


def _virtual_fixed_table_rect_surface(
    region_name: str,
    table_geometry: Mapping[str, Any],
    hint: Mapping[str, Any],
    scene: SceneState | None = None,
    task: ParsedTask | None = None,
) -> TAMPObject:
    adapter_rect = _adapter_fixed_table_rect_bounds(
        region_name=region_name,
        table_geometry=table_geometry,
        scene=scene,
        task=task,
        hint=hint,
    )
    using_adapter_rect = adapter_rect is not None
    if using_adapter_rect:
        assert adapter_rect is not None
        bounds = dict(adapter_rect["bounds"])
        bddl_metadata = dict(adapter_rect.get("metadata") or {})
    else:
        bounds = hint.get("bounds_m")
        bounds = dict(bounds) if isinstance(bounds, Mapping) else {}
        bddl_metadata: Dict[str, Any] = {}
        bddl_bounds, bddl_metadata = _bddl_table_rect_bounds(region_name, hint, scene, task)
        if bddl_bounds:
            bounds = bddl_bounds
    table_bounds = dict(table_geometry.get("bounds", {}) if isinstance(table_geometry, Mapping) else {})
    table_center = table_geometry.get("center", [0.0, 0.0, 0.0]) if isinstance(table_geometry, Mapping) else [0.0, 0.0, 0.0]
    center = list(table_center) if isinstance(table_center, (list, tuple)) else [0.0, 0.0, 0.0]
    default_x = float(center[0]) if len(center) > 0 else 0.0
    default_y = float(center[1]) if len(center) > 1 else 0.0
    x_min = _float_hint(bounds, "x_min", default_x - 0.05)
    x_max = _float_hint(bounds, "x_max", default_x + 0.05)
    y_min = _float_hint(bounds, "y_min", default_y - 0.05)
    y_max = _float_hint(bounds, "y_max", default_y + 0.05)
    min_span = _float_hint(hint, "min_span_m", 0.045)
    if x_max <= x_min:
        x_min, x_max = default_x - 0.5 * min_span, default_x + 0.5 * min_span
    if y_max <= y_min:
        y_min, y_max = default_y - 0.5 * min_span, default_y + 0.5 * min_span
    if using_adapter_rect:
        crop_metadata = {}
    else:
        x_min, x_max, y_min, y_max, crop_metadata = _crop_bounds_away_from_reference(
            x_min,
            x_max,
            y_min,
            y_max,
            hint,
            scene,
            min_span=min_span,
        )
    support_z = float(table_bounds.get("z", center[2] if len(center) > 2 else 0.0))
    thickness = max(_float_hint(hint, "thickness_m", 0.010), 0.004)
    half_extents = [
        max(0.5 * (x_max - x_min), 0.5 * min_span),
        max(0.5 * (y_max - y_min), 0.5 * min_span),
        0.5 * thickness,
    ]
    proxy_center = [0.5 * (x_min + x_max), 0.5 * (y_min + y_max), support_z - half_extents[2]]
    candidate_metadata: Dict[str, Any] = {}
    for key in (
        "place_candidate_policy",
        "place_candidate_reference_object",
        "place_candidate_edge_margin_m",
        "place_candidate_max_count",
    ):
        if key in hint:
            candidate_metadata[key] = hint[key]
    ref_name = str(candidate_metadata.get("place_candidate_reference_object") or "")
    if ref_name and scene is not None and ref_name in scene.objects:
        candidate_metadata["place_candidate_reference_pos"] = (
            np.asarray(scene.objects[ref_name].pos, dtype=np.float64).reshape(-1)[:3].astype(float).tolist()
        )
    surface_metadata = {
        "category": "surface",
        "affordances": ["surface", "placement_region", "fixed_table_region"],
        "planner_primitive": _geometry_planner_primitive(hint) or "fixed_table_rect",
        "support_surface": str(hint.get("support_surface") or "table"),
        "source_bddl_region": bddl_metadata.get("source_bddl_region", hint.get("source_bddl_region")),
        "source_bddl_qualified_region": bddl_metadata.get("source_bddl_qualified_region", region_name),
        "source_bddl_target": bddl_metadata.get("source_bddl_target", ""),
        "source_bddl_ranges": list(bddl_metadata.get("source_bddl_ranges", hint.get("source_bddl_ranges") or [])),
        "bddl_scene_xy_offset": bddl_metadata.get("bddl_scene_xy_offset", [0.0, 0.0]),
        "place_z_offset_m": _float_hint(hint, "place_z_offset_m", 0.160),
    }
    surface_metadata.update(bddl_metadata)
    surface_metadata.update(crop_metadata)
    surface_metadata.update(candidate_metadata)
    surface_metadata["inner_bounds"] = {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "z_min": support_z,
        "z_max": support_z + thickness,
        "support_z": support_z,
    }
    surface_metadata["inner_bounds_coordinate_frame"] = (
        "planner_frame"
        if scene is not None and isinstance(scene.robot_joint_debug.get("world_to_planner_frame"), Mapping)
        else "world"
    )
    proxy_geometry = {
        "kind": "virtual_fixed_table_rect",
        "center": proxy_center,
        "radius": float(np.linalg.norm(np.asarray(half_extents[:2], dtype=np.float64))),
        "height": float(2.0 * half_extents[2]),
        "half_extents": half_extents,
        "mesh_path": None,
        "source": "skill_geometry_hint",
        "metadata": surface_metadata,
    }
    return _virtual_surface_from_descriptor(
        region_name,
        {
            "shape": "box",
            "kind": proxy_geometry["kind"],
            "center": proxy_center,
            "quat": [1.0, 0.0, 0.0, 0.0],
            "half_extents": half_extents,
            "radius": proxy_geometry["radius"],
            "height": proxy_geometry["height"],
            "source": proxy_geometry["source"],
            "metadata": proxy_geometry["metadata"],
        },
        default_kind="virtual_fixed_table_rect",
    )


def build_tamp_problem(
    scene: SceneState,
    task: ParsedTask,
    sym: SymbolicState,
    goal_atoms_override: Optional[List[GroundedAtom]] = None,
    surface_names: Optional[Iterable[str]] = None,
    init_atoms: Optional[List[Dict[str, Any]]] = None,
    required_final_atoms: Optional[List[Dict[str, Any]]] = None,
    recovery_hints: Optional[Mapping[str, Any]] = None,
) -> TAMPProblem:
    scene = _scene_in_robot_base_frame(scene)
    table_geometry = estimate_table_geometry(scene)
    table_z = float(table_geometry.get("bounds", {}).get("z", _estimate_table_z(scene)))
    goal_atoms: List[GroundedAtom] = []
    surfaces: List[TAMPObject] = []
    movables: List[TAMPObject] = []
    statics: List[TAMPObject] = []
    surface_name_set = set(surface_names or [])
    placement_region_hint = _placement_region_hint(recovery_hints)
    fixed_table_rect_hint = _fixed_table_rect_region_hint(recovery_hints)

    if goal_atoms_override:
        goal_atoms.extend(goal_atoms_override)
    else:
        if sym.target is not None and sym.goal is not None:
            goal_atoms.append(GroundedAtom("on", (sym.target.name, sym.goal.name)))
        elif task.operation == "pick" and sym.target is not None:
            goal_atoms.append(GroundedAtom("holding", (sym.target.name,)))
        goal_atoms.append(GroundedAtom("handempty", ()))

    for atom in goal_atoms:
        if atom.predicate in {"on", "inside"} and len(atom.args) >= 2:
            surface_name_set.add(atom.args[1])

    goal_movable_names = set()
    for atom in goal_atoms:
        if atom.predicate in {"on", "inside"} and atom.args:
            goal_movable_names.add(atom.args[0])
        elif atom.predicate == "holding" and atom.args:
            goal_movable_names.add(atom.args[-1])

    for obj in scene.objects.values():
        is_goal_surface = sym.goal is not None and obj.name == sym.goal.name and is_probably_surface(obj.name)
        is_named_surface = obj.name in surface_name_set and obj.name not in goal_movable_names
        is_goal_movable = obj.name in goal_movable_names and is_probably_movable(obj.name)
        if is_goal_surface or is_named_surface or (is_probably_surface(obj.name) and not is_goal_movable):
            surfaces.append(_make_object(obj, scene, "surface"))
        elif (sym.target is not None and obj.name == sym.target.name) or is_goal_movable:
            role = "target_movable" if obj.name in goal_movable_names or (sym.target is not None and obj.name == sym.target.name) else "goal_movable"
            movables.append(_make_object(obj, scene, role))
        else:
            # TiPToP treats non-goal objects as movable when they might need to be cleared.
            near_target = sym.target is not None and float(np.linalg.norm(obj.pos[:2] - sym.target.pos[:2])) < 0.20
            role = "obstacle_movable" if near_target else "static_context"
            should_move = near_target and is_probably_movable(obj.name)
            (movables if should_move else statics).append(_make_object(obj, scene, role if should_move else "static_context"))

    for name in sorted(surface_name_set):
        if any(obj.name == name for obj in surfaces):
            continue
        language_region_surface = _language_relative_table_region_surface(
            name,
            table_geometry,
            scene,
            task,
        )
        if language_region_surface is not None:
            surfaces.append(language_region_surface)
            continue
        descriptor_surface = _adapter_virtual_surface_descriptor(
            surface_name=name,
            scene=scene,
            task=task,
            table_geometry=table_geometry,
            recovery_hints=recovery_hints,
        )
        if descriptor_surface is not None:
            surfaces.append(descriptor_surface)
            continue
        if _fixed_table_rect_region_applies(name, fixed_table_rect_hint, task):
            surfaces.append(_virtual_fixed_table_rect_surface(name, table_geometry, fixed_table_rect_hint, scene, task))
            continue
        source_name = _placement_region_source_name(name, placement_region_hint)
        source = scene.objects.get(str(source_name)) if source_name else None
        if source is not None:
            surfaces.append(_virtual_inner_floor_surface(name, source, scene, placement_region_hint))

    table = TAMPObject("table", table_geometry["center"], 0.70, 0.02, "surface", half_extents=table_geometry["half_extents"], mesh_path=table_geometry.get("mesh_path"), geometry=table_geometry)
    surfaces = [obj for obj in surfaces if obj.name != "table"]
    surfaces.insert(0, table)

    grasp_profile = _grasp_profile_from_hints(recovery_hints)
    grasp_profile_registry = registry_from_recovery_hints(recovery_hints)
    grasps = {
        obj.name: _grasp_candidates_for_profile(obj, scene, grasp_profile, registry=grasp_profile_registry)
        for obj in scene.objects.values()
    }
    bounds = table_geometry.get("bounds", {})
    table_x = [float(bounds.get("x_min", -0.65)) + 0.12, float(bounds.get("x_max", 0.65)) - 0.12]
    table_y = [float(bounds.get("y_min", -0.45)) + 0.12, float(bounds.get("y_max", 0.45)) - 0.12]
    place_candidates = {"table": np.array([
        [sum(table_x) * 0.5, sum(table_y) * 0.5, table_z + 0.16],
        [table_x[0], sum(table_y) * 0.5, table_z + 0.16],
        [table_x[1], sum(table_y) * 0.5, table_z + 0.16],
        [sum(table_x) * 0.5, table_y[0], table_z + 0.16],
        [sum(table_x) * 0.5, table_y[1], table_z + 0.16],
    ], dtype=np.float32)}
    for obj in scene.objects.values():
        place_candidates[obj.name] = _placement_candidates(obj, scene)
    for surface in surfaces:
        if surface.name in place_candidates:
            continue
        metadata = surface.geometry.get("metadata", {}) if isinstance(surface.geometry, dict) else {}
        inner = metadata.get("inner_bounds", {}) if isinstance(metadata, dict) else {}
        if isinstance(inner, dict) and inner:
            x_min = float(inner.get("x_min", surface.pos[0]))
            x_max = float(inner.get("x_max", surface.pos[0]))
            y_min = float(inner.get("y_min", surface.pos[1]))
            y_max = float(inner.get("y_max", surface.pos[1]))
            z_offset = float(metadata.get("place_z_offset_m", 0.12))
            z = float(inner.get("support_z", inner.get("z_min", surface.pos[2]))) + z_offset
            place_candidates[surface.name] = _inner_floor_place_candidates(x_min, x_max, y_min, y_max, z, metadata)
        else:
            place_candidates[surface.name] = np.asarray(
                [[surface.pos[0], surface.pos[1], surface.pos[2] + 0.12]],
                dtype=np.float32,
            )

    init_atoms_list = list(init_atoms or [])
    required_atoms_list = list(required_final_atoms or [])
    init_mapping = map_atoms_to_cutamp(init_atoms_list, allow_approximations=True)
    goal_mapping = map_atoms_to_cutamp(required_atoms_list or goal_atoms, allow_approximations=True)
    action_schemas = build_action_schemas(scene, surface_name_set)
    q_init = scene.robot_qpos.astype(float).tolist() if scene.robot_qpos.size > 0 else None
    q_init_debug = dict(scene.robot_joint_debug)
    current_grasp = _reconstruct_current_grasp(scene)
    if current_grasp is not None:
        init_atoms_list = [
            atom for atom in init_atoms_list if str(atom.get("predicate", "")).replace("_", "").lower() != "holdingwithgrasp"
        ]
        init_atoms_list.append(
            {
                "predicate": "holdingwithgrasp",
                "args": [current_grasp["object_name"], current_grasp["symbol"]],
                "source": "sim_truth_reconstructed_grasp",
                "confidence": float(current_grasp["confidence"]),
            }
        )
        init_mapping = map_atoms_to_cutamp(init_atoms_list, allow_approximations=True)

    return TAMPProblem(
        movables=movables,
        surfaces=surfaces,
        statics=statics,
        goal_atoms=goal_atoms,
        init_atoms=init_atoms_list,
        required_final_atoms=required_atoms_list,
        fluent_mapping={"init": init_mapping.to_dict(), "goal": goal_mapping.to_dict()},
        action_schemas=action_schemas,
        grasps=grasps,
        place_candidates=place_candidates,
        retreat_candidates=_retreat_candidates(scene),
        table_z=table_z,
        table_geometry=table_geometry,
        q_init=q_init,
        q_init_debug=q_init_debug,
        current_grasp=current_grasp,
    )
