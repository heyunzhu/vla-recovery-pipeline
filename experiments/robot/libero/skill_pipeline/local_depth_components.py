"""Offline four-neighbor optical-Z connectivity, without semantic verification."""
from collections import deque
import numpy as np


def depth_components(depth, valid, domain, max_jump_m):
    if (depth.ndim != 2 or valid.shape != depth.shape or domain.shape != depth.shape
            or valid.dtype != np.bool_ or domain.dtype != np.bool_):
        raise ValueError('aligned 2D boolean validity and domain required')
    if not np.isfinite(max_jump_m) or max_jump_m < 0:
        raise ValueError('finite nonnegative depth jump required')
    usable = domain & valid & np.isfinite(depth) & (depth > 0)
    labels = np.zeros(depth.shape, dtype=np.int32)
    height, width = depth.shape
    count = 0
    for y, x in zip(*np.nonzero(usable)):
        if labels[y, x]:
            continue
        count += 1
        labels[y, x] = count
        queue = deque([(y, x)])
        while queue:
            cy, cx = queue.popleft()
            z = float(depth[cy, cx])
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if (0 <= ny < height and 0 <= nx < width and usable[ny, nx] and not labels[ny, nx]
                        and abs(float(depth[ny, nx]) - z) <= max_jump_m):
                    labels[ny, nx] = count
                    queue.append((ny, nx))
    return labels


def classify_proposal_components(labels, proposal, robot_union, all_proposals):
    """Use model-derived exclusive regions as anchors; ambiguous regions unknown.

    Anchor names denote mask hypotheses, never trusted robot/object identities.
    """
    if labels.ndim != 2 or labels.dtype.kind not in 'iu' or np.any(labels < 0):
        raise ValueError('nonnegative 2D integer component labels required')
    for mask in (proposal, robot_union, all_proposals):
        if mask.shape != labels.shape or mask.dtype != np.bool_:
            raise ValueError('aligned boolean anchor masks required')
    if np.any(proposal & ~all_proposals):
        raise ValueError('proposal must belong to all proposals')
    object_ids = np.unique(labels[proposal & ~robot_union])
    robot_ids = np.unique(labels[robot_union & ~all_proposals])
    object_ids = object_ids[object_ids > 0]
    robot_ids = robot_ids[robot_ids > 0]
    object_connected = np.isin(labels, object_ids)
    robot_connected = np.isin(labels, robot_ids)
    retained = proposal & object_connected & ~robot_connected & (labels > 0)
    robot_only = proposal & robot_connected & ~object_connected & (labels > 0)
    unknown = proposal & ~retained & ~robot_only
    return retained, robot_only, unknown
