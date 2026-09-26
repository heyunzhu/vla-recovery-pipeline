#!/usr/bin/env python3
"""Name the geometry the robot collides with, instead of only counting particles.

``[Collision] robot_to_world <= 0.001 has 0/64 satisfying`` says nothing about what
the robot hits. This is the CLI over ``tiptop_repro.collision_report``: it probes one
configuration, or sweeps a serialized plan's ``q0/q1/...`` waypoints with
joint-space interpolation between them, and prints the deepest obstacle per sample.

It must run under the py3.10 wrapper because it imports cuTAMP and cuRobo:

    ROOT=<work> OVERLAY_ROOT=<repo> \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      scripts/recovery/skill_pipeline/collision_attribution_probe.py \\
      --solve-json <run>/cutamp_debug/solve_*.problem.json \\
      --result-json <run>/cutamp_debug/solve_*.result.json --interpolate 6 --verify

An interpolated hit says "this region is occupied"; a hit on a waypoint itself is
exact, because that configuration is one the optimizer selected.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.collision_report import (  # noqa: E402
    _load_problem,
    densify,
    extract_waypoints,
    label_segments,
    obb_boxes_from_world_config,
    quat_wxyz_to_matrix,
    rank_obstacles,
    robot_spheres_at,
    sphere_obb_penetration,
    worst_penetration,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solve-json", required=True, help="Serialized cuTAMP problem: supplies the collision world.")
    parser.add_argument(
        "--result-json",
        default="",
        help="Serialized result of the same problem: supplies the optimized plan's q0/q1/... waypoints.",
    )
    parser.add_argument("--out-json", default="", help="Where to write the machine-readable report.")
    parser.add_argument("--q", default="", help="Comma-separated joint vector; overrides --result-json.")
    parser.add_argument(
        "--interpolate",
        type=int,
        default=4,
        help="Samples inserted between consecutive waypoints, in joint space. 0 probes waypoints only.",
    )
    parser.add_argument("--top", type=int, default=10, help="How many obstacles to print per sample.")
    parser.add_argument("--verify", action="store_true", help="Cross-check against cuRobo's aggregate collision function.")
    return parser.parse_args(argv)


def _sample_plan(args: argparse.Namespace, problem: Any) -> Tuple[List[Dict[str, Any]], str]:
    """The configurations to probe, and where they came from."""
    if args.q.strip():
        q = [float(v) for v in args.q.split(",") if v.strip()]
        return [{"label": "explicit", "waypoint": "q", "t": 0.0, "q": q}], "explicit --q"
    if args.result_json:
        path = pathlib.Path(args.result_json).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        waypoints = extract_waypoints(payload)
        if not waypoints:
            return [], f"{path.name}: no q0/q1/... waypoints in optimized_plan.bindings"
        operators = ((payload.get("optimized_plan") or {}).get("operators")) or []
        labels = label_segments(operators, waypoints)
        note = f"{path.name}: {len(waypoints)} waypoints ({', '.join(w['name'] for w in waypoints)})"
        return densify(waypoints, labels, args.interpolate), note
    q = list(problem.q_init or [])
    return ([{"label": "q_init", "waypoint": "q0", "t": 0.0, "q": q}] if q else []), "problem q_init"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    cfg, problem = _load_problem(solve_json)

    from curobo.types.base import TensorDeviceType
    from cutamp.robots import load_robot_container
    from cutamp.utils.common import get_world_cfg
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend

    samples, source = _sample_plan(args, problem)
    if not samples:
        print(f"nothing to probe: {source}")
        return 2

    backend = RealCuTAMPBackend(cfg)
    env, name_map, goal_notes, geometry_debug = backend._build_env(problem)
    world_cfg = get_world_cfg(env, include_movables=False)
    boxes = obb_boxes_from_world_config(world_cfg)

    tensor_args = TensorDeviceType()
    robot_container = load_robot_container(cfg.robot, tensor_args)

    aggregate_fn = None
    if args.verify:
        from cutamp.utils.collision import get_world_collision_cost

        aggregate_fn = get_world_collision_cost(world_cfg, tensor_args, 0.0)

    rows: List[Dict[str, Any]] = []
    for sample in samples:
        spheres = robot_spheres_at(robot_container, tensor_args, sample["q"])
        ranked = rank_obstacles(spheres, boxes)
        worst = ranked[0] if ranked else {"name": "", "depth_m": 0.0, "sphere_index": -1}
        row = {
            **sample,
            "worst_obstacle": str(worst["name"]),
            "worst_depth_m": float(worst["depth_m"]),
            "worst_sphere_index": int(worst["sphere_index"]),
            "ranked": ranked,
        }
        if aggregate_fn is not None:
            value = aggregate_fn(tensor_args.to_device(spheres.reshape(1, 1, -1, 4).astype(np.float32)))
            row["cutamp_aggregate_collision"] = float(np.asarray(value.detach().cpu().numpy()).max())
        rows.append(row)

    worst_row = max(rows, key=lambda row: row["worst_depth_m"])
    by_label: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        entry = by_label.setdefault(row["label"], {"samples": 0, "worst_obstacle": "", "worst_depth_m": -np.inf})
        entry["samples"] += 1
        if row["worst_depth_m"] > entry["worst_depth_m"]:
            entry["worst_depth_m"] = float(row["worst_depth_m"])
            entry["worst_obstacle"] = row["worst_obstacle"]

    report: Dict[str, Any] = {
        "solve_json": str(solve_json),
        "result_json": str(args.result_json or ""),
        "source": source,
        "robot": str(cfg.robot),
        "num_spheres": int(robot_spheres_at(robot_container, tensor_args, samples[0]["q"]).shape[0]),
        "num_obstacles": len(boxes),
        "worst_penetration_m": float(worst_row["worst_depth_m"]),
        "worst_sample": worst_row["waypoint"],
        "worst_obstacle": worst_row["worst_obstacle"],
        "by_segment": by_label,
        "samples": rows,
    }

    print(f"problem         : {solve_json.name}")
    print(f"samples from    : {source}")
    print(f"robot           : {cfg.robot}   obstacles={len(boxes)}")
    print(f"worst           : {worst_row['worst_depth_m']:+.5f} m on {worst_row['worst_obstacle'] or '<none>'}"
          f"   at {worst_row['waypoint']} (t={worst_row['t']:.2f})")
    print()
    print(f"{'segment':<16}{'waypoint':<22}{'t':>5}{'penetration':>13}  obstacle")
    for row in rows:
        print(
            f"{row['label'][:14]:<16}{row['waypoint'][:20]:<22}{row['t']:>5.2f}"
            f"{row['worst_depth_m']:>13.5f}  {row['worst_obstacle'][:44]}"
        )
    print()
    print("worst per segment:")
    for label, entry in by_label.items():
        print(f"   {label:<16} samples={entry['samples']:<3} worst={entry['worst_depth_m']:+.5f} m  {entry['worst_obstacle'][:44]}")
    if args.verify:
        print()
        print("verify (sample, probe worst, cuRobo aggregate):")
        for row in rows[: min(6, len(rows))]:
            print(f"   {row['waypoint']:<22}{row['worst_depth_m']:>12.5f}{row.get('cutamp_aggregate_collision', float('nan')):>14.5f}")

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0 if worst_row["worst_depth_m"] <= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
