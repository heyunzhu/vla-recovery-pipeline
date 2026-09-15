from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import numpy as np

from .domain import PlanStep
from .predicates import SymbolicState
from .scene_reader import SceneState


@dataclass
class SkillConfig:
    xy_gain: float = 4.0
    z_gain: float = 4.0
    max_delta: float = 0.08
    pregrasp_height: float = 0.16
    grasp_height: float = 0.03
    lift_height: float = 0.18
    steps_per_move: int = 8
    gripper_steps: int = 5


def _action(delta_xyz: Iterable[float], gripper: float, max_delta: float = 0.08) -> np.ndarray:
    out = np.zeros(7, dtype=np.float32)
    out[:3] = np.clip(np.asarray(list(delta_xyz), dtype=np.float32), -max_delta, max_delta)
    out[6] = float(gripper)
    return out


def _arg(step: PlanStep, name: str, default: float) -> float:
    return float(step.args.get(name, default))


def _int_arg(step: PlanStep, name: str, default: int) -> int:
    return max(1, int(step.args.get(name, default)))


def _move_towards(scene: SceneState, goal_pos: np.ndarray, cfg: SkillConfig, gripper: float, steps: int | None = None) -> List[np.ndarray]:
    goal = np.asarray(goal_pos, dtype=np.float32)
    delta = goal - scene.ee_pos
    cmd = np.array([cfg.xy_gain * delta[0], cfg.xy_gain * delta[1], cfg.z_gain * delta[2]], dtype=np.float32)
    cmd = np.clip(cmd, -cfg.max_delta, cfg.max_delta)
    return [_action(cmd, gripper, cfg.max_delta) for _ in range(steps or cfg.steps_per_move)]


def actions_for_step(step: PlanStep, scene: SceneState, sym: SymbolicState, cfg: SkillConfig) -> List[np.ndarray]:
    target = sym.target
    goal = sym.goal
    if step.name == "hold_position":
        steps = _int_arg(step, "steps", 3)
        gripper = _arg(step, "gripper", -1.0 if scene.gripper_open else 1.0)
        return [_action([0.0, 0.0, 0.0], gripper, cfg.max_delta) for _ in range(steps)]
    if step.name == "open_gripper":
        steps = _int_arg(step, "steps", cfg.gripper_steps)
        return [_action([0.0, 0.0, 0.0], -1.0, cfg.max_delta) for _ in range(steps)]
    if step.name == "micro_lift":
        height = _arg(step, "height", 0.035)
        steps = _int_arg(step, "steps", 3)
        gripper = _arg(step, "gripper", 1.0)
        return [_action([0.0, 0.0, height / steps], gripper, cfg.max_delta) for _ in range(steps)]
    if step.name == "retreat_open":
        lift = _arg(step, "lift", 0.06)
        back = _arg(step, "back", 0.03)
        lateral = _arg(step, "lateral", 0.0)
        up_steps = _int_arg(step, "up_steps", 6)
        back_steps = _int_arg(step, "back_steps", 4)
        gripper = _arg(step, "gripper", -1.0)
        return (
            [_action([0.0, 0.0, lift / up_steps], gripper, cfg.max_delta) for _ in range(up_steps)]
            + [_action([-back / back_steps, lateral / back_steps, 0.02 / back_steps], gripper, cfg.max_delta) for _ in range(back_steps)]
        )
    if step.name == "move_above_object" and target is not None:
        pos = target.pos.copy()
        pos[2] += _arg(step, "height", cfg.pregrasp_height)
        return _move_towards(scene, pos, cfg, -1.0, _int_arg(step, "steps", cfg.steps_per_move))
    if step.name == "descend_to_grasp" and target is not None:
        pos = target.pos.copy()
        pos[2] += _arg(step, "height", cfg.grasp_height)
        return _move_towards(scene, pos, cfg, -1.0, _int_arg(step, "steps", cfg.steps_per_move))
    if step.name == "close_gripper":
        steps = _int_arg(step, "steps", cfg.gripper_steps)
        return [_action([0.0, 0.0, 0.0], 1.0, cfg.max_delta) for _ in range(steps)]
    if step.name == "lift":
        height = _arg(step, "height", cfg.lift_height)
        steps = _int_arg(step, "steps", max(3, cfg.steps_per_move))
        return [_action([0.0, 0.0, height / steps], 1.0, cfg.max_delta) for _ in range(steps)]
    if step.name == "move_above_goal" and goal is not None:
        pos = goal.pos.copy()
        pos[2] += _arg(step, "height", cfg.lift_height)
        return _move_towards(scene, pos, cfg, 1.0, _int_arg(step, "steps", cfg.steps_per_move))
    if step.name == "slow_place":
        descend = _arg(step, "descend", 0.28)
        descend_steps = _int_arg(step, "descend_steps", 8)
        release_steps = _int_arg(step, "release_steps", cfg.gripper_steps)
        return (
            [_action([0.0, 0.0, -descend / descend_steps], 1.0, cfg.max_delta) for _ in range(descend_steps)]
            + [_action([0.0, 0.0, 0.0], -1.0, cfg.max_delta) for _ in range(release_steps)]
        )
    return []
