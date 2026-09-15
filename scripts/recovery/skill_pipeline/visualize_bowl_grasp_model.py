#!/usr/bin/env python3
"""Visualize bowl proxy geometry and recovery grasp samples.

The script can either use explicit dimensions or read a cuTAMP
`solve_*.problem.json` dump. It writes dependency-free SVG/HTML plus a CSV
table of grasp samples, so it can run in the local repo or on the server
without matplotlib.

Examples:

    python scripts/recovery/skill_pipeline/visualize_bowl_grasp_model.py \
        --dims 0.15 0.15 0.05 \
        --profiles bowl_rim_diagonal_mixed_topdown_v1

    python scripts/recovery/skill_pipeline/visualize_bowl_grasp_model.py \
        --problem-json remote_outputs/debug/task38_shallow_bowl_v2_20260824/cutamp_debug/solve_1787502001850_921233.problem.json \
        --object-name white_bowl_1_main \
        --profiles bowl_rim_diagonal_mixed_topdown_v1,bowl_rim_small_shallow_diagonal_topdown_v1
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
    normalize_grasp_sampler_profile,
    profile_gripper_width,
    sample_grasp_profile,
)


DEFAULT_PROFILES = ("bowl_rim_diagonal_mixed_topdown_v1",)
DEFAULT_GRASP_PROFILE_REGISTRY = load_grasp_profile_registry(
    REPO / "skill_packs" / "libero90_legacy" / "code" / "grasp_profiles.py"
)
BOWLISH_NAME_RE = re.compile(r"(bowl|akita)", re.IGNORECASE)


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


def _parse_profiles(raw: str | Sequence[str]) -> List[str]:
    if isinstance(raw, str):
        parts = re.split(r"[,\s]+", raw.strip())
    else:
        parts = []
        for item in raw:
            parts.extend(re.split(r"[,\s]+", str(item).strip()))
    profiles = [normalize_grasp_sampler_profile(part, registry=DEFAULT_GRASP_PROFILE_REGISTRY) for part in parts if part]
    return profiles or list(DEFAULT_PROFILES)


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
    for key in ("movables", "surfaces", "statics"):
        values = problem.get(key) or []
        if isinstance(values, list):
            objects.extend(item for item in values if isinstance(item, Mapping))
    return objects


def _object_from_problem(problem_json: Path, object_name: str | None) -> Mapping[str, Any]:
    objects = _problem_objects(problem_json)
    if object_name:
        exact = [obj for obj in objects if str(obj.get("name") or "") == object_name]
        if exact:
            return exact[0]
        fuzzy = [obj for obj in objects if object_name.lower() in str(obj.get("name") or "").lower()]
        if fuzzy:
            return fuzzy[0]
        raise SystemExit(f"object not found in {problem_json}: {object_name}")
    bowl_like = [obj for obj in objects if BOWLISH_NAME_RE.search(str(obj.get("name") or ""))]
    if not bowl_like:
        names = ", ".join(str(obj.get("name") or "") for obj in objects[:20])
        raise SystemExit(f"no bowl-like object found in {problem_json}; available: {names}")
    return bowl_like[0]


def _half_extents_from_object(obj: Mapping[str, Any]) -> List[float]:
    direct = _as_float_list(obj.get("half_extents"), 3)
    if direct is not None:
        return direct
    geometry = obj.get("geometry")
    if isinstance(geometry, Mapping):
        nested = _as_float_list(geometry.get("half_extents"), 3)
        if nested is not None:
            return nested
    radius = float(obj.get("radius") or 0.06)
    height = float(obj.get("height") or 0.04)
    return [radius, radius, 0.5 * height]


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


def _ring(rx: float, ry: float, z: float = 0.0, n: int = 96) -> List[Tuple[float, float, float]]:
    return [
        (rx * math.cos(2.0 * math.pi * i / n), ry * math.sin(2.0 * math.pi * i / n), z)
        for i in range(n + 1)
    ]


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


def _meter_bounds(half: Sequence[float], samples_by_profile: Mapping[str, Sequence[LocalGraspSample]]) -> float:
    radius = max(abs(float(half[0])), abs(float(half[1])), 0.03)
    for samples in samples_by_profile.values():
        for sample in samples:
            radius = max(radius, abs(float(sample.xyz[0])), abs(float(sample.xyz[1])), abs(float(sample.xyz[2])))
    return radius * 1.28


def _iso(x: float, y: float, z: float, cx: float, cy: float, scale: float) -> Tuple[float, float]:
    return (
        cx + scale * 0.88 * (x - y),
        cy + scale * (0.44 * (x + y) - 1.65 * z),
    )


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
                "yaw_rad",
                "yaw_deg",
                "gripper_width_m",
                "metadata_json",
            ],
        )
        writer.writeheader()
        for profile, samples in samples_by_profile.items():
            for rank, sample in enumerate(samples):
                yaw = float(sample.metadata.get("world_yaw", sample.rpy[2]))
                writer.writerow(
                    {
                        "profile": profile,
                        "rank": rank,
                        "x_m": f"{float(sample.xyz[0]):.6f}",
                        "y_m": f"{float(sample.xyz[1]):.6f}",
                        "z_m": f"{float(sample.xyz[2]):.6f}",
                        "yaw_rad": f"{yaw:.6f}",
                        "yaw_deg": f"{math.degrees(yaw):.2f}",
                        "gripper_width_m": f"{float(widths_by_profile[profile]):.6f}",
                        "metadata_json": json.dumps(sample.metadata, sort_keys=True),
                    }
                )


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


def _draw_top_view(
    svg: List[str],
    panel: Panel,
    half: Sequence[float],
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    widths_by_profile: Mapping[str, float],
    collision_parts: Sequence[Mapping[str, Any]],
    colors: Sequence[str],
    label_ranks: bool,
) -> None:
    hx, hy, hz = [float(v) for v in half]
    _axis(svg, panel, "Top view: local x/y grasp points", "local x (m)", "local y (m)")
    top_path = _path(panel.p(x, y) for x, y, _ in _ring(hx, hy, hz))
    inner_path = _path(panel.p(x, y) for x, y, _ in _ring(0.72 * hx, 0.72 * hy, hz - 0.006))
    svg.append(f'<path class="rim" d="{top_path}" />')
    svg.append(f'<path class="inner" d="{inner_path}" />')
    svg.append(f'<g class="aabb">{_panel_rect(panel, -hx, hx, -hy, hy)}</g>')

    for part in collision_parts:
        local = _as_float_list(part.get("local_pos"), 3)
        size = _as_float_list(part.get("size"), 3)
        if local is None or size is None:
            continue
        x, y = local[0], local[1]
        sx, sy = abs(size[0]), abs(size[1])
        svg.append(f'<g class="collision">{_panel_rect(panel, x - sx, x + sx, y - sy, y + sy)}</g>')

    for pidx, (profile, samples) in enumerate(samples_by_profile.items()):
        color = colors[pidx % len(colors)]
        width = widths_by_profile[profile]
        for rank, sample in enumerate(samples):
            x, y, z = [float(v) for v in sample.xyz]
            yaw = float(sample.metadata.get("world_yaw", sample.rpy[2]))
            px, py = panel.p(x, y)
            dx = 0.5 * width * math.cos(yaw)
            dy = 0.5 * width * math.sin(yaw)
            a0 = panel.p(x - dx, y - dy)
            a1 = panel.p(x + dx, y + dy)
            svg.append(
                f'<line x1="{a0[0]:.2f}" y1="{a0[1]:.2f}" x2="{a1[0]:.2f}" y2="{a1[1]:.2f}" '
                f'stroke="{color}" stroke-width="1.2" opacity="0.42" />'
            )
            svg.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.6" fill="{color}" opacity="0.88">'
                f'<title>{escape(profile)} rank={rank} xyz=({x:.4f},{y:.4f},{z:.4f}) yaw={math.degrees(yaw):.1f}</title>'
                f'</circle>'
            )
            if label_ranks:
                svg.append(f'<text class="rank" x="{px + 4:.2f}" y="{py - 4:.2f}" fill="{color}">{rank}</text>')


def _draw_side_view(
    svg: List[str],
    panel: Panel,
    half_a: float,
    half_z: float,
    axis_name: str,
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    colors: Sequence[str],
    coord_idx: int,
) -> None:
    _axis(svg, panel, f"Side view: {axis_name}/z", f"local {axis_name} (m)", "local z (m)")
    svg.append(f'<g class="aabb">{_panel_rect(panel, -half_a, half_a, -half_z, half_z)}</g>')
    p0 = panel.p(-half_a, half_z)
    p1 = panel.p(half_a, half_z)
    svg.append(f'<line class="rim-line" x1="{p0[0]:.2f}" y1="{p0[1]:.2f}" x2="{p1[0]:.2f}" y2="{p1[1]:.2f}" />')
    for pidx, samples in enumerate(samples_by_profile.values()):
        color = colors[pidx % len(colors)]
        for sample in samples:
            coord = float(sample.xyz[coord_idx])
            z = float(sample.xyz[2])
            px, py = panel.p(coord, z)
            svg.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.7" fill="{color}" opacity="0.76" />')


def _draw_iso_view(
    svg: List[str],
    x: float,
    y: float,
    w: float,
    h: float,
    half: Sequence[float],
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    colors: Sequence[str],
) -> None:
    hx, hy, hz = [float(v) for v in half]
    svg.append(f'<rect class="panel-bg" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" />')
    svg.append(f'<text class="panel-title" x="{x:.1f}" y="{y - 10:.1f}">3D proxy: bowl rings and top-down approach</text>')
    scale = min(w, h) / max(0.20, 4.8 * max(hx, hy, hz))
    cx = x + w * 0.52
    cy = y + h * 0.58
    rings = [
        (_ring(hx, hy, hz), "rim"),
        (_ring(0.82 * hx, 0.82 * hy, 0.05 * hz), "inner"),
        (_ring(0.46 * hx, 0.46 * hy, -hz), "inner"),
    ]
    for ring, cls in rings:
        svg.append(f'<path class="{cls}" d="{_path(_iso(px, py, pz, cx, cy, scale) for px, py, pz in ring)}" />')
    for i in range(0, 96, 12):
        t = 2.0 * math.pi * i / 96
        top = (hx * math.cos(t), hy * math.sin(t), hz)
        bottom = (0.46 * hx * math.cos(t), 0.46 * hy * math.sin(t), -hz)
        p0 = _iso(*bottom, cx, cy, scale)
        p1 = _iso(*top, cx, cy, scale)
        svg.append(f'<line class="bowl-side" x1="{p0[0]:.2f}" y1="{p0[1]:.2f}" x2="{p1[0]:.2f}" y2="{p1[1]:.2f}" />')
    for pidx, samples in enumerate(samples_by_profile.values()):
        color = colors[pidx % len(colors)]
        step = max(1, len(samples) // 32)
        for rank, sample in enumerate(samples):
            sx, sy, sz = [float(v) for v in sample.xyz]
            px, py = _iso(sx, sy, sz, cx, cy, scale)
            svg.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.1" fill="{color}" opacity="0.82" />')
            if rank % step == 0:
                p0 = _iso(sx, sy, sz + 0.026, cx, cy, scale)
                svg.append(
                    f'<line x1="{p0[0]:.2f}" y1="{p0[1]:.2f}" x2="{px:.2f}" y2="{py:.2f}" '
                    f'stroke="{color}" stroke-width="0.9" opacity="0.35" />'
                )


def _write_svg(
    path: Path,
    *,
    object_name: str,
    problem_json: Optional[Path],
    half: Sequence[float],
    samples_by_profile: Mapping[str, Sequence[LocalGraspSample]],
    widths_by_profile: Mapping[str, float],
    collision_parts: Sequence[Mapping[str, Any]],
    label_ranks: bool,
) -> None:
    colors = ["#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#4f46e5"]
    radius = _meter_bounds(half, samples_by_profile)
    hz = max(float(half[2]) * 1.8, radius * 0.55)
    top_panel = Panel(70, 105, 440, 440, -radius, radius, -radius, radius)
    xz_panel = Panel(585, 105, 390, 285, -radius, radius, -hz, hz)
    yz_panel = Panel(585, 505, 390, 285, -radius, radius, -hz, hz)
    width = 1460
    height = 870
    dims = [2.0 * float(v) for v in half]
    source = problem_json.name if problem_json else "explicit/default dimensions"

    svg: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#0f172a}.title{font-size:20px;font-weight:700}.subtitle{font-size:12px;fill:#475569}.panel-title{font-size:13px;font-weight:700}.axis-label{font-size:11px;fill:#475569}.rank{font-size:7px;font-weight:700}.panel-bg{fill:#f8fafc;stroke:#cbd5e1;stroke-width:1}.axis{stroke:#cbd5e1;stroke-width:1}.rim{fill:none;stroke:#2563eb;stroke-width:2}.inner{fill:none;stroke:#60a5fa;stroke-width:1.4;stroke-dasharray:4 4}.bowl-side{stroke:#93c5fd;stroke-width:1;opacity:.7}.rim-line{stroke:#2563eb;stroke-width:1.5}.aabb rect{fill:none;stroke:#ef4444;stroke-width:1.6}.collision rect{fill:none;stroke:#64748b;stroke-width:.8;stroke-dasharray:3 3;opacity:.55}.legend{font-size:12px}.small{font-size:11px;fill:#475569}",
        "</style>",
        f'<text class="title" x="32" y="34">{escape(object_name)} bowl grasp model</text>',
        f'<text class="subtitle" x="32" y="56">dims={dims[0]:.4f} x {dims[1]:.4f} x {dims[2]:.4f} m | source={escape(source)} | collision_parts={len(collision_parts)}</text>',
    ]

    _draw_top_view(svg, top_panel, half, samples_by_profile, widths_by_profile, collision_parts, colors, label_ranks)
    _draw_side_view(svg, xz_panel, float(half[0]), float(half[2]), "x", samples_by_profile, colors, 0)
    _draw_side_view(svg, yz_panel, float(half[1]), float(half[2]), "y", samples_by_profile, colors, 1)
    _draw_iso_view(svg, 1030, 105, 380, 440, half, samples_by_profile, colors)

    legend_x = 1030
    legend_y = 610
    svg.append(f'<text class="panel-title" x="{legend_x}" y="{legend_y}">Legend / sample counts</text>')
    for idx, (profile, samples) in enumerate(samples_by_profile.items()):
        color = colors[idx % len(colors)]
        row_y = legend_y + 26 + idx * 28
        z_values = sorted({round(float(sample.xyz[2]), 5) for sample in samples})
        svg.append(f'<circle cx="{legend_x + 8}" cy="{row_y - 4}" r="5" fill="{color}" />')
        svg.append(
            f'<text class="legend" x="{legend_x + 22}" y="{row_y}">{escape(profile)}: '
            f'{len(samples)} pts, width={widths_by_profile[profile]:.3f}m, z={z_values}</text>'
        )
    svg.append(f'<text class="small" x="{legend_x}" y="{height - 55}">Object-frame view. Red box is sampler AABB proxy; blue ellipses are bowl rim/body guides.</text>')
    svg.append(f'<text class="small" x="{legend_x}" y="{height - 35}">Short colored lines in top view show the sampled yaw/gripper lateral axis.</text>')
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
                "<title>Bowl grasp model visualization</title>",
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
    parser.add_argument("--problem-json", type=Path, help="Optional cuTAMP solve_*.problem.json.")
    parser.add_argument("--object-name", help="Object name or substring to load from --problem-json.")
    parser.add_argument(
        "--dims",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        default=None,
        help="Full object extents in meters. Ignored when --problem-json provides half_extents.",
    )
    parser.add_argument(
        "--profiles",
        default=",".join(DEFAULT_PROFILES),
        help="Comma/space separated grasp profiles to overlay.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("remote_outputs") / "bowl_grasp_model_viz")
    parser.add_argument("--name", default="", help="Optional output stem label.")
    parser.add_argument("--label-ranks", action="store_true", help="Draw rank numbers next to candidates.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    profiles = _parse_profiles(args.profiles)
    object_name = args.object_name or "bowl_proxy"
    collision_parts: List[Mapping[str, Any]] = []

    if args.problem_json:
        obj = _object_from_problem(args.problem_json, args.object_name)
        object_name = str(obj.get("name") or object_name)
        half = _half_extents_from_object(obj)
        collision_parts = _collision_parts_from_object(obj)
    elif args.dims:
        half = [0.5 * float(v) for v in args.dims]
    else:
        half = [0.075, 0.075, 0.025]

    dims = [2.0 * float(v) for v in half]
    samples_by_profile: Dict[str, List[LocalGraspSample]] = {
        profile: sample_grasp_profile(profile, dims, rim=True, registry=DEFAULT_GRASP_PROFILE_REGISTRY)
        for profile in profiles
    }
    widths_by_profile: Dict[str, float] = {
        profile: profile_gripper_width(
            profile,
            dims,
            rim=True,
            radius=max(half[0], half[1]),
            registry=DEFAULT_GRASP_PROFILE_REGISTRY,
        )
        for profile in profiles
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or object_name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "bowl_proxy"
    svg_path = args.out_dir / f"{stem}_bowl_grasp_model.svg"
    html_path = args.out_dir / f"{stem}_bowl_grasp_model.html"
    csv_path = args.out_dir / f"{stem}_bowl_grasp_samples.csv"
    summary_path = args.out_dir / f"{stem}_bowl_grasp_summary.json"

    _write_svg(
        svg_path,
        object_name=object_name,
        problem_json=args.problem_json,
        half=half,
        samples_by_profile=samples_by_profile,
        widths_by_profile=widths_by_profile,
        collision_parts=collision_parts,
        label_ranks=bool(args.label_ranks),
    )
    _write_html(html_path, svg_path.name)
    _write_samples_csv(csv_path, samples_by_profile, widths_by_profile)
    summary = {
        "object_name": object_name,
        "problem_json": None if args.problem_json is None else str(args.problem_json),
        "half_extents_m": half,
        "dims_m": dims,
        "profiles": {
            profile: {
                "num_samples": len(samples_by_profile[profile]),
                "gripper_width_m": widths_by_profile[profile],
                "z_values_m": sorted({round(float(sample.xyz[2]), 6) for sample in samples_by_profile[profile]}),
            }
            for profile in profiles
        },
        "collision_part_count": len(collision_parts),
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
