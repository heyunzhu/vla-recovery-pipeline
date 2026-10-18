import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_bowl_geometry import fit_bowl_support


class BowlGeometryTest(unittest.TestCase):
    def bowl(self):
        r, theta = np.meshgrid(np.linspace(0, .055, 80), np.linspace(-np.pi, np.pi, 120))
        return np.stack([.2+r*np.cos(theta), -.1+r*np.sin(theta), .9+16*r*r], axis=-1)

    def test_curved_bottom_uses_target_contact_height_and_keeps_walls(self):
        world = self.bowl()
        fit = fit_bowl_support(world, np.ones(world.shape[:2], bool), target_radius_m=.02)
        np.testing.assert_allclose(fit['center_xy_world_m'], [.2,-.1], atol=.001)
        self.assertGreater(fit['support_z_world_m'], .905)
        self.assertLess(fit['support_z_world_m'], .91)
        self.assertGreater(len(fit['observed_wall_points_world_m']), 100)
        self.assertEqual(fit['placement_policy'], 'center_only')

    def test_rejects_oversize_target(self):
        world = self.bowl()
        with self.assertRaisesRegex(ValueError, 'footprint'):
            fit_bowl_support(world, np.ones(world.shape[:2], bool), target_radius_m=.06)

    def test_rejects_occluded_bottom(self):
        world = self.bowl()
        mask = np.linalg.norm(world[:,:,:2]-[.2,-.1], axis=-1) > .03
        with self.assertRaisesRegex(ValueError, 'bottom'):
            fit_bowl_support(world, mask, target_radius_m=.02)


if __name__ == '__main__':
    unittest.main()
