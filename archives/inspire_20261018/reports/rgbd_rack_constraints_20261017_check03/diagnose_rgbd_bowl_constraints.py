"""Offline diagnosis of a saved RGB-D bowl placement problem; no env actions.

Native box dimensions are patched only inside diagnostic worker processes.
The frozen runtime and reference recovery files are never edited.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys


def worker(args):
    import numpy as np
    import torch
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    from experiments.robot.libero.tiptop_repro import real_cutamp_backend as backend
    from cutamp.cost_function import CostFunction
    from cutamp.utils.common import transform_spheres

    raw = json.loads(args.problem.read_text())
    problem = copy.deepcopy(raw['problem'])
    wall_names = set(args.wall_names)
    if args.variant == 'no_walls':
        problem['statics'] = [o for o in problem['statics'] if o['name'] not in wall_names]
    original_dims = backend._cuboid_dims
    dimensions = {}

    def diagnostic_dims(obj, cfg):
        old = original_dims(obj, cfg)
        exact = (obj.role == 'static' and str(obj.geometry.get('source','')).startswith('rgbd_')
                 and (args.variant == 'exact_all' or
                      (args.variant == 'exact_walls' and obj.name in wall_names)))
        new = [max(2*float(v), .0002) for v in obj.half_extents] if exact else old
        dimensions[obj.name] = dict(native_before=old, native_used=new, source_half_extents=obj.half_extents)
        return new

    backend._cuboid_dims = diagnostic_dims
    latest = {}
    original_call = CostFunction.__call__

    def captured_call(self, rollout):
        costs = original_call(self, rollout)
        latest.update(instance=self, rollout=rollout, costs=costs)
        return costs

    if args.capture:
        CostFunction.__call__ = captured_call
    payload = dict(raw, problem=problem)
    args.out_dir.mkdir(exist_ok=False)
    (args.out_dir/'problem.json').write_text(json.dumps(payload,indent=2))
    cfg = backend.RealCuTAMPBackendConfig(**raw['config'])
    result = backend.RealCuTAMPBackend(cfg)._solve_in_process(backend._problem_from_dict(problem))
    (args.out_dir/'result.json').write_text(json.dumps(result.to_dict(),indent=2))
    (args.out_dir/'native_dimensions.json').write_text(json.dumps(dimensions,indent=2))
    if latest:
        cf, rollout, costs = latest['instance'],latest['rollout'],latest['costs']
        arrays, metrics = {}, {}
        for group, values in costs.items():
            for key, tensor in values.get('values',{}).items():
                array = tensor.detach().cpu().numpy()
                arrays[f'{group}__{key}'] = array
                metrics[f'{group}.{key}'] = dict(shape=list(array.shape), minimum=float(array.min()),
                    median=float(np.median(array)), maximum=float(array.max()))
        with torch.no_grad():
            for key in ['robot_spheres', 'confs']:
                if torch.is_tensor(rollout.get(key)):
                    arrays[key] = rollout[key].detach().cpu().numpy()
            for obj in cf.world.movables:
                pose = rollout['obj_to_pose'][obj.name]
                arrays['pose__'+obj.name] = pose.detach().cpu().numpy()
                spheres = transform_spheres(cf.world.get_collision_spheres(obj),pose)
                arrays['spheres__'+obj.name] = spheres.detach().cpu().numpy()
        surfaces = {}
        for name,z in cf.surface_to_target_z.items():
            obb = cf.surface_to_obb.get(name)
            surfaces[name] = dict(target_bottom_z=float(z),
                obb_center=None if obb is None else obb.center.detach().cpu().tolist(),
                obb_half_extents=None if obb is None else obb.half_extents.detach().cpu().tolist())
        trace = dict(metrics=metrics, action_to_pose_ts=rollout['action_to_pose_ts'],
            surface_constraints=surfaces, collision_activation_distance=float(cf.world.collision_activation_distance),
            mask_initial_movable_world_collision=cf.config.mask_initial_movable_world_collision,
            placement_check=cf.config.placement_check, placement_shrink_dist=cf.config.placement_shrink_dist,
            manipulated_objects=list(cf._activated_objs), first_place_ts=cf.obj_to_first_pose_ts)
        trace['world_cuboids'] = [dict(name=o.name, pose=list(o.pose), dims=list(o.dims))
            for o in cf.world.world_cfg.cuboid]
        np.savez_compressed(args.out_dir/'final_particles.npz',**arrays)
        (args.out_dir/'constraint_trace.json').write_text(json.dumps(trace,indent=2))
    print(json.dumps(dict(variant=args.variant,seed=args.seed,feasible=result.feasible,
                          satisfying=result.num_satisfying,failure=result.failure_reason)),flush=True)


def batch(args):
    root = Path(os.environ['ROOT'])
    reference = args.reference
    command = json.loads((reference/'command.json').read_text())
    env = dict(os.environ)
    env.update(command['env'])
    env.update(REAL_CUTAMP_BACKEND_CHILD='1',CUTAMP_CONTACT_MODE_TARGET='1',
               CUTAMP_ALLOW_START_COLLISION_ESCAPE='1',CUTAMP_START_ESCAPE_Z='0.08')
    args.out_dir.mkdir(exist_ok=False)
    (args.out_dir/'DIAGNOSTIC_ONLY.txt').write_text('Offline solver tests only; no simulator or robot actions.')
    obstacles = json.loads((reference/'visual_nomination_step50/recovery01/pre_solver_attempt01/agentview/obstacles.json').read_text())
    wall_count = obstacles['bowl_observed_wall_box_count']
    count = len(obstacles['centres'])
    walls = [f'rgbd_obstacle_{i:04d}' for i in range(count-wall_count,count)]
    (args.out_dir/'manifest.json').write_text(json.dumps(dict(
        reference=str(reference),problem=str(args.problem),problem_sha256=hashlib.sha256(args.problem.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), wall_names=walls,
        runtime_head=subprocess.check_output(['git','-C',str(root/'logs/continual_skill_core60_pilot_20261006/runtime_repo'),'rev-parse','HEAD'],text=True).strip()),indent=2))
    runs = [('baseline',0),('exact_walls',0),('no_walls',0),('exact_all',0),('baseline',1),('exact_walls',1)]
    records = []
    for variant,seed in runs:
        destination = args.out_dir/f'{variant}_seed{seed}'
        argv = [env['CUTAMP_REAL_RUNNER'],str(Path(__file__).resolve()),'--worker','--problem',str(args.problem),
                '--out-dir',str(destination),'--variant',variant,'--seed',str(seed),'--wall-names',*walls]
        if seed == 0:
            argv.append('--capture')
        (args.out_dir/f'{variant}_seed{seed}.command.json').write_text(json.dumps(dict(argv=argv,env={k:env[k] for k in command['env']}),indent=2))
        with (args.out_dir/f'{variant}_seed{seed}.log').open('wb') as log:
            proc = subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        record = dict(variant=variant,seed=seed,exit_code=proc.returncode)
        if (destination/'result.json').exists():
            result = json.loads((destination/'result.json').read_text())
            record.update(feasible=result['feasible'],num_satisfying=result['num_satisfying'],
                          failure_reason=result['failure_reason'])
        records.append(record)
        (args.out_dir/'progress.json').write_text(json.dumps(records,indent=2))
    (args.out_dir/'finished.json').write_text(json.dumps(records,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--problem',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--variant',choices=['baseline','exact_walls','exact_all','no_walls'],default='baseline')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--wall-names',nargs='*',default=[])
    parser.add_argument('--capture',action='store_true')
    args=parser.parse_args()
    worker(args) if args.worker else batch(args)


if __name__=='__main__':
    main()
