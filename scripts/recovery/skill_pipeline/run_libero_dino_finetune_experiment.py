#!/usr/bin/env python3
"""Run the fixed training/evaluation sequence inside an existing isolated setup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import traceback


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--tag',default='rgbd_dino_finetune_20261015')
    p.add_argument('--gpu',required=True);p.add_argument('--batch-size',type=int,default=1)
    p.add_argument('--accumulation',type=int,default=4);p.add_argument('--epochs',type=int,default=12)
    p.add_argument('--resume-completed',action='store_true',help='Skip stages whose recorded subprocess exited successfully')
    args=p.parse_args();root=args.root.resolve();out=root/'logs'/args.tag
    code=root/'code_snapshots'/args.tag;mmdet=root/'code_snapshots/mmdetection_rgbd_20261015'
    dataset=root/'datasets/rgbd_dino_20261015';models=root/'models'/args.tag
    python=root/'envs/rgbd_dino_mm_20261015/bin/python';scripts=code/'scripts/recovery/skill_pipeline'
    env={**os.environ,'CUDA_VISIBLE_DEVICES':args.gpu,'PYTHONPATH':str(code)+':'+str(mmdet),
        'UV_CACHE_DIR':str(root/'.cache/uv-rgbd-dino'),'TMPDIR':str(root/'tmp/rgbd_dino'),
        'XDG_CACHE_HOME':str(root/'.cache/rgbd_dino'),'MPLCONFIGDIR':str(root/'.cache/rgbd_dino/matplotlib'),
        'CUDA_CACHE_PATH':str(root/'.cache/rgbd_dino/cuda'),'HF_HOME':str(root/'.cache/rgbd_dino/huggingface'),
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'1',
        'TOKENIZERS_PARALLELISM':'false','NLTK_DATA':str(models/'nltk_data')}
    training=models/'training';state={'started':time.time(),'stages':[], 'process_env_overrides':{k:v for k,v in env.items() if os.environ.get(k)!=v},
        'source_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in scripts.glob('*grounding_dino*.py')},'args':vars(args)|{'root':str(root)}}
    if args.resume_completed:
        previous=json.loads((out/'experiment_status.json').read_text())
        state['stages']=previous['stages'];state['resumed_from_started']=previous['started']
    def save(): (out/'experiment_status.json').write_text(json.dumps(state,indent=2))
    def run(name, argv):
        if args.resume_completed and any(r['name']==name and r.get('returncode')==0 and not r.get('invalidated') for r in state['stages']):
            print('SKIP COMPLETED',name,flush=True);return
        row={'name':name,'argv':list(map(str,argv)),'started':time.time()};state['stages'].append(row);save()
        print('START',name,flush=True)
        logfile=out/(name+'.log')
        if logfile.exists():logfile.rename(out/(name+f'.previous_{time.time_ns()}.log'))
        with logfile.open('w') as log:
            result=subprocess.run(row['argv'],cwd=code,env=env,stdout=log,stderr=subprocess.STDOUT)
        row.update(ended=time.time(),returncode=result.returncode);save()
        if result.returncode: raise RuntimeError(f'{name} failed: see {out/(name+".log")}')
        print('DONE',name,round(row['ended']-row['started'],1),flush=True)
    def train_cmd(output):
        return [python,'-u',scripts/'train_grounding_dino_libero.py','--mmdetection',mmdet,'--dataset',dataset,
            '--bert',models/'bert_local','--pretrained',models/'groundingdino_swint_ogc_mmdet-822d7e9d.pth',
            '--output',output,'--epochs',str(args.epochs),'--batch-size',str(args.batch_size),'--accumulation',str(args.accumulation),'--workers','2']
    def evaluate(name, checkpoint, resolution, split):
        destination=models/'evaluation'/name/split
        argv=[python,'-u',scripts/'evaluate_grounding_dino_libero.py','--config',training/'config.py',
            '--checkpoint',checkpoint,'--dataset',dataset,'--output',destination,'--split',split,'--resolution',str(resolution)]
        if split=='test':argv+=['--calibration',models/'evaluation'/name/'val/calibration.json']
        run(name+'_'+split,argv)
    try:
        assert (dataset/'completed.json').exists()
        assert (out/'environment_install_complete.json').exists()
        run('build_config',train_cmd(training)+['--config-only'])
        reference=out/'diagnostic_reference'
        if not reference.exists():
            import tarfile
            with tarfile.open(out/'diagnostic_reference.tar.gz') as archive:archive.extractall(out,filter='data')
        audit=[python,'-u',scripts/'audit_mmdet_grounding_dino.py','--config',training/'config.py','--reference',reference]
        pretrained=models/'groundingdino_swint_ogc_mmdet-822d7e9d.pth'
        run('audit_native_reference',audit+['--checkpoint',pretrained,'--output',models/'diagnostics/native_reference'])
        run('audit_before',audit+['--checkpoint',pretrained,'--output',models/'diagnostics/before','--fixed-classes'])
        run('smoke_train',train_cmd(models/'smoke_training_validated')+['--smoke-iterations','12'])
        evaluate('pretrained640',pretrained,640,'val')
        evaluate('pretrained256',pretrained,256,'val')
        run('train',train_cmd(training))
        best=list(training.glob('best_coco_bbox_mAP*.pth'))
        if len(best)!=1:raise RuntimeError(f'expected one best validation checkpoint: {best}')
        checkpoint=best[0];state['best_checkpoint']=str(checkpoint);save()
        evaluate('finetuned640',checkpoint,640,'val')
        evaluate('pretrained640',pretrained,640,'test')
        evaluate('pretrained256',pretrained,256,'test')
        evaluate('finetuned640',checkpoint,640,'test')
        run('audit_after',audit+['--checkpoint',checkpoint,'--output',models/'diagnostics/after','--fixed-classes'])
        state['complete']=True;state['ended']=time.time();save()
    except Exception:
        state['error']=traceback.format_exc();state['ended']=time.time();save();raise


if __name__=='__main__':main()
