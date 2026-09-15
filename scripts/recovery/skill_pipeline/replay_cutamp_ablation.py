#!/usr/bin/env python3
"""Replay serialized real-cuTAMP problems with small collision ablations.

This is a diagnostic helper. It does not change rollout behavior or skill
selection; it reuses ``cutamp_debug/*.problem.json`` files and asks the same
real-cuTAMP backend whether a lightly modified planning world becomes feasible.
"""

from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any


CONSTRAINT_RE = re.compile(
    r"\[(?P<kind>[^\]]+)\]\s+"
    r"(?P<name>[^<]+?)\s*<=\s*"
    r"(?P<tol>[-+0-9.eE]+)\s+has\s+"
    r"(?P<satisfied>[0-9]+)/(?P<total>[0-9]+)\s+satisfying,\s+"
    r"(?P<remaining>[0-9]+)\s+remaining"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Replay serialized cuTAMP problems with ablations.")
    parser.add_argument("--run-dir", required=True, help="Run directory containing cutamp_debug.")
    parser.add_argument("--out-dir", default="", help="Output directory for replayed problems and reports.")
    parser.add_argument("--repo-root", default="", help="Repository root used as subprocess cwd.")
    parser.add_argument("--runner", default="", help="Python or wrapper used to run real_cutamp_backend.")
    parser.add_argument(
        "--problem-glob",
        default="cutamp_debug/*.problem.json",
        help="Glob relative to run-dir selecting serialized problem files.",
    )
    parser.add_argument(
        "--goal-match",
        action="append",
        default=[],
        help="Fnmatch pattern against formatted goal atoms. Can be repeated.",
    )
    parser.add_argument(
        "--variants",
        default="baseline,no_mug,no_table",
        help=(
            "Comma-separated variants: baseline,no_mug,no_table,no_pos_err,"
            "no_robot_world_collision,no_pos_err_no_robot_world_collision,"
            "caddy_real_floor_z,book_flat_box_topdown_short_side,thin_table_proxy,"
            "caddy_real_floor_z_book_flat_box,"
            "book_flat_box_topdown_short_side_no_robot_world_collision,"
            "book_flat_box_topdown_short_side_no_pos_err_no_robot_world_collision,"
            "caddy_real_floor_z_book_flat_box_no_robot_world_collision,"
            "caddy_real_floor_z_book_flat_box_no_pos_err_no_robot_world_collision,"
            "book_thin_along_x_flat_box,"
            "book_thin_along_x_flat_box_no_robot_world_collision,"
            "book_flat_box_topdown_short_side_no_robot_world_collision_no_opt,"
            "book_place_center_thin_x_flat_box_no_robot_world_collision,"
            "book_place_center_thin_x_flat_box_no_robot_world_collision_no_opt,"
            "book_place_center_thin_x_flat_box_table_cutout,"
            "caddy_exclude_table_collision,"
            "caddy_exclude_table_collision_flat_box,"
            "caddy_exclude_table_collision_flat_box_real_floor."
        ),
    )
    parser.add_argument(
        "--remove-object-match",
        action="append",
        default=["*mug*"],
        help="Fnmatch pattern for no_mug object removal. Can be repeated.",
    )
    parser.add_argument("--max-problems", type=int, default=0, help="Limit selected problems, 0 means all.")
    parser.add_argument("--timeout-sec", type=float, default=420.0)
    return parser.parse_args()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def problem_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    problem = payload.get("problem", payload)
    return problem if isinstance(problem, dict) else {}


def config_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config")
    return dict(config) if isinstance(config, dict) else {}


def atom_text(atom: dict[str, Any]) -> str:
    pred = str(atom.get("predicate", ""))
    args = ", ".join(str(arg) for arg in atom.get("args", []) or [])
    return f"{pred}({args})"


def goal_text(problem: dict[str, Any]) -> str:
    atoms = problem.get("required_final_atoms") or problem.get("goal_atoms") or []
    return "; ".join(atom_text(atom) for atom in atoms if isinstance(atom, dict))


def matches_goal(problem: dict[str, Any], patterns: list[str]) -> bool:
    if not patterns:
        return True
    text = goal_text(problem).lower()
    return any(fnmatch.fnmatchcase(text, str(pattern).lower()) for pattern in patterns)


def object_matches(name: str, patterns: list[str]) -> bool:
    low = str(name or "").lower()
    return any(fnmatch.fnmatchcase(low, str(pattern).lower()) for pattern in patterns)


def collision_part_prefix(name: Any) -> str:
    text = str(name or "")
    match = re.match(r"(?P<prefix>.+?)_(?:g|geom_)?[0-9]+$", text)
    return match.group("prefix") if match else text


def collision_part_summary(obj: dict[str, Any]) -> dict[str, Any]:
    geometry = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else {}
    metadata = geometry.get("metadata") if isinstance(geometry.get("metadata"), dict) else {}
    parts = [part for part in metadata.get("collision_parts", []) or [] if isinstance(part, dict)]
    prefixes = collections.Counter(collision_part_prefix(part.get("name")) for part in parts)
    bodies = collections.Counter(str(part.get("body_name") or "") for part in parts)
    return {
        "name": obj.get("name"),
        "role": obj.get("role"),
        "collision_part_count": len(parts),
        "part_name_prefix_counts": dict(prefixes.most_common(8)),
        "part_body_name_counts": dict(bodies.most_common(8)),
    }


def remove_objects(problem: dict[str, Any], patterns: list[str]) -> dict[str, Any]:
    removed: list[dict[str, Any]] = []
    for section in ("movables", "surfaces", "statics"):
        kept = []
        for obj in problem.get(section, []) or []:
            if isinstance(obj, dict) and object_matches(str(obj.get("name") or ""), patterns):
                removed.append({"section": section, **collision_part_summary(obj)})
            else:
                kept.append(obj)
        problem[section] = kept
    grasps = problem.get("grasps")
    if isinstance(grasps, dict):
        for name in list(grasps):
            if object_matches(name, patterns):
                grasps.pop(name, None)
    return {"removed_objects": removed, "patterns": list(patterns)}


def set_constraint_override(
    config: dict[str, Any],
    kind: str,
    name: str,
    *,
    tolerance: float | None = None,
    multiplier: float | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"constraint": f"{kind}.{name}"}
    if tolerance is not None:
        tol_overrides = config.setdefault("diagnostic_constraint_tol_overrides", {})
        tol_overrides.setdefault(kind, {})[name] = float(tolerance)
        metadata["tolerance"] = float(tolerance)
    if multiplier is not None:
        mult_overrides = config.setdefault("diagnostic_constraint_mult_overrides", {})
        mult_overrides.setdefault(kind, {})[name] = float(multiplier)
        metadata["multiplier"] = float(multiplier)
    return metadata


def disable_pos_err(config: dict[str, Any]) -> dict[str, Any]:
    return set_constraint_override(
        config,
        "KinematicConstraint",
        "pos_err",
        tolerance=1e6,
        multiplier=0.0,
    )


def disable_robot_world_collision(config: dict[str, Any]) -> dict[str, Any]:
    return set_constraint_override(
        config,
        "Collision",
        "robot_to_world",
        tolerance=1e6,
    )


def caddy_surfaces(problem: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for surface in problem.get("surfaces", []) or []:
        if not isinstance(surface, dict):
            continue
        name = str(surface.get("name") or "")
        geometry = surface.get("geometry") if isinstance(surface.get("geometry"), dict) else {}
        metadata = geometry.get("metadata") if isinstance(geometry.get("metadata"), dict) else {}
        if "desk_caddy" in name and str(geometry.get("kind") or "") == "virtual_inner_floor":
            selected.append(surface)
            continue
        if str(metadata.get("intent") or "") == "compartment_inner_floor":
            selected.append(surface)
    return selected


def set_caddy_planner_support_to_real_floor(problem: dict[str, Any]) -> dict[str, Any]:
    updated = []
    for surface in caddy_surfaces(problem):
        geometry = surface.get("geometry") if isinstance(surface.get("geometry"), dict) else {}
        metadata = geometry.setdefault("metadata", {})
        inner = metadata.get("inner_bounds") if isinstance(metadata.get("inner_bounds"), dict) else {}
        if not inner:
            continue
        support_z = float(inner.get("support_z", inner.get("z_min", surface.get("pos", [0.0, 0.0, 0.0])[2])))
        old = metadata.get("planner_support_z_m")
        metadata["planner_support_z_m"] = support_z
        updated.append({"surface": surface.get("name"), "previous_planner_support_z_m": old, "planner_support_z_m": support_z})
    return {"updated_surfaces": updated}


def set_book_flat_box_grasp_profile(config: dict[str, Any]) -> dict[str, Any]:
    old = config.get("grasp_sampler_profile")
    config["grasp_sampler_profile"] = "flat_box_topdown_short_side_v1"
    return {
        "previous_grasp_sampler_profile": old,
        "grasp_sampler_profile": config["grasp_sampler_profile"],
        "note": "real cuTAMP sampler profile only; serialized problem.grasps are debug candidates",
    }


def _quat_wxyz_to_matrix(quat: Any) -> list[list[float]]:
    values = [float(item) for item in list(quat or [1.0, 0.0, 0.0, 0.0])[:4]]
    while len(values) < 4:
        values.append(0.0)
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    w, x, y, z = [item / norm for item in values]
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _quat_multiply(left: list[float], right: list[float]) -> list[float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return [
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    ]


def _yaw_quat_wxyz(yaw: float) -> list[float]:
    return [math.cos(0.5 * yaw), 0.0, 0.0, math.sin(0.5 * yaw)]


def _rotate_xy(point: list[float], origin: list[float], yaw: float) -> list[float]:
    dx = float(point[0]) - float(origin[0])
    dy = float(point[1]) - float(origin[1])
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    out = list(point)
    out[0] = float(origin[0]) + cosine * dx - sine * dy
    out[1] = float(origin[1]) + sine * dx + cosine * dy
    return out


def _book_objects(problem: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for obj in problem.get("movables", []) or []:
        if not isinstance(obj, dict):
            continue
        if "book" in str(obj.get("name") or "").lower():
            selected.append(obj)
    return selected


def _collision_parts(obj: dict[str, Any]) -> list[dict[str, Any]]:
    geometry = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else {}
    metadata = geometry.get("metadata") if isinstance(geometry.get("metadata"), dict) else {}
    return [part for part in metadata.get("collision_parts", []) or [] if isinstance(part, dict)]


def align_book_thin_axis_to_world_x(problem: dict[str, Any]) -> dict[str, Any]:
    """Rotate the serialized book so its thin horizontal axis aligns with world +x."""
    updated = []
    for obj in _book_objects(problem):
        parts = _collision_parts(obj)
        box = next(
            (
                part
                for part in parts
                if str(part.get("shape") or "").lower() == "box" and len(part.get("size") or []) >= 3
            ),
            None,
        )
        if box is None:
            continue
        half = [float(item) for item in box["size"][:3]]
        rot = _quat_wxyz_to_matrix(box.get("quat") or obj.get("quat") or [1.0, 0.0, 0.0, 0.0])
        vertical = max(range(3), key=lambda idx: abs(rot[2][idx]))
        horizontal = [idx for idx in range(3) if idx != vertical]
        thin = min(horizontal, key=lambda idx: half[idx])
        thin_yaw = math.atan2(rot[1][thin], rot[0][thin])
        delta = -thin_yaw
        origin = [float(item) for item in (box.get("pos") or obj.get("pos") or [0.0, 0.0, 0.0])[:3]]
        while len(origin) < 3:
            origin.append(0.0)
        delta_quat = _yaw_quat_wxyz(delta)
        old_obj_quat = [float(item) for item in (obj.get("quat") or [1.0, 0.0, 0.0, 0.0])[:4]]
        obj["quat"] = _quat_multiply(delta_quat, old_obj_quat)
        if isinstance(obj.get("pos"), list) and len(obj["pos"]) >= 2:
            obj["pos"] = _rotate_xy([float(item) for item in obj["pos"]], origin, delta)
        for part in parts:
            if isinstance(part.get("pos"), list) and len(part["pos"]) >= 2:
                part["pos"] = _rotate_xy([float(item) for item in part["pos"]], origin, delta)
            if isinstance(part.get("quat"), list) and len(part["quat"]) >= 4:
                part["quat"] = _quat_multiply(delta_quat, [float(item) for item in part["quat"][:4]])
        updated.append(
            {
                "object": obj.get("name"),
                "thin_axis": thin,
                "previous_thin_yaw_deg": math.degrees(thin_yaw),
                "delta_yaw_deg": math.degrees(delta),
            }
        )
    return {
        "aligned_books": updated,
        "note": "yaw-only diagnostic; book stays on the table, thin edge aimed along world x",
    }


def _compose_xyz(parent_pos: list[float], parent_quat: list[float], local_pos: list[float]) -> list[float]:
    rot = _quat_wxyz_to_matrix(parent_quat)
    lx, ly, lz = (list(local_pos) + [0.0, 0.0, 0.0])[:3]
    return [
        float(parent_pos[0]) + rot[0][0] * lx + rot[0][1] * ly + rot[0][2] * lz,
        float(parent_pos[1]) + rot[1][0] * lx + rot[1][1] * ly + rot[1][2] * lz,
        float(parent_pos[2]) + rot[2][0] * lx + rot[2][1] * ly + rot[2][2] * lz,
    ]


def _translate_xy(point: Any, dx: float, dy: float) -> list[float]:
    out = [float(item) for item in list(point or [0.0, 0.0, 0.0])]
    while len(out) < 3:
        out.append(0.0)
    out[0] += float(dx)
    out[1] += float(dy)
    return out


def _goal_on_surface_name(problem: dict[str, Any]) -> str:
    atoms = problem.get("required_final_atoms") or problem.get("goal_atoms") or []
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        if str(atom.get("predicate") or "").lower() != "on":
            continue
        args = atom.get("args") or []
        if len(args) >= 2:
            return str(args[1])
    return ""


def _surface_center_xy(surface: dict[str, Any]) -> list[float] | None:
    geometry = surface.get("geometry") if isinstance(surface.get("geometry"), dict) else {}
    metadata = geometry.get("metadata") if isinstance(geometry.get("metadata"), dict) else {}
    inner = metadata.get("inner_bounds") if isinstance(metadata.get("inner_bounds"), dict) else {}
    if inner:
        return [
            0.5 * (float(inner["x_min"]) + float(inner["x_max"])),
            0.5 * (float(inner["y_min"]) + float(inner["y_max"])),
        ]
    pos = surface.get("pos") or []
    if len(pos) >= 2:
        return [float(pos[0]), float(pos[1])]
    return None


def _book_cuboid_center_xy(obj: dict[str, Any]) -> list[float]:
    parts = _collision_parts(obj)
    box = next(
        (
            part
            for part in parts
            if str(part.get("shape") or "").lower() == "box" and len(part.get("size") or []) >= 3
        ),
        None,
    )
    parent_pos = [float(item) for item in (obj.get("pos") or [0.0, 0.0, 0.0])[:3]]
    while len(parent_pos) < 3:
        parent_pos.append(0.0)
    parent_quat = [float(item) for item in (obj.get("quat") or [1.0, 0.0, 0.0, 0.0])[:4]]
    if box is None:
        return parent_pos[:2]
    local_pos = [float(item) for item in (box.get("local_pos") or [0.0, 0.0, 0.0])[:3]]
    return _compose_xyz(parent_pos, parent_quat, local_pos)[:2]


def move_book_to_goal_surface_center(problem: dict[str, Any]) -> dict[str, Any]:
    """Translate the already-yawed book so its cuboid XY sits on the goal inner floor."""
    target_name = _goal_on_surface_name(problem)
    surfaces = {str(surface.get("name") or ""): surface for surface in caddy_surfaces(problem)}
    surface = surfaces.get(target_name) or (next(iter(surfaces.values()), None) if surfaces else None)
    if not isinstance(surface, dict):
        return {"moved_books": [], "note": "no caddy inner-floor surface found"}
    center = _surface_center_xy(surface)
    if center is None:
        return {"moved_books": [], "note": "goal surface has no XY center"}
    updated = []
    for obj in _book_objects(problem):
        current = _book_cuboid_center_xy(obj)
        dx = float(center[0]) - float(current[0])
        dy = float(center[1]) - float(current[1])
        if isinstance(obj.get("pos"), list):
            obj["pos"] = _translate_xy(obj.get("pos"), dx, dy)
        for part in _collision_parts(obj):
            if isinstance(part.get("pos"), list):
                part["pos"] = _translate_xy(part.get("pos"), dx, dy)
        updated.append(
            {
                "object": obj.get("name"),
                "surface": surface.get("name"),
                "previous_cuboid_xy": current,
                "target_xy": center,
                "delta_xy_m": [dx, dy],
            }
        )
    return {
        "moved_books": updated,
        "note": "diagnostic only: book XY moved onto the goal inner-floor center; z unchanged",
    }


def caddy_footprint_xy(problem: dict[str, Any], *, margin_m: float = 0.02) -> list[float] | None:
    for obj in problem.get("statics", []) or []:
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name") or "")
        if "desk_caddy" not in name or "inner" in name:
            continue
        pos = [float(item) for item in (obj.get("pos") or [0.0, 0.0, 0.0])[:2]]
        he = [float(item) for item in (obj.get("half_extents") or [0.0, 0.0])[:2]]
        if len(pos) < 2 or len(he) < 2:
            continue
        return [
            pos[0] - he[0] - margin_m,
            pos[0] + he[0] + margin_m,
            pos[1] - he[1] - margin_m,
            pos[1] + he[1] + margin_m,
        ]
    return None


def set_table_cutout_from_caddy(problem: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    cutout = caddy_footprint_xy(problem)
    old = config.get("table_cutout_xy")
    config["table_cutout_xy"] = cutout
    config["table_as_collision_obstacle"] = True
    return {
        "previous_table_cutout_xy": old,
        "table_cutout_xy": cutout,
        "table_as_collision_obstacle": True,
        "note": "diagnostic only: keep table collision but punch a hole under the caddy AABB",
    }


def set_exclude_table_collision(problem: dict[str, Any]) -> dict[str, Any]:
    updated = []
    for surface in caddy_surfaces(problem):
        geometry = surface.get("geometry") if isinstance(surface.get("geometry"), dict) else {}
        metadata = geometry.setdefault("metadata", {})
        old = metadata.get("exclude_table_collision")
        metadata["exclude_table_collision"] = True
        updated.append({"surface": surface.get("name"), "previous_exclude_table_collision": old})
    return {
        "updated_surfaces": updated,
        "note": "diagnostic/skill equivalent: exclude table collision like on(object, table)",
    }


def set_num_opt_steps(config: dict[str, Any], steps: int) -> dict[str, Any]:
    old = config.get("num_opt_steps")
    config["num_opt_steps"] = int(steps)
    return {"previous_num_opt_steps": old, "num_opt_steps": int(steps)}


def set_thin_table_proxy(config: dict[str, Any]) -> dict[str, Any]:
    old_height = config.get("table_height_override")
    old_collision = config.get("table_as_collision_obstacle")
    config["table_height_override"] = 0.001
    config["table_as_collision_obstacle"] = True
    return {
        "previous_table_height_override": old_height,
        "table_height_override": config["table_height_override"],
        "previous_table_as_collision_obstacle": old_collision,
        "table_as_collision_obstacle": config["table_as_collision_obstacle"],
        "note": "diagnostic thin slab; not a true caddy-footprint cutout",
    }


def make_variant(payload: dict[str, Any], variant: str, remove_patterns: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    copied = json.loads(json.dumps(payload))
    problem = problem_from_payload(copied)
    config = config_from_payload(copied)
    copied["problem"] = problem
    copied["config"] = config
    config["runner_python"] = ""
    metadata: dict[str, Any] = {"variant": variant}
    if variant == "baseline":
        metadata["description"] = "unchanged serialized problem"
    elif variant == "no_mug":
        metadata["description"] = "remove static/surface/movable objects matching mug patterns"
        metadata.update(remove_objects(problem, remove_patterns))
    elif variant == "no_table":
        metadata["description"] = "keep table as semantic surface but disable table collision obstacle"
        metadata["previous_table_as_collision_obstacle"] = config.get("table_as_collision_obstacle")
        config["table_as_collision_obstacle"] = False
    elif variant == "no_pos_err":
        metadata["description"] = "diagnostic only: make KinematicConstraint.pos_err non-binding"
        metadata["constraint_overrides"] = [disable_pos_err(config)]
    elif variant == "no_robot_world_collision":
        metadata["description"] = "diagnostic only: make Collision.robot_to_world non-binding"
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "no_pos_err_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: make KinematicConstraint.pos_err and "
            "Collision.robot_to_world non-binding"
        )
        metadata["constraint_overrides"] = [
            disable_pos_err(config),
            disable_robot_world_collision(config),
        ]
    elif variant == "caddy_real_floor_z":
        metadata["description"] = "diagnostic only: put planner support z back on the real compartment floor"
        metadata.update(set_caddy_planner_support_to_real_floor(problem))
    elif variant == "book_flat_box_topdown_short_side":
        metadata["description"] = "diagnostic only: use flat-box short-side top-down grasp sampling for the book"
        metadata.update(set_book_flat_box_grasp_profile(config))
    elif variant == "thin_table_proxy":
        metadata["description"] = "diagnostic only: keep table collision but shrink it to a 1 mm slab"
        metadata.update(set_thin_table_proxy(config))
    elif variant == "caddy_real_floor_z_book_flat_box":
        metadata["description"] = (
            "diagnostic only: combine real compartment-floor planner z with "
            "flat-box short-side top-down book grasp sampling"
        )
        metadata.update(set_caddy_planner_support_to_real_floor(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
    elif variant == "book_flat_box_topdown_short_side_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: use flat-box short-side top-down book grasp sampling "
            "and make Collision.robot_to_world non-binding"
        )
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "book_flat_box_topdown_short_side_no_pos_err_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: use flat-box short-side top-down book grasp sampling "
            "and make KinematicConstraint.pos_err plus Collision.robot_to_world non-binding"
        )
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata["constraint_overrides"] = [
            disable_pos_err(config),
            disable_robot_world_collision(config),
        ]
    elif variant == "caddy_real_floor_z_book_flat_box_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: combine real compartment-floor planner z, flat-box "
            "short-side top-down book grasp sampling, and non-binding robot-world collision"
        )
        metadata.update(set_caddy_planner_support_to_real_floor(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "caddy_real_floor_z_book_flat_box_no_pos_err_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: combine real compartment-floor planner z and flat-box "
            "short-side top-down book grasp sampling while making pos_err and "
            "robot-world collision non-binding"
        )
        metadata.update(set_caddy_planner_support_to_real_floor(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata["constraint_overrides"] = [
            disable_pos_err(config),
            disable_robot_world_collision(config),
        ]
    elif variant == "book_thin_along_x_flat_box":
        metadata["description"] = (
            "diagnostic only: yaw the book so its thin edge aligns with world x, "
            "and use flat-box short-side top-down grasp sampling"
        )
        metadata.update(align_book_thin_axis_to_world_x(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
    elif variant == "book_thin_along_x_flat_box_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: yaw the book so its thin edge aligns with world x, "
            "use flat-box short-side top-down grasp sampling, and make "
            "Collision.robot_to_world non-binding"
        )
        metadata.update(align_book_thin_axis_to_world_x(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "book_flat_box_topdown_short_side_no_robot_world_collision_no_opt":
        metadata["description"] = (
            "diagnostic only: keep high-drop planner z and flat-box grasp, disable "
            "robot-world collision, and use num_opt_steps=1 (cuTAMP rejects 0)"
        )
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata.update(set_num_opt_steps(config, 1))
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "book_place_center_thin_x_flat_box_no_robot_world_collision":
        metadata["description"] = (
            "diagnostic only: yaw thin-edge along world x, move the book onto the "
            "goal inner-floor center, keep high-drop planner z, use flat-box grasp, "
            "and make Collision.robot_to_world non-binding"
        )
        metadata.update(align_book_thin_axis_to_world_x(problem))
        metadata.update(move_book_to_goal_surface_center(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "book_place_center_thin_x_flat_box_no_robot_world_collision_no_opt":
        metadata["description"] = (
            "diagnostic only: same as place-center thin-x with collision off, but "
            "skip continuous optimization (cuTAMP requires at least 1 step, so this uses num_opt_steps=1)"
        )
        metadata.update(align_book_thin_axis_to_world_x(problem))
        metadata.update(move_book_to_goal_surface_center(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata.update(set_num_opt_steps(config, 1))
        metadata["constraint_overrides"] = [disable_robot_world_collision(config)]
    elif variant == "book_place_center_thin_x_flat_box_table_cutout":
        metadata["description"] = (
            "diagnostic only: yaw thin-edge along world x, move the book onto the "
            "goal inner-floor center, keep high-drop planner z, use flat-box grasp, "
            "and keep table collision except for a hole under the caddy footprint"
        )
        metadata.update(align_book_thin_axis_to_world_x(problem))
        metadata.update(move_book_to_goal_surface_center(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata.update(set_table_cutout_from_caddy(problem, config))
    elif variant == "caddy_exclude_table_collision":
        metadata["description"] = (
            "skill-equivalent diagnostic: keep the book at its real start pose and "
            "exclude table collision while placing on the caddy inner floor"
        )
        metadata.update(set_exclude_table_collision(problem))
    elif variant == "caddy_exclude_table_collision_flat_box":
        metadata["description"] = (
            "skill-equivalent diagnostic: exclude table collision like on(table), "
            "keep the book at its real start pose, and use flat-box grasp sampling"
        )
        metadata.update(set_exclude_table_collision(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
    elif variant == "caddy_exclude_table_collision_flat_box_real_floor":
        metadata["description"] = (
            "skill-equivalent diagnostic: exclude table collision, use flat-box "
            "grasp sampling, keep the book at its real start pose, and put planner "
            "support z back on the real compartment floor"
        )
        metadata.update(set_exclude_table_collision(problem))
        metadata.update(set_book_flat_box_grasp_profile(config))
        metadata.update(set_caddy_planner_support_to_real_floor(problem))
    else:
        raise ValueError(f"unknown variant: {variant}")
    return copied, metadata


def parse_stderr(text: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = CONSTRAINT_RE.search(line)
        if not match:
            continue
        item = match.groupdict()
        item.update(
            {
                "line": line_no,
                "tol": float(item["tol"]),
                "satisfied": int(item["satisfied"]),
                "total": int(item["total"]),
                "remaining": int(item["remaining"]),
                "key": f"{item['kind']}.{item['name'].strip()}",
            }
        )
        events.append(item)
    zero = []
    seen = set()
    peak_by_key: dict[str, int] = {}
    first_by_key: dict[str, int] = {}
    for event in events:
        key = event["key"]
        satisfied = int(event["satisfied"])
        peak_by_key[key] = max(peak_by_key.get(key, 0), satisfied)
        first_by_key.setdefault(key, satisfied)
        if event["satisfied"] == 0 and key not in seen:
            zero.append(key)
            seen.add(key)
    return {
        "events": events,
        "zero_satisfying_constraints": zero,
        "final_blockers": events[-3:],
        "peak_satisfying_by_constraint": peak_by_key,
        "first_satisfying_by_constraint": first_by_key,
    }


def run_variant(
    runner: str,
    repo_root: pathlib.Path,
    solve_json: pathlib.Path,
    result_json: pathlib.Path,
    timeout_sec: float,
) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    executable = runner or sys.executable
    cmd = [
        executable,
        "-m",
        "experiments.robot.libero.tiptop_repro.real_cutamp_backend",
        "--solve-json",
        str(solve_json),
        "--result-json",
        str(result_json),
    ]
    env = os.environ.copy()
    env["REAL_CUTAMP_BACKEND_CHILD"] = "1"
    env.setdefault("CUTAMP_CONTACT_MODE_TARGET", "1")
    env.setdefault("CUTAMP_ALLOW_START_COLLISION_ESCAPE", "1")
    env.setdefault("CUTAMP_START_ESCAPE_Z", "0.08")
    env["PYTHONPATH"] = f"{repo_root}{os.pathsep}" + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return proc, ""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return None, f"timeout:{exc.timeout}s\nSTDOUT\n{stdout[-2000:]}\nSTDERR\n{stderr[-2000:]}"


def result_summary(path: pathlib.Path, stderr_text: str, returncode: int | None, timeout_error: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if path.exists():
        try:
            result = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            result = {"load_error": str(exc)}
    constraints = parse_stderr(stderr_text)
    diag = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    return {
        "returncode": returncode,
        "timeout_error": timeout_error,
        "available": result.get("available"),
        "feasible": result.get("feasible"),
        "num_satisfying": result.get("num_satisfying"),
        "failure_reason": result.get("failure_reason"),
        "elapsed_sec": result.get("elapsed_sec"),
        "grasp_sampler_profile": diag.get("grasp_sampler_profile"),
        "optimized_plan_present": diag.get("optimized_plan_present"),
        "optimized_operator_count": diag.get("optimized_operator_count"),
        "zero_satisfying_constraints": constraints["zero_satisfying_constraints"],
        "first_satisfying_by_constraint": constraints.get("first_satisfying_by_constraint", {}),
        "peak_satisfying_by_constraint": constraints.get("peak_satisfying_by_constraint", {}),
        "final_blockers": [event.get("key") for event in constraints["final_blockers"]],
    }


def write_markdown(path: pathlib.Path, report: dict[str, Any]) -> None:
    lines = ["# cuTAMP Ablation Replay", ""]
    lines.append(f"- run_dir: `{report['run_dir']}`")
    lines.append(f"- selected_problems: {report['selected_problem_count']}")
    lines.append("")
    lines.append("## Summary")
    for variant, item in report["summary_by_variant"].items():
        lines.append(
            f"- `{variant}`: feasible={item['feasible']}/{item['count']} "
            f"zero={item['zero_satisfying_constraint_frequency']}"
        )
    lines.append("")
    lines.append("## Problems")
    for problem in report["problems"]:
        lines.append(f"### {problem['problem_name']}")
        lines.append(f"- goal: `{problem['goal']}`")
        for variant in problem["variants"]:
            result = variant["result"]
            lines.append(
                f"- `{variant['variant']}`: feasible={result.get('feasible')} "
                f"sat={result.get('num_satisfying')} reason=`{result.get('failure_reason')}` "
                f"zero={result.get('zero_satisfying_constraints')} "
                f"first={result.get('first_satisfying_by_constraint')} "
                f"peak={result.get('peak_satisfying_by_constraint')} "
                f"final={result.get('final_blockers')}"
            )
            removed = variant.get("metadata", {}).get("removed_objects") or []
            if removed:
                lines.append(f"  removed: `{removed}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    out_dir = pathlib.Path(args.out_dir).expanduser().resolve() if args.out_dir else run_dir / "cutamp_ablation_replay"
    repo_root = pathlib.Path(args.repo_root).expanduser().resolve() if args.repo_root else pathlib.Path.cwd()
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    problems = []
    for path in sorted(run_dir.glob(args.problem_glob)):
        payload = load_json(path)
        problem = problem_from_payload(payload)
        if matches_goal(problem, args.goal_match):
            problems.append((path, payload, goal_text(problem)))
    if args.max_problems > 0:
        problems = problems[: args.max_problems]

    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    started = time.time()
    for problem_idx, (path, payload, goal) in enumerate(problems):
        problem_name = path.name.replace(".problem.json", "")
        problem_record = {"problem_name": problem_name, "source_problem": str(path), "goal": goal, "variants": []}
        for variant in variants:
            variant_payload, metadata = make_variant(payload, variant, args.remove_object_match)
            prefix = out_dir / f"{problem_idx:03d}_{problem_name}_{variant}"
            solve_json = prefix.with_suffix(".problem.json")
            result_json = prefix.with_suffix(".result.json")
            stdout_path = prefix.with_suffix(".stdout.txt")
            stderr_path = prefix.with_suffix(".stderr.txt")
            dump_json(solve_json, variant_payload)
            proc, timeout_error = run_variant(args.runner, repo_root, solve_json, result_json, args.timeout_sec)
            stdout = proc.stdout if proc is not None else ""
            stderr = proc.stderr if proc is not None else timeout_error
            stdout_path.write_text(stdout or "", encoding="utf-8")
            stderr_path.write_text(stderr or "", encoding="utf-8")
            variant_record = {
                "variant": variant,
                "metadata": metadata,
                "paths": {
                    "problem": str(solve_json),
                    "result": str(result_json),
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                },
                "result": result_summary(
                    result_json,
                    stderr or "",
                    None if proc is None else proc.returncode,
                    timeout_error,
                ),
            }
            problem_record["variants"].append(variant_record)
        records.append(problem_record)

    summary_by_variant: dict[str, dict[str, Any]] = {}
    for variant in variants:
        selected = [v for p in records for v in p["variants"] if v["variant"] == variant]
        constraint_counts = collections.Counter()
        for item in selected:
            for key in item["result"].get("zero_satisfying_constraints") or []:
                constraint_counts[key] += 1
        summary_by_variant[variant] = {
            "count": len(selected),
            "feasible": sum(1 for item in selected if item["result"].get("feasible")),
            "num_satisfying_sum": sum(int(item["result"].get("num_satisfying") or 0) for item in selected),
            "zero_satisfying_constraint_frequency": dict(constraint_counts),
        }

    report = {
        "run_dir": str(run_dir),
        "out_dir": str(out_dir),
        "repo_root": str(repo_root),
        "runner": args.runner or sys.executable,
        "elapsed_sec": round(time.time() - started, 3),
        "selected_problem_count": len(records),
        "summary_by_variant": summary_by_variant,
        "problems": records,
    }
    dump_json(out_dir / "ablation_report.json", report)
    write_markdown(out_dir / "ablation_report.md", report)
    print(json.dumps(summary_by_variant, indent=2, ensure_ascii=False))
    print(f"wrote_json={out_dir / 'ablation_report.json'}")
    print(f"wrote_markdown={out_dir / 'ablation_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
