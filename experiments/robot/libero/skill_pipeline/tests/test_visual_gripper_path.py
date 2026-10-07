import dataclasses
import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.tests import test_visual_path_and_frames as samples
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import _frame_digest
from experiments.robot.libero.skill_pipeline.visual_robot_pixels import StaticGripperGeometry,box_triangles,RobotPixelEvidence
from experiments.robot.libero.skill_pipeline.visual_gripper_path import supporting_planes,points_in_outer_body,inspect_gripper_path


class GripperPathTest(unittest.TestCase):
    def sample(self):
        frame,proposal=samples.VisualPathAndFramesTest().sample()
        proposal['waypoints_world_m']=[[0,0,1.0]]
        triangles=box_triangles([.02,.02,.02])+np.asarray(frame.robot_state['robot0_eef_pos'])
        geometry=StaticGripperGeometry(_frame_digest(frame).hex(),(dict(name='pad',kind='box',triangles_world_m=triangles),),dict(geometry_mode='collision'))
        return frame,proposal,geometry

    def test_exact_box_halfspaces_classify_interior_and_exterior(self):
        triangles=box_triangles([.02,.03,.04])
        planes=supporting_planes(triangles)
        result=points_in_outer_body(np.array([[0,0,0],[.019,0,0],[.021,0,0],[0,0,.041]]),planes,0)
        np.testing.assert_array_equal(result,[True,True,False,False])
        np.testing.assert_array_equal(points_in_outer_body(triangles.reshape(-1,3),planes,0),True)

    def test_rotated_box_preserves_local_shape(self):
        angle=.7;r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        triangles=box_triangles([.02,.03,.04]) @ r.T+np.array([1,2,3])
        points=np.array([[.019,0,0],[.025,0,0]]) @ r.T+np.array([1,2,3])
        np.testing.assert_array_equal(points_in_outer_body(points,supporting_planes(triangles),0),[True,False])

    def test_geometry_margin_is_explicit(self):
        planes=supporting_planes(box_triangles([.02]*3))
        points=np.array([[.021,0,0]])
        self.assertFalse(points_in_outer_body(points,planes,0)[0])
        self.assertTrue(points_in_outer_body(points,planes,.002)[0])
        with self.assertRaises(ValueError):points_in_outer_body(points,planes,.1)

    def test_gripper_moves_with_path_and_reports_observed_surface(self):
        frame,proposal,geometry=self.sample()
        report=inspect_gripper_path(frame,proposal,geometry)
        self.assertGreater(report['raw_intersection_centre_count'],0)
        self.assertEqual(report['centres'][0]['raw_point_count'],0)
        self.assertEqual(report['parts'][0]['representation'],'exact_box')
        self.assertFalse(report['continuous_swept_volume_verified'])
        self.assertFalse(report['execution_allowed'])

    def test_raw_counts_preserved_when_depth_matched_self_pixels_are_removed(self):
        frame,proposal,geometry=self.sample()
        depth=np.full(frame.depth_m.shape,np.inf);depth[8:12,8:12]=1
        pixels=RobotPixelEvidence(_frame_digest(frame).hex(),np.isfinite(depth),depth,dict(depth_tolerance_m=.002))
        report=inspect_gripper_path(frame,proposal,geometry,robot_pixels=pixels)
        self.assertGreater(report['raw_intersection_centre_count'],0)
        self.assertEqual(report['remaining_intersection_centre_count'],0)
        self.assertFalse(report['execution_allowed'])

    def test_stale_and_visual_geometry_cannot_replace_collision_parts(self):
        frame,proposal,geometry=self.sample()
        for modified in (dataclasses.replace(geometry,frame_content_sha256='stale'),
                         dataclasses.replace(geometry,report=dict(geometry_mode='visual'))):
            with self.assertRaises(ValueError):inspect_gripper_path(frame,proposal,modified)


if __name__=='__main__':unittest.main()
