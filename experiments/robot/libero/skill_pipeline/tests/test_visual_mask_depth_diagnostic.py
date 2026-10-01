from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from experiments.robot.libero.skill_pipeline.tests.test_rgbd_scene import _frame
from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import (
    mask_depth_diagnostic, cross_view_depth_diagnostic,
)


class MaskDepthDiagnosticTest(unittest.TestCase):
    def test_boundary_jump_reported_without_changing_mask(self):
        frame = _frame(0)
        mask = np.zeros((32, 32), dtype=bool)
        mask[8:24, 8:24] = True
        original = mask.copy()
        depth = frame.depth_m.copy()
        depth[~mask] = 0.7
        frame = replace(frame, depth_m=depth)
        result = mask_depth_diagnostic(frame, mask)
        self.assertGreater(result["boundary_depth_jump_pixels"], 0)
        self.assertEqual(result["erosion_sensitivity"][0]["valid_points"], 256)
        self.assertEqual(result["erosion_sensitivity"][1]["valid_points"], 196)
        np.testing.assert_array_equal(mask, original)
        self.assertFalse(result["planning_allowed"])
        self.assertIn("hidden_underside_and_contact", result["unresolved_checks"])

    def test_invalid_depth_and_tiny_masks_do_not_create_lower_geometry(self):
        frame = _frame(0, invalid=True)
        mask = np.ones((32, 32), dtype=bool)
        report = mask_depth_diagnostic(frame, mask)
        self.assertTrue(report["mask_touches_image_boundary"])
        self.assertNotIn("visible_xy_span_m", report["erosion_sensitivity"][0])
        mask[:] = False
        with self.assertRaisesRegex(ValueError, "nonempty"):
            mask_depth_diagnostic(frame, mask)

    def test_identical_geometry_in_distinct_camera_has_consistent_depth(self):
        source = _frame(0)
        other = replace(source, camera_id="other")
        mask = np.zeros((32, 32), dtype=bool)
        mask[8:24, 8:24] = True
        report = cross_view_depth_diagnostic(source, mask, other)
        self.assertEqual(report["source_valid_points"], 256)
        self.assertEqual(report["consistent_depth_points"], 256)
        self.assertFalse(report["identity_fused"])

    def test_depth_in_front_is_not_fused_as_target_evidence(self):
        source = _frame(0)
        other = replace(source, camera_id="other", depth_m=np.full((32, 32), 0.3, dtype=np.float32))
        mask = np.ones((32, 32), dtype=bool)
        report = cross_view_depth_diagnostic(source, mask, other)
        self.assertEqual(report["observed_depth_in_front_points"], 1024)
        self.assertEqual(report["consistent_depth_points"], 0)
        self.assertFalse(report["planning_allowed"])

    def test_unsynchronized_frames_or_robot_state_rejected(self):
        source = _frame(0)
        mask = np.ones((32, 32), dtype=bool)
        with self.assertRaisesRegex(ValueError, "synchronized"):
            cross_view_depth_diagnostic(source, mask, replace(_frame(1), camera_id="other"))
        state = dict(source.robot_state)
        state["robot0_joint_pos"] = [1.0] * 7
        with self.assertRaisesRegex(ValueError, "synchronized"):
            cross_view_depth_diagnostic(source, mask, replace(source, camera_id="other", robot_state=state))


if __name__ == "__main__":
    unittest.main()
