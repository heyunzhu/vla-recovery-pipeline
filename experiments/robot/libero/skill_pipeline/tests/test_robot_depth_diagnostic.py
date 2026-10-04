import unittest
import numpy as np
from scripts.recovery.skill_pipeline.probe_robot_depth_compatibility import depth_band, compatible_depth


class RobotDepthDiagnosticTest(unittest.TestCase):
    def test_invalid_depth_cannot_rescue_robot_overlap(self):
        depth = np.array([[1., np.nan, np.inf, -1., 1.]], dtype=np.float32)
        valid = np.array([[True, True, True, True, False]])
        self.assertEqual(compatible_depth(depth, valid, [0.9, 1.1], 0).tolist(), [[True, False, False, False, False]])

    def test_seed_statistics_exclude_invalid_values_and_require_evidence(self):
        depth = np.ones((5, 5), dtype=np.float32)
        depth[0, 0] = np.nan
        valid = np.ones_like(depth, dtype=bool)
        mask = valid.copy()
        self.assertEqual(depth_band(depth, valid, mask), [1., 1.])
        valid[:2] = False
        with self.assertRaisesRegex(ValueError, 'insufficient'):
            depth_band(depth, valid, mask)

    def test_reject_invalid_band_margin_and_validity_shape(self):
        depth = np.ones((5, 5)); valid = np.ones((5, 5), dtype=bool)
        for band, margin in [([2., 1.], 0), ([1., np.inf], 0), ([1., 2.], -1)]:
            with self.assertRaises(ValueError):
                compatible_depth(depth, valid, band, margin)
        with self.assertRaises(ValueError):
            compatible_depth(depth, valid[:2], [1., 2.], 0)
