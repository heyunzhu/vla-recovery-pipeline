from pathlib import Path
import json,copy,subprocess,os,hashlib
import numpy as np
from scipy.spatial.transform import Rotation
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');run=Path(__file__).parent
ref=root/'logs/rgbd_rack_placement_20261016_replay07'
gtpath=root/'logs/rgbd_ten_tasks_20261015/03_goal_cheese_rack/oracle/cutamp_debug/solve_1792034118342_67675.problem.json'
gt=json.loads(gtpath.read_text());visual=json.loads((ref/'plane_00/cutamp_debug/solve_1792149055213_55213.problem.json').read_text())
command=json.loads((ref/'plane_00/command.json').read_text());env=dict(os.environ,**command['env']);env['REAL_CUTAMP_BACKEND_CHILD']='1'
def transform(raw):
 d=raw['problem']['q_init_debug']['world_to_planner_frame'];q=d['quat_world_wxyz'];t=np.eye(4);t[:3,:3]=Rotation.from_quat(q[1:]+q[:1]).as_matrix();t[:3,3]=d['origin_world'];return t
t=np.linalg.inv(transform(gt))@transform(visual)
def pose(pos,q):
 x=t[:3,:3]@np.asarray(pos)+t[:3,3];r=Rotation.from_matrix(t[:3,:3])*Rotation.from_quat(q[1:]+q[:1]);q=r.as_quat();return x.tolist(),np.r_[q[3],q[:3]].tolist()
def observed_target():
 obj=copy.deepcopy(visual['problem']['movables'][0]);obj['name']=gt['problem']['movables'][0]['name']
 obj['pos'],obj['quat']=pose(obj['pos'],obj['quat']);geom=obj['geometry'];geom['center']=obj['pos']
 for part in geom['metadata']['collision_parts']:
  part['pos'],part['quat']=pose(part['pos'],part['quat'])
 # Relative local transforms are unchanged under a common left transform.
 return obj
records=[]
for name,hard_bowl,hard_rack,use_observed in [('oracle_original',False,False,False),('oracle_bowl_hard',True,False,False),('oracle_bowl_rack_hard',True,True,False),('oracle_visual_target',False,False,True),('oracle_visual_target_bowl_hard',True,False,True)]:
 raw=copy.deepcopy(gt)
 if hard_bowl:
  for surface in raw['problem']['surfaces']:surface['geometry'].get('metadata',{}).pop('allowed_contact_objects',None)
 if use_observed:raw['problem']['movables']=[observed_target()]
 problem=run/(name+'.problem.json');problem.write_text(json.dumps(raw))
 out=run/name;argv=[env['CUTAMP_REAL_RUNNER'],str(run/'worker.py'),'--problem',str(problem),'--out-dir',str(out)]
 if hard_rack:argv.append('--hard-rack')
 (run/(name+'.command.json')).write_text(json.dumps(dict(argv=argv,env=command['env'],input_sha256=hashlib.sha256(problem.read_bytes()).hexdigest(),oracle_input_sha256=hashlib.sha256(gtpath.read_bytes()).hexdigest()),indent=2))
 with (run/(name+'.log')).open('wb') as log:
  try:rc=subprocess.run(argv,env=env,cwd=ref/'runtime_overlay',stdout=log,stderr=subprocess.STDOUT,timeout=240).returncode
  except subprocess.TimeoutExpired:rc=124
 row=dict(name=name,exit_code=rc,hard_bowl=hard_bowl,hard_rack=hard_rack,observed_target=use_observed)
 if (out/'result.json').exists():
  result=json.loads((out/'result.json').read_text());row.update({k:result.get(k) for k in ['available','feasible','num_satisfying','failure_reason']})
 records.append(row);(run/'progress.json').write_text(json.dumps(records,indent=2));print(row,flush=True)
(run/'finished.json').write_text(json.dumps(records,indent=2))
