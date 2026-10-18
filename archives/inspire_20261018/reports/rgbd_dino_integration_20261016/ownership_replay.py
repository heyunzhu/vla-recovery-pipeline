from pathlib import Path
import os,shutil,json,subprocess,tarfile,time
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');out=root/'logs/rgbd_dino_integration_20261016';code=out/'code_ownership8'
shutil.copytree(out/'code',code)
with tarfile.open(out/'ownership_patch.tar.gz') as t:t.extractall(code)
env=dict(os.environ,PYTHONPATH=str(code)+':'+str(root/'logs/rgbd_exact_box_20261008/pydeps'))
with (out/'ownership_tests.log').open('w') as f:subprocess.run([str(root/'envs/tiptop-planning-py310/bin/python'),'-m','unittest','-v','experiments.robot.libero.skill_pipeline.tests.test_visual_anchor_obstacles'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
print('OWNERSHIP_TESTS_PASSED',flush=True)
for i in range(720):
 if (out/'recovery_finished.json').exists():break
 time.sleep(5)
else:raise RuntimeError('primary regression did not finish')
old=root/'logs/rgbd_ten_tasks_20261015/01_goal_bottle_plate/visual';run=out/'anchor_ownership8_256';run.mkdir(exist_ok=False)
shutil.copytree(old/'capture_support',run/'capture_support');shutil.copy2(code/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py',run/'capture_support/visual_selection_oracle_geometry_hook.py');shutil.copy2(old/'distractor_prompts.json',run/'distractor_prompts.json')
env=dict(os.environ)
for line in (old/'command.sh').read_text().splitlines():
 if line.startswith('export '):
  k,v=line[7:].split('=',1);env[k]=v
base=json.loads((out/'recovery/01_goal_bottle_plate_256/command.json').read_text());env.update(base['env_overrides']);env.update(ANCHOR_CAPTURE_DIR=str(run/'snapshots'),ANCHOR_DIAGNOSTIC_HOOK=str(run/'capture_support/visual_selection_oracle_geometry_hook.py'),ANCHOR_VISUAL_CODE=str(code),CUTAMP_FLOCK_LOCK=str(run/'cutamp.lock'),DINO_INFERENCE_PYTHONPATH=':'.join(map(str,[out/'dino440_deps',root/'logs/rgbd_exact_box_20261008/pydeps',code])))
a=base['argv'].copy();a[1]=str(code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py');a[a.index('--run-dir')+1]=str(run)
(run/'command.json').write_text(json.dumps({'argv':a,'env':{k:v for k,v in env.items() if k.startswith(('ANCHOR_','DINO_','CUTAMP_'))}},indent=2));print('START_OWNERSHIP_ANCHOR',flush=True)
with (run/'driver.log').open('w') as f:
 try:p=subprocess.run(a,env=env,cwd=root/'logs/continual_skill_core60_pilot_20261006/runtime_repo',stdout=f,stderr=subprocess.STDOUT,timeout=1200);rc=p.returncode
 except subprocess.TimeoutExpired:rc=124
(out/'ownership_finished.json').write_text(json.dumps({'returncode':rc,'ended':time.time()}));print('DONE_OWNERSHIP_ANCHOR',rc,flush=True)
