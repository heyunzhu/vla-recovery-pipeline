from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from .scene_reader import ObjectState, SceneState
from .task_parser import ParsedTask


@dataclass
class SymbolicState:
    target: Optional[ObjectState]
    goal: Optional[ObjectState]
    nearest: Optional[ObjectState]
    predicates: Dict[str, bool]


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a)[:3] - np.asarray(b)[:3]))


def _choose_by_hint(scene: SceneState, hint: Optional[str]) -> Optional[ObjectState]:
    if hint and hint in scene.objects:
        return scene.objects[hint]
    return None


def build_symbolic_state(scene: SceneState, task: ParsedTask) -> SymbolicState:
    target = _choose_by_hint(scene, task.target_hint) or scene.nearest_object()
    goal = _choose_by_hint(scene, task.goal_hint)
    nearest = scene.nearest_object()
    target_dist = _dist(scene.ee_pos, target.pos) if target is not None else 999.0
    goal_dist = _dist(target.pos, goal.pos) if target is not None and goal is not None else 999.0
    lifted = bool(target is not None and target.pos[2] > 0.90)
    predicates = {
        "gripper_open": scene.gripper_open,
        "target_reachable": target_dist < 0.35,
        "near_target": target_dist < 0.10,
        "target_lifted": lifted,
        "target_at_goal": goal_dist < 0.10,
        "has_goal": goal is not None,
        "nearest_is_target": bool(target is not None and nearest is not None and target.name == nearest.name),
    }
    return SymbolicState(target=target, goal=goal, nearest=nearest, predicates=predicates)
