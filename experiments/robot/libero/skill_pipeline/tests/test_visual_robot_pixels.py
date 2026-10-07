import dataclasses
import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
from experiments.robot.libero.skill_pipeline.tests import test_visual_path_and_frames as samples
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import _frame_digest
from experiments.robot.libero.skill_pipeline.visual_robot_pixels import RobotPixelEvidence,project_static_gripper
from experiments.robot.libero.skill_pipeline.visual_path_diagnostic import inspect_pregrasp_path
from experiments.robot.libero.skill_pipeline.visual_robot_frames import STATIC_SOURCE_SHA256


class RobotPixelsTest(unittest.TestCase):
    def sample(self):
        f,p=samples.VisualPathAndFramesTest().sample()
        p['waypoints_world_m']=[[0,0,1.0]]
        depth=np.full(f.depth_m.shape,np.inf)
        depth[8:12,8:12]=f.depth_m[8:12,8:12]
        mask=np.isfinite(depth)
        pixels=RobotPixelEvidence(_frame_digest(f).hex(),mask,depth,dict(depth_tolerance_m=.002,complete_robot_mask=False))
        return f,p,pixels

    def test_matching_pixels_removed_only_from_secondary_distance_check(self):
        f,p,pixels=self.sample()
        raw=inspect_pregrasp_path(f,p)
        filtered=inspect_pregrasp_path(f,p,robot_pixels=pixels)
        self.assertEqual(filtered['removed_matched_gripper_point_count'],16)
        self.assertEqual(filtered['remaining_point_count'],384)
        self.assertEqual(filtered['observed_point_intersection_count'],raw['observed_point_intersection_count'])
        self.assertEqual(filtered['front_of_observed_surface_count'],raw['front_of_observed_surface_count'])
        self.assertLessEqual(filtered['remaining_point_intersection_count'],raw['observed_point_intersection_count'])
        self.assertFalse(filtered['execution_allowed'])

    def test_wrong_frame_and_arbitrary_masks_are_rejected(self):
        f,p,pixels=self.sample()
        with self.assertRaises(ValueError):inspect_pregrasp_path(f,p,robot_pixels=np.zeros_like(f.depth_valid))
        with self.assertRaises(ValueError):inspect_pregrasp_path(f,p,robot_pixels=dataclasses.replace(pixels,frame_content_sha256='stale'))
        with self.assertRaisesRegex(ValueError,'depth consistency'):
            inspect_pregrasp_path(f,p,robot_pixels=dataclasses.replace(pixels,mask=np.ones_like(pixels.mask)))

    def test_foreground_object_cannot_be_removed_by_silhouette_only(self):
        f,p,pixels=self.sample()
        wrong=pixels.mesh_depth_m.copy();wrong[8:12,8:12]+=.02
        with self.assertRaisesRegex(ValueError,'depth consistency'):
            inspect_pregrasp_path(f,p,robot_pixels=dataclasses.replace(pixels,mesh_depth_m=wrong))

    def test_witness_pixels_reference_remaining_observed_points(self):
        f,p,pixels=self.sample()
        result=inspect_pregrasp_path(f,p,robot_pixels=pixels)
        for witness in result['remaining_nearest_witnesses']:
            x,y=witness['pixel_xy']
            self.assertFalse(pixels.mask[y,x])
            self.assertTrue(f.depth_valid[y,x])
            self.assertLessEqual(witness['distance_m'],result['probe_radius_m'])

    def test_model_projection_rejects_nonvisual_input_and_unsupported_tolerance(self):
        with self.assertRaises(TypeError):project_static_gripper(object(),'unused')
        f,_,_=self.sample()
        with self.assertRaises(ValueError):project_static_gripper(f,'unused',depth_tolerance_m=.02)

    def test_modified_model_file_is_rejected_before_projection(self):
        f,_,_=self.sample()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);relative='models/assets/grippers/panda_gripper.xml'
            xml=root/relative;xml.parent.mkdir(parents=True);xml.write_text('<changed/>')
            (root/'manifest.json').write_text(json.dumps(dict(source_sha256={relative:STATIC_SOURCE_SHA256['panda_gripper.xml']})))
            with self.assertRaisesRegex(ValueError,'digest mismatch'):
                project_static_gripper(f,root)


if __name__=='__main__':unittest.main()
