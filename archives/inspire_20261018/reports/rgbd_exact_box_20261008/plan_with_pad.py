"""Use the existing robosuite panda gripper to infer an open pad gap, then solve."""
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.skill_pipeline.visual_planning_input import build_visual_planning_input
from experiments.robot.libero.skill_pipeline.visual_tamp_adapter import build_visual_tamp_problem
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict,
)

work = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo")
root = work / "logs/rgbd_exact_box_20261008"
robosuite = work / "envs/rlinf-openpi/lib/python3.11/site-packages/robosuite"
model = root / "static_panda_model"
xml_rel = Path("models/assets/grippers/panda_gripper.xml")
src_xml = robosuite / xml_rel
tree = ET.parse(src_xml)
copied = [xml_rel]
for element in tree.findall("./asset/mesh"):
    relative = Path("models/assets/grippers") / element.get("file")
    copied.append(relative)
if model.exists():
    shutil.rmtree(model)
for relative in copied:
    destination = model / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(robosuite / relative, destination)
sources = {
    relative.as_posix(): hashlib.sha256((model / relative).read_bytes()).hexdigest()
    for relative in copied
}
(model / "manifest.json").write_text(
    json.dumps({"source_sha256": sources}, indent=2) + "\n", encoding="utf-8"
)

summary = json.loads((root / "snapshot_t6/summary.json").read_text(encoding="utf-8"))
frame = load_observation(root / "snapshot_t6/agentview")
detector_id, detections = load_detections(frame, root / "snapshot_t6/detector_manual")
provider = RGBDSceneProvider(lambda _frame: detections, detector_id=detector_id, camera_id=frame.camera_id)
handoff = VisualDryRunAdapter(provider).query_state(frame, summary["language"])
evidence = build_visual_planning_input(frame, handoff, provider)
built = build_visual_tamp_problem(
    frame, evidence, hand_model_dir=model, include_unlabeled_voxels=False,
)
inference = built.report.get("visual_hand_inference") or {}
cfg = RealCuTAMPBackendConfig(
    initial_state_source="rgbd_observed",
    apply_simulator_truth_initial_state=False,
    initial_state_allow_pad_model_inference=bool(built.problem.init_atoms),
    enable_initial_holding_prebinding=False,
    grasp_sampler_profile="cutamp_native",
    grasp_dof=6,
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
out = root / "result_t6_manual_novoxel_pad"
out.mkdir(parents=True, exist_ok=True)
payload = {
    "report": built.report,
    "problem": built.problem.to_dict(),
    "config": asdict(cfg),
    "language": summary["language"],
    "solver_called": False,
    "environment_actions": 0,
    "hand_model_source": "robosuite_rlinf_openpi_panda_gripper",
    "gripper_xml_sha256": sources[xml_rel.as_posix()],
}
(out / "problem.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({
    "initial_hand_state": built.report.get("initial_hand_state"),
    "inference_status": inference.get("status"),
    "inference_reason": inference.get("reason"),
    "atom_count": len(built.problem.init_atoms),
    "static_count": len(built.problem.statics),
    "gripper_xml_sha256": sources[xml_rel.as_posix()],
}, indent=2))
if not built.problem.init_atoms:
    (out / "plan_summary.json").write_text(json.dumps({
        "feasible": False,
        "failure_reason": inference.get("reason") or built.report.get("initial_hand_state"),
        "solver_called": False,
        "executable_plan_present": False,
        "environment_actions": 0,
        "inference": {k: inference.get(k) for k in ("status", "reason", "source")},
        "evidence": {k: (inference.get("evidence") or {}).get(k) for k in (
            "status", "reason", "ray_count", "free_ray_count", "foreground_occluded_ray_count",
            "occupied_or_boundary_ray_count", "invalid_depth_ray_count", "complete_box_in_image",
            "gripper_measured_open",
        )},
    }, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0)

with OracleImportGuard():
    result = RealCuTAMPBackend(cfg).solve(_problem_from_dict(payload["problem"]))
debug = (result.diagnostics or {}).get("symbolic_initial_state_debug") or {}
plan_summary = {
    "available": result.available,
    "feasible": result.feasible,
    "failure_reason": result.failure_reason,
    "num_satisfying": result.num_satisfying,
    "elapsed_sec": result.elapsed_sec,
    "executable_plan_present": bool(result.executable_plan),
    "environment_actions": 0,
    "solver_called": True,
    "initial_state_source": debug.get("initial_state_source"),
    "applied_fluents": debug.get("applied_fluents"),
    "hand_state_semantics": debug.get("hand_state_semantics"),
}
(out / "plan_summary.json").write_text(json.dumps(plan_summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps(plan_summary, indent=2, allow_nan=False))
