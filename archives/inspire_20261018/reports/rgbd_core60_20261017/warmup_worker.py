
from pathlib import Path
import json,os,numpy as np
from multiprocessing.connection import Client
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');run=root/'logs/rgbd_core60_20261017'
from experiments.robot.libero import skill_pipeline
skill_pipeline.__path__.insert(0,str(run/'code/experiments/robot/libero/skill_pipeline'))
from experiments.robot.libero.skill_pipeline import runner
print('RUNNER_MODULE',runner.__file__,flush=True)
from experiments.robot.libero.skill_pipeline.visual_language_prompts import parse_visual_pick_place_language
supported=[];unsupported=[]
for r in json.loads((run/'requested_cases.json').read_text())[::5]:
 try:parse_visual_pick_place_language(r['language']);supported.append(r['case_id'])
 except Exception as e:unsupported.append(dict(case_id=r['case_id'],language=r['language'],reason=str(e)))
(run/'language_census.json').write_text(json.dumps(dict(supported=supported,unsupported=unsupported),indent=2))
ep=json.loads((run/'policy_endpoint.json').read_text())
def connect(seed):
 c=Client(tuple(ep['address']),authkey=bytes.fromhex(ep['authkey']));c.send(('start',dict(config_name='pi0_libero',checkpoint_dir=str(root/'models/pi0_libero_openpi'),seed=seed)));assert c.recv()[0]=='ok';return c
def call(c,cmd,payload=None):
 c.send((cmd,payload));assert c.poll(600);status,result=c.recv()
 if status!='ok':raise RuntimeError(result)
 return result
obs={'observation/image':np.zeros((256,256,3),np.uint8),'observation/wrist_image':np.zeros((256,256,3),np.uint8),'observation/state':np.zeros(8,np.float32),'prompt':'put the cheese on the rack'}
a=connect(90);b=connect(91);call(a,'reset');a1=call(a,'infer',obs);b1=call(b,'infer',obs);call(a,'reset');a2=call(a,'infer',obs)
x=np.asarray(a1['output']['actions']);y=np.asarray(a2['output']['actions'])
assert np.isfinite(x).all() and np.allclose(x,y,atol=1e-6)
report=dict(actions_shape=list(x.shape),reset_max_diff=float(np.max(np.abs(x-y))),different_seed_max_diff=float(np.max(np.abs(x-np.asarray(b1['output']['actions'])))),language_supported=len(supported),language_unsupported=len(unsupported),runner_module=runner.__file__)
(run/'policy_warmup_passed.json').write_text(json.dumps(report,indent=2));print('PASSED',report,flush=True)
a.close();b.close()
