from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .affordances import is_probably_movable, is_probably_surface, object_affordances, object_category
from .geometry import estimate_object_geometry, estimate_table_geometry
from .predicates import SymbolicState
from .scene_reader import ObjectState, SceneState
from .task_parser import ParsedTask


Atom = Dict[str, Any]


@dataclass
class ObjectNode:
    name: str
    pos: List[float]
    role: str = "object"
    dist_to_ee: float = 0.0
    category: str = "object"
    affordances: List[str] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    geometry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneGraph:
    task_language: str
    ee_pos: List[float]
    gripper_open: bool
    objects: List[ObjectNode] = field(default_factory=list)
    predicates: Dict[str, bool] = field(default_factory=dict)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    world_atoms: List[Atom] = field(default_factory=list)
    task_atoms: List[Atom] = field(default_factory=list)
    task_progress: Dict[str, Any] = field(default_factory=dict)
    target: Optional[str] = None
    goal: Optional[str] = None
    table_geometry: Dict[str, Any] = field(default_factory=dict)
    holding_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_planner_context(self) -> Dict[str, Any]:
        return {
            "task": self.task_language,
            "ee_pos": self.ee_pos,
            "gripper_open": self.gripper_open,
            "target": self.target,
            "goal": self.goal,
            "objects": [node.__dict__ for node in self.objects],
            "predicates": self.predicates,
            "relations": self.relations,
            "world_atoms": self.world_atoms,
            "task_atoms": self.task_atoms,
            "task_progress": self.task_progress,
            "table_geometry": self.table_geometry,
            "holding_evidence": self.holding_evidence,
        }


def make_atom(predicate: str, *args: str, source: str = "sim_truth", confidence: float = 1.0) -> Atom:
    return {"predicate": predicate, "args": list(args), "source": source, "confidence": float(confidence)}


def make_handempty_atoms(scene: SceneState, source: str = "sim_contact_truth") -> List[Atom]:
    """Closed-but-unconfirmed grippers are treated as empty so planning can start.

    Bilateral contact still produces Holding elsewhere. This helper only covers the
    unconfirmed branch: keep HandEmpty at the simulator-truth threshold and record
    the closed-gripper ambiguity as a diagnostic atom, not as a missing fluent.
    """
    if scene.gripper_open:
        return [make_atom("handempty", "gripper", source=source, confidence=1.0)]
    return [
        make_atom("handempty", "gripper", source=source, confidence=0.60),
        make_atom("gripper_closed_unconfirmed", "gripper", source=source, confidence=1.0),
    ]


def atom_key(atom: Atom) -> Tuple[str, Tuple[str, ...]]:
    return str(atom.get("predicate", "")), tuple(str(x) for x in atom.get("args", []))


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32)[:3] - np.asarray(b, dtype=np.float32)[:3]))


def _xy_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32)[:2] - np.asarray(b, dtype=np.float32)[:2]))


def _joint_state_for_object(scene: SceneState, object_name: str) -> Dict[str, Any]:
    low = object_name.lower().replace("_", " ")
    best_name: Optional[str] = None
    best_value = 0.0
    for joint in scene.joints.values():
        jlow = joint.name.lower().replace("_", " ")
        if any(token and token in jlow for token in low.split()):
            best_name = joint.name
            best_value = joint.qpos
            break
        if ("microwave" in low and "micro" in jlow) or ("drawer" in low and "drawer" in jlow):
            best_name = joint.name
            best_value = joint.qpos
            break
    if best_name is None:
        return {}
    is_open = abs(float(best_value)) > 0.04
    return {"joint": best_name, "joint_qpos": float(best_value), "open_state": "open" if is_open else "closed"}


def _object_node(scene: SceneState, obj: ObjectState, role: str) -> ObjectNode:
    affordances = object_affordances(obj.name)
    state = _joint_state_for_object(scene, obj.name) if "articulated" in affordances or "door_link" in affordances else {}
    geometry = estimate_object_geometry(obj, scene).to_dict()
    return ObjectNode(
        name=obj.name,
        pos=obj.pos[:3].astype(float).tolist(),
        role=role,
        dist_to_ee=_dist(scene.ee_pos, obj.pos),
        category=object_category(obj.name),
        affordances=affordances,
        state=state,
        geometry=geometry,
    )


def _nearest_surface_or_container(obj: ObjectState, scene: SceneState, max_xy: float = 0.11) -> Optional[ObjectState]:
    candidates = [other for other in scene.objects.values() if other.name != obj.name and is_probably_surface(other.name)]
    if not candidates:
        return None
    best = min(candidates, key=lambda other: _xy_dist(obj.pos, other.pos))
    if _xy_dist(obj.pos, best.pos) <= max_xy:
        return best
    return None


def _build_world_atoms(scene: SceneState, objects: List[ObjectNode]) -> List[Atom]:
    atoms: List[Atom] = []
    by_name = {obj.name: scene.objects[obj.name] for obj in objects if obj.name in scene.objects}
    holding_object = scene.holding_evidence.get("object_name") if scene.holding_evidence.get("status") == "holding" else None
    if holding_object is not None:
        atoms.append(
            make_atom(
                "holding",
                "gripper",
                str(holding_object),
                source="sim_contact_truth",
                confidence=float(scene.holding_evidence.get("confidence", 0.0)),
            )
        )
    else:
        atoms.extend(make_handempty_atoms(scene))

    for node in objects:
        atoms.append(make_atom("category", node.name, node.category))
        atoms.append(make_atom("geometry_proxy", node.name, node.geometry.get("kind", "unknown")))
        for affordance in node.affordances:
            atoms.append(make_atom("affordance", node.name, affordance))
        if node.dist_to_ee < 0.10:
            atoms.append(make_atom("near", "gripper", node.name, confidence=max(0.0, 1.0 - node.dist_to_ee / 0.10)))
        open_state = node.state.get("open_state")
        if open_state in {"open", "closed"}:
            atoms.append(make_atom(open_state, node.name))

    for obj in by_name.values():
        if not is_probably_movable(obj.name) or obj.name == holding_object:
            continue
        surface = _nearest_surface_or_container(obj, scene)
        if surface is None:
            atoms.append(make_atom("on", obj.name, "table", confidence=0.65))
            continue
        predicate = "inside" if "container" in object_affordances(surface.name) else "on"
        conf = max(0.35, 1.0 - _xy_dist(obj.pos, surface.pos) / 0.11)
        atoms.append(make_atom(predicate, obj.name, surface.name, confidence=conf))

    seen = set()
    unique: List[Atom] = []
    for atom in atoms:
        key = atom_key(atom)
        if key in seen:
            continue
        seen.add(key)
        unique.append(atom)
    return unique


def build_scene_graph(scene: SceneState, task: ParsedTask, sym: SymbolicState) -> SceneGraph:
    objects: List[ObjectNode] = []
    relations: List[Dict[str, Any]] = []
    for obj in scene.objects.values():
        role = "object"
        if sym.target is not None and obj.name == sym.target.name:
            role = "target"
        elif sym.goal is not None and obj.name == sym.goal.name:
            role = "goal"
        node = _object_node(scene, obj, role)
        objects.append(node)
        if node.dist_to_ee < 0.10:
            relations.append({"type": "near", "subject": "end_effector", "object": obj.name, "distance": node.dist_to_ee})

    objects.sort(key=lambda node: node.dist_to_ee)
    for idx, src in enumerate(objects):
        for dst in objects[idx + 1 :]:
            if src.name not in scene.objects or dst.name not in scene.objects:
                continue
            d_xy = _xy_dist(scene.objects[src.name].pos, scene.objects[dst.name].pos)
            if d_xy < 0.12:
                relations.append({"type": "near", "subject": src.name, "object": dst.name, "xy_distance": d_xy})
    if sym.target is not None and sym.goal is not None:
        relations.append(
            {
                "type": "target_goal_distance",
                "subject": sym.target.name,
                "object": sym.goal.name,
                "distance": _dist(sym.target.pos, sym.goal.pos),
            }
        )

    return SceneGraph(
        task_language=task.language,
        ee_pos=scene.ee_pos[:3].astype(float).tolist(),
        gripper_open=scene.gripper_open,
        objects=objects,
        predicates=dict(sym.predicates),
        relations=relations,
        world_atoms=_build_world_atoms(scene, objects),
        target=sym.target.name if sym.target is not None else task.target_hint,
        goal=sym.goal.name if sym.goal is not None else task.goal_hint,
        table_geometry=estimate_table_geometry(scene),
        holding_evidence=dict(scene.holding_evidence),
    )
