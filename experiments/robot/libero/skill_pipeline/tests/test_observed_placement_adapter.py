import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from scipy.spatial.transform import Rotation
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import _place_yaw_policies_by_surface
from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import FramewiseRGBDTracker,transform
from experiments.robot.libero.skill_pipeline.visual_inclined_support import canonical_box
from experiments.robot.libero.skill_pipeline.visual_observed_geometry import fit_observed_cuboid
from experiments.robot.libero.skill_pipeline.tests import test_visual_observed_geometry as observed_tests

class ObservedPlacementAdapterTest(unittest.TestCase):
    def test_only_explicit_visual_source_enables_measured_sampler(self):
        surface=SimpleNamespace(name='visual_rack',geometry=dict(source='rgbd_observed_release_region',metadata=dict(rgbd_release_candidates=[[.4,.1,.2,0.]])))
        policies=_place_yaw_policies_by_surface(SimpleNamespace(surfaces=[surface]),{'visual_rack':'rack'})
        self.assertEqual(policies['rack'],[[.4,.1,.2,0.]])
        surface.geometry['source']='other'
        self.assertEqual(_place_yaw_policies_by_surface(SimpleNamespace(surfaces=[surface]),{}),{})

    def test_invalid_candidate_is_rejected(self):
        surface=SimpleNamespace(name='visual_rack',geometry=dict(source='rgbd_observed_release_region',metadata=dict(rgbd_release_candidates=[[.4,.1,float('nan'),0.]])))
        with self.assertRaisesRegex(ValueError,'invalid measured'):
            _place_yaw_policies_by_surface(SimpleNamespace(surfaces=[surface]),{})

    def test_generic_tracker_transforms_center_and_corners_without_bottle_fields(self):
        points,_,_,center=observed_tests.ObservedGeometryTest.box_surface()
        model=canonical_box(fit_observed_cuboid(points))
        pose=np.eye(4);pose[:3,:3]=Rotation.from_euler('y',8,degrees=True).as_matrix();pose[:3,3]=center-pose[:3,:3]@center+[.02,.01,.02]
        state=dict(robot0_eef_pos=center.tolist(),robot0_eef_quat=[0,0,0,1],robot0_gripper_qpos=[.01,-.01])
        frame=SimpleNamespace(env_step=1,robot_state=state)
        state2=dict(state,robot0_eef_pos=transform(center[None],pose)[0].tolist(),robot0_eef_quat=Rotation.from_matrix(pose[:3,:3]).as_quat().tolist())
        current=SimpleNamespace(env_step=2,robot_state=state2)
        segmenter=lambda f:([np.ones((1,1),bool)],dict(categories=['cheese']))
        with patch.object(FramewiseRGBDTracker,'cloud',side_effect=[points,transform(points,pose)]):
            tracker=FramewiseRGBDTracker(frame,np.ones((1,1)),model,segmenter,category='cheese')
            updated,_=tracker.update(current)
        np.testing.assert_allclose(updated['center_world_m'],transform(np.array(model['center_world_m'])[None],pose)[0],atol=.001)
        np.testing.assert_allclose(updated['corners_world_m'],transform(np.array(model['corners_world_m']),pose),atol=.001)
        self.assertNotIn('body_radius_m',updated)

if __name__=='__main__':unittest.main()
