import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_anchor_obstacles import observed_anchor_obstacles


class AnchorObstaclesTest(unittest.TestCase):
    def test_boundary_ownership_keeps_neighbor_outside_fitted_bottle(self):
        x,y=np.meshgrid(np.linspace(.1,.7,40),np.linspace(-.3,.3,30))
        points=np.stack([x,y,np.full_like(x,-.01)],axis=-1)
        points[0,5:8,2]=.1
        mask=np.zeros(x.shape,bool);mask[0,5]=True
        frame=SimpleNamespace(depth_m=np.ones(x.shape),depth_valid=np.ones(x.shape,bool),
                              episode_id='test',env_step=1,camera_id='main')
        pixels=SimpleNamespace(mask=np.zeros(x.shape,bool),report={})
        model=dict(axis_xy_world_m=points[0,5,:2].tolist(),
                   parts=[dict(radius_m=.021,z_min_m=.09,z_max_m=.11)])
        with patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.unproject_world',return_value=points.reshape(-1,3)), patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.infer_world_from_base',return_value=np.eye(4)):
            result=observed_anchor_obstacles(frame,mask,pixels,bottle_model=model,bottle_mask=mask)
        self.assertEqual(result['target_boundary_ownership_extra_pixels'],1)
        self.assertEqual(result['residual_point_count'],1)

    def test_table_separation_robot_filter_and_obstacle_coverage(self):
        x,y=np.meshgrid(np.linspace(.1,.7,40),np.linspace(-.3,.3,30))
        points=np.stack([x,y,np.full_like(x,-.01)],axis=-1)
        points[0,:10,2]=.1
        points[1,:10,2]=.2
        robot=np.zeros(x.shape,bool);robot[1,:10]=True
        frame=SimpleNamespace(depth_m=np.ones(x.shape),depth_valid=np.ones(x.shape,bool),
                              episode_id='test',env_step=1,camera_id='main')
        pixels=SimpleNamespace(mask=robot,report={'source':'test'})
        with patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.unproject_world',return_value=points.reshape(-1,3)), patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.infer_world_from_base',return_value=np.eye(4)):
            result=observed_anchor_obstacles(frame,np.zeros(x.shape,bool),pixels)
        self.assertAlmostEqual(result['table_z'],-.01)
        self.assertEqual(result['residual_point_count'],10)
        centres=np.array(result['centres']);halves=np.array(result['half_extents'])
        for point in points[0,:10]:
            self.assertTrue(np.any(np.all(abs(centres-point)<=halves+1e-12,axis=1)))
        self.assertFalse(result['full_scene_coverage_verified'])
