#!/usr/bin/env python3
"""Name the geometry the robot collides with, instead of only counting particles.

The pipeline reports ``[Collision] robot_to_world <= 0.001 has 0/64 satisfying``
and says nothing about *what* the robot hits. Every diagnosis of that line so far
has had to guess or to delete whole objects from the world and re-solve, which
cannot separate two objects that both overlap.

This probe rebuilds the exact collision world the cuTAMP backend uses for one
serialized problem and reports, per obstacle, the deepest overlap with the robot's
collision spheres at a given configuration. It reuses the backend's own world
assembly (``RealCuTAMPBackend._build_env`` plus ``cutamp.utils.common.get_world_cfg``)
and cuRobo's own OBB conversion, so the names and geometry are the ones the solver
actually sees; ``--verify`` cross-checks the total against cuRobo's aggregate
collision function.

It must run under the py3.10 wrapper because it imports cuTAMP and cuRobo:

    ROOT=<work> OVERLAY_ROOT=<repo> \\
      <repo>/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \\
      scripts/recovery/skill_pipeline/collision_attribution_probe.py \\
      --solve-json <run>/cutamp_debug/solve_*.problem.json

The sphere/OBB math lives in module-level functions so it can be unit tested
without cuRobo; see ``tests/test_collision_attribution.py``.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def quat_wxyz_to_matrix(quat: Sequence[float]) -> np.ndarray:
    """Rotation matrix for a (w, x, y, z) quaternion."""
    raw = np.asarray(list(quat)[:4], dtype=float)
    if raw.size < 4:
        return np.eye(3)
    norm = float(np.linalg.norm(raw))
    if norm < 1e-12:
        return np.eye(3)
    w, x, y, z = raw / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def sphere_obb_penetration(
    sphere_xyz: Sequence[float],
    sphere_radius: float,
    box_center: Sequence[float],
    box_quat_wxyz: Sequence[float],
    box_half_extents: Sequence[float],
) -> float:
    """Positive when the sphere penetrates the box; negative is the clearance.

    The box is the exact oriented box; this matches the OBB world cuRobo builds
    for the collision checker.
    """
    center = np.asarray(list(box_center)[:3], dtype=float)
    half = np.abs(np.asarray(list(box_half_extents)[:3], dtype=float))
    point = np.asarray(list(sphere_xyz)[:3], dtype=float)
    rotation = quat_wxyz_to_matrix(box_quat_wxyz)
    local = rotation.T @ (point - center)
    # Distance from the box surface; negative inside.
    outside = np.maximum(np.abs(local) - half, 0.0)
    if float(np.linalg.norm(outside)) > 1e-12:
        signed_distance = float(np.linalg.norm(outside))
    else:
        signed_distance = float(np.max(np.abs(local) - half))
    return float(sphere_radius) - signed_distance


def worst_penetration(
    spheres: np.ndarray,
    box_center: Sequence[float],
    box_quat_wxyz: Sequence[float],
    box_half_extents: Sequence[float],
) -> Tuple[float, int]:
    """Deepest penetration over a set of spheres, with the index of that sphere."""
    values = np.asarray(spheres, dtype=float).reshape(-1, 4)
    if values.size == 0:
        return 0.0, -1
    best, best_idx = -np.inf, -1
    for index, row in enumerate(values):
        depth = sphere_obb_penetration(row[:3], float(row[3]), box_center, box_quat_wxyz, box_half_extents)
        if depth > best:
            best, best_idx = depth, index
    return float(best), int(best_idx)


def rank_obstacles(
    spheres: np.ndarray,
    boxes: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Per-obstacle deepest penetration, worst first."""
    rows: List[Dict[str, Any]] = []
    for box in boxes:
        depth, index = worst_penetration(
            spheres,
            box["center"],
            box["quat"],
            box["half_extents"],
        )
        rows.append(
            {
                "name": str(box.get("name") or ""),
                "depth_m": depth,
                "sphere_index": index,
                "sphere": None if index < 0 else [float(v) for v in np.asarray(spheres)[index]],
                "center": [float(v) for v in box["center"]],
                "half_extents": [float(v) for v in box["half_extents"]],
            }
        )
    rows.sort(key=lambda row: row["depth_m"], reverse=True)
    return rows


def obb_boxes_from_world_config(world_cfg: Any) -> List[Dict[str, Any]]:
    """Every obstacle of a cuRobo world as an oriented box.

    ``get_collision_checker`` converts the world with ``create_obb_world``, so this
    is the geometry the collision checker actually queries.
    """
    from curobo.geom.types import WorldConfig

    obb_world = WorldConfig.create_obb_world(world_cfg)
    boxes: List[Dict[str, Any]] = []
    for cuboid in list(getattr(obb_world, "cuboid", []) or []):
        pose = [float(v) for v in list(getattr(cuboid, "pose", []))[:7]]
        dims = [float(v) for v in list(getattr(cuboid, "dims", []))[:3]]
        if len(pose) < 7 or len(dims) < 3:
            continue
        boxes.append(
            {
                "name": str(getattr(cuboid, "name", "") or ""),
                "center": pose[:3],
                "quat": pose[3:7],
                "half_extents": [0.5 * dims[0], 0.5 * dims[1], 0.5 * dims[2]],
            }
        )
    return boxes


def robot_spheres_at(robot_container: Any, tensor_args: Any, q: Sequence[float]) -> np.ndarray:
    """Collision spheres of the robot at one configuration, as an (n, 4) array."""
    q_tensor = tensor_args.to_device(np.asarray(list(q), dtype=np.float32))
    state = robot_container.kin_model.get_state(q_tensor)
    spheres = state.get_link_spheres()
    return np.asarray(spheres.detach().cpu().numpy(), dtype=float).reshape(-1, 4)


WAYPOINT_RE = re.compile(r"^q(\d+)$")


def extract_waypoints(result_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Joint configurations of a serialized optimized plan, in skeleton order.

    ``_serialize_optimized_cutamp_solution`` writes the best particle's bindings,
    so an optimized plan carries the skeleton's ``q0``, ``q1``, ... waypoints even
    though the dense ``traj*`` paths only exist inside the motion solver.
    """
    plan = result_payload.get("optimized_plan") or {}
    bindings = plan.get("bindings") or {}
    shapes = plan.get("binding_shapes") or {}
    found: List[Tuple[int, Dict[str, Any]]] = []
    for name, value in bindings.items():
        match = WAYPOINT_RE.match(str(name))
        if not match:
            continue
        shape = list(shapes.get(name) or [])
        array = np.asarray(value, dtype=float).reshape(-1)
        if shape and int(np.prod(shape)) != array.size:
            continue
        found.append(
            (
                int(match.group(1)),
                {"name": str(name), "q": [float(v) for v in array], "shape": shape},
            )
        )
    found.sort(key=lambda item: item[0])
    return [item[1] for item in found]


def label_segments(operators: Sequence[Dict[str, Any]], waypoints: Sequence[Dict[str, Any]]) -> List[str]:
    """Name each waypoint by the motion that reaches it.

    ``labels[i]`` names the segment from waypoint ``i`` to ``i + 1``; a motion
    operator consuming two configurations claims its segment. Point operators
    (``Pick``, ``Place``) do not traverse a segment, so they only annotate the
    single waypoint they bind, as ``Place@q2``.
    """
    names = [str(wp["name"]) for wp in waypoints]
    labels = ["" for _ in waypoints]
    points: Dict[int, str] = {}
    for operator in operators or []:
        operator_name = str(operator.get("name") or "")
        symbols = [str(arg.get("symbol")) for arg in (operator.get("arguments") or [])]
        positions = [names.index(symbol) for symbol in symbols if symbol in names]
        if len(positions) >= 2:
            for start, end in zip(positions, positions[1:]):
                if end == start + 1 and not labels[start]:
                    labels[start] = operator_name
        elif len(positions) == 1:
            points.setdefault(positions[0], operator_name)
    for index, label in enumerate(labels):
        if label:
            continue
        point = points.get(index)
        labels[index] = f"{point}@{names[index]}" if point else f"segment{index}"
    return labels


def densify(
    waypoints: Sequence[Dict[str, Any]],
    labels: Sequence[str],
    steps_per_segment: int,
) -> List[Dict[str, Any]]:
    """Joint-space interpolation between consecutive waypoints.

    The serialized plan has no dense path, so this samples the straight line the
    skeleton implies. It cannot prove a segment is free; it does say which obstacle
    the motion passes through.
    """
    if not waypoints:
        return []
    steps = max(0, int(steps_per_segment))
    samples: List[Dict[str, Any]] = []
    for index, waypoint in enumerate(waypoints):
        samples.append(
            {"label": labels[index], "waypoint": waypoint["name"], "t": 0.0, "q": list(waypoint["q"])}
        )
        if index + 1 >= len(waypoints):
            continue
        start = np.asarray(waypoint["q"], dtype=float)
        end = np.asarray(waypoints[index + 1]["q"], dtype=float)
        for step in range(1, steps + 1):
            fraction = step / float(steps + 1)
            samples.append(
                {
                    "label": labels[index],
                    "waypoint": f"{waypoint['name']}->{waypoints[index + 1]['name']}",
                    "t": float(fraction),
                    "q": [float(v) for v in (start + fraction * (end - start))],
                }
            )
    return samples


def _load_problem(solve_json: pathlib.Path):
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
        RealCuTAMPBackendConfig,
        _problem_from_dict,
    )

    payload = json.loads(solve_json.read_text(encoding="utf-8"))
    cfg = RealCuTAMPBackendConfig(**payload.get("config", {}))
    problem = _problem_from_dict(payload["problem"])
    return cfg, problem


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
