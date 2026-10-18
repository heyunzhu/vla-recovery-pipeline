#!/usr/bin/env python3
"""Review a new detector implementation on the frozen nine diagnostic frames."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--checkpoint',required=True)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fixed-classes',action='store_true')
    args=p.parse_args()
    from mmengine.config import Config
    from mmcv.transforms import Compose
    from mmdet.apis import init_detector,inference_detector
    from PIL import Image,ImageDraw
    cfg=Config.fromfile(args.config)
    model=init_detector(cfg,args.checkpoint,device='cuda:0',palette='random')
    pipeline=Compose([t for t in cfg.test_dataloader.dataset.pipeline if t.type!='LoadAnnotations'])
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in json.loads((args.reference/'manifest.json').read_text())['cases']:
        for mode in (('fixed_eight',) if args.fixed_classes else ('full_joint','task_joint')):
            native=None
            if args.fixed_classes:
                caption='wine bottle. bowl. plate. basket. rack. cream cheese. milk. orange juice.'
            else:
                native=json.loads((args.reference/f"{case['case']}_{mode}.json").read_text())
                caption=native['caption']
            result=inference_detector(model,str(args.reference/(case['case']+'.png')),test_pipeline=pipeline,text_prompt=caption,custom_entities=True)
            pred=result.pred_instances.cpu();image=Image.open(args.reference/(case['case']+'.png')).convert('RGB');draw=ImageDraw.Draw(image)
            boxes=[]
            for box,score,label,name in zip(pred.bboxes.tolist(),pred.scores.tolist(),pred.labels.tolist(),pred.label_names):
                if score<.25:continue
                boxes.append(dict(box_xyxy=box,score=score,label=label,text_label=name))
                draw.rectangle(box,outline='lime',width=2);draw.text((box[0],max(0,box[1]-12)),f'{name} {score:.2f}',fill='lime',stroke_width=1,stroke_fill='black')
            image.save(args.output/f"{case['case']}_{mode}.png")
            row=dict(case=case['case'],mode=mode,caption=caption,mmdet_boxes=boxes)
            if native is not None:row['native_boxes']=native['native_boxes']
            rows.append(row);print(json.dumps(row),flush=True)
    (args.output/'summary.json').write_text(json.dumps({'rows':rows,'checkpoint':args.checkpoint,
        'note':'MMDetection aggregates token scores per entity; upstream native uses max token score and phrase decoding. These outputs are a visual implementation sanity check, not bitwise equivalence or an accuracy metric.'},indent=2))


if __name__=='__main__':main()
