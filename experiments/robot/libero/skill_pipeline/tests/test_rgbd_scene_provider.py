from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider


def _frame(step: int, episode: str = "episode_a", camera: str = "agentview") -> RGBDObservation:
    transform = np.eye(4)
    return RGBDObservation(
        episode_id=episode,
        env_step=step,
        timestamp_s=step * 0.05,
        camera_id=camera,
        rgb=np.zeros((16, 16, 3), dtype=np.uint8),
        depth_m=np.full((16, 16), 0.5, dtype=np.float32),
        depth_valid=np.ones((16, 16), dtype=bool),
        K=np.asarray([[16.0, 0.0, 8.0], [0.0, 16.0, 8.0], [0.0, 0.0, 1.0]]),
        T_world_camera=transform,
        robot_state={
            "robot0_joint_pos": [0.0] * 7,
            "robot0_gripper_qpos": [0.0, 0.0],
            "robot0_eef_pos": [0.0, 0.0, 0.0],
            "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
        },
        calibration_version="test",
    )


class RGBDSceneProviderTest(unittest.TestCase):
    def test_consumers_share_exact_cached_snapshot_and_detector_runs_once(self) -> None:
        calls = []

        def detector(frame):
            calls.append(frame.env_step)
            mask = np.zeros((16, 16), dtype=bool)
            mask[2:8, 2:8] = True
            return [VisualDetection(mask, "bowl", 0.7, "text_guided_segmentation")]

        provider = RGBDSceneProvider(detector, detector_id="test-detector-v1", camera_id="agentview")
        first = provider.get_scene(_frame(0))
        self.assertIs(first, provider.get_scene(_frame(0)))
        self.assertEqual(calls, [0])
        self.assertEqual(first.perception_backend_id, "test-detector-v1")
        self.assertEqual(first.objects[0].id, "obj_001")
        next_scene = provider.get_scene(_frame(1))
        self.assertEqual(next_scene.objects[0].id, "obj_001")
        self.assertEqual(next_scene.objects[0].identity_status, "tracked")
        self.assertEqual(calls, [0, 1])

    def test_rejects_changed_cached_frame_camera_and_episode_without_reset(self) -> None:
        provider = RGBDSceneProvider(lambda _: [], detector_id="empty-v1", camera_id="agentview")
        provider.get_scene(_frame(0))
        changed = _frame(0)
        changed.rgb[0, 0, 0] = 1
        with self.assertRaisesRegex(ValueError, "content changed"):
            provider.get_scene(changed)
        with self.assertRaisesRegex(ValueError, "expected RGB-D camera"):
            provider.get_scene(_frame(1, camera="robot0_eye_in_hand"))
        with self.assertRaisesRegex(ValueError, "reset"):
            provider.get_scene(_frame(0, episode="episode_b"))
        provider.reset()
        self.assertEqual(provider.get_scene(_frame(0, episode="episode_b")).episode_id, "episode_b")

    def test_failed_detection_does_not_cache_or_advance_tracking(self) -> None:
        calls = 0

        def detector(_):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("detector unavailable")
            return []

        provider = RGBDSceneProvider(detector, detector_id="retry-v1", camera_id="agentview")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            provider.get_scene(_frame(0))
        self.assertEqual(provider.get_scene(_frame(0)).env_step, 0)
        self.assertEqual(calls, 2)

    def test_height_only_proposals_remain_unbound(self) -> None:
        mask = np.zeros((16, 16), dtype=bool)
        mask[2:8, 2:8] = True
        provider = RGBDSceneProvider(
            lambda _: [VisualDetection(mask, None, None, "rgbd_height_component")],
            detector_id="height-components-v1",
            camera_id="agentview",
        )
        item = provider.get_scene(_frame(0)).objects[0]
        self.assertIsNone(item.category)
        self.assertEqual(item.identity_status, "unbound")

    def test_conflicting_masks_return_cached_refusal_and_do_not_advance_tracker(self) -> None:
        calls = []
        first_mask = np.zeros((16, 16), dtype=bool)
        first_mask[2:8, 2:8] = True
        second_mask = np.zeros((16, 16), dtype=bool)
        second_mask[3:9, 3:9] = True

        def detector(frame):
            calls.append(frame.env_step)
            masks = [first_mask, second_mask] if frame.env_step == 0 else [first_mask]
            return [
                VisualDetection(mask, "bowl" if index == 0 else "ramekin", 0.7, "text_guided_segmentation")
                for index, mask in enumerate(masks)
            ]

        provider = RGBDSceneProvider(detector, detector_id="test-detector-v1", camera_id="agentview")
        refused = provider.get_admission(_frame(0))
        self.assertEqual(refused.status, "refused")
        self.assertEqual(refused.reason, "overlapping_instance_masks")
        self.assertIsNone(refused.scene)
        self.assertEqual(len(refused.mask_conflicts), 1)
        self.assertIs(refused, provider.get_admission(_frame(0)))
        with self.assertRaisesRegex(ValueError, "masks overlap"):
            provider.get_scene(_frame(0))
        self.assertEqual(calls, [0])
        accepted = provider.get_admission(_frame(1))
        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(accepted.scene.objects[0].id, "obj_001")
        self.assertEqual(calls, [0, 1])


if __name__ == "__main__":
    unittest.main()
