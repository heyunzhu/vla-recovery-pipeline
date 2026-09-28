"""Pre-flight: choose a tilted grasp for a low drawer that the *full* articulation solve accepts.

For each candidate grasp it rebuilds the recorded problem with that grasp and runs the real
`cutamp_articulation.solve` (GraspHandle approach -> refine -> retreat), so the decision costs no
episode. The first candidate that produces a plan is written out as a ready-to-use articulation
config, leaving every existing config untouched.

Candidate families:
  rz{deg}     - rotate the configured grasp about the handle frame's z axis: G = Rz(theta) @ G0.
                Keeps the original in-plane roll (gripper x stays world +x) and lifts the tool
                centre to handle_center - approach * standoff.
  probe{deg}  - the frame the orientation sweep already proved plan_single accepts, expressed as a
                grasp matrix G = inv(handle_pose(0)) @ [R | handle_center - approach * standoff].

Usage (py310 overlay):
    .../cutamp_runner_py310_overlay.sh scripts/recovery/skill_pipeline/choose_tilted_grasp.py \
        --solve-json <problem.json> --config-out <config.json> --report-out <report.json>
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
from experiments.robot.libero.tiptop_repro.cutamp_articulation import solve  # noqa: E402


def rz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    out = np.eye(4)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return out


def with_grasp(part: ArticulatedPart, grasp: np.ndarray) -> ArticulatedPart:
    values = part.to_dict()
    values["grasps"] = [np.asarray(grasp, dtype=float).tolist()]
    return ArticulatedPart(**values)


def probe_style_grasp(handle_pose: np.ndarray, approach: np.ndarray, standoff: float,
                      dx: float = 0.0, bar_axis_world: np.ndarray | None = None) -> np.ndarray:
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
    if bar_axis_world is not None and dx:
        # Grasp the horizontal bar `dx` metres off its centre, along the bar.
        pose[:3, 3] = pose[:3, 3] + bar_axis_world * dx
    return np.linalg.inv(handle_pose) @ pose


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-json", required=True)
    parser.add_argument("--config-out", required=True)
    parser.add_argument("--report-out", default="")
    parser.add_argument("--degrees", default="45,30")
    parser.add_argument(
        "--tilts",
        default="40,50,45",
        help="Tilt grid (deg below horizontal) in the roll family the travel sweep showed can reach"
             " the full slide; evaluated before the rz/probe families.",
    )
    parser.add_argument("--dxs", default="0.02,0,-0.02", help="Offsets along the horizontal handle bar.")
    parser.add_argument("--grid-only", action="store_true", help="Skip the rz/probe families.")
    parser.add_argument(
        "--ignore-drawer-overlap",
        action="store_true",
        help="Set ignore_drawer_environment_overlap in the probed problem and in the written config:"
             " the drawer-vs-scene box overlap is this extension's own bookkeeping, and LIBERO tasks"
             " are happy to let the simulator resolve those contacts.",
    )
    parser.add_argument("--budget-sec", type=float, default=40.0)
    parser.add_argument("--goal", default="open")
    args = parser.parse_args()

    cfg, problem = _load_problem(pathlib.Path(args.solve_json))
    if args.ignore_drawer_overlap:
        problem.articulation_options["ignore_drawer_environment_overlap"] = True
        print("ignore_drawer_environment_overlap = True (drawer-vs-scene box overlap not enforced)",
              flush=True)
    binding = dict(problem.articulation_options["bindings"][0])
    part0 = ArticulatedPart(**problem.articulations[binding["part_id"]])
    base_grasp = np.asarray(binding["grasps"][0], dtype=float)
    handle_pose = part0.handle_pose(part0.reference_position)
    standoff = float(np.linalg.norm((handle_pose @ base_grasp)[:3, 3] - handle_pose[:3, 3]))
    q_init = np.asarray(problem.q_init, dtype=float)

    candidates: list[tuple[str, np.ndarray]] = []
    bar_axis_world = handle_pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
    for tilt in [float(v) for v in args.tilts.split(",") if v.strip()]:
        for dx in [float(v) for v in args.dxs.split(",") if v.strip()]:
            theta = np.deg2rad(tilt)
            approach = np.array([0.0, -np.cos(theta), -np.sin(theta)])
            candidates.append((f"tilt{tilt:g}_dx{dx:+.3f}",
                               probe_style_grasp(handle_pose, approach, standoff, dx, bar_axis_world)))
    if not args.grid_only:
        for text in args.degrees.split(","):
            if not text.strip():
                continue
            deg = float(text)
            theta = np.deg2rad(deg)
            candidates.append((f"rz{deg:g}", rz(theta) @ base_grasp))
            candidates.append((f"probe{deg:g}",
                               probe_style_grasp(handle_pose, np.array([0.0, -np.cos(theta), -np.sin(theta)]),
                                                 standoff)))
    candidates.append(("horizontal_control", base_grasp))

    from experiments.robot.libero.tiptop_repro.articulation_curobo import CuroboArticulationMotion

    rows, chosen = [], None
    for name, grasp in candidates:
        part = with_grasp(part0, grasp)
        target = handle_pose @ grasp
        row = {
            "candidate": name,
            "tool_center_xyz": np.round(target[:3, 3], 4).tolist(),
            "approach": np.round(target[:3, 2], 4).tolist(),
            "grasp": np.round(grasp, 6).tolist(),
        }
        try:
            motion = CuroboArticulationMotion(problem, part, cfg.robot)
            plan = solve(part, args.goal, q_init, motion, PathSettings(), args.budget_sec)
            row["ok"] = bool(plan.get("actions"))
            row["phases"] = [a.get("phase") for a in plan.get("actions", [])]
            row["operators"] = [o.get("name") for o in plan.get("operators", [])]
        except ArticulationError as exc:
            row["ok"] = False
            row["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - report, do not hide
            row["ok"] = False
            row["error"] = f"{type(exc).__name__}:{exc}"
        rows.append(row)
        print(f"[{name}] ok={row['ok']} tool_center={row['tool_center_xyz']} {row.get('error', '')}", flush=True)
        if row["ok"] and chosen is None and name != "horizontal_control":
            chosen = row

    report = {
        "solve_json": args.solve_json,
        "part_id": binding["part_id"],
        "standoff_m": round(standoff, 4),
        "handle_xyz": np.round(handle_pose[:3, 3], 4).tolist(),
        "candidates": rows,
        "chosen": chosen["candidate"] if chosen else None,
    }
    if args.report_out:
        pathlib.Path(args.report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    if chosen is None:
        print("NO tilted candidate solved; config not written", flush=True)
        return 3

    binding["grasps"] = [chosen["grasp"]]
    binding["grasp_source"] = f"preflight:{chosen['candidate']}"
    out = {"enabled": True, "bindings": [binding]}
    if args.ignore_drawer_overlap:
        out["ignore_drawer_environment_overlap"] = True
    pathlib.Path(args.config_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"WROTE {args.config_out} with {chosen['candidate']} (tool centre {chosen['tool_center_xyz']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
