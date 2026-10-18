"""Record effective HF detections for cross-version runtime comparison."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',default='cpu')
    args=p.parse_args()
    import torch
    import transformers
    from PIL import Image
    from transformers import GroundingDinoProcessor
    from scripts.recovery.skill_pipeline.export_grounding_dino_libero_hf import load_exported_hf_detector
    from scripts.recovery.skill_pipeline.grounding_dino_entity_postprocess import entity_token_indices,entity_detections
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    model=load_exported_hf_detector(args.export,args.device)
    processor=GroundingDinoProcessor.from_pretrained(str(args.export),local_files_only=True)
    classes=['wine bottle','bowl','plate','basket','rack','cream cheese','milk','orange juice']
    caption='. '.join(classes)+'.'
    ids=entity_token_indices(processor.tokenizer,caption,classes)
    rows=[]
    for path in sorted(args.reference.glob('*.png')):
        rgb=Image.open(path).convert('RGB')
        inputs=processor(images=rgb,text=caption,return_tensors='pt').to(args.device)
        with torch.no_grad():
            output=model(**inputs,return_dict=True)
            boxes,scores,labels=entity_detections(output.logits[0],output.pred_boxes[0],ids,(rgb.height,rgb.width))
        keep=scores>=.25
        row={'image':path.name,'rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),
             'pixel_values_sha256':hashlib.sha256(inputs.pixel_values.cpu().numpy().tobytes()).hexdigest(),
             'boxes':boxes[keep].cpu().tolist(),'scores':scores[keep].cpu().tolist(),'labels':labels[keep].cpu().tolist()}
        rows.append(row)
        print(json.dumps({'completed':len(rows),'image':path.name,'detections':len(row['scores'])}),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'torch':torch.__version__,'transformers':transformers.__version__,
        'device':args.device,'caption':caption,'token_indices':ids,'rows':rows},indent=2))


if __name__=='__main__':main()
