#!/usr/bin/env python3
"""Evaluation-only table geometry diagnostic for one fixed LIBERO init.

Never import this file from runner, scene providers, matchers or planners. It
reads simulator geometry only to check an independently saved RGB-D snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
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

    import numpy as np
    from libero.libero import benchmark, get_libero_path
    from libero.libero.envs import OffScreenRenderEnv

    suite = benchmark.get_benchmark_dict()[args.task_suite_name]()
    task = suite.get_task(args.task_id)
    init_states = suite.get_task_init_states(args.task_id)
    bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
    env = OffScreenRenderEnv(bddl_file_name=str(bddl), camera_heights=128, camera_widths=128)
    try:
        env.seed(args.seed)
        env.reset()
        env.set_init_state(init_states[args.init_index])
        model, data = env.sim.model, env.sim.data
        rows = []
        for geom_id, name in enumerate(model.geom_names):
            if "table" not in str(name).lower():
                continue
            size = np.asarray(model.geom_size[geom_id], dtype=float).reshape(-1)
            pos = np.asarray(data.geom_xpos[geom_id], dtype=float).reshape(-1)
            rows.append(
                {
                    "name": str(name),
                    "shape": int(model.geom_type[geom_id]),
                    "center_world_m": pos.tolist(),
                    "half_size_m": size.tolist(),
                    "axis_aligned_top_z_if_box_m": float(pos[2] + size[2]),
                }
            )
        print(json.dumps({"evaluation_only": True, "table_geoms": rows}, ensure_ascii=False, indent=2))
    finally:
        env.close()


if __name__ == "__main__":
    main()
