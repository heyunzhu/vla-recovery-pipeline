#!/usr/bin/env python3
"""Capture a short LIBERO RGB-D motion probe without a policy or recovery.

The output contains only camera observations and robot proprioception. The
small wrist-lift command is the same sensor probe used by
``check_rgbd_wrist_motion.py``; it is not a manipulation rollout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

NO_OP = [0.0] * 6 + [-1.0]
WRIST_LIFT = [0.0, 0.0, 0.05, 0.0, 0.0, 0.0, -1.0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-suite-name", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0, help="zero-based task ID")
    parser.add_argument("--init-index", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--cameras", nargs="+", default=["agentview", "robot0_eye_in_hand"])
    parser.add_argument("--steps", type=int, default=3, help="simulated motion steps after reset")
    parser.add_argument("--motion", choices=["no_op", "wrist_lift"], default="wrist_lift")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.task_id < 0 or args.init_index < 0 or args.resolution <= 0 or not 1 <= args.steps <= 20:
        parser.error("task/init must be nonnegative, resolution positive, and steps within 1..20")
    if len(set(args.cameras)) != len(args.cameras):
        parser.error("camera names must be unique")

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv

    from experiments.robot.libero.skill_pipeline.libero_rgbd_sensor import capture_libero_rgbd
    from experiments.robot.libero.skill_pipeline.rgbd_observation import save_observation

    suite = benchmark.get_benchmark_dict()[args.task_suite_name]()
    task = suite.get_task(args.task_id)
    initial_states = suite.get_task_init_states(args.task_id)
    if args.init_index >= len(initial_states):
        raise ValueError(f"init-index {args.init_index} is outside 0..{len(initial_states) - 1}")
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    if not bddl.is_file():
        raise FileNotFoundError(bddl)
    if args.task_suite_name.endswith("_task"):
        from experiments.robot.libero.tiptop_repro.bddl_goals import parse_bddl_task_goals

        language = str((parse_bddl_task_goals(bddl.read_text(encoding="utf-8")) or {}).get("language") or "").strip()
        language_source = "bddl"
    else:
        language = str(task.language).strip()
        language_source = "task"
    if not language:
        raise ValueError("task has no usable language instruction")
    output = args.out_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"sequence output already exists: {output}")
    output.mkdir(parents=True)

    env = OffScreenRenderEnv(
        bddl_file_name=str(bddl),
        camera_names=args.cameras,
        camera_heights=args.resolution,
        camera_widths=args.resolution,
        camera_depths=True,
        camera_segmentations=None,
    )
    try:
        env.seed(args.seed)
        env.reset()
        obs = env.set_init_state(initial_states[args.init_index])
        episode_id = f"{args.task_suite_name}_task{args.task_id}_init{args.init_index}_probe"
        rows = []
        action = NO_OP if args.motion == "no_op" else WRIST_LIFT
        for step in range(args.steps + 1):
            if step:
                obs, _, _, _ = env.step(action)
            for camera_id in args.cameras:
                frame = capture_libero_rgbd(
                    env, obs, episode_id=episode_id, env_step=step, camera_id=camera_id
                )
                frame_dir = output / f"step{step:03d}" / camera_id
                save_observation(frame, frame_dir)
                rows.append({
                    "env_step": step,
                    "camera_id": camera_id,
                    "relative_path": str(frame_dir.relative_to(output)),
                    "timestamp_s": frame.timestamp_s,
                    "valid_depth_fraction": float(frame.depth_valid.mean()),
                    "ee_pos_m": frame.robot_state["robot0_eef_pos"],
                })
        summary = {
            "kind": "rgbd_motion_probe",
            "task_suite_name": args.task_suite_name,
            "task_id_zero_based": args.task_id,
            "init_index": args.init_index,
            "seed": args.seed,
            "language": language,
            "language_source": language_source,
            "resolution": args.resolution,
            "motion": args.motion,
            "probe_env_steps": args.steps,
            "policy_rollout_steps": 0,
            "frames": rows,
        }
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        env.close()


if __name__ == "__main__":
    main()
