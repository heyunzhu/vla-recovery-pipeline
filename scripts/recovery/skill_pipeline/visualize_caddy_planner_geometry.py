#!/usr/bin/env python3
"""Top-down visualization of planner-side caddy / compartment / book geometry."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
from typing import Any

import numpy as np

COMPARTMENT_FRACTIONS = {
    "front": {"x_min": 0.10, "x_max": 0.90, "y_min": 0.04, "y_max": 0.42},
    "back": {"x_min": 0.10, "x_max": 0.90, "y_min": 0.58, "y_max": 0.96},
    "left": {"x_min": 0.04, "x_max": 0.45, "y_min": 0.10, "y_max": 0.90},
    "right": {"x_min": 0.55, "x_max": 0.96, "y_min": 0.10, "y_max": 0.90},
}


def quat_wxyz_to_matrix(quat: Any) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64).reshape(-1)[:4]
    q = q / max(float(np.linalg.norm(q)), 1e-12)
    w, x, y, z = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def box_corners(pos: Any, quat: Any, half: Any) -> np.ndarray:
    rot = quat_wxyz_to_matrix(quat)
    pos_arr = np.asarray(pos, dtype=np.float64).reshape(-1)[:3]
    half_arr = np.asarray(half, dtype=np.float64).reshape(-1)[:3]
    corners = []
    for signs in itertools.product((-1.0, 1.0), repeat=3):
        local = np.asarray(signs, dtype=np.float64) * half_arr
        corners.append(pos_arr + rot @ local)
    return np.stack(corners, axis=0)


def convex_hull_xy(points: np.ndarray) -> list[list[float]]:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, np.asarray(points).shape[-1])[:, :2]
    uniq = np.unique(np.round(pts, 6), axis=0)
    if len(uniq) <= 2:
        return uniq.tolist()
    ordered = uniq[np.lexsort((uniq[:, 1], uniq[:, 0]))]

    def cross(origin: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
        return float((a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0]))

    lower: list[list[float]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(np.asarray(lower[-2]), np.asarray(lower[-1]), point) <= 0.0:
            lower.pop()
        lower.append(point.tolist())
    upper: list[list[float]] = []
    for point in ordered[::-1]:
        while len(upper) >= 2 and cross(np.asarray(upper[-2]), np.asarray(upper[-1]), point) <= 0.0:
            upper.pop()
        upper.append(point.tolist())
    return lower[:-1] + upper[:-1]


def aabb_of_points(points: np.ndarray) -> dict[str, float]:
    pts = np.asarray(points, dtype=np.float64)
    return {
        "x_min": float(pts[:, 0].min()),
        "x_max": float(pts[:, 0].max()),
        "y_min": float(pts[:, 1].min()),
        "y_max": float(pts[:, 1].max()),
        "z_min": float(pts[:, 2].min()) if pts.shape[1] > 2 else 0.0,
        "z_max": float(pts[:, 2].max()) if pts.shape[1] > 2 else 0.0,
    }


def rect_poly(bounds: dict[str, float]) -> list[list[float]]:
    return [
        [bounds["x_min"], bounds["y_min"]],
        [bounds["x_max"], bounds["y_min"]],
        [bounds["x_max"], bounds["y_max"]],
        [bounds["x_min"], bounds["y_max"]],
    ]


def _poly_area(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for idx, point in enumerate(points):
        nxt = points[(idx + 1) % len(points)]
        area += point[0] * nxt[1] - nxt[0] * point[1]
    return abs(area) * 0.5


def crop_fraction(bounds: dict[str, float], fraction: dict[str, float], margin: float) -> dict[str, float]:
    x_min = bounds["x_min"] + margin
    x_max = bounds["x_max"] - margin
    y_min = bounds["y_min"] + margin
    y_max = bounds["y_max"] - margin
    span_x = max(x_max - x_min, 1e-6)
    span_y = max(y_max - y_min, 1e-6)
    return {
        "x_min": x_min + span_x * fraction["x_min"],
        "x_max": x_min + span_x * fraction["x_max"],
        "y_min": y_min + span_y * fraction["y_min"],
        "y_max": y_min + span_y * fraction["y_max"],
    }


def standing_footprint_dims(half: np.ndarray, rot: np.ndarray) -> tuple[float, float, int, int]:
    vertical = int(np.argmax(np.abs(rot[2, :])))
    horiz = [idx for idx in range(3) if idx != vertical]
    thin = min(horiz, key=lambda idx: float(half[idx]))
    wide = max(horiz, key=lambda idx: float(half[idx]))
    return float(2.0 * half[thin]), float(2.0 * half[wide]), thin, wide


def yaw_of_axis(rot: np.ndarray, axis: int) -> float:
    return float(math.atan2(rot[1, axis], rot[0, axis]))


def standing_book_poly(center_xy: list[float], thin_m: float, wide_m: float, yaw_rad: float) -> list[list[float]]:
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    hx, hy = 0.5 * thin_m, 0.5 * wide_m
    local = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    out = []
    for x, y in local:
        out.append([center_xy[0] + c * x - s * y, center_xy[1] + s * x + c * y])
    return out


def aabb_fits(poly: list[list[float]], bounds: dict[str, float]) -> dict[str, Any]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    box = {"x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys)}
    return {
        "fits": box["x_min"] >= bounds["x_min"] - 1e-6
        and box["x_max"] <= bounds["x_max"] + 1e-6
        and box["y_min"] >= bounds["y_min"] - 1e-6
        and box["y_max"] <= bounds["y_max"] + 1e-6,
        "x_clearance_m": min(box["x_min"] - bounds["x_min"], bounds["x_max"] - box["x_max"]),
        "y_clearance_m": min(box["y_min"] - bounds["y_min"], bounds["y_max"] - box["y_max"]),
        "footprint_aabb_m": [box["x_max"] - box["x_min"], box["y_max"] - box["y_min"]],
    }


def iter_objects(problem: dict[str, Any]):
    for key in ("movables", "statics", "surfaces"):
        for obj in problem.get(key) or []:
            if isinstance(obj, dict):
                yield obj


def collision_parts(obj: dict[str, Any]) -> list[dict[str, Any]]:
    geom = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else {}
    meta = geom.get("metadata") if isinstance(geom.get("metadata"), dict) else {}
    return [part for part in meta.get("collision_parts") or [] if isinstance(part, dict)]


def extract_scene(path: pathlib.Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    problem = payload.get("problem", payload)
    objects = {str(obj["name"]): obj for obj in iter_objects(problem)}
    book = objects["black_book_1_main"]
    caddy = objects["desk_caddy_1_main"]
    part = collision_parts(book)[0]
    half = np.asarray(part["size"][:3], dtype=np.float64)
    rot = quat_wxyz_to_matrix(part["quat"])
    corners = box_corners(part["pos"], part["quat"], half)
    thin_m, wide_m, thin_axis, wide_axis = standing_footprint_dims(half, rot)
    caddy_parts = []
    caddy_corners = []
    for item in collision_parts(caddy):
        if str(item.get("shape") or "").lower() != "box":
            continue
        item_half = np.asarray(item["size"][:3], dtype=np.float64)
        item_corners = box_corners(item["pos"], item.get("quat") or [1, 0, 0, 0], item_half)
        caddy_corners.append(item_corners)
        caddy_parts.append(
            {
                "name": item.get("name"),
                "body_name": item.get("body_name"),
                "size_m": [float(2.0 * v) for v in item_half],
                "pos": [float(v) for v in item["pos"][:3]],
                "hull_xy": convex_hull_xy(item_corners),
                "aabb": aabb_of_points(item_corners),
            }
        )
    all_caddy = np.concatenate(caddy_corners, axis=0) if caddy_corners else box_corners(caddy["pos"], caddy.get("quat") or [1, 0, 0, 0], caddy["half_extents"])
    caddy_aabb = aabb_of_points(all_caddy)
    planner_compartments = {}
    for obj in problem.get("surfaces") or []:
        name = str(obj.get("name") or "")
        if "inner_floor" not in name:
            continue
        meta = ((obj.get("geometry") or {}).get("metadata") or {})
        inner = dict(meta.get("inner_bounds") or {})
        if not inner:
            continue
        compartment = str(meta.get("compartment") or name.split("_")[-3] if "_inner_floor" in name else name)
        planner_compartments[compartment] = {
            "name": name,
            "bounds": {k: float(inner[k]) for k in ("x_min", "x_max", "y_min", "y_max") if k in inner},
            "support_z": float(inner.get("support_z", inner.get("z_min", 0.0))),
            "planner_support_z_m": float(meta.get("planner_support_z_m", inner.get("support_z", 0.0))),
            "poly": rect_poly({k: float(inner[k]) for k in ("x_min", "x_max", "y_min", "y_max")}),
        }
    reconstructed = {}
    for name, fraction in COMPARTMENT_FRACTIONS.items():
        bounds = crop_fraction(caddy_aabb, fraction, margin=0.010)
        reconstructed[name] = {
            "name": f"reconstructed_{name}",
            "bounds": bounds,
            "poly": rect_poly(bounds),
            "span_m": [bounds["x_max"] - bounds["x_min"], bounds["y_max"] - bounds["y_min"]],
        }
    goal = ""
    for atom in problem.get("required_final_atoms") or problem.get("goal_atoms") or []:
        if isinstance(atom, dict) and str(atom.get("predicate") or "").lower() == "on":
            args = atom.get("args") or []
            if len(args) >= 2:
                goal = f"on({args[0]}, {args[1]})"
    mug = objects.get("white_yellow_mug_1_main")
    mug_payload = None
    if mug is not None:
        mug_he = np.asarray(mug.get("half_extents") or [0.04, 0.04, 0.04], dtype=np.float64)
        mug_corners = box_corners(mug["pos"], mug.get("quat") or [1, 0, 0, 0], mug_he)
        mug_payload = {"name": mug["name"], "hull_xy": convex_hull_xy(mug_corners), "aabb": aabb_of_points(mug_corners)}
    return {
        "problem_name": path.stem.replace(".problem", ""),
        "goal": goal,
        "book": {
            "name": book["name"],
            "collision_part_name": part.get("name"),
            "body_name": part.get("body_name"),
            "pos": [float(v) for v in part["pos"][:3]],
            "quat_wxyz": [float(v) for v in part["quat"][:4]],
            "box_size_m": [float(2.0 * v) for v in half],
            "aabb_size_m": [float(2.0 * v) for v in book["half_extents"][:3]],
            "hull_xy": convex_hull_xy(corners),
            "aabb": aabb_of_points(corners),
            "thin_m": thin_m,
            "wide_m": wide_m,
            "thin_axis": thin_axis,
            "wide_axis": wide_axis,
            "thin_yaw_deg": math.degrees(yaw_of_axis(rot, thin_axis)),
            "wide_yaw_deg": math.degrees(yaw_of_axis(rot, wide_axis)),
        },
        "caddy": {
            "name": caddy["name"],
            "aabb": caddy_aabb,
            "aabb_size_m": [caddy_aabb["x_max"] - caddy_aabb["x_min"], caddy_aabb["y_max"] - caddy_aabb["y_min"], caddy_aabb["z_max"] - caddy_aabb["z_min"]],
            "hull_xy": convex_hull_xy(all_caddy),
            "parts": caddy_parts,
        },
        "mug": mug_payload,
        "planner_compartments": planner_compartments,
        "reconstructed_compartments": reconstructed,
    }


def candidate_poses(scene: dict[str, Any]) -> list[dict[str, Any]]:
    book = scene["book"]
    out = []
    for compartment, info in {**scene["reconstructed_compartments"], **{k: {"bounds": v["bounds"], "poly": v["poly"]} for k, v in scene["planner_compartments"].items()}}.items():
        bounds = info["bounds"]
        center = [0.5 * (bounds["x_min"] + bounds["x_max"]), 0.5 * (bounds["y_min"] + bounds["y_max"])]
        span = [bounds["x_max"] - bounds["x_min"], bounds["y_max"] - bounds["y_min"]]
        options = [
            ("current_yaw_at_center", math.radians(book["thin_yaw_deg"])),
            ("thin_along_x", 0.0),
            ("thin_along_y", math.pi / 2.0),
        ]
        for label, yaw in options:
            poly = standing_book_poly(center, book["thin_m"], book["wide_m"], yaw)
            fit = aabb_fits(poly, bounds)
            out.append(
                {
                    "compartment": compartment,
                    "label": label,
                    "yaw_deg": (math.degrees(yaw) + 180.0) % 360.0 - 180.0,
                    "center_xy": center,
                    "span_m": span,
                    "poly": poly,
                    **fit,
                }
            )
    return out


def _svg_poly(points: list[list[float]], world_to_px, **attrs: Any) -> str:
    pts = " ".join(f"{world_to_px(x, y)[0]:.1f},{world_to_px(x, y)[1]:.1f}" for x, y in points)
    extra = " ".join(f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<polygon points="{pts}" {extra} />'


def _svg_text(x: float, y: float, text: str, world_to_px, **attrs: Any) -> str:
    px, py = world_to_px(x, y)
    extra = " ".join(f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<text x="{px:.1f}" y="{py:.1f}" {extra}>{text}</text>'


def plot_scene(scene: dict[str, Any], candidates: list[dict[str, Any]], out_path: pathlib.Path) -> None:
    colors = {"front": "#d9480f", "left": "#2b8a3e", "back": "#7048e8", "right": "#1971c2"}
    caddy_aabb = scene["caddy"]["aabb"]
    xs = [caddy_aabb["x_min"], caddy_aabb["x_max"], scene["book"]["aabb"]["x_min"], scene["book"]["aabb"]["x_max"]]
    ys = [caddy_aabb["y_min"], caddy_aabb["y_max"], scene["book"]["aabb"]["y_min"], scene["book"]["aabb"]["y_max"]]
    if scene.get("mug"):
        xs.extend([scene["mug"]["aabb"]["x_min"], scene["mug"]["aabb"]["x_max"]])
        ys.extend([scene["mug"]["aabb"]["y_min"], scene["mug"]["aabb"]["y_max"]])
    pad = 0.04
    x_min, x_max = min(xs) - pad, max(xs) + pad
    y_min, y_max = min(ys) - pad, max(ys) + pad
    panel_w, panel_h, gap, margin = 640, 640, 28, 56
    width = margin * 2 + panel_w * 2 + gap
    height = margin + 48 + panel_h + 120

    def mapper(origin_x: float):
        scale = min(panel_w / (x_max - x_min), panel_h / (y_max - y_min))

        def world_to_px(x: float, y: float) -> tuple[float, float]:
            px = origin_x + (x - x_min) * scale
            py = margin + 48 + (y_max - y) * scale
            return px, py

        return world_to_px

    left_map = mapper(margin)
    right_map = mapper(margin + panel_w + gap)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fffef8"/>',
        f'<text x="{margin}" y="28" font-size="16" font-family="Segoe UI, sans-serif">{scene["problem_name"]}</text>',
        f'<text x="{margin}" y="48" font-size="12" fill="#495057" font-family="Segoe UI, sans-serif">{scene["goal"]}</text>',
        f'<text x="{margin}" y="{margin + 64}" font-size="12" font-family="Segoe UI, sans-serif">left: planner collision / compartment proxies</text>',
        f'<text x="{margin + panel_w + gap}" y="{margin + 64}" font-size="12" font-family="Segoe UI, sans-serif">right: standing-book yaws in the goal slot</text>',
    ]

    def draw_panel(world_to_px, include_candidates: bool) -> None:
        parts.append(_svg_poly(rect_poly(caddy_aabb), world_to_px, fill="none", stroke="#444", stroke_width="1.6", stroke_dasharray="6 4"))
        for part in scene["caddy"]["parts"]:
            area = _poly_area(part["hull_xy"])
            caddy_area = (caddy_aabb["x_max"] - caddy_aabb["x_min"]) * (caddy_aabb["y_max"] - caddy_aabb["y_min"])
            if area > 0.6 * caddy_area:
                continue
            parts.append(_svg_poly(part["hull_xy"], world_to_px, fill="#d0d0d0", fill_opacity="0.55", stroke="#333", stroke_width="0.8"))
        for name, info in scene["reconstructed_compartments"].items():
            parts.append(_svg_poly(info["poly"], world_to_px, fill="none", stroke=colors[name], stroke_width="1.6"))
            cx = 0.5 * (info["bounds"]["x_min"] + info["bounds"]["x_max"])
            cy = 0.5 * (info["bounds"]["y_min"] + info["bounds"]["y_max"])
            parts.append(_svg_text(cx, cy, name, world_to_px, fill=colors[name], font_size="11", text_anchor="middle", font_family="Segoe UI, sans-serif"))
        for name, info in scene["planner_compartments"].items():
            parts.append(_svg_poly(info["poly"], world_to_px, fill=colors.get(name, "#888"), fill_opacity="0.18", stroke=colors.get(name, "#888"), stroke_width="2.2"))
        parts.append(_svg_poly(scene["book"]["hull_xy"], world_to_px, fill="#fab005", fill_opacity="0.85", stroke="#e67700", stroke_width="1.4"))
        parts.append(_svg_poly(rect_poly(scene["book"]["aabb"]), world_to_px, fill="none", stroke="#e67700", stroke_width="1.1", stroke_dasharray="3 3"))
        if scene.get("mug"):
            parts.append(_svg_poly(scene["mug"]["hull_xy"], world_to_px, fill="none", stroke="#868e96", stroke_width="1", stroke_dasharray="2 2"))
        if include_candidates:
            goal_comp = next(iter(scene["planner_compartments"]), None)
            style = {
                "thin_along_x": {"stroke": "#2b8a3e", "dash": "none"},
                "thin_along_y": {"stroke": "#c92a2a", "dash": "7 4"},
                "current_yaw_at_center": {"stroke": "#e67700", "dash": "2 3"},
            }
            for cand in candidates:
                if goal_comp and cand["compartment"] != goal_comp:
                    continue
                sty = style.get(cand["label"], {"stroke": "#495057", "dash": "none"})
                parts.append(
                    _svg_poly(
                        cand["poly"],
                        world_to_px,
                        fill="none",
                        stroke=sty["stroke"],
                        stroke_width="2.2",
                        stroke_dasharray=sty["dash"],
                    )
                )

    draw_panel(left_map, False)
    draw_panel(right_map, True)
    legend_y = height - 96
    legend = [
        ("caddy AABB", "#444", "6 4"),
        ("caddy collision box", "#333", "none"),
        ("book OBB now / AABB dotted", "#e67700", "none"),
        ("thin along x = FIT candidate", "#2b8a3e", "none"),
        ("thin along y", "#c92a2a", "7 4"),
        ("current yaw moved to slot center", "#e67700", "2 3"),
    ]
    for idx, (label, color, dash) in enumerate(legend):
        x = margin + (idx % 3) * 360
        y = legend_y + (idx // 3) * 22
        parts.append(f'<line x1="{x}" y1="{y}" x2="{x + 28}" y2="{y}" stroke="{color}" stroke-width="2.2" stroke-dasharray="{dash}"/>')
        parts.append(f'<text x="{x + 36}" y="{y + 4}" font-size="11" font-family="Segoe UI, sans-serif">{label}</text>')
    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--problems",
        nargs="+",
        default=[
            "remote_outputs/caddy_compartment_highdrop_20260827/tasks74_75_caddy_highdrop_gpu1_r1/cutamp_debug/solve_1787766776771_160944.problem.json",
            "remote_outputs/caddy_compartment_highdrop_20260827/tasks74_75_caddy_highdrop_gpu1_r1/cutamp_debug/solve_1787767073027_160944.problem.json",
        ],
    )
    parser.add_argument("--out-dir", default="remote_outputs/caddy_compartment_geometry_viz_20260827")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = []
    for raw in args.problems:
        path = pathlib.Path(raw)
        scene = extract_scene(path)
        cands = candidate_poses(scene)
        png = out_dir / f"{scene['problem_name']}_topdown.svg"
        plot_scene(scene, cands, png)
        scenes.append({"scene": scene, "candidates": cands, "svg": str(png)})
        print(f"wrote {png}")
        for cand in cands:
            if cand["compartment"] in scene["planner_compartments"] or cand["label"] == "thin_along_x":
                print(
                    f"  {cand['compartment']:5s} {cand['label']:22s} yaw={cand['yaw_deg']:7.1f} "
                    f"fit={cand['fits']}  clearance_cm=({cand['x_clearance_m']*100:6.2f}, {cand['y_clearance_m']*100:6.2f}) "
                    f"span_cm=({cand['span_m'][0]*100:.1f}x{cand['span_m'][1]*100:.1f})"
                )
    compact = []
    for item in scenes:
        scene = item["scene"]
        compact.append(
            {
                "problem_name": scene["problem_name"],
                "goal": scene["goal"],
                "book": scene["book"],
                "caddy": {
                    "aabb": scene["caddy"]["aabb"],
                    "aabb_size_m": scene["caddy"]["aabb_size_m"],
                    "hull_xy": scene["caddy"]["hull_xy"],
                    "parts": [{"name": p["name"], "hull_xy": p["hull_xy"], "size_m": p["size_m"]} for p in scene["caddy"]["parts"]],
                },
                "mug": scene["mug"],
                "planner_compartments": scene["planner_compartments"],
                "reconstructed_compartments": scene["reconstructed_compartments"],
                "candidates": item["candidates"],
            }
        )
    json_path = out_dir / "caddy_planner_geometry.json"
    json_path.write_text(json.dumps(compact, indent=2), encoding="utf-8")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
