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


def rz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    out = np.eye(4)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return out


def roll_grasp(grasp: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate the tool about its own z (approach) axis only: z and the tool origin are unchanged."""
    return np.asarray(grasp, dtype=float) @ rz(np.deg2rad(degrees))


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

    settings = PathSettings()
    target = float(np.mean(part.target_range(args.goal)))
    step = settings.slide_step
    count = max(2, int(np.ceil(abs(target - part.reference_position) / step)) + 1)
    positions = np.linspace(part.reference_position, target, count)

    if args.rolls.strip():
        # Rolling the tool about its approach axis keeps the tool origin and the approach direction,
        # so the collision world is unchanged and one MotionGen instance can serve every roll.
        rows = []
        for text in args.rolls.split(","):
            if not text.strip():
                continue
            deg = float(text)
            rolled = roll_grasp(grasp, deg)
            motion.set_position(part.reference_position)
            q0 = motion.ik(part.handle_pose(part.reference_position) @ rolled, q_init)
            row = {
                "roll_deg": deg,
                "tool_center_xyz": np.round((handle_pose @ rolled)[:3, 3], 4).tolist(),
                "grasp_ik_from_q_init": q0 is not None,
            }
            if q0 is not None:
                knots = [q0]
                fail = None
                for s in positions[1:]:
                    motion.set_position(float(s))
                    q = motion.ik(part.handle_pose(float(s)) @ rolled, knots[-1])
                    if q is None:
                        fail = float(s)
                        break
                    knots.append(q)
                row["steps_solved"] = len(knots) - 1
                row["first_failing_position"] = fail
                row["travelled_m"] = round(abs((fail if fail is not None else target)), 4)
                row["reached_open_range"] = len(knots) - 1 >= count - 2
            rows.append(row)
            print(f"[roll {deg:+.0f}] {row}", flush=True)
        out = {
            "solve_json": args.solve_json,
            "candidate": args.candidate,
            "goal": args.goal,
            "target_position": target,
            "open_range": list(part.target_range(args.goal)),
            "num_slide_steps": int(count),
            "rolls": rows,
            "best": max((r for r in rows if r.get("steps_solved") is not None),
                        key=lambda r: r["steps_solved"], default=None),
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

    # step 1: the grasp pose itself, single-seed from q_init (what refine_articulation's check does next)
    motion.set_position(part.reference_position)
    q_start = motion.ik(handle_pose @ grasp, q_init)
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
