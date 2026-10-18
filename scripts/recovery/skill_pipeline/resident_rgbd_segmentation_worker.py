"""Persistent SAM2 process; detector runs in its isolated persistent HF worker."""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True)
    args=p.parse_args()
    import numpy as np
    import torch
    from PIL import Image
    from types import SimpleNamespace
    from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
    from experiments.robot.libero.skill_pipeline.resident_vision import reply
    torch.set_num_threads(2)
    config=json.loads(Path(args.config).read_text())
    detector=GroundedSam2Detector(**config)
    reply(dict(ready=True,device=config['device']))
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if request.get('shutdown'):break
            rgb=np.array(Image.open(request['rgb']).convert('RGB'))
            if config['device'].startswith('cuda'):torch.cuda.synchronize()
            start=time.perf_counter()
            detections=detector(SimpleNamespace(rgb=rgb))
            if config['device'].startswith('cuda'):torch.cuda.synchronize()
            elapsed=(time.perf_counter()-start)*1000
            masks=np.stack([d.mask for d in detections]) if detections else np.zeros((0,*rgb.shape[:2]),bool)
            np.savez_compressed(request['output'],masks=masks)
            reply(dict(ok=True,categories=[d.category for d in detections],
                scores=[d.raw_score for d in detections],vision_ms=elapsed,
                dino_ms=getattr(detector,'last_dino_ms',None)))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            reply(dict(error=traceback.format_exc()))
    if hasattr(detector,'_resident_dino'):detector._resident_dino.close()


if __name__=='__main__':main()
