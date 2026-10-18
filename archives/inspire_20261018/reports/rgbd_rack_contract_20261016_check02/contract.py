from pathlib import Path
from types import SimpleNamespace
import os,json,shutil,runpy,sys
from unittest.mock import patch
import numpy as np
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');run=root/'logs/rgbd_rack_contract_20261016_check02';code=run/'code';base=root/'logs/rgbd_rack_placement_20261016_replay06'
sys.path.append(str(code));import experiments.robot.libero.skill_pipeline as pipeline;pipeline.__path__.insert(0,str(code/'experiments/robot/libero/skill_pipeline'))
case=run/'case';case.mkdir();shutil.copytree(base/'plane_00/capture_support',case/'capture_support');shutil.copytree(base/'plane_00/snapshots',case/'snapshots')
sys.path.insert(0,str(case/'capture_support'))
config=json.loads((base/'plane_00/observed_config.json').read_text());(case/'observed_config.json').write_text(json.dumps(config))
command=json.loads((base/'plane_00/command.json').read_text());e=command['env'];e.update(ANCHOR_VISUAL_CODE=str(code),ANCHOR_CAPTURE_DIR=str(case/'snapshots'),ANCHOR_OBSERVED_PLACEMENT_CONFIG=str(case/'observed_config.json'));os.environ.update(e)
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
frame=load_observation(case/'snapshots/recovery01/pre_solver_attempt01/agentview')
ref=base/'plane_00/resident_vision/step00055'
wref=root/'logs/rgbd_box_geometry_20261016/perception/recovery01/pre_solver_attempt01/robot0_eye_in_hand'
class Seg:
 def __init__(self,*a,**kw):self.worker=self
 def __call__(self,frame):return np.load(ref/'masks.npz')['masks'],json.loads((ref/'result.json').read_text())
 def request(self,request):
  with np.load(wref/'detections.npz') as a:np.savez_compressed(request['output'],masks=a['masks'])
  return dict(categories=[d['category'] for d in json.loads((wref/'detections.json').read_text())['detections']])
 def close(self):pass
with patch('experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker.ResidentSegmentation',Seg):
 runpy.run_path(str(code/'scripts/recovery/skill_pipeline/observed_geometry_recovery_hook.py'))
 from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as ctl
 env=SimpleNamespace(_anchor_control_steps=55,step=lambda *a,**kw:None)
 obs={k:np.array(v) for k,v in frame.robot_state.items()}
 cfg=ctl.CuTAMPV2Config()
 result=ctl.CuTAMPV2OraclePerceiver(cfg).perceive(env,obs,'Put the cream cheese on the rack')
 problem=result[3]
 print('PROBLEM',len(problem.movables),len(problem.surfaces),len(problem.statics))
 print('SOURCES',[o.geometry['source'] for o in problem.movables+problem.surfaces])
 print('GOAL',problem.goal_atoms)
 (run/'contract_passed.json').write_text(json.dumps(dict(movables=len(problem.movables),surfaces=len(problem.surfaces),statics=len(problem.statics),environment_created=False)))
