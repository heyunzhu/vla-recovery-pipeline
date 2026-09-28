"""Sweep the ROLL-CORRECT grasp family for the low drawer: is any of it reachable at all?

The correct family keeps the fingers perpendicular to the horizontal handle bar. Its orientation is
`rz(theta) @ G0` (a rotation about the bar's own axis, i.e. about the handle frame's z), and the tool
centre is put at `handle + d * bar_axis - approach * standoff` so both the standoff and the
along-the-bar offset can be swept.

For each candidate this asks only the two questions the planner needs first - can the grasp pose be
solved from q_init, and does the free-motion approach plan - and then runs the full
`cutamp_articulation.solve` on the first few that pass, so a whole family is screened in minutes.

Usage (py310 overlay):
    .../cutamp_runner_py310_overlay.sh scripts/recovery/skill_pipeline/probe_roll_family.py \
        --solve-json <problem.json> --tilts 10,20,...,70 --standoffs 0.07,0.0965,0.12,0.15
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
from experiments.robot.libero.tiptop_repro.cutamp_articulation import solve  # noqa: E402


def rz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    out = np.eye(4)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return out


def correct_roll_rotation(base_grasp: np.ndarray, tilt_deg: float) -> np.ndarray:
    """Orientation only: the configured grasp rotated about the bar's axis (handle frame z)."""
    return (rz(np.deg2rad(tilt_deg)) @ np.asarray(base_grasp, dtype=float))[:3, :3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--goal", default="open")
    parser.add_argument("--tilts", default="10,20,30,40,50,60,70")
    parser.add_argument("--standoffs", default="0.07,0.0965,0.12,0.15")
    parser.add_argument("--dxs", default="0")
    parser.add_argument("--full-solve-top", type=int, default=4)
    parser.add_argument("--budget-sec", type=float, default=40.0)
    parser.add_argument("--report-out", default="")
    args = parser.parse_args()

    cfg, problem = _load_problem(pathlib.Path(args.solve_json))
    binding = problem.articulation_options["bindings"][0]
    base = ArticulatedPart(**problem.articulations[binding["part_id"]])
    base_grasp = np.asarray(binding["grasps"][0], dtype=float)
    handle_pose = base.handle_pose(base.reference_position)
    handle_center = handle_pose[:3, 3]
    bar_axis = handle_pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
    q_init = np.asarray(problem.q_init, dtype=float)

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion

    motion = CuroboArticulationMotion(problem, base, cfg.robot)

    def grasp_for(tilt: float, standoff: float, dx: float) -> np.ndarray:
        rot = correct_roll_rotation(base_grasp, tilt)
        approach = rot[:, 2]
        pose = np.eye(4)
        pose[:3, :3] = rot
        pose[:3, 3] = handle_center + bar_axis * dx - approach * standoff
        return np.linalg.inv(handle_pose) @ pose

    rows, feasible = [], []
    for tilt, standoff, dx in itertools.product(
        [float(v) for v in args.tilts.split(",") if v.strip()],
        [float(v) for v in args.standoffs.split(",") if v.strip()],
        [float(v) for v in args.dxs.split(",") if v.strip()],
    ):
        grasp = grasp_for(tilt, standoff, dx)
        target = handle_pose @ grasp
        row = {
            "tilt_deg": tilt, "standoff": standoff, "dx": dx,
            "grasp": np.round(grasp, 6).tolist(),
            "tool_center_xyz": np.round(target[:3, 3], 4).tolist(),
            "approach_dir": np.round(target[:3, 2], 4).tolist(),
        }
        try:
            row["grasp_ik"] = motion.ik(target, q_init) is not None
        except Exception as exc:  # noqa: BLE001
            row["grasp_ik"] = False
            row["ik_error"] = f"{type(exc).__name__}:{exc}"
        try:
            path = motion.approach(q_init, target, base.reference_position)
            row["approach_ok"] = True
            row["approach_points"] = int(len(path))
        except ArticulationError as exc:
            row["approach_ok"] = False
            row["approach_error"] = str(exc)
        rows.append(row)
        flag = "OK " if row.get("approach_ok") else "   "
        print(f"[{flag}tilt {tilt:>4.0f} s {standoff:.4f} dx {dx:+.3f}] ik={row['grasp_ik']} "
              f"approach={row.get('approach_ok')} {row.get('approach_error', '')}", flush=True)
        if row.get("approach_ok"):
            feasible.append(row)

    solved = []
    for row in feasible[: max(0, args.full_solve_top)]:
        values = base.to_dict()
        values["grasps"] = [row["grasp"]]
        part = ArticulatedPart(**values)
        try:
            plan = solve(part, args.goal, q_init, motion, PathSettings(), args.budget_sec)
            row["full_solve"] = bool(plan.get("actions"))
            row["phases"] = [a.get("phase") for a in plan.get("actions", [])]
            solved.append(row)
            print(f"[full-solve OK] tilt {row['tilt_deg']} s {row['standoff']} dx {row['dx']} "
                  f"phases={row['phases']}", flush=True)
        except ArticulationError as exc:
            row["full_solve"] = False
            row["full_solve_error"] = str(exc)
            print(f"[full-solve NO] tilt {row['tilt_deg']} s {row['standoff']} dx {row['dx']} {exc}",
                  flush=True)

    out = {
        "solve_json": args.solve_json,
        "part_id": binding["part_id"],
        "n_candidates": len(rows),
        "n_approach_ok": len(feasible),
        "n_full_solve_ok": len(solved),
        "rows": rows,
        "candidates": [{"tilt_deg": r["tilt_deg"], "standoff": r["standoff"], "dx": r["dx"],
                        "grasp": r["grasp"]} for r in solved],
    }
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    if args.report_out:
        pathlib.Path(args.report_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
