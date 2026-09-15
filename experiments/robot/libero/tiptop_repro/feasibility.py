from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .domain import RecoveryPlan
from .predicates import SymbolicState
from .scene_reader import SceneState


@dataclass
class FeasibilityReport:
    ok: bool
    reasons: List[str]
    cost: float = 0.0
    details: Dict[str, float] = field(default_factory=dict)


def check_plan(scene: SceneState, sym: SymbolicState, plan: RecoveryPlan, workspace_radius: float = 0.85) -> FeasibilityReport:
    reasons: List[str] = []
    if sym.target is None:
        reasons.append("no_target_object")
    elif float(np.linalg.norm(sym.target.pos[:2])) > workspace_radius:
        reasons.append("target_outside_workspace")

    for step in plan.steps:
        if step.name in {"move_above_object", "descend_to_grasp", "close_gripper", "lift"} and sym.target is None:
            reasons.append(f"{step.name}:missing_target")
        if step.name in {"move_above_goal", "slow_place"} and sym.goal is None:
            reasons.append(f"{step.name}:missing_goal")

    return FeasibilityReport(ok=len(reasons) == 0, reasons=sorted(set(reasons)))
