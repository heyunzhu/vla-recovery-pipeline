import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_robot_pixels import box_triangles
from experiments.robot.libero.skill_pipeline.visual_mesh_diagnostic import (
    classify_mesh_points,point_surface_distance,mesh_closed_edge_check,ray_parity,
)
from experiments.robot.libero.skill_pipeline.visual_arm_followup import transform_gripper_parts,inspect_gripper_arm_pairs
from experiments.robot.libero.skill_pipeline.visual_robot_pixels import StaticGripperGeometry
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame


class MeshDiagnosticTest(unittest.TestCase):
    def test_closed_box_inside_outside_and_margin(self):
        t=box_triangles([1,1,1]);result=classify_mesh_points(np.array([[0,0,0],[2,0,0],[1.001,0,0]]),t)
        self.assertTrue(result['topology']['closed_edge_topology'])
        self.assertEqual([p['category'] for p in result['points']],
            ['inside_two_ray_candidate','outside_two_ray_candidate','near_triangle_surface'])
        self.assertFalse(result['execution_allowed'])

    def test_triangle_distance_covers_face_edge_and_vertex(self):
        t=np.array([[[0,0,0],[1,0,0],[0,1,0]]],float)
        self.assertAlmostEqual(point_surface_distance([.2,.2,2],t),2)
        self.assertAlmostEqual(point_surface_distance([.5,-1,0],t),1)
        self.assertAlmostEqual(point_surface_distance([-1,-1,0],t),np.sqrt(2))

    def test_open_mesh_remains_unknown_away_from_surface(self):
        t=box_triangles([1,1,1])[:-1]
        self.assertFalse(mesh_closed_edge_check(t)['closed_edge_topology'])
        self.assertEqual(classify_mesh_points(np.array([[0,0,0]]),t)['points'][0]['category'],'unknown')

    def test_gap_inside_outer_box_is_outside_two_closed_mesh_components(self):
        t=np.concatenate((box_triangles([.2,.2,.2])+[-1,0,0],box_triangles([.2,.2,.2])+[1,0,0]))
        result=classify_mesh_points(np.array([[0,0,0]]),t)
        self.assertEqual(result['points'][0]['category'],'outside_two_ray_candidate')

    def test_edge_ray_is_ambiguous_and_invalid_geometry_rejected(self):
        t=box_triangles([1,1,1])
        self.assertIsNone(ray_parity([0,0,0],t,[1,1,1]))
        with self.assertRaises(ValueError):classify_mesh_points(np.array([[np.nan,0,0]]),t)
        with self.assertRaises(ValueError):classify_mesh_points(np.array([[0,0,0]]),t,margin_m=.1)

    def test_gripper_rigid_transform_tracks_hand_orientation_and_position(self):
        triangles=box_triangles([.1,.2,.3])+[2,0,0]
        geometry=StaticGripperGeometry('unused',({'name':'part','triangles_world_m':triangles},),{})
        current=np.eye(4);current[:3,3]=[2,0,0]
        candidate=np.eye(4);candidate[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]];candidate[:3,3]=[0,3,0]
        moved=transform_gripper_parts(geometry,current,candidate)[0]['triangles_world_m']
        np.testing.assert_allclose(moved,(triangles-[2,0,0]) @ candidate[:3,:3].T+[0,3,0],atol=1e-15)
        np.testing.assert_array_equal(transform_gripper_parts(geometry,current,current)[0]['triangles_world_m'],triangles)

    def test_stale_gripper_pair_trajectory_rejected_before_model_read(self):
        with self.assertRaises(ValueError):inspect_gripper_arm_pairs(frame(),{'status':'kinematic_candidate','frame_content_sha256':'stale'},'missing')


if __name__=='__main__':unittest.main()
