"""Validated HF 4.40 detector loaded once for successive current RGB frames."""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--export',required=True)
    p.add_argument('--device',default='cuda')
    p.add_argument('--threshold',type=float,default=.25)
    args=p.parse_args()
    import torch,transformers
    from PIL import Image
    from transformers import GroundingDinoProcessor
    from scripts.recovery.skill_pipeline.export_grounding_dino_libero_hf import load_exported_hf_detector
    from scripts.recovery.skill_pipeline.grounding_dino_entity_postprocess import entity_token_indices,entity_detections
    from experiments.robot.libero.skill_pipeline.resident_vision import reply
    assert transformers.__version__=='4.40.2'
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    model=load_exported_hf_detector(Path(args.export),args.device)
    processor=GroundingDinoProcessor.from_pretrained(args.export,local_files_only=True)
    reply(dict(ready=True,transformers=transformers.__version__,device=args.device))
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if request.get('shutdown'):break
            classes=list(json.loads(Path(request['prompts']).read_text()).values())
            caption='. '.join(classes)+'.'
            ids=entity_token_indices(processor.tokenizer,caption,classes)
            image=Image.open(request['rgb']).convert('RGB')
            if args.device.startswith('cuda'):torch.cuda.synchronize()
            start=time.perf_counter()
            inputs=processor(images=image,text=caption,return_tensors='pt').to(args.device)
            with torch.inference_mode():
                result=model(**inputs,return_dict=True)
                boxes,scores,labels=entity_detections(result.logits[0],result.pred_boxes[0],ids,(image.height,image.width))
            keep=scores>=args.threshold
            output=dict(boxes=boxes[keep].cpu().tolist(),scores=scores[keep].cpu().tolist(),
                text_labels=[classes[i] for i in labels[keep].tolist()])
            if args.device.startswith('cuda'):torch.cuda.synchronize()
            output['dino_ms']=(time.perf_counter()-start)*1000
            Path(request['output']).write_text(json.dumps(output))
            reply(dict(ok=True,dino_ms=output['dino_ms']))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            reply(dict(error=traceback.format_exc()))


if __name__=='__main__':main()
