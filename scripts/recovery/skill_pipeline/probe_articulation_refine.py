"""Is `articulation_ik_failed` a real infeasibility, or the single-seed IK inside refine_articulation?

`refine_articulation` walks the slide with `motion.ik(pose, seed=previous_knot)` - one seed per step -
while `plan_single` uses the full multi-seed IK. This probe walks the same slide positions with a
candidate grasp, finds the first step whose single-seed IK returns nothing, and then re-asks that same
pose with other seeds and with the multi-seed planner.

Usage (py310 overlay):
    .../cutamp_runner_py310_overlay.sh scripts/recovery/skill_pipeline/probe_articulation_refine.py \
        --solve-json <problem.json> --candidate probe45 --report-out <report.json>
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
    ArticulationError,
    PathSettings,
)
from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402
from experiments.robot.libero.tiptop_repro.articulation_collision import (  # noqa: E402
    boxes_overlap,
    sphere_clearance,
)


def rz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    out = np.eye(4)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return out


def roll_grasp(grasp: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate the tool about its own z (approach) axis only: z and the tool origin are unchanged."""
    return np.asarray(grasp, dtype=float) @ rz(np.deg2rad(degrees))


def offset_grasp(grasp: np.ndarray, offset_handle_xyz: tuple[float, float, float]) -> np.ndarray:
    """Translate a handle-relative grasp in the handle frame, preserving orientation."""
    out = np.asarray(grasp, dtype=float).copy()
    out[:3, 3] += np.asarray(offset_handle_xyz, dtype=float)
    return out


def _csv_floats(raw: str) -> list[float]:
    return [float(value) for value in raw.split(",") if value.strip()]


def probe_style_grasp(handle_pose: np.ndarray, approach: np.ndarray, standoff: float) -> np.ndarray:
    approach = approach / np.linalg.norm(approach)
    hint = np.array([1.0, 0.0, 0.0]) if abs(approach[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    x_axis = np.cross(hint, approach)
    if np.linalg.norm(x_axis) < 1e-6:
        x_axis = np.cross(np.array([0.0, 1.0, 0.0]), approach)
    x_axis = x_axis / np.linalg.norm(x_axis)
    y_axis = np.cross(approach, x_axis)
    pose = np.eye(4)
    pose[:3, 0], pose[:3, 1], pose[:3, 2] = x_axis, y_axis, approach
    pose[:3, 3] = handle_pose[:3, 3] - approach * standoff
    return np.linalg.inv(handle_pose) @ pose


def candidate_grasp(name: str, base: np.ndarray, handle_pose: np.ndarray, standoff: float):
    if name == "horizontal":
        return base
    kind, _, deg = name.partition("probe" if name.startswith("probe") else "rz")
    theta = np.deg2rad(float(deg or 45.0))
    if name.startswith("rz"):
        return rz(theta) @ base
    approach = np.array([0.0, -np.cos(theta), -np.sin(theta)])
    return probe_style_grasp(handle_pose, approach, standoff)


def _invalid_diagnostics(motion, q: np.ndarray, position: float) -> dict:
    motion.set_position(position)
    state = motion.motion.compute_kinematics(motion._state(q))
    spheres = state.robot_spheres.reshape(-1, 4).detach().cpu().numpy()
    rows = []
    for box in motion.boxes:
        clearance = sphere_clearance(spheres, box)
        sphere_index = int(np.argmin(clearance))
        rows.append({
            "name": box.name,
            "geom_id": box.geom_id,
            "clearance_m": float(clearance[sphere_index]),
            "sphere_index": sphere_index,
            "finger_sphere": sphere_index in motion.finger_indices,
            "handle_geometry": box.geom_id in motion.part.handle_geom_ids,
            "moving_geometry": box.geom_id in motion.part.moving_geom_ids,
        })
    rows.sort(key=lambda row: row["clearance_m"])
    metrics = motion.motion.check_constraints(motion._state(q))
    moving = [box for box in motion.boxes if box.geom_id in motion.part.moving_geom_ids]
    fixed = [box for box in motion.boxes if box.geom_id not in motion.part.moving_geom_ids]
    overlaps = []
    for moving_box in moving:
        for fixed_box in fixed:
            pair = frozenset((moving_box.geom_id, fixed_box.geom_id))
            if pair not in motion.allowed_pairs and boxes_overlap(moving_box, fixed_box):
                overlaps.append({
                    "moving_name": moving_box.name,
                    "moving_geom_id": moving_box.geom_id,
                    "fixed_name": fixed_box.name,
                    "fixed_geom_id": fixed_box.geom_id,
                })
    return {
        "q": q.tolist(),
        "curobo_constraints_feasible": bool(metrics.feasible.all().item()),
        "nearest_geometry": rows[:10],
        "moving_fixed_overlaps": overlaps,
    }


def _approach_failure(motion, path: np.ndarray, position: float, joint_step: float = 0.08):
    """Validate an approach exactly like cuTAMP and attribute its first rejected sample."""
    sample_index = 0
    for segment_index, (previous, current) in enumerate(zip(path[:-1], path[1:])):
        count = max(2, int(np.ceil(np.max(np.abs(current - previous)) / joint_step)))
        for fraction in np.linspace(0, 1, count + 1):
            q = previous * (1 - fraction) + current * fraction
            if motion.valid(q, position, True):
                sample_index += 1
                continue
            return {
                "sample_index": sample_index,
                "segment_index": segment_index,
                "segment_fraction": float(fraction),
                **_invalid_diagnostics(motion, q, position),
            }
    return None


def _dense_slide_failure(motion, knots, positions, settings):
    for index in range(1, len(knots)):
        previous, current = knots[index - 1], knots[index]
        count = max(2, int(np.ceil(np.max(np.abs(current - previous)) / settings.joint_step)))
        for fraction in np.linspace(0, 1, count + 1)[1:]:
            q = previous * (1 - fraction) + current * fraction
            position = float(positions[index - 1] * (1 - fraction) + positions[index] * fraction)
            if not motion.valid(q, position, True):
                return {
                    "segment_index": index - 1,
                    "segment_fraction": float(fraction),
                    "joint_position": position,
                    **_invalid_diagnostics(motion, q, position),
                }
    return None


def _probe_approach(motion, q_init: np.ndarray, pose: np.ndarray, position: float, profile: dict):
    try:
        path = np.asarray(motion.approach(q_init, pose, position, profile), dtype=float)
    except ArticulationError as exc:
        return {"planned": False, "strict_valid": False, "error": str(exc)}
    failure = _approach_failure(motion, path, position)
    return {
        "planned": True,
        "points": int(len(path)),
        "strict_valid": failure is None,
        "first_failure": failure,
        "final_q": path[-1].tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--candidate", default="probe45")
    parser.add_argument("--goal", default="open")
    parser.add_argument("--report-out", default="")
    parser.add_argument(
        "--rolls",
        default="",
        help="Comma-separated roll angles (deg) about the approach axis; sweeps how far the slide gets.",
    )
    parser.add_argument("--offsets-x", default="0", help="Handle-frame x offsets in metres.")
    parser.add_argument("--offsets-y", default="0", help="Handle-frame y offsets in metres.")
    parser.add_argument("--offsets-z", default="0", help="Handle-frame z offsets in metres.")
    args = parser.parse_args()

    cfg, problem = _load_problem(pathlib.Path(args.solve_json))
    binding = problem.articulation_options["bindings"][0]
    base_part = ArticulatedPart(**problem.articulations[binding["part_id"]])
    base_grasp = np.asarray(binding["grasps"][0], dtype=float)
    handle_pose = base_part.handle_pose(base_part.reference_position)
    standoff = float(np.linalg.norm((handle_pose @ base_grasp)[:3, 3] - handle_pose[:3, 3]))
    grasp = candidate_grasp(args.candidate, base_grasp, handle_pose, standoff)

    values = base_part.to_dict()
    values["grasps"] = [grasp.tolist()]
    part = ArticulatedPart(**values)
    q_init = np.asarray(problem.q_init, dtype=float)

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion
    motion = CuroboArticulationMotion(problem, part, cfg.robot)

    settings = PathSettings(**problem.articulation_options.get("path_settings", {}))
    target = float(np.mean(part.target_range(args.goal)))
    step = settings.slide_step
    count = max(2, int(np.ceil(abs(target - part.reference_position) / step)) + 1)
    positions = np.linspace(part.reference_position, target, count)

    if args.rolls.strip():
        # One MotionGen instance can serve the whole local pose grid because only the requested
        # tool pose changes.  The offsets are in the handle frame: callers can independently move
        # along the bar, toward/away from the drawer, and above/below it once the frame is inspected.
        rows = []
        grid = itertools.product(
            _csv_floats(args.rolls), _csv_floats(args.offsets_x),
            _csv_floats(args.offsets_y), _csv_floats(args.offsets_z),
        )
        for deg, ox, oy, oz in grid:
            rolled = offset_grasp(roll_grasp(grasp, deg), (ox, oy, oz))
            motion.set_position(part.reference_position)
            direct_q = motion.ik(part.handle_pose(part.reference_position) @ rolled, q_init)
            row = {
                "roll_deg": deg,
                "relative_offset_handle_xyz_m": [ox, oy, oz],
                "tool_center_xyz": np.round((handle_pose @ rolled)[:3, 3], 4).tolist(),
                "grasp_ik_from_q_init": direct_q is not None,
            }
            row["approach"] = _probe_approach(
                motion,
                q_init,
                part.handle_pose(part.reference_position) @ rolled,
                part.reference_position,
                part.grasp_profile(0),
            )
            q0 = (
                np.asarray(row["approach"]["final_q"], dtype=float)
                if row["approach"].get("strict_valid") else None
            )
            if q0 is not None:
                knots = [q0]
                fail = None
                jump = None
                for s in positions[1:]:
                    motion.set_position(float(s))
                    q = motion.ik(part.handle_pose(float(s)) @ rolled, knots[-1])
                    if q is None:
                        fail = float(s)
                        break
                    delta = float(np.max(np.abs(q - knots[-1])))
                    if delta > settings.max_joint_jump:
                        jump = {"position": float(s), "max_joint_delta_rad": delta}
                        break
                    knots.append(q)
                row["steps_solved"] = len(knots) - 1
                row["first_failing_position"] = fail
                row["first_joint_jump"] = jump
                stop = fail if fail is not None else (jump["position"] if jump else target)
                row["travelled_m"] = round(abs(stop), 4)
                dense_failure = None
                if fail is None and jump is None and len(knots) == count:
                    dense_failure = _dense_slide_failure(motion, knots, positions, settings)
                row["first_dense_failure"] = dense_failure
                row["reached_open_range"] = (
                    fail is None and jump is None and dense_failure is None and len(knots) == count
                )
                if row["reached_open_range"]:
                    row["grasp"] = rolled.tolist()
            rows.append(row)
            print(f"[roll {deg:+.0f} offset=({ox:+.3f},{oy:+.3f},{oz:+.3f})] {row}", flush=True)
        out = {
            "solve_json": args.solve_json,
            "candidate": args.candidate,
            "goal": args.goal,
            "target_position": target,
            "open_range": list(part.target_range(args.goal)),
            "num_slide_steps": int(count),
            "candidates": rows,
            "best": max((r for r in rows if r.get("steps_solved") is not None),
                        key=lambda r: (bool(r.get("reached_open_range")), r["steps_solved"]), default=None),
        }
        text = json.dumps(out, indent=2)
        print(text)
        if args.report_out:
            pathlib.Path(args.report_out).write_text(text, encoding="utf-8")
        return 0

    report = {
        "solve_json": args.solve_json,
        "candidate": args.candidate,
        "part_id": binding["part_id"],
        "goal": args.goal,
        "target_position": target,
        "num_slide_steps": int(count),
        "tool_center_xyz": np.round((handle_pose @ grasp)[:3, 3], 4).tolist(),
    }

    report["approach"] = _probe_approach(
        motion,
        q_init,
        handle_pose @ grasp,
        part.reference_position,
        part.grasp_profile(0),
    )

    # step 1: the grasp pose itself, single-seed from q_init (what refine_articulation's check does next)
    motion.set_position(part.reference_position)
    q_start = (
        np.asarray(report["approach"]["final_q"], dtype=float)
        if report["approach"].get("strict_valid") else None
    )
    report["ik_at_grasp_from_q_init"] = q_start is not None
    if q_start is None:
        report["verdict"] = "cannot even solve the grasp pose with one seed from q_init"
        print(json.dumps(report, indent=2))
        if args.report_out:
            pathlib.Path(args.report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    # step 2: walk the slide exactly like refine_articulation
    knots = [q_start]
    first_failure = None
    for s in positions[1:]:
        motion.set_position(float(s))
        pose = part.handle_pose(float(s)) @ grasp
        q = motion.ik(pose, knots[-1])
        if q is None:
            first_failure = float(s)
            break
        knots.append(q)
    report["slide_steps_solved"] = len(knots) - 1
    report["first_failing_position"] = first_failure
    report["first_failing_joint_target_m"] = None if first_failure is None else float(first_failure)

    if first_failure is not None:
        motion.set_position(first_failure)
        pose = part.handle_pose(first_failure) @ grasp
        # (a) other seeds for the same pose
        seeds = {
            "previous_knot": knots[-1],
            "q_init": q_init,
            "zero": np.zeros_like(q_init),
        }
        seed_rows = {}
        for name, seed in seeds.items():
            seed_rows[name] = motion.ik(pose, seed) is not None
        report["same_pose_other_seeds"] = seed_rows
        # (b) the multi-seed planner for the same pose
        try:
            path = motion._plan(knots[-1], pose, first_failure)
            report["multi_seed_plan_single"] = {"ok": True, "points": int(len(path))}
        except ArticulationError as exc:
            report["multi_seed_plan_single"] = {"ok": False, "error": str(exc)}
        report["verdict"] = (
            "single-seed limitation: the pose is reachable with other seeds/planner"
            if (any(seed_rows.values()) or report["multi_seed_plan_single"].get("ok"))
            else "all seeds and the multi-seed planner fail: the slide pose is genuinely unsolvable"
        )
    else:
        report["verdict"] = "the whole slide is solvable with a tilted grasp: refine_articulation should pass"

    text = json.dumps(report, indent=2)
    print(text)
    if args.report_out:
        pathlib.Path(args.report_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
