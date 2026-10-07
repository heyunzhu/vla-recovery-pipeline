import dataclasses
import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame
from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base,panda_base_from_hand,compare_base_estimates
from experiments.robot.libero.skill_pipeline.visual_path_diagnostic import inspect_pregrasp_path


class VisualPathAndFramesTest(unittest.TestCase):
    def sample(self,valid=True):
        f=frame(valid)
        f=dataclasses.replace(f,robot_state=dict(f.robot_state,robot0_eef_pos=[0,0,.6]))
        proposal=dict(episode_id=f.episode_id,env_step=f.env_step,camera_id=f.camera_id,waypoints_world_m=[[0,0,.7]])
        return f,proposal

    def test_front_samples_do_not_certify_full_robot_or_execution(self):
        f,p=self.sample();result=inspect_pregrasp_path(f,p)
        self.assertGreater(result['front_of_observed_surface_count'],0)
        self.assertEqual(result['observed_point_intersection_count'],0)
        self.assertFalse(result['full_arm_collision_verified'])
        self.assertFalse(result['execution_allowed'])

    def test_missing_depth_never_counts_as_front_space(self):
        f,p=self.sample(False);result=inspect_pregrasp_path(f,p)
        self.assertEqual(result['front_of_observed_surface_count'],0)
        self.assertGreater(result['invalid_depth_count'],0)
        self.assertIsNone(result['min_observed_point_distance_m'])

    def test_visible_surface_intersection_is_reported(self):
        f,p=self.sample();p['waypoints_world_m']=[[0,0,1.0]]
        result=inspect_pregrasp_path(f,p)
        self.assertGreater(result['observed_point_intersection_count'],0)
        self.assertGreater(result['occluded_or_near_surface_count'],0)

    def test_outside_camera_is_unknown_and_never_front_space(self):
        f,p=self.sample();f=dataclasses.replace(f,robot_state=dict(f.robot_state,robot0_eef_pos=[.3,0,.6]))
        p['waypoints_world_m']=[[.3,0,.7]]
        result=inspect_pregrasp_path(f,p)
        self.assertEqual(result['front_of_observed_surface_count'],0)
        self.assertGreater(result['outside_view_count'],0)

    def test_stale_or_unbounded_path_refused(self):
        f,p=self.sample()
        with self.assertRaises(ValueError):inspect_pregrasp_path(dataclasses.replace(f,env_step=99),p)
        p['waypoints_world_m']=[[0,0,2]]
        with self.assertRaises(ValueError):inspect_pregrasp_path(f,p)

    def test_static_fk_and_base_estimate_are_proper_rigid_transforms(self):
        f,_=self.sample()
        for t in (panda_base_from_hand([0]*7),infer_world_from_base(f)):
            np.testing.assert_allclose(t[:3,:3].T @ t[:3,:3],np.eye(3),atol=1e-12)
            self.assertAlmostEqual(np.linalg.det(t[:3,:3]),1)
            np.testing.assert_array_equal(t[3],[0,0,0,1])
        with self.assertRaises(ValueError):panda_base_from_hand([0]*6)

    def test_base_estimate_tracks_world_translation_and_comparison_reports_change(self):
        f,_=self.sample();shift=np.array([.1,.2,.3])
        moved=dataclasses.replace(f,env_step=f.env_step+1,robot_state=dict(f.robot_state,
            robot0_eef_pos=(np.asarray(f.robot_state['robot0_eef_pos'])+shift).tolist()))
        np.testing.assert_allclose(infer_world_from_base(moved)[:3,3]-infer_world_from_base(f)[:3,3],shift)
        report=compare_base_estimates([f,moved])
        self.assertAlmostEqual(report['comparisons'][1]['position_difference_m'],np.linalg.norm(shift))
        self.assertFalse(report['solver_allowed'])
        with self.assertRaises(ValueError):compare_base_estimates([f,f])

    def test_environment_inputs_rejected(self):
        with self.assertRaises(TypeError):infer_world_from_base(object())
        with self.assertRaises(TypeError):inspect_pregrasp_path(object(),{})


if __name__=='__main__':unittest.main()
