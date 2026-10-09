import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_plate_geometry import fit_plate_support


class PlateGeometryTest(unittest.TestCase):
    def grid(self):
        x, y = np.meshgrid(np.linspace(-.07, .07, 65), np.linspace(-.07, .07, 65))
        radial = np.hypot(x, y)
        world = np.stack([x+.1, y-.2, .9+np.where(radial>.05, .01, 0)], axis=-1)
        return world, radial<.07, radial

    def test_interior_plane_excludes_raised_rim(self):
        world, mask, _ = self.grid()
        model = fit_plate_support(world, mask)
        self.assertAlmostEqual(model['support_z_world_m'], .9, places=4)
        self.assertLess(model['support_radius_m'], .05)
        self.assertGreater(model['support_radius_m'], .045)

    def test_curved_bowl_is_not_a_planar_plate_patch(self):
        world, mask, radial = self.grid()
        world[:, :, 2] = .9 + 8*radial**2
        with self.assertRaisesRegex(ValueError, 'nonplanar'):
            fit_plate_support(world, mask)


if __name__ == '__main__':
    unittest.main()
