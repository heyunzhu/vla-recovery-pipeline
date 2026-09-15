from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np

from .domain import RecoveryPlan
from .optimized_skills import OptimizedSkillConfig, optimized_actions_for_step
from .predicates import build_symbolic_state
from .scene_reader import SceneState, read_scene
from .task_parser import ParsedTask

@dataclass
class PostconditionResult:
    ok: bool
    hard: bool = False
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)



@dataclass
class GoalSatisfactionResult:
    ok: bool
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


def _atom_parts(atom: Any) -> Tuple[str, Tuple[str, ...]]:
    if hasattr(atom, "predicate") and hasattr(atom, "args"):
        return str(atom.predicate).lower(), tuple(str(arg) for arg in atom.args)
    return str(atom.get("predicate", "")).lower(), tuple(str(arg) for arg in atom.get("args", []))


def _named_object(scene: SceneState, name: str):
    if name == "table":
        return None
    return scene.objects.get(name)


def _scene_holding(scene: SceneState, obj_name: str) -> bool:
    obj = scene.objects.get(obj_name)
    if obj is None or scene.gripper_open:
        return False
    evidence = dict(getattr(scene, "holding_evidence", None) or {})
    if evidence:
        return bool(evidence.get("status") == "holding" and str(evidence.get("object_name") or "") == str(obj_name))
    return _dist(scene.ee_pos, obj.pos) < 0.095


def _scene_on_or_inside(scene: SceneState, obj_name: str, surface_name: str) -> GoalSatisfactionResult:
    obj = scene.objects.get(obj_name)
    if obj is None:
        return GoalSatisfactionResult(False, "missing_object", {"object": obj_name})
    if surface_name == "table":
        xy_ok = True
        z_ok = float(obj.pos[2]) < 0.20
        return GoalSatisfactionResult(bool(xy_ok and z_ok and scene.gripper_open), "object_parked_on_table", {"z": float(obj.pos[2]), "gripper_open": scene.gripper_open})
    surface = _named_object(scene, surface_name)
    if surface is None:
        return GoalSatisfactionResult(False, "missing_surface", {"surface": surface_name})
    xy = float(np.linalg.norm(obj.pos[:2] - surface.pos[:2]))
    z_delta = float(obj.pos[2] - surface.pos[2])
    ok = bool(xy < 0.13 and z_delta > -0.04 and scene.gripper_open)
    return GoalSatisfactionResult(ok, "object_near_surface_and_released", {"xy_dist": xy, "z_delta": z_delta, "gripper_open": scene.gripper_open})


def goal_satisfied(scene: SceneState, goal_atoms: Iterable[Any] | None) -> GoalSatisfactionResult:
    atoms = list(goal_atoms or [])
    if not atoms:
        return GoalSatisfactionResult(False, "no_goal_atoms")
    checks: List[GoalSatisfactionResult] = []
    for atom in atoms:
        pred, args = _atom_parts(atom)
        if pred == "handempty":
            checks.append(GoalSatisfactionResult(bool(scene.gripper_open), "handempty", {"gripper_open": scene.gripper_open}))
        elif pred == "holding" and len(args) == 1:
            evidence = dict(getattr(scene, "holding_evidence", None) or {})
            checks.append(
                GoalSatisfactionResult(
                    _scene_holding(scene, args[0]),
                    "holding_object",
                    {
                        "object": args[0],
                        "gripper_open": scene.gripper_open,
                        "holding_status": evidence.get("status"),
                        "holding_object": evidence.get("object_name"),
                    },
                )
            )
        elif pred == "holding" and len(args) == 2:
            evidence = dict(getattr(scene, "holding_evidence", None) or {})
            checks.append(
                GoalSatisfactionResult(
                    _scene_holding(scene, args[-1]),
                    "holding_object",
                    {
                        "object": args[-1],
                        "gripper_open": scene.gripper_open,
                        "holding_status": evidence.get("status"),
                        "holding_object": evidence.get("object_name"),
                    },
                )
            )
        elif pred in {"on", "inside"} and len(args) == 2:
            checks.append(_scene_on_or_inside(scene, args[0], args[1]))
    if not checks:
        return GoalSatisfactionResult(False, "no_supported_goal_atoms", {"atoms": atoms})
    ok = all(item.ok for item in checks)
    return GoalSatisfactionResult(ok, "all_goal_atoms_satisfied" if ok else "goal_atoms_not_yet_satisfied", {"checks": [item.__dict__ for item in checks]})

def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32)[:3] - np.asarray(b, dtype=np.float32)[:3]))


def _target_from_scene(scene: SceneState, parsed_task: ParsedTask):
    if parsed_task.target_hint and parsed_task.target_hint in scene.objects:
        return scene.objects[parsed_task.target_hint]
    return scene.nearest_object()


def _postcondition_for_step(step_name: str, before: SceneState, after: SceneState, parsed_task: ParsedTask) -> PostconditionResult:
    target_before = _target_from_scene(before, parsed_task)
    target_after = _target_from_scene(after, parsed_task)
    if step_name in {"retreat_open", "wide_retreat_open"}:
        lift = float(after.ee_pos[2] - before.ee_pos[2])
        ok = bool(after.gripper_open and lift > -0.03)
        return PostconditionResult(ok=ok, hard=not ok, reason="retreat_should_open_and_not_descend", details={"ee_lift": lift, "gripper_open": after.gripper_open})
    if step_name in {"move_above_object", "move_above_obstacle"} and target_after is not None:
        xy = float(np.linalg.norm(after.ee_pos[:2] - target_after.pos[:2]))
        dz = float(after.ee_pos[2] - target_after.pos[2])
        ok = bool(xy < 0.18 and dz > 0.02)
        return PostconditionResult(ok=ok, hard=False, reason="move_above_target_pose_tolerance", details={"xy_dist": xy, "z_clearance": dz})
    if step_name in {"descend_to_grasp", "descend_to_obstacle"} and target_after is not None:
        dist = _dist(after.ee_pos, target_after.pos)
        ok = bool(dist < 0.16)
        return PostconditionResult(ok=ok, hard=False, reason="descend_grasp_pose_tolerance", details={"ee_target_dist": dist})
    if step_name == "close_gripper":
        ok = bool(not after.gripper_open)
        return PostconditionResult(ok=ok, hard=not ok, reason="gripper_should_be_closed", details={"gripper_open": after.gripper_open})
    if step_name in {"lift", "lift_obstacle"} and target_before is not None and target_after is not None:
        dz = float(target_after.pos[2] - target_before.pos[2])
        ok = bool(dz > 0.015 or not after.gripper_open)
        return PostconditionResult(ok=ok, hard=False, reason="target_should_lift_or_remain_grasped", details={"target_lift": dz, "gripper_open": after.gripper_open})
    if step_name in {"slow_place", "open_gripper"}:
        ok = bool(after.gripper_open)
        return PostconditionResult(ok=ok, hard=not ok, reason="gripper_should_be_open", details={"gripper_open": after.gripper_open})
    return PostconditionResult(ok=True)

@dataclass
class OptimizedExecutionTrace:
    plan_reason: str
    plan_steps: List[str]
    executed_steps: List[str] = field(default_factory=list)
    num_env_steps: int = 0
    done: bool = False
    success: bool = False
    goal_satisfied: bool = False
    handoff_to_vla: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)


def execute_optimized_plan(
    env: Any,
    obs: Dict[str, Any],
    parsed_task: ParsedTask,
    plan: RecoveryPlan,
    max_env_steps: int = 120,
    skill_cfg: OptimizedSkillConfig | None = None,
    stop_on_hard_postcondition_failure: bool = True,
    goal_atoms: Iterable[Any] | None = None,
    stop_on_goal_satisfied: bool = True,
    step_callback: Callable[[Dict[str, Any], Dict[str, Any]], None] | None = None,
) -> Tuple[Dict[str, Any], OptimizedExecutionTrace]:
    cfg = skill_cfg or OptimizedSkillConfig()
    trace = OptimizedExecutionTrace(plan_reason=plan.reason, plan_steps=plan.names())
    current_obs = obs
    if stop_on_goal_satisfied and goal_atoms:
        initial_scene = read_scene(env, current_obs)
        initial_goal = goal_satisfied(initial_scene, goal_atoms)
        trace.events.append({"step": "__start__", "event": "goal_check", "ok": initial_goal.ok, "reason": initial_goal.reason, "details": initial_goal.details})
        if initial_goal.ok:
            trace.goal_satisfied = True
            trace.handoff_to_vla = True
            trace.success = True
            return current_obs, trace

    for step in plan.steps:
        scene = read_scene(env, current_obs)
        sym = build_symbolic_state(scene, parsed_task)
        actions = optimized_actions_for_step(step, scene, sym, cfg)
        if not actions:
            trace.events.append({"step": step.name, "event": "no_actions"})
            continue
        trace.events.append(
            {
                "step": step.name,
                "event": "primitive_start",
                "args": {
                    key: value
                    for key, value in step.args.items()
                    if key
                    in {
                        "source",
                        "target",
                        "surface",
                        "real_cutamp_goal",
                        "real_cutamp_num_satisfying",
                        "pregrasp_pos",
                        "grasp_pos",
                        "place_pos",
                        "retreat_pos",
                    }
                },
            }
        )
        trace.executed_steps.append(step.name)
        before_scene = scene
        for action in actions:
            action_arr = np.asarray(action, dtype=np.float32)
            current_obs, _, done, _ = env.step(action_arr.tolist())
            trace.num_env_steps += 1
            if step_callback is not None:
                step_callback(
                    current_obs,
                    {
                        "env_step": trace.num_env_steps,
                        "label": step.name,
                        "phase": "optimized_fallback",
                        "type": "trajectory",
                        "done": bool(done),
                        "action": action_arr.astype(float).tolist(),
                    },
                )
            if done:
                trace.done = True
                trace.success = True
                return current_obs, trace
            if trace.num_env_steps >= max_env_steps:
                trace.events.append({"step": step.name, "event": "max_env_steps"})
                return current_obs, trace
        after_scene = read_scene(env, current_obs)
        post = _postcondition_for_step(step.name, before_scene, after_scene, parsed_task)
        trace.events.append({
            "step": step.name,
            "event": "postcondition",
            "ok": post.ok,
            "hard": post.hard,
            "reason": post.reason,
            "details": post.details,
        })
        if stop_on_goal_satisfied and goal_atoms:
            goal = goal_satisfied(after_scene, goal_atoms)
            trace.events.append({"step": step.name, "event": "goal_check", "ok": goal.ok, "reason": goal.reason, "details": goal.details})
            if goal.ok:
                trace.goal_satisfied = True
                trace.handoff_to_vla = True
                trace.success = True
                trace.events.append({"step": step.name, "event": "goal_satisfied_after_step"})
                return current_obs, trace
        if (not post.ok) and post.hard and stop_on_hard_postcondition_failure:
            trace.events.append({"step": step.name, "event": "postcondition_failed_stop", "reason": post.reason})
            return current_obs, trace
    return current_obs, trace
