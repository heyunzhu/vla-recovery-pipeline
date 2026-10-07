import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_proxy_overlap import cuboid_point_signed_distance,sphere_cuboid_penetrations


class ProxyDistanceTest(unittest.TestCase):
    def test_inside_face_edge_and_corner_distances(self):
        points=[[0,0,0],[1,0,0],[2,0,0],[2,2,0],[2,2,2]]
        np.testing.assert_allclose(cuboid_point_signed_distance(points,[0,0,0],[1,1,1]),
            [-1,0,1,np.sqrt(2),np.sqrt(3)])

    def test_sphere_touch_has_zero_penetration_and_inside_is_positive(self):
        values=sphere_cuboid_penetrations([[1.5,0,0,.5],[1.25,0,0,.5],[0,0,0,.5]],[0,0,0],[1,1,1])
        np.testing.assert_allclose(values,[0,.25,1.5])

    def test_invalid_geometry_rejected(self):
        with self.assertRaises(ValueError):cuboid_point_signed_distance([[0,0,float('nan')]],[0,0,0],[1,1,1])
        with self.assertRaises(ValueError):sphere_cuboid_penetrations([[0,0,0,-1]],[0,0,0],[1,1,1])


if __name__=='__main__':unittest.main()
