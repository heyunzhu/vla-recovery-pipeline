import unittest
import numpy as np
from scipy.spatial import cKDTree
from experiments.robot.libero.skill_pipeline.robot_surface_ownership import sampled_triangle_surfaces


class RobotSurfaceOwnershipTest(unittest.TestCase):
    def test_samples_stay_on_triangle_and_do_not_own_separate_surface(self):
        triangle=np.array([[[0.,0.,0.],[.03,0.,0.],[0.,.03,0.]]])
        samples=sampled_triangle_surfaces(triangle)
        self.assertTrue(np.all(samples[:,2]==0))
        self.assertTrue(np.all(samples[:,:2]>=0))
        self.assertTrue(np.all(samples[:,:2].sum(1)<=.03+1e-12))
        distances,_=cKDTree(samples).query([[.01,.01,0],[.01,.01,.01]])
        self.assertLess(distances[0],.003)
        self.assertGreater(distances[1],.005)
