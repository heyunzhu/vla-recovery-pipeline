from pathlib import Path
import json,sys,numpy as np
from scipy.ndimage import label
from scipy.optimize import least_squares
sys.path.insert(0,str(Path.cwd()))
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.visual_bottle_tracker import BottleColorDepthTracker
from experiments.robot.libero.skill_pipeline.visual_bottle_geometry import connected_depth_surface
r=Path('analysis_outputs/rgbd_static_box_fix_20261016/remote/bowl_strict_acceptance')
s=r/'snapshots/recovery01'
d=r/'visual_nomination_step50/recovery01/pre_solver_attempt01/agentview'
f0=load_observation(s/'pre_solver_attempt01/agentview')
mask=np.load(d/'detections.npz')['masks'][1]
model=json.loads((d/'bottle_model.json').read_text())
t=BottleColorDepthTracker(f0,mask,model)
frame=load_observation(s/'failure/agentview')
previous=json.loads((r/'visual_execution/step0124.json').read_text())
prediction=np.array(previous['axis_xy_world_m'])
world=t._world(frame)
colour=t._colour_mask(frame)&frame.depth_valid
components,n=label(colour,np.ones((3,3)))
rows=[]
for i in range(1,n+1):
 m=components==i
 if m.sum()<50:continue
 raw_count=int(m.sum())
 try:m,_=connected_depth_surface(world,m)
 except (TypeError,ValueError):continue
 points=world[m]
 record=dict(component=i,raw_count=raw_count,count=len(points),height_range_m=float(np.ptp(points[:,2])),median_distance_to_previous_axis_m=float(np.linalg.norm(np.median(points[:,:2],axis=0)-prediction)))
 if len(points)<50 or np.ptp(points[:,2])<.035:record['rejected']='point_count_or_height'
 elif record['median_distance_to_previous_axis_m']>.14:record['rejected']='search_distance'
 else:
  lower=points[points[:,2]<=np.quantile(points[:,2],.5),:2]
  def residual(xy):return np.linalg.norm(lower-xy,axis=1)-model['body_radius_m']
  fits=[least_squares(residual,prediction+off,loss='soft_l1',f_scale=.001) for off in (np.zeros(2),np.array([.02,0]),np.array([-.02,0]))]
  fit=min(fits,key=lambda f:np.median(abs(residual(f.x))))
  errors=abs(residual(fit.x))
  record.update(fitted_axis_xy_world_m=fit.x.tolist(),median_residual_m=float(np.median(errors)),q95_residual_m=float(np.quantile(errors,.95)),distance_to_previous_axis_m=float(np.linalg.norm(fit.x-prediction)))
  record['rejected']='residual' if np.median(errors)>.002 or np.quantile(errors,.95)>.005 else 'not_rejected_by_fit'
 rows.append(record)
out=dict(env_step=125,method='Saved failure frame; search is centered on last accepted axis, without unavailable step-124 EEF displacement. Geometry gates are the unchanged tracker gates.',previous=previous,components=rows,thresholds=dict(height_range_min_m=.035,median_residual_max_m=.002,q95_residual_max_m=.005))
Path('analysis_outputs/rgbd_static_box_fix_20261016/tracker_failure_analysis.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
