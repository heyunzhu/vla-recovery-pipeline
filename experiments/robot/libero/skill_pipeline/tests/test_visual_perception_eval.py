from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
from experiments.robot.libero.skill_pipeline.tests.test_rgbd_scene import _frame
from experiments.robot.libero.skill_pipeline.visual_perception_eval import evaluate_reference_points


class VisualPerceptionEvalTest(unittest.TestCase):
    def test_conflicting_masks_fail_even_when_reference_point_matches(self) -> None:
        frame = _frame(0)
        mask = np.zeros((32, 32), dtype=bool)
        mask[10:20, 10:20] = True
        detections = [
            VisualDetection(mask=mask, category="bowl", raw_score=0.7, source="text_guided_segmentation"),
            VisualDetection(mask=mask.copy(), category="ramekin", raw_score=0.5,
                            source="text_guided_segmentation"),
        ]
        reference = {
            "rgb_sha256": rgb_sha256(frame),
            "instances": [{"reference_id": "bowl", "category": "bowl", "point_xy": [15, 15]}],
        }
        result = evaluate_reference_points(frame, detections, reference)
        self.assertEqual(result["status_counts"]["matched"], 1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["mask_conflicts"][0]["overlap_fraction_of_smaller_mask"], 1.0)

    def test_wrong_category_on_negative_point_fails_despite_positive_match(self) -> None:
        frame = _frame(0)
        good = np.zeros((32, 32), dtype=bool)
        good[10:15, 10:15] = True
        distractor = np.zeros((32, 32), dtype=bool)
        distractor[20:25, 20:25] = True
        detections = [
            VisualDetection(good, "plate", 0.8, "text_guided_segmentation"),
            VisualDetection(distractor, "plate", 0.3, "text_guided_segmentation"),
        ]
        reference = {
            "rgb_sha256": rgb_sha256(frame),
            "instances": [{"reference_id": "plate", "category": "plate", "point_xy": [12, 12]}],
            "negative_points": [{"reference_id": "cabinet", "forbidden_category": "plate",
                                 "point_xy": [22, 22]}],
        }
        result = evaluate_reference_points(frame, detections, reference)
        self.assertEqual(result["status_counts"]["matched"], 1)
        self.assertEqual(result["negative_point_hits"][0]["detection_indices"], [1])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
