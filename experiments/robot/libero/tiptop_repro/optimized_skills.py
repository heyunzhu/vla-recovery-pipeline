from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import numpy as np

from .domain import PlanStep
from .predicates import SymbolicState
from .scene_reader import SceneState
from .skills import SkillConfig


@dataclass
class OptimizedSkillConfig(SkillConfig):
    move_steps: int = 10
    wide_retreat_steps: int = 12


def _action(delta_xyz: Iterable[float], gripper: float) -> np.ndarray:
    out = np.zeros(7, dtype=np.float32)
    out[:3] = np.clip(np.asarray(list(delta_xyz), dtype=np.float32), -0.08, 0.08)
    out[6] = float(gripper)
    return out


def _pos(step: PlanStep, key: str) -> Optional[np.ndarray]:
    value = step.args.get(key)
    if value is None:
        return None
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    if arr.size < 3:
        return None
    return arr[:3]


def _move_to(scene: SceneState, goal: np.ndarray, cfg: OptimizedSkillConfig, gripper: float, steps: Optional[int] = None) -> List[np.ndarray]:
    delta = np.asarray(goal, dtype=np.float32)[:3] - scene.ee_pos[:3]
    cmd = np.array([cfg.xy_gain * delta[0], cfg.xy_gain * delta[1], cfg.z_gain * delta[2]], dtype=np.float32)
    cmd = np.clip(cmd, -cfg.max_delta, cfg.max_delta)
    return [_action(cmd, gripper) for _ in range(steps or cfg.move_steps)]


def optimized_actions_for_step(step: PlanStep, scene: SceneState, sym: SymbolicState, cfg: OptimizedSkillConfig) -> List[np.ndarray]:
    if step.name == "retreat_open":
        target = _pos(step, "retreat_pos")
        if target is not None:
            return _move_to(scene, target, cfg, -1.0, steps=8)
        return [_action([0.0, 0.0, 0.06], -1.0) for _ in range(6)]
    if step.name == "wide_retreat_open":
        target = _pos(step, "retreat_pos")
        if target is not None:
            return _move_to(scene, target, cfg, -1.0, steps=cfg.wide_retreat_steps)
        return [_action([0.0, -0.05, 0.06], -1.0) for _ in range(cfg.wide_retreat_steps)]
    if step.name in {"move_above_object", "move_above_obstacle"}:
        target = _pos(step, "pregrasp_pos")
        if step.name == "move_above_obstacle":
            target = _pos(step, "obstacle_place_pos")
        if target is not None:
            target = target.copy()
            target[2] = max(target[2], cfg.table_z + cfg.pregrasp_height) if hasattr(cfg, "table_z") else target[2]
            return _move_to(scene, target, cfg, -1.0)
    if step.name in {"descend_to_grasp", "descend_to_obstacle"}:
        target = _pos(step, "grasp_pos")
        if target is not None:
            return _move_to(scene, target, cfg, -1.0, steps=8)
    if step.name == "close_gripper":
        return [_action([0.0, 0.0, 0.0], 1.0) for _ in range(cfg.gripper_steps)]
    if step.name in {"lift", "lift_obstacle"}:
        return [_action([0.0, 0.0, 0.06], 1.0) for _ in range(8)]
    if step.name == "move_above_goal":
        target = _pos(step, "place_pos")
        if target is not None:
            return _move_to(scene, target, cfg, 1.0, steps=cfg.move_steps)
    if step.name == "move_obstacle_aside":
        target = _pos(step, "obstacle_place_pos")
        if target is not None:
            return _move_to(scene, target, cfg, 1.0, steps=cfg.move_steps)
    if step.name == "slow_place":
        return [_action([0.0, 0.0, -0.035], 1.0) for _ in range(8)] + [_action([0.0, 0.0, 0.0], -1.0) for _ in range(5)]
    if step.name == "open_gripper":
        return [_action([0.0, 0.0, 0.0], -1.0) for _ in range(cfg.gripper_steps)]
    return []
