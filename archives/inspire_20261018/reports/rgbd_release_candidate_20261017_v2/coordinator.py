from pathlib import Path
import json,os,subprocess,hashlib
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');run=Path(__file__).parent
ref=root/'logs/rgbd_collision_aligned_20261017'
records=[];feasible=[]
for case in sorted(ref.glob('plane_01')):
 command=json.loads((case/'command.json').read_text());env=dict(os.environ,**command['env'])
 env.update(OVERLAY_ROOT=str(run/'runtime_overlay'),REAL_CUTAMP_BACKEND_CHILD='1')
 for path in sorted((case/'cutamp_debug').glob('*.problem.json')):
  raw=json.loads(path.read_text())
  if not any(a['predicate']=='on' for a in raw['problem']['goal_atoms']):continue
  for surface in raw['problem']['surfaces']:
   if surface['geometry'].get('source')=='rgbd_observed_release_region':
    surface['geometry'].setdefault('metadata',{})['rgbd_release_constraint']='candidate_pose_v1'
    surface['geometry']['metadata'].setdefault('affordances',[]).append('placement_region')
  input_path=run/(case.name+'.preflight.problem.json');input_path.write_text(json.dumps(raw))
  destination=run/(case.name+'_preflight')
  argv=[env['CUTAMP_REAL_RUNNER'],str(run/'code/scripts/recovery/skill_pipeline/diagnose_rgbd_bowl_constraints.py'),
   '--worker','--problem',str(input_path),'--out-dir',str(destination),'--capture']
  (run/(case.name+'.preflight.command.json')).write_text(json.dumps(dict(argv=argv,env={k:env[k] for k in command['env']},
   overlay=str(run/'runtime_overlay'),source_problem_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),indent=2))
  with (run/(case.name+'.preflight.log')).open('wb') as log:
   rc=subprocess.run(argv,env=env,cwd=run/'runtime_overlay',stdout=log,stderr=subprocess.STDOUT,timeout=240).returncode
  row=dict(case=case.name,exit_code=rc)
  if (destination/'result.json').exists():
   r=json.loads((destination/'result.json').read_text());row.update({k:r.get(k) for k in ['available','feasible','num_satisfying','failure_reason']})
   if r['feasible']:feasible.append(case.name)
  records.append(row);(run/'preflight_progress.json').write_text(json.dumps(records,indent=2));print(row,flush=True)
  break
(run/'preflight_finished.json').write_text(json.dumps(records,indent=2))
if feasible:
 argv=[str(root/'envs/rlinf-openpi/bin/python'),str(run/'code/scripts/recovery/skill_pipeline/run_observed_rack_recovery.py'),
  '--root',str(root),'--run',str(run),'--collision-policy','oracle_cheese_rack_contacts_v1',
  '--tracking-gap-steps','10','--tracking-gap-seconds','0.5','--release-pose-constraint','--wrist-fallback','--plane-ids',*feasible]
 (run/'replay_driver.command.json').write_text(json.dumps(dict(argv=argv),indent=2))
 with (run/'batch_driver.log').open('wb') as log:
  rc=subprocess.run(argv,env=dict(os.environ,PYTHONPATH=str(run/'code'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),
   cwd=run/'code',stdout=log,stderr=subprocess.STDOUT,timeout=1100).returncode
 (run/'coordinator_finished.json').write_text(json.dumps(dict(replay_exit_code=rc,selected_planes=feasible)))
else:
 (run/'coordinator_finished.json').write_text(json.dumps(dict(selected_planes=[],reason='No feasible native release preflight; no simulator created')))
