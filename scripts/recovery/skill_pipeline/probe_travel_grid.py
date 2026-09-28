"""How far can the low drawer actually be pulled, and can a mid-travel re-grasp finish the job?

Two modes, both planner-level (no episode, no GPU-heavy rollout):

  grid     - sweep (tilt angle, offset along the horizontal handle bar) and measure the travel that
             the fixed-grasp slide achieves, i.e. the step where refine_articulation's per-step
             single-seed IK first fails.
  regrasp  - pull to a given slide position with the best grasp, then ask, in that moved scene,
             whether a fresh grasp can reach the handle again and continue to the target.

Facts that motivate the grid: the environment needs `qpos < -0.14` (WoodenCabinet
.default_open_ranges = [-0.16, -0.14]), while the binding targets the mean of [-0.155, -0.145] =
-0.15; and the handle bar's long axis is world +x (the brackets g41/g42 sit at +-0.032 in x), so
"higher on the bar" is not a thing - sideways along the bar is.

Usage (py310 overlay):
    .../cutamp_runner_py310_overlay.sh scripts/recovery/skill_pipeline/probe_travel_grid.py \
        --solve-json <problem.json> --mode grid --tilts 30,40,45,50,60 --dxs 0,0.02,-0.035
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.articulation import (  # noqa: E402
    ArticulatedPart,
    PathSettings,
)
from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402

ENV_OPEN_THRESHOLD = -0.14  # WoodenCabinet.default_open_ranges = [-0.16, -0.14] -> is_open: qpos < -0.14


def rz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    out = np.eye(4)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return out


def frame(approach: np.ndarray) -> np.ndarray:
    """The roll family that the orientation sweep showed is solvable (x = cross(world x, approach))."""
    approach = approach / np.linalg.norm(approach)
    hint = np.array([1.0, 0.0, 0.0]) if abs(approach[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    x_axis = np.cross(hint, approach)
    if np.linalg.norm(x_axis) < 1e-6:
        x_axis = np.cross(np.array([0.0, 1.0, 0.0]), approach)
    x_axis = x_axis / np.linalg.norm(x_axis)
    y_axis = np.cross(approach, x_axis)
    out = np.eye(4)
    out[:3, 0], out[:3, 1], out[:3, 2] = x_axis, y_axis, approach
    return out


def make_grasp(handle_pose: np.ndarray, tilt_deg: float, dx: float, standoff: float,
               bar_axis_world: np.ndarray) -> np.ndarray:
    """Grasp the bar at (centre + dx along the bar), approached from `tilt_deg` below horizontal."""
    theta = np.deg2rad(tilt_deg)
    approach = np.array([0.0, -np.cos(theta), -np.sin(theta)])
    pose = frame(approach)
    pose[:3, 3] = handle_pose[:3, 3] + bar_axis_world * dx - approach * standoff
    return np.linalg.inv(handle_pose) @ pose


def valid_detail(motion, part, q, s) -> str | None:
    """Which of `valid()`'s three rules rejects this (q, s)? None means it passes."""
    motion.set_position(float(s))
    metrics = motion.motion.check_constraints(motion._state(q))
    if not bool(metrics.feasible.all().item()):
        parts = []
        for name in ("world_collision", "self_collision", "joint_limit", "cspace", "scene_collision"):
            value = getattr(metrics, name, None)
            if value is None:
                continue
            try:
                parts.append(f"{name}={bool(value.all().item())}")
            except Exception:  # noqa: BLE001
                parts.append(f"{name}=?")
        return "constraints_infeasible(" + ",".join(parts) + ")"
    state = motion.motion.compute_kinematics(motion._state(q))
    spheres_tensor = getattr(state, "robot_spheres", None)
    if spheres_tensor is None:
        return "robot_spheres_unavailable"
    spheres = spheres_tensor.reshape(-1, 4).detach().cpu().numpy()
    if not np.isfinite(spheres).all():
        return "nonfinite_spheres"
    from experiments.robot.libero.tiptop_repro.articulation_collision import sphere_clearance

    for box in motion.boxes:
        if box.geom_id not in part.handle_geom_ids:
            continue
        colliding = np.flatnonzero((sphere_clearance(spheres, box) < -1e-5) & (spheres[:, 3] > 0))
        offenders = [int(i) for i in colliding if int(i) not in motion.finger_indices]
        if offenders:
            return f"handle_touched_by_non_finger({box.name},spheres={offenders[:4]})"
    from experiments.robot.libero.tiptop_repro.articulation_collision import boxes_overlap

    moving = [b for b in motion.boxes if b.geom_id in part.moving_geom_ids]
    fixed = [b for b in motion.boxes if b.geom_id not in part.moving_geom_ids]
    for a in moving:
        for b in fixed:
            if frozenset((a.geom_id, b.geom_id)) not in motion.allowed_pairs and boxes_overlap(a, b):
                return f"drawer_overlaps_fixed({a.name}|{b.name})"
    return None


def walk(motion, part, grasp: np.ndarray, q_start: np.ndarray, positions: np.ndarray, goal: str,
         cfg: PathSettings | None = None, detail: bool = False):
    """Mirror refine_articulation step for step: pose residual, validity, joint-jump, then IK.

    The first version of this only asked whether the per-step IK returned a solution, which
    over-reported: the IK chain can hop between arm branches (elbow up/down) and still "solve" every
    step. refine_articulation rejects that with `articulation_ik_jump` (0.25 rad per 5 mm step), and
    the full solve did reject the candidates this function had blessed. Checks are mirrored here so
    the sweep ranks candidates the way the real gate does.
    """
    from experiments.robot.libero.tiptop_repro.articulation import pose_residual

    cfg = cfg or PathSettings()

    def pose_ok(q, s) -> bool:
        error, angle = pose_residual(motion.fk(q), part.handle_pose(float(s)) @ grasp)
        return error <= cfg.position_tolerance and angle <= cfg.rotation_tolerance

    def why(q, s):
        if detail:
            return valid_detail(motion, part, q, s)
        return None if motion.valid(q, float(s), True) else "invalid"

    knots = [np.asarray(q_start, dtype=float)]
    if not pose_ok(knots[0], positions[0]):
        return knots, float(positions[0]), "handle_pose_constraint_failed"
    reason = why(knots[0], positions[0])
    if reason is not None:
        return knots, float(positions[0]), f"articulation_collision_or_joint_limit:{reason}"
    for s in positions[1:]:
        motion.set_position(float(s))
        q = motion.ik(part.handle_pose(float(s)) @ grasp, knots[-1])
        if q is None:
            return knots, float(s), "articulation_ik_failed"
        q = np.asarray(q, dtype=float)
        if np.max(np.abs(q - knots[-1])) > cfg.max_joint_jump:
            return knots, float(s), "articulation_ik_jump"
        if not pose_ok(q, s):
            return knots, float(s), "handle_pose_constraint_failed"
        reason = why(q, s)
        if reason is not None:
            return knots, float(s), f"articulation_collision_or_joint_limit:{reason}"
        knots.append(q)
    return knots, None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--mode", choices=("grid", "regrasp"), default="grid")
    parser.add_argument("--goal", default="open")
    parser.add_argument("--tilts", default="30,40,45,50,60")
    parser.add_argument("--dxs", default="0,0.02,-0.035")
    parser.add_argument("--best-tilt", type=float, default=None)
    parser.add_argument("--best-dx", type=float, default=0.0)
    parser.add_argument("--regrasp-at", type=float, default=-0.115)
    parser.add_argument("--report-out", default="")
    parser.add_argument(
        "--allow-pairs",
        default="",
        help="Extra moving/fixed geom-id pairs to allow, e.g. 195:160.",
    )
    parser.add_argument(
        "--allow-owner",
        default="",
        help="Allow every (moving drawer geom, fixed geom owned by this object) pair, matched by"
             " substring on the owning object's name, e.g. plate_1. Measures the drawer travel with"
             " that obstacle out of its way, while it still blocks the robot.",
    )
    args = parser.parse_args()

    cfg, problem = _load_problem(pathlib.Path(args.solve_json))
    binding = problem.articulation_options["bindings"][0]
    base = ArticulatedPart(**problem.articulations[binding["part_id"]])
    base_grasp = np.asarray(binding["grasps"][0], dtype=float)
    handle_pose = base.handle_pose(base.reference_position)
    standoff = float(np.linalg.norm((handle_pose @ base_grasp)[:3, 3] - handle_pose[:3, 3]))
    # The bar's long local axis is the geom's third half-extent (0.0444 m); its world direction:
    bar_axis_world = handle_pose[:3, :3] @ np.array([0.0, 0.0, 1.0])

    settings = PathSettings()
    target = float(np.mean(base.target_range(args.goal)))
    count = max(2, int(np.ceil(abs(target - base.reference_position) / settings.slide_step)) + 1)
    positions = np.linspace(base.reference_position, target, count)
    q_init = np.asarray(problem.q_init, dtype=float)

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion

    values = base.to_dict()
    values["grasps"] = [base_grasp.tolist()]
    holder = ArticulatedPart(**values)
    motion = CuroboArticulationMotion(problem, holder, cfg.robot)
    if args.allow_pairs.strip():
        for pair in args.allow_pairs.split(","):
            a, _, b = pair.partition(":")
            motion.allowed_pairs.add(frozenset((int(a), int(b))))
    if args.allow_owner.strip():
        owners = {}
        for obj in [*problem.statics, *problem.movables, *problem.surfaces]:
            geometry = getattr(obj, "geometry", {}) or {}
            for geom in (geometry.get("articulation_geoms") or geometry.get("geoms") or []):
                owners[int(geom["geom_id"])] = str(getattr(obj, "name", ""))
        needles = [v.strip() for v in args.allow_owner.split(",") if v.strip()]
        wanted = [gid for gid, owner in owners.items() if any(n in owner for n in needles)]
        for gid in wanted:
            for moving in holder.moving_geom_ids:
                motion.allowed_pairs.add(frozenset((int(moving), int(gid))))
        print(f"allow_owner {needles} -> geoms {sorted(wanted)} "
              f"({len(motion.allowed_pairs)} allowed pairs)", flush=True)

    head = {
        "solve_json": args.solve_json,
        "part_id": binding["part_id"],
        "goal": args.goal,
        "target_position": target,
        "env_open_threshold": ENV_OPEN_THRESHOLD,
        "num_slide_steps": int(count),
        "handle_xyz": np.round(handle_pose[:3, 3], 4).tolist(),
        "bar_axis_world": np.round(bar_axis_world, 4).tolist(),
        "standoff_m": round(standoff, 4),
    }
    print(json.dumps(head, indent=2), flush=True)

    def travel_row(tilt: float, dx: float) -> dict:
        grasp = make_grasp(handle_pose, tilt, dx, standoff, bar_axis_world)
        motion.set_position(base.reference_position)
        q0 = motion.ik(handle_pose @ grasp, q_init)
        row = {
            "tilt_deg": tilt,
            "dx": dx,
            "tool_center_xyz": np.round((handle_pose @ grasp)[:3, 3], 4).tolist(),
            "grasp_ik_from_q_init": q0 is not None,
        }
        if q0 is not None:
            knots, fail, reason = walk(motion, holder, grasp, q0, positions, args.goal, settings,
                                       detail=True)
            steps = len(knots) - 1
            row.update({
                "steps_solved": steps,
                "max_travel_m": round(abs(float(positions[steps])), 4),
                "first_failing_position": fail,
                "failure_reason": reason,
                "reaches_env_threshold": fail is None or float(positions[steps]) <= ENV_OPEN_THRESHOLD,
                "reaches_binding_target": steps >= count - 1,
            })
        return row

    if args.mode == "grid":
        rows = []
        tilts = [float(v) for v in args.tilts.split(",") if v.strip()]
        dxs = [float(v) for v in args.dxs.split(",") if v.strip()]
        for tilt, dx in itertools.product(tilts, dxs):
            row = travel_row(tilt, dx)
            rows.append(row)
            print(f"[tilt {tilt:>4.0f} dx {dx:+.3f}] ik={row['grasp_ik_from_q_init']} "
                  f"steps={row.get('steps_solved')} travel={row.get('max_travel_m')} "
                  f"env_ok={row.get('reaches_env_threshold')} reason={row.get('failure_reason')}", flush=True)
        best = max((r for r in rows if r.get("steps_solved") is not None),
                   key=lambda r: r["steps_solved"], default=None)
        out = {**head, "mode": "grid", "rows": rows, "best": best}
    else:
        tilt = args.best_tilt if args.best_tilt is not None else 45.0
        base_g = make_grasp(handle_pose, tilt, args.best_dx, standoff, bar_axis_world)
        motion.set_position(base.reference_position)
        q0 = motion.ik(handle_pose @ base_g, q_init)
        knots, fail, reason = (walk(motion, holder, base_g, q0, positions, args.goal, settings,
                                    detail=True)
                               if q0 is not None else ([], None, "grasp_ik_from_q_init_failed"))
        reached = float(positions[len(knots) - 1]) if knots else None
        rows = []
        if knots and reached is not None and reached <= args.regrasp_at + 1e-9:
            q_at = knots[len(knots) - 1]
            motion.set_position(args.regrasp_at)
            moved = base.handle_pose(args.regrasp_at)
            remaining = np.linspace(args.regrasp_at, target,
                                    max(2, int(np.ceil(abs(target - args.regrasp_at) / settings.slide_step)) + 1))
            candidates = {
                "same_tilt": base_g,
                "horizontal": base_grasp,
                "tilt60": make_grasp(handle_pose, 60.0, args.best_dx, standoff, bar_axis_world),
                "tilt30_otherside": make_grasp(handle_pose, 30.0, -args.best_dx, standoff, bar_axis_world),
            }
            for name, grasp in candidates.items():
                pose = moved @ grasp
                pre = pose.copy()
                pre[:3, 3] -= pose[:3, 2] * 0.05
                row = {"candidate": name, "grasp_ik_from_current_arm": motion.ik(pose, q_at) is not None}
                try:
                    plan = motion._plan(q_at, pre, args.regrasp_at)
                    row["free_motion_to_regrasp"] = {"ok": True, "points": int(len(plan))}
                    q_new = motion.ik(pose, np.asarray(plan[-1], dtype=float))
                except Exception as exc:  # noqa: BLE001
                    row["free_motion_to_regrasp"] = {"ok": False, "error": str(exc)}
                    q_new = None
                row["regrasp_ik_after_approach"] = q_new is not None
                if q_new is not None:
                    knots2, fail2, reason2 = walk(motion, holder, grasp, np.asarray(q_new, dtype=float),
                                                  remaining, args.goal, settings, detail=True)
                    steps2 = len(knots2) - 1
                    pos2 = float(remaining[steps2])
                    row.update({
                        "continued_steps": steps2,
                        "final_position": pos2,
                        "continued_failure_reason": reason2,
                        "finishes_to_target": steps2 >= len(remaining) - 1,
                        "reaches_env_threshold": pos2 <= ENV_OPEN_THRESHOLD,
                    })
                rows.append(row)
                print(f"[regrasp {name}] {row}", flush=True)
        out = {**head, "mode": "regrasp", "pull_grasp": {"tilt_deg": tilt, "dx": args.best_dx},
               "pulled_to": reached, "regrasp_at": args.regrasp_at, "candidates": rows}

    text = json.dumps(out, indent=2)
    print(text)
    if args.report_out:
        pathlib.Path(args.report_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
