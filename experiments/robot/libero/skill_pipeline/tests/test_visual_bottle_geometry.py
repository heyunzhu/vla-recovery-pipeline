import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_bottle_geometry import fit_upright_bottle


class BottleGeometryTest(unittest.TestCase):
    def test_partial_cylinder_recovers_hidden_radius_and_rejects_background(self):
        angles = np.linspace(-1.1, 1.1, 30)
        heights = np.linspace(.9, 1.06, 65)
        radii = np.interp(heights, [.9, 1.0, 1.02, 1.06], [.022, .022, .006, .006])
        world = np.empty((65, 30, 3))
        world[:, :, 0] = -.2 + radii[:, None] * np.cos(angles)
        world[:, :, 1] = .1 + radii[:, None] * np.sin(angles)
        world[:, :, 2] = heights[:, None]
        world[:2, :2] += [.3, 0, 0]
        model, retained = fit_upright_bottle(world, np.ones(world.shape[:2], bool))
        self.assertFalse(retained[0, 0])
        np.testing.assert_allclose(model['axis_xy_world_m'], [-.2, .1], atol=.0001)
        self.assertAlmostEqual(model['body_radius_m'], .022, places=4)
        self.assertEqual(len(model['parts']), 2)

    def test_flat_surface_does_not_support_bottle_curvature(self):
        world = np.empty((60, 30, 3))
        world[:, :, 0] = -.2
        world[:, :, 1] = np.linspace(-.02, .02, 30)
        world[:, :, 2] = np.linspace(.9, 1.06, 60)[:, None]
        with self.assertRaisesRegex(ValueError, 'curvature'):
            fit_upright_bottle(world, np.ones(world.shape[:2], bool))


if __name__ == '__main__':
    unittest.main()
