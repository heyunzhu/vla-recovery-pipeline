"""Re-solve the saved problem and record why every sample failed."""
import json
from pathlib import Path

import torch

from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict,
)

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008")
payload = json.loads((root / "result_t6_manual_novoxel_pad/problem.json").read_text(encoding="utf-8"))
cfg = RealCuTAMPBackendConfig(**payload["config"])
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
                "max": float(reduced.max()),
            }
    costs = torch.stack([
        (values.detach().float().amax(dim=1) if values.ndim == 2 else values.detach().float())
        for info in result.values() if info.get("type") == "constraint"
        for values in info["values"].values()
    ]).sum(0)
    best = int(costs.argmin())
    poses = {}
    for name, mats in rollout["obj_to_pose"].items():
        poses[str(name)] = mats[best, -1].detach().float().cpu().tolist()
    stash.clear()
    stash.update({
        "constraint_stats": stats,
        "best_index": best,
        "best_constraint_sum": float(costs[best]),
        "best_final_joints": rollout["confs"][best, -1].detach().float().cpu().tolist(),
        "best_final_object_poses": poses,
    })
    return result

cost_function.CostFunction.__call__ = remember
with OracleImportGuard():
    result = RealCuTAMPBackend(cfg).solve(_problem_from_dict(payload["problem"]))
summary = {
    "feasible": result.feasible,
    "failure_reason": result.failure_reason,
    "num_satisfying": result.num_satisfying,
    "elapsed_sec": result.elapsed_sec,
    "executable_plan_present": bool(result.executable_plan),
    **stash,
}
out = root / "result_t6_manual_novoxel_pad/stuck_summary.json"
out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary["constraint_stats"], indent=2))
print("BEST", summary["best_index"], summary["best_constraint_sum"])
