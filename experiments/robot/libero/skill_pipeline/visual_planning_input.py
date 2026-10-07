"""Observed geometry for planning preparation, never a legacy TAMPProblem.

The controller obtains masks from its shared provider. No guessed body pose,
full object dimensions, handempty fact or free-space certificate is emitted.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .rgbd_observation import unproject_world
from .rgbd_scene_provider import RGBDSceneProvider, _frame_digest
from .visual_geometry import WorkspaceBounds
from .visual_goal_surface import goal_surface_evidence
from .visual_skill_pack import evaluate_visual_skill_candidate
from .visual_robot_frames import base_frame_evidence
from .visual_path_diagnostic import inspect_pregrasp_path


CANARY_WORKSPACE = WorkspaceBounds((-.5, .4), (-.5, .5), (.75, 1.5))


@dataclass(frozen=True)
class VisualPlanningInput:
    report: dict
    arrays: dict[str, np.ndarray]

    def __post_init__(self):
        if self.report.get("solver_allowed") is not False or self.report.get("execution_allowed") is not False:
            raise ValueError("visual planning evidence cannot authorize a solver or execution")


def _immutable(array):
    array = np.ascontiguousarray(array, dtype=np.float64)
    return np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)


def build_visual_planning_input(frame, handoff, provider: RGBDSceneProvider, *, workspace=CANARY_WORKSPACE):
    admission = provider.get_admission(frame)  # Full content check at the shared cache boundary.
    if handoff.snapshot_id != admission.snapshot_id or handoff.task_language.strip() == "":
        raise ValueError("planning handoff snapshot mismatch")
    # Recreate provenance from the checked frame/admission, including binding and robot state.
    from .visual_recovery_handoff import build_visual_recovery_handoff
    if handoff != build_visual_recovery_handoff(handoff.task_language, frame, admission):
        raise ValueError("planning handoff evidence changed")
    report = dict(schema_version="rgbd_planning_evidence_v1", snapshot_id=handoff.snapshot_id,
                  frame_content_sha256=_frame_digest(frame).hex(), coordinate_frame="world",
                  status="refused", reason="visual_binding_unavailable", solver_allowed=False,
                  execution_allowed=False, robot_state=dict(frame.robot_state),
                  workspace_m=dataclasses.asdict(workspace), desired_goal=None, surfaces=[],
                  holding_state="unknown", goal_state="unknown", unknown_space="unclassified",
                  free_space_verified=False, observed_points_include_robot=True,
                  blockers=[*handoff.unresolved_checks, "complete_collision_geometry_unavailable",
                            "robot_base_transform_unverified", "legacy_cutamp_bridge_unavailable",
                            "rgbd_skill_pack_not_admitted", "visual_recovery_executor_missing"])
    arrays = {}
    if handoff.status != "visual_id_candidate" or admission.scene is None or handoff.binding is None:
        return VisualPlanningInput(report, arrays)
    detections = provider.get_detections(frame)
    world = np.full((*frame.depth_m.shape, 3), np.nan)
    world[frame.depth_valid] = unproject_world(frame)
    bounds = np.array([workspace.x, workspace.y, workspace.z])
    inside = frame.depth_valid & np.all((world >= bounds[:, 0]) & (world <= bounds[:, 1]), axis=-1)
    arrays["observed_world_points"] = _immutable(world[inside])
    report["observed_world_point_count"] = len(arrays["observed_world_points"])
    for obj in handoff.visible_objects:
        if obj.validity != "observed" or obj.last_seen_step != frame.env_step or obj.detection_index is None:
            continue
        mask = detections[obj.detection_index].mask
        key = obj.id + "_visible_world_points"
        points = world[mask & frame.depth_valid]
        arrays[key] = _immutable(points)
        report["surfaces"].append(dict(visual_id=obj.id, category=obj.category, array_key=key,
            point_count=len(points), mask_sha256=obj.detection_mask_sha256,
            visible_centroid_world_m=obj.visible_centroid_world_m,
            visible_bounds_world_m=obj.visible_bounds_world_m, hidden_geometry="unknown",
            object_pose="unknown", full_dimensions="unknown", role="unverified"))
    binding = handoff.binding
    report.update(status="evidence_prepared_with_gaps", reason=None,
                  desired_goal=dict(predicate=binding.goal_relation, args=[binding.target_id, binding.goal_id],
                                    source="language_bound_visual_ids", already_satisfied="unknown"),
                  goal_surface=goal_surface_evidence(frame, handoff, list(detections), workspace),
                  grasp_candidate=evaluate_visual_skill_candidate(frame, handoff, detections))
    report["blockers"] = list(dict.fromkeys(report["blockers"]))
    report['robot_frame_evidence']=base_frame_evidence(frame)
    proposal=report['grasp_candidate'].get('approach_proposal')
    if proposal is not None and proposal['status']=='unverified_waypoint_proposal':
        report['approach_path_diagnostic']=inspect_pregrasp_path(frame,proposal['proposal'])
    return VisualPlanningInput(report, arrays)


def export_visual_planning_input(evidence: VisualPlanningInput, directory):
    """Save replayable point arrays with a matching summary and artifact digest."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(root / "visible_geometry.npz", **evidence.arrays)
    report = dict(evidence.report, geometry_npz_sha256=hashlib.sha256(
        (root / "visible_geometry.npz").read_bytes()).hexdigest())
    (root / "planning_input.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
