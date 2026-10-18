"""Finish independent HF validation after the long collection/training pipeline."""
from pathlib import Path
import argparse,collections,json,os,subprocess,time,traceback


def overlap(a,b):
    x=max(a[0],b[0]);y=max(a[1],b[1]);right=min(a[0]+a[2],b[0]+b[2]);bottom=min(a[1]+a[3],b[1]+b[3]);inter=max(0,right-x)*max(0,bottom-y)
    return inter/max(1e-12,a[2]*a[3]+b[2]*b[3]-inter)


def compare_outputs(first,second,threshold=.25):
    groups=collections.defaultdict(lambda:[[],[]])
    for side,rows in enumerate([first,second]):
        for r in rows:
            if r['score']>=threshold:groups[(r['image_id'],r['category_id'])][side].append(r)
    matched=0;unmatched=0;min_iou=1.;max_score_delta=0.
    for a,b in groups.values():
        remaining=set(range(len(b)))
        for r in sorted(a,key=lambda x:-x['score']):
            candidates=[(overlap(r['bbox'],b[i]['bbox']),i) for i in remaining]
            iou,index=max(candidates,default=(0,None))
            if iou<.95:unmatched+=1;continue
            remaining.remove(index);matched+=1;min_iou=min(min_iou,iou);max_score_delta=max(max_score_delta,abs(r['score']-b[index]['score']))
        unmatched+=len(remaining)
    return dict(matched=matched,unmatched=unmatched,min_matched_iou=min_iou,max_score_delta=max_score_delta,passed=matched>0 and max_score_delta<=.02 and unmatched<=max(3,int(matched*.002)))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--gpu',required=True);args=ap.parse_args()
    root=args.root;tag='rgbd_dino_full_20261018';run=root/'logs'/tag;models=root/'models'/tag;code=root/'code_snapshots'/tag
    status=dict(stage='waiting_for_training',started=time.time())
    def save():(run/'validation_status.json').write_text(json.dumps(status,indent=2))
    save()
    try:
        while True:
            p=run/'pipeline_status.json'
            if p.exists():
                s=json.loads(p.read_text())
                if s.get('error'):raise RuntimeError('collection/training failed; see pipeline_status.json')
                if s.get('complete'):break
            if time.time()-status['started']>172800:raise TimeoutError('training pipeline not complete after 48 hours')
            time.sleep(30)
        checkpoint=Path(s['best_checkpoint']);python=root/'envs'/(tag+'_train/bin/python')
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=args.gpu,PYTHONPATH=str(code)+':'+str(root/'code_snapshots/mmdetection_rgbd_20261015'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',XDG_CACHE_HOME=str(root/'.cache'/tag),HF_HOME=str(root/'.cache/rgbd_dino/huggingface'),CUDA_CACHE_PATH=str(root/'.cache'/tag/'cuda'),TMPDIR=str(root/'tmp'))
        status['stage']='hf_independent_evaluation';save()
        for split in ['val','test']:
            argv=[python,code/'scripts/recovery/skill_pipeline/evaluate_grounding_dino_libero.py','--config',models/'training/config.py','--checkpoint',checkpoint,'--dataset',root/'datasets'/tag,'--output',models/'evaluation/hf_full19'/split,'--split',split,'--hf-export',models/'hf_export_best']
            if split=='test':argv+=['--calibration',models/'evaluation/hf_full19/val/calibration.json']
            with (run/('hf_'+split+'.log')).open('wb') as log:r=subprocess.run(list(map(str,argv)),env=env,cwd=code,stdout=log,stderr=subprocess.STDOUT)
            if r.returncode:raise RuntimeError('HF '+split+' evaluation failed')
        comparison={}
        for split in ['val','test']:
            a=json.loads((models/'evaluation/full19'/split/'predictions.json').read_text());b=json.loads((models/'evaluation/hf_full19'/split/'predictions.json').read_text())
            comparison[split]=compare_outputs(a,b)
        metrics={name:json.loads((models/'evaluation'/name/'test/metrics.json').read_text()) for name in ['pretrained','old8','full19','hf_full19']}
        taxonomy=json.loads((run/'taxonomy.json').read_text());old_classes=taxonomy['old_classes']
        new=metrics['full19'];old=metrics['old8'];per_class=new['validation_calibrated']['per_class']
        regressions=[c for c in old_classes if per_class[c]['recall']+.02<old['validation_calibrated']['per_class'][c]['recall']]
        low_recall=[c for c,v in per_class.items() if v['recall']<.90]
        ap_delta=abs(new['coco_stats']['AP']-metrics['hf_full19']['coco_stats']['AP'])
        report=dict(complete=True,source_checkpoint=str(checkpoint),export_consistency=comparison,hf_ap_delta=ap_delta,old_class_recall_regressions=regressions,classes_below_90_recall=low_recall,metrics=metrics,automatic_benchmark_deployment=False,export_passed=all(v['passed'] for v in comparison.values()) and ap_delta<=.002)
        report['detection_acceptance_passed']=report['export_passed'] and not regressions and not low_recall and new['validation_calibrated']['overall']['precision']>=.95
        (run/'final_detection_report.json').write_text(json.dumps(report,indent=2));status.update(stage='complete',complete=True,ended=time.time(),export_passed=report['export_passed'],detection_acceptance_passed=report['detection_acceptance_passed']);save()
    except Exception:
        status.update(error=traceback.format_exc(),ended=time.time());save();raise


if __name__=='__main__':main()
