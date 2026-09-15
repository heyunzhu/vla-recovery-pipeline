from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .cutamp_like import CuTAMPPlanResult, CuTAMPStylePlanner, ParticleOptimizationConfig
from .human_fallback import HumanFallback, HumanFallbackRequest
from .optimized_executor import execute_optimized_plan
from .predicates import build_symbolic_state
from .scene_graph import SceneGraph, build_scene_graph
from .scene_reader import SceneState, read_scene
from .task_parser import ParsedTask, parse_task


@dataclass
class CuTAMPTipTopConfig:
    max_replans: int = 1
    max_recovery_steps: int = 140
    min_success_fraction: float = 0.01
    particle_cfg: ParticleOptimizationConfig = field(default_factory=ParticleOptimizationConfig)


@dataclass
class CuTAMPAttempt:
    attempt_idx: int
    parsed_task: ParsedTask
    scene_graph: SceneGraph
    selected_skeleton: str
    plan_reason: str
    plan_steps: List[str]
    best_cost: float
    success_fraction: float
    all_skeletons: List[Dict[str, Any]]
    planner_backend: Dict[str, Any] = field(default_factory=dict)
    executed_steps: List[str] = field(default_factory=list)
    num_env_steps: int = 0
    success_during_recovery: bool = False
    feasible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_idx": self.attempt_idx,
            "target": self.parsed_task.target_hint,
            "goal": self.parsed_task.goal_hint,
            "scene_graph": self.scene_graph.to_planner_context(),
            "selected_skeleton": self.selected_skeleton,
            "plan_reason": self.plan_reason,
            "plan_steps": self.plan_steps,
            "best_cost": self.best_cost,
            "success_fraction": self.success_fraction,
            "all_skeletons": self.all_skeletons,
            "planner_backend": self.planner_backend,
            "executed_steps": self.executed_steps,
            "num_env_steps": self.num_env_steps,
            "success_during_recovery": self.success_during_recovery,
            "feasible": self.feasible,
        }


@dataclass
class CuTAMPRecoveryResult:
    obs: Dict[str, Any]
    success: bool
    total_env_steps: int
    attempts: List[CuTAMPAttempt] = field(default_factory=list)
    human_requested: bool = False
    human_reason: str = ""
    abort_episode: bool = False
    abort_reason: str = ""

    @property
    def executed_steps(self) -> List[str]:
        out: List[str] = []
        for attempt in self.attempts:
            out.extend(attempt.executed_steps)
        return out


class CuTAMPOraclePerceiver:
    def perceive(self, env: Any, obs: Dict[str, Any], task_description: str) -> Tuple[SceneState, ParsedTask, SceneGraph]:
        scene = read_scene(env, obs)
        parsed = parse_task(task_description, scene.objects.keys(), env=env)
        sym = build_symbolic_state(scene, parsed)
        return scene, parsed, build_scene_graph(scene, parsed, sym)


class CuTAMPTipTopController:
    def __init__(
        self,
        cfg: CuTAMPTipTopConfig | None = None,
        perceiver: CuTAMPOraclePerceiver | None = None,
        planner: CuTAMPStylePlanner | None = None,
        human_fallback: HumanFallback | None = None,
    ) -> None:
        self.cfg = cfg or CuTAMPTipTopConfig()
        self.perceiver = perceiver or CuTAMPOraclePerceiver()
        self.planner = planner or CuTAMPStylePlanner(self.cfg.particle_cfg)
        self.human_fallback = human_fallback or HumanFallback()

    def recover(self, env: Any, obs: Dict[str, Any], task_description: str) -> CuTAMPRecoveryResult:
        current_obs = obs
        attempts: List[CuTAMPAttempt] = []
        total_env_steps = 0

        for attempt_idx in range(self.cfg.max_replans + 1):
            scene, parsed, graph = self.perceiver.perceive(env, current_obs, task_description)
            sym = build_symbolic_state(scene, parsed)
            plan_result: CuTAMPPlanResult = self.planner.plan(scene, sym)
            selected = plan_result.particle
            all_skeletons = [
                {
                    "name": item.skeleton.name,
                    "reason": item.skeleton.reason,
                    "steps": item.skeleton.steps,
                    "best_cost": item.best_cost,
                    "success_fraction": item.success_fraction,
                    "diagnostics": item.diagnostics,
                }
                for item in plan_result.all_particles
            ]
            feasible = selected.success_fraction >= self.cfg.min_success_fraction
            attempt = CuTAMPAttempt(
                attempt_idx=attempt_idx,
                parsed_task=parsed,
                scene_graph=graph,
                selected_skeleton=selected.skeleton.name,
                plan_reason=plan_result.plan.reason,
                plan_steps=plan_result.plan.names(),
                best_cost=selected.best_cost,
                success_fraction=selected.success_fraction,
                all_skeletons=all_skeletons,
                feasible=feasible,
            )

            if not feasible:
                attempts.append(attempt)
                human = self.human_fallback.request(
                    HumanFallbackRequest(
                        reason="no_feasible_particle",
                        planner_context=graph.to_planner_context(),
                        attempted_plans=[x.to_dict() for x in attempts],
                    )
                )
                return CuTAMPRecoveryResult(
                    obs=current_obs,
                    success=False,
                    total_env_steps=total_env_steps,
                    attempts=attempts,
                    human_requested=human.requested,
                    human_reason=human.reason,
                )

            remaining = max(1, self.cfg.max_recovery_steps - total_env_steps)
            current_obs, trace = execute_optimized_plan(env, current_obs, parsed, plan_result.plan, max_env_steps=remaining)
            attempt.executed_steps = list(trace.executed_steps)
            attempt.num_env_steps = trace.num_env_steps
            attempt.success_during_recovery = bool(trace.success)
            attempts.append(attempt)
            total_env_steps += trace.num_env_steps
            if trace.success:
                return CuTAMPRecoveryResult(obs=current_obs, success=True, total_env_steps=total_env_steps, attempts=attempts)
            if total_env_steps >= self.cfg.max_recovery_steps:
                break

        scene, parsed, graph = self.perceiver.perceive(env, current_obs, task_description)
        human = self.human_fallback.request(
            HumanFallbackRequest(
                reason="cutamp_replan_budget_exhausted",
                planner_context=graph.to_planner_context(),
                attempted_plans=[x.to_dict() for x in attempts],
            )
        )
        return CuTAMPRecoveryResult(
            obs=current_obs,
            success=False,
            total_env_steps=total_env_steps,
            attempts=attempts,
            human_requested=human.requested,
            human_reason=human.reason,
        )
