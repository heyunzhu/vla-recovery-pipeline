"""Replay a frozen live-canary frame through runner and visual interfaces.

No simulator is created. This verifies diagnostic routing, not online recovery.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import numpy as np
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    parser.add_argument("--recovery-admission", action="store_true")
    parser.add_argument("--planning-dir", type=Path)
    parser.add_argument("--robot-model-dir", type=Path)
    args = parser.parse_args(argv)
    if args.planning_dir is not None and not args.recovery_admission:
        parser.error("--planning-dir requires --recovery-admission")
    if args.robot_model_dir is not None and args.planning_dir is None:
        parser.error("--robot-model-dir requires --planning-dir")
    if args.out_file.exists():
        raise FileExistsError(args.out_file)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
        from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
        from experiments.robot.libero.skill_pipeline import runner
        from experiments.robot.libero.tiptop_repro.visual_diagnostic_interfaces import (
            CuTAMPVisualDiagnosticPerceiver, VisualDiagnosticRobotClient,
        )
        root = args.input_dir.resolve()
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        config = json.loads((root / "detector/run_config.json").read_text(encoding="utf-8"))
        frame = load_observation(root / "observation")
        if (config.get("prompt_source") != "prompts_json"
                or config.get("prompts") != summary["expected_prompts"]
                or config.get("image_shape_hw") != list(frame.rgb.shape[:2])):
            raise ValueError("frozen detector configuration mismatch")
        expected_id = "grounded-sam2-" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        calls = []
        def detector(current):
            actual_id, detections = load_detections(current, root / "detector")
            if actual_id != expected_id:
                raise ValueError("frozen detector identity mismatch")
            calls.append(current.env_step)
            return detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id=expected_id, camera_id=frame.camera_id))
        language = summary["language"]
        binding = runner._parse_episode_task(None, None, language, "language_rgbd",
                                            visual_adapter=adapter, rgbd_frame=frame)
        state = runner._query_state(None, None, language, scene_source="rgbd",
                                    visual_adapter=adapter, rgbd_frame=frame)
        handoff = state["visual_handoff"]
        perceiver = CuTAMPVisualDiagnosticPerceiver(adapter)
        client = VisualDiagnosticRobotClient(adapter)
        perceived = perceiver.perceive(frame=frame, task_description=language)
        scene = client.get_scene(frame=frame, task_description=language)
        readiness = client.check_execution_readiness(frame=frame, task_description=language)
        denied = False
        try:
            client.step(None)
        except PermissionError:
            denied = True
        if (not denied or handoff is not perceived or handoff is not scene
                or binding is not handoff.binding or len(calls) != 1):
            raise RuntimeError("visual interface replay invariant failed")
        artifacts = [root / "summary.json", root / "observation/metadata.json",
                     root / "observation/rgbd.npz", *sorted((root / "detector").glob("*"))]
        result = dict(schema_version=1, scope="offline_frozen_live_frame_visual_interface_replay",
                      input_dir=str(root), snapshot_id=handoff.snapshot_id,
                      detector_id=expected_id, detector_calls=len(calls),
                      target_id=binding.target_id if binding else None,
                      goal_id=binding.goal_id if binding else None,
                      runner_query_state_routed=True, visual_diagnostic_interfaces_routed=True,
                      shared_handoff_identity=True, action_request_denied=denied,
                      execution_readiness=dataclasses.asdict(readiness),
                      blocked_oracle_import_attempts=guard.blocked_import_attempts,
                      simulator_created=False, policy_actions=0, recovery_actions=0,
                      production_runner_integrated=False,
                      input_sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in artifacts if p.is_file()})
        if args.recovery_admission:
            from experiments.robot.libero.tiptop_repro.visual_recovery_controller import RGBDRecoveryAdmissionController
            admission = RGBDRecoveryAdmissionController(adapter).recover(frame=frame, task_description=language)
            if admission.snapshot_id != handoff.snapshot_id or len(calls) != 1:
                raise RuntimeError("recovery admission replay invariant failed")
            result.update(scope="offline_frozen_live_frame_recovery_admission",
                          recovery_admission=dataclasses.asdict(admission))
            from experiments.robot.libero.skill_pipeline.visual_skill_pack import evaluate_visual_skill_candidate
            _, masks = load_detections(frame, root / "detector")
            result["visual_skill_candidate"] = evaluate_visual_skill_candidate(frame, handoff, masks)
            if args.planning_dir is not None:
                from experiments.robot.libero.skill_pipeline.visual_planning_input import (
                    build_visual_planning_input, export_visual_planning_input,
                )
                evidence = build_visual_planning_input(frame, handoff, adapter.provider)
                from experiments.robot.libero.skill_pipeline.visual_panda_ik import prepare_panda_joint_trajectory
                approach=evidence.report.get('grasp_candidate',{}).get('approach_proposal',{})
                if approach.get('status')=='unverified_waypoint_proposal':
                    ik=prepare_panda_joint_trajectory(frame,approach['proposal'])
                    evidence.report['panda_joint_trajectory_candidate']=ik
                    evidence.arrays['panda_joint_trajectory_rad']=np.asarray([row['joints'] for row in ik['samples']])
                if args.robot_model_dir is not None:
                    from experiments.robot.libero.skill_pipeline.visual_robot_pixels import project_static_gripper
                    from experiments.robot.libero.skill_pipeline.visual_path_diagnostic import inspect_pregrasp_path
                    pixels = project_static_gripper(frame,args.robot_model_dir)
                    proposal = evidence.report.get('grasp_candidate',{}).get('approach_proposal',{})
                    if proposal.get('status')=='unverified_waypoint_proposal':
                        diagnostic=inspect_pregrasp_path(
                            frame,proposal['proposal'],robot_pixels=pixels)
                        for witness in diagnostic['remaining_nearest_witnesses']:
                            x,y=witness['pixel_xy']
                            witness['segmentation_categories']=[d.category for d in masks if d.mask[y,x]]
                        evidence.report['approach_path_robot_pixel_diagnostic']=diagnostic
                        from experiments.robot.libero.skill_pipeline.visual_robot_pixels import load_static_gripper_geometry
                        from experiments.robot.libero.skill_pipeline.visual_gripper_path import inspect_gripper_path
                        geometry=load_static_gripper_geometry(frame,args.robot_model_dir)
                        for part in geometry.parts:
                            evidence.arrays['collision_'+part['name']+'_triangles_world_m']=part['triangles_world_m']
                        gripper_path=inspect_gripper_path(frame,proposal['proposal'],geometry,robot_pixels=pixels)
                        for row in gripper_path['centres']:
                            for hit in row['hits']:
                                x,y=hit['first_witness_pixel_xy']
                                hit['segmentation_categories']=[d.category for d in masks if d.mask[y,x]]
                        evidence.report['actual_gripper_path_diagnostic']=gripper_path
                    evidence.arrays['depth_matched_gripper_mask']=pixels.mask
                    evidence.arrays['static_gripper_mesh_depth_m']=pixels.mesh_depth_m
                result["planning_artifact"] = export_visual_planning_input(evidence,args.planning_dir)
        args.out_file.parent.mkdir(parents=True, exist_ok=True)
        args.out_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return result


if __name__ == "__main__":
    main()
