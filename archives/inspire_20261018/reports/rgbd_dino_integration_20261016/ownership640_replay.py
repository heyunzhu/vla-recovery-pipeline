from pathlib import Path
import os,time,shutil,json,subprocess
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');o=root/'logs/rgbd_dino_integration_20261016'
for i in range(960):
 if (o/'ownership_finished.json').exists():break
 time.sleep(5)
else:raise RuntimeError('256 ownership run did not finish')
source=o/'anchor_ownership8_256';run=o/'anchor_ownership8_640';run.mkdir(exist_ok=False)
shutil.copytree(source/'capture_support',run/'capture_support');shutil.copy2(source/'distractor_prompts.json',run/'distractor_prompts.json')
base=json.loads((source/'command.json').read_text());env=dict(os.environ)
old=root/'logs/rgbd_ten_tasks_20261015/01_goal_bottle_plate/visual/command.sh'
for line in old.read_text().splitlines():
 if line.startswith('export '):k,v=line[7:].split('=',1);env[k]=v
env.update(base['env']);env.update(ANCHOR_CAPTURE_DIR=str(run/'snapshots'),ANCHOR_DIAGNOSTIC_HOOK=str(run/'capture_support/visual_selection_oracle_geometry_hook.py'),CUTAMP_FLOCK_LOCK=str(run/'cutamp.lock'))
a=base['argv'].copy();a[a.index('--run-dir')+1]=str(run);a[a.index('--camera-resolution')+1]='640'
(run/'command.json').write_text(json.dumps({'argv':a,'env':{k:v for k,v in env.items() if k.startswith(('ANCHOR_','DINO_','CUTAMP_'))}},indent=2));print('START_OWNERSHIP_640',flush=True)
with (run/'driver.log').open('w') as f:
 try:p=subprocess.run(a,env=env,cwd=root/'logs/continual_skill_core60_pilot_20261006/runtime_repo',stdout=f,stderr=subprocess.STDOUT,timeout=1200);rc=p.returncode
 except subprocess.TimeoutExpired:rc=124
(o/'ownership640_finished.json').write_text(json.dumps({'returncode':rc,'ended':time.time()}));print('DONE_OWNERSHIP_640',rc,flush=True)
