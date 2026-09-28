"""Reproduce, and then dissect, the exact cuRobo call that returned MotionGenStatus.IK_FAIL for a
recorded articulation recovery attempt.

It replays the real code path (cutamp_articulation.solve -> articulation_curobo.approach -> _plan)
on a saved `*.problem.json`, and then asks the same question with the world emptied, with the
standoff swept, and with the goal pose raised, so that "no IK solution" can be attributed to
collision versus kinematics.

Run with the py310 overlay (needs cuRobo + cuTAMP):
    $REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \
        scripts/recovery/skill_pipeline/probe_articulation_ik.py --solve-json <problem.json>
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

from experiments.robot.libero.tiptop_repro.articulation import ArticulatedPart, ArticulationError  # noqa: E402
from experiments.robot.libero.tiptop_repro.collision_report import _load_problem  # noqa: E402


def attempt(motion, q, pose, position, label):
    """One plan_single, reported the way the backend reports it."""
    try:
        path = motion._plan(q, pose, position)
        return {"label": label, "ok": True, "points": int(len(path)),
                "end_xyz": np.round(path[-1][:3], 4).tolist() if path.shape[1] >= 3 else None}
    except ArticulationError as exc:
        return {"label": label, "ok": False, "error": str(exc)}


def ik_only(motion, q, pose, label):
    try:
        solution = motion.ik(pose, q)
    except Exception as exc:  # noqa: BLE001 - the probe reports, it does not raise
        return {"label": label, "ok": False, "error": f"{type(exc).__name__}:{exc}"}
    return {"label": label, "ok": solution is not None,
            "solution": None if solution is None else np.round(solution, 4).tolist()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--standoffs", default="0.02,0.05,0.08,0.12,0.18")
    parser.add_argument("--z-offsets", default="-0.03,0.0,0.03,0.06,0.10")
    args = parser.parse_args()

    solve_json = pathlib.Path(args.solve_json)
    cfg, problem = _load_problem(solve_json)
    binding = problem.articulation_options["bindings"][0]
    part_id = binding["part_id"]
    part = ArticulatedPart(**problem.articulations[part_id])
    grasp = np.asarray(binding["grasps"][0], dtype=float)
    q = np.asarray(problem.q_init, dtype=float)

    report = {
        "solve_json": str(solve_json),
        "goal_atoms": [(a.predicate, list(a.args)) for a in problem.goal_atoms],
        "part_id": part_id,
        "joint_name": part.joint_name,
        "joint_type": part.joint_type,
        "reference_position": part.reference_position,
        "joint_range": list(part.joint_range),
        "handle_reference_xyz": np.round(part.handle_pose(part.reference_position)[:3, 3], 4).tolist(),
        "q_init": np.round(q, 4).tolist(),
    }

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion

    motion = CuroboArticulationMotion(problem, part, cfg.robot)
    target = part.handle_pose(part.reference_position) @ grasp
    pre = target.copy()
    pre[:3, 3] -= target[:3, 2] * 0.05
    report["target_xyz"] = np.round(target[:3, 3], 4).tolist()
    report["approach_dir"] = np.round(target[:3, 2], 4).tolist()
    report["pre_xyz"] = np.round(pre[:3, 3], 4).tolist()
    report["table_z"] = getattr(problem, "table_z", None)
    report["q_init_fk_xyz"] = np.round(motion.fk(q)[:3, 3], 4).tolist()
    report["num_world_boxes"] = len(motion.boxes)

    # 1) the exact failing request
    report["baseline"] = attempt(motion, q, pre, part.reference_position, "plan_single(pre) with world")
    report["baseline_ik"] = ik_only(motion, q, pre, "solve_ik(pre) with world")

    # 2) same request with the collision world emptied: collision vs kinematics
    from curobo.geom.types import WorldConfig
    motion.motion.update_world(WorldConfig(cuboid=[]))
    report["empty_world"] = attempt(motion, q, pre, part.reference_position, "plan_single(pre) empty world")
    report["empty_world_ik"] = ik_only(motion, q, pre, "solve_ik(pre) empty world")

    # 3) restore the world, then sweep the standoff and the goal height
    motion.set_position(part.reference_position)
    motion.motion.update_world(motion._world())
    sweep = []
    for standoff in [float(v) for v in args.standoffs.split(",") if v.strip()]:
        pose = target.copy()
        pose[:3, 3] -= target[:3, 2] * standoff
        sweep.append(attempt(motion, q, pose, part.reference_position, f"standoff={standoff:.3f}"))
    report["standoff_sweep"] = sweep
    raised = []
    for dz in [float(v) for v in args.z_offsets.split(",") if v.strip()]:
        pose = pre.copy()
        pose[2, 3] += dz
        raised.append(attempt(motion, q, pose, part.reference_position, f"pre_dz={dz:+.3f}"))
    report["raise_sweep"] = raised

    # 4) orientation sweep: the configured grasp is horizontal/front-facing, which forces the tool
    #    centre to sit at the handle's own height. Rebuild the same grasp with other approach axes
    #    (the tool centre is always handle_center - approach * standoff, mirroring the grasp matrix),
    #    to separate "too low" from "this wrist orientation at this height".
    handle_center = part.handle_pose(part.reference_position)[:3, 3]
    standoff = float(np.linalg.norm(target[:3, 3] - handle_center))
    report["grasp_standoff_m"] = round(standoff, 4)
    orientations = {
        "front_horizontal(-y)": np.array([0.0, -1.0, 0.0]),
        "top_down(-z)": np.array([0.0, 0.0, -1.0]),
        "tilt45(-y,-z)": np.array([0.0, -1.0, -1.0]) / np.sqrt(2.0),
        "tilt30_low(-y,-z)": np.array([0.0, -0.866, -0.5]),
    }
    orientation_rows = []
    for name, approach in orientations.items():
        approach = approach / np.linalg.norm(approach)
        z_axis = approach
        hint = np.array([1.0, 0.0, 0.0]) if abs(approach[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
        x_axis = np.cross(hint, z_axis)
        if np.linalg.norm(x_axis) < 1e-6:
            x_axis = np.cross(np.array([0.0, 1.0, 0.0]), z_axis)
        x_axis = x_axis / np.linalg.norm(x_axis)
        y_axis = np.cross(z_axis, x_axis)
        pose = np.eye(4)
        pose[:3, 0], pose[:3, 1], pose[:3, 2] = x_axis, y_axis, z_axis
        pose[:3, 3] = handle_center - approach * standoff
        row = attempt(motion, q, pose, part.reference_position, f"orient={name}")
        row["tool_center_xyz"] = np.round(pose[:3, 3], 4).tolist()
        orientation_rows.append(row)
    report["orientation_sweep"] = orientation_rows

    text = json.dumps(report, indent=2)
    print(text)
    if args.out_json:
        pathlib.Path(args.out_json).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
