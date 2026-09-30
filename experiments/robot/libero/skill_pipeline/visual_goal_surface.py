"""Visible goal surface evidence; no free-space or placement certificate."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, replace

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_observation import RGBDObservation
from .rgbd_scene import VisualDetection
from .visual_geometry import WorkspaceBounds, dominant_horizontal_plane
from .visual_recovery_handoff import VisualRecoveryHandoff


def goal_surface_evidence(
    frame: RGBDObservation,
    handoff: VisualRecoveryHandoff,
    detections: list[VisualDetection],
    workspace: WorkspaceBounds,
    *,
    erosion_pixels: int = 2,
    min_inliers: int = 200,
    inlier_tolerance_m: float = 0.002,
    max_rms_m: float = 0.001,
    min_inlier_fraction: float = 0.5,
) -> dict[str, object]:
    """Fit a plane using only the bound plate's eroded, valid depth mask.

    The reported XY rectangle bounds visible inliers. It is not a polygon
    contained in the plate and does not account for a held object's footprint.
    """
    snapshot_id = f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}"
    if handoff.snapshot_id != snapshot_id or handoff.frame_rgb_sha256 != rgb_sha256(frame):
        raise ValueError("handoff does not match the RGB-D frame")
    if (type(erosion_pixels) is not int or not 0 <= erosion_pixels <= 20
            or min_inliers < 3 or not np.isfinite([inlier_tolerance_m, max_rms_m]).all()
            or inlier_tolerance_m <= 0 or max_rms_m <= 0
            or not 0 < min_inlier_fraction <= 1):
        raise ValueError("invalid surface fitting thresholds")
    result = {
        "snapshot_id": snapshot_id, "source": "rgbd_goal_mask_visible_points",
        "status": "refused", "reason": None, "planning_allowed": False,
        "workspace_m": asdict(workspace),
        "thresholds": dict(erosion_pixels=erosion_pixels, min_inliers=min_inliers,
                           inlier_tolerance_m=inlier_tolerance_m, max_rms_m=max_rms_m,
                           min_inlier_fraction=min_inlier_fraction),
        "unresolved_checks": ["segmentation_semantics", "support_extent_and_object_footprint",
                              "obstacles_and_clearance", "grasp_and_execution"],
    }

    def refuse(reason: str) -> dict[str, object]:
        result["reason"] = reason
        return result

    if handoff.status != "visual_id_candidate" or handoff.binding is None:
        return refuse("visual_binding_unavailable")
    goal = next((item for item in handoff.visible_objects if item.id == handoff.binding.goal_id), None)
    if (goal is None or goal.validity != "observed"
            or goal.identity_status not in ("new", "tracked") or goal.last_seen_step != frame.env_step):
        return refuse("goal_not_currently_observed")
    if goal.category != "plate" or handoff.binding.goal_relation != "on":
        return refuse("unsupported_goal_surface")
    index = goal.detection_index
    if index is None or not 0 <= index < len(detections):
        return refuse("goal_mask_provenance_missing")
    detection = detections[index]
    mask = np.asarray(detection.mask)
    if mask.shape != frame.depth_m.shape:
        raise ValueError("goal mask does not align with RGB-D frame")
    digest = hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest()
    if detection.category != goal.category or digest != goal.detection_mask_sha256:
        raise ValueError("goal mask does not match scene provenance")
    result.update(goal_id=goal.id, detection_index=index, mask_sha256=digest,
                  mask_pixels=int(mask.sum()))
    interior = mask.copy()
    for _ in range(erosion_pixels):
        padded = np.pad(interior, 1, constant_values=False)
        interior = np.logical_and.reduce([
            padded[y:y + mask.shape[0], x:x + mask.shape[1]]
            for y in range(3) for x in range(3)
        ])
    valid = interior & frame.depth_valid
    result.update(interior_pixels=int(interior.sum()), valid_depth_pixels=int(valid.sum()))
    if valid.sum() < min_inliers:
        return refuse("insufficient_interior_depth")
    masked_frame = replace(frame, depth_valid=valid)
    plane = dominant_horizontal_plane(
        masked_frame, workspace, min_inliers=min_inliers,
        inlier_tolerance_m=inlier_tolerance_m,
    )
    if plane is None:
        return refuse("horizontal_plane_not_found")
    fraction = plane.inlier_points / int(valid.sum())
    result.update(plane=asdict(plane), inlier_fraction_of_valid_interior=fraction)
    if plane.rms_residual_m > max_rms_m or fraction < min_inlier_fraction:
        return refuse("plane_fit_insufficient")
    result.update(status="visible_surface_candidate", reason=None)
    return result
