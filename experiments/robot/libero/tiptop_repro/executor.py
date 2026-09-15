from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np

from .domain import RecoveryPlan
from .predicates import build_symbolic_state
from .scene_reader import read_scene
from .skills import SkillConfig, actions_for_step
from .task_parser import ParsedTask


@dataclass
class ExecutionTrace:
    plan_reason: str
    plan_steps: List[str]
    executed_steps: List[str] = field(default_factory=list)
    num_env_steps: int = 0
    done: bool = False
    success: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)


def execute_plan(
    env: Any,
    obs: Dict[str, Any],
    parsed_task: ParsedTask,
    plan: RecoveryPlan,
    max_env_steps: int = 80,
    skill_cfg: SkillConfig | None = None,
) -> Tuple[Dict[str, Any], ExecutionTrace]:
    cfg = skill_cfg or SkillConfig()
    trace = ExecutionTrace(plan_reason=plan.reason, plan_steps=plan.names())
    current_obs = obs

    for step in plan.steps:
        scene = read_scene(env, current_obs)
        sym = build_symbolic_state(scene, parsed_task)
        actions = actions_for_step(step, scene, sym, cfg)
        if not actions:
            trace.events.append({"step": step.name, "event": "no_actions"})
            continue
        trace.executed_steps.append(step.name)
        for action in actions:
            current_obs, _, done, _ = env.step(np.asarray(action, dtype=np.float32).tolist())
            trace.num_env_steps += 1
            if done:
                trace.done = True
                trace.success = True
                return current_obs, trace
            if trace.num_env_steps >= max_env_steps:
                trace.events.append({"step": step.name, "event": "max_env_steps"})
                return current_obs, trace
    return current_obs, trace
