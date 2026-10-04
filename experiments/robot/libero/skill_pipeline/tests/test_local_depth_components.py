import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.local_depth_components import depth_components, classify_proposal_components


class LocalDepthComponentsTest(unittest.TestCase):
    def test_depth_jump_separates_object_and_robot_anchor(self):
        depth = np.array([[1., 1., 2., 2.]])
        valid = np.ones_like(depth, dtype=bool)
        labels = depth_components(depth, valid, valid, .01)
        proposal = np.array([[True, True, True, False]])
        robot = np.array([[False, True, True, True]])
        kept, rejected, unknown = classify_proposal_components(labels, proposal, robot, proposal)
        self.assertEqual(kept.tolist(), [[True, True, False, False]])
        self.assertEqual(rejected.tolist(), [[False, False, True, False]])
        self.assertFalse(unknown.any())

    def test_both_anchors_and_unanchored_pixels_remain_unknown(self):
        labels = np.array([[1, 1, 1, 0, 2]], dtype=np.int32)
        proposal = np.array([[True, True, False, True, True]])
        robot = np.array([[False, True, True, True, True]])
        kept, rejected, unknown = classify_proposal_components(labels, proposal, robot, proposal)
        self.assertFalse(kept.any()); self.assertFalse(rejected.any())
        self.assertTrue(np.array_equal(unknown, proposal))

    def test_invalid_depth_and_diagonal_pixels_do_not_bridge(self):
        depth = np.array([[1., np.nan], [0., 1.]])
        valid = np.ones_like(depth, dtype=bool)
        labels = depth_components(depth, valid, valid, .01)
        self.assertEqual(labels[0, 1], 0); self.assertEqual(labels[1, 0], 0)
        self.assertNotEqual(labels[0, 0], labels[1, 1])

    def test_gradual_chain_is_connected_even_with_large_endpoint_difference(self):
        depth = np.array([[1., 1.004, 1.008, 1.012]])
        valid = np.ones_like(depth, dtype=bool)
        labels = depth_components(depth, valid, valid, .005)
        self.assertTrue(np.all(labels == 1))
        with self.assertRaises(ValueError):
            depth_components(depth, valid, valid, -1)
