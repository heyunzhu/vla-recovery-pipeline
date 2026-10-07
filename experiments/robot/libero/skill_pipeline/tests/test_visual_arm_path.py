import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_arm_path import (
    arm_parts_at_joints,face_axis_overlap_candidate,inspect_arm_joint_trajectory,
)
from experiments.robot.libero.skill_pipeline.visual_robot_pixels import box_triangles
from experiments.robot.libero.skill_pipeline.visual_gripper_path import supporting_planes
from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import _frame_digest
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame

SEED=np.array([0,-.7,0,-2.2,0,1.6,.7])


def synthetic_model():
    root=ET.Element('mujoco');parent=ET.SubElement(ET.SubElement(root,'worldbody'),'body')
    mesh=box_triangles([.01,.01,.01])
    for i in range(8):
        if i:
            parent=ET.SubElement(parent,'body',pos='0.1 0 0')
            ET.SubElement(parent,'joint',name=f'joint{i}',axis='0 0 1')
        ET.SubElement(parent,'geom',name=f'link{i}',group='0',type='mesh',mesh='box')
    return dict(xml=ET.ElementTree(root),meshes={'box':mesh},proxies={'box':supporting_planes(mesh)},source_sha256={})


class ArmPathTest(unittest.TestCase):
    def test_joint_rotation_updates_descendants_only(self):
        model=synthetic_model();original=arm_parts_at_joints(model,SEED,np.eye(4))
        moved=SEED.copy();moved[0]=.5
        changed=arm_parts_at_joints(model,moved,np.eye(4))
        self.assertEqual(len(changed),8)
        np.testing.assert_array_equal(original[0]['triangles_world_m'],changed[0]['triangles_world_m'])
        self.assertFalse(np.allclose(original[-1]['triangles_world_m'],changed[-1]['triangles_world_m']))

    def test_fixed_base_translation_moves_every_link(self):
        model=synthetic_model();base=np.eye(4);base[:3,3]=[1,2,3]
        a=arm_parts_at_joints(model,SEED,np.eye(4));b=arm_parts_at_joints(model,SEED,base)
        for before,after in zip(a,b):
            np.testing.assert_allclose(after['triangles_world_m']-before['triangles_world_m'],np.broadcast_to([1,2,3],after['triangles_world_m'].shape))

    def test_invalid_joints_and_base_rejected(self):
        model=synthetic_model()
        with self.assertRaises(ValueError):arm_parts_at_joints(model,[0]*7,np.eye(4))
        with self.assertRaises(ValueError):arm_parts_at_joints(model,SEED,np.ones((4,4)))

    def test_face_axis_separates_overlapping_aabbs(self):
        a=np.array([[0,0,0],[1,1,0],[1,1,1]])
        b=a+[.1,-.1,0]
        self.assertFalse(face_axis_overlap_candidate(a,b,[[1,-1,0]]))
        self.assertTrue(face_axis_overlap_candidate(a,a,[[1,0,0],[0,1,0],[0,0,1]]))
        self.assertFalse(face_axis_overlap_candidate(a,a+[5,0,0],[]))

    def test_stale_and_empty_trajectory_rejected_before_model_read(self):
        f=frame()
        with self.assertRaises(ValueError):inspect_arm_joint_trajectory(f,{'status':'kinematic_candidate','frame_content_sha256':'stale'},'missing')
        with self.assertRaises(ValueError):inspect_arm_joint_trajectory(f,{'status':'kinematic_candidate','frame_content_sha256':_frame_digest(f).hex(),'samples':[]},'missing')

    def test_diagnostic_keeps_execution_blocked_and_checks_base(self):
        f=frame();trajectory=dict(status='kinematic_candidate',frame_content_sha256=_frame_digest(f).hex(),
            world_from_base_candidate=infer_world_from_base(f).tolist(),samples=[dict(status='converged',joints=SEED.tolist())])
        with patch('experiments.robot.libero.skill_pipeline.visual_arm_path.load_arm_model',return_value=synthetic_model()):
            result=inspect_arm_joint_trajectory(f,trajectory,'unused')
            self.assertEqual(result['sample_count'],1)
            self.assertFalse(result['execution_allowed'])
            self.assertTrue(result['current_arm_pixels_not_removed'])
            self.assertFalse(result['gripper_self_pairs_checked'])
            trajectory['world_from_base_candidate'][0][3]+=1
            with self.assertRaises(ValueError):inspect_arm_joint_trajectory(f,trajectory,'unused')


if __name__=='__main__':unittest.main()
