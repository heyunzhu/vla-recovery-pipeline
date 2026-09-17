"""Compact, BDDL-goal-free contexts for offline task-binding mining.

The collector consumes only the task language and one initial MuJoCo
``SceneState``.  It deliberately records no BDDL goal, object-of-interest,
region, or init atoms.  The resulting JSON is intended to be cached and later
fed to an offline miner; collecting it never runs a policy or an episode.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

import numpy as np

from experiments.robot.libero.tiptop_repro.affordances import object_affordances, object_category
from experiments.robot.libero.tiptop_repro.geometry import estimate_object_geometry, estimate_table_geometry
from experiments.robot.libero.tiptop_repro.language_mujoco_goals import resolve_language_mujoco_hints


SCHEMA_VERSION = 1
COLLECTOR_VERSION = "task_binding_context_v1"
_INSTANCE_SUFFIX_RE = re.compile(r"_(?:\d+)(?:_main)?$")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return str(value)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _semantic_family(name: str) -> str:
    text = str(name or "").lower().strip("_")
    if text.endswith("_main"):
        text = text[: -len("_main")]
    return _INSTANCE_SUFFIX_RE.sub("", text).strip("_")


def _compact_site(site: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonable(site.get(key))
        for key in ("name", "body_name", "shape", "size", "pos", "quat")
        if site.get(key) is not None
    }


def _compact_geom(geom: Mapping[str, Any]) -> dict[str, Any]:
    # Mesh vertices/faces dominate the raw scene and do not help language
    # binding.  Shape, size and world pose are sufficient for offline mining.
    return {
        key: _jsonable(geom.get(key))
        for key in (
            "name",
            "body_name",
            "shape",
            "size",
            "pos",
            "quat",
            "mesh_name",
            "mesh_path",
            "collision_active",
        )
        if geom.get(key) is not None
    }


def _dedupe_sites(raw_geometry: Mapping[str, Any], proxy_metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = list(raw_geometry.get("sites") or [])
    candidates.extend(list(proxy_metadata.get("sites") or []))
    candidates.extend(list(proxy_metadata.get("containment_sites") or []))
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in candidates:
        if not isinstance(raw, Mapping):
            continue
        item = _compact_site(raw)
        key = (str(item.get("name") or ""), str(item.get("body_name") or ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return sorted(out, key=lambda item: (str(item.get("name") or ""), str(item.get("body_name") or "")))


def _object_summary(obj: Any, scene: Any) -> dict[str, Any]:
    name = str(getattr(obj, "name", "") or "")
    raw_geometry = getattr(obj, "geometry", {}) or {}
    raw_geometry = raw_geometry if isinstance(raw_geometry, Mapping) else {}
    proxy = estimate_object_geometry(obj, scene)
    proxy_data = proxy.to_dict()
    proxy_metadata = proxy_data.pop("metadata", {}) or {}
    compact_proxy_metadata = {
        key: _jsonable(proxy_metadata.get(key))
        for key in ("inner_bounds", "collision_geom_count", "visual_only_geom_count")
        if proxy_metadata.get(key) is not None
    }
    return {
        "name": name,
        "semantic_family": _semantic_family(name),
        "category": object_category(name),
        "affordances": object_affordances(name),
        "pos": _jsonable(getattr(obj, "pos", [])),
        "quat": _jsonable(getattr(obj, "quat", None)),
        "geometry_proxy": {**_jsonable(proxy_data), "metadata": compact_proxy_metadata},
        "sites": _dedupe_sites(raw_geometry, proxy_metadata),
        "geoms": sorted(
            [_compact_geom(geom) for geom in raw_geometry.get("geoms") or [] if isinstance(geom, Mapping)],
            key=lambda item: str(item.get("name") or ""),
        ),
    }


def _is_robot_joint(name: str) -> bool:
    low = str(name or "").lower()
    return any(token in low for token in ("robot0", "panda", "finger", "gripper", "hand"))


def summarize_scene(scene: Any) -> dict[str, Any]:
    objects = [
        _object_summary(obj, scene)
        for _, obj in sorted((getattr(scene, "objects", {}) or {}).items(), key=lambda item: str(item[0]))
    ]
    joints = []
    for name, joint in sorted((getattr(scene, "joints", {}) or {}).items(), key=lambda item: str(item[0])):
        if _is_robot_joint(str(name)):
            continue
        joints.append(
            {
                "name": str(name),
                "qpos": float(getattr(joint, "qpos", 0.0)),
                "qvel": float(getattr(joint, "qvel", 0.0)),
            }
        )
    return {
        "objects": objects,
        "articulated_joints": joints,
        "table_geometry": _jsonable(estimate_table_geometry(scene)),
    }


def _binding_summary(language: str, scene: Any) -> dict[str, Any]:
    hints = resolve_language_mujoco_hints(language, scene)
    return {
        key: _jsonable(hints.get(key))
        for key in (
            "source",
            "target",
            "goal",
            "obj_of_interest",
            "goal_atoms",
            "goal_surfaces",
            "parsed_language",
            "binding_evidence",
            "failure_reason",
            "failure_detail",
        )
    }


def build_task_binding_context(
    language: str,
    scene: Any,
    *,
    task: Mapping[str, Any] | None = None,
    language_source: str = "task",
    seed: int = 0,
    init_state_index: int = 0,
) -> dict[str, Any]:
    """Build one cacheable context without reading or accepting BDDL goal data."""

    scene_summary = summarize_scene(scene)
    normalized_language = " ".join(str(language or "").split())
    topology = {
        "language": normalized_language.lower(),
        "objects": [
            {
                "name": obj["name"],
                "semantic_family": obj["semantic_family"],
                "category": obj["category"],
                "affordances": obj["affordances"],
                "sites": [site.get("name") for site in obj["sites"]],
                "geoms": [
                    {"name": geom.get("name"), "shape": geom.get("shape"), "size": geom.get("size")}
                    for geom in obj["geoms"]
                ],
            }
            for obj in scene_summary["objects"]
        ],
        "joint_names": [joint["name"] for joint in scene_summary["articulated_joints"]],
        "collector_version": COLLECTOR_VERSION,
    }
    snapshot = {
        "topology": topology,
        "object_poses": [
            {"name": obj["name"], "pos": obj["pos"], "quat": obj["quat"]}
            for obj in scene_summary["objects"]
        ],
        "joint_values": scene_summary["articulated_joints"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "task": _jsonable(dict(task or {})),
        "language": normalized_language,
        "language_source": str(language_source or "task"),
        "seed": int(seed),
        "init_state_index": int(init_state_index),
        "input_contract": {
            "used": ["task_language", "initial_mujoco_scene"],
            "forbidden": ["bddl_goal", "bddl_obj_of_interest", "bddl_regions", "bddl_init_atoms"],
            "policy_rollout_steps": 0,
        },
        "scene": scene_summary,
        "binding": _binding_summary(normalized_language, scene),
        "task_fingerprint": _stable_hash(topology),
        "snapshot_fingerprint": _stable_hash(snapshot),
    }

