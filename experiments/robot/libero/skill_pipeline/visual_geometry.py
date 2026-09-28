"""Conservative geometric candidates derived only from RGB-D points.

A horizontal plane candidate is not automatically a table or a placement
region. Semantic binding and clearance checks belong to later perception
stages.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .rgbd_observation import RGBDObservation, unproject_world


@dataclass(frozen=True)
class WorkspaceBounds:
    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]

    def __post_init__(self) -> None:
        for axis in (self.x, self.y, self.z):
            if len(axis) != 2 or not np.isfinite(axis).all() or axis[0] >= axis[1]:
                raise ValueError("workspace bounds must be finite increasing pairs")


@dataclass(frozen=True)
class HorizontalPlaneCandidate:
    z_at_world_origin_m: float
    slope_x: float
    slope_y: float
    normal_world: tuple[float, float, float]
    visible_xy_bounds_m: tuple[tuple[float, float], tuple[float, float]]
    inlier_points: int
    rms_residual_m: float
    source: str = "rgbd_visible_points"

    def height_at(self, x: float, y: float) -> float:
        return self.slope_x * x + self.slope_y * y + self.z_at_world_origin_m


def dominant_horizontal_plane(
    observation: RGBDObservation,
    workspace: WorkspaceBounds,
    *,
    bin_width_m: float = 0.005,
    inlier_tolerance_m: float = 0.008,
    min_inliers: int = 200,
    max_slope: float = 0.15,
) -> HorizontalPlaneCandidate | None:
    """Fit the largest near-horizontal visible plane in a declared workspace.

    This intentionally returns a candidate, with measured error and observed
    bounds. It does not infer unobserved table extent or free placement area.
    """

    if bin_width_m <= 0 or inlier_tolerance_m <= 0 or min_inliers < 3 or max_slope <= 0:
        raise ValueError("plane fitting tolerances and min_inliers must be positive")
    points = unproject_world(observation)
    inside = (
        (points[:, 0] >= workspace.x[0])
        & (points[:, 0] <= workspace.x[1])
        & (points[:, 1] >= workspace.y[0])
        & (points[:, 1] <= workspace.y[1])
        & (points[:, 2] >= workspace.z[0])
        & (points[:, 2] <= workspace.z[1])
    )
    points = points[inside]
    if len(points) < min_inliers:
        return None
    bins = np.arange(workspace.z[0], workspace.z[1] + bin_width_m, bin_width_m)
    counts, edges = np.histogram(points[:, 2], bins=bins)
    if not len(counts) or counts.max() < min_inliers:
        return None
    peak = int(np.argmax(counts))
    seed_height = 0.5 * (edges[peak] + edges[peak + 1])
    candidate = points[np.abs(points[:, 2] - seed_height) <= 2 * bin_width_m]
    if len(candidate) < min_inliers:
        return None

    for _ in range(3):
        design = np.column_stack((candidate[:, 0], candidate[:, 1], np.ones(len(candidate))))
        coefficients, _, _, _ = np.linalg.lstsq(design, candidate[:, 2], rcond=None)
        slope_x, slope_y, intercept = coefficients
        if np.hypot(slope_x, slope_y) > max_slope:
            return None
        residual = points[:, 2] - (points[:, 0] * slope_x + points[:, 1] * slope_y + intercept)
        candidate = points[np.abs(residual) <= inlier_tolerance_m]
        if len(candidate) < min_inliers:
            return None

    design = np.column_stack((candidate[:, 0], candidate[:, 1], np.ones(len(candidate))))
    coefficients, _, _, _ = np.linalg.lstsq(design, candidate[:, 2], rcond=None)
    slope_x, slope_y, intercept = (float(value) for value in coefficients)
    if np.hypot(slope_x, slope_y) > max_slope:
        return None
    residual = candidate[:, 2] - design @ coefficients
    normal = np.asarray([-slope_x, -slope_y, 1.0])
    normal /= np.linalg.norm(normal)
    xy_low = np.percentile(candidate[:, :2], 2, axis=0)
    xy_high = np.percentile(candidate[:, :2], 98, axis=0)
    return HorizontalPlaneCandidate(
        z_at_world_origin_m=intercept,
        slope_x=slope_x,
        slope_y=slope_y,
        normal_world=tuple(float(value) for value in normal),
        visible_xy_bounds_m=((float(xy_low[0]), float(xy_high[0])), (float(xy_low[1]), float(xy_high[1]))),
        inlier_points=len(candidate),
        rms_residual_m=float(np.sqrt(np.mean(residual**2))),
    )
