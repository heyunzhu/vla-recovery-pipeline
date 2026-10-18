import unittest
from types import SimpleNamespace
import numpy as np

from experiments.robot.libero.skill_pipeline.visual_placement_verification import check_rgbd_bowl_placement


class VisualPlacementVerificationTest(unittest.TestCase):
    def check(self, xy=(0., 0.), z=.91, opened=True):
        target=SimpleNamespace(pos=np.array([*xy,z]),geometry={'model':{'body_radius_m':.021}})
        scene=SimpleNamespace(objects={'bottle':target,'bowl':object()},gripper_open=opened)
        model=dict(center_xy_world_m=[0.,0.],support_radius_m=.051,support_z_world_m=.91)
        return check_rgbd_bowl_placement(scene,'bottle','bowl',model)

    def test_bottle_near_bowl_on_table_does_not_pass(self):
        self.assertFalse(self.check(xy=(.122,0),z=.903)['ok'])

    def test_centered_supported_and_released_passes(self):
        self.assertTrue(self.check()['ok'])

    def test_centered_airborne_or_held_does_not_pass(self):
        self.assertFalse(self.check(z=.94)['ok'])
        self.assertFalse(self.check(opened=False)['ok'])

    def test_footprint_must_fit_and_measurements_must_be_finite(self):
        self.assertFalse(self.check(xy=(.04,0))['ok'])
        self.assertFalse(self.check(z=float('nan'))['ok'])

    def test_se3_base_check_uses_measured_fingers_and_all_base_heights(self):
        angles=np.linspace(0,2*np.pi,24,endpoint=False)
        points=np.c_[.021*np.cos(angles),.021*np.sin(angles),np.full(24,.91)]
        target=SimpleNamespace(pos=np.array([0.,0.,.91]),geometry={'model':{'support_footprint_world_m':points.tolist()}})
        scene=SimpleNamespace(objects={'bottle':target,'bowl':object()},gripper_open=True,gripper_qpos=np.array([.021,-.021]))
        model=dict(center_xy_world_m=[0.,0.],support_radius_m=.051,support_z_world_m=.91)
        self.assertFalse(check_rgbd_bowl_placement(scene,'bottle','bowl',model)['ok'])
        scene.gripper_qpos=np.array([.039,-.039])
        self.assertTrue(check_rgbd_bowl_placement(scene,'bottle','bowl',model)['ok'])
        points[0,2]+=.02;target.geometry['model']['support_footprint_world_m']=points.tolist()
        self.assertFalse(check_rgbd_bowl_placement(scene,'bottle','bowl',model)['ok'])


if __name__ == '__main__':
    unittest.main()
