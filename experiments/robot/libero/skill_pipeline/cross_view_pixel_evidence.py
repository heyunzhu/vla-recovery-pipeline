"""Per-pixel synchronized depth association without semantic or identity fusion."""
import numpy as np
from .rgbd_observation import unproject_world
from .visual_mask_depth_diagnostic import cross_view_depth_diagnostic

STATUS = {0: 'not_requested', 1: 'source_depth_invalid', 2: 'behind_destination_camera',
          3: 'outside_destination_image', 4: 'destination_depth_invalid',
          5: 'depth_consistent', 6: 'destination_surface_in_front', 7: 'destination_surface_behind'}


def project_pixel_evidence(source, mask, other, depth_tolerance_m=.005):
    # Reuse the established synchronization, calibration, proprioception and mask gate.
    aggregate = cross_view_depth_diagnostic(source, mask, other, depth_tolerance_m=depth_tolerance_m)
    xyz = np.full((*mask.shape, 3), np.nan)
    xyz[source.depth_valid] = unproject_world(source)
    sy, sx = np.nonzero(mask & source.depth_valid)
    points = xyz[sy, sx]
    camera = np.linalg.inv(other.T_world_camera) @ np.vstack((points.T, np.ones(len(points))))
    homogeneous = other.K @ camera[:3]
    front = camera[2] > 0
    uv = np.full((2, len(points)), -1, dtype=np.int32)
    uv[:, front] = np.floor(homogeneous[:2, front] / homogeneous[2, front]).astype(np.int32)
    inside = front & (uv[0] >= 0) & (uv[1] >= 0) & (uv[0] < other.rgb.shape[1]) & (uv[1] < other.rgb.shape[0])
    valid = np.zeros(len(points), dtype=bool)
    valid[inside] = other.depth_valid[uv[1, inside], uv[0, inside]]
    delta = np.full(len(points), np.nan)
    delta[valid] = other.depth_m[uv[1, valid], uv[0, valid]] - camera[2, valid]
    state = np.full(len(points), 2, dtype=np.uint8)
    state[front] = 3
    state[inside] = 4
    state[valid & (np.abs(delta) <= depth_tolerance_m)] = 5
    state[valid & (delta < -depth_tolerance_m)] = 6
    state[valid & (delta > depth_tolerance_m)] = 7
    status = np.zeros(mask.shape, dtype=np.uint8)
    status[mask] = 1
    status[sy, sx] = state
    destination_uv = np.full((*mask.shape, 2), -1, dtype=np.int32)
    destination_uv[sy, sx] = uv.T
    delta_grid = np.full(mask.shape, np.nan)
    delta_grid[sy, sx] = delta
    return dict(status=status, destination_uv=destination_uv, delta_m=delta_grid, aggregate=aggregate)
