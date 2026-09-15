from __future__ import annotations

from .domain import PlanStep, RecoveryPlan
from .predicates import SymbolicState


def make_recovery_plan(sym: SymbolicState) -> RecoveryPlan:
    p = sym.predicates
    if p.get("target_at_goal", False):
        return RecoveryPlan([PlanStep("retreat_open")], reason="already_at_goal")

    steps = [PlanStep("retreat_open")]
    if not p.get("near_target", False) or not p.get("nearest_is_target", False):
        steps.append(PlanStep("move_above_object"))
    steps.extend([PlanStep("descend_to_grasp"), PlanStep("close_gripper"), PlanStep("lift")])
    if p.get("has_goal", False):
        steps.extend([PlanStep("move_above_goal"), PlanStep("slow_place")])
    steps.append(PlanStep("retreat_open"))
    reason = "regrasp_and_place" if p.get("has_goal", False) else "regrasp_and_retreat"
    return RecoveryPlan(steps=steps, reason=reason)
