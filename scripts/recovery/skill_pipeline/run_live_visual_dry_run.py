#!/usr/bin/env python3
"""Hold one LIBERO frame for external detection, then exercise visual interfaces.

The environment stays alive while a separate detector writes frozen artifacts.
Only initial settling actions are sent. No policy, planner or recovery executes.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")


def main(argv=None, *, query_reader=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-suite-name", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--init-index", type=int, default=1)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--settle-steps", type=int, default=10)
    parser.add_argument("--timeout-s", type=int, default=600)
    parser.add_argument("--prompts-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.task_id < 0 or args.init_index < 0 or args.resolution < 1
            or not 0 <= args.settle_steps <= 100 or not 1 <= args.timeout_s <= 1200):
        parser.error("invalid capture or timeout parameters")
    root = args.out_dir.resolve()
    if root.exists():
        raise FileExistsError(root)
    prompts = json.loads(args.prompts_json.read_text(encoding="utf-8"))
    if not isinstance(prompts, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                for k, v in prompts.items()):
        raise ValueError("invalid frozen prompts")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard

    with OracleImportGuard() as guard:
        from libero.libero import benchmark, get_libero_path
        from libero.libero.envs import OffScreenRenderEnv
        from experiments.robot.libero.skill_pipeline.libero_rgbd_sensor import capture_libero_rgbd
        from experiments.robot.libero.skill_pipeline.rgbd_observation import save_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
        from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
        from experiments.robot.libero.tiptop_repro.visual_diagnostic_interfaces import (
            CuTAMPVisualDiagnosticPerceiver, VisualDiagnosticRobotClient,
        )

        suite = benchmark.get_benchmark_dict()[args.task_suite_name]()
        task = suite.get_task(args.task_id)
        states = suite.get_task_init_states(args.task_id)
        if args.init_index >= len(states):
            raise ValueError("init index out of range")
        language = str(task.language).strip()
        if not language:
            raise ValueError("task language required")
        bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
        env = OffScreenRenderEnv(bddl_file_name=str(bddl), camera_names=["agentview"],
                                 camera_heights=args.resolution, camera_widths=args.resolution,
                                 camera_depths=True, camera_segmentations=None)
        root.mkdir(parents=True)
        try:
            env.seed(args.seed)
            env.reset()
            obs = env.set_init_state(states[args.init_index])
            for _ in range(args.settle_steps):
                obs, _, _, _ = env.step([0.0] * 6 + [-1.0])
            episode = f"{args.task_suite_name}_task{args.task_id}_init{args.init_index}_visual_dry_run"
            frame = capture_libero_rgbd(env, obs, episode_id=episode,
                                       env_step=args.settle_steps, camera_id="agentview")
            save_observation(frame, root / "observation")
            summary = dict(kind="live_visual_dry_run", language=language,
                           task_suite_name=args.task_suite_name, task_id_zero_based=args.task_id,
                           init_index=args.init_index, seed=args.seed, settle_env_steps=args.settle_steps,
                           resolution=args.resolution, expected_prompts=prompts)
            (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print("VISUAL_FRAME_READY " + str(root), flush=True)
            deadline = time.monotonic() + args.timeout_s
            ready = root / "detector" / "READY"
            while not ready.is_file():
                if time.monotonic() >= deadline:
                    raise TimeoutError("external detector artifact did not arrive")
                time.sleep(0.5)
            config = json.loads((root / "detector" / "run_config.json").read_text(encoding="utf-8"))
            if (config.get("prompt_source") != "prompts_json" or config.get("prompts") != prompts
                    or config.get("image_shape_hw") != list(frame.rgb.shape[:2])):
                raise ValueError("external detector configuration mismatch")
            expected_id = "grounded-sam2-" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
            detector_id, _ = load_detections(frame, root / "detector")
            if detector_id != expected_id:
                raise ValueError("detector identity does not match frozen configuration")
            calls = [0]

            def detector(current):
                calls[0] += 1
                actual_id, detections = load_detections(current, root / "detector")
                if actual_id != detector_id:
                    raise ValueError("detector identity changed")
                return detections

            adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id=detector_id,
                                                           camera_id="agentview"))
            query = (query_reader(adapter, frame, language) if query_reader is not None
                     else adapter.query_state(frame, language))
            # Capture again from the held environment; provider checks full RGB-D digest.
            recaptured = capture_libero_rgbd(env, obs, episode_id=episode,
                                            env_step=args.settle_steps, camera_id="agentview")
            perceiver = CuTAMPVisualDiagnosticPerceiver(adapter)
            client = VisualDiagnosticRobotClient(adapter)
            perceived = perceiver.perceive(frame=recaptured, task_description=language)
            executed_scene = client.get_scene(frame=recaptured, task_description=language)
            readiness = client.check_execution_readiness(frame=recaptured, task_description=language)
            denied = False
            try:
                client.step(None)
            except PermissionError:
                denied = True
            if not denied or query is not perceived or query is not executed_scene or calls[0] != 1:
                raise RuntimeError("visual dry-run interface invariant failed")
            result = dict(schema_version=1, scope="held_live_frame_external_detector_visual_adapter_dry_run",
                          runner_query_state_routed=query_reader is not None,
                          production_runner_integrated=False, handoff=dataclasses.asdict(query),
                          visual_diagnostic_interfaces_routed=True,
                          execution_readiness=dataclasses.asdict(readiness),
                          shared_handoff_identity=True, detector_calls=calls[0], action_request_denied=denied,
                          oracle_guard_scope="imports_of_scene_reader_cutamp_perceiver_executor",
                          blocked_oracle_import_attempts=guard.blocked_import_attempts,
                          recovery_actions=0, policy_actions=0, settle_actions=args.settle_steps,
                          environment_advanced_during_detection=False)
            (root / "dry_run_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("VISUAL_DRY_RUN_COMPLETE " + json.dumps({"status": query.status,
                  "detector_calls": calls[0], "action_request_denied": denied,
                  "blocked_oracle_import_attempts": guard.blocked_import_attempts}), flush=True)
            return result
        finally:
            env.close()


if __name__ == "__main__":
    main()
