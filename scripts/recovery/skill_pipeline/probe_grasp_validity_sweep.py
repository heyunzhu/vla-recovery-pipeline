"""Is any top-down grasp of the cheese both collision-free AND IK-solvable?

`verify_grasp_ik.py` found a perfect disagreement on the installed profile's 24 candidates:

  * yaw in {0, -180}  -> gripper clear of the cheese (penetration 0.00 mm), IK fails
                         in the real scene AND with an empty world
  * yaw in {+-90}     -> gripper 25.6-32.7 mm INSIDE the cheese, IK succeeds

cuTAMP's pre-IK filter keeps only `grasp_coll <= 1e-2`, so it keeps exactly the twelve that
IK cannot solve and throws away exactly the twelve IK can. Every particle is infeasible
before the optimiser ever sees it, which is why `Pick(...) IK success: 0/64` is deterministic
rather than unlucky.

That leaves one question that decides the fix: is the profile's yaw set just badly chosen, or
is the whole top-down family blocked at this object pose? This sweeps the two degrees of
freedom the profile pins down -- the hand's yaw about the world vertical, and how deep the
TCP sits -- and reports cuTAMP's collision filter and cuRobo's IK side by side for each.

    ROOT=<work> OVERLAY_ROOT=<repo> \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      scripts/recovery/skill_pipeline/probe_grasp_validity_sweep.py --solve-json <problem>
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

from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402
from scripts.recovery.skill_pipeline.verify_grasp_ik import (  # noqa: E402
    _extents,
    _ik_world_obstacle_names,
    _solutions,
    _statuses,
    _success_flags,
)

CHEESE = "cream_cheese_1_main"
DEFAULT_YAW_OFFSETS = "0,30,45,60,90,120,135,150,180,210,225,240,270,300,315,330"
DEFAULT_DEPTH_FRACS = "0.35,0.15"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--object", default=CHEESE)
    parser.add_argument("--yaw-offsets", default=DEFAULT_YAW_OFFSETS, help="degrees from the object's long axis")
    parser.add_argument("--depth-fracs", default=DEFAULT_DEPTH_FRACS, help="fractions of the half thickness, below the top face")
    parser.add_argument("--long-offsets", default="0.0", help="metres along the object's long axis")
    parser.add_argument("--out-json", default="")
    return parser.parse_args(argv)


def _floats(text: str) -> List[float]:
    return [float(item) for item in str(text).split(",") if item.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    cfg, problem = _load_problem(solve_json)

    from curobo.geom.types import WorldConfig
    from curobo.types.base import TensorDeviceType
    from curobo.types.math import Pose
    from cutamp.config import TAMPConfiguration
    from cutamp.particle_initialization import sphere_to_sphere_overlap, transform_spheres
    from cutamp.robots import load_robot_container
    from cutamp.tamp_world import TAMPWorld
    from cutamp.utils.common import action_6dof_to_mat4x4, pose_list_to_mat4x4
    from experiments.robot.libero.tiptop_repro.grasp_profiles import (
        matrix_to_xyz_rpy,
        pose7_rotation_matrix,
        rot_z,
    )
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend

    backend = RealCuTAMPBackend(cfg)
    env, name_map, goal_notes, geometry_debug = backend._build_env(problem)

    tensor_args = TensorDeviceType()
    world = TAMPWorld(
        env,
        tensor_args,
        robot=load_robot_container(cfg.robot, tensor_args),
        q_init=tensor_args.to_device(problem.q_init),
        collision_activation_distance=0.0,
    )
    conf = TAMPConfiguration(num_particles=64, robot=cfg.robot, grasp_dof=6)
    obj = world.get_object(args.object)
    obj_dims = [float(value) for value in getattr(obj, "dims", []) or []]
    obj_pose = [float(value) for value in getattr(obj, "pose", []) or []]

    ext = _extents(obj_dims)
    world_from_obj_np = pose7_rotation_matrix(obj_pose)
    vertical_axis = int(np.argmax(np.abs(world_from_obj_np[2, :])))
    horizontal = [axis for axis in range(3) if axis != vertical_axis]
    long_axis = max(horizontal, key=lambda axis: float(ext[axis]))
    across_axis = [axis for axis in horizontal if axis != long_axis][0]
    top_sign = 1.0 if float(world_from_obj_np[2, vertical_axis]) >= 0.0 else -1.0
    long_world = world_from_obj_np[:, long_axis]
    long_yaw = float(np.arctan2(float(long_world[1]), float(long_world[0])))
    half = 0.5 * ext

    print(f"problem     : {solve_json.name}")
    print(f"object      : {args.object}  dims={[round(value, 5) for value in obj_dims]}")
    print(f"              pose={[round(value, 4) for value in obj_pose]}")
    print(f"axes        : vertical={vertical_axis} long={long_axis} across={across_axis} "
          f"top_sign={top_sign:+.0f} long_yaw={np.degrees(long_yaw):+.1f} deg")
    print(f"extents mm  : long={ext[long_axis]*1000:.2f} across={ext[across_axis]*1000:.2f} "
          f"vertical={ext[vertical_axis]*1000:.2f}   grasp_dof={conf.grasp_dof}")

    world_from_obj = pose_list_to_mat4x4(tensor_args.to_device(obj_pose)).to(tensor_args.device)

    combos: List[Dict[str, Any]] = []
    rows: List[List[float]] = []
    for frac in _floats(args.depth_fracs):
        for long_offset in _floats(args.long_offsets):
            for offset_deg in _floats(args.yaw_offsets):
                yaw = long_yaw + np.radians(offset_deg)
                local = np.zeros(3, dtype=np.float64)
                local[vertical_axis] = top_sign * (-frac * float(half[vertical_axis]))
                local[long_axis] = float(long_offset)
                object_from_grasp = world_from_obj_np.T @ rot_z(float(yaw))
                rpy = matrix_to_xyz_rpy(object_from_grasp)
                combos.append(
                    {
                        "yaw_offset_deg": float(offset_deg),
                        "depth_frac": float(frac),
                        "depth_from_top_m": float((1.0 + frac) * float(half[vertical_axis])),
                        "long_offset_m": float(long_offset),
                        "world_yaw_deg": float(np.degrees(np.arctan2(np.sin(yaw), np.cos(yaw)))),
                        "closing_axis": int(np.argmax(np.abs(object_from_grasp[:, 0]))),
                        "straddle_m": float(
                            ext[across_axis] if int(np.argmax(np.abs(object_from_grasp[:, 0]))) == long_axis else ext[long_axis]
                        ),
                    }
                )
                rows.append([*local.tolist(), *rpy])

    tensor_rows = tensor_args.to_device(np.asarray(rows, dtype=np.float32))
    world_from_ee = world_from_obj @ action_6dof_to_mat4x4(tensor_rows) @ world.tool_from_ee
    n = len(combos)
    print(f"combinations: {n}   ik world obstacles={len(_ik_world_obstacle_names(world))}")

    obj_from_grasp = action_6dof_to_mat4x4(tensor_rows)
    grip_spheres = transform_spheres(world.robot_container.gripper_spheres, obj_from_grasp)
    grasp_coll = np.asarray(
        sphere_to_sphere_overlap(world.get_collision_spheres(args.object), grip_spheres, activation_distance=0.0)
        .detach()
        .cpu()
    ).reshape(-1)
    free = grasp_coll <= 1e-2

    ik_real = world.ik_solver.solve_batch(Pose.from_matrix(world_from_ee))
    ok_real = _success_flags(ik_real)
    statuses_real = _statuses(ik_real, n)
    solved_real = _solutions(ik_real)

    ok_empty = np.zeros(n, dtype=bool)
    statuses_empty = [""] * n
    try:
        world.ik_solver.update_world(WorldConfig())
        ik_empty = world.ik_solver.solve_batch(Pose.from_matrix(world_from_ee))
        ok_empty = _success_flags(ik_empty)
        statuses_empty = _statuses(ik_empty, n)
    except Exception as exc:
        print(f"empty-world IK failed: {type(exc).__name__}: {exc}")

    print("\n=== swept candidates (mm) ===")
    print(f"{'yawOff':>7}{'depth':>7}{'longOff':>8}{'close':>6}{'strad':>7}{'gcoll':>8}{'free':>6}{'ik':>5}{'ikEmp':>7}  BOTH")
    both: List[Dict[str, Any]] = []
    for index, combo in enumerate(combos):
        usable = bool(free[index] and ok_real[index])
        if usable:
            both.append({**combo, "index": index})
        print(
            f"{combo['yaw_offset_deg']:>7.1f}{combo['depth_from_top_m']*1000:>7.2f}{combo['long_offset_m']*1000:>8.2f}"
            f"{combo['closing_axis']:>6}{combo['straddle_m']*1000:>7.1f}{grasp_coll[index]*1000:>8.2f}"
            f"{('yes' if free[index] else 'NO'):>6}{('ok' if ok_real[index] else 'FAIL'):>5}"
            f"{('ok' if ok_empty[index] else 'FAIL'):>7}  {'<== USABLE' if usable else ''}"
        )

    print("\n=== verdict ===")
    print(f"  collision-free : {int(free.sum())}/{n}")
    print(f"  IK-solvable    : {int(ok_real.sum())}/{n}   (empty world: {int(ok_empty.sum())}/{n})")
    print(f"  BOTH           : {len(both)}/{n}")
    if both:
        offsets = sorted({round(float(item["yaw_offset_deg"]), 1) for item in both})
        print(f"  usable yaw offsets (deg from the long axis): {offsets}")
        print("  => the profile's fixed yaw set {0,90,180,270} misses all of them" if not set(offsets) & {0.0, 90.0, 180.0, 270.0} else "  => some of them are already in the profile's yaw set")
    else:
        print("  => no top-down grasp in this family is both collision-free and IK-solvable;")
        print("     the profile's yaw set is not the whole problem")
    print("\n=== candidates IK solves while the gripper is inside the object ===")
    inside = [index for index in range(n) if ok_real[index] and not free[index]]
    print(f"  {len(inside)}/{n}" + (f"   penetration {grasp_coll[inside].min()*1000:.2f}..{grasp_coll[inside].max()*1000:.2f} mm" if inside else ""))
    print("\n=== candidates that are collision-free but IK cannot solve ===")
    blocked = [index for index in range(n) if free[index] and not ok_real[index]]
    print(f"  {len(blocked)}/{n}"
          + (f"   empty-world IK also fails for {sum(1 for index in blocked if not ok_empty[index])} of them"
             if blocked else ""))
    if blocked:
        sample = blocked[0]
        print(f"  sample #{sample}: yawOff={combos[sample]['yaw_offset_deg']:+.1f} "
              f"depth={combos[sample]['depth_from_top_m']*1000:.2f}mm status={statuses_real[sample]!r}/{statuses_empty[sample]!r}")

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "solve_json": str(solve_json),
                    "object": args.object,
                    "object_dims": obj_dims,
                    "object_pose": obj_pose,
                    "axes": {"vertical": vertical_axis, "long": long_axis, "across": across_axis},
                    "combinations": [
                        {
                            **combo,
                            "gripper_object_penetration_m": float(grasp_coll[index]),
                            "gripper_object_free": bool(free[index]),
                            "ik_real": bool(ok_real[index]),
                            "ik_empty": bool(ok_empty[index]),
                            "status_real": statuses_real[index],
                            "status_empty": statuses_empty[index],
                            "q_real": (
                                [float(value) for value in np.asarray(solved_real[index, 0]).reshape(-1)]
                                if solved_real is not None and solved_real.shape[0] > index
                                else None
                            ),
                        }
                        for index, combo in enumerate(combos)
                    ],
                    "collision_free": int(free.sum()),
                    "ik_solvable": int(ok_real.sum()),
                    "usable": len(both),
                    "usable_yaw_offsets_deg": sorted({float(item["yaw_offset_deg"]) for item in both}),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
