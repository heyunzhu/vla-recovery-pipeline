"""Data-only candidate pack admission, separate from the oracle skill loader.

Only one frozen simulation prototype is supported. No dynamic code loading,
legacy profile conversion, action forwarding or online admission is provided.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_observation import RGBDObservation, unproject_world
from .visual_recovery_handoff import VisualRecoveryHandoff
from .visual_rim_grasp import derive_visible_rim_geometry, assess_rim_approach
from .visual_pregrasp_control import make_pregrasp_plan


DEFAULT_PACK = Path(__file__).resolve().parents[4] / "skill_packs/rgbd_bowl_rim_candidate_v1/pack.json"
_SELECTOR = dict(target="language_bound_visual_id", target_category="bowl", goal_category="plate", goal_relation="on")
_FRAMES = dict(anchor="rgbd_visible_surface_world", closing_axis="robot_hand_y", pad_offset="robot_hand_z")
_PARAMETERS = dict(rim_depth_offset_m=.010, pad_offset_hand_z_m=-.0036, lift_m=.040)
_REQUIRED = ["target_attributes", "segmentation_semantics", "contact_geometry", "swept_volume_and_collision",
             "holding_and_goal_verification", "visual_cutamp_problem_adapter", "visual_recovery_executor"]


def load_visual_candidate_pack(path=DEFAULT_PACK):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = dict(schema_version="rgbd_candidate_pack_v1", pack_id="rgbd_bowl_rim_candidate_v1",
                    status="candidate_only", online_enabled=False, selector=_SELECTOR,
                    generator="visible_high_rim_geometry_candidate_v2", reference_frames=_FRAMES,
                    parameters=_PARAMETERS, required_verification=_REQUIRED)
    # Fixed executable contract: unsupported settings cannot silently become metadata.
    if data != expected or data.get("online_enabled") is not False:
        raise ValueError("unsupported or unauthorized visual candidate pack configuration")
    return data


def select_visual_skill(handoff: VisualRecoveryHandoff, *, pack=None):
    if type(handoff) is not VisualRecoveryHandoff:
        raise TypeError("VisualRecoveryHandoff required")
    pack = load_visual_candidate_pack() if pack is None else pack
    # Validate caller-supplied configurations too; no flag can authorize actions.
    if pack != load_visual_candidate_pack():
        raise ValueError("unsupported visual candidate pack")
    result = dict(pack_id=pack["pack_id"], snapshot_id=handoff.snapshot_id,
                  selector_status="refused", reason=None, target_id=None, goal_id=None,
                  online_admission="refused", execution_allowed=False,
                  blockers=list(pack["required_verification"]))
    binding = handoff.binding
    if handoff.source != "rgbd" or handoff.status != "visual_id_candidate" or binding is None:
        result["reason"] = "visual_binding_unavailable"
        return result
    objects = {obj.id: obj for obj in handoff.visible_objects}
    target, goal = objects.get(binding.target_id), objects.get(binding.goal_id)
    if (binding.snapshot_id != handoff.snapshot_id or target is None or goal is None
            or target.id == goal.id or binding.goal_relation != "on"
            or target.category != "bowl" or goal.category != "plate"):
        result["reason"] = "visual_selector_not_applicable"
        return result
    if any(obj.validity != "observed" or obj.last_seen_step != handoff.env_step
           or obj.identity_status not in ("new", "tracked") or not obj.id.startswith("obj_")
           for obj in (target, goal)):
        result["reason"] = "visual_identity_not_current"
        return result
    result.update(selector_status="candidate_match", target_id=target.id, goal_id=goal.id,
                  reason="candidate_only_not_verified")
    return result


def evaluate_visual_skill_candidate(frame: RGBDObservation, handoff: VisualRecoveryHandoff, detections, *, pack=None):
    if type(frame) is not RGBDObservation:
        raise TypeError("RGBDObservation required")
    if (handoff.snapshot_id != f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}"
            or handoff.timestamp_s != frame.timestamp_s or handoff.calibration_version != frame.calibration_version
            or handoff.frame_rgb_sha256 != rgb_sha256(frame)):
        raise ValueError("visual handoff does not match candidate frame")
    if (set(handoff.robot_state) != set(frame.robot_state)
            or any(not np.array_equal(np.asarray(handoff.robot_state[key]), np.asarray(frame.robot_state[key]))
                   for key in frame.robot_state)):
        raise ValueError("robot reference frame changed since scene query")
    result = select_visual_skill(handoff, pack=pack)
    result.update(geometry_status="refused", candidate=None,
                  frame_depth_sha256=hashlib.sha256(np.ascontiguousarray(frame.depth_m).tobytes()).hexdigest())
    if result["selector_status"] != "candidate_match":
        return result
    target = next(obj for obj in handoff.visible_objects if obj.id == result["target_id"])
    index = target.detection_index
    if index is None or not 0 <= index < len(detections):
        raise ValueError("target has no current mask")
    detection = detections[index]
    mask = detection.mask
    if (detection.category != target.category or detection.source != target.mask_source
            or mask.shape != frame.depth_m.shape
            or hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest() != target.detection_mask_sha256):
        raise ValueError("target mask provenance mismatch")
    points = unproject_world(frame)[mask[frame.depth_valid]]
    if (not len(points) or target.visible_centroid_world_m is None
            or not np.allclose(np.mean(points, axis=0), target.visible_centroid_world_m, rtol=0, atol=1e-9)):
        raise ValueError("target depth geometry changed since scene query")
    try:
        candidate = derive_visible_rim_geometry(frame, mask)
    except (ValueError, KeyError) as exc:
        result["reason"] = "geometry_unavailable:" + str(exc)
        return result
    assessment = assess_rim_approach(frame, candidate)
    result.update(geometry_status="visible_rim_candidate", candidate=candidate,
                  approach_assessment=assessment,
                  reason="approach_requires_planning" if assessment['failed_checks'] else "candidate_only_not_verified")
    # A bounded translation proposal is planning input, not a collision-free path.
    try:
        proposal = make_pregrasp_plan(frame, mask)
    except (ValueError, KeyError) as exc:
        result["approach_proposal"] = dict(status="refused", reason=str(exc), execution_allowed=False)
    else:
        proposal["kind"] = "language_bound_visual_pregrasp_waypoint_proposal"
        result["approach_proposal"] = dict(status="unverified_waypoint_proposal", reason=None,
            target_id=result["target_id"], snapshot_id=handoff.snapshot_id,
            execution_allowed=False, proposal=proposal)
    return result
