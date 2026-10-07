"""Recovery admission over the shared visual snapshot.

This is a controller boundary, not a migrated cuTAMP solver. It has no
environment, policy, oracle scene or action sink. Missing planning/execution
capabilities terminate an admission trial with a structured refusal.
"""
from __future__ import annotations

from dataclasses import dataclass

from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from .visual_diagnostic_interfaces import CuTAMPVisualDiagnosticPerceiver, VisualDiagnosticRobotClient


@dataclass(frozen=True)
class VisualRecoveryAdmission:
    snapshot_id: str
    decision: str
    perception_status: str
    target_id: str | None
    goal_id: str | None
    blockers: tuple[str, ...]
    shared_snapshot_verified: bool
    recovery_actions: int = 0

    def __post_init__(self):
        if (self.decision != "refused" or not self.blockers or self.recovery_actions != 0
                or not self.shared_snapshot_verified):
            raise ValueError("admission controller cannot authorize recovery actions")


class RGBDRecoveryAdmissionController:
    def __init__(self, adapter: VisualDryRunAdapter):
        self._adapter = adapter
        self._perceiver = CuTAMPVisualDiagnosticPerceiver(adapter)
        self._client = VisualDiagnosticRobotClient(adapter)

    def recover(self, *, frame: RGBDObservation, task_description: str) -> VisualRecoveryAdmission:
        # All three reads revalidate frame contents against the provider cache.
        perceived = self._perceiver.perceive(frame=frame, task_description=task_description)
        queried = self._adapter.query_state(frame, task_description)
        execution_scene = self._client.get_scene(frame=frame, task_description=task_description)
        if perceived is not queried or execution_scene is not queried:
            raise ValueError("recovery consumers did not receive the same visual snapshot")
        binding = queried.binding
        blockers = tuple(dict.fromkeys((
            *queried.unresolved_checks,
            "visual_cutamp_problem_adapter_missing",
            "rgbd_skill_pack_not_admitted",
            "visual_recovery_executor_missing",
        )))
        return VisualRecoveryAdmission(
            snapshot_id=queried.snapshot_id, decision="refused",
            perception_status=queried.status,
            target_id=binding.target_id if binding is not None else None,
            goal_id=binding.goal_id if binding is not None else None,
            blockers=blockers, shared_snapshot_verified=True,
        )
