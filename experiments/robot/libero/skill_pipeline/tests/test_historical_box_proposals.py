import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.historical_box_proposals import HistoricalBoxProposal
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
