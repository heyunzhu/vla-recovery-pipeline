"""Solve the saved visual problem after lowering the hand target to the box bottom."""
import json
from pathlib import Path

import torch

from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict, _rgbd_grasp_z_shifts,
)

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008")
payload = json.loads((root / "result_t6_manual_novoxel_pad/problem.json").read_text(encoding="utf-8"))
cfg = RealCuTAMPBackendConfig(**payload["config"])
problem = _problem_from_dict(payload["problem"])
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
            stats[f"{cost_type}/{name}"] = {"min": float(reduced.min()), "median": float(reduced.median())}
    stash.clear()
    stash["constraint_stats"] = stats
    return result

cost_function.CostFunction.__call__ = remember
with OracleImportGuard():
    solved = RealCuTAMPBackend(cfg).solve(problem)
summary = {
    "feasible": solved.feasible,
    "failure_reason": solved.failure_reason,
    "num_satisfying": solved.num_satisfying,
    "elapsed_sec": solved.elapsed_sec,
    "executable_plan_present": bool(solved.executable_plan),
    "environment_actions": 0,
    "visual_grasp_z_shift_m": _rgbd_grasp_z_shifts(problem),
    "movable_pos": [round(float(v), 5) for v in problem.movables[0].pos],
    "movable_half_extents": [round(float(v), 5) for v in problem.movables[0].half_extents],
    "constraint_stats": stash.get("constraint_stats"),
}
out = root / "result_t6_manual_novoxel_pad/plan_bottom.json"
out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
