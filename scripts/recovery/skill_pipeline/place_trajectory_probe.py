#!/usr/bin/env python3
"""Sweep the arm from its start configuration to the placement configuration.

Layer 4 of the task04 place goal is `Collision.robot_to_world`: with the object frame
fixed, `pos_err` and `rot_err` are satisfied for ~63/64 particles and arm-versus-world
collision is the only binding constraint left. This probes that path directly - q_init
interpolated in joint space to the configuration IK finds for a sampled placement - and
names the obstacle at every sample.

Run it under the py3.10 wrapper, which is where cuTAMP and cuRobo live:

    ROOT=<work> OVERLAY_ROOT=<repo> CUTAMP_CANONICAL_OBJECT_FRAME=1 \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      scripts/recovery/skill_pipeline/place_trajectory_probe.py \\
      --solve-json <run>/cutamp_debug/solve_*.problem.json --samples 13 --targets 3

A hit at the final sample means the arm cannot even hold the placement pose; a hit only
in the middle means the straight-line interpolation is what clips, not the goal.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.collision_report import (  # noqa: E402
    _load_problem,
    obb_boxes_from_world_config,
    rank_obstacles,
    robot_spheres_at,
)


def joint_space_path(q_start: Sequence[float], q_target: Sequence[float], samples: int) -> List[np.ndarray]:
    """Evenly spaced configurations from start to target, both endpoints included."""
    start = np.asarray(list(q_start), dtype=np.float64).reshape(-1)
    target = np.asarray(list(q_target), dtype=np.float64).reshape(-1)
    if start.shape != target.shape:
        raise ValueError(f"shape mismatch: {start.shape} vs {target.shape}")
    count = max(2, int(samples))
    return [start + (target - start) * (index / (count - 1)) for index in range(count)]


def worst_per_phase(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Fold a sweep into one entry per phase, keeping the deepest sample."""
    phases: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        phase = str(row["phase"])
        entry = phases.setdefault(phase, {"samples": 0, "worst_depth_m": -np.inf, "worst_obstacle": ""})
        entry["samples"] += 1
        if float(row["worst_depth_m"]) > float(entry["worst_depth_m"]):
            entry["worst_depth_m"] = float(row["worst_depth_m"])
            entry["worst_obstacle"] = str(row["worst_obstacle"])
    return phases


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solve-json", required=True, help="Problem supplying the world, the object and q_init.")
    parser.add_argument("--samples", type=int, default=13, help="Configurations along start->target.")
    parser.add_argument("--targets", type=int, default=3, help="How many IK-solvable placements to sweep.")
    parser.add_argument("--num-placements", type=int, default=64, help="Placements to sample before IK.")
    parser.add_argument("--top", type=int, default=3, help="Obstacles to print per sample.")
    parser.add_argument("--out-json", default="")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import json

    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    cfg, problem = _load_problem(solve_json)
    q_start = list(problem.q_init or [])
    if not q_start:
        print("problem has no q_init")
        return 2

    from curobo.types.base import TensorDeviceType
    from curobo.types.math import Pose
    from cutamp.config import TAMPConfiguration
    from cutamp.robots import load_robot_container
    from cutamp.samplers import grasp_6dof_sampler, place_4dof_sampler
    from cutamp.tamp_world import TAMPWorld
    from cutamp.utils.common import action_4dof_to_mat4x4, action_6dof_to_mat4x4, get_world_cfg
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend

    backend = RealCuTAMPBackend(cfg)
    env, name_map, goal_notes, geometry_debug = backend._build_env(problem)
    world_cfg = get_world_cfg(env, include_movables=False)
    boxes = obb_boxes_from_world_config(world_cfg)

    target_names = {str(getattr(o, "name", "")) for o in env.movables}
    surface_objs = list(env.type_to_objects.get("Surface", []))
    if not surface_objs:
        print("no Surface objects in the environment")
        return 3
    # The placement surface is whichever one the goal atoms name.
    goal_surfaces = {str(arg) for atom in problem.goal_atoms for arg in atom.args}
    surface = next((o for o in surface_objs if str(getattr(o, "name", "")) in goal_surfaces), surface_objs[-1])
    obj_name = next(iter(target_names))
    print(f"problem        : {solve_json.name}")
    print(f"object         : {obj_name}")
    print(f"placement on   : {getattr(surface, 'name', '?')}")

    tensor_args = TensorDeviceType()
    world = TAMPWorld(
        env,
        tensor_args,
        robot=load_robot_container(cfg.robot, tensor_args),
        q_init=tensor_args.to_device(q_start),
        collision_activation_distance=0.0,
    )
    conf = TAMPConfiguration(num_particles=int(args.num_placements), robot=cfg.robot, grasp_dof=int(cfg.grasp_dof))

    obj = world.get_object(obj_name)
    obj_spheres = world.get_collision_spheres(obj)
    is_cuboid = type(obj).__name__ == "Cuboid"
    sampled = place_4dof_sampler(
        int(args.num_placements),
        obj,
        obj_spheres,
        surface,
        surface_rep=conf.placement_check,
        shrink_dist=conf.placement_shrink_dist,
        collision_activation_dist=conf.world_activation_distance,
    )
    grasps = grasp_6dof_sampler(int(args.num_placements), obj, num_faces=4 if is_cuboid else None)
    obj_from_grasp = action_6dof_to_mat4x4(tensor_args.to_device(grasps))
    world_from_obj = action_4dof_to_mat4x4(sampled)
    world_from_ee = world_from_obj @ obj_from_grasp @ world.tool_from_ee
    ik = world.ik_solver.solve_batch(Pose.from_matrix(world_from_ee))
    solved = [int(i) for i in np.flatnonzero(np.asarray(ik.success.detach().cpu()))][: max(1, int(args.targets))]
    print(f"placements     : {len(sampled)} sampled, IK solved {int(ik.success.sum())}/{len(sampled)}")
    if not solved:
        print("no IK-solvable placement; nothing to sweep")
        return 4

    container = world.robot_container
    rows: List[Dict[str, Any]] = []
    for target_index in solved:
        q_target = np.asarray(ik.solution[target_index, 0].detach().cpu().numpy(), dtype=np.float64).reshape(-1)
        path = joint_space_path(q_start, q_target, int(args.samples))
        for index, q in enumerate(path):
            spheres = robot_spheres_at(container, tensor_args, q)
            ranked = rank_obstacles(spheres, boxes)
            worst = ranked[0] if ranked else {"name": "", "depth_m": 0.0, "sphere_index": -1}
            rows.append(
                {
                    "phase": "start" if index == 0 else ("goal" if index == len(path) - 1 else "transit"),
                    "target": int(target_index),
                    "t": index / (len(path) - 1),
                    "worst_obstacle": str(worst["name"]),
                    "worst_depth_m": float(worst["depth_m"]),
                    "ranked": ranked[: max(1, int(args.top))],
                }
            )

    worst_row = max(rows, key=lambda row: float(row["worst_depth_m"]))
    print()
    print(f"{'target':<7}{'phase':<9}{'t':>5}{'penetration':>13}  obstacle")
    for row in rows:
        print(
            f"{row['target']:<7}{row['phase']:<9}{row['t']:>5.2f}"
            f"{row['worst_depth_m']:>13.5f}  {row['worst_obstacle'][:46]}"
        )
    print()
    print("worst per phase:")
    for phase, entry in worst_per_phase(rows).items():
        print(
            f"   {phase:<9} samples={entry['samples']:<3} worst={entry['worst_depth_m']:+.5f} m  "
            f"{entry['worst_obstacle'][:46]}"
        )
    print()
    print(
        f"deepest        : {worst_row['worst_depth_m']:+.5f} m on {worst_row['worst_obstacle']} "
        f"at target {worst_row['target']} {worst_row['phase']} (t={worst_row['t']:.2f})"
    )

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "solve_json": str(solve_json),
                    "object": obj_name,
                    "surface": str(getattr(surface, "name", "")),
                    "ik_solved": int(ik.success.sum()),
                    "num_sampled": int(len(sampled)),
                    "worst_penetration_m": float(worst_row["worst_depth_m"]),
                    "worst_obstacle": str(worst_row["worst_obstacle"]),
                    "by_phase": worst_per_phase(rows),
                    "samples": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {out}")
    return 0 if float(worst_row["worst_depth_m"]) <= 0.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
