"""Load a real checkpoint and infer once on saved synchronized camera data.

This probe has no environment or action sink. It does not measure task success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-observation", type=Path, required=True)
    parser.add_argument("--wrist-observation", type=Path, required=True)
    parser.add_argument("--language-summary", type=Path, required=True)
    parser.add_argument("--worker-python", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config-name", default="pi0_libero")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--startup-timeout-s", type=int, default=600)
    parser.add_argument("--infer-timeout-s", type=int, default=300)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.cross_python_policy import CrossPythonPolicyAdapter
    from experiments.robot.libero.skill_pipeline.runner import _quat2axisangle
    agent, wrist = load_observation(args.agent_observation), load_observation(args.wrist_observation)
    if (agent.camera_id != "agentview" or wrist.camera_id != "robot0_eye_in_hand"
            or (agent.episode_id, agent.env_step, agent.timestamp_s, agent.robot_state)
            != (wrist.episode_id, wrist.env_step, wrist.timestamp_s, wrist.robot_state)):
        raise ValueError("synchronized actual agent/wrist observations required")
    language = json.loads(args.language_summary.read_text(encoding="utf-8"))["language"]
    if not isinstance(language, str) or not language.strip():
        raise ValueError("task language required")
    args.out_dir.mkdir(parents=True)
    policy = None
    started = time.monotonic()
    try:
        policy = CrossPythonPolicyAdapter(python=args.worker_python, config_name=args.config_name,
            checkpoint_dir=args.checkpoint, ipc_root=args.out_dir / "policy_ipc",
            startup_timeout_s=args.startup_timeout_s, infer_timeout_s=args.infer_timeout_s)
        load_s = time.monotonic() - started
        policy.reset()
        # Sensor RGB is already top-left oriented (raw OpenGL was flipped in Y).
        # The policy runner rotates raw images in both axes: flip sensor RGB in X.
        state = agent.robot_state
        observation = {"observation/image": np.ascontiguousarray(agent.rgb[:, ::-1]),
                       "observation/wrist_image": np.ascontiguousarray(wrist.rgb[:, ::-1]),
                       "observation/state": np.concatenate((state["robot0_eef_pos"],
                           _quat2axisangle(state["robot0_eef_quat"]), state["robot0_gripper_qpos"])),
                       "prompt": language}
        infer_started = time.monotonic()
        output = policy.infer(observation)
        infer_s = time.monotonic() - infer_started
        np.savez(args.out_dir / "policy_output.npz", **output)
        inputs = [args.language_summary, args.agent_observation / "metadata.json",
                  args.agent_observation / "rgbd.npz", args.wrist_observation / "metadata.json",
                  args.wrist_observation / "rgbd.npz"]
        result = dict(scope="real_checkpoint_cpu_offline_single_inference", config_name=args.config_name,
            checkpoint=args.checkpoint, worker_metadata=policy.worker_metadata,
            parent_python=sys.version, episode_id=agent.episode_id, env_step=agent.env_step,
            timestamp_s=agent.timestamp_s, language=language,
            action_shape=list(output["actions"].shape), actions_finite=bool(np.isfinite(output["actions"]).all()),
            action_min=float(output["actions"].min()), action_max=float(output["actions"].max()),
            load_seconds=load_s, inference_seconds=infer_s,
            cpu_only=True, policy_actions_executed=0, recovery_actions=0,
            simulator_created=False, visual_success_verified=False,
            input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            output_sha256=hashlib.sha256((args.out_dir / "policy_output.npz").read_bytes()).hexdigest())
    except Exception as exc:
        (args.out_dir / "abort.json").write_text(json.dumps({"error": str(exc),
            "elapsed_seconds": time.monotonic() - started, "policy_actions_executed": 0,
            "oracle_fallback": False}, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if policy is not None:
            policy.close()
    result["worker_exit_code"] = policy.process.returncode
    (args.out_dir / "probe_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
