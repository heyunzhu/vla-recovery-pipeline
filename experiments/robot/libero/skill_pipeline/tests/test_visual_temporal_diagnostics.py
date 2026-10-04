import unittest
from dataclasses import replace
import numpy as np

from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample
from experiments.robot.libero.skill_pipeline.visual_temporal_diagnostics import VisualTemporalDiagnostics


def sample(index, *, target_x=0.02, ee_x=0.02, aperture=0.02, near=True):
    frame, _, handoff = _sample()
    robot = dict(frame.robot_state)
    robot["robot0_eef_pos"] = [ee_x, 0, 1.10] if near else [0.5, 0.5, 1.2]
    robot["robot0_gripper_qpos"] = [aperture / 2, aperture / 2]
    frame = replace(frame, env_step=index * 4, timestamp_s=index * 0.2, robot_state=robot)
    objects = []
    for obj in handoff.visible_objects:
        center = (target_x, 0, 1.05) if obj.id == handoff.binding.target_id else (0, 0, 1.0)
        bounds = ((target_x - 0.015, -0.015, 1.035), (target_x + 0.015, 0.015, 1.065)) if obj.id == handoff.binding.target_id else ((-0.1, -0.1, 0.995), (0.1, 0.1, 1.005))
        objects.append(replace(obj, last_seen_step=frame.env_step, identity_status="new" if index == 0 else "tracked",
                               visible_centroid_world_m=center, visible_bounds_world_m=bounds))
    snapshot = f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}"
    handoff = replace(handoff, snapshot_id=snapshot, env_step=frame.env_step,
                      timestamp_s=frame.timestamp_s, robot_state=robot, visible_objects=tuple(objects),
                      binding=replace(handoff.binding, snapshot_id=snapshot))
    return frame, handoff


class VisualTemporalDiagnosticsTest(unittest.TestCase):
    def test_following_needs_two_intervals_and_never_verifies_contact(self):
        temporal = VisualTemporalDiagnostics()
        for index in range(3):
            result = temporal.observe(*sample(index, target_x=0.02 + index * 0.02, ee_x=0.02 + index * 0.02))
        self.assertEqual(result["holding"]["status"], "holding_motion_candidate")
        self.assertEqual(result["holding"]["consecutive_following_intervals"], 2)
        self.assertFalse(result["holding_verified"])
        self.assertFalse(result["goal_verified"])
        self.assertFalse(result["planning_allowed"])

    def test_static_target_with_moving_closed_hand_disconfirms_motion(self):
        temporal = VisualTemporalDiagnostics()
        temporal.observe(*sample(0))
        result = temporal.observe(*sample(1, ee_x=0.04))
        self.assertEqual(result["holding"]["status"], "motion_not_consistent_with_holding")

    def test_stationary_closed_hand_or_open_fingers_do_not_prove_holding(self):
        for aperture, reason in ((0.02, "insufficient_hand_motion"), (0.06, "gripper_not_consistently_closed")):
            temporal = VisualTemporalDiagnostics()
            temporal.observe(*sample(0, aperture=aperture))
            result = temporal.observe(*sample(1, aperture=aperture))
            self.assertEqual(result["holding"]["reason"], reason)

    def test_stable_open_release_only_produces_goal_proximity_candidate(self):
        temporal = VisualTemporalDiagnostics()
        for index in range(3):
            result = temporal.observe(*sample(index, aperture=0.06, near=False))
        self.assertEqual(result["goal"]["status"], "visible_goal_proximity_candidate")
        self.assertFalse(result["goal_verified"])
        self.assertIn("support_contact_and_footprint", result["unresolved_checks"])

    def test_missing_target_breaks_motion_continuity(self):
        temporal = VisualTemporalDiagnostics()
        temporal.observe(*sample(0))
        frame, handoff = sample(1)
        missing = tuple(replace(o, validity="not_observed") if o.id == handoff.binding.target_id else o for o in handoff.visible_objects)
        result = temporal.observe(frame, replace(handoff, visible_objects=missing))
        self.assertEqual(result["holding"]["reason"], "current_binding_or_depth_unavailable")
        result = temporal.observe(*sample(2))
        self.assertEqual(result["holding"]["reason"], "first_observation")

    def test_moving_camera_or_identity_reset_cannot_accumulate(self):
        for change in ("camera", "identity"):
            temporal = VisualTemporalDiagnostics()
            temporal.observe(*sample(0))
            frame, handoff = sample(1)
            if change == "camera":
                transform = frame.T_world_camera.copy()
                transform[0, 3] += 0.01
                frame = replace(frame, T_world_camera=transform)
            else:
                handoff = replace(handoff, visible_objects=tuple(replace(o, identity_status="new") for o in handoff.visible_objects))
            result = temporal.observe(frame, handoff)
            self.assertEqual(result["holding"]["reason"], "identity_camera_calibration_or_time_discontinuity")

    def test_cached_frame_is_immutable_and_mutated_depth_rejected(self):
        temporal = VisualTemporalDiagnostics()
        frame, handoff = sample(0)
        result = temporal.observe(frame, handoff)
        result["holding"]["reason"] = "tampered"
        self.assertEqual(temporal.observe(frame, handoff)["holding"]["reason"], "first_observation")
        depth = frame.depth_m.copy()
        depth[0, 0] += 0.01
        with self.assertRaisesRegex(ValueError, "changed for cached"):
            temporal.observe(replace(frame, depth_m=depth), handoff)

    def test_wrong_provenance_or_changed_episode_rejected(self):
        frame, handoff = sample(0)
        temporal = VisualTemporalDiagnostics()
        with self.assertRaisesRegex(ValueError, "does not match"):
            temporal.observe(frame, replace(handoff, timestamp_s=0.01))
        temporal.observe(frame, handoff)
        frame, handoff = sample(1)
        frame = replace(frame, episode_id="other")
        handoff = replace(handoff, episode_id="other", snapshot_id="other:step4:agentview")
        with self.assertRaisesRegex(ValueError, "reset temporal"):
            temporal.observe(frame, handoff)


if __name__ == "__main__":
    unittest.main()
