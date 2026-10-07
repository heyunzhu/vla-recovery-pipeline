import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.visual_collision_changes import (
    subdivide_joint_path,membership_changes,outer_hit_indices,inspect_collision_changes,
)
from experiments.robot.libero.skill_pipeline.visual_robot_pixels import box_triangles
from experiments.robot.libero.skill_pipeline.visual_gripper_path import supporting_planes
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame

SEED=np.array([0,-.7,0,-2.2,0,1.6,.7])


class CollisionChangesTest(unittest.TestCase):
    def test_subdivision_starts_at_actual_pose_and_keeps_endpoint(self):
        target=SEED.copy();target[0]+=.029
        rows=subdivide_joint_path(SEED,[target])
        q=np.array([r['joints'] for r in rows])
        np.testing.assert_array_equal(q[0],SEED);np.testing.assert_array_equal(q[-1],target)
        self.assertLessEqual(np.abs(np.diff(q,axis=0)).max(),.01+1e-15)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[1]['target_sample_index'],0)

    def test_duplicate_targets_do_not_reset_baseline_or_lose_next_index(self):
        target=SEED.copy();target[0]+=.01
        rows=subdivide_joint_path(SEED,[SEED,SEED,target,target])
        self.assertEqual(len(rows),2);self.assertEqual(rows[-1]['target_sample_index'],2)
        self.assertEqual(len(subdivide_joint_path(SEED,[SEED])),1)

    def test_membership_partition_retains_unresolved_baseline(self):
        change=membership_changes([1,2,3],[2,3,4])
        np.testing.assert_array_equal(change['new'],[4])
        np.testing.assert_array_equal(change['persistent'],[2,3])
        np.testing.assert_array_equal(change['resolved'],[1])
        # The same pixel entering another part is new for that part.
        np.testing.assert_array_equal(membership_changes([],[2])['new'],[2])

    def test_subdivision_detects_intermediate_membership_missed_at_endpoints(self):
        target=SEED.copy();target[0]=.02
        rows=subdivide_joint_path(SEED,[target]);box=box_triangles([.001,.001,.001])
        observed=np.array([[.01,0,0]])
        counts=[]
        for row in rows:
            transform=np.eye(4);transform[0,3]=row['joints'][0]
            part=dict(world_from_geom=transform,triangles_world_m=box+transform[:3,3],local_planes=supporting_planes(box))
            counts.append(len(outer_hit_indices(observed,np.array([True]),part,0)))
        self.assertEqual(counts,[0,1,0])

    def test_current_mask_is_respected_without_deleting_other_points(self):
        box=box_triangles([1,1,1]);part=dict(world_from_geom=np.eye(4),triangles_world_m=box,local_planes=supporting_planes(box))
        points=np.array([[0,0,0],[.5,0,0],[3,0,0]])
        np.testing.assert_array_equal(outer_hit_indices(points,np.array([False,True,True]),part,0),[1])

    def test_invalid_joint_bounds_or_spacing_rejected(self):
        for current,targets,spacing in (([0]*7,[SEED],.01),(SEED,[],.01),(SEED,[SEED],0)):
            with self.assertRaises(ValueError):subdivide_joint_path(current,targets,max_joint_step_rad=spacing)

    def test_stale_trajectory_rejected_before_loading_model(self):
        with self.assertRaises(ValueError):inspect_collision_changes(frame(),{'status':'kinematic_candidate','frame_content_sha256':'stale'},'missing',None)


if __name__=='__main__':unittest.main()
