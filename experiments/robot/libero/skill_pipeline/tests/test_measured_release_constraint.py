import unittest
import torch
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import _measured_release_pose_errors


class MeasuredReleaseConstraintTest(unittest.TestCase):
    def test_exact_candidate_has_zero_error_and_far_pose_is_rejected(self):
        pose=torch.eye(4).repeat(2,1,1);pose[1,0,3]=.08
        xy,z=_measured_release_pose_errors(pose,[[0,0,0,0]])
        self.assertEqual(float(xy[0]),0);self.assertGreater(float(xy[1]),.01)
        self.assertTrue(torch.equal(z,torch.zeros(2)))

    def test_cannot_mix_xy_from_one_candidate_with_z_from_another(self):
        pose=torch.eye(4)[None];pose[0,2,3]=.1
        xy,z=_measured_release_pose_errors(pose,[[0,0,0,0],[.1,0,.1,0]])
        self.assertGreater(float(xy[0]+z[0]),.01)

    def test_gradient_is_finite_and_yaw_wraps(self):
        pose=torch.eye(4)[None].clone();pose[0,0,3]=.002;pose.requires_grad_()
        xy,z=_measured_release_pose_errors(pose,[[0,0,0,2*torch.pi]])
        (xy.sum()+z.sum()).backward()
        self.assertTrue(torch.isfinite(pose.grad).all());self.assertGreater(float(pose.grad[0,0,3]),0)


if __name__=='__main__':unittest.main()
