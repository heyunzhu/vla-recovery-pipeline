from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .domain import PlanStep, RecoveryPlan
from .feasibility import check_plan
from .predicates import SymbolicState
from .scene_reader import SceneState
from .skills import SkillConfig, actions_for_step


@dataclass
class RecoveryCandidate:
    candidate_id: str
    skeleton_id: str
    plan: RecoveryPlan
    skill_cfg: SkillConfig
    continuous_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateScore:
    ok: bool
    cost: float
    reasons: List[str] = field(default_factory=list)
    details: Dict[str, float] = field(default_factory=dict)


@dataclass
class SelectedRecovery:
    candidate: Optional[RecoveryCandidate]
    score: CandidateScore
    ranked: List[Dict[str, Any]] = field(default_factory=list)


def _plan(names: List[str], reason: str, args: Optional[Dict[str, Dict[str, Any]]] = None) -> RecoveryPlan:
    args = args or {}
    return RecoveryPlan([PlanStep(name, dict(args.get(name, {}))) for name in names], reason=reason)


def generate_plan_skeletons(sym: SymbolicState) -> List[RecoveryPlan]:
    p = sym.predicates
    plans: List[RecoveryPlan] = []

    if p.get("target_at_goal", False):
        plans.append(
            _plan(
                ["micro_lift", "retreat_open"],
                "stabilize_at_goal",
                {
                    "micro_lift": {"height": 0.025, "steps": 3, "gripper": 1.0},
                    "retreat_open": {"lift": 0.035, "back": 0.012, "up_steps": 3, "back_steps": 2},
                },
            )
        )

    plans.extend(
        [
            _plan(["micro_lift", "retreat_open"], "minimal_lift_retreat"),
            _plan(["open_gripper", "retreat_open"], "open_and_retreat"),
        ]
    )

    if sym.target is not None:
        plans.append(_plan(["move_above_object", "descend_to_grasp", "close_gripper", "lift"], "regrasp_target"))
        if p.get("has_goal", False):
            plans.append(
                _plan(
                    ["move_above_object", "descend_to_grasp", "close_gripper", "lift", "move_above_goal", "slow_place", "retreat_open"],
                    "regrasp_and_place",
                )
            )
    return plans


def _copy_plan_with_profile(plan: RecoveryPlan, profile: Dict[str, Any]) -> RecoveryPlan:
    steps: List[PlanStep] = []
    for step in plan.steps:
        args = dict(step.args)
        if step.name == "micro_lift":
            args.setdefault("height", profile["micro_lift"])
            args.setdefault("steps", profile["short_steps"])
        elif step.name == "retreat_open":
            args.setdefault("lift", profile["retreat_lift"])
            args.setdefault("back", profile["retreat_back"])
            args.setdefault("up_steps", profile["short_steps"])
            args.setdefault("back_steps", max(2, profile["short_steps"] - 1))
        elif step.name == "open_gripper":
            args.setdefault("steps", profile["gripper_steps"])
        elif step.name == "move_above_object":
            args.setdefault("height", profile["pregrasp_height"])
            args.setdefault("steps", profile["move_steps"])
        elif step.name == "descend_to_grasp":
            args.setdefault("height", profile["grasp_height"])
            args.setdefault("steps", profile["move_steps"])
        elif step.name == "close_gripper":
            args.setdefault("steps", profile["gripper_steps"])
        elif step.name == "lift":
            args.setdefault("height", profile["lift_height"])
            args.setdefault("steps", profile["move_steps"])
        elif step.name == "move_above_goal":
            args.setdefault("height", profile["lift_height"])
            args.setdefault("steps", profile["move_steps"])
        elif step.name == "slow_place":
            args.setdefault("descend", profile["place_descend"])
            args.setdefault("descend_steps", profile["move_steps"])
            args.setdefault("release_steps", profile["gripper_steps"])
        steps.append(PlanStep(step.name, args))
    return RecoveryPlan(steps, reason=plan.reason)


def generate_continuous_candidates(sym: SymbolicState, max_candidates: int = 48) -> List[RecoveryCandidate]:
    profiles = [
        {
            "name": "gentle",
            "max_delta": 0.035,
            "pregrasp_height": 0.09,
            "grasp_height": 0.035,
            "lift_height": 0.10,
            "place_descend": 0.16,
            "micro_lift": 0.025,
            "retreat_lift": 0.035,
            "retreat_back": 0.012,
            "short_steps": 3,
            "move_steps": 5,
            "gripper_steps": 3,
        },
        {
            "name": "medium",
            "max_delta": 0.055,
            "pregrasp_height": 0.13,
            "grasp_height": 0.03,
            "lift_height": 0.14,
            "place_descend": 0.22,
            "micro_lift": 0.04,
            "retreat_lift": 0.055,
            "retreat_back": 0.025,
            "short_steps": 4,
            "move_steps": 7,
            "gripper_steps": 4,
        },
        {
            "name": "strong",
            "max_delta": 0.075,
            "pregrasp_height": 0.17,
            "grasp_height": 0.025,
            "lift_height": 0.18,
            "place_descend": 0.28,
            "micro_lift": 0.055,
            "retreat_lift": 0.075,
            "retreat_back": 0.04,
            "short_steps": 5,
            "move_steps": 8,
            "gripper_steps": 5,
        },
    ]
    candidates: List[RecoveryCandidate] = []
    for skeleton_idx, skeleton in enumerate(generate_plan_skeletons(sym)):
        for profile in profiles:
            cfg = SkillConfig(
                max_delta=profile["max_delta"],
                pregrasp_height=profile["pregrasp_height"],
                grasp_height=profile["grasp_height"],
                lift_height=profile["lift_height"],
                steps_per_move=profile["move_steps"],
                gripper_steps=profile["gripper_steps"],
            )
            plan = _copy_plan_with_profile(skeleton, profile)
            candidates.append(
                RecoveryCandidate(
                    candidate_id=f"s{skeleton_idx}_{profile['name']}",
                    skeleton_id=skeleton.reason,
                    plan=plan,
                    skill_cfg=cfg,
                    continuous_params={k: v for k, v in profile.items() if k != "name"},
                )
            )
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def _plan_has(plan: RecoveryPlan, name: str) -> bool:
    return any(step.name == name for step in plan.steps)


def score_candidate(scene: SceneState, sym: SymbolicState, candidate: RecoveryCandidate, max_env_steps: int = 80) -> CandidateScore:
    report = check_plan(scene, sym, candidate.plan)
    reasons = list(report.reasons)
    actions = []
    for step in candidate.plan.steps:
        actions.extend(actions_for_step(step, scene, sym, candidate.skill_cfg))
    if not actions:
        reasons.append("no_actions")
    if len(actions) > max_env_steps:
        reasons.append("too_many_env_steps")

    arr = np.asarray(actions, dtype=np.float32) if actions else np.zeros((0, 7), dtype=np.float32)
    deltas = arr[:, :3] if arr.size else np.zeros((0, 3), dtype=np.float32)
    grips = arr[:, 6] if arr.size else np.zeros((0,), dtype=np.float32)
    motion_l1 = float(np.abs(deltas).sum())
    max_step = float(np.abs(deltas).max()) if deltas.size else 0.0
    gripper_switches = float(np.sum(np.abs(np.diff(grips)) > 0.5)) if grips.size > 1 else 0.0
    plan_len = float(len(actions))

    p = sym.predicates
    # Keep disturbance low, but do not let the shortest disengage motion always win.
    # The selector should prefer task-progress skeletons when target/goal are known and
    # the object is not already at the goal.
    cost = 0.06 * plan_len + 1.15 * motion_l1 + 2.0 * max_step + 0.25 * gripper_switches

    if candidate.skeleton_id == "open_and_retreat":
        cost += 0.15
    elif candidate.skeleton_id == "minimal_lift_retreat":
        cost += 0.35
    elif candidate.skeleton_id == "regrasp_target":
        cost += 0.25
    elif candidate.skeleton_id == "regrasp_and_place":
        cost += 0.50

    if p.get("target_at_goal", False):
        if _plan_has(candidate.plan, "descend_to_grasp") or _plan_has(candidate.plan, "slow_place"):
            cost += 8.0
            reasons.append("would_disturb_target_at_goal")
        if candidate.skeleton_id in {"open_and_retreat", "minimal_lift_retreat"}:
            cost -= 0.4
    elif p.get("has_goal", False):
        if candidate.skeleton_id in {"open_and_retreat", "minimal_lift_retreat"}:
            cost += 1.75
        if candidate.skeleton_id == "regrasp_target":
            cost -= 1.25
        if candidate.skeleton_id == "regrasp_and_place":
            cost -= 2.25
        if p.get("near_target", False):
            if candidate.skeleton_id == "regrasp_target":
                cost -= 0.75
            if candidate.skeleton_id == "regrasp_and_place":
                cost -= 1.0
        if p.get("target_reachable", False):
            if candidate.skeleton_id == "regrasp_target":
                cost -= 0.35
            if candidate.skeleton_id == "regrasp_and_place":
                cost -= 0.55

    if _plan_has(candidate.plan, "slow_place"):
        cost += 0.20
    if _plan_has(candidate.plan, "descend_to_grasp"):
        cost += 0.10
    if not p.get("near_target", False) and not _plan_has(candidate.plan, "move_above_object"):
        cost += 1.5
    if not p.get("nearest_is_target", True) and _plan_has(candidate.plan, "descend_to_grasp"):
        cost += 1.25

    details = {
        "plan_len": plan_len,
        "motion_l1": motion_l1,
        "max_step": max_step,
        "gripper_switches": gripper_switches,
    }
    hard_reasons = [r for r in reasons if r in {"no_actions", "too_many_env_steps"} or r.startswith(("no_", "target_outside", "move_above", "descend", "close", "lift", "slow_place"))]
    ok = report.ok and not hard_reasons
    if not ok:
        cost += 100.0 + 10.0 * len(hard_reasons)
    return CandidateScore(ok=ok, cost=float(cost), reasons=sorted(set(reasons)), details=details)


def _rank_item(candidate: RecoveryCandidate, score: CandidateScore) -> Dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "skeleton_id": candidate.skeleton_id,
        "cost": float(score.cost),
        "ok": bool(score.ok),
        "reasons": score.reasons,
        "plan_steps": candidate.plan.names(),
        "continuous_params": candidate.continuous_params,
        "details": score.details,
    }


def select_recovery_candidate(scene: SceneState, sym: SymbolicState, max_env_steps: int = 80, max_candidates: int = 48) -> SelectedRecovery:
    scored = []
    for candidate in generate_continuous_candidates(sym, max_candidates=max_candidates):
        score = score_candidate(scene, sym, candidate, max_env_steps=max_env_steps)
        scored.append((candidate, score))
    scored.sort(key=lambda item: (not item[1].ok, item[1].cost))
    ranked = [_rank_item(candidate, score) for candidate, score in scored]
    for candidate, score in scored:
        if score.ok:
            return SelectedRecovery(candidate=candidate, score=score, ranked=ranked)
    if scored:
        candidate, score = scored[0]
        return SelectedRecovery(candidate=None, score=score, ranked=ranked)
    return SelectedRecovery(candidate=None, score=CandidateScore(ok=False, cost=999.0, reasons=["no_candidates"]), ranked=[])
