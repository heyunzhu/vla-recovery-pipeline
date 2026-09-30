from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, BOUNDS, LANGUAGE
from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff
from experiments.robot.libero.skill_pipeline.visual_placement_region import (
    _convex_hull, _footprint_offsets, _fit_centers, visible_placement_diagnostic,
)


class VisiblePlacementRegionTest(unittest.TestCase):
    def test_unknown_hole_blocks_containment_without_filling(self):
        support = np.ones((9, 9), dtype=bool)
        support[4, 4] = False
        offsets = np.asarray([(x, y) for y in (-1, 0, 1) for x in (-1, 0, 1)])
        fits = _fit_centers(support, offsets)
        self.assertFalse(fits[3:6, 3:6].any())
        self.assertFalse(fits[0].any())
        self.assertTrue(fits[2, 2])
        self.assertFalse(support[4, 4])

    def test_circular_support_does_not_become_its_bounding_rectangle(self):
        yy, xx = np.mgrid[-5:6, -5:6]
        support = xx ** 2 + yy ** 2 <= 25
        offsets = np.asarray([(x, y) for y in (-4, 0, 4) for x in (-4, 0, 4)])
        self.assertFalse(_fit_centers(support, offsets).any())
        self.assertTrue(_fit_centers(np.ones_like(support), offsets)[5, 5])

    def test_margin_and_cell_extent_expand_visible_hull(self):
        hull = _convex_hull(np.asarray([[-1, -1], [1, -1], [1, 1], [-1, 1], [0, 0]]))
        self.assertEqual(len(hull), 4)
        first = _footprint_offsets(hull, 0.5, 0)
        padded = _footprint_offsets(hull, 0.5, 0.5)
        self.assertGreater(len(padded), len(first))
        support = np.ones((25, 25), dtype=bool)
        self.assertLess(_fit_centers(support, padded).sum(), _fit_centers(support, first).sum())

    def test_real_projection_path_reports_only_sampled_fit(self):
        frame, detections, handoff = _sample()
        result = visible_placement_diagnostic(frame, handoff, detections, BOUNDS)
        self.assertEqual(result.report["status"], "sampled_visible_footprint_fit")
        self.assertGreater(result.report["sampled_fit_center_count"], 0)
        self.assertFalse(result.report["planning_allowed"])
        self.assertIn("target_contact_footprint", result.report["unresolved_checks"])
        self.assertTrue(np.all(result.arrays["visible_footprint_fit_centers"] <= result.arrays["support_cells"]))

    def test_invalid_goal_depth_remains_a_hole_in_projected_grid(self):
        frame, detections, _ = _sample()
        valid = frame.depth_valid.copy()
        valid[15:19, 17:21] = False
        frame = replace(frame, depth_valid=valid)
        provider = RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id)
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, provider.get_admission(frame))
        result = visible_placement_diagnostic(frame, handoff, detections, BOUNDS)
        support = result.arrays["support_cells"]
        self.assertFalse(support[support.shape[0] // 2, support.shape[1] // 2])
        self.assertLess(int(support.sum()), support.size)

    def test_changed_target_mask_and_partial_target_depth_refuse(self):
        frame, detections, handoff = _sample()
        mask = detections[0].mask.copy()
        mask[3, 3] = False
        changed = [replace(detections[0], mask=mask), detections[1]]
        with self.assertRaisesRegex(ValueError, "target mask"):
            visible_placement_diagnostic(frame, handoff, changed, BOUNDS)
        valid = frame.depth_valid.copy()
        valid[2:4, 2:8] = False
        frame = replace(frame, depth_valid=valid)
        provider = RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id)
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, provider.get_admission(frame))
        result = visible_placement_diagnostic(frame, handoff, detections, BOUNDS)
        self.assertEqual(result.report["reason"], "target_depth_coverage_insufficient")


if __name__ == "__main__":
    unittest.main()
