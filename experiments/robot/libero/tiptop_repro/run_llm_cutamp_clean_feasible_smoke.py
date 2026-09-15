from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.real_cutamp_adapter import RealCuTAMPRecoveryPlanner, build_recovery_goal_candidates
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackendConfig
from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.task_parser import parse_task
from experiments.robot.libero.tiptop_repro.task_semantics import LLMTaskSemanticsInterpreter, RuleTaskSemanticsInterpreter
from experiments.robot.libero.tiptop_repro.predicates import build_symbolic_state
from experiments.robot.libero.tiptop_repro.scene_graph import build_scene_graph


def _object(name: str, pos: list[float], kind: str) -> ObjectState:
    if kind == "container":
        geometry: Dict[str, Any] = {
            "source": "clean_smoke_proxy",
            "geoms": [
                {
                    "name": f"{name}_box",
                    "type": 6,
                    "size": [0.09, 0.09, 0.04],
                    "pos": pos,
                    "mesh_id": None,
                }
            ],
        }
    else:
        geometry = {
            "source": "clean_smoke_proxy",
            "geoms": [
                {
                    "name": f"{name}_box",
                    "type": 6,
                    "size": [0.035, 0.025, 0.025],
                    "pos": pos,
                    "mesh_id": None,
                }
            ],
        }
    return ObjectState(name=name, pos=np.asarray(pos, dtype=np.float32), quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32), geometry=geometry)


def build_clean_scene() -> SceneState:
    objects = {
        "cream_cheese_1_main": _object("cream_cheese_1_main", [0.55, -0.30, 0.04], "box"),
        "butter_1_main": _object("butter_1_main", [0.40, -0.325, 0.04], "box"),
        "basket_1_main": _object("basket_1_main", [0.55, 0.00, 0.04], "container"),
    }
    return SceneState(
        ee_pos=np.asarray([0.45, -0.25, 0.25], dtype=np.float32),
        ee_quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, 0.04], dtype=np.float32),
        objects=objects,
        raw_obs_keys=(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="put both the cream cheese box and the butter in the basket")
    parser.add_argument("--scenario", default="default", choices=["default", "pick_cream"])
    parser.add_argument("--task_semantics_backend", default="llm_with_rule_fallback", choices=["rule", "llm", "llm_with_rule_fallback"])
    parser.add_argument("--solve_real_cutamp", action="store_true")
    parser.add_argument("--runner_python", default="")
    parser.add_argument("--num_particles", type=int, default=32)
    parser.add_argument("--num_opt_steps", type=int, default=10)
    parser.add_argument("--max_loop_dur", type=float, default=12.0)
    parser.add_argument("--output_json", default="")
    parser.add_argument("--max_goals", type=int, default=0)
    args = parser.parse_args()

    if args.scenario == "pick_cream":
        args.task = "pick up the cream cheese box"

    scene = build_clean_scene()
    parsed = parse_task(args.task, scene.objects.keys())
    sym = build_symbolic_state(scene, parsed)
    graph = build_scene_graph(scene, parsed, sym)
    if args.task_semantics_backend == "rule":
        task_semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
    elif args.task_semantics_backend == "llm":
        task_semantics = LLMTaskSemanticsInterpreter().interpret(parsed, graph)
    else:
        try:
            task_semantics = LLMTaskSemanticsInterpreter().interpret(parsed, graph)
        except Exception as exc:
            task_semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
            task_semantics.diagnostics["llm_fallback_error"] = str(exc)
            task_semantics.diagnostics["requested_backend"] = args.task_semantics_backend
    graph.task_atoms = list(task_semantics.task_atoms)
    graph.task_progress = dict(task_semantics.task_progress)
    graph.target = task_semantics.target_object or graph.target
    graph.goal = task_semantics.goal_object or graph.goal

    goals = build_recovery_goal_candidates(scene, parsed, sym, task_semantics)
    if args.max_goals > 0:
        goals = goals[: args.max_goals]
    result: Dict[str, Any] = {
        "task": args.task,
        "backend": args.task_semantics_backend,
        "task_semantics": task_semantics.to_dict(),
        "goal_candidates": [goal.to_dict() for goal in goals],
        "real_cutamp_attempts": [],
    }
    result["task_semantics"]["prompt"] = result["task_semantics"].get("prompt", "")[:1200]
    result["task_semantics"]["raw_response"] = result["task_semantics"].get("raw_response", "")[:3000]

    if args.solve_real_cutamp:
        planner = RealCuTAMPRecoveryPlanner(
            cfg=RealCuTAMPBackendConfig(
                runner_python=args.runner_python,
                num_particles=args.num_particles,
                num_opt_steps=args.num_opt_steps,
                max_loop_dur=args.max_loop_dur,
                runner_timeout_sec=max(args.max_loop_dur + 180.0, 240.0),
            )
        )
        original_build_goals = None
        if args.max_goals > 0:
            from experiments.robot.libero.tiptop_repro import real_cutamp_adapter as adapter_mod

            original_build_goals = adapter_mod.build_recovery_goal_candidates
            adapter_mod.build_recovery_goal_candidates = lambda *_args, **_kwargs: goals
        try:
            plan = planner.plan(scene, parsed, sym, graph, task_semantics)
        finally:
            if original_build_goals is not None:
                adapter_mod.build_recovery_goal_candidates = original_build_goals
        result["real_cutamp"] = {
            "feasible": plan.feasible,
            "selected_goal": None if plan.selected is None else plan.selected.goal.to_dict(),
            "fallback_reason": plan.fallback_reason,
            "num_attempts": len(plan.attempts),
        }
        result["real_cutamp_attempts"] = [
            {
                "goal": attempt.goal.to_dict(),
                "available": attempt.result.available,
                "feasible": attempt.result.feasible,
                "num_satisfying": attempt.result.num_satisfying,
                "failure_reason": attempt.result.failure_reason,
                "elapsed_sec": attempt.result.elapsed_sec,
                "plan_summary": attempt.result.diagnostics.get("plan_summary", []),
                "goal_notes": attempt.result.diagnostics.get("goal_notes", []),
                "fluent_mapping": attempt.problem.fluent_mapping,
                "movables": [obj.name for obj in attempt.problem.movables],
                "surfaces": [obj.name for obj in attempt.problem.surfaces],
            }
            for attempt in plan.attempts
        ]

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
