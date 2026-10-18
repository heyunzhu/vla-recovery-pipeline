from pathlib import Path
import json,numpy as np
from dataclasses import fields
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend,RealCuTAMPBackendConfig,_problem_from_dict
from cutamp.tamp_world import TAMPWorld
from cutamp.utils.common import pose_list_to_mat4x4,transform_spheres
from curobo.types.base import TensorDeviceType
r=Path(__file__).parent
payload=json.loads(next((r/'cutamp_debug').glob('*.problem.json')).read_text());known={f.name for f in fields(RealCuTAMPBackendConfig)}
cfg=RealCuTAMPBackendConfig(**{k:v for k,v in payload['config'].items() if k in known});problem=_problem_from_dict(payload['problem']);env,_,_,_=RealCuTAMPBackend(cfg)._build_env(problem)
ta=TensorDeviceType();world=TAMPWorld(env,ta,cfg.robot,ta.to_device(problem.q_init));obj=env.movables[0];transform=pose_list_to_mat4x4(obj.pose).to(device=ta.device,dtype=ta.dtype);spheres=transform_spheres(world.get_collision_spheres(obj),transform)
cost=float(world.collision_fn(spheres[None,None].contiguous()).sum().item());sp=spheres.cpu().numpy();rows=[]
for o in problem.statics:
 centre=np.array(o.pos);half=np.array(o.half_extents)
 gap=np.maximum(abs(sp[:,:3]-centre)-half,0);signed=np.linalg.norm(gap,axis=1)-sp[:,3]
 rows.append(dict(name=o.name,min_sphere_to_box_clearance_m=float(signed.min()),pos=o.pos,half_extents=o.half_extents))
rows.sort(key=lambda x:x['min_sphere_to_box_clearance_m']);out=dict(initial_target_collision_cost=cost,nearest_obstacles=rows[:20],native_world_fields=list(vars(world)),sphere_count=len(sp),environment_actions=0)
(r/'collision_diagnostic.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2),flush=True)
