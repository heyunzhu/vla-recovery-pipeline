from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from experiments.robot.libero.skill_pipeline.visual_heightfield import _height_bins, visible_heightfield_diagnostic
from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, BOUNDS, LANGUAGE
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff
from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds


class VisualHeightfieldTest(unittest.TestCase):
    def test_curvature_preserved_without_interpolating_hole(self):
        points = []
        for y in range(5):
            for x in range(5):
                if (x, y) == (2, 2):
                    continue
                for d in [0.2, 0.4, 0.6]:
                    points.append([x + d, y + d, 1 + 0.02 * x * x])
        arrays = _height_bins(np.asarray(points), 1.0, 3, 0.004)
        self.assertFalse(arrays["witnessed_cells"][2, 2])
        self.assertTrue(np.isnan(arrays["visible_mean_z_m"][2, 2]))
        self.assertAlmostEqual(arrays["visible_mean_z_m"][0, 4], 1.32)
        self.assertTrue(arrays["witnessed_cells"][0, 4])

    def test_local_height_jump_is_rejected_without_erasing_raw_heights(self):
        points = np.asarray([[0.1, 0.1, 1], [0.2, 0.2, 1], [0.3, 0.3, 1.1]])
        arrays = _height_bins(points, 1.0, 3, 0.004)
        self.assertFalse(arrays["witnessed_cells"][0, 0])
        self.assertAlmostEqual(arrays["visible_max_z_m"][0, 0], 1.1)

    def test_curved_goal_does_not_require_global_plane_candidate(self):
        frame, detections, _ = _sample()
        depth = frame.depth_m.copy()
        ys, xs = np.nonzero(detections[1].mask)
        depth[ys, xs] += 0.025 * ((xs - 20) / 10) ** 2
        frame = replace(frame, depth_m=depth)
        provider = RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id)
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, provider.get_admission(frame))
        result = visible_heightfield_diagnostic(frame, handoff, detections, BOUNDS,
                                              cell_m=0.035, max_cell_height_spread_m=0.01)
        self.assertGreater(result.report["witnessed_cell_count"], 0)
        self.assertGreater(np.nanmax(result.arrays["visible_mean_z_m"])
                           - np.nanmin(result.arrays["visible_mean_z_m"]), 0.01)
        self.assertFalse(result.report["planning_allowed"])

    def test_changed_mask_and_wrong_frame_rejected(self):
        frame, detections, handoff = _sample()
        altered = detections[1].mask.copy()
        altered[12, 12] = False
        with self.assertRaisesRegex(ValueError, "scene provenance"):
            visible_heightfield_diagnostic(frame, handoff,
                                           [detections[0], replace(detections[1], mask=altered)], BOUNDS)
        with self.assertRaisesRegex(ValueError, "RGB-D frame"):
            visible_heightfield_diagnostic(replace(frame, env_step=1), handoff, detections, BOUNDS)

    def test_outside_workspace_and_no_depth_refuse(self):
        frame, detections, handoff = _sample()
        outside = WorkspaceBounds((-1, 1), (-1, 1), (0.8, 0.9))
        self.assertEqual(visible_heightfield_diagnostic(frame, handoff, detections, outside).report["reason"],
                         "goal_depth_insufficient")
        frame = replace(frame, depth_valid=np.zeros_like(frame.depth_valid))
        result = visible_heightfield_diagnostic(frame, handoff, detections, BOUNDS)
        self.assertEqual(result.report["reason"], "goal_depth_insufficient")
        self.assertEqual(result.arrays, {})


if __name__ == "__main__":
    unittest.main()
