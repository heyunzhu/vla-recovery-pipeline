import dataclasses
import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.visual_hand_aperture import inspect_box_visibility


class BoxVisibilityTest(unittest.TestCase):
    def sample(self):
        frame=RGBDObservation('episode',1,.1,'camera',np.zeros((100,100,3),np.uint8),
            np.full((100,100),2,np.float32),np.ones((100,100),bool),
            np.array([[100.,0,50],[0,100.,50],[0,0,1]]),np.eye(4),
            {'robot0_joint_pos':[0]*7,'robot0_gripper_qpos':[.04,-.04],
             'robot0_eef_pos':[0,0,1],'robot0_eef_quat':[0,0,0,1]},'test')
        t=np.eye(4);t[2,3]=1
        return frame,t,np.array([.1,.1,.1])

    def test_all_resolved_rays_free_has_no_handempty_fact(self):
        frame,t,half=self.sample();r=inspect_box_visibility(frame,t,half)
        self.assertEqual(r['status'],'resolved_box_observed_free')
        self.assertEqual(r['ray_count'],r['free_ray_count'])
        self.assertEqual(r['initial_atoms'],[])
        self.assertFalse(r['holding_verified'])

    def test_foreground_is_unknown_not_empty(self):
        frame,t,half=self.sample()
        r=inspect_box_visibility(dataclasses.replace(frame,depth_m=np.full((100,100),.5,np.float32)),t,half)
        self.assertEqual(r['status'],'unknown');self.assertEqual(r['foreground_occluded_ray_count'],r['ray_count'])

    def test_in_box_and_missing_depth_remain_unknown(self):
        frame,t,half=self.sample();depth=frame.depth_m.copy();depth[50,50]=1
        r=inspect_box_visibility(dataclasses.replace(frame,depth_m=depth),t,half)
        self.assertEqual(r['occupied_or_boundary_ray_count'],1);self.assertEqual(r['status'],'unknown')
        valid=frame.depth_valid.copy();valid[50,50]=False
        r=inspect_box_visibility(dataclasses.replace(frame,depth_valid=valid),t,half)
        self.assertEqual(r['invalid_depth_ray_count'],1);self.assertEqual(r['status'],'unknown')

    def test_off_image_and_subpixel_boxes_are_unknown(self):
        frame,t,half=self.sample();t[0,3]=.45
        self.assertEqual(inspect_box_visibility(frame,t,half)['status'],'unknown')
        frame,t,half=self.sample()
        self.assertEqual(inspect_box_visibility(frame,t,half*.001)['status'],'unknown')

    def test_rotated_box_and_bad_rotation(self):
        frame,t,half=self.sample();angle=.6
        t[:3,:3]=[[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]]
        self.assertEqual(inspect_box_visibility(frame,t,half)['status'],'resolved_box_observed_free')
        t[0,0]=2
        with self.assertRaisesRegex(ValueError,'proper oriented box'):inspect_box_visibility(frame,t,half)


if __name__=='__main__':unittest.main()
