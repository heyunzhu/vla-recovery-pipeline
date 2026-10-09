"""Observed collision boxes for the table-top anchor; no hidden-volume claim."""
import numpy as np
from .rgbd_observation import unproject_world
from .visual_robot_frames import infer_world_from_base
from .visual_tamp_adapter import occupied_point_boxes


def observed_anchor_obstacles(frame, excluded_mask, robot_pixels, *, bottle_model=None, bottle_mask=None):
    world = np.full((*frame.depth_m.shape, 3), np.nan)
    world[frame.depth_valid] = unproject_world(frame)
    ownership_extra = np.zeros(frame.depth_m.shape, bool)
    if bottle_model is not None:
        from scipy.ndimage import binary_dilation
        boundary = binary_dilation(bottle_mask, iterations=2) & ~excluded_mask
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
    residual = points[crop & ~robot_pixels.mask & ~excluded_mask
                      & (points[..., 2] > table_z + .003)]
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
                target_boundary_ownership_extra_pixels=int(ownership_extra.sum()),
                target_boundary_ownership_rule='two_pixel_neighborhood_and_fitted_volume_with_2mm_margin',
                robot_pixels_report=robot_pixels.report, voxel_size_m=.03, padding_m=.002,
                workspace_crop_base_m=[[-.05,1.05],[-.65,.65],[-.12,.65]],
                hidden_geometry='unobserved', full_scene_coverage_verified=False)
