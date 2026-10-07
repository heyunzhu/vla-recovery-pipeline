"""Policy evaluation with optional visual recovery admission; no recovery actions."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from .perception_artifact import load_detections
from .rgbd_observation import save_observation
from .rgbd_scene_provider import RGBDSceneProvider
from .visual_dry_run_adapter import VisualDryRunAdapter
from .visual_temporal_diagnostics import VisualTemporalDiagnostics
from experiments.robot.libero.tiptop_repro.visual_diagnostic_interfaces import VisualDiagnosticRobotClient
from experiments.robot.libero.tiptop_repro.visual_recovery_controller import RGBDRecoveryAdmissionController


class ExternalFrameDetector:
    """Publish each current frame, wait for a matching frozen artifact.

    The caller holds the environment while this blocks. A configuration change
    or timeout aborts the episode; neither path falls back to oracle perception.
    """
    def __init__(self, root, prompts, language, timeout_s):
        self.root = Path(root)
        self.prompts, self.language, self.timeout_s = prompts, language, timeout_s
        self.config_digest = None
        self.artifact_detector_id = None

    def __call__(self, frame):
        directory = self.root / f"step{frame.env_step:06d}"
        directory.mkdir(parents=True, exist_ok=False)
        save_observation(frame, directory / "observation")
        (directory / "summary.json").write_text(json.dumps({
            "language": self.language, "expected_prompts": self.prompts,
            "snapshot_id": f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}",
        }, indent=2) + "\n", encoding="utf-8")
        print("VISUAL_POLICY_FRAME_READY " + str(directory), flush=True)
        deadline = time.monotonic() + self.timeout_s
        while not (directory / "detector/READY").is_file():
            if time.monotonic() >= deadline:
                raise TimeoutError("visual policy detector artifact timed out")
            time.sleep(0.5)
        config = json.loads((directory / "detector/run_config.json").read_text(encoding="utf-8"))
        if (config.get("prompts") != self.prompts or config.get("prompt_source") != "prompts_json"
                or config.get("image_shape_hw") != list(frame.rgb.shape[:2])):
            raise ValueError("visual policy detector configuration mismatch")
        digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        if self.config_digest is not None and digest != self.config_digest:
            raise ValueError("visual policy detector configuration changed during episode")
        detector_id, detections = load_detections(frame, directory / "detector")
        if detector_id != "grounded-sam2-" + digest[:12]:
            raise ValueError("visual policy detector identity mismatch")
        self.config_digest, self.artifact_detector_id = digest, detector_id
        return detections


def run_visual_policy_episode(*, env, policy, initial_obs, language, capture_frame,
                              adapter, write_query, max_steps, action_chunk,
                              settle_steps=10, force_recovery_query=-1, save_final_observation=None,
                              save_query_observation=None, recovery_admission=False):
    """Run policy actions, logging visual refusal at every query boundary.

    capture_frame(obs, env_step) is the only sensor bridge; this loop never
    reads sim/object state. Admission dispatch precedes policy inference and
    stops on refusal; ordinary diagnostic evaluation keeps its existing flow.
    """
    from . import runner
    if max_steps < 1 or action_chunk < 1 or not 0 <= settle_steps <= 100:
        raise ValueError("invalid visual policy episode bounds")
    if recovery_admission and force_recovery_query < 0:
        raise ValueError("recovery admission requires a nonnegative query index")
    policy.reset()
    obs = initial_obs
    done = False
    for settle_index in range(settle_steps):
        obs, _, done, _ = env.step(runner.LIBERO_DUMMY_ACTION)
        if done:
            if save_final_observation is not None:
                save_final_observation(obs, settle_index + 1)
            return dict(policy_actions=0, settle_actions=settle_index + 1, recovery_actions=0,
                        recovery_attempts=0, recovery_boundary_reached=False, termination_reason="benchmark_done",
                        queries=0, benchmark_done=True, visual_success_verified=False,
                        final_env_step=settle_index + 1, final_observation_saved=save_final_observation is not None)
    policy_actions = queries = 0
    client = VisualDiagnosticRobotClient(adapter)
    controller = RGBDRecoveryAdmissionController(adapter) if recovery_admission else None
    recovery_attempts = 0
    termination_reason = "policy_budget_exhausted"
    temporal = VisualTemporalDiagnostics()
    while policy_actions < max_steps and not done:
        frame = capture_frame(obs, settle_steps + policy_actions)
        state = runner._query_state(None, None, language, scene_source="rgbd",
                                    visual_adapter=adapter, rgbd_frame=frame)
        if save_query_observation is not None:
            save_query_observation(obs, frame.env_step, frame)
        readiness = client.check_execution_readiness(frame=frame, task_description=language)
        temporal_evidence = temporal.observe(frame, state["visual_handoff"])
        if controller is not None and queries == force_recovery_query:
            admission = controller.recover(frame=frame, task_description=language)
            if admission.snapshot_id != state["visual_handoff"].snapshot_id:
                raise ValueError("recovery admission snapshot mismatch")
            recovery_attempts += 1
            write_query(dict(
                schema_version=1, trace_kind="visual_recovery_admission", query_idx=queries,
                env_step=frame.env_step, mode="recovery_admission", scene_source="rgbd",
                snapshot_id=admission.snapshot_id, visual_status=admission.perception_status,
                recovery_requested=True, recovery_decision=admission.decision,
                recovery_admission=dataclasses.asdict(admission),
                execution_readiness=dataclasses.asdict(readiness),
                visual_temporal_diagnostics=temporal_evidence,
                policy_action_count=0, recovery_action_count=0,
                synchronized_query_wrist_saved=save_query_observation is not None,
            ))
            queries += 1
            termination_reason = "visual_recovery_refused"
            break
        policy_state = np.concatenate((obs["robot0_eef_pos"],
                                       runner._quat2axisangle(obs["robot0_eef_quat"]),
                                       obs["robot0_gripper_qpos"]))
        output = policy.infer({
            "observation/image": np.ascontiguousarray(obs["agentview_image"][::-1, ::-1]),
            "observation/wrist_image": np.ascontiguousarray(obs["robot0_eye_in_hand_image"][::-1, ::-1]),
            "observation/state": policy_state, "prompt": language,
        })
        actions = np.asarray(output["actions"], dtype=np.float64)
        if actions.ndim != 2 or actions.shape[1] != 7 or not len(actions) or not np.isfinite(actions).all():
            raise ValueError("policy must return finite nonempty actions[N,7]")
        write_query(dict(
            schema_version=1, trace_kind="visual_policy_diagnostic", query_idx=queries,
            env_step=frame.env_step, mode="vla", scene_source="rgbd_diagnostic",
            snapshot_id=readiness.snapshot_id, visual_status=readiness.perception_status,
            visual_binding=dataclasses.asdict(state["visual_handoff"].binding)
                if state["visual_handoff"].binding is not None else None,
            execution_readiness=dataclasses.asdict(readiness),
            visual_temporal_diagnostics=temporal_evidence,
            recovery_requested=queries == force_recovery_query,
            recovery_decision="refused" if queries == force_recovery_query else "not_requested",
            unavailable_oracle_fields=state["unavailable_oracle_fields"],
            policy_action_count=min(action_chunk, len(actions), max_steps - policy_actions),
            synchronized_query_wrist_saved=save_query_observation is not None,
        ))
        queries += 1
        for action in actions[:min(action_chunk, max_steps - policy_actions)]:
            obs, _, done, _ = env.step(action.tolist())
            policy_actions += 1
            if done:
                break
    if save_final_observation is not None:
        save_final_observation(obs, settle_steps + policy_actions)
    return dict(policy_actions=policy_actions, settle_actions=settle_steps,
                recovery_actions=0, queries=queries, benchmark_done=bool(done),
                recovery_attempts=recovery_attempts,
                recovery_boundary_reached=recovery_attempts > 0,
                termination_reason="benchmark_done" if done else termination_reason,
                visual_success_verified=False, final_env_step=settle_steps + policy_actions,
                final_observation_saved=save_final_observation is not None)


def run_from_args(args):
    """Explicit runner branch, separate from oracle skill evaluation."""
    import uuid
    from .visual_oracle_import_guard import OracleImportGuard
    from . import runner
    runner.validate_visual_policy_args(args)
    root = Path(args.visual_output_dir).resolve()
    if root.exists():
        raise FileExistsError(root)
    prompts = json.loads(Path(args.visual_prompts_json).read_text(encoding="utf-8"))
    if not isinstance(prompts, dict) or not prompts or not all(
            isinstance(k, str) and isinstance(v, str) and k and v for k, v in prompts.items()):
        raise ValueError("nonempty frozen visual prompts required")
    root.mkdir(parents=True)
    env = policy = None
    with OracleImportGuard() as guard:
        try:
            from libero.libero import benchmark, get_libero_path
            from libero.libero.envs import OffScreenRenderEnv
            from .libero_rgbd_sensor import capture_libero_rgbd
            suite = benchmark.get_benchmark_dict()[args.task_suite_name]()
            task_id = int(args.task_ids) - 1
            task = suite.get_task(task_id)
            states = suite.get_task_init_states(task_id)
            index = runner.init_state_index_for_episode(args.episode_index_start, len(states))
            seed = runner.episode_seed_for_index(args.seed, args.episode_index_start, args.episode_seed_start)
            language = str(task.language).strip()
            if not language:
                raise ValueError("ordinary task language required")
            bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
            env = OffScreenRenderEnv(bddl_file_name=str(bddl),
                camera_names=["agentview", "robot0_eye_in_hand"], camera_depths=True,
                camera_heights=args.visual_resolution, camera_widths=args.visual_resolution,
                camera_segmentations=None)
            env.seed(seed)
            env.reset()
            obs = env.set_init_state(states[index])
            if args.visual_policy_python:
                from .cross_python_policy import CrossPythonPolicyAdapter
                policy = CrossPythonPolicyAdapter(
                    python=args.visual_policy_python, config_name=args.config_name,
                    checkpoint_dir=args.pretrained_path, ipc_root=root / "policy_ipc",
                    startup_timeout_s=args.visual_policy_startup_timeout_s,
                    infer_timeout_s=args.visual_policy_infer_timeout_s,
                    gpu=None if args.visual_policy_gpu < 0 else args.visual_policy_gpu)
            else:
                runner._patch_torch_load()
                policy_class = (runner.JaxOpenPIUncertaintyPolicyAdapter if args.policy_in_process
                                else runner.SubprocessOpenPIUncertaintyPolicyAdapter)
                policy = policy_class(args.config_name, args.pretrained_path)
            episode = "visual_policy_" + uuid.uuid4().hex
            detector = ExternalFrameDetector(root / "frames", prompts, language, args.visual_timeout_s)
            wrapper_id = "external-frozen-artifacts-" + hashlib.sha256(
                json.dumps(prompts, sort_keys=True).encode()).hexdigest()[:12]
            adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id=wrapper_id, camera_id="agentview"))
            def capture(obs, step):
                return capture_libero_rgbd(env, obs, episode_id=episode, env_step=step, camera_id="agentview")
            def write_query(row):
                row["artifact_detector_id"] = detector.artifact_detector_id
                with (root / "visual_query_trace.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")
            def save_final(obs, step):
                for camera in ("agentview", "robot0_eye_in_hand"):
                    final = capture_libero_rgbd(env, obs, episode_id=episode, env_step=step, camera_id=camera)
                    save_observation(final, root / "final_observation" / camera)
            def save_query(obs, step, primary):
                from .visual_mask_depth_diagnostic import validate_synchronized_views
                wrist = capture_libero_rgbd(env, obs, episode_id=episode, env_step=step,
                                           camera_id="robot0_eye_in_hand")
                validate_synchronized_views(primary, wrist)
                save_observation(wrist, root / "frames" / f"step{step:06d}" / "robot0_eye_in_hand")
            result = run_visual_policy_episode(
                env=env, policy=policy, initial_obs=obs, language=language, capture_frame=capture,
                adapter=adapter, write_query=write_query, max_steps=args.visual_policy_max_steps,
                action_chunk=args.action_chunk, settle_steps=args.num_steps_wait,
                force_recovery_query=args.force_recovery_query, save_final_observation=save_final,
                save_query_observation=save_query,
                recovery_admission=getattr(args, "visual_recovery_admission", False))
            result.update(scope="visual_recovery_admission_evaluation" if getattr(args, "visual_recovery_admission", False)
                          else "visual_policy_diagnostic_evaluation", episode_id=episode,
                          task_suite=args.task_suite_name, task_id_zero_based=task_id,
                          init_index=index, seed=seed, checkpoint=args.pretrained_path,
                          artifact_detector_id=detector.artifact_detector_id,
                          policy_python=args.visual_policy_python or "current_interpreter",
                          policy_worker_metadata=getattr(policy, "worker_metadata", None),
                          blocked_oracle_import_attempts=guard.blocked_import_attempts,
                          production_recovery_integrated=False)
            (root / "episode.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            return result
        except Exception as exc:
            (root / "abort.json").write_text(json.dumps({"aborted": True, "error": str(exc),
                "oracle_fallback": False}, indent=2) + "\n", encoding="utf-8")
            raise
        finally:
            try:
                if policy is not None and hasattr(policy, "close"):
                    policy.close()
            finally:
                if env is not None:
                    env.close()
