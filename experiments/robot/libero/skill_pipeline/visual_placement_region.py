"""Sampled containment of a visible footprint, never an execution certificate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .rgbd_observation import RGBDObservation, unproject_world
from .rgbd_scene import VisualDetection
from .visual_geometry import WorkspaceBounds
from .visual_goal_surface import goal_surface_evidence
from .visual_recovery_handoff import VisualRecoveryHandoff


@dataclass(frozen=True)
class VisiblePlacementDiagnostic:
    report: dict[str, object]
    arrays: dict[str, np.ndarray]


def _convex_hull(points: np.ndarray) -> np.ndarray:
    points = sorted(set(map(tuple, points)))
    if len(points) < 3:
        return np.asarray(points).reshape(-1, 2)

    def half(sequence):
        result = []
        for p in sequence:
            while len(result) >= 2:
                a, b = result[-2:]
                cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
                if cross > 0:
                    break
                result.pop()
            result.append(p)
        return result

    return np.asarray(half(points)[:-1] + half(points[::-1])[:-1], dtype=np.float64)


def _footprint_offsets(hull: np.ndarray, cell_m: float, margin_m: float) -> np.ndarray:
    # A circumscribed dilation includes every grid cell touching the hull.
    radius = margin_m + cell_m / np.sqrt(2)
    lo = np.floor((hull.min(axis=0) - radius) / cell_m).astype(int)
    hi = np.ceil((hull.max(axis=0) + radius) / cell_m).astype(int)
    if np.prod(hi - lo + 1) > 100000:
        raise ValueError("visible footprint grid exceeds diagnostic size limit")
    xx, yy = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
    offsets = np.column_stack((xx.ravel(), yy.ravel()))
    xy = offsets * cell_m
    keep = np.ones(len(xy), dtype=bool)
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        edge = b - a
        cross = edge[0] * (xy[:, 1] - a[1]) - edge[1] * (xy[:, 0] - a[0])
        keep &= cross >= -radius * np.linalg.norm(edge)
    return offsets[keep]


def _fit_centers(support: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Require every translated footprint cell to have surface evidence."""
    result = np.zeros_like(support)
    if (np.ptp(offsets[:, 0]) >= support.shape[1]
            or np.ptp(offsets[:, 1]) >= support.shape[0]):
        return result
    yy, xx = np.nonzero(support)
    if len(xx) * len(offsets) > 20000000:
        raise ValueError("containment search exceeds diagnostic size limit")
    keep = np.ones(len(xx), dtype=bool)
    for dx, dy in offsets:
        qx, qy = xx + dx, yy + dy
        inside = (qx >= 0) & (qy >= 0) & (qx < support.shape[1]) & (qy < support.shape[0])
        supported = np.zeros(len(xx), dtype=bool)
        supported[inside] = support[qy[inside], qx[inside]]
        keep &= supported
    result[yy[keep], xx[keep]] = True
    return result


def visible_placement_diagnostic(
    frame: RGBDObservation, handoff: VisualRecoveryHandoff,
    detections: list[VisualDetection], workspace: WorkspaceBounds,
    *, cell_m: float = 0.003, margin_m: float = 0.005,
    min_target_depth_fraction: float = 0.9,
) -> VisiblePlacementDiagnostic:
    """Translate the unrotated visible XY hull over a sampled plate surface.

    Each supported cell requires valid surface evidence at its four corners
    and centre. Unknown samples remain unsupported; no hole filling occurs.
    Hidden shape, underside contact and swept-volume clearance remain unknown.
    """
    if (not np.isfinite([cell_m, margin_m, min_target_depth_fraction]).all()
            or cell_m <= 0 or margin_m < 0 or not 0 < min_target_depth_fraction <= 1):
        raise ValueError("invalid visible placement thresholds")
    surface = goal_surface_evidence(frame, handoff, detections, workspace)
    report = {
        "snapshot_id": handoff.snapshot_id, "source": "rgbd_sampled_visible_containment",
        "status": "refused", "reason": None, "planning_allowed": False,
        "cell_m": cell_m, "margin_m": margin_m,
        "min_target_depth_fraction": min_target_depth_fraction,
        "orientation": "current_visible_xy_hull_translation_only",
        "cell_support_rule": "four_corners_and_center_valid_goal_plane_samples",
        "unresolved_checks": ["hidden_target_shape", "target_contact_footprint", "full_support_and_stability",
                              "segmentation_semantics", "swept_volume_and_collision",
                              "grasp_holding_and_execution"],
        "goal_surface_status": surface["status"],
    }
    arrays = {}

    def refuse(reason):
        report["reason"] = reason
        return VisiblePlacementDiagnostic(report, arrays)

    if surface["status"] != "visible_surface_candidate":
        return refuse("goal_surface_unavailable:" + str(surface["reason"]))
    target = next((o for o in handoff.visible_objects if o.id == handoff.binding.target_id), None)
    if (target is None or target.validity != "observed" or target.identity_status not in ("new", "tracked")
            or target.last_seen_step != frame.env_step or target.detection_index is None):
        return refuse("target_not_currently_observed")
    index = target.detection_index
    if not 0 <= index < len(detections):
        return refuse("target_mask_provenance_missing")
    detection = detections[index]
    mask = np.asarray(detection.mask)
    if (mask.shape != frame.depth_m.shape or detection.category != target.category
            or hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest() != target.detection_mask_sha256):
        raise ValueError("target mask does not match scene provenance")
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        return refuse("target_mask_touches_image_boundary")
    fraction = np.count_nonzero(mask & frame.depth_valid) / int(mask.sum())
    report.update(target_id=target.id, goal_id=surface["goal_id"],
                  target_mask_sha256=target.detection_mask_sha256,
                  goal_mask_sha256=surface["mask_sha256"], target_depth_fraction=fraction)
    if fraction < min_target_depth_fraction:
        return refuse("target_depth_coverage_insufficient")
    xyz = np.full((*frame.depth_m.shape, 3), np.nan)
    xyz[frame.depth_valid] = unproject_world(frame)
    goal_points = xyz[detections[surface["detection_index"]].mask & frame.depth_valid]
    report.update(goal_all_visible_xy_span_m=np.ptp(goal_points[:, :2], axis=0).tolist(),
                  goal_visible_z_percentile_2_98_m=np.percentile(goal_points[:, 2], [2, 98]).tolist())
    target_xy = xyz[mask & frame.depth_valid, :2]
    if len(target_xy) < 20:
        return refuse("target_visible_points_insufficient")
    center = (target_xy.min(axis=0) + target_xy.max(axis=0)) / 2
    hull = _convex_hull(target_xy - center)
    if len(hull) < 3:
        return refuse("target_visible_hull_degenerate")
    offsets = _footprint_offsets(hull, cell_m, margin_m)
    plane = surface["plane"]
    xmin, xmax = plane["visible_xy_bounds_m"][0]
    ymin, ymax = plane["visible_xy_bounds_m"][1]
    nx, ny = int(np.floor((xmax - xmin) / cell_m)), int(np.floor((ymax - ymin) / cell_m))
    if nx < 1 or ny < 1:
        return refuse("goal_visible_grid_too_small")
    if nx * ny > 100000:
        raise ValueError("goal surface grid exceeds diagnostic size limit")
    xx, yy = np.meshgrid(xmin + (np.arange(nx) + 0.5) * cell_m,
                         ymin + (np.arange(ny) + 0.5) * cell_m)
    # Reproject into the actual mask; rectangle corners never imply support.
    goal_mask = detections[surface["detection_index"]].mask.copy()
    for _ in range(surface["thresholds"]["erosion_pixels"]):
        pad = np.pad(goal_mask, 1, constant_values=False)
        goal_mask = np.logical_and.reduce([pad[y:y + goal_mask.shape[0], x:x + goal_mask.shape[1]]
                                          for y in range(3) for x in range(3)])
    residual = np.abs(xyz[:, :, 2] - (plane["slope_x"] * xyz[:, :, 0]
                      + plane["slope_y"] * xyz[:, :, 1] + plane["z_at_world_origin_m"]))
    observed = goal_mask & frame.depth_valid & (residual <= surface["thresholds"]["inlier_tolerance_m"])
    support = np.ones((ny, nx), dtype=bool)
    inv = np.linalg.inv(frame.T_world_camera)
    for dx, dy in [(0, 0), (-0.5, -0.5), (-0.5, 0.5), (0.5, -0.5), (0.5, 0.5)]:
        x, y = xx.ravel() + dx * cell_m, yy.ravel() + dy * cell_m
        z = plane["slope_x"] * x + plane["slope_y"] * y + plane["z_at_world_origin_m"]
        camera = inv @ np.vstack((x, y, z, np.ones(len(x))))
        pixel = frame.K @ camera[:3]
        valid = camera[2] > 0
        uv = np.zeros((2, len(x)), dtype=int)
        uv[:, valid] = np.floor(pixel[:2, valid] / pixel[2, valid]).astype(int)
        valid &= ((uv[0] >= 0) & (uv[1] >= 0) & (uv[0] < frame.rgb.shape[1])
                  & (uv[1] < frame.rgb.shape[0]))
        witnessed = np.zeros(len(x), dtype=bool)
        witnessed[valid] = observed[uv[1, valid], uv[0, valid]]
        support &= witnessed.reshape(ny, nx)
    fits = _fit_centers(support, offsets)
    arrays.update(support_cells=support, visible_footprint_fit_centers=fits,
                  footprint_offsets_xy=offsets, origin_xy_m=np.asarray([xmin, ymin]),
                  cell_m=np.asarray(cell_m), goal_observed_plane_mask=observed,
                  visible_hull_offsets_xy_m=hull)
    report.update(target_visible_xy_bounds_center_m=center.tolist(),
                  target_visible_xy_span_m=np.ptp(target_xy, axis=0).tolist(),
                  target_visible_hull_vertices=len(hull), footprint_grid_cells=len(offsets),
                  grid_shape_yx=[ny, nx], grid_origin_xy_m=[xmin, ymin],
                  supported_grid_cells=int(support.sum()), sampled_fit_center_count=int(fits.sum()))
    if not fits.any():
        return refuse("no_sampled_visible_footprint_fit")
    report.update(status="sampled_visible_footprint_fit", reason=None)
    return VisiblePlacementDiagnostic(report, arrays)
