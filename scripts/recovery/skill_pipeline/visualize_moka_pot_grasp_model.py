#!/usr/bin/env python3
"""Visualize moka-pot proxy geometry and grasp candidates.

This is a diagnostic helper only: it does not change recovery behavior.  It
reads a cuTAMP ``solve_*.problem.json`` dump and writes SVG/HTML/CSV outputs
that show the object-frame AABB, collision-part boxes, the current default
top-down sampler, and a few hand-authored candidate side-body grasp points.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "experiments" / "robot" / "libero"))

from tiptop_repro.grasp_profiles import (  # noqa: E402
    LocalGraspSample,
    load_grasp_profile_registry,
    profile_gripper_width,
    sample_grasp_profile,
    wrap_yaw_rad,
)

DEFAULT_GRASP_PROFILE_REGISTRY = load_grasp_profile_registry(
    REPO / "skill_packs" / "libero90_legacy" / "code" / "grasp_profiles.py"
)


@dataclass(frozen=True)
class Panel:
    x: float
    y: float
    w: float
    h: float
    xmin: float
    xmax: float
    ymin: float
    ymax: float

    def p(self, x: float, y: float) -> Tuple[float, float]:
        sx = self.x + (float(x) - self.xmin) / (self.xmax - self.xmin) * self.w
        sy = self.y + self.h - (float(y) - self.ymin) / (self.ymax - self.ymin) * self.h
        return sx, sy


def _as_float_list(value: Any, n: int) -> Optional[List[float]]:
    if value is None:
        return None
    try:
        out = [float(v) for v in value]
    except TypeError:
        return None
    if len(out) < n:
        return None
    return out[:n]


def _problem_objects(problem_json: Path) -> List[Mapping[str, Any]]:
    with problem_json.open("r", encoding="utf-8") as f:
        data = json.load(f)
    problem = data.get("problem", data)
    objects: List[Mapping[str, Any]] = []
    for key in ("movables", "surfaces", "statics", "objects"):
        values = problem.get(key) or []
        if isinstance(values, list):
            objects.extend(item for item in values if isinstance(item, Mapping))
    return objects


def _object_from_problem(problem_json: Path, object_name: str) -> Mapping[str, Any]:
    objects = _problem_objects(problem_json)
    exact = [obj for obj in objects if str(obj.get("name") or "") == object_name]
    if exact:
        return exact[0]
    fuzzy = [obj for obj in objects if object_name.lower() in str(obj.get("name") or "").lower()]
    if fuzzy:
        return fuzzy[0]
    names = ", ".join(str(obj.get("name") or "") for obj in objects[:30])
    raise SystemExit(f"object not found in {problem_json}: {object_name}; available: {names}")


def _half_extents_from_object(obj: Mapping[str, Any]) -> List[float]:
    direct = _as_float_list(obj.get("half_extents"), 3)
    if direct is not None:
        return direct
    geometry = obj.get("geometry")
    if isinstance(geometry, Mapping):
        nested = _as_float_list(geometry.get("half_extents"), 3)
        if nested is not None:
            return nested
    return [0.04, 0.07, 0.075]


def _pose7_from_object(obj: Mapping[str, Any]) -> Optional[List[float]]:
    pose = _as_float_list(obj.get("pose"), 7)
    if pose is not None:
        return pose
    pos = _as_float_list(obj.get("pos"), 3)
    quat = _as_float_list(obj.get("quat"), 4)
    if pos is not None and quat is not None:
        return [*pos, *quat]
    return None


def _collision_parts_from_object(obj: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    geometry = obj.get("geometry")
    if not isinstance(geometry, Mapping):
        return []
    metadata = geometry.get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    parts = metadata.get("collision_parts")
    if not isinstance(parts, list):
        return []
    return [part for part in parts if isinstance(part, Mapping)]


def _central_body_half(parts: Sequence[Mapping[str, Any]], half: Sequence[float]) -> Tuple[float, float, float]:
    candidates: List[Tuple[float, float, float, float]] = []
    for part in parts:
        local = _as_float_list(part.get("local_pos"), 3)
        size = _as_float_list(part.get("size"), 3)
        if local is None or size is None:
            continue
        if abs(local[0]) <= 0.008 and abs(local[1]) <= 0.010 and size[2] >= 0.035:
            candidates.append((size[0] * size[1] * size[2], size[0], size[1], size[2]))
    if candidates:
        _, hx, hy, hz = max(candidates)
        return float(hx), float(hy), float(hz)
    return 0.62 * float(half[0]), 0.34 * float(half[1]), 0.82 * float(half[2])


def _sample(x: float, y: float, z: float, yaw: float, **metadata: Any) -> LocalGraspSample:
    return LocalGraspSample(
        xyz=(float(x), float(y), float(z)),
        rpy=(0.0, 0.0, wrap_yaw_rad(float(yaw))),
        metadata=dict(metadata, world_yaw=wrap_yaw_rad(float(yaw))),
    )


def _proposal_moka_body_x_side(
    parts: Sequence[Mapping[str, Any]],
    half: Sequence[float],
    *,
    mode: str,
) -> Tuple[List[LocalGraspSample], float]:
    body_hx, body_hy, body_hz = _central_body_half(parts, half)
    if mode == "upper":
        z_values = [min(0.044, body_hz - 0.018), min(0.036, body_hz - 0.026)]
    elif mode == "mid":
        z_values = [min(0.030, body_hz - 0.034), min(0.024, body_hz - 0.040)]
    else:
        raise ValueError(f"unknown moka proposal mode: {mode}")
    z_values = [max(0.012, float(z)) for z in z_values]
    y_offsets = [0.0, 0.18 * body_hy, -0.18 * body_hy]
    x_offsets = [0.0]
    yaws = [0.0, math.pi]
    width = max(0.045, min(0.066, 2.25 * body_hx))
    samples: List[LocalGraspSample] = []
    for z in z_values:
        for y in y_offsets:
            for x in x_offsets:
                for yaw in yaws:
                    samples.append(
                        _sample(
                            x,
                            y,
                            z,
                            yaw,
                            proposal_profile=f"proposal_moka_body_x_side_{mode}_v0",
                            body_half_x=body_hx,
                            body_half_y=body_hy,
                            body_half_z=body_hz,
                            avoid="y-axis handle/spout; close across compact x body width",
                        )
                    )
    return samples, width


def _profile_samples(
    profile: str,
    dims: Sequence[float],
    pose: Optional[List[float]],
    parts: Sequence[Mapping[str, Any]],
    half: Sequence[float],
) -> Tuple[List[LocalGraspSample], float]:
    if profile == "proposal_moka_body_x_side_upper_v0":
        return _proposal_moka_body_x_side(parts, half, mode="upper")
    if profile == "proposal_moka_body_x_side_mid_v0":
        return _proposal_moka_body_x_side(parts, half, mode="mid")
    samples = sample_grasp_profile(profile, dims, rim=False, pose=pose, registry=DEFAULT_GRASP_PROFILE_REGISTRY)
    width = profile_gripper_width(
        profile,
        dims,
        rim=False,
        radius=max(float(half[0]), float(half[1])),
        pose=pose,
        registry=DEFAULT_GRASP_PROFILE_REGISTRY,
    )
    return samples, width


def _parse_profiles(raw: str) -> List[str]:
    profiles = [part for part in re.split(r"[,\s]+", raw.strip()) if part]
    return profiles or ["libero_topdown"]


def _path(points: Iterable[Tuple[float, float]]) -> str:
    pts = list(points)
    if not pts:
        return ""
    head = f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"
    tail = " ".join(f"L {x:.2f} {y:.2f}" for x, y in pts[1:])
    return f"{head} {tail}"


def _panel_rect(panel: Panel, xmin: float, xmax: float, ymin: float, ymax: float) -> str:
    x0, y0 = panel.p(xmin, ymax)
    x1, y1 = panel.p(xmax, ymin)
    return f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" />'


def _axis(svg: List[str], panel: Panel, title: str, xlabel: str, ylabel: str) -> None:
    svg.append(
        f'<rect class="panel-bg" x="{panel.x:.1f}" y="{panel.y:.1f}" width="{panel.w:.1f}" height="{panel.h:.1f}" />'
    )
    x0, y0 = panel.p(0.0, 0.0)
    svg.append(f'<line class="axis" x1="{panel.x:.1f}" y1="{y0:.1f}" x2="{panel.x + panel.w:.1f}" y2="{y0:.1f}" />')
    svg.append(f'<line class="axis" x1="{x0:.1f}" y1="{panel.y:.1f}" x2="{x0:.1f}" y2="{panel.y + panel.h:.1f}" />')
    svg.append(f'<text class="panel-title" x="{panel.x:.1f}" y="{panel.y - 10:.1f}">{escape(title)}</text>')
    svg.append(f'<text class="axis-label" x="{panel.x + panel.w / 2:.1f}" y="{panel.y + panel.h + 28:.1f}">{xlabel}</text>')
    svg.append(
        f'<text class="axis-label" transform="translate({panel.x - 32:.1f},{panel.y + panel.h / 2:.1f}) rotate(-90)">{ylabel}</text>'
    )


def _bounds(half: Sequence[float], samples_by_profile: Mapping[str, Sequence[LocalGraspSample]]) -> Tuple[float, float]:
    xy = max(float(half[0]), float(half[1]), 0.04)
    z = max(float(half[2]), 0.075)
    for samples in samples_by_profile.values():
        for sample in samples:
            xy = max(xy, abs(float(sample.xyz[0])), abs(float(sample.xyz[1])))
            z = max(z, abs(float(sample.xyz[2])))
    return 1.25 * xy, 1.22 * z


def _draw_collision_top(svg: List[str], panel: Panel, parts: Sequence[Mapping[str, Any]], object_name: str) -> None:
    prefix = object_name.split("_main")[0]
    for part in parts:
        local = _as_float_list(part.get("local_pos"), 3)
        size = _as_float_list(part.get("size"), 3)
        if local is None or size is None:
            continue
        cls = "collision suspicious" if not str(part.get("name") or "").startswith(prefix) else "collision"
        x, y = local[0], local[1]
        sx, sy = abs(size[0]), abs(size[1])
        svg.append(f'<g class="{cls}">{_panel_rect(panel, x - sx, x + sx, y - sy, y + sy)}</g>')


def _draw_collision_side(
    svg: List[str],
    panel: Panel,
    parts: Sequence[Mapping[str, Any]],
    object_name: str,
    coord_idx: int,
) -> None:
    prefix = object_name.split("_main")[0]
    for part in parts:
        local = _as_float_list(part.get("local_pos"), 3)
        size = _as_float_list(part.get("size"), 3)
        if local is None or size is None:
            continue
        cls = "collision suspicious" if not str(part.get("name") or "").startswith(prefix) else "collision"
        coord = local[coord_idx]
        coord_size = abs(size[coord_idx])
        z = local[2]
        z_size = abs(size[2])
        svg.append(f'<g class="{cls}">{_panel_rect(panel, coord - coord_size, coord + coord_size, z - z_size, z + z_size)}</g>')


def _draw_samples(
    svg: List[str],
    panel: Panel,
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    widths_by_profile: Mapping[str, float],
    colors: Sequence[str],
    *,
    view: str,
    coord_idx: int = 0,
    label_ranks: bool = False,
) -> None:
    for pidx, (profile, samples) in enumerate(samples_by_profile.items()):
        color = colors[pidx % len(colors)]
        width = widths_by_profile[profile]
        for rank, sample in enumerate(samples):
            x, y, z = [float(v) for v in sample.xyz]
            if view == "top":
                yaw = float(sample.rpy[2])
                px, py = panel.p(x, y)
                dx = 0.5 * width * math.cos(yaw)
                dy = 0.5 * width * math.sin(yaw)
                a0 = panel.p(x - dx, y - dy)
                a1 = panel.p(x + dx, y + dy)
                svg.append(
                    f'<line x1="{a0[0]:.2f}" y1="{a0[1]:.2f}" x2="{a1[0]:.2f}" y2="{a1[1]:.2f}" '
                    f'stroke="{color}" stroke-width="1.4" opacity="0.43" />'
                )
                svg.append(
                    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.9" fill="{color}" opacity="0.90">'
                    f'<title>{escape(profile)} rank={rank} xyz=({x:.4f},{y:.4f},{z:.4f}) yaw={math.degrees(yaw):.1f}</title>'
                    f'</circle>'
                )
                if label_ranks:
                    svg.append(f'<text class="rank" x="{px + 4:.2f}" y="{py - 4:.2f}" fill="{color}">{rank}</text>')
            else:
                px, py = panel.p(sample.xyz[coord_idx], z)
                svg.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.0" fill="{color}" opacity="0.82" />')


def _write_samples_csv(
    path: Path,
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    widths_by_profile: Mapping[str, float],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "profile",
                "rank",
                "x_m",
                "y_m",
                "z_m",
                "local_yaw_rad",
                "local_yaw_deg",
                "world_yaw_rad",
                "world_yaw_deg",
                "gripper_width_m",
                "metadata_json",
            ],
        )
        writer.writeheader()
        for profile, samples in samples_by_profile.items():
            for rank, sample in enumerate(samples):
                local_yaw = float(sample.rpy[2])
                world_yaw = float(sample.metadata.get("world_yaw", local_yaw))
                writer.writerow(
                    {
                        "profile": profile,
                        "rank": rank,
                        "x_m": f"{float(sample.xyz[0]):.6f}",
                        "y_m": f"{float(sample.xyz[1]):.6f}",
                        "z_m": f"{float(sample.xyz[2]):.6f}",
                        "local_yaw_rad": f"{local_yaw:.6f}",
                        "local_yaw_deg": f"{math.degrees(local_yaw):.2f}",
                        "world_yaw_rad": f"{world_yaw:.6f}",
                        "world_yaw_deg": f"{math.degrees(world_yaw):.2f}",
                        "gripper_width_m": f"{float(widths_by_profile[profile]):.6f}",
                        "metadata_json": json.dumps(sample.metadata, sort_keys=True),
                    }
                )


def _write_svg(
    path: Path,
    *,
    object_name: str,
    problem_json: Path,
    half: Sequence[float],
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    widths_by_profile: Mapping[str, float],
    parts: Sequence[Mapping[str, Any]],
    label_ranks: bool,
) -> None:
    colors = ["#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#4f46e5"]
    xy_bound, z_bound = _bounds(half, samples_by_profile)
    top_panel = Panel(70, 105, 500, 500, -xy_bound, xy_bound, -xy_bound, xy_bound)
    xz_panel = Panel(665, 105, 460, 300, -xy_bound, xy_bound, -z_bound, z_bound)
    yz_panel = Panel(665, 525, 460, 300, -xy_bound, xy_bound, -z_bound, z_bound)
    width = 1460
    height = 900
    dims = [2.0 * float(v) for v in half]
    suspect_count = sum(1 for part in parts if not str(part.get("name") or "").startswith(object_name.split("_main")[0]))

    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#0f172a}.title{font-size:20px;font-weight:700}.subtitle{font-size:12px;fill:#475569}.panel-title{font-size:13px;font-weight:700}.axis-label{font-size:11px;fill:#475569}.rank{font-size:7px;font-weight:700}.panel-bg{fill:#f8fafc;stroke:#cbd5e1;stroke-width:1}.axis{stroke:#cbd5e1;stroke-width:1}.aabb rect{fill:none;stroke:#2563eb;stroke-width:2}.body-guide rect{fill:none;stroke:#0f766e;stroke-width:1.5;stroke-dasharray:5 4}.collision rect{fill:none;stroke:#64748b;stroke-width:.8;stroke-dasharray:3 3;opacity:.6}.collision.suspicious rect{stroke:#f97316;stroke-width:1.2;opacity:.8}.legend{font-size:12px}.small{font-size:11px;fill:#475569}",
        "</style>",
        f'<text class="title" x="32" y="34">{escape(object_name)} moka-pot grasp model</text>',
        f'<text class="subtitle" x="32" y="56">dims={dims[0]:.4f} x {dims[1]:.4f} x {dims[2]:.4f} m | source={escape(problem_json.name)} | collision_parts={len(parts)} | suspicious_names={suspect_count}</text>',
    ]

    _axis(svg, top_panel, "Top view: local x/y grasp points", "local x (m)", "local y (m)")
    _axis(svg, xz_panel, "Side view: local x/z", "local x (m)", "local z (m)")
    _axis(svg, yz_panel, "Side view: local y/z", "local y (m)", "local z (m)")
    for panel, coord_idx in ((top_panel, -1), (xz_panel, 0), (yz_panel, 1)):
        if coord_idx == -1:
            svg.append(f'<g class="aabb">{_panel_rect(panel, -half[0], half[0], -half[1], half[1])}</g>')
            _draw_collision_top(svg, panel, parts, object_name)
        elif coord_idx == 0:
            svg.append(f'<g class="aabb">{_panel_rect(panel, -half[0], half[0], -half[2], half[2])}</g>')
            _draw_collision_side(svg, panel, parts, object_name, 0)
        else:
            svg.append(f'<g class="aabb">{_panel_rect(panel, -half[1], half[1], -half[2], half[2])}</g>')
            _draw_collision_side(svg, panel, parts, object_name, 1)

    body_hx, body_hy, body_hz = _central_body_half(parts, half)
    svg.append(f'<g class="body-guide">{_panel_rect(top_panel, -body_hx, body_hx, -body_hy, body_hy)}</g>')
    svg.append(f'<g class="body-guide">{_panel_rect(xz_panel, -body_hx, body_hx, -body_hz, body_hz)}</g>')
    svg.append(f'<g class="body-guide">{_panel_rect(yz_panel, -body_hy, body_hy, -body_hz, body_hz)}</g>')

    _draw_samples(svg, top_panel, samples_by_profile, widths_by_profile, colors, view="top", label_ranks=label_ranks)
    _draw_samples(svg, xz_panel, samples_by_profile, widths_by_profile, colors, view="side", coord_idx=0)
    _draw_samples(svg, yz_panel, samples_by_profile, widths_by_profile, colors, view="side", coord_idx=1)

    legend_x = 1180
    legend_y = 120
    svg.append(f'<text class="panel-title" x="{legend_x}" y="{legend_y}">Legend</text>')
    svg.append(f'<text class="small" x="{legend_x}" y="{legend_y + 26}">blue box: full AABB</text>')
    svg.append(f'<text class="small" x="{legend_x}" y="{legend_y + 46}">teal box: inferred central body</text>')
    svg.append(f'<text class="small" x="{legend_x}" y="{legend_y + 66}">gray/orange boxes: collision parts</text>')
    row_y = legend_y + 104
    for idx, (profile, samples) in enumerate(samples_by_profile.items()):
        color = colors[idx % len(colors)]
        z_values = sorted({round(float(sample.xyz[2]), 5) for sample in samples})
        svg.append(f'<circle cx="{legend_x + 8}" cy="{row_y - 4}" r="5" fill="{color}" />')
        svg.append(
            f'<text class="legend" x="{legend_x + 22}" y="{row_y}">{escape(profile)}: '
            f'{len(samples)} pts, width={widths_by_profile[profile]:.3f}m</text>'
        )
        svg.append(f'<text class="small" x="{legend_x + 22}" y="{row_y + 18}">z={z_values}</text>')
        row_y += 52
    svg.append(f'<text class="small" x="{legend_x}" y="{height - 68}">Object-frame diagnostic. Short colored lines show sampled gripper lateral axis.</text>')
    svg.append(f'<text class="small" x="{legend_x}" y="{height - 48}">Proposal profiles are visual-only candidates; they are not registered pipeline skills.</text>')
    svg.append("</svg>")
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def _write_html(html_path: Path, svg_name: str) -> None:
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '<meta charset="utf-8" />',
                "<title>Moka-pot grasp model visualization</title>",
                '<style>body{margin:0;background:#e2e8f0}main{max-width:1500px;margin:0 auto;padding:18px}object{width:100%;height:auto;background:white;box-shadow:0 1px 8px rgba(15,23,42,.18)}</style>',
                "</head>",
                "<body><main>",
                f'<object type="image/svg+xml" data="{escape(svg_name)}"></object>',
                "</main></body></html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem-json", type=Path, required=True)
    parser.add_argument("--object-name", default="moka_pot_1_main")
    parser.add_argument(
        "--profiles",
        default="libero_topdown,moka_pot_handle_topdown_v1",
        help="Comma/space separated profiles. Proposal profiles are diagnostic only.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("remote_outputs") / "moka_pot_grasp_model_viz")
    parser.add_argument("--name", default="", help="Optional output stem label.")
    parser.add_argument("--label-ranks", action="store_true", help="Draw rank numbers next to candidates.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    obj = _object_from_problem(args.problem_json, args.object_name)
    object_name = str(obj.get("name") or args.object_name)
    half = _half_extents_from_object(obj)
    dims = [2.0 * float(v) for v in half]
    pose = _pose7_from_object(obj)
    parts = _collision_parts_from_object(obj)

    samples_by_profile: Dict[str, List[LocalGraspSample]] = {}
    widths_by_profile: Dict[str, float] = {}
    for profile in _parse_profiles(args.profiles):
        samples, width = _profile_samples(profile, dims, pose, parts, half)
        samples_by_profile[profile] = list(samples)
        widths_by_profile[profile] = float(width)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or object_name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "moka_pot"
    svg_path = args.out_dir / f"{stem}_moka_grasp_model.svg"
    html_path = args.out_dir / f"{stem}_moka_grasp_model.html"
    csv_path = args.out_dir / f"{stem}_moka_grasp_samples.csv"
    summary_path = args.out_dir / f"{stem}_moka_grasp_summary.json"

    _write_svg(
        svg_path,
        object_name=object_name,
        problem_json=args.problem_json,
        half=half,
        samples_by_profile=samples_by_profile,
        widths_by_profile=widths_by_profile,
        parts=parts,
        label_ranks=bool(args.label_ranks),
    )
    _write_html(html_path, svg_path.name)
    _write_samples_csv(csv_path, samples_by_profile, widths_by_profile)
    summary = {
        "object_name": object_name,
        "problem_json": str(args.problem_json),
        "half_extents_m": half,
        "dims_m": dims,
        "collision_part_count": len(parts),
        "suspicious_collision_part_names": [
            str(part.get("name") or "")
            for part in parts
            if not str(part.get("name") or "").startswith(object_name.split("_main")[0])
        ],
        "inferred_central_body_half_extents_m": list(_central_body_half(parts, half)),
        "profiles": {
            profile: {
                "num_samples": len(samples_by_profile[profile]),
                "gripper_width_m": widths_by_profile[profile],
                "z_values_m": sorted({round(float(sample.xyz[2]), 6) for sample in samples_by_profile[profile]}),
            }
            for profile in samples_by_profile
        },
        "outputs": {"svg": str(svg_path), "html": str(html_path), "csv": str(csv_path)},
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"wrote {svg_path}")
    print(f"wrote {html_path}")
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
