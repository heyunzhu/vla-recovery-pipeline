"""Report mask/depth boundary sensitivity and visible lower bands, not contact."""

from __future__ import annotations

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_observation import unproject_world


def _erode(mask, pixels):
    result = mask.copy()
    for _ in range(pixels):
        padded = np.pad(result, 1, constant_values=False)
        result = np.logical_and.reduce([padded[y:y + mask.shape[0], x:x + mask.shape[1]]
                                       for y in range(3) for x in range(3)])
    return result


def mask_depth_diagnostic(frame, mask, *, erosion_pixels=(0, 1, 2, 4),
                          depth_jump_m=0.015, lower_band_m=0.010):
    """Retain each erosion result; never silently replace the original mask.

    The lower band includes all points below visible Z percentile 2 plus its
    configured height, including the lower tail. It is not the underside,
    contact footprint or a grasp target, and may include background pixels.
    """
    mask = np.asarray(mask)
    if mask.dtype != np.bool_ or mask.shape != frame.depth_m.shape or not mask.any():
        raise ValueError("mask must be a nonempty aligned bool array")
    if (not np.isfinite([depth_jump_m, lower_band_m]).all()
            or depth_jump_m <= 0 or lower_band_m <= 0
            or not erosion_pixels or any(type(n) is not int or not 0 <= n <= 20 for n in erosion_pixels)):
        raise ValueError("invalid boundary diagnostic thresholds")
    xyz = np.full((*mask.shape, 3), np.nan)
    xyz[frame.depth_valid] = unproject_world(frame)
    boundary = mask & ~_erode(mask, 1) & frame.depth_valid
    jump = np.zeros_like(mask)
    for axis in (0, 1):
        a = [slice(None), slice(None)]
        b = [slice(None), slice(None)]
        a[axis], b[axis] = slice(None, -1), slice(1, None)
        a, b = tuple(a), tuple(b)
        difference = (frame.depth_valid[a] & frame.depth_valid[b]
                      & (np.abs(frame.depth_m[a] - frame.depth_m[b]) > depth_jump_m))
        jump[a] |= difference
        jump[b] |= difference
    rows = []
    for pixels in erosion_pixels:
        interior = _erode(mask, pixels)
        points = xyz[interior & frame.depth_valid]
        row = dict(erosion_pixels=pixels, mask_pixels=int(interior.sum()), valid_points=len(points))
        if len(points) >= 20:
            low, high = np.percentile(points[:, 2], [2, 98])
            band = points[points[:, 2] <= low + lower_band_m]
            row.update(visible_xy_span_m=np.ptp(points[:, :2], axis=0).tolist(),
                       visible_z_percentile_2_98_m=[float(low), float(high)],
                       lower_visible_band_anchor_z_m=float(low), lower_visible_band_points=len(band),
                       lower_visible_band_xy_span_m=np.ptp(band[:, :2], axis=0).tolist(),
                       lower_visible_band_bounds_world_m=[band.min(axis=0).tolist(), band.max(axis=0).tolist()])
        rows.append(row)
    return dict(source="rgbd_mask_boundary_and_visible_lower_band", planning_allowed=False,
                episode_id=frame.episode_id, env_step=frame.env_step, camera_id=frame.camera_id,
                rgb_sha256=rgb_sha256(frame), depth_jump_m=depth_jump_m, lower_band_m=lower_band_m,
                lower_band_rule="z_le_percentile2_plus_band_including_lower_tail",
                valid_boundary_pixels=int(boundary.sum()), boundary_depth_jump_pixels=int((boundary & jump).sum()),
                mask_touches_image_boundary=bool(mask[0].any() or mask[-1].any()
                                                or mask[:, 0].any() or mask[:, -1].any()),
                erosion_sensitivity=rows,
                unresolved_checks=["mask_semantics_and_background", "hidden_underside_and_contact",
                                   "complete_collision_geometry", "grasp_and_execution"])


def validate_synchronized_views(source, other):
    """Require distinct cameras at identical episode/time and robot state."""
    if (source.episode_id != other.episode_id or source.env_step != other.env_step
            or source.timestamp_s != other.timestamp_s or source.camera_id == other.camera_id
            or source.calibration_version != other.calibration_version
            or source.robot_state.keys() != other.robot_state.keys()
            or any(not np.array_equal(source.robot_state[k], other.robot_state[k])
                   for k in source.robot_state)):
        raise ValueError("cross-view diagnostic requires synchronized distinct cameras")


def cross_view_depth_diagnostic(source, mask, other, *, depth_tolerance_m=0.005):
    """Project source-mask points into a synchronized camera, without ID fusion."""
    validate_synchronized_views(source, other)
    if not np.isfinite(depth_tolerance_m) or depth_tolerance_m <= 0:
        raise ValueError("invalid cross-view depth tolerance")
    mask = np.asarray(mask)
    if mask.shape != source.depth_m.shape or mask.dtype != np.bool_ or not mask.any():
        raise ValueError("invalid source mask")
    xyz = np.full((*mask.shape, 3), np.nan)
    xyz[source.depth_valid] = unproject_world(source)
    points = xyz[mask & source.depth_valid]
    camera = np.linalg.inv(other.T_world_camera) @ np.vstack((points.T, np.ones(len(points))))
    pixel = other.K @ camera[:3]
    front = camera[2] > 0
    uv = np.zeros((2, len(points)), dtype=int)
    uv[:, front] = np.floor(pixel[:2, front] / pixel[2, front]).astype(int)
    inside = (front & (uv[0] >= 0) & (uv[1] >= 0)
              & (uv[0] < other.depth_m.shape[1]) & (uv[1] < other.depth_m.shape[0]))
    valid = np.zeros(len(points), dtype=bool)
    valid[inside] = other.depth_valid[uv[1, inside], uv[0, inside]]
    delta = other.depth_m[uv[1, valid], uv[0, valid]] - camera[2, valid]
    return dict(source="synchronized_rgbd_projection_only", planning_allowed=False,
                source_camera=source.camera_id, destination_camera=other.camera_id,
                env_step=source.env_step, depth_tolerance_m=depth_tolerance_m,
                source_valid_points=len(points), projected_in_image_points=int(inside.sum()),
                destination_valid_depth_points=int(valid.sum()),
                consistent_depth_points=int(np.count_nonzero(np.abs(delta) <= depth_tolerance_m)),
                observed_depth_in_front_points=int(np.count_nonzero(delta < -depth_tolerance_m)),
                observed_depth_behind_points=int(np.count_nonzero(delta > depth_tolerance_m)),
                identity_fused=False)
