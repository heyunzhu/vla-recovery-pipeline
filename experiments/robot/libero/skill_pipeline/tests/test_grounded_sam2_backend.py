from __future__ import annotations

import unittest
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np

from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector, _resolve_grounded_boxes


class GroundedBoxesTest(unittest.TestCase):
    def fake_detector(self, mode, results):
        queries = []
        class Inputs(dict):
            input_ids = None
            def to(self, device):
                return self
        class Processor:
            def __call__(self, **kwargs):
                queries.append(kwargs['text'])
                return Inputs()
            def post_process_grounded_object_detection(self, *args, **kwargs):
                return [results.pop(0)]
        detector = GroundedSam2Detector.__new__(GroundedSam2Detector)
        detector.prompts = {'bowl': 'black bowl', 'ramekin': 'silver ramekin'}
        detector.grounding_mode = mode
        detector.device = 'cpu'
        detector.box_threshold = detector.text_threshold = 0.25
        detector._torch = SimpleNamespace(no_grad=nullcontext)
        detector.grounding_processor = Processor()
        detector.grounding_model = lambda **kwargs: None
        return detector, queries

    def test_separate_queries_do_not_borrow_labels_from_another_category(self):
        result = {'boxes': np.array([[0, 0, 5, 5], [6, 0, 11, 5]]),
                  'scores': np.array([0.5, 0.9]),
                  'text_labels': ['black bowl', 'silver ramekin']}
        detector, queries = self.fake_detector('per_category', [result, result])
        boxes, categories, scores = detector._ground_image(np.zeros((12, 12, 3)), (12, 12))
        self.assertEqual(queries, [[['black bowl']], [['silver ramekin']]])
        self.assertEqual(categories, ['bowl', 'ramekin'])
        self.assertEqual(scores, [0.5, 0.9])
        self.assertEqual(len(detector.last_grounding_boxes), 4)
        self.assertEqual(detector.last_grounding_boxes[2]['query_category'], 'ramekin')

    def test_joint_mode_preserves_mixed_label_rejection_and_all_instances(self):
        result = {'boxes': np.array([[0, 0, 5, 5], [6, 0, 11, 5], [0, 6, 5, 11]]),
                  'scores': np.array([0.5, 0.7, 0.9]),
                  'text_labels': ['black bowl', 'black bowl', 'black bowl silver ramekin']}
        detector, queries = self.fake_detector('joint', [result])
        boxes, categories, scores = detector._ground_image(np.zeros((12, 12, 3)), (12, 12))
        self.assertEqual(queries, [[['black bowl', 'silver ramekin']]])
        self.assertEqual(categories, ['bowl', 'bowl'])
        self.assertEqual(len(detector.last_grounding_boxes), 3)
        self.assertNotIn('query_category', detector.last_grounding_boxes[0])

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
