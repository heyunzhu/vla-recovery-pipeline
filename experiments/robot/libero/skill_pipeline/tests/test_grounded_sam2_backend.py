from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import _resolve_grounded_boxes


class GroundedBoxesTest(unittest.TestCase):
    def test_keeps_two_same_category_instances_and_clips_image_boxes(self) -> None:
        result = {
            "boxes": np.asarray([[-1, 1, 5, 7], [6, 1, 13, 7], [2, 8, 9, 12]]),
            "scores": np.asarray([0.8, 0.7, 0.6]),
            "text_labels": ["black bowl", "a black bowl", "plate"],
        }
        boxes, categories, scores = _resolve_grounded_boxes(
            result, {"bowl": "black bowl", "plate": "plate"}, (12, 12)
        )
        self.assertEqual(categories, ["bowl", "bowl", "plate"])
        self.assertEqual(boxes[0], [0.0, 1.0, 5.0, 7.0])
        self.assertEqual(boxes[1], [6.0, 1.0, 12.0, 7.0])
        self.assertEqual(scores, [0.8, 0.7, 0.6])

    def test_drops_unlisted_labels_and_degenerate_boxes(self) -> None:
        result = {
            "boxes": np.asarray([[0, 0, 5, 5], [3, 3, 3, 6]]),
            "scores": np.asarray([0.8, 0.7]),
            "labels": ["robot", "black bowl"],
        }
        self.assertEqual(_resolve_grounded_boxes(result, {"bowl": "black bowl"}, (12, 12))[0], [])


if __name__ == "__main__":
    unittest.main()
