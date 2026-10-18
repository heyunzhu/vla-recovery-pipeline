#!/usr/bin/env python3
"""Export detections and evaluate fixed LIBERO splits without tuning on test."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import re
from pathlib import Path
import sys

import numpy as np


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0]+a[2], b[0]+b[2]), min(a[1]+a[3], b[1]+b[3])
    area = max(0, x2-x1)*max(0, y2-y1)
    return area/max(1e-12, a[2]*a[3]+b[2]*b[3]-area)


def detection_metrics(annotation, predictions, threshold, root=None, resolution=640):
    gt, pred = defaultdict(list), defaultdict(list)
    names = {c["id"]: c["name"] for c in annotation["categories"]}
    for a in annotation["annotations"]: gt[a["image_id"]].append(a)
    for p in predictions:
        if p["score"] >= threshold: pred[p["image_id"]].append(p)
    stats = {c: Counter() for c in names}
    pairs = Counter(); task_sets = Counter()
    aliases = {}
    if root is not None and (root / "taxonomy.json").exists():
        aliases = json.loads((root / "taxonomy.json").read_text()).get("aliases", {})
    for image in annotation["images"]:
        used = set()
        matched_names = set()
        robot_mask = None
        if root is not None:
            from PIL import Image
            robot_mask = np.array(Image.open(root/f"instance_masks{resolution}"/(Path(image["file_name"]).stem+".png"))) == 65535
        for p in sorted(pred[image["id"]], key=lambda x: -x["score"]):
            options = [(iou(p["bbox"], a["bbox"]), j) for j,a in enumerate(gt[image["id"]])
                       if j not in used and a["category_id"] == p["category_id"]]
            overlap, index = max(options, default=(0, -1))
            counts = stats[p["category_id"]]
            if overlap >= .5:
                counts["tp"] += 1
                used.add(index)
                matched_names.add(gt[image["id"]][index].get("instance_name"))
            else:
                counts["fp"] += 1
                if robot_mask is not None:
                    x,y,w,h = p["bbox"]
                    x1,y1 = max(0,int(np.floor(x))),max(0,int(np.floor(y)))
                    x2,y2 = min(resolution,int(np.ceil(x+w))),min(resolution,int(np.ceil(y+h)))
                    crop = robot_mask[y1:y2,x1:x2]
                    # Explicit proxy: majority of clipped predicted box pixels are robot.
                    if crop.size and float(crop.mean()) >= .5: counts["robot_majority_fp"] += 1
        for j,a in enumerate(gt[image["id"]]):
            if j not in used: stats[a["category_id"]]["fn"] += 1
        visible = {a.get("instance_name") for a in gt[image["id"]]}
        text = " ".join(image.get("task_language", "").lower().split())
        required = {name for name in names.values() if any(
            re.search(r"\b" + re.escape(alias) + r"\b", text)
            for alias in aliases.get(name, [name]))}
        visible_categories = {names[a["category_id"]] for a in gt[image["id"]]}
        matched_categories = {names[a["category_id"]] for a in gt[image["id"]] if a.get("instance_name") in matched_names}
        if required:
            task_sets["annotated"] += 1
            if required <= visible_categories:
                task_sets["all_visible"] += 1
                task_sets["all_correct"] += required <= matched_categories
        for pair in image.get("goal_role_pairs", []):
            target, goal = pair["target_instance"], pair["goal_instance"]
            pairs["annotated"] += 1
            if target in visible and goal in visible:
                pairs["both_visible"] += 1
                if target in matched_names and goal in matched_names: pairs["both_correct"] += 1

    def rates(counts):
        tp,fp,fn = counts["tp"],counts["fp"],counts["fn"]
        return {**{k:counts[k] for k in ("tp","fp","fn","robot_majority_fp")}, "precision":tp/max(1,tp+fp), "recall":tp/max(1,tp+fn), "f1":2*tp/max(1,2*tp+fp+fn)}
    total = sum(stats.values(), Counter())
    return {"threshold":float(threshold), "overall":rates(total), "per_class":{names[k]:rates(v) for k,v in stats.items()},
            "task_category_sets": {**dict(task_sets), "success_rate": task_sets["all_correct"]/max(1,task_sets["all_visible"]),
                "definition": "All task-mentioned category types have an IoU-matched instance; not semantic instance binding accuracy"},
            "goal_role_pairs":{**{k:pairs[k] for k in ("annotated","both_visible","both_correct")}, "success_rate":pairs["both_correct"]/max(1,pairs["both_visible"])},
            "robot_fp_definition":"unmatched prediction with >=50% robot pixels inside its clipped bbox"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True);parser.add_argument("--checkpoint",type=Path,required=True)
    parser.add_argument("--dataset",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--split",choices=("val","test"),required=True);parser.add_argument("--resolution",type=int,choices=(256,640),default=640)
    parser.add_argument("--calibration",type=Path,help="Required for test; generated using validation predictions only")
    parser.add_argument("--device",default="cuda:0");parser.add_argument("--limit",type=int,default=0)
    parser.add_argument("--hf-export",type=Path,help="Audited local converted weights; use entity-mean scoring")
    args=parser.parse_args()
    if args.split=="test" and not args.calibration: parser.error("test requires --calibration from validation")
    annotation=json.loads((args.dataset/f"annotations/{args.split}{args.resolution}.json").read_text())
    if args.limit: annotation["images"]=annotation["images"][:args.limit]
    ids={i["id"] for i in annotation["images"]}
    annotation["annotations"]=[a for a in annotation["annotations"] if a["image_id"] in ids]
    args.output.mkdir(parents=True,exist_ok=True)
    caption=". ".join(c["name"] for c in annotation["categories"])+"."
    backend='hf_entity_mean' if args.hf_export else 'mmdetection'
    export_sha=None
    if args.hf_export:
        import torch
        from PIL import Image
        from transformers import GroundingDinoProcessor
        from scripts.recovery.skill_pipeline.export_grounding_dino_libero_hf import load_exported_hf_detector
        from scripts.recovery.skill_pipeline.grounding_dino_entity_postprocess import entity_token_indices, entity_detections
        audit=json.loads((args.hf_export/'export_audit.json').read_text())
        if Path(audit['source_checkpoint']).resolve()!=args.checkpoint.resolve():raise ValueError('HF export source checkpoint differs')
        export_sha=hashlib.sha256((args.hf_export/'model.safetensors').read_bytes()).hexdigest()
        torch.set_num_threads(2)
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        model=load_exported_hf_detector(args.hf_export,args.device)
        processor=GroundingDinoProcessor.from_pretrained(str(args.hf_export),local_files_only=True)
        token_indices=entity_token_indices(processor.tokenizer,caption,[c['name'] for c in annotation['categories']])
    else:
        from mmengine.config import Config
        from mmcv.transforms import Compose
        from mmdet.apis import init_detector, inference_detector
        cfg=Config.fromfile(str(args.config))
        model=init_detector(cfg,str(args.checkpoint),device=args.device,palette="random")
        pipeline=Compose([t for t in cfg.test_dataloader.dataset.pipeline if t.type!="LoadAnnotations"])
    predictions=[]
    for index,image in enumerate(annotation["images"]):
        if args.hf_export:
            rgb=Image.open(args.dataset/image['file_name']).convert('RGB')
            inputs=processor(images=rgb,text=caption,return_tensors='pt').to(args.device)
            with torch.no_grad():
                result=model(**inputs,return_dict=True)
                boxes,scores,labels=entity_detections(result.logits[0],result.pred_boxes[0],token_indices,(rgb.height,rgb.width))
            arrays=[x.cpu().numpy() for x in (boxes,scores,labels)]
        else:
            result=inference_detector(model,str(args.dataset/image["file_name"]),test_pipeline=pipeline,text_prompt=caption,custom_entities=True)
            pred=result.pred_instances.cpu()
            arrays=(pred.bboxes.numpy(),pred.scores.numpy(),pred.labels.numpy())
        for box,score,label in zip(*arrays):
            x1,y1,x2,y2=map(float,box)
            predictions.append({"image_id":image["id"],"category_id":int(label)+1,"bbox":[x1,y1,max(0,x2-x1),max(0,y2-y1)],"score":float(score)})
        if (index+1)%25==0: print(json.dumps({"completed":index+1,"total":len(annotation["images"])}),flush=True)
    write(args.output/"predictions.json",predictions)
    if args.split=="val":
        sweep=[detection_metrics(annotation,predictions,t) for t in np.arange(.05,.81,.025)]
        best=max(sweep,key=lambda m:(m["overall"]["f1"],m["threshold"]))
        calibration={"split":"val","threshold":best["threshold"],"objective":"micro F1 at IoU .5", "sweep":sweep,
                     "checkpoint":str(args.checkpoint),"resolution":args.resolution,"image_count":len(ids)}
        calibration.update(backend=backend,export_sha256=export_sha)
        write(args.output/"calibration.json",calibration)
    else:
        calibration=json.loads(args.calibration.read_text())
        assert calibration["split"]=="val"
        if calibration["checkpoint"]!=str(args.checkpoint): raise ValueError("calibration checkpoint differs")
        if calibration["resolution"]!=args.resolution: raise ValueError("calibration resolution differs")
        if calibration.get('backend','mmdetection')!=backend or calibration.get('export_sha256')!=export_sha: raise ValueError('calibration inference backend/weights differ')
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval
    coco=COCO();coco.dataset={**annotation,"info":{},"licenses":[]};coco.createIndex()
    result=coco.loadRes(predictions)
    evaluation=COCOeval(coco,result,"bbox");evaluation.params.imgIds=sorted(ids)
    evaluation.evaluate();evaluation.accumulate();evaluation.summarize()
    per_class_ap={}
    for index,category in enumerate(annotation["categories"]):
        precision=evaluation.eval['precision'][:,:,index,0,-1]
        p50=precision[0]
        per_class_ap[category['name']]={'AP':float(precision[precision>=0].mean()) if np.any(precision>=0) else None,
            'AP50':float(p50[p50>=0].mean()) if np.any(p50>=0) else None}
    summary={"split":args.split,"resolution":args.resolution,"images":len(ids),"caption":caption,"backend":backend,"export_sha256":export_sha,
        "per_class_coco":per_class_ap,
        "coco_stats":dict(zip(("AP","AP50","AP75","AP_small","AP_medium","AP_large","AR1","AR10","AR100","AR_small","AR_medium","AR_large"),map(float,evaluation.stats))),
        "fixed_025":detection_metrics(annotation,predictions,.25,args.dataset,args.resolution),
        "validation_calibrated":detection_metrics(annotation,predictions,calibration["threshold"],args.dataset,args.resolution),
        "argv":sys.argv,"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write(args.output/"metrics.json",summary)
    print(json.dumps(summary),flush=True)


if __name__=="__main__":main()
