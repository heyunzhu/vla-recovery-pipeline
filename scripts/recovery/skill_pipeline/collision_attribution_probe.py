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
    parser.add_argument("--solve-json", required=True, help="Serialized cuTAMP problem to replay.")
    parser.add_argument("--out-json", default="", help="Where to write the machine-readable report.")
    parser.add_argument("--q", default="", help="Comma-separated joint vector; default the problem's q_init.")
    parser.add_argument("--top", type=int, default=15, help="How many obstacles to print.")
    parser.add_argument("--verify", action="store_true", help="Cross-check against cuRobo's aggregate collision function.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    solve_json = pathlib.Path(args.solve_json).expanduser().resolve()
    cfg, problem = _load_problem(solve_json)

    from curobo.types.base import TensorDeviceType
    from cutamp.robots import load_robot_container
    from cutamp.utils.common import get_world_cfg
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend

    q = [float(v) for v in args.q.split(",") if v.strip()] if args.q.strip() else list(problem.q_init or [])
    if not q:
        print("no configuration to probe: pass --q or use a problem with q_init")
        return 2

    backend = RealCuTAMPBackend(cfg)
    env, name_map, goal_notes, geometry_debug = backend._build_env(problem)
    world_cfg = get_world_cfg(env, include_movables=False)
    boxes = obb_boxes_from_world_config(world_cfg)

    tensor_args = TensorDeviceType()
    robot_container = load_robot_container(cfg.robot, tensor_args)
    spheres = robot_spheres_at(robot_container, tensor_args, q)

    ranked = rank_obstacles(spheres, boxes)
    worst = float(ranked[0]["depth_m"]) if ranked else 0.0

    report: Dict[str, Any] = {
        "solve_json": str(solve_json),
        "robot": str(cfg.robot),
        "q": [float(v) for v in q],
        "num_spheres": int(spheres.shape[0]),
        "num_obstacles": len(boxes),
        "worst_penetration_m": worst,
        "goal_notes": list(goal_notes or []),
        "collision_world_objects": [str(getattr(obj, "name", "")) for obj in getattr(env, "statics", [])],
        "ranked": ranked,
    }
    if args.verify:
        from cutamp.utils.collision import get_world_collision_cost

        total_fn = get_world_collision_cost(world_cfg, tensor_args, 0.0)
        value = total_fn(tensor_args.to_device(spheres.reshape(1, 1, -1, 4).astype(np.float32)))
        report["cutamp_aggregate_collision"] = float(np.asarray(value.detach().cpu().numpy()).max())

    print(f"problem            : {solve_json.name}")
    print(f"robot              : {cfg.robot}   spheres={spheres.shape[0]}   obstacles={len(boxes)}")
    print(f"configuration      : {[round(v, 4) for v in q]}")
    print(f"worst penetration  : {worst:+.5f} m" + ("" if worst > 0 else "   (robot is collision-free here)"))
    if "cutamp_aggregate_collision" in report:
        print(f"cuTAMP aggregate   : {report['cutamp_aggregate_collision']:+.5f}")
    print()
    print(f"{'obstacle':<52}{'penetration(m)':>15}{'sphere':>8}")
    for row in ranked[: max(0, int(args.top))]:
        print(f"{row['name'][:50]:<52}{row['depth_m']:>15.5f}{row['sphere_index']:>8}")

    if args.out_json:
        out = pathlib.Path(args.out_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0 if worst <= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
