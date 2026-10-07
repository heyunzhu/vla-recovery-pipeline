import dataclasses
import tempfile
import unittest
from pathlib import Path
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_arm_pixels import read_obj_triangles,depth_match_evidence
from experiments.robot.libero.skill_pipeline.visual_path_diagnostic import inspect_pregrasp_path
from experiments.robot.libero.skill_pipeline.tests import test_visual_path_and_frames as samples


class ArmPixelsTest(unittest.TestCase):
    def test_obj_triangle_coordinates_and_index_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mesh.obj'
            path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1/1 2/2 3/3\n')
            np.testing.assert_array_equal(read_obj_triangles(path),[[[0,0,0],[1,0,0],[0,1,0]]])
            for face in ('f 0 2 3','f 1 2 4','f 1 2 3 1'):
                path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\n'+face)
                with self.assertRaises(ValueError):read_obj_triangles(path)

    def sample(self):
        f,p=samples.VisualPathAndFramesTest().sample()
        depth=np.full(f.depth_m.shape,np.inf)
        depth[8:12,8:12]=f.depth_m[8:12,8:12]
        evidence=depth_match_evidence(f,depth,depth_tolerance_m=.002,source_sha256={},skipped=0,geom_names=['arm'])
        return f,p,evidence

    def test_depth_matching_retains_foreground_and_background_discrepancies(self):
        f,p,e=self.sample();depth=e.mesh_depth_m.copy()
        depth[8,8]=f.depth_m[8,8]+.01
        depth[8,9]=f.depth_m[8,9]-.01
        e=depth_match_evidence(f,depth,depth_tolerance_m=.002,source_sha256={},skipped=0,geom_names=['arm'])
        self.assertEqual(e.report['matched_pixel_count'],14)
        self.assertFalse(e.mask[8,8]);self.assertFalse(e.mask[8,9])
        self.assertFalse(e.report['complete_robot_mask'])
        self.assertTrue(e.report['arm_mesh_projected'])
        self.assertFalse(e.mask.flags.writeable);self.assertFalse(e.mesh_depth_m.flags.writeable)

    def test_invalid_depth_and_tolerance_rejected(self):
        f,p,e=self.sample()
        for depth,tolerance in ((np.ones((1,1)),.002),(np.zeros(f.depth_m.shape),.002),(e.mesh_depth_m,.02)):
            with self.assertRaises(ValueError):depth_match_evidence(f,depth,depth_tolerance_m=tolerance,source_sha256={},skipped=0,geom_names=[])

    def test_full_arm_evidence_uses_existing_snapshot_and_mask_checks(self):
        f,p,e=self.sample();result=inspect_pregrasp_path(f,p,robot_pixels=e)
        self.assertEqual(result['remaining_point_count'],384)
        self.assertFalse(result['execution_allowed'])
        with self.assertRaises(ValueError):inspect_pregrasp_path(dataclasses.replace(f,env_step=f.env_step+1),p,robot_pixels=e)
        mask=e.mask.copy();mask[0,0]=True
        with self.assertRaises(ValueError):inspect_pregrasp_path(f,p,robot_pixels=dataclasses.replace(e,mask=mask))


if __name__=='__main__':unittest.main()
