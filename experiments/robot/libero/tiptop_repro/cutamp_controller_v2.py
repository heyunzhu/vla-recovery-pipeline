from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Tuple

from .cutamp_controller import CuTAMPAttempt, CuTAMPRecoveryResult
from .cutamp_like import ParticleOptimizationConfig
from .human_fallback import HumanFallback, HumanFallbackRequest
from .libero_tiptop_executor import (
    _apply_confirmed_holding_latch,
    client_config_from_recovery_hints,
    execute_optimized_cutamp_plan,
    execute_recovery_entry_lift,
    execute_real_cutamp_executable_plan,
)
from .predicates import build_symbolic_state
from .real_cutamp_adapter import RealCuTAMPRecoveryPlanner, build_recovery_goal_candidates
from .real_cutamp_backend import RealCuTAMPBackend, RealCuTAMPBackendConfig
from .llm_client import LLMClientConfig
from .llm_recovery_goals import LLMRecoveryGoalGenerator
from .scene_graph import SceneGraph, build_scene_graph
from .scene_reader import SceneState, read_scene
from .skeleton_generator import RuleSkeletonGenerator, SkeletonGenerationResult
from .tamp_scene import TAMPProblem, build_tamp_problem
from .task_semantics import LLMTaskSemanticsInterpreter, RuleTaskSemanticsInterpreter, TaskSemanticsResult, build_rule_layer_record
from .task_parser import ParsedTask, parse_task

LOGGER = logging.getLogger(__name__)


@dataclass
class CuTAMPV2Config:
    max_replans: int = 1
    max_recovery_steps: int = 140
    min_success_fraction: float = 0.01
    particle_cfg: ParticleOptimizationConfig = field(default_factory=ParticleOptimizationConfig)
    use_real_cutamp_backend: bool = False
    real_cutamp_require_feasible: bool = False
    real_cutamp_primary_feasibility: bool = True
    execute_real_cutamp_plan: bool = True
    prefer_real_cutamp_executable_plan: bool = False
    require_real_cutamp_executable_plan: bool = False
    real_cutamp_cfg: RealCuTAMPBackendConfig = field(default_factory=RealCuTAMPBackendConfig)
    use_skeleton_generator: bool = True
    skeleton_backend: str = "rule"
    task_semantics_backend: str = field(default_factory=lambda: os.environ.get("TIPTOP_TASK_SEMANTICS_BACKEND", "rule"))
    recovery_goal_backend: str = field(default_factory=lambda: os.environ.get("TIPTOP_RECOVERY_GOAL_BACKEND", "rule"))
    recovery_goal_mode: str = "default"
    llm_cfg: LLMClientConfig = field(default_factory=LLMClientConfig.from_env)


class CuTAMPV2OraclePerceiver:
    def __init__(self, cfg: CuTAMPV2Config | None = None) -> None:
        self.cfg = cfg or CuTAMPV2Config()
        self.rule_task_semantics = RuleTaskSemanticsInterpreter()
        self.llm_task_semantics = None
        if self.cfg.task_semantics_backend in {"llm", "llm_with_rule_fallback"}:
            self.llm_task_semantics = LLMTaskSemanticsInterpreter(cfg=self.cfg.llm_cfg)
        self.skeleton_generator = RuleSkeletonGenerator()

    def _interpret_task_semantics(self, parsed: ParsedTask, graph: SceneGraph) -> TaskSemanticsResult:
        backend = self.cfg.task_semantics_backend
        if backend == "rule":
            return self.rule_task_semantics.interpret(parsed, graph)
        if backend in {"llm", "llm_with_rule_fallback"}:
            try:
                if self.llm_task_semantics is None:
                    self.llm_task_semantics = LLMTaskSemanticsInterpreter(cfg=self.cfg.llm_cfg)
                return self.llm_task_semantics.interpret(parsed, graph)
            except Exception as exc:
                if backend == "llm":
                    raise
                result = self.rule_task_semantics.interpret(parsed, graph)
                result.diagnostics["llm_fallback_error"] = str(exc)
                result.diagnostics["requested_backend"] = backend
                return result
        raise ValueError(f"Unsupported task_semantics_backend: {backend}")

    def perceive(
        self,
        env: Any,
        obs: Dict[str, Any],
        task_description: str,
        holding_latch: Dict[str, Any] | None = None,
    ) -> Tuple[SceneState, ParsedTask, SceneGraph, TAMPProblem, SkeletonGenerationResult, TaskSemanticsResult]:
        scene = read_scene(env, obs)
        _apply_confirmed_holding_latch(scene, holding_latch)
        parsed = parse_task(task_description, scene.objects.keys(), env=env)
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        task_semantics = self._interpret_task_semantics(parsed, graph)
        graph.task_atoms = list(task_semantics.task_atoms)
        graph.task_progress = dict(task_semantics.task_progress)
        graph.target = task_semantics.target_object or graph.target
        graph.goal = task_semantics.goal_object or graph.goal
        skeleton_result = self.skeleton_generator.generate(parsed, scene, graph, sym, task_semantics)
        goal_atoms = skeleton_result.goal_atoms if self.cfg.use_skeleton_generator else None
        goal_objects = skeleton_result.goal_objects if self.cfg.use_skeleton_generator else None
        tamp_problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal_atoms,
            surface_names=goal_objects,
            init_atoms=graph.world_atoms,
            required_final_atoms=task_semantics.required_final_atoms,
        )
        return scene, parsed, graph, tamp_problem, skeleton_result, task_semantics


class CuTAMPV2TipTopController:
    def __init__(
        self,
        cfg: CuTAMPV2Config | None = None,
        perceiver: CuTAMPV2OraclePerceiver | None = None,
        human_fallback: HumanFallback | None = None,
    ) -> None:
        self.cfg = cfg or CuTAMPV2Config()
        self.perceiver = perceiver or CuTAMPV2OraclePerceiver(self.cfg)
        self.real_cutamp = RealCuTAMPBackend(self.cfg.real_cutamp_cfg) if self.cfg.use_real_cutamp_backend else None
        llm_goal_generator = None
        if self.cfg.recovery_goal_backend in {"llm", "llm_with_rule_fallback"}:
            llm_goal_generator = LLMRecoveryGoalGenerator(cfg=self.cfg.llm_cfg)
        elif self.cfg.recovery_goal_backend != "rule":
            raise ValueError(f"Unsupported recovery_goal_backend: {self.cfg.recovery_goal_backend}")
        self.real_cutamp_recovery = (
            RealCuTAMPRecoveryPlanner(backend=self.real_cutamp, llm_goal_generator=llm_goal_generator)
            if self.real_cutamp is not None
            else None
        )
        if self.real_cutamp_recovery is not None:
            self.real_cutamp_recovery.goal_mode = self.cfg.recovery_goal_mode
        self.human_fallback = human_fallback or HumanFallback()

    def recover(
        self,
        env: Any,
        obs: Dict[str, Any],
        task_description: str,
        step_callback: Callable[[Dict[str, Any], Dict[str, Any]], None] | None = None,
        hook_bridge: Any = None,
        recovery_hints: Mapping[str, Any] | None = None,
    ) -> CuTAMPRecoveryResult:
        current_obs = obs
        attempts: List[CuTAMPAttempt] = []
        total_env_steps = 0
        hints = dict(recovery_hints or {})
        holding_latch: Dict[str, Any] = {}
        client_cfg = client_config_from_recovery_hints(hints)
        entry_lift_event: Dict[str, Any] | None = None
        entry_lift_attached = False
        if (
            client_cfg is not None
            and float(client_cfg.recovery_entry_lift_m) > 0.0
            and int(client_cfg.recovery_entry_lift_max_steps) > 0
        ):
            current_obs, entry_lift_event = execute_recovery_entry_lift(
                env,
                current_obs,
                client_cfg=client_cfg,
                max_env_steps=self.cfg.max_recovery_steps,
                step_callback=step_callback,
                holding_latch=holding_latch,
            )
            total_env_steps += int(entry_lift_event.get("env_steps") or 0)
            if bool(entry_lift_event.get("done")):
                return CuTAMPRecoveryResult(
                    obs=current_obs,
                    success=True,
                    total_env_steps=total_env_steps,
                    attempts=attempts,
                )

        for attempt_idx in range(self.cfg.max_replans + 1):
            scene, parsed, graph, tamp_problem, skeleton_result, task_semantics = self.perceiver.perceive(
                env,
                current_obs,
                task_description,
                holding_latch=holding_latch,
            )
            sym = build_symbolic_state(scene, parsed)
            real_cutamp_record: Dict[str, Any] = {}
            real_cutamp_feasible = False
            real_plan = None
            if self.real_cutamp_recovery is not None and self.cfg.real_cutamp_primary_feasibility:
                real_plan = self.real_cutamp_recovery.plan(
                    scene,
                    parsed,
                    sym,
                    graph,
                    task_semantics,
                    recovery_hints=hints,
                )
                real_cutamp_record = real_plan.to_dict()
                real_cutamp_feasible = bool(real_plan.feasible)

            all_skeletons: List[Dict[str, Any]] = []
            feasible = False
            if self.real_cutamp is not None and not self.cfg.real_cutamp_primary_feasibility:
                real_result = self.real_cutamp.solve(tamp_problem, recovery_hints=hints)
                real_cutamp_record = real_result.to_dict()
                real_cutamp_feasible = bool(real_result.feasible)
            if self.cfg.execute_real_cutamp_plan and real_cutamp_feasible:
                feasible = True
            if self.cfg.real_cutamp_require_feasible and not real_cutamp_feasible:
                feasible = False
            planner_backend: Dict[str, Any] = {
                "task_semantics": task_semantics.to_dict(),
                "skeleton_generator": skeleton_result.to_dict(),
                "skeleton_backend": self.cfg.skeleton_backend,
                "recovery_hints": hints,
            }
            rule_goals = list(getattr(real_plan, "rule_goals", None) or []) if real_plan is not None else []
            if not rule_goals:
                from .recovery_symbols import build_recovery_symbolic_abstraction

                recovery = build_recovery_symbolic_abstraction(scene, sym, graph)
                rule_goals = build_recovery_goal_candidates(
                    scene,
                    parsed,
                    sym,
                    task_semantics,
                    recovery=recovery,
                    graph=graph,
                    mode=self.cfg.recovery_goal_mode,
                    recovery_hints=hints,
                )
            rule_record = build_rule_layer_record(parsed, task_semantics, recovery_goals=rule_goals)
            planner_backend["rule_layer"] = rule_record
            LOGGER.info("recovery rule layer: %s", json.dumps(rule_record, ensure_ascii=False))
            if real_cutamp_record:
                planner_backend["real_cutamp"] = real_cutamp_record
            planner_backend["execution_bridge_diagnostics"] = {
                "real_cutamp_feasible": bool(real_cutamp_feasible),
                "lite_planner_removed": True,
            }
            if entry_lift_event is not None and not entry_lift_attached:
                planner_backend["execution_bridge_diagnostics"]["recovery_entry_lift"] = entry_lift_event
                entry_lift_attached = True
            attempt = CuTAMPAttempt(
                attempt_idx=attempt_idx,
                parsed_task=parsed,
                scene_graph=graph,
                selected_skeleton="",
                plan_reason="real_cutamp_not_selected",
                plan_steps=[],
                best_cost=0.0,
                success_fraction=1.0 if real_cutamp_feasible else 0.0,
                all_skeletons=all_skeletons,
                planner_backend=planner_backend,
                feasible=feasible,
            )
            executable_plan = None
            optimized_plan = None
            execution_source = "real_cutamp_no_optimized_solution"
            execution_goal_atoms = None
            if self.cfg.execute_real_cutamp_plan and real_plan is not None and real_plan.selected is not None:
                execution_goal_atoms = list(real_plan.selected.goal.atoms)
                selected_result = real_plan.selected.result
                planner_backend["execution_bridge_diagnostics"].update(
                    {
                        "selected_recovery_goal": real_plan.selected.goal.name,
                        "selected_recovery_goal_reason": real_plan.selected.goal.reason,
                        "selected_recovery_goal_atoms": [
                            atom.to_dict() if hasattr(atom, "to_dict") else str(atom)
                            for atom in execution_goal_atoms
                        ],
                        "selected_recovery_goal_surfaces": list(real_plan.selected.goal.surface_names),
                    }
                )
                if self.cfg.prefer_real_cutamp_executable_plan and selected_result.executable_plan:
                    executable_plan = list(selected_result.executable_plan)
                    execution_source = "real_cutamp_executable_plan"
                    attempt.selected_skeleton = real_plan.selected.goal.name
                    attempt.plan_reason = f"real_cutamp_executable_plan:{real_plan.selected.goal.name}:{real_plan.selected.goal.reason}"
                    attempt.plan_steps = [str(step.get("label") or step.get("type") or f"step_{idx}") for idx, step in enumerate(executable_plan)]
                    planner_backend["execution_bridge_diagnostics"].update(
                        {"bridge": "curobo_joint_trajectory", "executable_plan_len": len(executable_plan)}
                    )
                elif self.cfg.prefer_real_cutamp_executable_plan and self.cfg.require_real_cutamp_executable_plan:
                    execution_source = "real_cutamp_executable_plan_missing"
                    feasible = False
                    attempt.selected_skeleton = real_plan.selected.goal.name
                    attempt.plan_reason = f"missing_real_cutamp_executable_plan:{real_plan.selected.goal.name}:{real_plan.selected.goal.reason}"
                    attempt.plan_steps = []
                    planner_backend["execution_bridge_diagnostics"].update(
                        {"bridge": "missing_curobo_joint_trajectory", "executable_plan_len": 0}
                    )
                elif selected_result.optimized_plan:
                    optimized_plan = dict(selected_result.optimized_plan)
                    execution_source = "real_cutamp_optimized_libero_bridge"
                    attempt.selected_skeleton = real_plan.selected.goal.name
                    attempt.plan_reason = f"real_cutamp_optimized_solution:{real_plan.selected.goal.name}:{real_plan.selected.goal.reason}"
                    attempt.plan_steps = [
                        str(operator.get("label") or operator.get("name") or f"operator_{idx}")
                        for idx, operator in enumerate(optimized_plan.get("operators", []))
                    ]
                    planner_backend["execution_bridge_diagnostics"].update(
                        {
                            "bridge": "optimized_cutamp_to_libero_delta_eef",
                            "optimized_operator_count": len(attempt.plan_steps),
                            "optimized_binding_count": len(optimized_plan.get("bindings", {})),
                        }
                    )
                else:
                    execution_source = "real_cutamp_optimized_solution_missing"
                    feasible = False
                    attempt.selected_skeleton = real_plan.selected.goal.name
                    attempt.plan_reason = f"missing_real_cutamp_optimized_solution:{real_plan.selected.goal.name}:{real_plan.selected.goal.reason}"
                    attempt.plan_steps = []
                    planner_backend["execution_bridge_diagnostics"].update(
                        {"bridge": "missing_optimized_cutamp_solution", "optimized_operator_count": 0}
                    )
            if self.real_cutamp_recovery is None:
                feasible = False
                attempt.plan_reason = "real_cutamp_backend_required"
                attempt.plan_steps = []
                execution_source = "real_cutamp_backend_required"
            elif not real_cutamp_feasible:
                feasible = False
                if attempt.plan_reason in {"", "real_cutamp_not_selected"}:
                    attempt.plan_reason = "real_cutamp_no_feasible_goal"
                if execution_source in {"real_cutamp_no_optimized_solution", "real_cutamp_not_selected"}:
                    execution_source = "real_cutamp_no_feasible_goal"
                attempt.plan_steps = []
            attempt.feasible = feasible
            attempt.planner_backend["execution_source"] = execution_source
            if not feasible:
                attempts.append(attempt)
                attempt_dict = attempt.to_dict()
                attempt_dict["tamp_problem"] = tamp_problem.to_dict()
                human = self.human_fallback.request(
                    HumanFallbackRequest(
                        reason="no_feasible_particle",
                        planner_context={**graph.to_planner_context(), "tamp_problem": tamp_problem.to_dict()},
                        attempted_plans=[attempt_dict],
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
            if execution_source == "real_cutamp_executable_plan" and executable_plan is not None:
                current_obs, trace = execute_real_cutamp_executable_plan(
                    env,
                    current_obs,
                    parsed,
                    executable_plan,
                    max_env_steps=remaining,
                    goal_atoms=execution_goal_atoms,
                    stop_on_goal_satisfied=True,
                    client_cfg=client_cfg,
                    step_callback=step_callback,
                    hook_bridge=hook_bridge,
                    holding_latch=holding_latch,
                )
            elif execution_source == "real_cutamp_optimized_libero_bridge" and optimized_plan is not None:
                current_obs, trace = execute_optimized_cutamp_plan(
                    env,
                    current_obs,
                    optimized_plan,
                    max_env_steps=remaining,
                    goal_atoms=execution_goal_atoms,
                    stop_on_goal_satisfied=True,
                    client_cfg=client_cfg,
                    step_callback=step_callback,
                    hook_bridge=hook_bridge,
                    holding_latch=holding_latch,
                )
            else:
                raise RuntimeError(f"No optimized cuTAMP execution route for source={execution_source}")
            attempt.plan_steps = list(getattr(trace, "plan_steps", attempt.plan_steps))
            attempt.executed_steps = list(trace.executed_steps)
            attempt.num_env_steps = trace.num_env_steps
            attempt.success_during_recovery = bool(trace.success)
            attempt.planner_backend["execution_trace"] = {
                "goal_satisfied": bool(getattr(trace, "goal_satisfied", False)),
                "handoff_to_vla": bool(getattr(trace, "handoff_to_vla", False)),
                "abort_episode": bool(getattr(trace, "abort_episode", False)),
                "abort_reason": str(getattr(trace, "abort_reason", "") or ""),
                "done": bool(trace.done),
                "events": list(trace.events),
            }
            attempts.append(attempt)
            total_env_steps += trace.num_env_steps
            if bool(getattr(trace, "abort_episode", False)):
                return CuTAMPRecoveryResult(
                    obs=current_obs,
                    success=False,
                    total_env_steps=total_env_steps,
                    attempts=attempts,
                    abort_episode=True,
                    abort_reason=str(getattr(trace, "abort_reason", "") or "recovery_abort_episode"),
                )
            if trace.success or bool(getattr(trace, "handoff_to_vla", False)):
                return CuTAMPRecoveryResult(
                    obs=current_obs,
                    success=bool(trace.success),
                    total_env_steps=total_env_steps,
                    attempts=attempts,
                )
            if total_env_steps >= self.cfg.max_recovery_steps:
                break

        scene, parsed, graph, tamp_problem, skeleton_result, task_semantics = self.perceiver.perceive(
            env,
            current_obs,
            task_description,
            holding_latch=holding_latch,
        )
        human = self.human_fallback.request(
            HumanFallbackRequest(
                reason="cutamp_v2_replan_budget_exhausted",
                planner_context={**graph.to_planner_context(), "tamp_problem": tamp_problem.to_dict()},
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
