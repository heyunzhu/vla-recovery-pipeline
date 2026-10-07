import dataclasses
import unittest
import numpy as np
from experiments.robot.libero.skill_pipeline.tests.test_visual_pregrasp_control import frame
from experiments.robot.libero.skill_pipeline.visual_panda_ik import (
    JOINT_LIMITS,world_grip_pose,solve_panda_pose,prepare_panda_joint_trajectory,rotation_log,
)

SEED=np.array([0,-.7,0,-2.2,0,1.6,.7])


class PandaIKTest(unittest.TestCase):
    def test_reachable_pose_converges_from_a_different_seed(self):
        target_q=SEED+np.array([.04,-.02,.01,.03,-.02,.02,.01])
        p,r=world_grip_pose(target_q,np.eye(4))
        solved=solve_panda_pose(SEED,np.eye(4),p,r)
        self.assertEqual(solved['status'],'converged')
        self.assertLessEqual(solved['position_error_m'],.001)
        self.assertLessEqual(solved['rotation_error_deg'],.5)
        q=np.array(solved['joints'])
        self.assertTrue(np.all(q>=JOINT_LIMITS[:,0]) and np.all(q<=JOINT_LIMITS[:,1]))
        self.assertFalse(solved['execution_allowed'])

    def test_current_pose_requires_no_joint_change(self):
        p,r=world_grip_pose(SEED,np.eye(4));solved=solve_panda_pose(SEED,np.eye(4),p,r)
        np.testing.assert_array_equal(solved['joints'],SEED)
        self.assertEqual(solved['iterations'],0)

    def test_far_pose_returns_nonconvergence_with_bounded_joints(self):
        solved=solve_panda_pose(SEED,np.eye(4),[10,10,10],np.eye(3),max_iterations=20)
        self.assertEqual(solved['status'],'not_converged')
        self.assertEqual(solved['iterations'],20)
        q=np.array(solved['joints'])
        self.assertTrue(np.all(q>=JOINT_LIMITS[:,0]) and np.all(q<=JOINT_LIMITS[:,1]))

    def test_invalid_seed_and_nonrigid_pose_are_rejected(self):
        p,r=world_grip_pose(SEED,np.eye(4))
        for seed in ([0]*7,[0]*6):
            with self.assertRaises(ValueError):solve_panda_pose(seed,np.eye(4),p,r)
        with self.assertRaises(ValueError):solve_panda_pose(SEED,np.eye(4),p,np.ones((3,3)))

    def test_pi_orientation_log_remains_finite(self):
        vector=rotation_log(np.diag([1,-1,-1]))
        self.assertTrue(np.isfinite(vector).all())
        self.assertAlmostEqual(np.linalg.norm(vector),np.pi)

    def test_small_translation_trajectory_is_candidate_only(self):
        f=frame();f=dataclasses.replace(f,robot_state=dict(f.robot_state,robot0_joint_pos=SEED.tolist(),robot0_eef_quat=[1,0,0,0]))
        p=dict(episode_id=f.episode_id,env_step=f.env_step,camera_id=f.camera_id,
               waypoints_world_m=[[.005,.001,1.2]])
        result=prepare_panda_joint_trajectory(f,p)
        self.assertEqual(result['status'],'kinematic_candidate')
        self.assertLessEqual(result['max_joint_change_rad'],.15)
        self.assertFalse(result['collision_verified'])
        self.assertFalse(result['execution_allowed'])
        with self.assertRaises(ValueError):prepare_panda_joint_trajectory(dataclasses.replace(f,env_step=99),p)


if __name__=='__main__':unittest.main()
