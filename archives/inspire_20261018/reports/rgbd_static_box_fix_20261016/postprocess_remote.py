from pathlib import Path
import json,hashlib,shutil
import numpy as np
from PIL import Image
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
run=root/'logs/rgbd_static_box_fix_20261016'
assert (run/'strict_bowl_finished.json').exists()
assert (run/'finished.json').exists()
assets=run/'report_assets';assets.mkdir(exist_ok=True)
for name,case,phase in [('bowl_before','bowl_strict_acceptance','entry'),('bowl_tracking_failure','bowl_strict_acceptance','failure'),('plate_success','plate_regression','final')]:
 with np.load(run/case/'snapshots/recovery01'/phase/'agentview/rgbd.npz') as d:
  Image.fromarray(d['rgb']).save(assets/(name+'.png'))
phases=run/'bowl_strict_acceptance/snapshots/recovery01'
sequence=[phases/'entry']+sorted(phases.glob('execution_step*'))+[phases/'failure']
frames=[]
for phase in sequence:
 with np.load(phase/'agentview/rgbd.npz') as d:frames.append(Image.fromarray(d['rgb']).resize((480,480)))
frames[0].save(assets/'bowl_recovery.gif',save_all=True,append_images=frames[1:],duration=[750]+[250]*(len(frames)-2)+[1000],loop=0)
ref=root/'logs/rgbd_labeled_obstacles_20261016/bowl/visual_nomination_step50/recovery01/pre_solver_attempt01/agentview'
cur=run/'bowl_strict_acceptance/visual_nomination_step50/recovery01/pre_solver_attempt01/agentview'
audit={}
for n in ['bottle_model.json','goal_support_model.json']:
 audit[n+'_unchanged']=json.loads((ref/n).read_text())==json.loads((cur/n).read_text())
with np.load(ref/'detections.npz') as a,np.load(cur/'detections.npz') as b:
 audit['detection_arrays_unchanged']=a.files==b.files and all(np.array_equal(a[n],b[n]) for n in a.files)
a=json.loads((ref/'obstacles.json').read_text());b=json.loads((cur/'obstacles.json').read_text())
audit['obstacle_centres_unchanged']=a['centres']==b['centres']
audit['obstacle_half_extents_unchanged']=a['half_extents']==b['half_extents']
audit['wall_count']=b['bowl_observed_wall_box_count'];audit['static_box_count']=len(b['centres'])
m=json.loads((run/'manifest.json').read_text())
audit['historical_backend_unchanged']=m['runtime_backend_sha256_before']==m['runtime_backend_sha256_after']==hashlib.sha256((Path(m['runtime_reference'])/'experiments/robot/libero/tiptop_repro/real_cutamp_backend.py').read_bytes()).hexdigest()
(run/'validation_audit.json').write_text(json.dumps(audit,indent=2))
source=run/'repro_sources';source.mkdir(exist_ok=False)
staging=root/'logs/rgbd_static_box_fix_20261016_staging'
for p in staging.rglob('*'):
 if p.is_file():
  dest=source/p.relative_to(staging);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
summary={}
for n in ['bowl','plate_regression','bowl_strict_acceptance']:
 f=run/n/'replay_result.json';f=f if f.exists() else run/n/'failure_result.json'
 d=json.loads(f.read_text())
 summary[n]={k:v for k,v in d.items() if k!='attempts'}
 if 'attempts' in d:
  summary[n]['attempts']=[{k:a.get(k) for k in ['selected_skeleton','executed_steps','num_env_steps','success_during_recovery','feasible']} for a in d['attempts']]
 summary[n]['event_count']=len(json.loads((run/n/'execution_events.json').read_text()))
summary['saved_problem']={k:v for k,v in json.loads((run/'saved_problem/result.json').read_text()).items() if k in ['feasible','num_satisfying','failure_reason','elapsed_sec']}
summary['audit']=audit
(run/'run_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
