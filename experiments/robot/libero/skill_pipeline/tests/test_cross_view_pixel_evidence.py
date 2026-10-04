from dataclasses import replace
import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.tests.test_rgbd_scene import _frame
from experiments.robot.libero.skill_pipeline.cross_view_pixel_evidence import project_pixel_evidence


class CrossViewPixelEvidenceTest(unittest.TestCase):
    def test_pixel_center_projection_and_invalid_depth_status(self):
        source = _frame(0)
        valid = source.depth_valid.copy(); valid[5, 5] = False
        source = replace(source, depth_valid=valid)
        other = replace(_frame(0), camera_id='wrist')
        mask = np.zeros((32, 32), dtype=bool); mask[5, 5] = True; mask[6, 6] = True
        result = project_pixel_evidence(source, mask, other)
        self.assertEqual(result['status'][5, 5], 1)
        self.assertEqual(result['status'][6, 6], 5)
        self.assertEqual(result['destination_uv'][6, 6].tolist(), [6, 6])
        self.assertEqual(result['status'][0, 0], 0)
        self.assertFalse(result['aggregate']['identity_fused'])

    def test_occluded_source_surface_does_not_become_consistent(self):
        source = _frame(0)
        other = replace(source, camera_id='wrist', depth_m=np.full((32, 32), .3, dtype=np.float32))
        result = project_pixel_evidence(source, np.ones((32, 32), dtype=bool), other)
        self.assertTrue(np.all(result['status'] == 6))
        self.assertFalse(result['aggregate']['planning_allowed'])

    def test_unsynchronized_frame_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'synchronized'):
            project_pixel_evidence(_frame(0), np.ones((32, 32), dtype=bool), replace(_frame(1), camera_id='wrist'))
