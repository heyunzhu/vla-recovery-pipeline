from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from experiments.robot.libero.skill_pipeline.libero_rgbd_sensor import capture_libero_rgbd


class LiberoRGBDSensorTest(unittest.TestCase):
    def test_normalized_depth_and_opengl_orientation_share_pixels(self) -> None:
        robosuite = types.ModuleType("robosuite")
        robosuite.__version__ = "1.4.1"
        robosuite.__path__ = []
        robosuite.macros = types.SimpleNamespace(IMAGE_CONVENTION="opengl")
        utilities = types.ModuleType("robosuite.utils")
        utilities.__path__ = []
        camera_utils = types.ModuleType("robosuite.utils.camera_utils")
        camera_utils.get_camera_intrinsic_matrix = lambda sim, name, h, w: np.asarray(
            [[2.0, 0.0, 1.0], [0.0, 2.0, 1.0], [0.0, 0.0, 1.0]]
        )
        camera_utils.get_camera_extrinsic_matrix = lambda sim, name: np.eye(4)
        camera_utils.get_real_depth_map = lambda sim, depth: 0.1 / (1.0 - depth * 0.99)
        sim = types.SimpleNamespace(data=types.SimpleNamespace(time=0.25))
        env = types.SimpleNamespace(sim=sim)
        obs = {
            "agentview_image": np.asarray(
                [[[255, 0, 0], [255, 0, 0]], [[0, 255, 0], [0, 255, 0]]], dtype=np.uint8
            ),
            "agentview_depth": np.asarray([[[0.5], [1.0]], [[0.25], [0.75]]], dtype=np.float32),
            "robot0_joint_pos": np.zeros(7),
            "robot0_gripper_qpos": np.zeros(2),
            "robot0_eef_pos": np.zeros(3),
            "robot0_eef_quat": np.asarray([0.0, 0.0, 0.0, 1.0]),
            "object_hidden_pos": np.asarray([9.0, 9.0, 9.0]),
        }
        with patch.dict(
            sys.modules,
            {"robosuite": robosuite, "robosuite.utils": utilities, "robosuite.utils.camera_utils": camera_utils},
        ):
            frame = capture_libero_rgbd(env, obs, episode_id="ep", env_step=0, camera_id="agentview")
        np.testing.assert_array_equal(frame.rgb[0, 0], [0, 255, 0])
        self.assertAlmostEqual(float(frame.depth_m[0, 0]), 0.1 / (1.0 - 0.25 * 0.99), places=6)
        self.assertFalse(frame.depth_valid[1, 1])
        self.assertTrue(np.isnan(frame.depth_m[1, 1]))
        self.assertEqual(frame.timestamp_s, 0.25)
        self.assertNotIn("object_hidden_pos", frame.robot_state)


if __name__ == "__main__":
    unittest.main()
