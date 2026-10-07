"""Capture native movable spheres and isolate collision costs without changing the full world."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('problem-json','cpu-result','out-file'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--gpu',type=int,required=True)
    args=parser.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from scripts.recovery.skill_pipeline.probe_native_visual_planner import validate_inputs,check_unused_gpu
    raw=args.problem_json.read_bytes();payload=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
    validate_inputs(payload,json.loads(args.cpu_result.read_text()),digest);gpu=check_unused_gpu(args.gpu)
    os.environ['CUDA_VISIBLE_DEVICES']=str(args.gpu)
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        import torch
        from experiments.robot.libero.skill_pipeline.visual_proxy_overlap import sphere_cuboid_penetrations
        from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
            RealCuTAMPBackend,RealCuTAMPBackendConfig,_problem_from_dict,_runtime_robot_alignment_debug)
        from cutamp.tamp_world import TAMPWorld
        from cutamp.utils.common import transform_spheres,pose_list_to_mat4x4
        from cutamp.utils.collision import get_world_collision_cost
        from curobo.geom.types import WorldConfig
        from curobo.types.base import TensorDeviceType
        cfg=RealCuTAMPBackendConfig(**payload['config']);problem=_problem_from_dict(payload['problem'])
        env,_,_,_=RealCuTAMPBackend(cfg)._build_env(problem);tensor_args=TensorDeviceType()
        alignment=_runtime_robot_alignment_debug(cfg.robot,problem.q_init,problem.q_init_debug)
        world=TAMPWorld(env,tensor_args,cfg.robot,tensor_args.to_device(problem.q_init))
        movable=env.movables[0]
        spheres=transform_spheres(world.get_collision_spheres(movable),pose_list_to_mat4x4(movable.pose,tensor_args))
        values=spheres.detach().cpu().numpy();query=spheres[None,None].contiguous()
        full_cost=float(world.collision_fn(query).sum().item());components=[]
        for obj in env.statics:
            if not np.array_equal(obj.pose[3:],[1,0,0,0]):raise ValueError('axis-aligned visual cuboid required')
            penetration=sphere_cuboid_penetrations(values,obj.pose[:3],np.asarray(obj.dims)/2)
            if not np.any(penetration>0):continue
            cost_fn=get_world_collision_cost(WorldConfig(cuboid=[obj]),tensor_args,0)
            cost=float(cost_fn(query).sum().item())
            components.append(dict(name=obj.name,native_single_obstacle_cost=cost,
                sphere_overlap_count=int(np.sum(penetration>0)),analytic_penetration_sum_m=float(penetration.sum())))
        report=dict(scope='native_initial_collision_attribution_new_sphere_sample',problem_sha256=digest,
            gpu_prelaunch=gpu,target=movable.name,native_spheres_base_m=values.tolist(),full_world_cost=full_cost,
            single_obstacle_cost_sum=sum(r['native_single_obstacle_cost'] for r in components),components=components,
            robot_alignment_debug=alignment,blocked_oracle_import_attempts=guard.blocked_import_attempts,
            solver_called=False,environment_actions=0,execution_allowed=False,
            limitations=['new native random sphere sample; not the exact spheres from the first failed solver call',
                'single-obstacle diagnostics are not a collision-free certificate',
                'visible proxy intersection does not establish physical contact'])
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps(dict(full_world_cost=full_cost,sphere_count=len(values),component_count=len(components),
            robot_alignment_debug=alignment),indent=2))


if __name__=='__main__':main()
