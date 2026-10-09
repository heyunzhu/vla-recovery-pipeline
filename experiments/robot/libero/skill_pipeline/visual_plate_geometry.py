"""Measured interior support patch of a visually nominated shallow plate.

The patch models an observed placement area, not the unobserved full plate rim.
"""
import numpy as np


def fit_plate_support(world, mask):
    points = world[np.asarray(mask, bool) & np.isfinite(world).all(axis=-1)]
    if len(points) < 100:
        raise ValueError("insufficient plate depth")
    centre = np.median(points[:, :2], axis=0)
    radial = np.linalg.norm(points[:, :2] - centre, axis=1)
    outer = float(np.quantile(radial, .99))
    interior = points[radial < .55 * outer]
    if len(interior) < 50:
        raise ValueError("insufficient plate interior")
    design = np.c_[interior[:, :2], np.ones(len(interior))]
    plane = np.linalg.lstsq(design, interior[:, 2], rcond=None)[0]
    residual = np.abs(design @ plane - interior[:, 2])
    if np.linalg.norm(plane[:2]) > .1 or np.quantile(residual, .95) > .002:
        raise ValueError("plate support is tilted or nonplanar")
    in_plane = np.abs(np.c_[points[:, :2], np.ones(len(points))] @ plane - points[:, 2]) < .0015
    support_radius = float(np.quantile(radial[in_plane], .95))
    if not .025 < support_radius < outer:
        raise ValueError("plate support footprint unavailable")
    support_z = float(np.r_[centre, 1] @ plane)
    half = support_radius / np.sqrt(2)
    bounds = dict(x_min=float(centre[0] - half), x_max=float(centre[0] + half),
                  y_min=float(centre[1] - half), y_max=float(centre[1] + half),
                  z_min=support_z, z_max=support_z+.002, support_z=support_z,
                  source="rgbd_fitted_interior_support_patch")
    return dict(source="rgbd_plate_support_patch", coordinate_frame="world",
                center_xy_world_m=centre.tolist(), support_z_world_m=support_z,
                outer_visible_radius_m=outer, support_radius_m=support_radius,
                plane_z_coefficients=plane.tolist(), plane_residual_q95_m=float(np.quantile(residual, .95)),
                interior_point_count=len(interior), coplanar_point_count=int(in_plane.sum()),
                inner_bounds=bounds, collision_patch_thickness_m=.002,
                hidden_geometry="full_rim_not_modeled", plane_tilt_approximation="horizontal_at_measured_centre")
