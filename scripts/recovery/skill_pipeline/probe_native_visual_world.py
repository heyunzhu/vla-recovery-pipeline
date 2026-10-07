"""Instantiate the real cuTAMP visual world on CPU; never solve or step an environment."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--problem-json',type=Path,required=True)
    parser.add_argument('--out-file',type=Path,required=True)
    args=parser.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    # Set before importing torch/warp. This probe needs no GPU reservation.
    os.environ['CUDA_VISIBLE_DEVICES']=''
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
            RealCuTAMPBackend,RealCuTAMPBackendConfig,_problem_from_dict)
        from experiments.robot.libero.tiptop_repro.visual_cutamp_state import build_observed_initial_state
        raw=args.problem_json.read_bytes();payload=json.loads(raw)
        cfg=RealCuTAMPBackendConfig(**payload['config'])
        if cfg.initial_state_source!='rgbd_observed':raise ValueError('visual config required')
        problem=_problem_from_dict(payload['problem'])
        if problem.to_dict()!=payload['problem']:raise ValueError('problem serialization changed')
        env,names,notes,geometry=RealCuTAMPBackend(cfg)._build_env(problem)
        state,symbolic,reason=build_observed_initial_state(env,problem,names,cfg)
        import torch
        if torch.cuda.is_initialized():raise RuntimeError('unexpected CUDA initialization')
        if not any(obj.name==problem.surfaces[0].name for obj in env.statics):raise ValueError('goal surface lost collision representation')
        report=dict(status='native_visual_world_constructed',problem_sha256=hashlib.sha256(raw).hexdigest(),
            snapshot_id=problem.q_init_debug['rgbd_snapshot_id'],movable_count=len(env.movables),
            static_count=len(env.statics),native_environment_type=type(env).__module__+'.'+type(env).__name__,
            native_geometry_types=sorted({type(obj).__module__+'.'+type(obj).__name__ for obj in env.movables+env.statics}),
            versions={name:importlib.metadata.version(name) for name in ('torch','numpy','warp-lang','cuTAMP','nvidia_curobo')},
            geometry_debug=geometry,symbolic_initial_state_debug=symbolic,initial_state_blocker=reason,
            initial_state_size=len(state),blocked_oracle_import_attempts=guard.blocked_import_attempts,
            cuda_initialized=False,solver_called=False,environment_actions=0,execution_allowed=False)
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('geometry_debug','symbolic_initial_state_debug')},indent=2))


if __name__=='__main__':main()
