"""Boundary checks for converted detector scoring and export acceptance."""
import unittest

try:
    import torch
except ImportError:
    torch = None
from types import SimpleNamespace

from scripts.recovery.skill_pipeline.audit_grounding_dino_hf_export import match_detections
from scripts.recovery.skill_pipeline.grounding_dino_entity_postprocess import entity_detections


class DetectionBatch(SimpleNamespace):
    def __getitem__(self, index):
        return DetectionBatch(**{k:v[index] for k,v in vars(self).items()})

    def cpu(self):
        return DetectionBatch(**{k:v.cpu() for k,v in vars(self).items()})

    def __len__(self):
        return len(self.scores)


@unittest.skipIf(torch is None, 'optional detector runtime is absent')
class ExportDetectionTests(unittest.TestCase):
    def detections(self, boxes, labels, scores):
        return DetectionBatch(bboxes=torch.tensor(boxes, dtype=torch.float32),
                            labels=torch.tensor(labels), scores=torch.tensor(scores))

    def test_query_permutation_does_not_fail_effective_detection_check(self):
        a = self.detections([[0,0,10,10],[20,20,40,40]], [0,1], [.9,.8])
        b = self.detections([[20,20,40,40],[0,0,10,10]], [1,0], [.8,.9])
        self.assertTrue(match_detections(a,b)['within_tolerance'])

    def test_wrong_class_missing_instance_and_changed_geometry_are_rejected(self):
        a = self.detections([[0,0,10,10]], [0], [.9])
        for b in (self.detections([[0,0,10,10]], [1], [.9]),
                  self.detections([[0,0,10,10]], [0], [.2]),
                  self.detections([[5,5,15,15]], [0], [.9])):
            self.assertFalse(match_detections(a,b)['within_tolerance'])

    def test_multiword_mean_and_image_coordinate_scaling(self):
        probabilities = torch.tensor([[.9,.1,.7],[.8,.8,.2]])
        logits = torch.logit(probabilities)
        boxes = torch.tensor([[.5,.5,1.,1.],[.5,.5,.2,.4]])
        xyxy, scores, labels = entity_detections(logits, boxes, [[0,1],[2]], (100,200), topk=2)
        self.assertEqual(labels.tolist(), [0,1])
        self.assertTrue(torch.allclose(scores,torch.tensor([.8,.7])))
        self.assertTrue(torch.allclose(xyxy,torch.tensor([[80,30,120,70],[0,0,200,100.]])))


if __name__ == '__main__':
    unittest.main()
