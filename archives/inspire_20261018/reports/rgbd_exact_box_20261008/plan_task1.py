"""Plan spatial task 1 from the camera boxes and from the simulator objects."""
import json
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.skill_pipeline.visual_planning_input import build_visual_planning_input
from experiments.robot.libero.skill_pipeline.visual_tamp_adapter import build_visual_tamp_problem
from experiments.robot.libero.tiptop_repro.predicates import build_symbolic_state
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict,
)
from experiments.robot.libero.tiptop_repro.scene_graph import build_scene_graph
from experiments.robot.libero.tiptop_repro.scene_types import ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.tamp_scene import build_tamp_problem
from experiments.robot.libero.tiptop_repro.task_parser import parse_task

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008")
task_root = root / "task1"
model = root / "static_panda_model"
stash = {}
import cutamp.cost_function as cost_function
_original_cost = cost_function.CostFunction.__call__

def _remember(self, rollout):
    result = _original_cost(self, rollout)
    if torch.is_grad_enabled():
        return result
    stats = {}
    for cost_type, info in result.items():
        if info.get("type") != "constraint":
            continue
        for name, values in info["values"].items():
            data = values.detach().float()
            reduced = data.amax(dim=1) if data.ndim == 2 else data
            stats[f"{cost_type}/{name}"] = {"min": round(float(reduced.min()), 5), "median": round(float(reduced.median()), 5)}
    stash["constraint_stats"] = stats
    return result

cost_function.CostFunction.__call__ = _remember

def solve(cfg, problem):
    stash.clear()
    with OracleImportGuard():
        result = RealCuTAMPBackend(cfg).solve(problem)
    return {
        "feasible": result.feasible,
        "failure_reason": result.failure_reason,
        "num_satisfying": result.num_satisfying,
        "elapsed_sec": round(float(result.elapsed_sec), 3),
        "executable_plan_present": bool(result.executable_plan),
        "environment_actions": 0,
        "constraint_stats": stash.get("constraint_stats"),
    }

shared = dict(
    enable_initial_holding_prebinding=False,
    curobo_plan=True,
    serialize_trajectories=True,
    accept_optimized_plan_if_motiongen_fails=False,
    project_motiongen_start_joint_limits=False,
    dummy_obstacle_if_empty=False,
    num_particles=64,
    num_opt_steps=40,
    max_loop_dur=20.0,
    runner_python="",
    grasp_sampler_profile="cutamp_native",
)
report = {}
try:
    summary = json.loads((task_root / "snapshot/summary.json").read_text(encoding="utf-8"))
    frame = load_observation(task_root / "snapshot/agentview")
    detector_id, detections = load_detections(frame, task_root / "snapshot/detector")
    provider = RGBDSceneProvider(lambda _frame: detections, detector_id=detector_id, camera_id=frame.camera_id)
    handoff = VisualDryRunAdapter(provider).query_state(frame, summary["language"])
    evidence = build_visual_planning_input(frame, handoff, provider)
    built = build_visual_tamp_problem(
        frame, evidence, hand_model_dir=model, include_unlabeled_voxels=False,
    )
    cfg = RealCuTAMPBackendConfig(
        initial_state_source="rgbd_observed",
        apply_simulator_truth_initial_state=False,
        initial_state_allow_pad_model_inference=bool(built.problem.init_atoms),
        grasp_dof=6,
        **shared,
    )
    visual = solve(cfg, built.problem)
    visual.update({
        "movable": None if not built.problem.movables else built.problem.movables[0].name,
        "static_count": len(built.problem.statics),
        "hand_state": built.report.get("initial_hand_state"),
        "categories": [item.get("category") for item in built.report.get("geometry", [])],
    })
except Exception as exc:
    visual = {"feasible": False, "failure_reason": f"{type(exc).__name__}: {exc}", "solver_called": False,
              "traceback": traceback.format_exc()[-1500:]}
report["visual"] = visual
print("VISUAL", json.dumps({k: visual[k] for k in visual if k != "traceback"}, default=str)[:2000])

raw = json.loads((task_root / "scene.json").read_text(encoding="utf-8"))
scene = SceneState(
    ee_pos=np.asarray(raw["ee_pos"], np.float32),
    ee_quat=np.asarray(raw["ee_quat"], np.float32),
    gripper_qpos=np.asarray(raw["gripper_qpos"], np.float32),
    robot_qpos=np.asarray(raw["robot_qpos"], np.float32),
    objects={name: ObjectState(name=name, pos=np.asarray(item["pos"], np.float32),
                                quat=np.asarray(item["quat"], np.float32), geometry=item["geometry"])
             for name, item in raw["objects"].items()},
    robot_joint_debug=raw["robot_joint_debug"],
    holding_evidence=raw["holding_evidence"],
)
parsed = parse_task(raw["language"], scene.objects.keys(), bddl_path=raw["bddl_path"])
sym = build_symbolic_state(scene, parsed)
graph = build_scene_graph(scene, parsed, sym)
problem = build_tamp_problem(scene, parsed, sym, init_atoms=graph.world_atoms)
cfg = RealCuTAMPBackendConfig(
    initial_state_source="legacy_simulator",
    apply_simulator_truth_initial_state=True,
    grasp_dof=4,
    **shared,
)
truth = solve(cfg, problem)
truth.update({
    "target": None if sym.target is None else sym.target.name,
    "goal": None if sym.goal is None else sym.goal.name,
    "movable_count": len(problem.movables),
    "static_count": len(problem.statics),
})
report["truth"] = truth
report["language"] = raw["language"]
(task_root / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("TRUTH", json.dumps(truth, default=str)[:2000])
