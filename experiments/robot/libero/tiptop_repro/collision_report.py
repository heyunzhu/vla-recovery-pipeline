"""Collision attribution helpers shared by the diagnostic tools.

The pipeline reports ``[Collision] robot_to_world <= 0.001 has 0/64 satisfying``
and never says which geometry is involved, so every diagnosis of that line had to
guess or delete whole objects and re-solve. These helpers rebuild the exact
collision world that cuTAMP builds for one serialized problem and report, per
obstacle, the deepest overlap with the robot's collision spheres.

The world is assembled by the backend itself (``RealCuTAMPBackend._build_env`` plus
``cutamp.utils.common.get_world_cfg``) and converted by cuRobo's own
``WorldConfig.create_obb_world``, so the names and geometry are the ones the solver
queries.

Only numpy is needed at import time; cuTAMP and cuRobo are imported inside the
functions that need them, which keeps the sphere/OBB math unit testable without a
GPU. See ``tests/test_collision_attribution.py``.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
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


def worst_obstacle(
    spheres: np.ndarray,
    boxes: Iterable[Dict[str, Any]],
) -> Tuple[float, str, int]:
    """Deepest overlap over all obstacles: ``(depth, obstacle_name, sphere_index)``.

    Cheaper than :func:`rank_obstacles` when only the maximum is needed, which is
    what a retreat search calls on every gradient evaluation.
    """
    best, name, sphere_index = -np.inf, "", -1
    for box in boxes:
        depth, index = worst_penetration(spheres, box["center"], box["quat"], box["half_extents"])
        if depth > best:
            best, name, sphere_index = depth, str(box.get("name") or ""), index
    if sphere_index < 0:
        return 0.0, "", -1
    return float(best), name, int(sphere_index)


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


