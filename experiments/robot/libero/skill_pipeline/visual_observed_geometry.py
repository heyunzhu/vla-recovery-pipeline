"""Observation-only cuboid and support estimates with explicit planning gates.

No simulator handles, object asset paths, class dimensions or truth poses are
accepted. A cuboid prior infers hidden interior; it is never certified complete.
"""
from __future__ import annotations
import itertools
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from scipy.ndimage import binary_erosion
from .rgbd_observation import unproject_world


def observed_points(frame, mask, *, erosion=1, world_from_base=None):
    mask = np.asarray(mask, bool)
    if mask.shape != frame.depth_m.shape:
        raise ValueError('mask does not match depth')
    use = binary_erosion(mask, iterations=erosion) if erosion else mask.copy()
    world = np.full((*frame.depth_m.shape, 3), np.nan)
    world[frame.depth_valid] = unproject_world(frame)
    use &= frame.depth_valid
    if world_from_base is not None:
        t = np.linalg.inv(np.asarray(world_from_base))
        base = world @ t[:3, :3].T + t[:3, 3]
        use &= ((base[..., 0] > -.05) & (base[..., 0] < 1.05)
                & (np.abs(base[..., 1]) < .65) & (base[..., 2] > -.12)
                & (base[..., 2] < .65))
    points = world[use]
    return points, dict(raw_mask_pixels=int(mask.sum()), retained_depth_pixels=len(points),
        erosion_pixels=erosion, workspace_crop_applied=world_from_base is not None)


def planes(points, *, tolerance=.0015, max_planes=8, min_points=30, trials=220):
    points = np.asarray(points, float)
    points = points[np.isfinite(points).all(axis=1)]
    rng = np.random.default_rng(19)
    remaining = np.arange(len(points)); result = []
    for _ in range(max_planes):
        if len(remaining) < min_points:
            break
        sample_ids = rng.choice(remaining, min(2500, len(remaining)), replace=False)
        sample = points[sample_ids]
        best = None; best_count = 0
        for _ in range(trials):
            a, b, c = sample[rng.choice(len(sample), 3, replace=False)]
            n = np.cross(b-a, c-a); length = np.linalg.norm(n)
            if length < 1e-8:
                continue
            n /= length; d = float(n@a)
            count = int((np.abs(sample@n-d) < tolerance).sum())
            if count > best_count:
                best_count, best = count, (n, d)
        if best is None:
            break
        n, d = best
        ids = remaining[np.abs(points[remaining]@n-d) < tolerance]
        if len(ids) < min_points:
            break
        q = points[ids]
        center = np.mean(q, axis=0)
        _, _, vh = np.linalg.svd(q-center, full_matrices=False)
        n = vh[-1]
        if n[2] < 0:
            n = -n
        d = float(n@center)
        ids = remaining[np.abs(points[remaining]@n-d) < tolerance]
        q = points[ids]
        # Do not fit a plane to an almost collinear rim or depth edge.
        spread = np.linalg.svd(q-q.mean(0), compute_uv=False)/np.sqrt(len(q))
        if spread[1] < .002:
            break
        result.append(dict(normal=n.tolist(), offset=d, count=len(ids),
            residual_q95_m=float(np.quantile(np.abs(q@n-d), .95)),
            centroid=q.mean(0).tolist(), indices=ids))
        remaining = remaining[np.abs(points[remaining]@n-d) >= tolerance]
    return result


def box_corners(center, rotation, half):
    return np.asarray(list(itertools.product((-1., 1.), repeat=3)))*half @ rotation.T + center


def fit_observed_cuboid(points, *, padding_m=.001):
    points = np.asarray(points, float)
    points = points[np.isfinite(points).all(1)]
    if len(points) < 100:
        raise ValueError('insufficient target depth: fewer than 100 points')
    # An additional close-up view can densely sample the top face without
    # adding any side observations. Do not let that erase real side evidence
    # by expressing the minimum face count as a fraction of all camera pixels.
    fits = planes(points, min_points=25, max_planes=8)
    options = []
    for a, b in itertools.combinations(fits, 2):
        u, v = np.asarray(a['normal']), np.asarray(b['normal'])
        if abs(u@v) > .15:
            continue
        v = v-u*(u@v); v /= np.linalg.norm(v)
        w = np.cross(u, v)
        r = np.column_stack((u, v, w))
        normals = np.asarray([p['normal'] for p in fits])
        axes = np.max(np.abs(normals@r), axis=0)
        covered = int((axes > .985).sum())
        local = points@r
        low, high = np.quantile(local, [.005, .995], axis=0)
        center = r@((low+high)/2); half = (high-low)/2
        distances = np.min(np.abs(np.abs((points-center)@r)-half), axis=1)
        explained = float(np.mean(distances < .003))
        options.append((covered, explained, r, center, half, distances))
    if not options:
        return dict(source='rgbd_observed_cuboid', status='unresolved', planning_allowed=False,
            reasons=['fewer_than_two_orthogonal_observed_faces'], point_count=len(points),
            plane_evidence=[{k:v for k,v in p.items() if k!='indices'} for p in fits])
    covered, explained, r, center, half, distances = max(options, key=lambda x:(x[0],x[1]))
    reasons = []
    if covered < 3:
        reasons.append('third_face_direction_unobserved')
    if np.any(2*half < .008):
        reasons.append('dimension_under_8mm_or_missing_depth_extent')
    if explained < .85 or np.quantile(distances,.95) > .004:
        reasons.append('visible_surface_inconsistent_with_cuboid')
    # Alternate sampling tests numerical stability, not hidden-face coverage.
    spans = [np.ptp(points[i::2]@r, axis=0) for i in (0,1)]
    stability = float(np.max(np.abs(spans[0]-spans[1])))
    if stability > .006:
        reasons.append('observed_extents_unstable')
    q = Rotation.from_matrix(r).as_quat()
    return dict(schema_version=1, source='rgbd_observed_cuboid',
        status='accepted' if not reasons else 'uncertain', planning_allowed=not reasons,
        reasons=reasons, center_world_m=center.tolist(), rotation_world_from_object=r.tolist(),
        quat_world_wxyz=np.r_[q[3],q[:3]].tolist(), dimensions_m=(2*half).tolist(),
        half_extents_m=half.tolist(), collision_half_extents_m=(half+padding_m).tolist(),
        padding_m=padding_m, point_count=len(points), observed_axis_directions=covered,
        explained_surface_fraction=explained, surface_residual_q95_m=float(np.quantile(distances,.95)),
        alternate_sample_extent_delta_m=stability,
        corners_world_m=box_corners(center,r,half).tolist(),
        plane_evidence=[{k:v for k,v in p.items() if k!='indices'} for p in fits],
        shape_prior='rigid_cuboid; extents_from_visible_surfaces',
        hidden_geometry='inferred_under_cuboid_prior; no completeness_certificate',
        simulator_geometry_used=False)


def fit_observed_support(points):
    points = np.asarray(points,float)
    points = points[np.isfinite(points).all(1)]
    if len(points) < 100:
        raise ValueError('insufficient support depth')
    all_planes = planes(points, max_planes=12, min_points=60)
    patches = []; inclined = []
    for plane in all_planes:
        n = np.asarray(plane['normal'])
        if n[2] < .985:
            if n[2] > .5:
                inclined.append(dict(normal=plane['normal'], offset=plane['offset'],
                    tilt_degrees=float(np.degrees(np.arccos(n[2]))),
                    count=plane['count'], centroid=plane['centroid'],
                    residual_q95_m=plane['residual_q95_m']))
            continue
        q = points[plane['indices']]
        if np.any(np.ptp(q[:,:2],axis=0) < .025):
            continue
        hull = ConvexHull(q[:,:2])
        patches.append(dict(normal=plane['normal'], offset=plane['offset'],
            support_z_world_m=float(np.median(q[:,2])),
            polygon_xy_world_m=q[hull.vertices,:2].tolist(), observed_point_count=len(q),
            plane_residual_q95_m=plane['residual_q95_m'], observed_area_m2=float(hull.volume)))
    # Distinct height levels are separate candidates, not an automatic top-shelf choice.
    patches.sort(key=lambda p:p['observed_point_count'],reverse=True)
    reasons = []
    if not patches:
        reasons.append('no_observed_near_horizontal_support_plane')
        if inclined:
            reasons.append('inclined_surfaces_observed; horizontal_support_adapter_not_applicable')
    elif len(patches)>1 and any(abs(p['support_z_world_m']-patches[0]['support_z_world_m'])>.01 for p in patches[1:]):
        reasons.append('multiple_support_levels_require_selection')
    # A hull encloses holes and unobserved gaps. This first-stage audit does
    # not yet certify a placement footprint even when a plane is observed.
    if patches:
        reasons.append('placement_footprint_coverage_not_yet_verified')
    return dict(source='rgbd_observed_support', status='candidate' if patches else 'unresolved',
        planning_allowed=False, reasons=reasons, candidates=patches,
        inclined_surfaces=inclined, adapter_scope='near_horizontal_support_only',
        plane_evidence=[{k:v for k,v in p.items() if k!='indices'} for p in all_planes],
        boundary='convex_hull_envelope_of_observed_plane; holes_not_certified',
        boundary_usable_for_placement=False,
        simulator_geometry_used=False)


def cuboid_geometry(model):
    """Produce the existing raw geometry schema without a simulator object."""
    if not model.get('planning_allowed'):
        raise ValueError('observed cuboid failed geometry quality gate')
    return dict(source='rgbd_observed_cuboid', model=model, geoms=[dict(
        name='rgbd_target_box', shape='box', type=6,
        size=model['collision_half_extents_m'], pos=model['center_world_m'],
        quat=model['quat_world_wxyz'], collision_active=True, contype=1, conaffinity=1)])
