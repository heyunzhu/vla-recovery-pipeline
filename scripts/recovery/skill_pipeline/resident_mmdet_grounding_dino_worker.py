"""Native MMDetection checkpoint inference; no HF conversion or simulator input."""
import argparse,hashlib,json,sys,time,traceback
from pathlib import Path


def reply(payload):
    print('RGBD_REPLY '+json.dumps(payload),flush=True)


def prediction_payload(boxes,scores,labels,prompts,threshold):
    names=list(prompts.values());out=dict(boxes=[],scores=[],text_labels=[])
    for box,score,label in zip(boxes,scores,labels):
        if float(score)<threshold:continue
        index=int(label)
        if index<0 or index>=len(names):raise ValueError('MMDetection label outside requested caption entities')
        out['boxes'].append([float(x) for x in box]);out['scores'].append(float(score));out['text_labels'].append(names[index])
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--checkpoint',required=True)
    p.add_argument('--device',default='cuda');p.add_argument('--threshold',type=float,default=.25)
    p.add_argument('--rgb');p.add_argument('--prompts');p.add_argument('--output');args=p.parse_args()
    import torch,mmcv,mmengine,mmdet
    from mmengine.config import Config
    from mmcv.transforms import Compose
    from mmdet.apis import init_detector,inference_detector
    torch.set_num_threads(2);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    cfg=Config.fromfile(args.config);model=init_detector(cfg,args.checkpoint,device=args.device,palette='random')
    pipeline=Compose([t for t in cfg.test_dataloader.dataset.pipeline if t.type!='LoadAnnotations'])
    provenance=dict(backend='native_mmdetection',torch=torch.__version__,mmcv=mmcv.__version__,mmengine=mmengine.__version__,mmdet=mmdet.__version__,checkpoint_sha256=hashlib.sha256(Path(args.checkpoint).read_bytes()).hexdigest(),config_sha256=hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),hf_conversion_used=False)
    def infer(request):
        prompts=json.loads(Path(request['prompts']).read_text());caption='. '.join(prompts.values())+'.'
        if args.device.startswith('cuda'):torch.cuda.synchronize()
        start=time.perf_counter()
        result=inference_detector(model,request['rgb'],test_pipeline=pipeline,text_prompt=caption,custom_entities=True).pred_instances.cpu()
        output=prediction_payload(result.bboxes.tolist(),result.scores.tolist(),result.labels.tolist(),prompts,args.threshold)
        if args.device.startswith('cuda'):torch.cuda.synchronize()
        output.update(dino_ms=(time.perf_counter()-start)*1000,provenance=provenance,caption=caption)
        Path(request['output']).write_text(json.dumps(output));return output
    if args.rgb:
        infer(dict(rgb=args.rgb,prompts=args.prompts,output=args.output));return
    reply(dict(ready=True,**provenance))
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if request.get('shutdown'):break
            output=infer(request);reply(dict(ok=True,dino_ms=output['dino_ms'],backend='native_mmdetection'))
        except Exception:
            traceback.print_exc(file=sys.stderr);reply(dict(error=traceback.format_exc()))


if __name__=='__main__':main()
