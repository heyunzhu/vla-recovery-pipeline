EXPECTED={'source_overlay.tar.gz': 'cf601f7f6c588985d5ff296f4141cca8cec08d41abc633b37cecf3266aa8c406', 'hf_export_best.tar': '1b6fdbb3ab467a8da0d190ae67a3550634cecfcf4a2ed0fa25e5bff625e68e7c'}
from pathlib import Path
import json,os,subprocess,tarfile,hashlib,time,shutil
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
out=root/'logs/rgbd_dino_integration_20261016'
for name in ('source_overlay.tar.gz','hf_export_best.tar'):
 p=out/name
 if hashlib.sha256(p.read_bytes()).hexdigest()!=EXPECTED[name]:raise RuntimeError('incomplete transfer: '+name)
code=out/'code';code.mkdir(exist_ok=True)
with tarfile.open(out/'source_overlay.tar.gz') as t:t.extractall(code)
with tarfile.open(out/'hf_export_best.tar') as t:t.extractall(out)
with tarfile.open(out/'integration_patch.tar.gz') as t:t.extractall(code)
# Use the exact former per-case environment and fixture; only the model adapter changes.
old=root/'logs/rgbd_ten_tasks_20261015'
# Validate the target Torch/HF worker before any recovery experiment.
refs=out/'runtime_reference';refs.mkdir(exist_ok=True)
for image in json.loads((out/'hf440_runtime.json').read_text())['rows']:
 case=old/Path(image['image']).stem
 src=case/'visual/snapshots/recovery01/pre_solver_attempt01/agentview/rgbd.npz'
 if not src.exists():raise RuntimeError('missing frozen reference '+str(src))
 import numpy as np
 from PIL import Image
 with np.load(src,allow_pickle=False) as arrays:Image.fromarray(arrays['rgb']).save(refs/image['image'])
probe_env=dict(os.environ,PYTHONPATH=':'.join(map(str,[out/'dino440_deps',root/'logs/rgbd_exact_box_20261008/pydeps',code])),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='2')
probe=[str(root/'envs/tiptop-planning-py310/bin/python'),'-m','scripts.recovery.skill_pipeline.audit_hf_dino_runtime','--export',str(out/'hf_export_best'),'--reference',str(refs),'--output',str(out/'worker_runtime.json'),'--device','cuda:0']
with (out/'worker_runtime.log').open('w') as f:subprocess.run(probe,env=probe_env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
# Match effective detections by class and IoU rather than decoder slot number.
import numpy as np
from scipy.optimize import linear_sum_assignment
baseline=json.loads((out/'hf440_runtime.json').read_text())['rows'];actual=json.loads((out/'worker_runtime.json').read_text())['rows'];checks=[]
for a,b in zip(baseline,actual):
 ok=a['image']==b['image'] and a['rgb_sha256']==b['rgb_sha256'] and len(a['scores'])==len(b['scores'])
 overlaps=[];score_errors=[]
 for label in set(a['labels'])|set(b['labels']):
  ia=[i for i,x in enumerate(a['labels']) if x==label];ib=[i for i,x in enumerate(b['labels']) if x==label]
  if len(ia)!=len(ib):ok=False;continue
  aa=np.asarray([a['boxes'][i] for i in ia]);bb=np.asarray([b['boxes'][i] for i in ib])
  lo=np.maximum(aa[:,None,:2],bb[None,:,:2]);hi=np.minimum(aa[:,None,2:],bb[None,:,2:]);inter=np.maximum(hi-lo,0).prod(-1)
  area_a=np.maximum(aa[:,2:]-aa[:,:2],0).prod(-1);area_b=np.maximum(bb[:,2:]-bb[:,:2],0).prod(-1)
  ious=inter/np.maximum(area_a[:,None]+area_b[None,:]-inter,1e-12);ii,jj=linear_sum_assignment(-ious)
  for i,j in zip(ii,jj):overlaps.append(float(ious[i,j]));score_errors.append(abs(a['scores'][ia[i]]-b['scores'][ib[j]]))
 ok=ok and all(x>=.95 for x in overlaps) and all(x<=.02 for x in score_errors)
 checks.append({'image':a['image'],'passed':ok,'minimum_iou':min(overlaps,default=1.),'maximum_score_error':max(score_errors,default=0.)})
(out/'worker_runtime_parity.json').write_text(json.dumps(checks,indent=2))
if len(checks)!=9 or not all(c['passed'] for c in checks):raise RuntimeError('target worker parity failed')
print('WORKER_PARITY_PASSED',flush=True)
rows=[]
for case in sorted(old.glob('[0-9][0-9]_*')):
 if not (case/'visual/command.sh').exists():continue
 for resolution in ([256,640] if case.name.startswith('01_') else [640]):
  run=out/'recovery'/f'{case.name}_{resolution}';run.mkdir(parents=True,exist_ok=False)
  shutil.copytree(case/'visual/capture_support',run/'capture_support')
  shutil.copy2(code/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py',run/'capture_support/visual_selection_oracle_geometry_hook.py')
  shutil.copy2(case/'visual/distractor_prompts.json',run/'distractor_prompts.json')
  env=dict(os.environ)
  for line in (case/'visual/command.sh').read_text().splitlines():
   if line.startswith('export '):
    key,value=line[7:].split('=',1);env[key]=value
  env.update(ANCHOR_CAPTURE_DIR=str(run/'snapshots'),ANCHOR_DIAGNOSTIC_HOOK=str(run/'capture_support/visual_selection_oracle_geometry_hook.py'),ANCHOR_VISUAL_CODE=str(code),CUTAMP_FLOCK_LOCK=str(run/'cutamp.lock'),ANCHOR_FINETUNED_DINO_EXPORT=str(out/'hf_export_best'),DINO_INFERENCE_PYTHON=str(root/'envs/tiptop-planning-py310/bin/python'),DINO_INFERENCE_PYTHONPATH=':'.join(map(str,[out/'dino440_deps',root/'logs/rgbd_exact_box_20261008/pydeps',code])),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  import shlex
  original=shlex.split((case/'visual/command.sh').read_text().splitlines()[-1]);args=original.copy();args[1]=str(code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py');args[args.index('--run-dir')+1]=str(run);args+=['--camera-resolution',str(resolution)]
  record={'case':case.name,'resolution':resolution,'argv':args,'env_overrides':{k:v for k,v in env.items() if k.startswith(('ANCHOR_','DINO_','CUTAMP_'))},'started':time.time()};(run/'command.json').write_text(json.dumps(record,indent=2));print('START',case.name,resolution,flush=True)
  with (run/'driver.log').open('w') as f:
   try: result=subprocess.run(args,env=env,cwd=root/'logs/continual_skill_core60_pilot_20261006/runtime_repo',stdout=f,stderr=subprocess.STDOUT,timeout=1200);record['returncode']=result.returncode
   except subprocess.TimeoutExpired:record['returncode']=124
  record['ended']=time.time()
  for name in ('replay_result.json','failure_result.json'):
   if (run/name).exists():record['result']=json.loads((run/name).read_text())
  rows.append(record);(out/'recovery_status.json').write_text(json.dumps(rows,indent=2));print('DONE',case.name,resolution,record.get('result',{}).get('recovery_success'),flush=True)
(out/'recovery_finished.json').write_text(json.dumps({'completed':len(rows),'ended':time.time()}))
