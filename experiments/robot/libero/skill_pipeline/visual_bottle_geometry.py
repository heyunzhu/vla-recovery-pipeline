"""Upright bottle shape prior fitted to RGB-D only, with explicit uncertainty.

This is a diagnostic model, not a certificate of unseen collision geometry.
No simulator state or object assets are accepted by this module.
"""
from __future__ import annotations
import numpy as np


def connected_depth_surface(world, mask, max_neighbor_distance_m=.01):
    mask = np.asarray(mask, bool) & np.isfinite(world).all(axis=-1)
    visited = np.zeros(mask.shape, bool)
    components = []
    height, width = mask.shape
    for y, x in np.argwhere(mask):
        if visited[y, x]:
            continue
        visited[y, x] = True
        stack, component = [(int(y), int(x))], []
        while stack:
            a, b = stack.pop()
            component.append((a, b))
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                c, d = a + dy, b + dx
                if (0 <= c < height and 0 <= d < width and mask[c, d]
                        and not visited[c, d]
                        and np.linalg.norm(world[c, d] - world[a, b]) <= max_neighbor_distance_m):
                    visited[c, d] = True
                    stack.append((c, d))
        components.append(component)
    if not components:
        raise ValueError("no finite bottle depth")
    retained = np.zeros(mask.shape, bool)
    pixels = np.asarray(max(components, key=len))
    retained[pixels[:, 0], pixels[:, 1]] = True
    return retained, sorted((len(c) for c in components), reverse=True)


def _circle(xy):
    from scipy.optimize import least_squares
    centre = np.median(xy, axis=0)
    fits = []
    for offset in ((0, 0), (-.025, 0), (.025, 0)):
        fit = least_squares(
            lambda v: np.linalg.norm(xy - v[:2], axis=1) - v[2],
            [*(centre + offset), .025], bounds=([-2, -2, .005], [2, 2, .08]),
            loss="soft_l1", f_scale=.001, max_nfev=250,
        )
        fits.append(fit)
    return min(fits, key=lambda f: f.cost)


def fit_upright_bottle(world, mask):
    retained, sizes = connected_depth_surface(world, mask)
    points = world[retained]
    if len(points) < 100 or len(points) < .65 * np.count_nonzero(mask):
        raise ValueError("insufficient coherent bottle surface")
    bottom, top = float(points[:, 2].min()), float(points[:, 2].max())
    height = top - bottom
    if not .04 < height < .5:
        raise ValueError("unsupported bottle height")
    body = points[points[:, 2] <= bottom + .5 * height]
    fit = _circle(body[:, :2])
    centre, radius = fit.x[:2], float(fit.x[2])
    residuals = np.abs(fit.fun)
    alternate = _circle(points[points[:, 2] <= bottom + .6 * height, :2])
    rng = np.random.default_rng(0)
    bootstrap = np.array([_circle(body[rng.integers(len(body), size=len(body)), :2]).x for _ in range(12)])
    if (radius >= .079 or np.median(residuals) > .003 or np.quantile(residuals, .95) > .008
            or abs(alternate.x[2] - radius) > .005 or bootstrap[:, 2].std() > .005):
        raise ValueError("bottle curvature is insufficient or unstable")
    # Find a narrower upper section. Both sections share a vertical symmetry
    # axis; this is an explicit upright/axisymmetric prior, not measured yaw.
    bins = np.linspace(bottom, top, 13)
    profile = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        layer = points[(points[:, 2] >= lo) & (points[:, 2] <= hi)]
        if len(layer) >= 3:
            radial = np.linalg.norm(layer[:, :2] - centre, axis=1)
            profile.append(dict(z_min_m=float(lo), z_max_m=float(hi),
                                radius_median_m=float(np.median(radial)),
                                radius_q95_m=float(np.quantile(radial, .95))))
    narrow = [p for p in profile if p["z_min_m"] > bottom + .55 * height
              and p["radius_median_m"] < .7 * radius]
    shoulder = narrow[0]["z_min_m"] if narrow else top
    neck_points = points[points[:, 2] >= shoulder]
    neck_radius = min(radius, max(.003, float(np.quantile(np.linalg.norm(neck_points[:, :2] - centre, axis=1), .95))))
    parts = [dict(shape="cylinder", radius_m=radius, z_min_m=bottom, z_max_m=shoulder)]
    if shoulder < top:
        parts.append(dict(shape="cylinder", radius_m=neck_radius, z_min_m=shoulder, z_max_m=top))
    model = dict(schema_version=1, source="rgbd_upright_bottle_fit", coordinate_frame="world",
                 shape_prior="upright_axisymmetric_body_and_neck", yaw="unobserved_symmetry",
                 axis_xy_world_m=centre.tolist(), bottom_z_world_m=bottom, top_z_world_m=top,
                 body_radius_m=radius, height_m=height, parts=parts,
                 raw_point_count=int(np.count_nonzero(mask)), retained_point_count=len(points),
                 component_sizes=sizes, neighbor_distance_threshold_m=.01,
                 residual_median_m=float(np.median(residuals)), residual_q95_m=float(np.quantile(residuals, .95)),
                 bootstrap_parameter_std_m=bootstrap.std(axis=0).tolist(),
                 alternate_lower_60_percent_fit=alternate.x.tolist(), radial_height_profile=profile,
                 hidden_geometry="inferred_under_shape_prior_not_verified",
                 bottom_uncertainty="lowest_visible_point_not_independently_measured_support_plane")
    return model, retained
