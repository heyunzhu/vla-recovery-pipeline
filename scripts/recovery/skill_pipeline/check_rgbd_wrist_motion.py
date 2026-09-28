#!/usr/bin/env python3
"""Check that wrist RGB-D extrinsic follows a small simulated robot motion."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-suite-name", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--init-index", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    import numpy as np
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv

    from experiments.robot.libero.skill_pipeline.libero_rgbd_sensor import capture_libero_rgbd

    suite = benchmark.get_benchmark_dict()[args.task_suite_name]()
    task = suite.get_task(args.task_id)
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    env = OffScreenRenderEnv(
        bddl_file_name=str(bddl),
        camera_names=["agentview", "robot0_eye_in_hand"],
        camera_heights=128,
        camera_widths=128,
        camera_depths=True,
    )
    try:
        env.seed(args.seed)
        env.reset()
        obs = env.set_init_state(suite.get_task_init_states(args.task_id)[args.init_index])
        before = capture_libero_rgbd(
            env, obs, episode_id="wrist_motion_probe", env_step=0, camera_id="robot0_eye_in_hand"
        )
        # Small upward OSC command for three steps; this is a sensor diagnostic,
        # not a policy or recovery action sequence.
        for step in range(1, 4):
            obs, _, _, _ = env.step([0.0, 0.0, 0.05, 0.0, 0.0, 0.0, -1.0])
        after = capture_libero_rgbd(
            env, obs, episode_id="wrist_motion_probe", env_step=3, camera_id="robot0_eye_in_hand"
        )
        ee_delta = np.asarray(after.robot_state["robot0_eef_pos"]) - np.asarray(
            before.robot_state["robot0_eef_pos"]
        )
        camera_delta = after.T_world_camera[:3, 3] - before.T_world_camera[:3, 3]
        result = {
            "evaluation_only": True,
            "env_steps": 3,
            "timestamp_before_s": before.timestamp_s,
            "timestamp_after_s": after.timestamp_s,
            "ee_delta_m": ee_delta.tolist(),
            "wrist_camera_delta_m": camera_delta.tolist(),
            "delta_difference_m": float(np.linalg.norm(camera_delta - ee_delta)),
            "before_valid_depth_pixels": int(before.depth_valid.sum()),
            "after_valid_depth_pixels": int(after.depth_valid.sum()),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if np.linalg.norm(ee_delta) < 0.001 or np.linalg.norm(camera_delta) < 0.001:
            raise RuntimeError("wrist motion probe did not move enough to check extrinsic updates")
        if after.timestamp_s <= before.timestamp_s:
            raise RuntimeError("simulation timestamp did not advance")
    finally:
        env.close()


if __name__ == "__main__":
    main()
