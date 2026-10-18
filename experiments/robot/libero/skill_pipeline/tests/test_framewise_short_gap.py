import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import FramewiseRGBDTracker
from experiments.robot.libero.skill_pipeline.tests import test_visual_observed_geometry as observed_tests
from experiments.robot.libero.skill_pipeline.visual_observed_geometry import fit_observed_cuboid
from experiments.robot.libero.skill_pipeline.visual_inclined_support import canonical_box


class ShortGapTest(unittest.TestCase):
    def setUp(self):
        self.points,_,_,_=observed_tests.ObservedGeometryTest.box_surface()
        self.model=canonical_box(fit_observed_cuboid(self.points));self.center=np.array(self.model['center_world_m'])

    def frame(self,step,*,closed=False,shift=0):
        hand=self.center+[shift,0,.025]
        return SimpleNamespace(env_step=step,timestamp_s=step*.05,robot_state=dict(
            robot0_eef_pos=hand.tolist(),robot0_eef_quat=[0,0,0,1],
            robot0_gripper_qpos=[.021,-.021] if closed else [.04,-.04]))

    def tracker(self,frame,**kwargs):
        with patch.object(FramewiseRGBDTracker,'cloud',return_value=self.points):
            return FramewiseRGBDTracker(frame,np.ones((1,1),bool),self.model,
                lambda f:([],dict(categories=[])),category='cheese',**kwargs)

    def test_default_still_rejects_missing_target(self):
        t=self.tracker(self.frame(0))
        with self.assertRaisesRegex(ValueError,'unresolved'):t.update(self.frame(1))

    def test_open_hand_freezes_pose_and_marks_it_unmeasured(self):
        t=self.tracker(self.frame(0),max_missing_steps=10)
        model,report=t.update(self.frame(1,shift=.01))
        np.testing.assert_allclose(model['center_world_m'],self.center)
        self.assertFalse(model['tracking_observed']);self.assertFalse(report['eligible_for_goal_confirmation'])
        self.assertEqual(report['status'],'predicted');self.assertNotIn('observed_aabb_world_m',model)
        self.assertEqual(t.update(self.frame(1))[1]['missing_steps'],1)
        with self.assertRaisesRegex(ValueError,'missing_step_limit'):t.update(self.frame(11))

    def test_closed_nearby_hand_predicts_then_visual_reacquires(self):
        t=self.tracker(self.frame(0,closed=True),max_missing_steps=10)
        model,_=t.update(self.frame(1,closed=True,shift=.01))
        np.testing.assert_allclose(model['center_world_m'],self.center+[.01,0,0])
        t.segmenter=lambda f:([np.ones((1,1),bool)],dict(categories=['cheese']))
        with patch.object(t,'cloud',return_value=self.points+[.01,0,0]):
            model,report=t.update(self.frame(2,closed=True,shift=.01))
        self.assertTrue(model['tracking_observed']);self.assertEqual(report['status'],'observed')
        self.assertEqual(t.last_observed_step,2)

    def test_time_motion_and_gripper_transition_limits(self):
        t=self.tracker(self.frame(0,closed=True),max_missing_steps=20)
        with self.assertRaisesRegex(ValueError,'simulation_time_limit'):t.update(self.frame(11,closed=True))
        t=self.tracker(self.frame(0,closed=True),max_missing_steps=10)
        with self.assertRaisesRegex(ValueError,'hand_motion_exceeds'):t.update(self.frame(1,closed=True,shift=.05))
        t=self.tracker(self.frame(0,closed=True),max_missing_steps=10)
        with self.assertRaisesRegex(ValueError,'gripper_mode_changed'):t.update(self.frame(1))

    def test_reacquired_different_pose_does_not_silently_change_identity(self):
        t=self.tracker(self.frame(0),max_missing_steps=10);t.update(self.frame(1))
        t.segmenter=lambda f:([np.ones((1,1),bool)],dict(categories=['cheese']))
        with patch.object(t,'cloud',return_value=self.points+[.08,0,0]):
            with self.assertRaisesRegex(ValueError,'reacquisition disagrees'):t.update(self.frame(2))

    def test_fresh_geometry_can_reacquire_after_hand_closes(self):
        t=self.tracker(self.frame(0),max_missing_steps=10);t.update(self.frame(1))
        t.segmenter=lambda f:([np.ones((1,1),bool)],dict(categories=['cheese']))
        with patch.object(t,'cloud',return_value=self.points):
            _,report=t.update(self.frame(2,closed=True))
        self.assertEqual(report['status'],'observed')

    def test_current_wrist_geometry_recovers_agentview_miss(self):
        t=self.tracker(self.frame(0),max_missing_steps=10)
        primary=self.frame(1);primary.camera_id='agentview'
        wrist=self.frame(1);wrist.camera_id='robot0_eye_in_hand'
        t.fallback_frame_provider=lambda f:wrist
        t.segmenter=lambda f:(([np.ones((1,1),bool)],dict(categories=['cheese']))
            if f.camera_id=='robot0_eye_in_hand' else ([],dict(categories=[])))
        with patch.object(t,'cloud',return_value=self.points):
            model,report=t.update(primary)
        self.assertTrue(model['tracking_observed']);self.assertEqual(report['selected_camera_id'],'robot0_eye_in_hand')


if __name__=='__main__':unittest.main()
