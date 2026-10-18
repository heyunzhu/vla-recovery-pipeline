"""Ask cuTAMP for one trajectory from the saved no-voxel problem."""
import json
from pathlib import Path

from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict,
)

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008")
payload = json.loads((root / "result_t6_manual_novoxel/problem.json").read_text(encoding="utf-8"))
cfg = RealCuTAMPBackendConfig(**payload["config"])
with OracleImportGuard():
    result = RealCuTAMPBackend(cfg).solve(_problem_from_dict(payload["problem"]))
summary = {
    "available": result.available,
    "feasible": result.feasible,
    "failure_reason": result.failure_reason,
    "num_satisfying": result.num_satisfying,
    "elapsed_sec": result.elapsed_sec,
    "executable_plan_present": bool(result.executable_plan),
    "environment_actions": 0,
}
debug = (result.diagnostics or {}).get("symbolic_initial_state_debug") or {}
summary["initial_state_source"] = debug.get("initial_state_source")
summary["applied_fluents"] = debug.get("applied_fluents")
out = root / "result_t6_manual_novoxel/plan_summary.json"
out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, allow_nan=False))
