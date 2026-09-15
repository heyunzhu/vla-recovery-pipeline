from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .affordances import is_probably_movable, is_probably_surface, object_affordances
from .predicates import SymbolicState
from .scene_graph import Atom, SceneGraph, make_atom, make_handempty_atoms
from .scene_reader import ObjectState, SceneState


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32)[:3] - np.asarray(b, dtype=np.float32)[:3]))


def _xy_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32)[:2] - np.asarray(b, dtype=np.float32)[:2]))


@dataclass
class RecoverySymbolicAbstraction:
    """Small recovery-oriented symbolic layer.

    These atoms are not meant to replace cuTAMP's native pick/place domain.
    They give the adapter enough state to ask cuTAMP for recovery subgoals
    such as regaining target holding or parking a disturbed object.
    """

    target: Optional[str]
    goal: Optional[str]
    nearest: Optional[str]
    holding: Optional[str]
    atoms: List[Atom] = field(default_factory=list)
    movable_obstacles: List[str] = field(default_factory=list)
    safe_surfaces: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "goal": self.goal,
            "nearest": self.nearest,
            "holding": self.holding,
            "atoms": list(self.atoms),
            "movable_obstacles": list(self.movable_obstacles),
            "safe_surfaces": list(self.safe_surfaces),
            "diagnostics": dict(self.diagnostics),
        }


def _held_object(scene: SceneState) -> Optional[ObjectState]:
    evidence = dict(scene.holding_evidence or {})
    if evidence.get("status") != "holding":
        return None
    object_name = evidence.get("object_name")
    return scene.objects.get(str(object_name)) if object_name is not None else None


def build_recovery_symbolic_abstraction(scene: SceneState, sym: SymbolicState, graph: SceneGraph) -> RecoverySymbolicAbstraction:
    target = sym.target.name if sym.target is not None else graph.target
    goal = sym.goal.name if sym.goal is not None else graph.goal
    nearest_obj = scene.nearest_object()
    nearest = nearest_obj.name if nearest_obj is not None else None
    held = _held_object(scene)
    holding = held.name if held is not None else None

    atoms: List[Atom] = []
    atoms.append(make_atom("gripper_open" if scene.gripper_open else "gripper_closed", "gripper", source="recovery_symbols"))
    if holding is not None:
        atoms.append(
            make_atom(
                "holding",
                "gripper",
                holding,
                source="sim_contact_truth",
                confidence=float(scene.holding_evidence.get("confidence", 0.0)),
            )
        )
        atoms.append(make_atom("object_in_hand_unstable", holding, source="recovery_symbols", confidence=0.5))
    else:
        atoms.extend(make_handempty_atoms(scene))

    if nearest_obj is not None:
        d = _dist(scene.ee_pos, nearest_obj.pos)
        atoms.append(make_atom("nearest_object", nearest_obj.name, source="recovery_symbols", confidence=max(0.0, 1.0 - d / 0.20)))
        if d < 0.10:
            atoms.append(make_atom("near", "gripper", nearest_obj.name, source="recovery_symbols", confidence=max(0.0, 1.0 - d / 0.10)))
        if not scene.gripper_open and d < 0.10:
            atoms.append(make_atom("stuck_like", "gripper", nearest_obj.name, source="recovery_symbols", confidence=max(0.25, 1.0 - d / 0.10)))

    if target is not None and target in scene.objects:
        target_obj = scene.objects[target]
        target_dist = _dist(scene.ee_pos, target_obj.pos)
        atoms.append(make_atom("recoverable", target, source="recovery_symbols", confidence=1.0 if is_probably_movable(target) else 0.35))
        if target_dist < 0.16:
            atoms.append(make_atom("near_gripper", target, source="recovery_symbols", confidence=max(0.0, 1.0 - target_dist / 0.16)))
        if goal is not None and goal in scene.objects:
            goal_dist = _xy_dist(target_obj.pos, scene.objects[goal].pos)
            atoms.append(make_atom("target_goal_xy_distance", target, goal, source="recovery_symbols", confidence=max(0.0, 1.0 - goal_dist / 0.25)))
            if goal_dist > 0.14:
                atoms.append(make_atom("target_not_at_goal", target, goal, source="recovery_symbols", confidence=min(1.0, goal_dist / 0.25)))

    movable_obstacles: List[str] = []
    if target is not None and target in scene.objects:
        target_pos = scene.objects[target].pos
        for obj in scene.objects.values():
            if obj.name == target or not is_probably_movable(obj.name):
                continue
            if _xy_dist(obj.pos, target_pos) < 0.16:
                movable_obstacles.append(obj.name)
                atoms.append(make_atom("movable_obstacle_near_target", obj.name, target, source="recovery_symbols"))

    safe_surfaces = ["table"]
    for name, obj in scene.objects.items():
        if is_probably_surface(name) and name != target:
            safe_surfaces.append(name)
            if "container" in object_affordances(name):
                atoms.append(make_atom("safe_container", name, source="recovery_symbols"))
            else:
                atoms.append(make_atom("safe_surface", name, source="recovery_symbols"))
    atoms.append(make_atom("safe_retreat_pose", "retreat_pose", source="recovery_symbols"))
    atoms.append(make_atom("can_retreat", "gripper", "retreat_pose", source="recovery_symbols"))

    seen = set()
    unique: List[Atom] = []
    for atom in [*graph.world_atoms, *atoms]:
        key = (str(atom.get("predicate", "")), tuple(str(x) for x in atom.get("args", [])))
        if key in seen:
            continue
        seen.add(key)
        unique.append(atom)

    return RecoverySymbolicAbstraction(
        target=target,
        goal=goal,
        nearest=nearest,
        holding=holding,
        atoms=unique,
        movable_obstacles=movable_obstacles,
        safe_surfaces=list(dict.fromkeys(safe_surfaces)),
        diagnostics={
            "num_atoms": len(unique),
            "gripper_open": scene.gripper_open,
            "uses_sim_truth": True,
            "holding_evidence": dict(scene.holding_evidence),
            "purpose": "recovery symbolic enrichment for cuTAMP goal/skeleton search",
        },
    )
