"""Bounded native GPU planner probe from frozen RGB-D evidence, without environment actions."""
import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import math
from datetime import datetime,timezone


def validate_inputs(payload,cpu,problem_sha256):
    if (cpu.get('status')!='native_visual_world_constructed' or cpu.get('problem_sha256')!=problem_sha256
            or cpu.get('initial_state_blocker') is not None or cpu.get('initial_state_size',0)<=0
            or cpu.get('blocked_oracle_import_attempts')!=0 or cpu.get('cuda_initialized') is not False):
        raise ValueError('matching successful CPU world and initial-state evidence required')
    cfg=payload['config']
    if (cfg.get('initial_state_source')!='rgbd_observed' or not cfg.get('curobo_plan')
            or not cfg.get('serialize_trajectories') or cfg.get('apply_simulator_truth_initial_state')
            or cfg.get('enable_initial_holding_prebinding') or cfg.get('accept_optimized_plan_if_motiongen_fails')
            or cfg.get('project_motiongen_start_joint_limits') or cfg.get('runner_python')
            or cfg.get('diagnostic_constraint_mult_overrides') or cfg.get('diagnostic_constraint_tol_overrides')):
        raise ValueError('strict visual native planner configuration required')
    if any(not isinstance(cfg.get(k),(int,float)) or not math.isfinite(cfg[k]) or cfg[k]<=0
           for k in ('num_particles','num_opt_steps','max_loop_dur')):
        raise ValueError('positive finite bounded planner settings required')
    if cpu.get('snapshot_id')!=payload['problem']['q_init_debug'].get('rgbd_snapshot_id'):
        raise ValueError('CPU snapshot mismatch')


def check_unused_gpu(index):
    # This is a fresh prelaunch observation, not a reservation of a shared card.
    command=['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits']
    lines=subprocess.check_output(command,text=True,timeout=15).strip().splitlines()
    matching=[line.split(',') for line in lines if int(line.split(',')[0])==index]
    if len(matching)!=1:raise ValueError('GPU index missing')
    _,uuid,memory,util=[x.strip() for x in matching[0]]
    processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True,timeout=15)
    if int(memory)>256 or int(util)!=0 or any(line.split(',')[0].strip()==uuid for line in processes.splitlines()):
        raise RuntimeError('requested shared GPU is occupied; probe not started')
    return dict(index=index,uuid=uuid,memory_used_mib=int(memory),utilization_percent=int(util),
        checked_at_utc=datetime.now(timezone.utc).isoformat(),compute_processes=[])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('problem-json','cpu-result','out-file'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--gpu',type=int,required=True)
    args=parser.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    raw=args.problem_json.read_bytes();payload=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
    cpu=json.loads(args.cpu_result.read_text());validate_inputs(payload,cpu,digest)
    gpu=check_unused_gpu(args.gpu)
    os.environ['CUDA_VISIBLE_DEVICES']=str(args.gpu)
    os.environ['CUTAMP_ALLOW_START_COLLISION_ESCAPE']='0'
    os.environ['CUTAMP_CONTACT_MODE_TARGET']='0'
    os.environ['CUTAMP_START_ESCAPE_Z']='0'
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
            RealCuTAMPBackend,RealCuTAMPBackendConfig,_problem_from_dict)
        import numpy as np
        import torch
        if torch.cuda.device_count()!=1:raise RuntimeError('exactly one selected CUDA device required')
        np.random.seed(0);torch.manual_seed(0)
        cfg=RealCuTAMPBackendConfig(**payload['config'])
        cfg=dataclasses.replace(cfg,num_particles=min(cfg.num_particles,128),num_opt_steps=min(cfg.num_opt_steps,60),
            max_loop_dur=min(cfg.max_loop_dur,30),debug_dir=str(args.out_file.parent/'planner_debug'))
        result=RealCuTAMPBackend(cfg).solve(_problem_from_dict(payload['problem']))
        report=dict(scope='native_gpu_planning_from_frozen_visual_evidence',problem_sha256=digest,
            cpu_result_sha256=hashlib.sha256(args.cpu_result.read_bytes()).hexdigest(),gpu_prelaunch=gpu,
            config=dataclasses.asdict(cfg),result=result.to_dict(),blocked_oracle_import_attempts=guard.blocked_import_attempts,
            solver_entry_called=True,environment_actions=0,execution_allowed=False,
            task_success_verified=False,physical_hand_state_verified=False)
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps(dict(available=result.available,feasible=result.feasible,failure_reason=result.failure_reason,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,environment_actions=0),indent=2))


if __name__=='__main__':main()
