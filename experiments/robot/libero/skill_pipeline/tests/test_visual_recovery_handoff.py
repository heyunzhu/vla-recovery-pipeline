from __future__ import annotations

import unittest
from dataclasses import replace

from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import VisualSceneAdmission
from experiments.robot.libero.skill_pipeline.tests.test_rgbd_scene_provider import _frame
from experiments.robot.libero.skill_pipeline.tests.test_visual_task_binding import LANGUAGE, _object, _scene
from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff


class VisualRecoveryHandoffTest(unittest.TestCase):
    def test_candidate_keeps_visible_geometry_and_unresolved_checks(self) -> None:
        frame = _frame(0, episode="episode")
        scene = _scene(
            _object("obj_001", "bowl", -0.20, 0.33),
            _object("obj_002", "bowl", -0.08, 0.20),
            _object("obj_003", "plate", 0.05, 0.20),
            _object("obj_004", "ramekin", -0.20, 0.19),
        )
        admission = VisualSceneAdmission(scene.snapshot_id, "accepted", None, scene)
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, admission)
        self.assertEqual(handoff.status, "visual_id_candidate")
        self.assertEqual(handoff.binding.target_id, "obj_002")
        self.assertEqual(handoff.perception_backend_id, "test_detector")
        self.assertEqual(handoff.visible_objects[1].visible_centroid_world_m, (-0.08, 0.20, 1.0))
        self.assertIn("target_attributes", handoff.unresolved_checks)
        self.assertIn("goal_region_and_clearance", handoff.unresolved_checks)
        self.assertFalse(handoff.planning_allowed)
        self.assertEqual(handoff.robot_state["robot0_eef_pos"], [0.0, 0.0, 0.0])
        with self.assertRaisesRegex(ValueError, "cannot authorize planning"):
            replace(handoff, planning_allowed=True)

    def test_scene_and_binding_refusals_do_not_expose_actionable_target(self) -> None:
        frame = _frame(0, episode="episode")
        refused = VisualSceneAdmission(
            "episode:step0:agentview", "refused", "overlapping_instance_masks", None,
            ({"first_index": 0, "second_index": 1},),
        )
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, refused)
        self.assertEqual(handoff.status, "scene_refused")
        self.assertIsNone(handoff.binding)
        self.assertEqual(handoff.visible_objects, ())
        self.assertFalse(handoff.planning_allowed)

        scene = _scene(_object("obj_001", "bowl", -0.08, 0.20))
        accepted = VisualSceneAdmission(scene.snapshot_id, "accepted", None, scene)
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, accepted)
        self.assertEqual(handoff.status, "binding_refused")
        self.assertEqual(handoff.reason, "goal_not_observed")
        self.assertFalse(handoff.planning_allowed)

    def test_rejects_mismatched_frame_and_nonvisual_scene(self) -> None:
        frame = _frame(0, episode="episode")
        scene = _scene(source="mujoco")
        accepted = VisualSceneAdmission(scene.snapshot_id, "accepted", None, scene)
        with self.assertRaisesRegex(ValueError, "accepted RGB-D scene"):
            build_visual_recovery_handoff(LANGUAGE, frame, accepted)
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_visual_recovery_handoff(
                LANGUAGE, _frame(1, episode="episode"),
                VisualSceneAdmission(scene.snapshot_id, "accepted", None, _scene()),
            )


if __name__ == "__main__":
    unittest.main()
