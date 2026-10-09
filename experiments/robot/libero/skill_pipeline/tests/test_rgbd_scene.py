from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.rgbd_scene import RGBDSceneTracker, VisualDetection


def _frame(step: int, *, invalid: bool = False) -> RGBDObservation:
    transform = np.diag([1.0, -1.0, -1.0, 1.0])
    transform[:3, 3] = [0.0, 0.0, 1.5]
    return RGBDObservation(
        episode_id="episode_a",
        env_step=step,
        timestamp_s=step * 0.05,
        camera_id="agentview",
        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
        depth_m=np.full((32, 32), 0.5, dtype=np.float32),
        depth_valid=np.zeros((32, 32), dtype=bool) if invalid else np.ones((32, 32), dtype=bool),
        K=np.asarray([[32.0, 0.0, 16.0], [0.0, 32.0, 16.0], [0.0, 0.0, 1.0]]),
        T_world_camera=transform,
        robot_state={
            "robot0_joint_pos": [0.0] * 7,
            "robot0_gripper_qpos": [0.0, 0.0],
            "robot0_eef_pos": [0.0, 0.0, 1.0],
            "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
        },
        calibration_version="test",
    )


def _detection(x: int, *, category: str | None = "bowl", source: str = "text_guided_segmentation") -> VisualDetection:
    mask = np.zeros((32, 32), dtype=bool)
    mask[12:18, x : x + 5] = True
    return VisualDetection(mask=mask, category=category, raw_score=0.7, source=source)


class RGBDSceneTrackerTest(unittest.TestCase):
    def test_tracks_same_category_instances_without_renumbering(self) -> None:
        tracker = RGBDSceneTracker()
        first = tracker.update(_frame(0), [_detection(3), _detection(22)])
        self.assertEqual([obj.id for obj in first.objects], ["obj_001", "obj_002"])
        self.assertTrue(all(obj.identity_status == "new" for obj in first.objects))
        second = tracker.update(_frame(1), [_detection(23), _detection(4)])
        self.assertEqual([obj.id for obj in second.objects], ["obj_002", "obj_001"])
        self.assertTrue(all(obj.identity_status == "tracked" for obj in second.objects))
        self.assertEqual([obj.detection_index for obj in second.objects], [0, 1])
        self.assertTrue(all(len(obj.detection_mask_sha256) == 64 for obj in second.objects))
        third = tracker.update(_frame(2), [_detection(5)])
        unseen = next(obj for obj in third.objects if obj.id == "obj_002")
        self.assertEqual(unseen.validity, "not_observed")
        self.assertEqual(unseen.identity_status, "history_only")
        self.assertEqual(unseen.last_seen_step, 1)
        self.assertIsNone(unseen.detection_index)
        self.assertIsNone(unseen.detection_mask_sha256)

    def test_ambiguous_identity_and_missing_depth_do_not_become_bound_objects(self) -> None:
        tracker = RGBDSceneTracker(ambiguity_margin_m=0.03)
        tracker.update(_frame(0), [_detection(10), _detection(16)])
        ambiguous = tracker.update(_frame(1), [_detection(13)])
        self.assertEqual(ambiguous.objects[0].identity_status, "ambiguous")
        self.assertTrue(ambiguous.objects[0].id.startswith("candidate_"))
        self.assertEqual(sum(obj.validity == "not_observed" for obj in ambiguous.objects), 2)
        missing = tracker.update(_frame(2, invalid=True), [_detection(13)])
        self.assertEqual(missing.objects[0].validity, "depth_insufficient")
        self.assertIsNone(missing.objects[0].visible_centroid_world_m)

    def test_rejects_oracle_source_and_unlabeled_height_semantics(self) -> None:
        with self.assertRaisesRegex(ValueError, "source"):
            _detection(3, source="mujoco_segmentation")
        with self.assertRaisesRegex(ValueError, "cannot supply semantic"):
            _detection(3, source="rgbd_height_component")
        tracker = RGBDSceneTracker()
        scene = tracker.update(_frame(0), [_detection(3, category=None, source="rgbd_height_component")])
        self.assertEqual(scene.objects[0].identity_status, "unbound")
        with self.assertRaisesRegex(ValueError, "advance"):
            tracker.update(_frame(0), [])

    def test_overlapping_masks_remain_separate_objects(self) -> None:
        tracker = RGBDSceneTracker()
        scene = tracker.update(_frame(0), [_detection(3), _detection(4)])
        self.assertEqual([obj.id for obj in scene.objects], ["obj_001", "obj_002"])
        self.assertTrue(all(obj.validity == "observed" for obj in scene.objects))


if __name__ == "__main__":
    unittest.main()
