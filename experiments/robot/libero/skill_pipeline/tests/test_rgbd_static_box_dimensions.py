import unittest
from types import SimpleNamespace

from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackendConfig, _cuboid_dims, _cuboid_pose,
)


class RGBDStaticBoxDimensionsTest(unittest.TestCase):
    def obj(self, role="static", source="rgbd_observed_anchor_obstacles"):
        return SimpleNamespace(name="rgbd_obstacle_0451", role=role,
            geometry={"source": source}, half_extents=[.001, .001, .001],
            radius=.001, height=.002, pos=[.54, -.034, 0.])

    def test_measured_static_cell_retains_dimensions_and_center(self):
        cfg = RealCuTAMPBackendConfig()
        obj = self.obj()
        self.assertEqual(_cuboid_dims(obj, cfg), [.002, .002, .002])
        obj.half_extents = [.00316005951884507, .005058161651167597, .0011160014411700217]
        self.assertEqual(_cuboid_dims(obj, cfg), [2*v for v in obj.half_extents])
        self.assertEqual(_cuboid_pose(obj, cfg)[:3], obj.pos)

    def test_proxy_floor_is_retained_outside_observed_static_cells(self):
        cfg = RealCuTAMPBackendConfig()
        for obj in (self.obj(source="generic_proxy"), self.obj(role="movable")):
            self.assertEqual(_cuboid_dims(obj, cfg), [.035, .035, .035])
        self.assertEqual(_cuboid_dims(self.obj(role="surface"), cfg), [.08, .08, .01])

    def test_observed_target_keeps_padded_thin_dimension(self):
        cfg = RealCuTAMPBackendConfig()
        for role in ["movable", "target_movable"]:
            obj = self.obj(role=role, source="rgbd_observed_cuboid")
            obj.half_extents = [.0426, .02245, .00994]
            self.assertEqual(_cuboid_dims(obj, cfg), [.0852, .0449, .01988])


if __name__ == "__main__":
    unittest.main()
