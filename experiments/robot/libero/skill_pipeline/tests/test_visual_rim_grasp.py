import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame
from experiments.robot.libero.skill_pipeline.visual_rim_grasp import (
    make_visible_rim_candidate,rotation_xyzw,derive_visible_rim_geometry,assess_rim_approach,
)
import dataclasses


class VisibleRimCandidateTests(unittest.TestCase):
    def sample_frame(self):
        f=frame();depth=np.full((20,20),.94,np.float32);depth[[0,-1],:]=.95;depth[:,[0,-1]]=.95
        return dataclasses.replace(f,depth_m=depth,robot_state=dict(f.robot_state,
            robot0_eef_pos=[0,0,1.07],robot0_eef_quat=[1,0,0,0]))

    def test_distant_eef_does_not_remove_geometry_and_old_canary_still_refuses(self):
        f=self.sample_frame();mask=np.ones((20,20),bool)
        original=derive_visible_rim_geometry(f,mask)
        far=dataclasses.replace(f,robot_state=dict(f.robot_state,robot0_eef_pos=[.4,0,1.07]))
        distant=derive_visible_rim_geometry(far,mask)
        self.assertEqual(original['visible_rim_anchor_world_m'],distant['visible_rim_anchor_world_m'])
        self.assertEqual(original['pinch_goal_world_m'],distant['pinch_goal_world_m'])
        result=assess_rim_approach(far,distant)
        self.assertEqual(result['failed_checks'],['current_eef_distance_exceeds_canary_limit'])
        self.assertFalse(result['execution_allowed'])
        with self.assertRaisesRegex(ValueError,'current_eef_distance'):
            make_visible_rim_candidate(far,mask)

    def test_height_and_distance_are_separate_failures(self):
        f=self.sample_frame();candidate=derive_visible_rim_geometry(f,np.ones((20,20),bool))
        candidate['pinch_goal_world_m']=[0,0,.8]
        result=assess_rim_approach(f,candidate)
        self.assertEqual(result['failed_checks'],['candidate_height_outside_canary_bounds',
                                                 'current_eef_distance_exceeds_canary_limit'])

    def test_passed_pose_gate_does_not_verify_reachability(self):
        f=self.sample_frame();candidate=derive_visible_rim_geometry(f,np.ones((20,20),bool))
        result=assess_rim_approach(f,candidate)
        self.assertEqual(result['canary_pose_gate_status'],'passed')
        self.assertEqual(result['reachability'],'unknown')
        self.assertEqual(result['path_collision'],'unknown')
        self.assertFalse(result['execution_allowed'])

    def test_stale_candidate_is_rejected_by_assessment(self):
        f=self.sample_frame();candidate=derive_visible_rim_geometry(f,np.ones((20,20),bool))
        with self.assertRaisesRegex(ValueError,'current frame'):
            assess_rim_approach(dataclasses.replace(f,env_step=f.env_step+1),candidate)

    def test_current_high_rim_and_hand_axis(self):
        f=frame();depth=np.full((20,20),.94,np.float32);depth[[0,-1],:]=.95;depth[:,[0,-1]]=.95
        state=dict(f.robot_state,robot0_eef_pos=[0,0,1.07],robot0_eef_quat=[1,0,0,0])
        f=dataclasses.replace(f,depth_m=depth,robot_state=state)
        c=make_visible_rim_candidate(f,np.ones((20,20),bool))
        self.assertEqual(c,derive_visible_rim_geometry(f,np.ones((20,20),bool)))
        self.assertLess(c['visible_rim_anchor_world_m'][1],0)
        self.assertAlmostEqual(c['pinch_goal_world_m'][2],.9364,places=5)
        self.assertFalse(c['holding_verified']);self.assertFalse(c['contact_verified'])

    def test_non_downward_and_invalid_quaternion_rejected(self):
        with self.assertRaises(ValueError):make_visible_rim_candidate(frame(),np.ones((20,20),bool))
        with self.assertRaises(ValueError):rotation_xyzw([0,0,0,0])

    def test_xyzw_rotation_convention(self):
        np.testing.assert_allclose(rotation_xyzw([1,0,0,0]),np.diag([1,-1,-1]))


if __name__=='__main__':unittest.main()
