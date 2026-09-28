from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.robot.libero.skill_pipeline.rgbd_observation import (
    RGBDObservation,
    load_observation,
    save_observation,
    unproject_world,
)


def _observation(**changes: object) -> RGBDObservation:
    values = {
        "episode_id": "task01_ep00",
        "env_step": 12,
        "timestamp_s": 0.6,
        "camera_id": "agentview",
        "rgb": np.zeros((2, 3, 3), dtype=np.uint8),
        "depth_m": np.asarray([[2.0, 2.0, np.nan], [0.0, 2.0, 2.0]], dtype=np.float32),
        "depth_valid": np.asarray([[True, True, False], [False, True, True]]),
        "K": np.asarray([[2.0, 0.0, 1.0], [0.0, 2.0, 0.5], [0.0, 0.0, 1.0]]),
        "T_world_camera": np.asarray(
            [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0], [0.0, 0.0, 0.0, 1.0]]
        ),
        "robot_state": {
            "robot0_joint_pos": [0.0] * 7,
            "robot0_gripper_qpos": [0.03, -0.03],
            "robot0_eef_pos": [0.0, 0.0, 0.8],
            "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
        },
        "calibration_version": "test-v1",
    }
    values.update(changes)
    return RGBDObservation(**values)


class RGBDObservationTest(unittest.TestCase):
    def test_unprojection_uses_optical_z_and_extrinsic(self) -> None:
        points = unproject_world(_observation())
        np.testing.assert_allclose(
            points,
            [[1.0, 1.5, 5.0], [1.0, 2.5, 5.0], [0.0, 2.5, 5.0], [0.0, 3.5, 5.0]],
        )

    def test_replay_is_lossless_and_has_explicit_conventions(self) -> None:
        frame = _observation()
        with tempfile.TemporaryDirectory() as root:
            save_observation(frame, root)
            metadata = json.loads((Path(root) / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["depth_convention"], "optical_z_meters")
            replay = load_observation(root)
        np.testing.assert_array_equal(replay.rgb, frame.rgb)
        np.testing.assert_array_equal(replay.depth_valid, frame.depth_valid)
        np.testing.assert_array_equal(replay.depth_m, frame.depth_m)
        np.testing.assert_array_equal(unproject_world(replay), unproject_world(frame))
        self.assertEqual(replay.robot_state, frame.robot_state)

    def test_rejects_misaligned_and_invalid_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "aligned"):
            _observation(depth_m=np.zeros((3, 2), dtype=np.float32))
        with self.assertRaisesRegex(ValueError, "valid depth"):
            _observation(depth_valid=np.ones((2, 3), dtype=bool))
        with self.assertRaisesRegex(ValueError, "proper rotation"):
            _observation(T_world_camera=np.diag([-1.0, 1.0, 1.0, 1.0]))
        with self.assertRaisesRegex(ValueError, "proprioceptive keys"):
            _observation(robot_state={**_observation().robot_state, "object_pos": [0.0, 0.0, 0.0]})

    def test_rejects_wrong_depth_convention_on_replay(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            save_observation(_observation(), root)
            path = Path(root) / "metadata.json"
            metadata = json.loads(path.read_text(encoding="utf-8"))
            metadata["depth_convention"] = "normalized_depth_buffer"
            path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "optical-Z"):
                load_observation(root)


if __name__ == "__main__":
    unittest.main()
