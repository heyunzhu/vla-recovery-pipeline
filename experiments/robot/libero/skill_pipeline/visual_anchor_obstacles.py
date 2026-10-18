"""Observed collision boxes for the table-top anchor; no hidden-volume claim."""
import numpy as np
from .rgbd_observation import unproject_world
from .visual_robot_frames import infer_world_from_base
from .visual_tamp_adapter import occupied_point_boxes


def observed_anchor_obstacles(frame, excluded_mask, robot_pixels, *, bottle_model=None, bottle_mask=None,
                              labeled_mask=None, debug_masks=None):
    if labeled_mask is not None:
        labeled_mask = np.asarray(labeled_mask, bool)
        if labeled_mask.shape != frame.depth_m.shape:
            raise ValueError('labeled mask must align with current depth')
    world = np.full((*frame.depth_m.shape, 3), np.nan)
    world[frame.depth_valid] = unproject_world(frame)
    ownership_extra = np.zeros(frame.depth_m.shape, bool)
    if bottle_model is not None:
        from scipy.ndimage import binary_dilation
        # A two-pixel image neighborhood includes diagonal offsets. SciPy's
        # default cross structuring element instead uses Manhattan distance
        # and can leave a (2, 1) cap pixel as a static obstacle against itself.
        # The anchor's original margin was specified at native 256 resolution.
        # Preserve its image-space angular extent when rendering the same FoV
        # at 640; the measured 3D volume gate below remains unchanged.
        radius_y=max(2,int(np.ceil(2*frame.depth_m.shape[0]/256)))
        radius_x=max(2,int(np.ceil(2*frame.depth_m.shape[1]/256)))
        boundary = binary_dilation(bottle_mask, structure=np.ones((2*radius_y+1,2*radius_x+1),bool)) & ~excluded_mask
        radial = np.linalg.norm(world[..., :2]-bottle_model['axis_xy_world_m'], axis=-1)
        for part in bottle_model['parts']:
            ownership_extra |= (boundary & frame.depth_valid
                & (radial <= part['radius_m']+.002)
                & (world[..., 2] >= part['z_min_m']-.002)
                & (world[..., 2] <= part['z_max_m']+.002))
        excluded_mask = excluded_mask | ownership_extra
    base_from_world = np.linalg.inv(infer_world_from_base(frame))
    points = world @ base_from_world[:3, :3].T + base_from_world[:3, 3]
    crop = (frame.depth_valid & (points[..., 0] > -.05) & (points[..., 0] < 1.05)
            & (np.abs(points[..., 1]) < .65) & (points[..., 2] > -.12)
            & (points[..., 2] < .65))
    table_points = points[crop & ~robot_pixels.mask & ~excluded_mask]
    heights = table_points[:, 2]
    edges = np.arange(-.12, .052, .002)
    hist, _ = np.histogram(heights, edges)
    peak = int(hist.argmax())
    near_plane = np.abs(heights - (edges[peak] + .001)) < .003
    if int(near_plane.sum()) < 500:
        raise ValueError('insufficient observed horizontal table support')
    table_z = float(np.median(heights[near_plane]))
    table_xy = table_points[near_plane, :2]
    if np.any(np.ptp(table_xy, axis=0) < .2):
        raise ValueError('observed table patch too small')
    eligible = crop & ~robot_pixels.mask & ~excluded_mask & (points[..., 2] > table_z + .003)
    ignored = eligible & ~labeled_mask if labeled_mask is not None else np.zeros_like(eligible)
    retained = eligible & ~ignored
    if debug_masks is not None:
        debug_masks.update(retained_obstacle_pixels=retained, ignored_unlabeled_pixels=ignored,
                           target_boundary_ownership_pixels=ownership_extra)
    residual = points[retained]
    centres, halves, counts = occupied_point_boxes(residual, voxel_size_m=.03,
                                                   padding_m=0, max_voxels=2500)
    # Give thin observed surface samples a small numerical collision thickness.
    halves = np.maximum(halves + .002, .002)
    return dict(source='rgbd_observed_anchor_obstacles', coordinate_frame='robot_base',
                snapshot_id=f'{frame.episode_id}:step{frame.env_step}:{frame.camera_id}',
                table_z=table_z, table_xy_min=table_xy.min(0).tolist(),
                table_xy_max=table_xy.max(0).tolist(), table_plane_points=int(near_plane.sum()),
                centres=centres.tolist(), half_extents=halves.tolist(), counts=counts.tolist(),
                residual_point_count=len(residual), robot_pixel_count=int(robot_pixels.mask.sum()),
                obstacle_policy='labeled_masks_only' if labeled_mask is not None else 'all_observed_depth',
                eligible_residual_point_count=int(eligible.sum()),
                ignored_unlabeled_point_count=int(ignored.sum()),
                target_boundary_ownership_extra_pixels=int(ownership_extra.sum()),
                target_boundary_ownership_rule='resolution_scaled_chebyshev_neighborhood_and_fitted_volume_with_2mm_margin',
                target_boundary_reference_resolution=256,
                target_boundary_radius_xy_px=[radius_x,radius_y] if bottle_model is not None else None,
                robot_pixels_report=robot_pixels.report, voxel_size_m=.03, padding_m=.002,
                workspace_crop_base_m=[[-.05,1.05],[-.65,.65],[-.12,.65]],
                hidden_geometry='unobserved', full_scene_coverage_verified=False)
