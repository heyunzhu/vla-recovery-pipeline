"""Is Place:end's IK_FAIL collision, or is the pose out of reach?

The per-stage cuRobo trace shows the placement approach (5 cm above) succeeding and the
placement pose itself failing IK for every particle, with no repair path. Two candidate
explanations, and they need different fixes:

  * collision - the gripper cannot physically fit inside the drawer at the release pose.
    cuRobo's IK is collision aware, so it reports IK_FAIL.
  * kinematics - the pose is outside what the arm can reach at all.

This separates them three ways:

  1. sweep the placement pose upward and find where IK starts succeeding;
  2. ask IK for the placement pose with an *empty* world - pure kinematics. If that
     solves, the pose is reachable and collisions are what reject it;
  3. feed that empty-world solution into the collision probe and name the obstacle and
     depth the gripper is embedded in.

    ROOT=<work> OVERLAY_ROOT=<repo> CUTAMP_CANONICAL_OBJECT_FRAME=1 \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      scripts/recovery/skill_pipeline/verify_place_ik.py --solve-json <problem>
"""

from __future__ import annotations

import argparse
import json
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

CHEESE = "cream_cheese_1_main"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--num-placements", type=int, default=64)
    parser.add_argument("--offsets", default="0,0.01,0.02,0.03,0.04,0.05")
    parser.add_argument("--out-json", default="")
    return parser.parse_args(argv)


def _ik_success(ik: Any) -> int:
    return int(np.asarray(ik.success.detach().cpu()).sum())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    cfg, problem = _load_problem(solve_json)

    from curobo.geom.types import WorldConfig
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

    goal_surfaces = {str(arg) for atom in problem.goal_atoms for arg in atom.args}
    surface_objs = list(env.type_to_objects.get("Surface", []))
    surface = next((o for o in surface_objs if str(getattr(o, "name", "")) in goal_surfaces), surface_objs[-1])

    tensor_args = TensorDeviceType()
    world = TAMPWorld(
        env,
        tensor_args,
        robot=load_robot_container(cfg.robot, tensor_args),
        q_init=tensor_args.to_device(problem.q_init),
        collision_activation_distance=0.0,
    )
    conf = TAMPConfiguration(num_particles=int(args.num_placements), robot=cfg.robot, grasp_dof=int(cfg.grasp_dof))

    obj = world.get_object(CHEESE)
    obj_spheres = world.get_collision_spheres(obj)
    sampled = place_4dof_sampler(
        int(args.num_placements), obj, obj_spheres, surface,
        surface_rep=conf.placement_check,
        shrink_dist=conf.placement_shrink_dist,
        collision_activation_dist=conf.world_activation_distance,
    )
    grasps = grasp_6dof_sampler(int(args.num_placements), obj, num_faces=4 if type(obj).__name__ == "Cuboid" else None)
    world_from_ee = action_4dof_to_mat4x4(sampled) @ action_6dof_to_mat4x4(tensor_args.to_device(grasps)) @ world.tool_from_ee
    n = int(world_from_ee.shape[0])
    print(f"problem        : {solve_json.name}")
    print(f"placement on   : {getattr(surface, 'name', '?')}")
    print(f"placements     : {n}")
    print(f"placement EE z : min={float(world_from_ee[:,2,3].min()):.4f} max={float(world_from_ee[:,2,3].max()):.4f}")

    report: Dict[str, Any] = {"solve_json": str(solve_json), "num_placements": n, "sweeps": {}}

    print("\n=== 1. sweep the placement pose upward, real world ===")
    print(f"{'dz (m)':>8}{'IK ok':>8}{'/':>3}{n:>4}")
    for text in str(args.offsets).split(","):
        text = text.strip()
        if not text:
            continue
        dz = float(text)
        matrix = world_from_ee.clone()
        matrix[:, 2, 3] = matrix[:, 2, 3] + dz
        ok = _ik_success(world.ik_solver.solve_batch(Pose.from_matrix(matrix)))
        report["sweeps"][f"dz{dz:+.3f}"] = ok
        print(f"{dz:>8.3f}{ok:>8}{'/':>3}{n:>4}")

    print("\n=== 2. the placement pose with an EMPTY world (pure kinematics) ===")
    ik_empty = None
    empty_solution = None
    try:
        world.ik_solver.update_world(WorldConfig())
        ik_empty = world.ik_solver.solve_batch(Pose.from_matrix(world_from_ee))
        print(f"empty-world IK : {_ik_success(ik_empty)}/{n}")
        report["empty_world_ik"] = _ik_success(ik_empty)
        if _ik_success(ik_empty) > 0:
            index = int(np.flatnonzero(np.asarray(ik_empty.success.detach().cpu()))[0])
            empty_solution = np.asarray(ik_empty.solution[index, 0].detach().cpu().numpy(), dtype=np.float64).reshape(-1)
    except Exception as exc:
        print(f"empty-world IK failed to run: {type(exc).__name__}: {exc}")
        report["empty_world_ik"] = f"{type(exc).__name__}: {exc}"

    if empty_solution is not None:
        print("\n=== 3. what is the gripper embedded in at that configuration? ===")
        spheres = robot_spheres_at(world.robot_container, tensor_args, empty_solution)
        ranked = rank_obstacles(spheres, boxes)
        report["gripper_contacts"] = ranked[:6]
        report["empty_world_solution"] = empty_solution.astype(float).tolist()
        for row in ranked[:6]:
            print(f"   sphere {int(row['sphere_index']):>3}  {float(row['depth_m']):+.5f} m  {row['name']}")
        worst = ranked[0] if ranked else {"name": "", "depth_m": 0.0, "sphere_index": -1}
        print(f"   worst: {float(worst['depth_m']):+.5f} m on {worst['name']} (sphere {int(worst['sphere_index'])})")
    else:
        print("\n(no empty-world solution, so nothing to attribute)")

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
