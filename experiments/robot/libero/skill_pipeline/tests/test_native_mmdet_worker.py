from pathlib import Path
import json,os,tempfile,unittest
from unittest.mock import patch
import numpy as np
from scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker import prediction_payload
from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector


class NativeMMDetectionTest(unittest.TestCase):
    def test_native_label_ids_follow_actual_query_order(self):
        result=prediction_payload([[0,0,4,4],[5,0,9,4],[0,6,4,9]],[.9,.8,.1],[1,1,0],{'sauce':'bbq sauce','basket':'basket'},.25)
        self.assertEqual(result['text_labels'],['basket','basket'])
        self.assertEqual(len(result['boxes']),2)

    def test_out_of_range_label_is_not_reassigned(self):
        with self.assertRaisesRegex(ValueError,'outside requested caption'):
            prediction_payload([[0,0,4,4]],[.9],[2],{'basket':'basket'},.25)

    def test_native_route_never_passes_hf_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            class Worker:
                def __init__(self,argv,**kwargs):calls.append(argv)
                def request(self,payload):
                    Path(payload['output']).write_text(json.dumps(dict(boxes=[[0,0,4,4]],scores=[.9],text_labels=['basket'],dino_ms=1)))
            obj=GroundedSam2Detector.__new__(GroundedSam2Detector)
            obj.dino_worker_python='native_python';obj.mmdet_native_config='native_config.py';obj.export_directory='trained.pth';obj.device='cpu';obj.box_threshold=.25
            env=dict(DINO_INFERENCE_WORKDIR=tmp,DINO_INFERENCE_PYTHONPATH=tmp,DINO_RESIDENT_WORKER='1',ANCHOR_VISUAL_CODE=tmp)
            with patch.dict(os.environ,env),patch('experiments.robot.libero.skill_pipeline.resident_vision.JSONLineProcess',Worker):
                result=obj._worker_ground_image(np.zeros((12,12,3),np.uint8),{'basket':'basket'})
            self.assertIn('scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker',calls[0])
            self.assertIn('--checkpoint',calls[0]);self.assertNotIn('--export',calls[0])
            self.assertEqual(result['text_labels'],['basket'])


if __name__=='__main__':unittest.main()
