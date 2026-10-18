"""Observed upright bowl opening and bottle-conditioned support approximation.

The circular opening is a shape prior fitted to visible rim points. Wall
collisions use observed samples only; no hidden back surface is fabricated.
"""
import numpy as np


def fit_bowl_support(world, mask, *, target_radius_m):
    points = world[np.asarray(mask, bool) & np.isfinite(world).all(axis=-1)]
    if len(points) < 300:
        raise ValueError("insufficient bowl depth")
    rim = points[points[:, 2] >= np.quantile(points[:, 2], .90)]
    fit = np.linalg.lstsq(np.c_[2 * rim[:, :2], np.ones(len(rim))],
                          np.sum(rim[:, :2] ** 2, axis=1), rcond=None)[0]
    centre = fit[:2]
    radius = float(np.sqrt(max(0., fit[2] + centre @ centre)))
    rim_error = np.abs(np.linalg.norm(rim[:, :2] - centre, axis=1) - radius)
    angles = np.arctan2(rim[:, 1]-centre[1], rim[:, 0]-centre[0])
    coverage = len(np.unique(np.floor((angles+np.pi)/(2*np.pi)*12).astype(int)))
    if not .03 < radius < .20 or np.quantile(rim_error, .95) > .004 or coverage < 9:
        raise ValueError("bowl circular opening is unresolved")
    radial = np.linalg.norm(points[:, :2]-centre, axis=1)
    central = points[radial < .25*radius]
    if len(central) < 50:
        raise ValueError("bowl interior bottom is not observed")
    floor = float(np.median(central[:, 2]))
    rim_z = float(np.quantile(rim[:, 2], .5))
    if not .01 < rim_z-floor < .15:
        raise ValueError("bowl cavity height is unresolved")
    footprint = float(target_radius_m)
    if not 0 < footprint < radius-.008:
        raise ValueError("target footprint does not fit observed bowl opening")
    # A curved bottom supports a flat bottle base at its perimeter. Measure
    # that contact band instead of treating the lowest central point as flat.
    band = points[(np.abs(radial-footprint) < .003) & (points[:, 2] > floor-.002)]
    if len(band) < 50:
        raise ValueError("bowl target contact band is not observed")
    support_z = float(np.quantile(band[:, 2], .95))
    if support_z-floor > .01 or np.quantile(band[:, 2], .95)-np.quantile(band[:, 2], .05) > .006:
        raise ValueError("bowl contact band is too steep or inconsistent")
    wall = points[(radial > footprint+.004) & (points[:, 2] > support_z+.003)]
    return dict(source="rgbd_bowl_support_patch", coordinate_frame="world",
        center_xy_world_m=centre.tolist(), support_z_world_m=support_z,
        support_radius_m=radius-.003, opening_radius_m=radius,
        rim_z_world_m=rim_z, bottom_z_world_m=floor,
        target_footprint_radius_m=footprint, rim_residual_q95_m=float(np.quantile(rim_error,.95)),
        rim_angular_bins_observed=coverage, contact_point_count=len(band),
        observed_wall_points_world_m=wall.tolist(),
        support_approximation="horizontal_contact_height_for_centered_upright_bottle",
        placement_policy="center_only", hidden_geometry="unobserved")
