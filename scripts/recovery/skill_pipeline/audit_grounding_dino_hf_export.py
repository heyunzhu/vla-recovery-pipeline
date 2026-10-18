#!/usr/bin/env python3
"""Compare exported HF and MMDetection inference on exactly the same pixels."""
import argparse
import json
from pathlib import Path


def match_detections(left, right, threshold=.25, min_iou=.95, max_score_error=.02):
    """Compare detection sets, without assuming that decoder query order agrees."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    a = left[left.scores >= threshold].cpu()
    b = right[right.scores >= threshold].cpu()
    pairs = []
    for label in sorted(set(a.labels.tolist()) | set(b.labels.tolist())):
        ia = (a.labels == label).nonzero().flatten().numpy()
        ib = (b.labels == label).nonzero().flatten().numpy()
        if not len(ia) or not len(ib):
            continue
        aa, bb = a.bboxes[ia].numpy(), b.bboxes[ib].numpy()
        lo = np.maximum(aa[:, None, :2], bb[None, :, :2])
        hi = np.minimum(aa[:, None, 2:], bb[None, :, 2:])
        intersection = np.maximum(hi-lo, 0).prod(-1)
        area_a = np.maximum(aa[:, 2:]-aa[:, :2], 0).prod(-1)
        area_b = np.maximum(bb[:, 2:]-bb[:, :2], 0).prod(-1)
        overlap = intersection / np.maximum(area_a[:, None]+area_b[None, :]-intersection, 1e-12)
        ii, jj = linear_sum_assignment(-overlap)
        for i, j in zip(ii, jj):
            pairs.append({'label': int(label), 'iou': float(overlap[i, j]),
                          'score_error': abs(float(a.scores[ia[i]])-float(b.scores[ib[j]]))})
    return {'threshold': threshold, 'left_count': len(a), 'right_count': len(b), 'pairs': pairs,
            'within_tolerance': len(a) == len(b) == len(pairs) and
            all(p['iou'] >= min_iou and p['score_error'] <= max_score_error for p in pairs)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True);p.add_argument('--mmdet-config',required=True)
    p.add_argument('--mmdet-checkpoint',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    import torch
    import transformers
    from PIL import Image
    from mmdet.apis import init_detector
    from mmdet.structures import DetDataSample
    from transformers import GroundingDinoForObjectDetection,GroundingDinoProcessor
    from scripts.recovery.skill_pipeline.export_grounding_dino_libero_hf import load_exported_hf_detector
    audit=json.loads((args.export/'export_audit.json').read_text())
    if Path(audit['source_checkpoint']).resolve()!=args.mmdet_checkpoint.resolve():raise ValueError('comparison weights differ')
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    hf=load_exported_hf_detector(args.export,'cuda:0')
    processor=GroundingDinoProcessor.from_pretrained(str(args.export),local_files_only=True)
    mmdet=init_detector(args.mmdet_config,str(args.mmdet_checkpoint),device='cuda:0',palette='random')
    captured={}
    def capture(_module,_inputs,outputs):
        captured['logits']=outputs[0][-1].detach()
        captured['boxes']=outputs[1][-1].detach()
    handle=mmdet.bbox_head.register_forward_hook(capture)
    caption='wine bottle. bowl. plate. basket. rack. cream cheese. milk. orange juice.'
    token_map, normalized_caption, _, _ = mmdet.get_tokens_positive_and_prompts(caption, True)
    assert normalized_caption.strip() == caption, (normalized_caption, caption)
    rows=[]
    for image_path in sorted(args.reference.glob('*.png')):
        image=Image.open(image_path).convert('RGB')
        inputs=processor(images=image,text=caption,return_tensors='pt').to('cuda:0')
        height,width=inputs.pixel_values.shape[-2:]
        sample=DetDataSample()
        sample.set_metainfo(dict(img_shape=(height,width),ori_shape=(image.height,image.width),
            batch_input_shape=(height,width),pad_shape=(height,width),scale_factor=(width/image.width,height/image.height),
            text=caption,custom_entities=True))
        with torch.no_grad():
            result=hf(**inputs,return_dict=True)
            mmdet.predict(inputs.pixel_values,[sample],rescale=False)
            hf_final=mmdet.bbox_head._predict_by_feat_single(result.logits[0],result.pred_boxes[0],token_map,sample.metainfo,rescale=False)
            mm_final=mmdet.bbox_head._predict_by_feat_single(captured['logits'][0],captured['boxes'][0],token_map,sample.metainfo,rescale=False)
        a,b=result.logits,captured['logits'];finite=torch.isfinite(a)&torch.isfinite(b)
        large_box_difference=(result.pred_boxes-captured['boxes']).abs().amax(-1)[0]>.005
        query_scores=torch.stack([a[0,:,ids].sigmoid().mean(-1) for ids in token_map.values()],-1).amax(-1)
        mm_query_scores=torch.stack([b[0,:,ids].sigmoid().mean(-1) for ids in token_map.values()],-1).amax(-1)
        row={'image':image_path.name,'nonfinite_mask_equal':bool(torch.equal(torch.isfinite(a),torch.isfinite(b))),
            'max_abs_finite_logit':float((a[finite]-b[finite]).abs().max()),
            'max_abs_sigmoid_score':float((a.sigmoid()-b.sigmoid()).abs().max()),
            'max_abs_normalized_box':float((result.pred_boxes-captured['boxes']).abs().max()),
            'export_boxes_finite':bool(result.pred_boxes.isfinite().all()),
            'large_box_difference_query_count':int(large_box_difference.sum()),
            'maximum_entity_score_among_large_box_differences':float(torch.maximum(query_scores,mm_query_scores)[large_box_difference].max()) if large_box_difference.any() else None,
            'effective_detections': [match_detections(hf_final,mm_final,t) for t in (.25,.5)]}
        rows.append(row);print(json.dumps(row),flush=True)
    handle.remove()
    summary={'transformers':transformers.__version__,'torch':torch.__version__,'images':len(rows),'rows':rows,
        'same_pixels':True,'head_scale_applied':True,'roundtrip_equal_tensors':audit['roundtrip_equal_tensors'],
        'max_abs_normalized_box':max(r['max_abs_normalized_box'] for r in rows),
        'max_abs_sigmoid_score':max(r['max_abs_sigmoid_score'] for r in rows)}
    summary['raw_query_within_tolerance']=all(r['nonfinite_mask_equal'] and r['export_boxes_finite'] for r in rows) and summary['max_abs_normalized_box']<.005 and summary['max_abs_sigmoid_score']<.02
    summary['effective_detection_within_tolerance']=bool(rows) and all(m['within_tolerance'] for r in rows for m in r['effective_detections'])
    summary['within_tolerance']=summary['effective_detection_within_tolerance']
    summary['criteria']={'same_class_set_matching':True,'minimum_iou':.95,'maximum_score_error':.02,'thresholds':[.25,.5], 'raw_query_order_is_diagnostic':True}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)
    if not summary['within_tolerance']:raise RuntimeError('export inference differs; inspect report before using export')


if __name__=='__main__':main()
