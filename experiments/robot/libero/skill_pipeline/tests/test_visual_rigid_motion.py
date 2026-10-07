import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_rigid_motion import rigid_fit,robust_motion


class RigidMotionTests(unittest.TestCase):
    def test_known_rotation_translation_with_outliers(self):
        s=np.random.default_rng(11).uniform(-.05,.05,(16,3));a=np.deg2rad(15);r=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
        t=s @ r.T+[.01,.02,.035];t[-3:]+=.1
        result=robust_motion(s,t)
        self.assertTrue(result['accepted']);self.assertEqual(len(result['inlier_indices']),13)
        self.assertAlmostEqual(result['rotation_deg'],15,places=6)
        np.testing.assert_allclose(result['rotation_matrix'],r,atol=1e-10)

    def test_collinear_and_nonfinite_rejected(self):
        s=np.zeros((8,3));s[:,0]=np.arange(8)*.01
        self.assertFalse(robust_motion(s,s)['accepted'])
        with self.assertRaises(ValueError):rigid_fit(s,np.full_like(s,np.nan))

    def test_stationary_world_points_have_no_motion(self):
        s=np.random.default_rng(12).uniform(-.05,.05,(12,3));result=robust_motion(s,s)
        self.assertTrue(result['accepted']);np.testing.assert_allclose(result['centroid_displacement_m'],0,atol=1e-12)

    def test_sparse_correspondences_stay_unknown(self):
        self.assertFalse(robust_motion(np.zeros((5,3)),np.zeros((5,3)))['accepted'])
