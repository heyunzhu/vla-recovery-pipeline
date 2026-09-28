from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds, dominant_horizontal_plane
from experiments.robot.libero.skill_pipeline.visual_object_proposals import foreground_proposals


class VisualGeometryTest(unittest.TestCase):
    def test_visible_support_plane_excludes_obstacle_and_reports_geometry(self) -> None:
        transform = np.diag([1.0, -1.0, -1.0, 1.0])
        transform[:3, 3] = [0.0, 0.0, 1.5]
        depth = np.full((40, 40), 0.6, dtype=np.float32)
        depth[:, :5] = 0.4  # A raised foreground obstacle.
        frame = RGBDObservation(
            episode_id="test",
            env_step=0,
            timestamp_s=0.0,
            camera_id="agentview",
            rgb=np.zeros((40, 40, 3), dtype=np.uint8),
            depth_m=depth,
            depth_valid=np.ones((40, 40), dtype=bool),
            K=np.asarray([[40.0, 0.0, 20.0], [0.0, 40.0, 20.0], [0.0, 0.0, 1.0]]),
            T_world_camera=transform,
            robot_state={
                "robot0_joint_pos": [0.0] * 7,
                "robot0_gripper_qpos": [0.0, 0.0],
                "robot0_eef_pos": [0.0, 0.0, 1.0],
                "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
            },
            calibration_version="test",
        )
        bounds = WorkspaceBounds(x=(-1.0, 1.0), y=(-1.0, 1.0), z=(0.7, 1.2))
        candidate = dominant_horizontal_plane(frame, bounds)
        self.assertIsNotNone(candidate)
        self.assertAlmostEqual(candidate.height_at(0.0, 0.0), 0.9, places=5)
        self.assertEqual(candidate.inlier_points, 1400)
        self.assertLess(candidate.rms_residual_m, 1e-6)
        self.assertGreater(candidate.normal_world[2], 0.99)
        self.assertIsNone(dominant_horizontal_plane(frame, bounds, min_inliers=1500))

    def test_two_separate_depth_objects_remain_unnamed_proposals(self) -> None:
        transform = np.diag([1.0, -1.0, -1.0, 1.0])
        transform[:3, 3] = [0.0, 0.0, 1.5]
        depth = np.full((40, 40), 0.6, dtype=np.float32)
        depth[5:10, 5:10] = 0.45
        depth[22:29, 20:28] = 0.5
        frame = RGBDObservation(
            episode_id="two_objects",
            env_step=0,
            timestamp_s=0.0,
            camera_id="agentview",
            rgb=np.zeros((40, 40, 3), dtype=np.uint8),
            depth_m=depth,
            depth_valid=np.ones((40, 40), dtype=bool),
            K=np.asarray([[40.0, 0.0, 20.0], [0.0, 40.0, 20.0], [0.0, 0.0, 1.0]]),
            T_world_camera=transform,
            robot_state={
                "robot0_joint_pos": [0.0] * 7,
                "robot0_gripper_qpos": [0.0, 0.0],
                "robot0_eef_pos": [0.0, 0.0, 1.0],
                "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
            },
            calibration_version="test",
        )
        bounds = WorkspaceBounds(x=(-1.0, 1.0), y=(-1.0, 1.0), z=(0.7, 1.2))
        plane = dominant_horizontal_plane(frame, bounds)
        proposals = foreground_proposals(frame, plane, bounds, min_pixels=10)
        self.assertEqual([proposal.pixel_count for proposal in proposals], [25, 56])
        self.assertEqual([proposal.pixel_bbox_xyxy for proposal in proposals], [(5, 5, 10, 10), (20, 22, 28, 29)])
        self.assertTrue(all(proposal.source == "rgbd_height_component" for proposal in proposals))


if __name__ == "__main__":
    unittest.main()
