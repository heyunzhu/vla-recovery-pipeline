from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.robot.libero.skill_pipeline.perception_artifact import (
    load_detections,
    rgb_sha256,
    save_detections,
)
from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation
from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
from experiments.robot.libero.skill_pipeline.visual_perception_eval import (
    evaluate_reference_points,
    load_visual_reference,
)


def _frame() -> RGBDObservation:
    return RGBDObservation(
        episode_id="test",
        env_step=0,
        timestamp_s=0.0,
        camera_id="agentview",
        rgb=np.zeros((12, 12, 3), dtype=np.uint8),
        depth_m=np.ones((12, 12), dtype=np.float32),
        depth_valid=np.ones((12, 12), dtype=bool),
        K=np.asarray([[12.0, 0.0, 6.0], [0.0, 12.0, 6.0], [0.0, 0.0, 1.0]]),
        T_world_camera=np.eye(4),
        robot_state={
            "robot0_joint_pos": [0.0] * 7,
            "robot0_gripper_qpos": [0.0, 0.0],
            "robot0_eef_pos": [0.0, 0.0, 0.0],
            "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
        },
        calibration_version="test",
    )


def _mask(*points: tuple[int, int]) -> np.ndarray:
    mask = np.zeros((12, 12), dtype=bool)
    for x, y in points:
        mask[y, x] = True
    return mask


def _reference(frame: RGBDObservation) -> dict:
    return {
        "reference_schema_version": 1,
        "episode_id": frame.episode_id,
        "env_step": frame.env_step,
        "camera_id": frame.camera_id,
        "image_shape_hw": [12, 12],
        "rgb_sha256": rgb_sha256(frame),
        "instances": [
            {"reference_id": "bowl_a", "category": "bowl", "point_xy": [2, 3]},
            {"reference_id": "bowl_b", "category": "bowl", "point_xy": [8, 3]},
            {"reference_id": "plate", "category": "plate", "point_xy": [6, 9]},
        ],
    }


class PerceptionArtifactTest(unittest.TestCase):
    def test_roundtrip_checks_image_identity_and_preserves_separate_instances(self) -> None:
        frame = _frame()
        detections = [
            VisualDetection(_mask((2, 3)), "bowl", 0.8, "text_guided_segmentation"),
            VisualDetection(_mask((8, 3)), "bowl", 0.7, "text_guided_segmentation"),
            VisualDetection(_mask((6, 9)), "plate", 0.6, "text_guided_segmentation"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            save_detections(frame, detections, temp, detector_id="frozen-v1")
            detector_id, replay = load_detections(frame, temp)
            self.assertEqual(detector_id, "frozen-v1")
            self.assertEqual([item.category for item in replay], ["bowl", "bowl", "plate"])
            self.assertTrue(evaluate_reference_points(frame, replay, _reference(frame))["passed"])
            changed = _frame()
            changed.rgb[0, 0, 0] = 1
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_detections(changed, temp)

    def test_merged_mask_and_unknown_category_fail_separation_gate(self) -> None:
        frame = _frame()
        merged = [
            VisualDetection(_mask((2, 3), (8, 3)), "bowl", 0.8, "text_guided_segmentation"),
            VisualDetection(_mask((6, 9)), "plate", 0.6, "text_guided_segmentation"),
        ]
        result = evaluate_reference_points(frame, merged, _reference(frame))
        self.assertFalse(result["passed"])
        self.assertEqual(result["status_counts"]["merged"], 2)
        self.assertEqual(result["shared_raw_mask_groups"][0]["reference_ids"], ["bowl_a", "bowl_b"])
        unknown = [VisualDetection(_mask((2, 3)), None, None, "rgbd_height_component")]
        self.assertEqual(evaluate_reference_points(frame, unknown, _reference(frame))["status_counts"]["missing"], 3)

    def test_visual_reference_rejects_wrong_frame(self) -> None:
        frame = _frame()
        reference = _reference(frame)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reference.json"
            path.write_text(json.dumps(reference), encoding="utf-8")
            self.assertEqual(len(load_visual_reference(frame, path)["instances"]), 3)
            reference["rgb_sha256"] = "wrong"
            path.write_text(json.dumps(reference), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_visual_reference(frame, path)


if __name__ == "__main__":
    unittest.main()
