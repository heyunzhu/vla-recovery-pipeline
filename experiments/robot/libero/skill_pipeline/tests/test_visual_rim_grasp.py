import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame
from experiments.robot.libero.skill_pipeline.visual_rim_grasp import make_visible_rim_candidate,rotation_xyzw
import dataclasses


class VisibleRimCandidateTests(unittest.TestCase):
    def test_current_high_rim_and_hand_axis(self):
        f=frame();depth=np.full((20,20),.94,np.float32);depth[[0,-1],:]=.95;depth[:,[0,-1]]=.95
        state=dict(f.robot_state,robot0_eef_pos=[0,0,1.07],robot0_eef_quat=[1,0,0,0])
        f=dataclasses.replace(f,depth_m=depth,robot_state=state)
        c=make_visible_rim_candidate(f,np.ones((20,20),bool))
        self.assertLess(c['visible_rim_anchor_world_m'][1],0)
        self.assertAlmostEqual(c['pinch_goal_world_m'][2],.9364,places=5)
        self.assertFalse(c['holding_verified']);self.assertFalse(c['contact_verified'])

    def test_non_downward_and_invalid_quaternion_rejected(self):
        with self.assertRaises(ValueError):make_visible_rim_candidate(frame(),np.ones((20,20),bool))
        with self.assertRaises(ValueError):rotation_xyzw([0,0,0,0])

    def test_xyzw_rotation_convention(self):
        np.testing.assert_allclose(rotation_xyzw([1,0,0,0]),np.diag([1,-1,-1]))


if __name__=='__main__':unittest.main()
