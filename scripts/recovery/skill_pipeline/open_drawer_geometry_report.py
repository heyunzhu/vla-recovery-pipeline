#!/usr/bin/env python3
"""Explain what the open-drawer skill reads out of a recorded planner problem.

This is the step-0 diagnostic for "put an object into a drawer": it takes the
``*.problem.json`` that a recovery run already wrote, rebuilds a minimal scene
from the geometry recorded inside it, and reports every box the skill's
decision rests on -- the drawer region site in the site's own frame, the same
site with its quaternion applied, and the axis-aligned box of the drawer link's
own collision geometry.

It then evaluates the *real* skill against that scene and, for comparison,
reproduces what the pre-fix code produced from the same numbers (site half
extents read as an axis-aligned box plus a fixed 9 cm gripper reach). When the
two disagree, the recorded run was reading the site in the wrong frame.

Only numpy is required. The recorded ``problem.json`` does not carry the drawer
joint position, so the joint progress is an explicit input.

    python scripts/recovery/skill_pipeline/open_drawer_geometry_report.py \
        --problem place_in_open_drawer_20260926/gap_top_s1.problem.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.tiptop_repro.place_in_open_drawer import (  # noqa: E402
    COLLISION_CLEARANCE_M,
    GEOMETRY_MISMATCH_TOLERANCE_M,
    OPEN_PROGRESS_MIN,
    _drawer_collision_boxes,
    _placed_object_half_extents,
    _release_height,
    _site_local_half_extents,
    evaluate_open_drawer_place,
    is_drawer_region_name,
    open_drawer_place_diagnostics,
    region_from_surface_name,
    site_axis_aligned_half_extents,
)

# The constant the skill used before the geometry fix. Reproducing the old
# release point is the whole point of the comparison, so it is kept here rather
# than in the skill.
LEGACY_HAND_BELOW_OBJECT_M = 0.09
# Progress used for the synthetic joint. The recorded runs only created the
# virtual surface when the drawer was already past OPEN_PROGRESS_MIN.
DEFAULT_DRAWER_PROGRESS = 1.0


class _Object:
    """The shape ``place_in_open_drawer`` needs from a scene object."""

    def __init__(self, name: str, pos: Sequence[float], geometry: Dict[str, Any]) -> None:
        self.name = str(name)
        self.pos = np.asarray(pos if pos is not None else [0.0, 0.0, 0.0], dtype=float).reshape(-1)
        self.geometry = geometry


class _Joint:
    def __init__(self, name: str, qpos: float, joint_range: Sequence[float]) -> None:
        self.name = str(name)
        self.qpos = float(qpos)
        self.joint_range = (float(joint_range[0]), float(joint_range[1]))


class _Scene:
    """A duck-typed stand-in for ``scene_reader.SceneState``."""

    def __init__(self, objects: Dict[str, _Object], joints: Dict[str, _Joint], structure: Dict[str, Any]) -> None:
        self.objects = objects
        self.joints = joints
        self.articulation_structure = structure
        self.robot_joint_debug: Dict[str, Any] = {}


def _load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _problem_of(document: Dict[str, Any]) -> Dict[str, Any]:
    return document.get("problem") or document


def _iter_geometry_entries(problem: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for key in ("surfaces", "movables", "statics"):
        for entry in problem.get(key) or []:
            if isinstance(entry, dict):
                yield entry


def _collect_sites(problem: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Every drawer region site recorded in the problem, keyed by site name."""
    sites: Dict[str, Dict[str, Any]] = {}
    for entry in _iter_geometry_entries(problem):
        metadata = (entry.get("geometry") or {}).get("metadata") or {}
        for site in metadata.get("sites") or []:
            if not isinstance(site, dict):
                continue
            name = str(site.get("name") or "")
            if name and (is_drawer_region_name(name) or name.lower().endswith("_region")):
                sites.setdefault(name, site)
    return sites


def _collect_collision_boxes(problem: Dict[str, Any], body_name: str) -> List[Dict[str, Any]]:
    """Collision geometry of the body that owns the region site."""
    boxes: List[Dict[str, Any]] = []
    for entry in _iter_geometry_entries(problem):
        metadata = (entry.get("geometry") or {}).get("metadata") or {}
        for part in metadata.get("collision_parts") or []:
            if not isinstance(part, dict):
                continue
            if str(part.get("shape") or "") != "box":
                continue
            if body_name and str(part.get("body_name") or entry.get("name") or "") != body_name:
                continue
            boxes.append(part)
    return boxes


def _object_half_extents(problem: Dict[str, Any], object_name: str) -> Optional[np.ndarray]:
    for entry in problem.get("movables") or []:
        if str(entry.get("name") or "") != object_name:
            continue
        geometry = entry.get("geometry") or {}
        half = geometry.get("half_extents")
        if half is not None and len(list(half)) >= 3:
            values = np.asarray(list(half)[:3], dtype=float)
            if np.isfinite(values).all() and np.all(values > 0.0):
                return values
        metadata = geometry.get("metadata") or {}
        for part in metadata.get("collision_parts") or []:
            if str(part.get("shape") or "") == "box" and part.get("size") is not None:
                return np.abs(np.asarray(list(part["size"])[:3], dtype=float))
    return None


def _placement_target(problem: Dict[str, Any]) -> tuple[str, str]:
    """(object, surface) of the first on/inside goal atom."""
    for atom in problem.get("goal_atoms") or []:
        if not isinstance(atom, dict):
            continue
        predicate = str(atom.get("predicate") or "").lower()
        args = [str(arg) for arg in (atom.get("args") or [])]
        if predicate in {"on", "inside", "in"} and len(args) >= 2:
            return args[0], args[1]
    return "", ""


def _build_scene(
    problem: Dict[str, Any],
    site: Dict[str, Any],
    drawer_boxes: List[Dict[str, Any]],
    object_name: str,
    object_half: Optional[np.ndarray],
    drawer_progress: float,
) -> _Scene:
    body_name = str(site.get("body_name") or "")
    objects: Dict[str, _Object] = {
        body_name or "drawer_link": _Object(
            body_name or "drawer_link",
            site.get("pos") or [0.0, 0.0, 0.0],
            {"sites": [site], "geoms": [dict(box) for box in drawer_boxes]},
        )
    }
    if object_name and object_half is not None:
        center = [0.0, 0.0, 0.0]
        for entry in problem.get("movables") or []:
            if str(entry.get("name") or "") == object_name:
                center = list(entry.get("pos") or center)
                break
        objects[object_name] = _Object(
            object_name,
            center,
            {
                "geoms": [
                    {
                        "name": f"{object_name}_g1",
                        "body_name": object_name,
                        "shape": "box",
                        "size": [float(value) for value in object_half[:3]],
                        "pos": center,
                        "quat": [1.0, 0.0, 0.0, 0.0],
                        "collision_active": True,
                    }
                ]
            },
        )
    joint_range = [0.0, 1.0]
    joints = {body_name: _Joint(body_name, drawer_progress, joint_range)}
    structure = {
        body_name: {
            "joint_name": body_name,
            "body_name": body_name,
            "joint_range": joint_range,
            "reference_position": 0.0,
            "frame": "world",
            "sites": {},
        }
    }
    return _Scene(objects, joints, structure)


def _aabb_from_boxes(boxes: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not boxes:
        return None
    corners: List[np.ndarray] = []
    for box in boxes:
        pos = np.asarray(box.get("pos") or [], dtype=float).reshape(-1)[:3]
        size = np.asarray(box.get("size") or [], dtype=float).reshape(-1)[:3]
        if pos.size < 3 or size.size < 3:
            continue
        half = np.abs(size)
        quat = np.asarray(box.get("quat") or [], dtype=float).reshape(-1)
        if quat.size >= 4 and float(np.linalg.norm(quat[:4])) > 1e-8:
            half = _rotated_half(size, quat[:4])
        corners.append(pos - half)
        corners.append(pos + half)
    if not corners:
        return None
    stack = np.stack(corners, axis=0)
    return {"lo": stack.min(axis=0).tolist(), "hi": stack.max(axis=0).tolist(), "box_count": len(boxes)}


def _rotated_half(size: np.ndarray, quat_wxyz: np.ndarray) -> np.ndarray:
    from experiments.robot.libero.tiptop_repro.libero_panda_frames import quat_wxyz_to_matrix

    return np.abs(quat_wxyz_to_matrix(quat_wxyz)) @ np.abs(size)


def _fmt(values: Any) -> str:
    array = np.asarray(values, dtype=float).reshape(-1)
    return "[" + " ".join(f"{value: .5f}" for value in array) + "]"


def _fmt_box(box: Optional[Dict[str, Any]]) -> str:
    if not box:
        return "<none>"
    lo = np.asarray(box["lo"], dtype=float)
    hi = np.asarray(box["hi"], dtype=float)
    return f"x[{lo[0]: .5f},{hi[0]: .5f}] y[{lo[1]: .5f},{hi[1]: .5f}] z[{lo[2]: .5f},{hi[2]: .5f}]"


def analyse(path: Path, drawer_progress: float) -> Dict[str, Any]:
    document = _load(path)
    problem = _problem_of(document)
    sites = _collect_sites(problem)
    object_name, goal_surface = _placement_target(problem)
    region = region_from_surface_name(goal_surface) if goal_surface else ""
    site = sites.get(region) if region else None

    report: Dict[str, Any] = {
        "problem": str(path),
        "goal_surface": goal_surface,
        "goal_object": object_name,
        "region": region,
        "site_found": site is not None,
        "drawer_progress": float(drawer_progress),
    }
    if site is None:
        report["verdict"] = "no drawer region site for this goal; the skill is not involved"
        return report

    body_name = str(site.get("body_name") or "")
    drawer_boxes = _collect_collision_boxes(problem, body_name)
    local_half = _site_local_half_extents(site)
    world_half = site_axis_aligned_half_extents(site)
    pos = np.asarray(site.get("pos") or [], dtype=float).reshape(-1)[:3]

    local_box = None
    world_box = None
    if local_half is not None and pos.size == 3:
        local_box = {"lo": (pos - local_half).tolist(), "hi": (pos + local_half).tolist()}
    if world_half is not None and pos.size == 3:
        world_box = {"lo": (pos - world_half).tolist(), "hi": (pos + world_half).tolist()}
    geometry_box = _aabb_from_boxes(drawer_boxes)

    report.update(
        {
            "site_name": str(site.get("name") or ""),
            "site_type": site.get("type"),
            "site_shape": site.get("shape"),
            "site_quat_wxyz": list(site.get("quat") or []),
            "drawer_link": body_name,
            "drawer_box_count": len(drawer_boxes),
            "site_local_half_extents": None if local_half is None else local_half.tolist(),
            "site_world_half_extents": None if world_half is None else world_half.tolist(),
            "site_local_aabb": local_box,
            "site_world_aabb": world_box,
            "drawer_geometry_aabb": geometry_box,
        }
    )

    # Reproduce the pre-fix release point from the same recorded numbers.
    object_half = _object_half_extents(problem, object_name)
    report["object_half_extents"] = None if object_half is None else object_half.tolist()
    if local_half is not None and object_half is not None and pos.size == 3:
        scene = _build_scene(problem, site, drawer_boxes, object_name, object_half, drawer_progress)
        legacy_boxes = _drawer_collision_boxes(scene, region, site)
        legacy_floor = float(pos[2] - local_half[2])
        legacy_ceiling = float(pos[2] + local_half[2])
        legacy_release, legacy_reason = _release_height(
            legacy_floor,
            legacy_ceiling,
            pos[:2],
            object_half,
            legacy_boxes,
            LEGACY_HAND_BELOW_OBJECT_M,
        )
        report["legacy"] = {
            "hand_below_object_m": LEGACY_HAND_BELOW_OBJECT_M,
            "floor_z": legacy_floor,
            "ceiling_z": legacy_ceiling,
            "release_z": None if legacy_release is None else legacy_release[0],
            "release_gap": None if legacy_release is None else legacy_release[1],
            "reason": legacy_reason,
        }

    # What the current skill decides for the same scene.
    scene = _build_scene(problem, site, drawer_boxes, object_name, object_half, drawer_progress)
    decision = evaluate_open_drawer_place(scene, region, object_name or "")
    if decision is None:
        report["fixed"] = None
        report["verdict"] = "the skill does not apply to this surface"
        return report
    report["fixed"] = {
        "status": decision.get("status"),
        "reason": decision.get("reason"),
        "floor_z": decision.get("floor_z"),
        "ceiling_z": decision.get("ceiling_z"),
        "release_pos": decision.get("release_pos"),
        "hand_below_object_m": decision.get("hand_below_object_m"),
        "hand_below_object_source": decision.get("hand_below_object_source"),
        "geometry": open_drawer_place_diagnostics(decision),
    }

    # The recorded place point, when the run already produced one.
    for entry in _iter_geometry_entries(problem):
        metadata = (entry.get("geometry") or {}).get("metadata") or {}
        if str(metadata.get("source_region") or "") == region and metadata.get("open_drawer_release_pos"):
            report["recorded_release_pos"] = list(metadata["open_drawer_release_pos"])
            break

    report["verdict"] = _verdict(report)
    return report


def _verdict(report: Dict[str, Any]) -> str:
    legacy = report.get("legacy") or {}
    fixed = report.get("fixed") or {}
    geometry_box = report.get("drawer_geometry_aabb")
    local_box = report.get("site_local_aabb")
    notes: List[str] = []

    if local_box and geometry_box:
        lo = np.asarray(local_box["lo"], dtype=float)
        hi = np.asarray(local_box["hi"], dtype=float)
        g_lo = np.asarray(geometry_box["lo"], dtype=float)
        g_hi = np.asarray(geometry_box["hi"], dtype=float)
        excess = float(np.max(np.maximum(g_lo - lo, hi - g_hi)))
        notes.append(f"unrotated site box exceeds the drawer geometry by {excess:.5f} m")
        if excess > GEOMETRY_MISMATCH_TOLERANCE_M:
            notes.append("=> the recorded run read site_size in the wrong frame")

    legacy_release = legacy.get("release_z")
    fixed_release = (fixed.get("release_pos") or [None, None, None])[2]
    if legacy_release is not None and fixed_release is not None:
        delta = float(legacy_release) - float(fixed_release)
        notes.append(
            f"release height moves {delta:+.5f} m ({legacy_release:.5f} -> {fixed_release:.5f})"
        )
    if geometry_box and fixed_release is not None:
        rim = float(np.asarray(geometry_box["hi"], dtype=float)[2])
        if float(legacy_release or 0.0) > rim and float(fixed_release) <= rim:
            notes.append(
                f"the old release was above the drawer rim ({rim:.5f}); the fixed one is inside it"
            )
    recorded = report.get("recorded_release_pos")
    if recorded and legacy_release is not None:
        if abs(float(recorded[2]) - float(legacy_release)) < 1e-4:
            notes.append("legacy reproduction matches the recorded place point exactly")
    if not notes:
        notes.append("no frame error detected")
    return "; ".join(notes)


def _render(report: Dict[str, Any]) -> str:
    lines = [f"=== {report['problem']} ==="]
    lines.append(f"goal surface : {report.get('goal_surface')}  (region {report.get('region')})")
    lines.append(f"goal object  : {report.get('goal_object')}")
    if not report.get("site_found"):
        lines.append(f"verdict      : {report.get('verdict')}")
        return "\n".join(lines)
    lines.append(
        f"site         : {report.get('site_name')} type={report.get('site_type')} shape={report.get('site_shape')}"
    )
    lines.append(f"site quat    : {_fmt(report.get('site_quat_wxyz'))} (wxyz)")
    lines.append(f"drawer link  : {report.get('drawer_link')}  boxes={report.get('drawer_box_count')}")
    lines.append(f"local half   : {_fmt(report.get('site_local_half_extents'))}")
    lines.append(f"world half   : {_fmt(report.get('site_world_half_extents'))}   <- site quat applied")
    lines.append(f"local AABB   : {_fmt_box(report.get('site_local_aabb'))}")
    lines.append(f"world AABB   : {_fmt_box(report.get('site_world_aabb'))}")
    lines.append(f"geometry AABB: {_fmt_box(report.get('drawer_geometry_aabb'))}")
    lines.append(f"object half  : {_fmt(report.get('object_half_extents'))}")
    legacy = report.get("legacy") or {}
    if legacy:
        lines.append(
            "legacy (pre-fix): floor {:.5f} ceiling {:.5f} release {} gap {} hand_below {:.2f}".format(
                float(legacy.get("floor_z") or 0.0),
                float(legacy.get("ceiling_z") or 0.0),
                "None" if legacy.get("release_z") is None else f"{float(legacy['release_z']):.5f}",
                _fmt(legacy.get("release_gap") or []),
                float(legacy.get("hand_below_object_m") or 0.0),
            )
        )
        if legacy.get("reason"):
            lines.append(f"                 reason: {legacy['reason']}")
    if report.get("recorded_release_pos"):
        lines.append(f"recorded place  : {_fmt(report['recorded_release_pos'])}")
    fixed = report.get("fixed") or {}
    lines.append(
        "fixed           : status={} floor={} ceiling={} release={} hand_below={} ({})".format(
            fixed.get("status"),
            "None" if fixed.get("floor_z") is None else f"{float(fixed['floor_z']):.5f}",
            "None" if fixed.get("ceiling_z") is None else f"{float(fixed['ceiling_z']):.5f}",
            _fmt(fixed.get("release_pos") or []),
            "None" if fixed.get("hand_below_object_m") is None else f"{float(fixed['hand_below_object_m']):.5f}",
            fixed.get("hand_below_object_source"),
        )
    )
    if fixed.get("reason"):
        lines.append(f"                  reason: {fixed['reason']}")
    lines.append(f"verdict         : {report.get('verdict')}")
    return "\n".join(lines)


def _discover(directory: Path) -> List[Path]:
    return sorted(directory.glob("*.problem.json"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--problem", action="append", default=[], help="recorded *.problem.json (repeatable)")
    parser.add_argument("--dir", default="", help="directory to scan for *.problem.json")
    parser.add_argument(
        "--drawer-progress",
        type=float,
        default=DEFAULT_DRAWER_PROGRESS,
        help=f"synthetic drawer open fraction in [0,1] (default {DEFAULT_DRAWER_PROGRESS})",
    )
    parser.add_argument("--json", default="", help="write the structured report to this path")
    args = parser.parse_args(argv)

    paths = [Path(value) for value in args.problem]
    if args.dir:
        paths.extend(_discover(Path(args.dir)))
    if not paths:
        parser.error("pass --problem and/or --dir")

    reports: List[Dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            print(f"skip missing: {path}", file=sys.stderr)
            continue
        report = analyse(path, float(args.drawer_progress))
        reports.append(report)
        print(_render(report))
        print()

    if not reports:
        return 1
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            json.dump({"reports": reports}, handle, indent=2, sort_keys=True)
        print(f"wrote {out}")
    # A frame error is a real finding, not a crash: report it through the exit code.
    bad = [r for r in reports if "wrong frame" in str(r.get("verdict") or "")]
    return 2 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
