from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .executor import execute_plan
from .feasibility import FeasibilityReport, check_plan
from .human_fallback import HumanFallback, HumanFallbackRequest
from .planner import make_recovery_plan
from .predicates import build_symbolic_state
from .scene_graph import SceneGraph, build_scene_graph
from .scene_reader import SceneState, read_scene
from .task_parser import ParsedTask, parse_task


@dataclass
class TipTopConfig:
    max_replans: int = 2
    max_recovery_steps: int = 80


@dataclass
class TipTopAttempt:
    attempt_idx: int
    parsed_task: ParsedTask
    scene_graph: SceneGraph
    plan_reason: str
    plan_steps: List[str]
    feasible: bool
    feasibility_reasons: List[str] = field(default_factory=list)
    executed_steps: List[str] = field(default_factory=list)
    num_env_steps: int = 0
    success_during_recovery: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_idx": self.attempt_idx,
            "target": self.parsed_task.target_hint,
            "goal": self.parsed_task.goal_hint,
            "scene_graph": self.scene_graph.to_planner_context(),
            "plan_reason": self.plan_reason,
            "plan_steps": self.plan_steps,
            "feasible": self.feasible,
            "feasibility_reasons": self.feasibility_reasons,
            "executed_steps": self.executed_steps,
            "num_env_steps": self.num_env_steps,
            "success_during_recovery": self.success_during_recovery,
        }


@dataclass
class TipTopRecoveryResult:
    obs: Dict[str, Any]
    success: bool
    total_env_steps: int
    attempts: List[TipTopAttempt] = field(default_factory=list)
    human_requested: bool = False
    human_reason: str = ""

    @property
    def executed_steps(self) -> List[str]:
        out: List[str] = []
        for attempt in self.attempts:
            out.extend(attempt.executed_steps)
        return out

    def to_record(self) -> Dict[str, Any]:
        return {
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "human_requested": self.human_requested,
            "human_reason": self.human_reason,
            "total_env_steps": self.total_env_steps,
            "success": self.success,
        }


class OracleScenePerceiver:
    def perceive(self, env: Any, obs: Dict[str, Any], task_description: str) -> Tuple[SceneState, ParsedTask, SceneGraph]:
        scene = read_scene(env, obs)
        parsed = parse_task(task_description, scene.objects.keys())
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        return scene, parsed, graph


class RuleTaskPlanner:
    def plan(self, scene: SceneState, parsed_task: ParsedTask):
        sym = build_symbolic_state(scene, parsed_task)
        return make_recovery_plan(sym), sym


class TipTopRecoveryController:
    def __init__(
        self,
        cfg: TipTopConfig | None = None,
        perceiver: OracleScenePerceiver | None = None,
        planner: RuleTaskPlanner | None = None,
        human_fallback: HumanFallback | None = None,
    ) -> None:
        self.cfg = cfg or TipTopConfig()
        self.perceiver = perceiver or OracleScenePerceiver()
        self.planner = planner or RuleTaskPlanner()
        self.human_fallback = human_fallback or HumanFallback()

    def recover(self, env: Any, obs: Dict[str, Any], task_description: str) -> TipTopRecoveryResult:
        current_obs = obs
        attempts: List[TipTopAttempt] = []
        total_env_steps = 0

        for attempt_idx in range(self.cfg.max_replans + 1):
            scene, parsed, graph = self.perceiver.perceive(env, current_obs, task_description)
            plan, sym = self.planner.plan(scene, parsed)
            feasibility: FeasibilityReport = check_plan(scene, sym, plan)
            attempt = TipTopAttempt(
                attempt_idx=attempt_idx,
                parsed_task=parsed,
                scene_graph=graph,
                plan_reason=plan.reason,
                plan_steps=plan.names(),
                feasible=feasibility.ok,
                feasibility_reasons=list(feasibility.reasons),
            )

            if not feasibility.ok:
                attempts.append(attempt)
                request = HumanFallbackRequest(
                    reason="infeasible_plan",
                    planner_context=graph.to_planner_context(),
                    attempted_plans=[x.to_dict() for x in attempts],
                )
                human = self.human_fallback.request(request)
                return TipTopRecoveryResult(
                    obs=current_obs,
                    success=False,
                    total_env_steps=total_env_steps,
                    attempts=attempts,
                    human_requested=human.requested,
                    human_reason=human.reason,
                )

            remaining_steps = max(1, self.cfg.max_recovery_steps - total_env_steps)
            current_obs, trace = execute_plan(env, current_obs, parsed, plan, max_env_steps=remaining_steps)
            attempt.executed_steps = list(trace.executed_steps)
            attempt.num_env_steps = trace.num_env_steps
            attempt.success_during_recovery = bool(trace.success)
            attempts.append(attempt)
            total_env_steps += trace.num_env_steps
            if trace.success:
                return TipTopRecoveryResult(obs=current_obs, success=True, total_env_steps=total_env_steps, attempts=attempts)
            if total_env_steps >= self.cfg.max_recovery_steps:
                break

        scene, parsed, graph = self.perceiver.perceive(env, current_obs, task_description)
        request = HumanFallbackRequest(
            reason="replan_budget_exhausted",
            planner_context=graph.to_planner_context(),
            attempted_plans=[x.to_dict() for x in attempts],
        )
        human = self.human_fallback.request(request)
        return TipTopRecoveryResult(
            obs=current_obs,
            success=False,
            total_env_steps=total_env_steps,
            attempts=attempts,
            human_requested=human.requested,
            human_reason=human.reason,
        )
