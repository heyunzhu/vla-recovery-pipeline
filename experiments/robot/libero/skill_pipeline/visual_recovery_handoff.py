"""Conservative RGB-D evidence package for a future recovery adapter.

Visible surface centroids are not simulator object poses. This package is
diagnostic and cannot be passed to the existing oracle SceneState planner.
"""

from __future__ import annotations

from dataclasses import dataclass

from .perception_artifact import rgb_sha256
from .rgbd_observation import RGBDObservation
from .rgbd_scene import VisualObject
from .rgbd_scene_provider import VisualSceneAdmission
from .visual_task_binding import VisualTaskBinding, bind_visual_pick_place


@dataclass(frozen=True)
class VisualRecoveryHandoff:
    snapshot_id: str
    source: str
    status: str
    reason: str | None
    task_language: str
    episode_id: str
    env_step: int
    timestamp_s: float
    camera_id: str
    calibration_version: str
    frame_rgb_sha256: str
    robot_state: dict[str, object]
    perception_backend_id: str | None
    binding: VisualTaskBinding | None
    visible_objects: tuple[VisualObject, ...]
    mask_conflicts: tuple[dict[str, object], ...]
    unresolved_checks: tuple[str, ...]
    planning_allowed: bool = False

    def __post_init__(self) -> None:
        if self.planning_allowed:
            raise ValueError("diagnostic visual handoff cannot authorize planning")


def build_visual_recovery_handoff(
    language: str, frame: RGBDObservation, admission: VisualSceneAdmission,
) -> VisualRecoveryHandoff:
    """Expose observed evidence and explicit blockers without oracle fallback."""

    if not language.strip():
        raise ValueError("task language is required")
    snapshot_id = f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}"
    if admission.snapshot_id != snapshot_id:
        raise ValueError("scene admission does not match the RGB-D frame")
    common = dict(
        snapshot_id=snapshot_id, source="rgbd", task_language=language,
        episode_id=frame.episode_id, env_step=frame.env_step,
        timestamp_s=frame.timestamp_s, camera_id=frame.camera_id,
        calibration_version=frame.calibration_version,
        frame_rgb_sha256=rgb_sha256(frame), robot_state=dict(frame.robot_state),
    )
    scene = admission.scene
    if admission.status == "refused":
        if scene is not None:
            raise ValueError("refused scene admission cannot contain a scene")
        return VisualRecoveryHandoff(
            **common,
            status="scene_refused",
            reason=admission.reason,
            perception_backend_id=None,
            binding=None,
            visible_objects=(),
            mask_conflicts=admission.mask_conflicts,
            unresolved_checks=("visual_scene",),
        )
    if admission.status != "accepted" or scene is None or scene.source != "rgbd":
        raise ValueError("handoff requires an accepted RGB-D scene or explicit refusal")
    if scene.snapshot_id != admission.snapshot_id or admission.mask_conflicts:
        raise ValueError("scene admission and visual scene are inconsistent")
    if scene.timestamp_s != frame.timestamp_s or scene.camera_id != frame.camera_id:
        raise ValueError("visual scene does not match the RGB-D frame")
    binding = bind_visual_pick_place(language, scene)
    if binding.status == "refused":
        status = "binding_refused"
        reason = binding.reason
        unresolved = ("task_binding",)
    else:
        status = "visual_id_candidate"
        reason = None
        unresolved = (
            *(("target_attributes",) if binding.unverified_descriptors else ()),
            "object_geometry_and_grasp",
            "goal_region_and_clearance",
            "holding_and_goal_verification",
        )
    return VisualRecoveryHandoff(
        **common,
        status=status,
        reason=reason,
        perception_backend_id=scene.perception_backend_id,
        binding=binding,
        visible_objects=scene.objects,
        mask_conflicts=(),
        unresolved_checks=unresolved,
    )
