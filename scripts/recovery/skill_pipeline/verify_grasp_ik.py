"""Of the 24 grasps the installed profile actually offers, which ones can be executed?

`compare_grasps_profiled.py` settled *which* sampler runs: every task04 run passes
`--real_cutamp_grasp_dof 6`, so `_allow_mesh_6dof_grasp_sampling` replaces cuTAMP's native
6-DOF sampler with the pack profile `cream_cheese_flat_box_topdown_deep_v1`, and the result is
64/64 tool-down grasps drawn from exactly 24 distinct poses (2 depths x 3 long-axis offsets x
4 yaws), cycled to fill `num_particles`. This probe asks the next question, per candidate:

  * does cuRobo IK solve it in the real scene?
  * does it solve it with an EMPTY world (pure reachability)?
  * when the two disagree, what is the hand embedded in at the empty-world solution?

It also records, per candidate, which object axis each of the grasp frame's two horizontal
axes lines up with, because for half of the yaw choices the fingers have to open across the
cheese's 81 mm long axis instead of its 42.7 mm short one. Whether that matters is exactly
what the IK numbers should show, so the two are printed side by side rather than assumed.

One more layer matters before any of that: cuTAMP does not feed the sampler's output
straight to IK. `particle_initialization.py` oversamples `num_particles * 2`, scores every
row with `sphere_to_sphere_overlap` between the gripper spheres and the object spheres, keeps
only rows with `grasp_coll <= 1e-2`, takes the first `num_particles` of those *in sampler
order*, and pads with `torch.randint` if there are too few. Since the profile's 24 candidates
are cycled to fill the oversampled array, that prefix rule makes the low-ranked candidates
dominate whenever only some are collision-free. This probe reproduces that filter so the
candidate table shows the grasps cuTAMP would actually keep.

    ROOT=<work> OVERLAY_ROOT=<repo> \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      scripts/recovery/skill_pipeline/verify_grasp_ik.py \\
        --solve-json <problem> \\
        --profile cream_cheese_flat_box_topdown_deep_v1 \\
        --adapter <pack>/code/grasp_profiles.py
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
DEFAULT_PROFILE = "cream_cheese_flat_box_topdown_deep_v1"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--adapter", default="")
    parser.add_argument("--object", default=CHEESE)
    parser.add_argument("--num-grasps", type=int, default=64)
    parser.add_argument("--out-json", default="")
    return parser.parse_args(argv)


def _extents(dims: Sequence[float]) -> np.ndarray:
    ext = np.asarray(list(dims), dtype=np.float64).reshape(-1)
    if ext.size < 3:
        ext = np.pad(ext, (0, 3 - ext.size), constant_values=0.0)
    return np.maximum(ext[:3], 1e-4)


def _straddle_extent(axis: int, vertical_axis: int, long_axis: int, across_axis: int, ext: np.ndarray) -> float:
    """Extent the fingers must open across if `axis` is the closing axis.

    The closing axis is horizontal for a tool-down grasp; the fingers then straddle the
    extent of the *other* horizontal axis.
    """
    if axis == vertical_axis:
        return float("nan")
    return float(ext[across_axis]) if axis == long_axis else float(ext[long_axis])


def grasp_candidate_table(
    profile: str,
    dims: Sequence[float],
    pose: Optional[Sequence[float]],
    *,
    rim: bool = False,
    registry: Any = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Pure, cuRobo-free description of the candidates the profile emits.

    `_topdown_6dof` fills `num_samples` particles by cycling the profile's own list, so the
    first `len(list)` rows are exactly the distinct candidates, in the profile's order.
    """
    from experiments.robot.libero.tiptop_repro.grasp_profiles import (
        pose7_rotation_matrix,
        rot_z,
        sample_grasp_profile,
    )

    ext = _extents(dims)
    world_from_obj = pose7_rotation_matrix(pose)
    vertical_axis = int(np.argmax(np.abs(world_from_obj[2, :])))
    horizontal = [axis for axis in range(3) if axis != vertical_axis]
    long_axis = max(horizontal, key=lambda axis: float(ext[axis]))
    across_axis = [axis for axis in horizontal if axis != long_axis][0]

    samples = list(sample_grasp_profile(profile, ext, rim=rim, pose=pose, registry=registry))
    if limit is not None:
        samples = samples[: int(limit)]

    rows: List[Dict[str, Any]] = []
    for rank, sample in enumerate(samples):
        yaw = float(sample.metadata.get("world_yaw", sample.rpy[2]))
        wrapping = float(np.arctan2(np.sin(yaw), np.cos(yaw)))
        object_from_grasp = world_from_obj.T @ rot_z(yaw)
        axes = {name: int(np.argmax(np.abs(object_from_grasp[:, column]))) for column, name in ((0, "x"), (1, "y"))}
        rows.append(
            {
                "rank": rank,
                "xyzrpy": [float(value) for value in sample.xyzrpy()],
                "world_yaw_deg": float(np.degrees(wrapping)),
                "depth_from_top_m": float(sample.metadata.get("depth_from_top", float("nan"))),
                "vertical_axis": vertical_axis,
                "long_axis": long_axis,
                "across_axis": across_axis,
                "closing_axis_local": axes,
                "local_xyz": [float(value) for value in sample.xyz],
                "local_rpy": [float(value) for value in sample.rpy],
                "straddle_if_x_closes_m": _straddle_extent(axes["x"], vertical_axis, long_axis, across_axis, ext),
                "straddle_if_y_closes_m": _straddle_extent(axes["y"], vertical_axis, long_axis, across_axis, ext),
            }
        )
    return rows


def _success_flags(ik: Any) -> np.ndarray:
    return np.asarray(ik.success.detach().cpu(), dtype=bool).reshape(-1)


def _statuses(ik: Any, count: int) -> List[str]:
    status = getattr(ik, "status", None)
    if status is None:
        return [""] * count
    try:
        values = np.asarray(status).reshape(-1)
    except Exception:
        return [str(status)] * count
    if values.size == 1:
        return [str(values[0])] * count
    return [str(value) for value in values[:count]]


def _solutions(ik: Any) -> Optional[np.ndarray]:
    solution = getattr(ik, "solution", None)
    if solution is None:
        return None
    return np.asarray(solution.detach().cpu().numpy(), dtype=np.float64)


def _solution_at(solved: Optional[np.ndarray], index: int) -> Optional[List[float]]:
    if solved is None or solved.shape[0] <= index:
        return None
    return [float(value) for value in np.asarray(solved[index, 0]).reshape(-1)]


def _ik_world_obstacle_names(world: Any) -> List[str]:
    try:
        model = world.ik_solver.world_model
        return [str(getattr(item, "name", "?")) for item in model.objects]
    except Exception:
        pass
    for attribute in ("world_coll_checker", "world_model"):
        try:
            holder = getattr(world.ik_solver, attribute)
            data = getattr(holder, "world_model", holder)
            return [str(getattr(item, "name", "?")) for item in data.objects]
        except Exception:
            continue
    return []


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    cfg, problem = _load_problem(solve_json)

    from curobo.geom.types import WorldConfig
    from curobo.types.base import TensorDeviceType
    from curobo.types.math import Pose
    from cutamp.config import TAMPConfiguration
    from cutamp.robots import load_robot_container
    from cutamp import samplers as samplers_module
    from cutamp.particle_initialization import sphere_to_sphere_overlap, transform_spheres
    from cutamp.tamp_world import TAMPWorld
    from cutamp.utils.common import action_6dof_to_mat4x4, get_world_cfg, pose_list_to_mat4x4
    from experiments.robot.libero.tiptop_repro.grasp_profiles import (
        registry_from_adapter_paths,
        sample_grasp_profile_xyzrpy,
    )
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
        RealCuTAMPBackend,
        _allow_mesh_6dof_grasp_sampling,
        _use_rim_6dof_grasp,
    )

    adapter = args.adapter or cfg.grasp_profile_adapter_path
    registry = registry_from_adapter_paths([adapter]) if adapter else registry_from_adapter_paths([])

    backend = RealCuTAMPBackend(cfg)
    env, name_map, goal_notes, geometry_debug = backend._build_env(problem)
    boxes = obb_boxes_from_world_config(get_world_cfg(env, include_movables=False))

    tensor_args = TensorDeviceType()
    world = TAMPWorld(
        env,
        tensor_args,
        robot=load_robot_container(cfg.robot, tensor_args),
        q_init=tensor_args.to_device(problem.q_init),
        collision_activation_distance=0.0,
    )
    conf = TAMPConfiguration(num_particles=int(args.num_grasps), robot=cfg.robot, grasp_dof=6)
    obj = world.get_object(args.object)
    obj_dims = [float(value) for value in getattr(obj, "dims", []) or []]
    obj_pose = [float(value) for value in getattr(obj, "pose", []) or []]
    rim = bool(_use_rim_6dof_grasp(obj))

    print(f"problem          : {solve_json.name}")
    print(f"object           : {args.object}  type={type(obj).__name__}  rim={rim}")
    print(f"  dims           : {[round(value, 5) for value in obj_dims]}")
    print(f"  pose           : {[round(value, 4) for value in obj_pose]}")
    print(f"  profile        : {args.profile}")
    print(f"  adapter        : {adapter}")
    print(f"  grasp_dof      : {conf.grasp_dof}   particles={conf.num_particles}")

    # What the runs really sample: the monkeypatched sampler, not cuTAMP's native one.
    # particle_initialization.py oversamples num_particles * 2 before filtering.
    n_oversample = int(args.num_grasps) * 2
    with _allow_mesh_6dof_grasp_sampling(args.profile, adapter_path=adapter):
        sampled = samplers_module.grasp_6dof_sampler(n_oversample, obj)
    rows_all = np.asarray(sampled.detach().cpu().numpy(), dtype=np.float64).reshape(n_oversample, -1)
    cycle = np.asarray(
        sample_grasp_profile_xyzrpy(args.profile, obj_dims, rim=rim, pose=obj_pose, registry=registry),
        dtype=np.float64,
    ).reshape(-1, 6)
    n_candidates = int(cycle.shape[0])
    distinct = np.unique(np.round(rows_all, 9), axis=0)
    print(f"  particles      : sampler called with {n_oversample} (2x oversample)  "
          f"distinct={len(distinct)}  profile candidates={n_candidates}")
    # the patched sampler cycles the profile's list, so the head of the particle array must be it
    assert np.allclose(rows_all[:n_candidates], cycle, atol=1e-6), "patched sampler no longer cycles the profile list"
    if rows_all.shape[0] > n_candidates:
        # _topdown_6dof pads the profile's list to num_particles by cycling it, so the tail
        # must be the same candidates again -- duplicated exactly, not resampled.
        expected = cycle[np.arange(rows_all.shape[0] - n_candidates) % n_candidates]
        assert np.allclose(rows_all[n_candidates:], expected, atol=1e-6)
    table = grasp_candidate_table(args.profile, obj_dims, obj_pose, rim=rim, registry=registry)
    assert len(table) == n_candidates, (len(table), n_candidates)

    # --- cuTAMP's own gripper-vs-object filter, copied from particle_initialization.py -------
    #     grasp_spheres = transform_spheres(world.robot_container.gripper_spheres, obj_from_grasp)
    #     grasp_coll    = sphere_to_sphere_overlap(obj_spheres, grasp_spheres, activation_distance=0.0)
    #     collision_free_mask = grasp_coll <= 1e-2
    # This runs BEFORE IK and is what decides which of the 24 candidates can be reached at all.
    obj_from_grasp_all = action_6dof_to_mat4x4(tensor_args.to_device(rows_all.astype(np.float32)))
    grip_spheres = transform_spheres(world.robot_container.gripper_spheres, obj_from_grasp_all)
    grasp_coll = np.asarray(
        sphere_to_sphere_overlap(world.get_collision_spheres(args.object), grip_spheres, activation_distance=0.0)
        .detach()
        .cpu()
    ).reshape(-1)
    free_mask = grasp_coll <= 1e-2
    per_candidate_coll = grasp_coll[:n_candidates]
    per_candidate_free = free_mask[:n_candidates]
    print("  gripper-vs-object filter (cuTAMP's own pre-IK filter)")
    print(f"    oversampled rows free : {int(free_mask.sum())}/{n_oversample}")
    print(f"    distinct candidates   : {int(per_candidate_free.sum())}/{n_candidates} free")
    for candidate_index, value in enumerate(per_candidate_coll):
        table[candidate_index]["gripper_object_penetration_m"] = float(value)
        table[candidate_index]["gripper_object_free"] = bool(per_candidate_free[candidate_index])
    if free_mask.any():
        cfree = rows_all[free_mask]
        kept_rows = np.flatnonzero(free_mask)[: int(args.num_grasps)]
        branch = f"collision-free prefix of {cfree.shape[0]} rows"
        selected = cfree[: int(args.num_grasps)]
    else:
        order = np.argsort(grasp_coll)[: int(args.num_grasps)]
        kept_rows = order
        branch = "no collision-free grasp: lowest-collision fallback"
        selected = rows_all[order]
    print(f"    selection branch      : {branch}")
    print(f"    selected rows         : {selected.shape[0]}  distinct={len(np.unique(np.round(selected, 9), axis=0))}")
    rank_counts: Dict[int, int] = {}
    for row_index in kept_rows:
        rank = int(row_index) % n_candidates
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    print(
        "    candidate ranks in the selected set: "
        + ", ".join(f"#{rank}x{count}" for rank, count in sorted(rank_counts.items()))
    )
    if selected.shape[0] < int(args.num_grasps):
        print(f"    (fewer than {args.num_grasps}: particle_initialization pads with torch.randint)")

    world_from_obj = pose_list_to_mat4x4(tensor_args.to_device(obj_pose)).to(tensor_args.device)
    rows = tensor_args.to_device(cycle.astype(np.float32))
    world_from_ee = world_from_obj @ action_6dof_to_mat4x4(rows) @ world.tool_from_ee

    obstacle_names = _ik_world_obstacle_names(world)
    print(f"  ik world       : {len(obstacle_names)} obstacles")
    if obstacle_names:
        shown = ", ".join(obstacle_names[:12])
        print(f"                   {shown}{' ...' if len(obstacle_names) > 12 else ''}")
        print(f"                   includes target object: {args.object in obstacle_names}")

    print("\n=== 1. IK for every profile candidate, REAL scene ===")
    ik_real = world.ik_solver.solve_batch(Pose.from_matrix(world_from_ee))
    ok_real = _success_flags(ik_real)
    statuses_real = _statuses(ik_real, n_candidates)
    solved_real = _solutions(ik_real)
    print(f"real-scene IK success: {int(ok_real.sum())}/{n_candidates}")

    print("\n=== 2. IK for the same candidates with an EMPTY world (pure reachability) ===")
    ok_empty = np.zeros(n_candidates, dtype=bool)
    statuses_empty = [""] * n_candidates
    solved_empty: Optional[np.ndarray] = None
    try:
        world.ik_solver.update_world(WorldConfig())
        ik_empty = world.ik_solver.solve_batch(Pose.from_matrix(world_from_ee))
        ok_empty = _success_flags(ik_empty)
        statuses_empty = _statuses(ik_empty, n_candidates)
        solved_empty = _solutions(ik_empty)
        print(f"empty-world IK success: {int(ok_empty.sum())}/{n_candidates}")
    except Exception as exc:
        print(f"empty-world IK failed to run: {type(exc).__name__}: {exc}")

    print("\n=== 3. per-candidate detail ===")
    print(
        f"{'#':>3}{'yaw':>7}{'depth':>7}{'xax':>5}{'yax':>5}"
        f"{'stradX':>8}{'stradY':>8}{'gcoll':>8}{'free':>5}{'real':>6}{'empty':>7}  status  (mm)"
    )
    detail: List[Dict[str, Any]] = []
    for index, row in enumerate(table):
        status = statuses_real[index] if ok_real[index] else (statuses_empty[index] or statuses_real[index])
        print(
            f"{index:>3}{row['world_yaw_deg']:>7.1f}{row['depth_from_top_m']*1000:>7.2f}"
            f"{row['closing_axis_local']['x']:>5}{row['closing_axis_local']['y']:>5}"
            f"{row['straddle_if_x_closes_m']*1000:>8.1f}{row['straddle_if_y_closes_m']*1000:>8.1f}"
            f"{row.get('gripper_object_penetration_m', float('nan'))*1000:>8.2f}"
            f"{('yes' if row.get('gripper_object_free') else 'no'):>5}"
            f"{('ok' if ok_real[index] else 'FAIL'):>6}{('ok' if ok_empty[index] else 'FAIL'):>7}  {status}"
        )
        detail.append(
            {
                **row,
                "ik_real": bool(ok_real[index]),
                "ik_empty": bool(ok_empty[index]),
                "status_real": statuses_real[index],
                "status_empty": statuses_empty[index],
                "ee_xyz": [float(value) for value in np.asarray(world_from_ee[index, :3, 3].detach().cpu())],
                "q_real": _solution_at(solved_real, index),
                "q_empty": _solution_at(solved_empty, index),
            }
        )

    print("\n=== 4. grouped by yaw, and by the extent the fingers must straddle ===")
    by_yaw: Dict[str, Dict[str, int]] = {}
    for row in detail:
        bucket = by_yaw.setdefault(f"{float(row['world_yaw_deg']):.1f}", {"n": 0, "real": 0, "empty": 0})
        bucket["n"] += 1
        bucket["real"] += int(row["ik_real"])
        bucket["empty"] += int(row["ik_empty"])
    for yaw in sorted(by_yaw, key=float):
        bucket = by_yaw[yaw]
        print(f"  yaw {float(yaw):>7.1f} deg : real {bucket['real']}/{bucket['n']}   empty {bucket['empty']}/{bucket['n']}")
    for key, label in (("straddle_if_x_closes_m", "grasp x closes"), ("straddle_if_y_closes_m", "grasp y closes")):
        by_extent: Dict[str, Dict[str, int]] = {}
        for row in detail:
            value = float(row[key])
            bucket = by_extent.setdefault("n/a" if np.isnan(value) else f"{value*1000:.1f}", {"n": 0, "real": 0})
            bucket["n"] += 1
            bucket["real"] += int(row["ik_real"])
        for extent in sorted(by_extent):
            bucket = by_extent[extent]
            print(f"  straddle {extent:>6} mm ({label}) : real {bucket['real']}/{bucket['n']}")
    by_filter: Dict[str, Dict[str, int]] = {}
    for row in detail:
        key = "cuTAMP keeps (gripper free)" if row.get("gripper_object_free") else "cuTAMP drops (gripper in object)"
        bucket = by_filter.setdefault(key, {"n": 0, "real": 0, "empty": 0})
        bucket["n"] += 1
        bucket["real"] += int(row["ik_real"])
        bucket["empty"] += int(row["ik_empty"])
    for key in sorted(by_filter):
        bucket = by_filter[key]
        print(f"  {key:<34}: real {bucket['real']}/{bucket['n']}   empty {bucket['empty']}/{bucket['n']}")

    print("\n=== 5. scene failures that an empty world solves (so: collision) ===")
    contested = [row for row in detail if not row["ik_real"] and row["ik_empty"]]
    if not contested:
        print("  (none)")
    for row in contested[:10]:
        print(f"  #{row['rank']:>3} yaw={row['world_yaw_deg']:>7.1f} depth={row['depth_from_top_m']*1000:.2f}mm")
        configuration = row["q_empty"]
        if configuration is None:
            continue
        spheres = robot_spheres_at(world.robot_container, tensor_args, configuration)
        for item in rank_obstacles(spheres, boxes)[:3]:
            print(f"        sphere {int(item['sphere_index']):>3}  {float(item['depth_m']):+.5f} m  {item['name']}")

    print("\n=== 6. scene failures that an empty world also fails (so: kinematics) ===")
    unreachable = [row for row in detail if not row["ik_real"] and not row["ik_empty"]]
    print(f"  {len(unreachable)}/{n_candidates} candidates")
    for row in unreachable[:6]:
        print(
            f"  #{row['rank']:>3} yaw={row['world_yaw_deg']:>7.1f} depth={row['depth_from_top_m']*1000:.2f}mm"
            f"  status={row['status_empty'] or row['status_real']}"
        )

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "solve_json": str(solve_json),
                    "profile": args.profile,
                    "adapter": adapter,
                    "object": args.object,
                    "object_dims": obj_dims,
                    "object_pose": obj_pose,
                    "num_particles": int(args.num_grasps),
                    "num_distinct": int(len(distinct)),
                    "num_candidates": n_candidates,
                    "gripper_free_oversampled_rows": int(free_mask.sum()),
                    "gripper_free_candidates": int(per_candidate_free.sum()),
                    "selection_branch": branch,
                    "selected_rank_counts": {str(key): value for key, value in sorted(rank_counts.items())},
                    "ik_world_obstacles": obstacle_names,
                    "real_scene_ik_success": int(ok_real.sum()),
                    "empty_world_ik_success": int(ok_empty.sum()),
                    "by_yaw": by_yaw,
                    "candidates": detail,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
