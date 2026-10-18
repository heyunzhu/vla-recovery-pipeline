from pathlib import Path
import json,numpy as np
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.visual_bottle_tracker import BottleColorDepthTracker
r=Path(__file__).parent
d=next(r.glob('visual_nomination*/recovery01/pre_solver_attempt01/agentview'))
v=json.loads((d/'visual_scene.json').read_text());b=json.loads((d/'binding.json').read_text());model=json.loads((d/'bottle_model.json').read_text());mask=np.load(d/'detections.npz')['masks'][next(o['detection_index'] for o in v['objects'] if o['id']==b['target_id'])]
start=r/'snapshots/recovery01/pre_solver_attempt01/agentview';frame=load_observation(start);tracker=BottleColorDepthTracker(frame,mask,model);rows=[]
paths=list((r/'snapshots/recovery01').glob('execution*/agentview'))+[r/'snapshots/recovery01/final/agentview'];paths.sort(key=lambda p:json.loads((p/'metadata.json').read_text())['env_step'])
for p in paths:
 f=load_observation(p)
 if f.env_step<=frame.env_step:continue
 try:
  current,report=tracker.update(f);row=dict(status='measured',**report)
 except ValueError as e:row=dict(env_step=f.env_step,status='unresolved',reason=str(e))
 rows.append(row);print(json.dumps(row),flush=True)
(r/'tracking_sequence_diagnostic.json').write_text(json.dumps(rows,indent=2));print('measured',sum(x['status']=='measured' for x in rows),'total',len(rows),flush=True)
