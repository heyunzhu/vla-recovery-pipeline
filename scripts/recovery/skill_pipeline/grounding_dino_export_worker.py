"""Isolated, pinned HF 4.40 detector; accepts RGB and explicit class prompts only."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--rgb',type=Path,required=True)
    p.add_argument('--prompts',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',default='cpu')
    p.add_argument('--threshold',type=float,default=.25)
    args=p.parse_args()
    import torch
    import transformers
    from PIL import Image
    from transformers import GroundingDinoProcessor
    from scripts.recovery.skill_pipeline.export_grounding_dino_libero_hf import load_exported_hf_detector
    from scripts.recovery.skill_pipeline.grounding_dino_entity_postprocess import entity_token_indices,entity_detections
    if transformers.__version__!='4.40.2':raise RuntimeError('worker requires validated transformers==4.40.2')
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    prompts=json.loads(args.prompts.read_text())
    classes=list(prompts.values());caption='. '.join(classes)+'.'
    model=load_exported_hf_detector(args.export,args.device)
    processor=GroundingDinoProcessor.from_pretrained(str(args.export),local_files_only=True)
    ids=entity_token_indices(processor.tokenizer,caption,classes)
    rgb=Image.open(args.rgb).convert('RGB')
    inputs=processor(images=rgb,text=caption,return_tensors='pt').to(args.device)
    with torch.no_grad():
        result=model(**inputs,return_dict=True)
        boxes,scores,labels=entity_detections(result.logits[0],result.pred_boxes[0],ids,(rgb.height,rgb.width))
    keep=scores>=args.threshold
    output={'boxes':boxes[keep].cpu().tolist(),'scores':scores[keep].cpu().tolist(),
        'text_labels':[classes[i] for i in labels[keep].tolist()],
        'provenance':{'transformers':transformers.__version__,'torch':torch.__version__,
            'export':str(args.export),'caption':caption,'threshold':args.threshold,
            'rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),
            'pixel_values_sha256':hashlib.sha256(inputs.pixel_values.cpu().numpy().tobytes()).hexdigest()}}
    args.output.write_text(json.dumps(output,indent=2))


if __name__=='__main__':main()
