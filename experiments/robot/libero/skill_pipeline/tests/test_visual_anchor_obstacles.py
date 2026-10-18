import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_anchor_obstacles import observed_anchor_obstacles


class AnchorObstaclesTest(unittest.TestCase):
    def test_labeled_only_filters_unknown_points_but_keeps_table_and_labeled_obstacle(self):
        x,y=np.meshgrid(np.linspace(.1,.7,40),np.linspace(-.3,.3,30))
        points=np.stack([x,y,np.full_like(x,-.01)],axis=-1)
        points[0,:10,2]=.1
        labels=np.zeros(x.shape,bool);labels[0,:3]=True
        frame=SimpleNamespace(depth_m=np.ones(x.shape),depth_valid=np.ones(x.shape,bool),
                              episode_id='test',env_step=1,camera_id='main')
        robot=SimpleNamespace(mask=np.zeros(x.shape,bool),report={})
        debug={}
        with patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.unproject_world',return_value=points.reshape(-1,3)), patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.infer_world_from_base',return_value=np.eye(4)):
            result=observed_anchor_obstacles(frame,np.zeros(x.shape,bool),robot,labeled_mask=labels,debug_masks=debug)
        self.assertAlmostEqual(result['table_z'],-.01)
        self.assertEqual(result['eligible_residual_point_count'],10)
        self.assertEqual(result['residual_point_count'],3)
        self.assertEqual(result['ignored_unlabeled_point_count'],7)
        self.assertTrue(np.all(debug['retained_obstacle_pixels'] <= labels))
        self.assertEqual(int(debug['ignored_unlabeled_pixels'].sum()),7)

    def test_native_640_preserves_the_reference_boundary_extent(self):
        x,y=np.meshgrid(np.linspace(.1,.7,640),np.linspace(-.3,.3,640))
        points=np.stack([x,y,np.full_like(x,-.01)],axis=-1)
        points[300,300]=[.3,-.1,.1]
        points[305,302]=[.301,-.1,.1]
        points[303,300]=[.4,-.1,.1]
        points[306,300]=[.3,-.1,.1]
        mask=np.zeros(x.shape,bool);mask[300,300]=True
        frame=SimpleNamespace(depth_m=np.ones(x.shape),depth_valid=np.ones(x.shape,bool),
                              episode_id='test',env_step=1,camera_id='main')
        pixels=SimpleNamespace(mask=np.zeros(x.shape,bool),report={})
        model=dict(axis_xy_world_m=[.3,-.1],parts=[dict(radius_m=.021,z_min_m=.09,z_max_m=.11)])
        with patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.unproject_world',return_value=points.reshape(-1,3)), patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.infer_world_from_base',return_value=np.eye(4)):
            result=observed_anchor_obstacles(frame,mask,pixels,bottle_model=model,bottle_mask=mask)
        self.assertEqual(result['target_boundary_radius_xy_px'],[5,5])
        self.assertEqual(result['target_boundary_ownership_extra_pixels'],1)
        self.assertEqual(result['residual_point_count'],2)

    def test_diagonal_cap_pixel_is_owned_but_outside_volume_and_distant_pixels_remain(self):
        x,y=np.meshgrid(np.linspace(.1,.7,40),np.linspace(-.3,.3,30))
        points=np.stack([x,y,np.full_like(x,-.01)],axis=-1)
        points[3,3]=[.3,-.1,.1]
        points[5,4]=[.301,-.1,.1]  # (2,1) image offset, inside fitted cap
        points[4,4]=[.4,-.1,.1]    # image neighbor, different physical surface
        points[7,3]=[.3,-.1,.1]    # same volume alone cannot authorize ownership
        mask=np.zeros(x.shape,bool);mask[3,3]=True
        frame=SimpleNamespace(depth_m=np.ones(x.shape),depth_valid=np.ones(x.shape,bool),
                              episode_id='test',env_step=1,camera_id='main')
        pixels=SimpleNamespace(mask=np.zeros(x.shape,bool),report={})
        model=dict(axis_xy_world_m=[.3,-.1],parts=[dict(radius_m=.021,z_min_m=.09,z_max_m=.11)])
        with patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.unproject_world',return_value=points.reshape(-1,3)), patch('experiments.robot.libero.skill_pipeline.visual_anchor_obstacles.infer_world_from_base',return_value=np.eye(4)):
            result=observed_anchor_obstacles(frame,mask,pixels,bottle_model=model,bottle_mask=mask)
        self.assertEqual(result['target_boundary_ownership_extra_pixels'],1)
        self.assertEqual(result['residual_point_count'],2)

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
