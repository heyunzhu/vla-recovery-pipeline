import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_bottle_tracker import BottleColorDepthTracker


class BottleTrackerTest(unittest.TestCase):
    def test_depth_motion_is_measured_and_missing_evidence_refused(self):
        angle=np.linspace(-.6,.6,15);z=np.linspace(.9,.98,30)
        points=np.zeros((30,15,3));points[:,:,0]=.2+.021*np.cos(angle)
        points[:,:,1]=.021*np.sin(angle);points[:,:,2]=z[:,None]
        rgb=np.zeros((30,15,3),np.uint8);rgb[:,:,1]=8
        state=dict(robot0_eef_pos=[.2,0,1.1],robot0_gripper_qpos=[.04,-.04])
        frame=SimpleNamespace(rgb=rgb,depth_m=np.ones((30,15)),depth_valid=np.ones((30,15),bool),
                              env_step=1,robot_state=state)
        model=dict(body_radius_m=.021,axis_xy_world_m=[.2,0],bottom_z_world_m=.9,
                   top_z_world_m=1.05,parts=[dict(radius_m=.021,z_min_m=.9,z_max_m=1.05)])
        with patch('experiments.robot.libero.skill_pipeline.visual_bottle_tracker.unproject_world',return_value=points.reshape(-1,3)):
            tracker=BottleColorDepthTracker(frame,np.ones((30,15),bool),model)
        shifted=points+np.array([.01,.02,.03]);frame.env_step=2
        with patch('experiments.robot.libero.skill_pipeline.visual_bottle_tracker.unproject_world',return_value=shifted.reshape(-1,3)):
            found,evidence=tracker.update(frame)
        np.testing.assert_allclose(found['axis_xy_world_m'],[.21,.02],atol=.0001)
        self.assertAlmostEqual(found['bottom_z_world_m'],.93,places=4)
        self.assertFalse(evidence['oracle_object_state_used'])
        frame.env_step=3;frame.rgb=np.full_like(rgb,200)
        frame.robot_state=dict(state,robot0_eef_pos=[.21,.02,1.13],robot0_gripper_qpos=[.01,-.01])
        with patch('experiments.robot.libero.skill_pipeline.visual_bottle_tracker.unproject_world',return_value=shifted.reshape(-1,3)):
            with self.assertRaisesRegex(ValueError,'unresolved'):tracker.update(frame)
