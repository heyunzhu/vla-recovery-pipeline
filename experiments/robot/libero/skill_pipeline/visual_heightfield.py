"""Observed height bins preserve curved surfaces; unknown bins stay unknown."""

from __future__ import annotations

import hashlib

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_observation import unproject_world
from .visual_placement_region import VisiblePlacementDiagnostic, _convex_hull, _footprint_offsets, _fit_centers


def _current_mask(frame, handoff, detections, object_id):
    obj = next((o for o in handoff.visible_objects if o.id == object_id), None)
    if (obj is None or obj.validity != "observed" or obj.last_seen_step != frame.env_step
            or obj.identity_status not in ("new", "tracked") or obj.detection_index is None
            or not 0 <= obj.detection_index < len(detections)):
        return None, None
    detection = detections[obj.detection_index]
    mask = np.asarray(detection.mask)
    if (mask.shape != frame.depth_m.shape or detection.category != obj.category
            or hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest() != obj.detection_mask_sha256):
        raise ValueError("heightfield mask does not match scene provenance")
    return obj, mask


def _height_bins(points, cell_m, min_points, max_spread_m):
    origin = np.floor(points[:, :2].min(axis=0) / cell_m) * cell_m
    xy = np.floor((points[:, :2] - origin) / cell_m).astype(int)
    nx, ny = xy.max(axis=0) + 1
    if nx * ny > 100000:
        raise ValueError("heightfield exceeds diagnostic grid size limit")
    index = xy[:, 1] * nx + xy[:, 0]
    counts = np.bincount(index, minlength=nx * ny)
    total = np.bincount(index, weights=points[:, 2], minlength=nx * ny)
    low, high = np.full(nx * ny, np.inf), np.full(nx * ny, -np.inf)
    np.minimum.at(low, index, points[:, 2])
    np.maximum.at(high, index, points[:, 2])
    witnessed = counts >= min_points
    # Limits variation within each bin, without flattening the whole surface.
    witnessed &= (high - low) <= max_spread_m
    mean = np.full(nx * ny, np.nan)
    mean[counts > 0] = total[counts > 0] / counts[counts > 0]
    low[counts == 0], high[counts == 0] = np.nan, np.nan
    return dict(origin_xy_m=origin, cell_m=np.asarray(cell_m),
                point_counts=counts.reshape(ny, nx), witnessed_cells=witnessed.reshape(ny, nx),
                visible_mean_z_m=mean.reshape(ny, nx), visible_min_z_m=low.reshape(ny, nx),
                visible_max_z_m=high.reshape(ny, nx))


def visible_heightfield_diagnostic(
    frame, handoff, detections, workspace, *, cell_m=0.003, margin_m=0.005,
    min_points_per_cell=3, max_cell_height_spread_m=0.004, erosion_pixels=2,
):
    """Compare XY containment against observed height bins, independently of a plane.

    Bin occupancy is evidence of measured points, not continuous support. A fit
    only means the translated visible hull lies in witnessed bins; it cannot
    certify contact, local normals, stability, collision clearance or execution.
    """
    if (not np.isfinite([cell_m, margin_m, max_cell_height_spread_m]).all()
            or cell_m <= 0 or margin_m < 0 or max_cell_height_spread_m <= 0
            or type(min_points_per_cell) is not int or min_points_per_cell < 1
            or type(erosion_pixels) is not int or not 0 <= erosion_pixels <= 20):
        raise ValueError("invalid heightfield diagnostic thresholds")
    snapshot_id = f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}"
    if snapshot_id != handoff.snapshot_id or handoff.frame_rgb_sha256 != rgb_sha256(frame):
        raise ValueError("heightfield handoff does not match RGB-D frame")
    report = dict(snapshot_id=snapshot_id, source="rgbd_observed_height_bins",
                  status="refused", reason=None, planning_allowed=False,
                  cell_m=cell_m, margin_m=margin_m, min_points_per_cell=min_points_per_cell,
                  max_cell_height_spread_m=max_cell_height_spread_m, erosion_pixels=erosion_pixels,
                  cell_rule="measured_points_and_local_height_spread_no_interpolation",
                  unresolved_checks=["segmentation_and_depth_edges", "continuous_surface_and_local_normals", "target_contact_footprint",
                                     "hidden_shape", "support_stability", "collision_and_execution"])
    arrays = {}

    def refuse(reason):
        report["reason"] = reason
        return VisiblePlacementDiagnostic(report, arrays)

    if handoff.status != "visual_id_candidate" or handoff.binding is None:
        return refuse("visual_binding_unavailable")
    goal, mask = _current_mask(frame, handoff, detections, handoff.binding.goal_id)
    if goal is None:
        return refuse("goal_not_currently_observed")
    if goal.category != "plate" or handoff.binding.goal_relation != "on":
        return refuse("unsupported_goal_heightfield")
    report.update(goal_id=goal.id, goal_mask_sha256=goal.detection_mask_sha256)
    interior = mask.copy()
    for _ in range(erosion_pixels):
        pad = np.pad(interior, 1, constant_values=False)
        interior = np.logical_and.reduce([pad[y:y + mask.shape[0], x:x + mask.shape[1]]
                                          for y in range(3) for x in range(3)])
    xyz = np.full((*frame.depth_m.shape, 3), np.nan)
    xyz[frame.depth_valid] = unproject_world(frame)
    good = interior & frame.depth_valid
    for axis, bounds in enumerate((workspace.x, workspace.y, workspace.z)):
        good &= (xyz[:, :, axis] >= bounds[0]) & (xyz[:, :, axis] <= bounds[1])
    points = xyz[good]
    if len(points) < 200:
        return refuse("goal_depth_insufficient")
    arrays.update(_height_bins(points, cell_m, min_points_per_cell, max_cell_height_spread_m))
    report.update(goal_valid_points=len(points), grid_shape_yx=list(arrays["witnessed_cells"].shape),
                  grid_origin_xy_m=arrays["origin_xy_m"].tolist(),
                  witnessed_cell_count=int(arrays["witnessed_cells"].sum()),
                  sparse_cell_count=int(np.count_nonzero(arrays["point_counts"] < min_points_per_cell)),
                  goal_visible_z_range_m=[float(points[:, 2].min()), float(points[:, 2].max())])
    target, mask = _current_mask(frame, handoff, detections, handoff.binding.target_id)
    if target is None:
        return refuse("target_not_currently_observed")
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        return refuse("target_mask_touches_image_boundary")
    coverage = float(np.count_nonzero(mask & frame.depth_valid) / int(mask.sum()))
    if coverage < 0.9:
        return refuse("target_depth_coverage_insufficient")
    xy = xyz[mask & frame.depth_valid, :2]
    if len(xy) < 20:
        return refuse("target_visible_points_insufficient")
    center = (xy.min(axis=0) + xy.max(axis=0)) / 2
    hull = _convex_hull(xy - center)
    if len(hull) < 3:
        return refuse("target_visible_hull_degenerate")
    offsets = _footprint_offsets(hull, cell_m, margin_m)
    fits = _fit_centers(arrays["witnessed_cells"], offsets)
    support = arrays["witnessed_cells"]
    yy, xx = np.nonzero(support)
    missing_grid = np.full(support.shape, -1, dtype=np.int32)
    if len(xx) * len(offsets) > 20000000:
        raise ValueError("heightfield shortfall search exceeds diagnostic size limit")
    missing = np.zeros(len(xx), dtype=np.int32)
    for dx, dy in offsets:
        qx, qy = xx + dx, yy + dy
        inside = (qx >= 0) & (qy >= 0) & (qx < support.shape[1]) & (qy < support.shape[0])
        witnessed = np.zeros(len(xx), dtype=bool)
        witnessed[inside] = support[qy[inside], qx[inside]]
        missing += ~witnessed
    missing_grid[yy, xx] = missing
    arrays.update(visible_hull_offsets_xy_m=hull, footprint_offsets_xy=offsets,
                  visible_footprint_fit_centers=fits, footprint_unwitnessed_cell_counts=missing_grid)
    report.update(target_id=target.id, target_mask_sha256=target.detection_mask_sha256,
                  target_depth_fraction=coverage, target_visible_xy_span_m=np.ptp(xy, axis=0).tolist(),
                  target_visible_xy_bounds_center_m=center.tolist(),
                  sampled_fit_center_count=int(fits.sum()), footprint_grid_cells=len(offsets),
                  minimum_unwitnessed_footprint_cells=int(missing.min()) if len(missing) else None)
    if not fits.any():
        return refuse("no_witnessed_visible_footprint_fit")
    report.update(status="witnessed_visible_footprint_fit", reason=None)
    return VisiblePlacementDiagnostic(report, arrays)
