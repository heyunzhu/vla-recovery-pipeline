import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.visual_pregrasp_control import make_pregrasp_plan,translation_action


def frame(valid=True):
    return RGBDObservation(episode_id='test',env_step=10,timestamp_s=.5,camera_id='agentview',
        rgb=np.zeros((20,20,3),np.uint8),depth_m=np.ones((20,20),np.float32),depth_valid=np.full((20,20),valid,bool),
        K=np.array([[100,0,10],[0,100,10],[0,0,1]],float),T_world_camera=np.eye(4),
        robot_state={'robot0_joint_pos':[0]*7,'robot0_gripper_qpos':[.04,-.04],'robot0_eef_pos':[0,0,1.2],'robot0_eef_quat':[0,0,0,1]},calibration_version='test')


class VisualPregraspTests(unittest.TestCase):
    def test_plan_uses_current_depth_and_stages_above_visible_surface(self):
        p=make_pregrasp_plan(frame(),np.ones((20,20),bool))
        np.testing.assert_allclose(p['goal_world_m'],[0,0,1.12],atol=1e-8)
        self.assertEqual(p['waypoints_world_m'][1][2],1.2)
        for k in ('identity_verified','holding_verified','collision_free_verified','task_success_verified'):self.assertFalse(p[k])

    def test_missing_depth_and_nonvisual_inputs_are_rejected(self):
        with self.assertRaises(ValueError):make_pregrasp_plan(frame(False),np.ones((20,20),bool))
        with self.assertRaises(TypeError):make_pregrasp_plan(object(),np.ones((20,20),bool))
        with self.assertRaises(ValueError):make_pregrasp_plan(frame(),np.ones((20,20),bool),.01)

    def test_action_caps_translation_and_keeps_gripper_open(self):
        action,d=translation_action([0,0,1.2],[.1,-.1,1.05])
        np.testing.assert_allclose(action,[.2,-.2,-.2,0,0,0,-1])
        self.assertGreater(d,.008)
        with self.assertRaises(ValueError):translation_action([0,np.nan,1],[0,0,1])

    def test_feedback_stops_on_position_tolerance(self):
        xyz=np.array([.1,.1,1.2]);goal=np.array([0,0,1.12])
        for _ in range(80):
            action,d=translation_action(xyz,goal)
            if action is None:break
            xyz+=.05*action[:3]
        else:self.fail('did not converge within canary budget')
        self.assertLessEqual(np.linalg.norm(xyz-goal),.008)


if __name__=='__main__':unittest.main()
