from pathlib import Path
import os,json,subprocess
root=Path('/mnt/nas/gezuhao/xinghanbo');tag='rgbd_native_mmdet_20261018';run=root/'logs'/tag;run.mkdir(exist_ok=True);gold=run/'golden';gold.mkdir(exist_ok=True)
code=root/'code_snapshots/rgbd_dino_full_20261018';models=root/'models/rgbd_dino_full_20261018';python=root/'envs/rgbd_dino_full_20261018_train/bin/python'
env=dict(os.environ,PYTHONPATH=str(code)+':'+str(root/'code_snapshots/mmdetection_rgbd_20261015'),CUDA_VISIBLE_DEVICES='GPU-97f96eec-562b-1e11-71e1-d64dd0bf6ec6',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',XDG_CACHE_HOME=str(root/'.cache'/tag),HF_HOME=str(root/'.cache/rgbd_dino/huggingface'))
cmd=[str(python),'-m','scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker','--config',str(models/'training/config.py'),'--checkpoint',str(models/'training/best_coco_bbox_mAP_epoch_10.pth'),'--device','cuda','--threshold','.25']
with (run/'golden_worker.log').open('w') as log:
 p=subprocess.Popen(cmd,env=env,cwd=code,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
 def read():
  for line in p.stdout:
   if line.startswith('RGBD_REPLY '):return json.loads(line[len('RGBD_REPLY '):])
  raise RuntimeError('native worker exited before replying')
 ready=read();assert ready.get('ready'),ready
 records=[]
 for episode,camera,phase,step,prompts in [
  ('libero_object_task_t01_i06','agentview','initial',0,dict(cheese='cream cheese',basket='basket',bowl='bowl',rack='rack',carton='carton',cabinet='cabinet',stove='stove')),
  ('libero_goal_task_t08_i06','robot0_eye_in_hand','skill_trigger',40,dict(cheese='cream cheese',rack='rack',bowl='bowl',carton='carton',cabinet='cabinet',stove='stove'))]:
  import shutil
  stem=f'{episode}_{phase}_{step:05d}_{camera}';src=root/'datasets/rgbd_dino_full_20261018/images640'/(stem+'.png')
  dest=gold/(stem+'.png');shutil.copyfile(src,dest);query=gold/(stem+'_prompts.json');query.write_text(json.dumps(prompts));output=gold/(stem+'_expected.json')
  p.stdin.write(json.dumps(dict(rgb=str(dest),prompts=str(query),output=str(output)))+'\n');p.stdin.flush();result=read();assert result.get('ok'),result
  records.append(dict(image=dest.name,prompts=query.name,expected=output.name))
 p.stdin.write(json.dumps(dict(shutdown=True))+'\n');p.stdin.flush();p.wait(timeout=30);assert p.returncode==0
(gold/'manifest.json').write_text(json.dumps(dict(provenance=ready,cases=records),indent=2));print('GOLDEN_COMPLETE',len(records),flush=True)
