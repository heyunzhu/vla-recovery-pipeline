from pathlib import Path
import json,subprocess,os,time,hashlib
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
reference=root/'logs/rgbd_rack_placement_20261016_replay07'
run=Path(__file__).parent
command=json.loads((reference/'plane_00/command.json').read_text())
env=dict(os.environ,**command['env']);env['REAL_CUTAMP_BACKEND_CHILD']='1'
jobs=[('holding40','target_dims','solve_1792149102851_55213'),
 ('holding200','target_dims','solve_1792149102851_55213'),
 ('holding200v1','target_dims','solve_1792149102851_55213'),
 ('place200','both','solve_1792149055213_55213')]
records=[]
for kind,variant,prefix in jobs:
 name=kind+'_'+variant;out=run/name
 problem=reference/'plane_00/cutamp_debug'/(prefix+'.problem.json')
 argv=[env['CUTAMP_REAL_RUNNER'],str(run/'diagnose_observed_rack_constraints.py'),
  '--problem',str(problem),'--out-dir',str(out),'--variant',variant]
 argv += ['--opt-steps','40' if kind=='holding40' else '200']
 if kind=='holding200v1':argv += ['--grasp-profile','cream_cheese_flat_box_topdown_deep_v1']
 (run/(name+'.command.json')).write_text(json.dumps(dict(argv=argv,env=command['env'],
  problem_sha256=hashlib.sha256(problem.read_bytes()).hexdigest()),indent=2))
 with (run/(name+'.log')).open('wb') as log:
  try:rc=subprocess.run(argv,env=env,cwd=reference/'runtime_overlay',stdout=log,stderr=subprocess.STDOUT,timeout=240).returncode
  except subprocess.TimeoutExpired:rc=124
 record=dict(name=name,exit_code=rc)
 if (out/'result.json').exists():
  r=json.loads((out/'result.json').read_text());record.update({k:r.get(k) for k in ['feasible','num_satisfying','failure_reason']})
 records.append(record);(run/'progress.json').write_text(json.dumps(records,indent=2));print(record,flush=True)
(run/'finished.json').write_text(json.dumps(records,indent=2))
