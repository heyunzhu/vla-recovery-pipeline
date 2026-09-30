#!/usr/bin/env python3
"""Capture one fixed-init LIBERO RGB-D reset observation; no policy or recovery.

Example (with LIBERO installed and its config set)::

    python scripts/recovery/skill_pipeline/collect_rgbd_snapshot.py \
        --task-suite-name libero_spatial --task-id 0 --init-index 0 \
        --out-dir /path/to/personal/data/rgbd-spatial-task0-init0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-suite-name", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0, help="Zero-based task ID")
    parser.add_argument("--init-index", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--resolution", type=int, default=128)
    parser.add_argument("--cameras", nargs="+", default=["agentview"])
    parser.add_argument("--settle-steps", type=int, default=10,
                        help="no-op steps before capture, matching the runner's default wait")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.resolution <= 0 or args.task_id < 0 or args.init_index < 0:
        parser.error("resolution must be positive and task/init indices nonnegative")
    if not 0 <= args.settle_steps <= 100:
        parser.error("settle-steps must be within 0..100")

    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo))
    import numpy as np
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv

    from experiments.robot.libero.skill_pipeline.libero_rgbd_sensor import capture_libero_rgbd
    from experiments.robot.libero.skill_pipeline.rgbd_observation import save_observation, unproject_world

    suite = benchmark.get_benchmark_dict()[args.task_suite_name]()
    task = suite.get_task(args.task_id)
    initial_states = suite.get_task_init_states(args.task_id)
    if args.init_index >= len(initial_states):
        raise ValueError(f"init-index {args.init_index} is outside 0..{len(initial_states) - 1}")
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    if not bddl.is_file():
        raise FileNotFoundError(bddl)
    output = args.out_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"snapshot output already exists: {output}")
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
        for _ in range(args.settle_steps):
            obs, _, _, _ = env.step([0.0] * 6 + [-1.0])
        frames = []
        episode_id = (
            f"{args.task_suite_name}_task{args.task_id}_init{args.init_index}"
            f"_settle{args.settle_steps}"
        )
        for camera_id in args.cameras:
            frame = capture_libero_rgbd(
                env, obs, episode_id=episode_id,
                env_step=args.settle_steps, camera_id=camera_id
            )
            save_observation(frame, output / camera_id)
            points = unproject_world(frame)
            np.savez_compressed(output / camera_id / "world_points.npz", xyz=points)
            frames.append(
                {
                    "camera_id": camera_id,
                    "shape": list(frame.depth_m.shape),
                    "valid_depth_pixels": int(frame.depth_valid.sum()),
                    "valid_depth_fraction": float(frame.depth_valid.mean()),
                    "world_bounds_min": points.min(axis=0).tolist() if len(points) else None,
                    "world_bounds_max": points.max(axis=0).tolist() if len(points) else None,
                    "calibration_version": frame.calibration_version,
                }
            )
        summary = {
            "kind": "reset_rgbd_snapshot",
            "task_suite_name": args.task_suite_name,
            "task_id_zero_based": args.task_id,
            "init_index": args.init_index,
            "seed": args.seed,
            "language": str(task.language),
            "policy_rollout_steps": 0,
            "settle_env_steps": args.settle_steps,
            "capture_start_env_step": args.settle_steps,
            "frames": frames,
        }
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        env.close()


if __name__ == "__main__":
    main()
