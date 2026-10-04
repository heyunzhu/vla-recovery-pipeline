"""Numerical checks for the offline rasterizer's coordinate and depth rules."""
import unittest
import numpy as np

from scripts.recovery.skill_pipeline.probe_static_wrist_gripper import quaternion_wxyz, raster_depth


class StaticGripperProjectionTests(unittest.TestCase):
    def test_quaternion_order_and_invalid_values(self):
        np.testing.assert_allclose(quaternion_wxyz([0, 1, 0, 0]), np.diag([1, -1, -1]))
        for q in ([0, 0, 0, 0], [np.nan, 0, 0, 1], [1, 0, 0]):
            with self.assertRaises(ValueError):
                quaternion_wxyz(q)

    def test_perspective_depth_at_pixel_center(self):
        # Projected vertices (0,0), (2,0), (0,2), depths 1,2,4.
        tri = np.array([[[0, 0, 1], [4, 0, 2], [0, 8, 4]]], float)
        d, skipped = raster_depth(tri, np.eye(3), (3, 3))
        self.assertEqual(skipped, 0)
        self.assertAlmostEqual(d[0, 0], 1/(.5/1+.25/2+.25/4))
        self.assertTrue(np.isinf(d[2, 2]))

    def test_nearest_surface_independent_of_triangle_order(self):
        near = np.array([[0, 0, 1], [2, 0, 1], [0, 2, 1]], float)
        far = near*3
        for tris in ([near, far], [far, near]):
            d, _ = raster_depth(np.array(tris), np.eye(3), (2, 2))
            self.assertEqual(d[0, 0], 1)

    def test_partial_near_plane_is_excluded_and_counted(self):
        tri = np.array([[[0, 0, -1], [2, 0, 1], [0, 2, 1]]], float)
        d, skipped = raster_depth(tri, np.eye(3), (2, 2))
        self.assertEqual(skipped, 1)
        self.assertTrue(np.isinf(d).all())


if __name__ == '__main__':
    unittest.main()
