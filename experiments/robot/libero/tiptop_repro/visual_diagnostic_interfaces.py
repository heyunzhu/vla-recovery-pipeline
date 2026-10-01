"""RGB-D diagnostic counterparts of cuTAMP perception and client scene reads.

These deliberately return VisualRecoveryHandoff, never legacy SceneState or
the six-item oracle perceiver tuple. They have no environment or action sink.
"""

from __future__ import annotations

from dataclasses import dataclass

from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import VisualRecoveryHandoff


@dataclass(frozen=True)
class VisualExecutionReadiness:
    snapshot_id: str
    perception_status: str
    blockers: tuple[str, ...]
    planning_allowed: bool = False
    execution_allowed: bool = False

    def __post_init__(self):
        if self.planning_allowed or self.execution_allowed or not self.blockers:
            raise ValueError("visual diagnostic readiness must refuse planning and execution")


def _validate_inputs(frame, task_description):
    if type(frame) is not RGBDObservation:
        raise TypeError("visual interfaces require RGBDObservation; no environment or oracle scene accepted")
    if not isinstance(task_description, str) or not task_description.strip():
        raise ValueError("visual interfaces require task language")


class CuTAMPVisualDiagnosticPerceiver:
    def __init__(self, adapter: VisualDryRunAdapter):
        if not isinstance(adapter, VisualDryRunAdapter):
            raise TypeError("a shared VisualDryRunAdapter is required")
        self._adapter = adapter

    def perceive(self, *, frame: RGBDObservation, task_description: str) -> VisualRecoveryHandoff:
        _validate_inputs(frame, task_description)
        return self._adapter.perceive(frame, task_description)


class VisualDiagnosticRobotClient:
    def __init__(self, adapter: VisualDryRunAdapter):
        if not isinstance(adapter, VisualDryRunAdapter):
            raise TypeError("a shared VisualDryRunAdapter is required")
        self._adapter = adapter

    def get_scene(self, *, frame: RGBDObservation, task_description: str) -> VisualRecoveryHandoff:
        _validate_inputs(frame, task_description)
        return self._adapter.executor_scene(frame, task_description)

    def check_execution_readiness(self, *, frame: RGBDObservation,
                                  task_description: str) -> VisualExecutionReadiness:
        handoff = self.get_scene(frame=frame, task_description=task_description)
        return VisualExecutionReadiness(
            snapshot_id=handoff.snapshot_id,
            perception_status=handoff.status,
            blockers=("diagnostic_mode", "legacy_scene_state_unavailable", *handoff.unresolved_checks),
        )

    def step(self, action):
        # Never read or forward an action, even when visual binding succeeds.
        raise PermissionError("visual diagnostic client forbids environment actions")
