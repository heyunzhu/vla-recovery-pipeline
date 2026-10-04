import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.historical_box_proposals import HistoricalBoxProposal, subtract_robot_proposal
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.tests.test_rgbd_scene import _frame


class HistoricalProposalTest(unittest.TestCase):
    def test_historical_label_cannot_be_admitted_as_current_detector_evidence(self):
        frame = _frame(0)
        proposal = HistoricalBoxProposal(np.ones(frame.depth_m.shape, dtype=bool), 'bowl', 0)
        provider = RGBDSceneProvider(lambda _: [proposal], detector_id='proposal', camera_id=frame.camera_id)
        with self.assertRaisesRegex(TypeError, 'VisualDetection'):
            provider.get_admission(frame)

    def test_proposals_cannot_set_verified_or_authorization_flags(self):
        for flag in ('category_verified', 'identity_verified', 'planning_allowed', 'execution_allowed'):
            with self.assertRaisesRegex(ValueError, 'cannot verify'):
                HistoricalBoxProposal(np.ones((3, 3), dtype=bool), 'bowl', 0, **{flag: True})

    def test_robot_subtraction_keeps_historical_status_and_drops_empty_masks(self):
        robot = np.zeros((4, 4), dtype=bool)
        robot[:2, :] = True
        source = HistoricalBoxProposal(np.ones((4, 4), dtype=bool), 'bowl', 0)
        occluded = HistoricalBoxProposal(robot.copy(), 'ramekin', 1)
        result = subtract_robot_proposal([source, occluded], robot)
        self.assertEqual(len(result), 1)
        self.assertEqual(int(result[0].mask.sum()), 8)
        self.assertEqual(int(source.mask.sum()), 16)
        self.assertFalse(result[0].category_verified)
        self.assertFalse(result[0].identity_verified)
        self.assertFalse(result[0].execution_allowed)

    def test_robot_mask_requires_aligned_boolean_pixels(self):
        source = HistoricalBoxProposal(np.ones((4, 4), dtype=bool), 'bowl', 0)
        with self.assertRaisesRegex(ValueError, 'align'):
            subtract_robot_proposal([source], np.ones((3, 3), dtype=bool))
        with self.assertRaisesRegex(ValueError, 'bool'):
            subtract_robot_proposal([source], np.ones((4, 4)))
