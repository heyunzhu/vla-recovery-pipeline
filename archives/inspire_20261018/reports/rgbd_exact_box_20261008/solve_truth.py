"""Plan the same reset from simulator object geometry, with the visual run's solver settings."""
import json
from pathlib import Path

import numpy as np
import torch

from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.tiptop_repro.predicates import build_symbolic_state
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict,
)
from experiments.robot.libero.tiptop_repro.scene_graph import build_scene_graph
from experiments.robot.libero.tiptop_repro.scene_types import ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.tamp_scene import build_tamp_problem
from experiments.robot.libero.tiptop_repro.task_parser import parse_task

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/truth_t6")
raw = json.loads((root / "scene.json").read_text(encoding="utf-8"))
scene = SceneState(
    ee_pos=np.asarray(raw["ee_pos"], np.float32),
    ee_quat=np.asarray(raw["ee_quat"], np.float32),
    gripper_qpos=np.asarray(raw["gripper_qpos"], np.float32),
    robot_qpos=np.asarray(raw["robot_qpos"], np.float32),
    objects={
        name: ObjectState(
            name=name,
            pos=np.asarray(item["pos"], np.float32),
            quat=np.asarray(item["quat"], np.float32),
            geometry=item["geometry"],
        )
        for name, item in raw["objects"].items()
    },
    robot_joint_debug=raw["robot_joint_debug"],
    holding_evidence=raw["holding_evidence"],
)
parsed = parse_task(raw["language"], scene.objects.keys(), bddl_path=raw["bddl_path"])
sym = build_symbolic_state(scene, parsed)
graph = build_scene_graph(scene, parsed, sym)
problem = build_tamp_problem(
    scene, parsed, sym,
    goal_atoms_override=None,
    init_atoms=graph.world_atoms,
)
cfg = RealCuTAMPBackendConfig(
    initial_state_source="legacy_simulator",
    apply_simulator_truth_initial_state=True,
    initial_state_allow_pad_model_inference=False,
    enable_initial_holding_prebinding=False,
    grasp_sampler_profile="cutamp_native",
    grasp_dof=4,
    curobo_plan=True,
    serialize_trajectories=True,
    accept_optimized_plan_if_motiongen_fails=False,
    project_motiongen_start_joint_limits=False,
    dummy_obstacle_if_empty=False,
    num_particles=64,
    num_opt_steps=40,
    max_loop_dur=20.0,
    runner_python="",
)
objects = []
for item in problem.movables + problem.surfaces + problem.statics:
    objects.append({
        "name": item.name,
        "role": item.role,
        "pos": [round(float(v), 4) for v in item.pos],
        "half_extents_m": [round(float(v), 4) for v in item.half_extents],
    })
stash = {}
import cutamp.cost_function as cost_function
original = cost_function.CostFunction.__call__

def remember(self, rollout):
    result = original(self, rollout)
    if torch.is_grad_enabled():
        return result
    stats = {}
    for cost_type, info in result.items():
        if info.get("type") != "constraint":
            continue
        for name, values in info["values"].items():
            data = values.detach().float()
            reduced = data.amax(dim=1) if data.ndim == 2 else data
            stats[f"{cost_type}/{name}"] = {
                "min": float(reduced.min()),
                "median": float(reduced.median()),
            }
    stash.clear()
    stash["constraint_stats"] = stats
    return result

cost_function.CostFunction.__call__ = remember
with OracleImportGuard():
    solved = RealCuTAMPBackend(cfg).solve(problem)
summary = {
    "language": raw["language"],
    "target": None if sym.target is None else sym.target.name,
    "goal": None if sym.goal is None else sym.goal.name,
    "movable_count": len(problem.movables),
    "surface_count": len(problem.surfaces),
    "static_count": len(problem.statics),
    "objects": objects,
    "feasible": solved.feasible,
    "failure_reason": solved.failure_reason,
    "num_satisfying": solved.num_satisfying,
    "elapsed_sec": solved.elapsed_sec,
    "executable_plan_present": bool(solved.executable_plan),
    "environment_actions": 0,
    "grasp_dof": cfg.grasp_dof,
    "constraint_stats": stash.get("constraint_stats"),
}
(root / "plan_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: summary[k] for k in (
    "target", "goal", "feasible", "failure_reason", "num_satisfying", "elapsed_sec",
    "movable_count", "surface_count", "static_count", "constraint_stats",
)}, indent=2))
