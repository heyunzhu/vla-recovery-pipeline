"""Build exact-bound visual boxes for one new RGB-D snapshot and measure collision."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-dir", type=Path, required=True)
    parser.add_argument("--detector-dir", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--drop-unlabeled-boxes", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo))
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
    from experiments.robot.libero.skill_pipeline.visual_planning_input import build_visual_planning_input
    from experiments.robot.libero.skill_pipeline.visual_tamp_adapter import build_visual_tamp_problem
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
        RealCuTAMPBackend, RealCuTAMPBackendConfig, _problem_from_dict,
    )

    summary = json.loads(args.summary_json.read_text(encoding="utf-8"))
    language = summary["language"]
    frame = load_observation(args.observation_dir)
    detector_id, detections = load_detections(frame, args.detector_dir)
    provider = RGBDSceneProvider(lambda _frame: detections, detector_id=detector_id, camera_id=frame.camera_id)
    handoff = VisualDryRunAdapter(provider).query_state(frame, language)
    evidence = build_visual_planning_input(frame, handoff, provider)
    built = build_visual_tamp_problem(frame, evidence, include_unlabeled_voxels=not args.drop_unlabeled_boxes)
    cfg = RealCuTAMPBackendConfig(
        initial_state_source="rgbd_observed",
        apply_simulator_truth_initial_state=False,
        initial_state_allow_pad_model_inference=False,
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
    payload = {
        "report": built.report,
        "problem": built.problem.to_dict(),
        "config": asdict(cfg),
        "language": language,
        "solver_called": False,
        "environment_actions": 0,
    }
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    problem_path = out / "problem.json"
    problem_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    problem = _problem_from_dict(payload["problem"])
    rows = []
    for obj in problem.movables + problem.surfaces + [item for item in problem.statics if item.name.startswith("obj_")]:
        rows.append({
            "name": obj.name,
            "role": obj.role,
            "half_extents_m": [round(float(v), 6) for v in obj.half_extents],
            "dims_m": [round(float(v) * 2, 6) for v in obj.half_extents],
            "observed_point_count": obj.geometry.get("observed_point_count"),
            "category": obj.geometry.get("category"),
        })
    boxes = problem.movables + problem.surfaces + problem.statics
    overlaps = []
    for i, left in enumerate(boxes):
        if not left.name.startswith("obj_"):
            continue
        for right in boxes[i + 1:]:
            if not right.name.startswith("obj_"):
                continue
            gap = np.asarray(left.half_extents) + np.asarray(right.half_extents) - np.abs(np.asarray(left.pos) - np.asarray(right.pos))
            overlaps.append({
                "a": left.name,
                "b": right.name,
                "overlap_m": [round(float(v), 6) for v in gap],
                "separated": bool(np.any(gap < 0)),
            })
    summary_out = {
        "language": language,
        "proxy_padding_m": built.report.get("proxy_padding_m"),
        "voxel_shape": built.report.get("voxel_shape"),
        "movable_count": len(problem.movables),
        "surface_count": len(problem.surfaces),
        "static_count": len(problem.statics),
        "objects": rows,
        "semantic_aabb_gaps": overlaps,
    }
    try:
        from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
        with OracleImportGuard():
            import torch
            from cutamp.tamp_world import TAMPWorld
            from cutamp.utils.common import pose_list_to_mat4x4, transform_spheres
            from curobo.types.base import TensorDeviceType
            env, _, _, _ = RealCuTAMPBackend(cfg)._build_env(problem)
            tensor_args = TensorDeviceType()
            world = TAMPWorld(env, tensor_args, cfg.robot, tensor_args.to_device(problem.q_init))
            movable = env.movables[0]
            transform = pose_list_to_mat4x4(movable.pose).to(device=tensor_args.device, dtype=tensor_args.dtype)
            spheres = transform_spheres(world.get_collision_spheres(movable), transform)
            query = spheres[None, None].contiguous()
            full_cost = float(world.collision_fn(query).sum().item())
            summary_out["gpu_initial_collision"] = {
                "target": movable.name,
                "sphere_count": int(spheres.shape[0]),
                "full_world_cost": full_cost,
                "cuda": torch.cuda.get_device_name(0),
            }
    except Exception as exc:
        summary_out["gpu_initial_collision"] = {"error": f"{type(exc).__name__}: {exc}"}
    (out / "exact_box_report.json").write_text(json.dumps(summary_out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary_out, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
