from pathlib import Path
import os,json,time,hashlib,tarfile,subprocess,traceback,sys
ROOT=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
RUN=ROOT/'logs/rgbd_native_mmdet_20261018'
def save(name,obj):
 p=RUN/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,indent=2));t.replace(p)
def stage(name):
 save('setup_status.json',dict(stage=name,time=time.time()));print(name,flush=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def command(argv,env=None):
 subprocess.run([str(x) for x in argv],env=env,check=True,cwd=RUN,timeout=900)
def main():
 stage('waiting_for_verified_assets')
 deadline=time.time()+14400
 while not (RUN/'package_status.json').exists():
  if time.time()>deadline:raise TimeoutError('native assets transfer deadline')
  time.sleep(10)
 info=json.loads((RUN/'package_status.json').read_text());assert info['complete']
 for key,folder in [('runtime','native_runtime'),('assets','native_assets')]:
  archive=RUN/Path(info[key]['path']).name
  while not archive.exists() or archive.stat().st_size!=info[key]['size']:
   if time.time()>deadline:raise TimeoutError(str(archive))
   time.sleep(10)
  stage('verifying_'+key);assert sha(archive)==info[key]['sha256'],key
  destination=RUN/folder;destination.mkdir(exist_ok=True)
  stage('extracting_'+key)
  with tarfile.open(archive) as t:
   # All archives originate from our own scoped training environment.
   for member in t.getmembers():
    target=(destination/member.name).resolve()
    if not target.is_relative_to(destination.resolve()):raise ValueError(member.name)
   t.extractall(destination,filter='data')
 checkpoint=RUN/'best_coco_bbox_mAP_epoch_10.pth'
 while not checkpoint.exists() or checkpoint.stat().st_size!=710647898:
  if time.time()>deadline:raise TimeoutError('checkpoint transfer deadline')
  time.sleep(10)
 stage('verifying_checkpoint');assert sha(checkpoint)==info['checkpoint_sha256']
 command([ROOT/'envs/tiptop-planning-py310/bin/python','-m','venv','--without-pip',RUN/'native_env'])
 site=RUN/'native_env/lib/python3.10/site-packages';site.mkdir(parents=True,exist_ok=True)
 (site/'native_runtime.pth').write_text('import site; site.addsitedir('+repr(str(RUN/'native_runtime/site-packages'))+')\n')
 env=dict(os.environ,**json.loads((RUN/'worker_env.json').read_text()))
 env.update(PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',CUDA_VISIBLE_DEVICES='0')
 source=(RUN/'native_assets/training_config.py').read_text()
 source=source.replace('/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_full_20261018/bert_local',str(RUN/'native_assets/bert_local'))
 source=source.replace('/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_finetune_20261015/bert_local',str(RUN/'native_assets/bert_local'))
 (RUN/'native_config.py').write_text(source)
 stage('native_fixed_image_preflight')
 golden=RUN/'native_assets/golden';manifest=json.loads((golden/'manifest.json').read_text())
 argv=[str(RUN/'native_env/bin/python'),'-u','-m','scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker','--config',str(RUN/'native_config.py'),'--checkpoint',str(checkpoint),'--device','cuda','--threshold','.25']
 with (RUN/'native_preflight_worker.log').open('w') as log:
  p=subprocess.Popen(argv,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
  def reply():
   for line in p.stdout:
    if line.startswith('RGBD_REPLY '):return json.loads(line[len('RGBD_REPLY '):])
   raise RuntimeError('native worker exited; inspect native_preflight_worker.log')
  ready=reply();assert ready.get('ready'),ready
  assert ready['backend']=='native_mmdetection' and not ready['hf_conversion_used']
  assert ready['checkpoint_sha256']==info['checkpoint_sha256']
  rows=[]
  for index,case in enumerate(manifest['cases']):
   output=RUN/f'native_preflight_{index}.json'
   p.stdin.write(json.dumps(dict(rgb=str(golden/case['image']),prompts=str(golden/case['prompts']),output=str(output)))+'\n');p.stdin.flush();answer=reply();assert answer.get('ok'),answer
   expected=json.loads((golden/case['expected']).read_text());actual=json.loads(output.read_text())
   assert actual['text_labels']==expected['text_labels'],(actual['text_labels'],expected['text_labels'])
   max_box=max([abs(a-b) for aa,bb in zip(actual['boxes'],expected['boxes']) for a,b in zip(aa,bb)] or [0])
   max_score=max([abs(a-b) for a,b in zip(actual['scores'],expected['scores'])] or [0])
   assert max_box<=1 and max_score<=.01,(max_box,max_score)
   rows.append(dict(image=case['image'],detections=len(actual['scores']),max_box_delta_px=max_box,max_score_delta=max_score,dino_ms=actual['dino_ms']))
  p.stdin.write(json.dumps(dict(shutdown=True))+'\n');p.stdin.flush();p.wait(timeout=60);assert p.returncode==0
 save('native_parity.json',dict(passed=True,provenance=ready,cases=rows,source=manifest['provenance']))
 assert (RUN/'policy_ready.json').exists(),'shared policy is not ready'
 policy=json.loads((RUN/'policy_launch.json').read_text());os.kill(policy['pid'],0)
 stage('launching_50_episode_batch')
 argv=[str(ROOT/'envs/rlinf-openpi/bin/python'),'-u',str(RUN/'code/scripts/recovery/skill_pipeline/run_rgbd_core60_batch.py'),'--root',str(ROOT),'--run',str(RUN),'--workers','2','--expected-cases','50','--timeout','2400']
 with (RUN/'scheduler.log').open('wb') as log:
  p=subprocess.Popen(argv,cwd=RUN,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 save('batch_launch.json',dict(pid=p.pid,argv=argv,started=time.time(),native_parity_passed=True))
 stage('batch_launched')
if __name__=='__main__':
 try:main()
 except Exception:
  (RUN/'setup_error.txt').write_text(traceback.format_exc());stage('failed');raise
from pathlib import Path
import os,json,time,hashlib,tarfile,subprocess,traceback,sys
ROOT=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
RUN=ROOT/'logs/rgbd_native_mmdet_20261018'
def save(name,obj):
 p=RUN/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,indent=2));t.replace(p)
def stage(name):
 save('setup_status.json',dict(stage=name,time=time.time()));print(name,flush=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def command(argv,env=None):
 subprocess.run([str(x) for x in argv],env=env,check=True,cwd=RUN,timeout=900)
def main():
 stage('waiting_for_verified_assets')
 deadline=time.time()+14400
 while not (RUN/'package_status.json').exists():
  if time.time()>deadline:raise TimeoutError('native assets transfer deadline')
  time.sleep(10)
 info=json.loads((RUN/'package_status.json').read_text());assert info['complete']
 for key,folder in [('runtime','native_runtime'),('assets','native_assets')]:
  archive=RUN/Path(info[key]['path']).name
  while not archive.exists() or archive.stat().st_size!=info[key]['size']:
   if time.time()>deadline:raise TimeoutError(str(archive))
   time.sleep(10)
  stage('verifying_'+key);assert sha(archive)==info[key]['sha256'],key
  destination=RUN/folder;destination.mkdir(exist_ok=True)
  stage('extracting_'+key)
  with tarfile.open(archive) as t:
   # All archives originate from our own scoped training environment.
   for member in t.getmembers():
    target=(destination/member.name).resolve()
    if not target.is_relative_to(destination.resolve()):raise ValueError(member.name)
   t.extractall(destination,filter='data')
 checkpoint=RUN/'best_coco_bbox_mAP_epoch_10.pth'
 while not checkpoint.exists() or checkpoint.stat().st_size!=710647898:
  if time.time()>deadline:raise TimeoutError('checkpoint transfer deadline')
  time.sleep(10)
 stage('verifying_checkpoint');assert sha(checkpoint)==info['checkpoint_sha256']
 command([ROOT/'envs/tiptop-planning-py310/bin/python','-m','venv','--without-pip',RUN/'native_env'])
 site=RUN/'native_env/lib/python3.10/site-packages';site.mkdir(parents=True,exist_ok=True)
 (site/'native_runtime.pth').write_text('import site; site.addsitedir('+repr(str(RUN/'native_runtime/site-packages'))+')\n')
 env=dict(os.environ,**json.loads((RUN/'worker_env.json').read_text()))
 env.update(PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',CUDA_VISIBLE_DEVICES='0')
 source=(RUN/'native_assets/training_config.py').read_text()
 source=source.replace('/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_full_20261018/bert_local',str(RUN/'native_assets/bert_local'))
 source=source.replace('/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_finetune_20261015/bert_local',str(RUN/'native_assets/bert_local'))
 (RUN/'native_config.py').write_text(source)
 stage('native_fixed_image_preflight')
 golden=RUN/'native_assets/golden';manifest=json.loads((golden/'manifest.json').read_text())
 argv=[str(RUN/'native_env/bin/python'),'-u','-m','scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker','--config',str(RUN/'native_config.py'),'--checkpoint',str(checkpoint),'--device','cuda','--threshold','.25']
 with (RUN/'native_preflight_worker.log').open('w') as log:
  p=subprocess.Popen(argv,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
  def reply():
   for line in p.stdout:
    if line.startswith('RGBD_REPLY '):return json.loads(line[len('RGBD_REPLY '):])
   raise RuntimeError('native worker exited; inspect native_preflight_worker.log')
  ready=reply();assert ready.get('ready'),ready
  assert ready['backend']=='native_mmdetection' and not ready['hf_conversion_used']
  assert ready['checkpoint_sha256']==info['checkpoint_sha256']
  rows=[]
  for index,case in enumerate(manifest['cases']):
   output=RUN/f'native_preflight_{index}.json'
   p.stdin.write(json.dumps(dict(rgb=str(golden/case['image']),prompts=str(golden/case['prompts']),output=str(output)))+'\n');p.stdin.flush();answer=reply();assert answer.get('ok'),answer
   expected=json.loads((golden/case['expected']).read_text());actual=json.loads(output.read_text())
   assert actual['text_labels']==expected['text_labels'],(actual['text_labels'],expected['text_labels'])
   max_box=max([abs(a-b) for aa,bb in zip(actual['boxes'],expected['boxes']) for a,b in zip(aa,bb)] or [0])
   max_score=max([abs(a-b) for a,b in zip(actual['scores'],expected['scores'])] or [0])
   assert max_box<=1 and max_score<=.01,(max_box,max_score)
   rows.append(dict(image=case['image'],detections=len(actual['scores']),max_box_delta_px=max_box,max_score_delta=max_score,dino_ms=actual['dino_ms']))
  p.stdin.write(json.dumps(dict(shutdown=True))+'\n');p.stdin.flush();p.wait(timeout=60);assert p.returncode==0
 save('native_parity.json',dict(passed=True,provenance=ready,cases=rows,source=manifest['provenance']))
 stage('native_dino_sam2_adapter_preflight')
 seg_env=dict(env,PYTHONPATH=str(ROOT/'logs/rgbd_exact_box_20261008/pydeps')+':'+str(RUN/'code'),DINO_RESIDENT_WORKER='1',DINO_INFERENCE_WORKDIR=str(RUN/'adapter_preflight'))
 (RUN/'adapter_preflight').mkdir(exist_ok=True)
 argv=[str(ROOT/'envs/tiptop-planning-py310/bin/python'),'-u','-m','scripts.recovery.skill_pipeline.resident_rgbd_segmentation_worker','--config',str(RUN/'vision_config.json')]
 request=dict(rgb=str(golden/manifest['cases'][0]['image']),output=str(RUN/'adapter_preflight/masks.npz'))
 with (RUN/'adapter_preflight/worker.log').open('w') as log:
  p=subprocess.Popen(argv,env=seg_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
  stdout,_=p.communicate(json.dumps(request)+'\n'+json.dumps(dict(shutdown=True))+'\n',timeout=900)
 responses=[json.loads(line[len('RGBD_REPLY '):]) for line in stdout.splitlines() if line.startswith('RGBD_REPLY ')]
 save('adapter_preflight.json',dict(returncode=p.returncode,responses=responses))
 assert p.returncode==0 and len(responses)==2 and responses[0].get('ready') and responses[1].get('ok'),responses
 assert responses[1]['categories'],'adapter returned no detections on reference frame'
 assert (RUN/'policy_ready.json').exists(),'shared policy is not ready'
 policy=json.loads((RUN/'policy_launch.json').read_text());os.kill(policy['pid'],0)
 stage('launching_50_episode_batch')
 argv=[str(ROOT/'envs/rlinf-openpi/bin/python'),'-u',str(RUN/'code/scripts/recovery/skill_pipeline/run_rgbd_core60_batch.py'),'--root',str(ROOT),'--run',str(RUN),'--workers','2','--expected-cases','50','--timeout','2400']
 with (RUN/'scheduler.log').open('wb') as log:
  p=subprocess.Popen(argv,cwd=RUN,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 save('batch_launch.json',dict(pid=p.pid,argv=argv,started=time.time(),native_parity_passed=True))
 stage('batch_launched')
if __name__=='__main__':
 try:main()
 except Exception:
  (RUN/'setup_error.txt').write_text(traceback.format_exc());stage('failed');raise
from pathlib import Path
import os,json,time,hashlib,tarfile,subprocess,traceback,sys
ROOT=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
RUN=ROOT/'logs/rgbd_native_mmdet_20261018'
def save(name,obj):
 p=RUN/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,indent=2));t.replace(p)
def stage(name):
 save('setup_status.json',dict(stage=name,time=time.time()));print(name,flush=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def command(argv,env=None):
 subprocess.run([str(x) for x in argv],env=env,check=True,cwd=RUN,timeout=900)
def main():
 stage('waiting_for_verified_assets')
 deadline=time.time()+14400
 while not (RUN/'slim_package_status.json').exists():
  if time.time()>deadline:raise TimeoutError('native assets transfer deadline')
  time.sleep(10)
 info=json.loads((RUN/'slim_package_status.json').read_text());assert info['complete']
 for key,folder in [('runtime','native_runtime'),('assets','native_assets')]:
  archive=RUN/Path(info[key]['path']).name
  while not archive.exists() or archive.stat().st_size!=info[key]['size']:
   if time.time()>deadline:raise TimeoutError(str(archive))
   time.sleep(10)
  stage('verifying_'+key);assert sha(archive)==info[key]['sha256'],key
  destination=RUN/folder;destination.mkdir(exist_ok=True)
  stage('extracting_'+key)
  with tarfile.open(archive) as t:
   # All archives originate from our own scoped training environment.
   for member in t.getmembers():
    target=(destination/member.name).resolve()
    if not target.is_relative_to(destination.resolve()):raise ValueError(member.name)
   t.extractall(destination,filter='data')
 checkpoint=RUN/'best_coco_bbox_mAP_epoch_10.pth'
 while not checkpoint.exists() or checkpoint.stat().st_size!=710647898:
  if time.time()>deadline:raise TimeoutError('checkpoint transfer deadline')
  time.sleep(10)
 stage('verifying_checkpoint');assert sha(checkpoint)==info['checkpoint_sha256']
 command([ROOT/'envs/tiptop-planning-py310/bin/python','-m','venv','--without-pip',RUN/'native_env'])
 site=RUN/'native_env/lib/python3.10/site-packages';site.mkdir(parents=True,exist_ok=True)
 (site/'native_runtime.pth').write_text('import site; site.addsitedir('+repr(str(RUN/'native_runtime/site-packages'))+')\n')
 stage('installing_pytorch_from_internal_mirror')
 command([ROOT/'envs/tiptop-planning-py310/bin/python','-m','pip','--python',RUN/'native_env/bin/python','install','--index-url','http://nexus.sii.shaipower.online/repository/pypi/simple/','--trusted-host','nexus.sii.shaipower.online','--cache-dir',RUN/'cache/pip','torch==2.1.2','torchvision==0.16.2'])
 env=dict(os.environ,**json.loads((RUN/'worker_env.json').read_text()))
 env.update(PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',CUDA_VISIBLE_DEVICES='0')
 source=(RUN/'native_assets/training_config.py').read_text()
 source=source.replace('/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_full_20261018/bert_local',str(RUN/'native_assets/bert_local'))
 source=source.replace('/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_finetune_20261015/bert_local',str(RUN/'native_assets/bert_local'))
 (RUN/'native_config.py').write_text(source)
 stage('restoring_bert_from_native_checkpoint')
 command([RUN/'native_env/bin/python','-c',"import torch;from pathlib import Path;r=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_native_mmdet_20261018');state=torch.load(r/'best_coco_bbox_mAP_epoch_10.pth',map_location='cpu')['state_dict'];prefix='language_model.language_backbone.body.model.';bert={k[len(prefix):]:v for k,v in state.items() if k.startswith(prefix)};assert len(bert)>190;torch.save(bert,r/'native_assets/bert_local/pytorch_model.bin');print('BERT_RECOVERED_FROM_NATIVE_CHECKPOINT',len(bert))"],env=env)
 stage('native_fixed_image_preflight')
 golden=RUN/'native_assets/golden';manifest=json.loads((golden/'manifest.json').read_text())
 argv=[str(RUN/'native_env/bin/python'),'-u','-m','scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker','--config',str(RUN/'native_config.py'),'--checkpoint',str(checkpoint),'--device','cuda','--threshold','.25']
 with (RUN/'native_preflight_worker.log').open('w') as log:
  p=subprocess.Popen(argv,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
  def reply():
   for line in p.stdout:
    if line.startswith('RGBD_REPLY '):return json.loads(line[len('RGBD_REPLY '):])
   raise RuntimeError('native worker exited; inspect native_preflight_worker.log')
  ready=reply();assert ready.get('ready'),ready
  assert ready['backend']=='native_mmdetection' and not ready['hf_conversion_used']
  assert ready['checkpoint_sha256']==info['checkpoint_sha256']
  rows=[]
  for index,case in enumerate(manifest['cases']):
   output=RUN/f'native_preflight_{index}.json'
   p.stdin.write(json.dumps(dict(rgb=str(golden/case['image']),prompts=str(golden/case['prompts']),output=str(output)))+'\n');p.stdin.flush();answer=reply();assert answer.get('ok'),answer
   expected=json.loads((golden/case['expected']).read_text());actual=json.loads(output.read_text())
   assert actual['text_labels']==expected['text_labels'],(actual['text_labels'],expected['text_labels'])
   max_box=max([abs(a-b) for aa,bb in zip(actual['boxes'],expected['boxes']) for a,b in zip(aa,bb)] or [0])
   max_score=max([abs(a-b) for a,b in zip(actual['scores'],expected['scores'])] or [0])
   assert max_box<=1 and max_score<=.01,(max_box,max_score)
   rows.append(dict(image=case['image'],detections=len(actual['scores']),max_box_delta_px=max_box,max_score_delta=max_score,dino_ms=actual['dino_ms']))
  p.stdin.write(json.dumps(dict(shutdown=True))+'\n');p.stdin.flush();p.wait(timeout=60);assert p.returncode==0
 save('native_parity.json',dict(passed=True,provenance=ready,cases=rows,source=manifest['provenance']))
 stage('native_dino_sam2_adapter_preflight')
 seg_env=dict(env,PYTHONPATH=str(ROOT/'logs/rgbd_exact_box_20261008/pydeps')+':'+str(RUN/'code'),DINO_RESIDENT_WORKER='1',DINO_INFERENCE_WORKDIR=str(RUN/'adapter_preflight'))
 (RUN/'adapter_preflight').mkdir(exist_ok=True)
 argv=[str(ROOT/'envs/tiptop-planning-py310/bin/python'),'-u','-m','scripts.recovery.skill_pipeline.resident_rgbd_segmentation_worker','--config',str(RUN/'vision_config.json')]
 request=dict(rgb=str(golden/manifest['cases'][0]['image']),output=str(RUN/'adapter_preflight/masks.npz'))
 with (RUN/'adapter_preflight/worker.log').open('w') as log:
  p=subprocess.Popen(argv,env=seg_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
  stdout,_=p.communicate(json.dumps(request)+'\n'+json.dumps(dict(shutdown=True))+'\n',timeout=900)
 responses=[json.loads(line[len('RGBD_REPLY '):]) for line in stdout.splitlines() if line.startswith('RGBD_REPLY ')]
 save('adapter_preflight.json',dict(returncode=p.returncode,responses=responses))
 assert p.returncode==0 and len(responses)==2 and responses[0].get('ready') and responses[1].get('ok'),responses
 assert responses[1]['categories'],'adapter returned no detections on reference frame'
 stage('waiting_for_shared_policy')
 deadline=time.time()+900
 while not (RUN/'policy_ready.json').exists():
  if time.time()>deadline:raise TimeoutError('shared policy is not ready')
  time.sleep(5)
 policy=json.loads((RUN/'policy_launch.json').read_text());os.kill(policy['pid'],0)
 stage('launching_50_episode_batch')
 argv=[str(ROOT/'envs/rlinf-openpi/bin/python'),'-u',str(RUN/'code/scripts/recovery/skill_pipeline/run_rgbd_core60_batch.py'),'--root',str(ROOT),'--run',str(RUN),'--workers','2','--expected-cases','50','--timeout','2400']
 with (RUN/'scheduler.log').open('wb') as log:
  p=subprocess.Popen(argv,cwd=RUN,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 save('batch_launch.json',dict(pid=p.pid,argv=argv,started=time.time(),native_parity_passed=True))
 stage('batch_launched')
if __name__=='__main__':
 try:main()
 except Exception:
  (RUN/'setup_error.txt').write_text(traceback.format_exc());stage('failed');raise
