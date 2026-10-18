import unittest
from types import SimpleNamespace
import numpy as np
from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import visible_registration_quality


class VisibleRegistrationTest(unittest.TestCase):
    def setUp(self):
        x,y=np.meshgrid(np.linspace(-.04,.04,20),np.linspace(-.02,.02,10))
        self.observed=np.c_[x.ravel(),y.ravel(),np.ones(x.size)]
        self.reference=np.r_[self.observed,self.observed+[0,0,.04]]
        self.frame=SimpleNamespace(T_world_camera=np.eye(4),K=np.array([[200,0,160],[0,200,160],[0,0,1]]),
            depth_m=np.ones((320,320)),depth_valid=np.ones((320,320),bool))

    def score(self,pose=None,observed=None):
        return visible_registration_quality(self.reference,self.observed if observed is None else observed,
            np.eye(4) if pose is None else pose,self.frame,np.eye(4))

    def test_depth_occluded_reference_does_not_invalidate_visible_surface(self):
        score=self.score();self.assertTrue(score['accepted'])
        self.assertEqual(score['visible_reference_points'],len(self.observed))

    def test_missing_foreground_is_not_explained_as_occlusion(self):
        self.frame.depth_m[:]=2
        self.assertFalse(self.score()['accepted'])

    def test_wrong_cloud_hidden_pose_and_motion_jump_are_rejected(self):
        self.assertFalse(self.score(observed=self.observed+[.1,0,0])['accepted'])
        pose=np.eye(4);pose[2,3]=.03
        self.assertFalse(self.score(pose=pose)['accepted'])
        pose=np.eye(4);pose[0,3]=.025
        self.assertFalse(self.score(pose=pose,observed=self.observed+[.025,0,0])['accepted'])


if __name__=='__main__':unittest.main()
