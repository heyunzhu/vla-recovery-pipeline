from pathlib import Path
import json
from dataclasses import fields
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend,RealCuTAMPBackendConfig,_problem_from_dict
from cutamp.tamp_world import TAMPWorld
from cutamp.utils.common import pose_list_to_mat4x4,transform_spheres
from curobo.types.base import TensorDeviceType
run=Path(__file__).parent
rows=[]
paths=[next((run/"cutamp_debug").glob("*problem*.json")),run/"visual_geometry_diagnostic/problem.json"]
for path in paths:
 payload=json.loads(path.read_text())
 known={f.name for f in fields(RealCuTAMPBackendConfig)}
 ignored={k:v for k,v in payload["config"].items() if k not in known}
 if any(v not in ({},None,[]) for v in ignored.values()):raise ValueError(f"unsupported config: {ignored}")
 cfg=RealCuTAMPBackendConfig(**{k:v for k,v in payload["config"].items() if k in known})
 problem=_problem_from_dict(payload["problem"])
 env,_,_,_=RealCuTAMPBackend(cfg)._build_env(problem)
 ta=TensorDeviceType()
 world=TAMPWorld(env,ta,cfg.robot,ta.to_device(problem.q_init))
 obj=env.movables[0]
 transform=pose_list_to_mat4x4(obj.pose).to(device=ta.device,dtype=ta.dtype)
 spheres=transform_spheres(world.get_collision_spheres(obj),transform)
 cost=float(world.collision_fn(spheres[None,None].contiguous()).sum().item())
 rows.append(dict(input=str(path),sphere_count=int(spheres.shape[0]),initial_target_collision_cost=cost,environment_actions=0,solver_called=False))
print(json.dumps(rows,indent=2))
(run/"collision_comparison.json").write_text(json.dumps(rows,indent=2))
