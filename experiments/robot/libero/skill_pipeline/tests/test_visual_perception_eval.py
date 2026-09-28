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


if __name__ == "__main__":
    unittest.main()
